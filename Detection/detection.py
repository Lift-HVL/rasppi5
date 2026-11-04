"""detection.py - Pi side: send the camera video and the YOLO boxes to the ground station SEPARATELY.

The ground station (gs_viewer.py) puts them together. Video and detection run in different
threads, so the video stays smooth even when YOLO is slow; the boxes simply update less often.

    python3 detection.py --host 192.168.1.185 --source /dev/video0
    python3 detection.py --host 192.168.1.185 --source /dev/video0 --show     # also a window on the Pi
    python3 detection.py --list-cameras

Faster boxes on the Pi:
    yolo export model=best.pt format=ncnn imgsz=320   # once; creates best_ncnn_model/ (2-4x faster on ARM)
    python3 detection.py --host 192.168.1.185 --source /dev/video0 --model best_ncnn_model --imgsz 320

What is sent (both UDP, to --host):
  port 5600  video: JPEG frames split into packets (same format as camera_tx.py)
             header "CF" | frame id (uint32) | chunk index (uint16) | chunk count (uint16) | 0 (uint16)
  port 5010  detections, one JSON packet per YOLO run (also when nothing is found):
    {"type": "detections", "timestamp": ..., "frame": 123, "width": 1280, "height": 720,
     "inference_ms": 85.2,
     "detections": [{"id": 0, "name": "person", "conf": 0.91,
                     "box": [x1, y1, x2, y2], "center": [cx, cy], "offset": [dx, dy]}]}
  "frame" is the id of the video frame YOLO looked at, so the viewer can match boxes to video.
  Boxes are in camera pixels ("width" x "height"), the video is resized: scale on the receiver.
  "offset" is the box center relative to the image middle, -1..1 (dx > 0 = right, dy > 0 = below).
"""

import argparse
import glob
import json
import socket
import struct
import threading
import time

import cv2
from ultralytics import YOLO

HEADER = struct.Struct("!2sIHHH")
MAGIC = b"CF"
CHUNK = 1400

# The Pi 5's own video hardware shows up as /dev/video* too - these are never cameras
INTERNAL_DEVICES = ("pispbe", "rpi-hevc", "rp1-cfe", "bcm2835", "hevc", "isp")


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def device_name(dev: str) -> str:
    try:
        with open(f"/sys/class/video4linux/{dev.rsplit('/', 1)[-1]}/name") as f:
            return f.read().strip()
    except OSError:
        return ""


def list_cameras() -> None:
    devices = sorted(glob.glob("/dev/video*"), key=lambda d: int(d[10:]) if d[10:].isdigit() else 0)
    found = False
    for dev in devices or [str(i) for i in range(8)]:
        name = device_name(dev)
        if name.lower().startswith(INTERNAL_DEVICES):
            continue
        cap = cv2.VideoCapture(int(dev) if dev.isdigit() else dev)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        cap.release()
        if ok:
            print(f"{dev}: {frame.shape[1]}x{frame.shape[0]}  {name}")
            found = True
    if not found:
        print("No working cameras found")


def open_camera(source: str, width: int, height: int, fps: float, mjpg: bool) -> cv2.VideoCapture:
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
    elif source.startswith("/dev/video"):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(source)            # video file or stream URL
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera '{source}' - try --list-cameras")
    # Compressed MJPG first: uncompressed 1080p is too much for USB and gives ~2 fps
    if mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps:
        cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip("\x00") or "?"
    print(f"Camera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
          f"{fourcc} @ {cap.get(cv2.CAP_PROP_FPS):g} fps")
    return cap


def encode_jpeg(img, width: int, quality: int) -> bytes | None:
    h, w = img.shape[:2]
    if width and w > width:
        img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


def send_video_frame(sock, addr, frame_id: int, jpeg: bytes) -> None:
    count = (len(jpeg) + CHUNK - 1) // CHUNK
    if count > 65535:
        return
    for i in range(count):
        sock.sendto(HEADER.pack(MAGIC, frame_id, i, count, 0) + jpeg[i * CHUNK:(i + 1) * CHUNK], addr)


# ---------------------------------------------------------------------------
# Camera thread: reads every frame, keeps the newest for YOLO, sends the video
# ---------------------------------------------------------------------------

class CameraThread(threading.Thread):
    def __init__(self, cap, video_addr, video_width: int, quality: int, video_fps: float,
                 pace_fps: float = 0.0):
        super().__init__(daemon=True)
        self.cap = cap
        self.pace = 1.0 / pace_fps if pace_fps > 0 else 0.0   # video files: play at real speed
        self.video_addr = video_addr
        self.video_width = video_width
        self.quality = quality
        self.period = 1.0 / video_fps if video_fps > 0 else 0.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
        self.lock = threading.Lock()
        self.frame = None
        self.frame_id = 0
        self.error = None
        self.running = True

    def latest(self):
        with self.lock:
            return self.frame_id, self.frame

    def run(self) -> None:
        failures = 0
        next_send = 0.0
        sent, sent_bytes, stats_t = 0, 0, time.time()
        last_error = None
        next_read = time.time()
        while self.running:
            if self.pace:
                time.sleep(max(0.0, next_read - time.time()))
                next_read = max(next_read + self.pace, time.time() - self.pace)
            ok, frame = self.cap.read()
            if not ok:
                failures += 1
                if failures > 50:
                    self.error = "Camera stopped sending frames"
                    return
                time.sleep(0.05)
                continue
            failures = 0
            with self.lock:
                self.frame_id = (self.frame_id + 1) & 0xFFFFFFFF
                self.frame = frame
                fid = self.frame_id

            now = time.time()
            if self.video_addr and now >= next_send:
                next_send = now + self.period
                jpeg = encode_jpeg(frame, self.video_width, self.quality)
                if jpeg:
                    try:
                        send_video_frame(self.sock, self.video_addr, fid, jpeg)
                        sent += 1
                        sent_bytes += len(jpeg)
                        last_error = None
                    except OSError as e:
                        if str(e) != last_error:
                            print(f"[VIDEO] send failed: {e}")
                            last_error = str(e)

            if now - stats_t >= 5:
                dt = now - stats_t
                print(f"[VIDEO] {sent / dt:.1f} fps, {sent_bytes * 8 / dt / 1e6:.2f} Mbit/s")
                sent, sent_bytes, stats_t = 0, 0, now


# ---------------------------------------------------------------------------
# Main loop: YOLO on the newest frame, send the boxes
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Camera video + YOLO boxes -> ground station (separately, over UDP)")
    p.add_argument("--host", help="ground station IP")
    p.add_argument("--video-port", type=int, default=5600, help="UDP port for video (0 = no video)")
    p.add_argument("--det-port", type=int, default=5010, help="UDP port for detections")
    p.add_argument("--model", default="best.pt")
    p.add_argument("--conf", type=float, default=0.5, help="minimum confidence")
    p.add_argument("--imgsz", type=int, default=640,
                   help="YOLO input size; 320 or 416 is much faster on the Pi (multiple of 32)")
    p.add_argument("--source", default="0", help="camera index, /dev/videoN, video file or URL")
    p.add_argument("--cam-width", type=int, default=1280, help="resolution requested from the camera")
    p.add_argument("--cam-height", type=int, default=720)
    p.add_argument("--cam-fps", type=float, default=30)
    p.add_argument("--no-mjpg", action="store_true", help="don't ask the camera for MJPG")
    p.add_argument("--video-width", type=int, default=640, help="width of the video sent")
    p.add_argument("--video-fps", type=float, default=20, help="maximum video frame rate sent")
    p.add_argument("--quality", type=int, default=70, help="JPEG quality 1-100")
    p.add_argument("--show", action="store_true", help="show the detections in a window on the Pi")
    p.add_argument("--list-cameras", action="store_true")
    args = p.parse_args()

    if args.list_cameras:
        list_cameras()
        return
    if not args.host:
        p.error("--host is required (the ground station's IP address)")

    model = YOLO(args.model)
    cap = open_camera(args.source, args.cam_width, args.cam_height, args.cam_fps, not args.no_mjpg)
    video_addr = (args.host, args.video_port) if args.video_port else None
    det_addr = (args.host, args.det_port)
    det_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    is_file = not (args.source.isdigit() or args.source.startswith("/dev/video") or "://" in args.source)
    pace = (cap.get(cv2.CAP_PROP_FPS) or 30) if is_file else 0.0
    cam = CameraThread(cap, video_addr, args.video_width, args.quality, args.video_fps, pace)
    cam.start()
    print(f"Video -> {args.host}:{args.video_port}" if video_addr else "Video off")
    print(f"Detections -> {det_addr[0]}:{det_addr[1]}")

    last_id = None
    runs, stats_t = 0, time.time()
    last_error = None
    try:
        while True:
            if cam.error:
                raise SystemExit(cam.error)
            fid, frame = cam.latest()
            if frame is None or fid == last_id:          # wait for a new frame
                time.sleep(0.005)
                continue
            last_id = fid
            h, w = frame.shape[:2]

            t0 = time.time()
            r = model(frame, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
            inference_ms = (time.time() - t0) * 1000

            detections = []
            for i, box in enumerate(r.boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                detections.append({
                    "id": i,
                    "name": r.names[int(box.cls[0])],
                    "conf": round(float(box.conf[0].item()), 3),
                    "box": [round(x1), round(y1), round(x2), round(y2)],
                    "center": [round(cx), round(cy)],
                    "offset": [round(2 * cx / w - 1, 3), round(2 * cy / h - 1, 3)],
                })

            msg = {"type": "detections", "timestamp": time.time(), "frame": fid,
                   "width": w, "height": h, "inference_ms": round(inference_ms, 1),
                   "detections": detections}
            try:
                det_sock.sendto(json.dumps(msg).encode(), det_addr)
                last_error = None
            except OSError as e:
                if str(e) != last_error:
                    print(f"[DET] send failed: {e}")
                    last_error = str(e)

            for d in detections:
                print(d["id"], d["name"], f"{d['conf']:.2f}", f"center ({d['center'][0]}, {d['center'][1]})")

            runs += 1
            if time.time() - stats_t >= 5:
                print(f"[DET] {runs / (time.time() - stats_t):.1f} detections/s, last {inference_ms:.0f} ms")
                runs, stats_t = 0, time.time()

            if args.show:
                cv2.imshow("detection", r.plot())
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cam.running = False
        cam.join(timeout=1)
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
