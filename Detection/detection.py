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

Tracking and picking one person (on by default, --no-track turns it off):
  YOLO runs with a tracker (ByteTrack/BoT-SORT), so every box also has a stable "track_id"
  (null while the tracker has not confirmed it). The detection message gets three more fields:
    "locked_id": the track id the operator picked (or null), "lock_state": idle | tracking | lost,
    "follow": true while the operator has following switched on.
  The operator picks a person in gs_viewer.py or in the ground-station-frontend. Both send JSON, to
  --control-port (default 5011), or - through NAT, the way the frontend does it - back to this machine
  from where the detection packets come (the backend answers to the sender of every detection packet):
    {"type": "track", "action": "lock", "track_id": 3}
    {"type": "track", "action": "lock_at", "x": 0.42, "y": 0.61}   # a click on the video, 0..1 of the picture
    {"type": "track", "action": "release"}
    {"type": "track", "action": "follow", "enabled": true}   # repeat every <1 s: dead-man's switch,
                                                             # following stops after --follow-timeout
  If the locked person disappears, a new track id that looks like them (clothes colour) close to
  where they were is accepted for --reacquire seconds; after that the lock is released.

  Video for the web frontend: an MJPEG stream with the boxes (locked person in green) drawn in is served at
  http://<pi>:8080/stream.mjpg (--stream-port, 0 = off). It only encodes while someone is watching.
  The frontend gets the detections from the backend, so use --video-port 0 unless gs_viewer.py also runs.

  Only the locked person goes to the drone's autonomy loop (this machine, 127.0.0.1:--autonomy-port,
  default 5012) - one packet per YOLO run, also when nobody is locked (it doubles as a heartbeat):
    {"type": "target", "timestamp": ..., "frame": 123, "width": 1280, "height": 720,
     "locked_id": 3, "state": "tracking", "detected": true, "conf": 0.91, "box": [x1, y1, x2, y2],
     "follow": true}
"""

import argparse
import glob
import json
import math
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
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
# MJPEG stream for the web frontend: video with the boxes drawn in
# ---------------------------------------------------------------------------

LOCK_BGR = (0, 255, 0)
OTHER_BGR = (0, 191, 255)


class Overlay:
    """What the stream draws on top of the video: the newest boxes and the lock state."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snap = None

    def set(self, snap: dict) -> None:
        with self._lock:
            self._snap = snap

    def get(self):
        with self._lock:
            return self._snap


def draw_overlay(img, snap, max_age: float = 1.0) -> None:
    """Boxes (scaled from camera pixels to img) + a status banner. Boxes older than max_age are not shown."""
    if not snap or time.time() - snap["time"] > max_age:
        return
    h, w = img.shape[:2]
    sx, sy = w / snap["width"], h / snap["height"]
    for d in snap["detections"]:
        x1, y1, x2, y2 = d["box"]
        p1, p2 = (int(x1 * sx), int(y1 * sy)), (int(x2 * sx), int(y2 * sy))
        tid = d["track_id"]
        locked = tid is not None and tid == snap["locked_id"]
        color = LOCK_BGR if locked else OTHER_BGR
        cv2.rectangle(img, p1, p2, color, 4 if locked else 2)
        label = f"{'LOCKED ' if locked else ''}{d['name']}{f' #{tid}' if tid is not None else ''} {d['conf']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = max(p1[1], th + 6)
        cv2.rectangle(img, (p1[0], ty - th - 6), (p1[0] + tw + 6, ty), color, -1)
        cv2.putText(img, label, (p1[0] + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    if snap["locked_id"] is not None:
        text = f"LOCK #{snap['locked_id']} {snap['state']}" + (" | FOLLOWING" if snap["follow"] else "")
        cv2.rectangle(img, (0, 0), (w, 22), (0, 0, 0), -1)
        cv2.putText(img, text, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, LOCK_BGR, 1)


class StreamServer:
    """HTTP: /stream.mjpg (multipart MJPEG, opened by an <img> in the browser) and / (a page showing it).
    Frames are only encoded while at least one viewer is connected."""

    def __init__(self, port: int, cam: CameraThread, overlay: Overlay, width: int, quality: int, fps: float,
                 burn_in: bool = False):
        self.port, self.cam, self.overlay = port, cam, overlay
        self.burn_in = burn_in
        self.width, self.quality = width, quality
        self.period = 1.0 / fps if fps > 0 else 0.0
        self.cond = threading.Condition()
        self.jpeg = None
        self.seq = 0
        self.viewers = 0
        self.running = True
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):          # no line per request
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/stream.mjpg":
                    server.serve_stream(self)
                elif path in ("/", "/index.html"):
                    page = (b'<!doctype html><meta charset="utf-8"><body style="margin:0;background:#020617">'
                            b'<img src="/stream.mjpg" style="width:100%;height:100vh;object-fit:contain"></body>')
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)
                else:
                    self.send_error(404)

        self.httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self.httpd.daemon_threads = True

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._encode_loop, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        self.httpd.shutdown()

    def _encode_loop(self) -> None:
        last_id, next_t = None, 0.0
        while self.running:
            if self.viewers == 0:
                time.sleep(0.1)
                last_id = None
                continue
            fid, frame = self.cam.latest()
            if frame is None or fid == last_id or time.time() < next_t:
                time.sleep(0.005)
                continue
            last_id, next_t = fid, time.time() + self.period
            h, w = frame.shape[:2]
            img = cv2.resize(frame, (self.width, round(h * self.width / w)), interpolation=cv2.INTER_AREA) \
                if self.width and w > self.width else frame.copy()
            if self.burn_in:
                draw_overlay(img, self.overlay.get())
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if ok:
                with self.cond:
                    self.jpeg, self.seq = buf.tobytes(), self.seq + 1
                    self.cond.notify_all()

    def serve_stream(self, h: BaseHTTPRequestHandler) -> None:
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        h.send_header("Cache-Control", "no-cache, no-store")
        h.send_header("Access-Control-Allow-Origin", "*")
        h.end_headers()
        seen = 0
        with self.cond:
            self.viewers += 1
        try:
            while self.running:
                with self.cond:
                    if not self.cond.wait_for(lambda: self.seq != seen, timeout=2.0):
                        continue
                    jpeg, seen = self.jpeg, self.seq
                h.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                h.wfile.write(jpeg)
                h.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionError, OSError):
            pass                                    # the viewer closed the page
        finally:
            with self.cond:
                self.viewers -= 1


# ---------------------------------------------------------------------------
# Picking one person: the lock
# ---------------------------------------------------------------------------

def appearance(frame, box):
    """Colour fingerprint of a person: HSV histogram of the middle of the box (less background)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    x1, x2 = int(x1 + 0.2 * w), int(x2 - 0.2 * w)
    y1, y2 = int(y1 + 0.15 * h), int(y2 - 0.15 * h)
    x1, y1 = max(x1, 0), max(y1, 0)
    crop = frame[y1:y2, x1:x2]
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    return cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class TargetLock:
    """The one person the operator picked. Survives tracker id changes by comparing appearance."""

    def __init__(self, reacquire_s: float, min_similarity: float, follow_timeout: float):
        self.reacquire_s = reacquire_s
        self.min_similarity = min_similarity
        self.follow_timeout = follow_timeout
        self.release()

    def release(self) -> None:
        self.locked_id = None
        self.state = "idle"            # idle | tracking | lost
        self.name = None
        self.hist = None
        self.last_center = None
        self.last_seen = 0.0
        self.follow_until = 0.0

    def lock(self, det: dict, now: float) -> None:
        self.release()
        self.locked_id = det["track_id"]
        self.name = det["name"]
        self.state = "tracking"
        self.last_seen = now

    def set_follow(self, enabled: bool, now: float) -> None:
        # only meaningful with a lock; the keepalive from the ground station keeps it alive
        self.follow_until = now + self.follow_timeout if enabled and self.locked_id is not None else 0.0

    def follow(self, now: float) -> bool:
        return self.locked_id is not None and self.state == "tracking" and now < self.follow_until

    def update(self, dets: list, frame, now: float):
        """Returns the detection of the locked person in this frame, or None. Sets det['locked']."""
        if self.locked_id is None:
            return None

        found = next((d for d in dets if d["track_id"] == self.locked_id), None)
        if found is None and self.state == "tracking":
            self.state = "lost"
        if found is None and self.state == "lost":
            found = self._reacquire(dets, frame, now)

        if found is None:
            if now - self.last_seen > self.reacquire_s:
                print(f"[LOCK] lost #{self.locked_id} for {self.reacquire_s:g} s - released")
                self.release()
            return None

        self.state = "tracking"
        self.last_seen = now
        self.last_center = found["center"]
        found["locked"] = True
        # learn the look slowly, but not while someone stands in front of the person
        if not any(o is not found and iou(o["box"], found["box"]) > 0.1 for o in dets):
            hist = appearance(frame, found["box"])
            if hist is not None:
                if self.hist is None:
                    self.hist = hist
                else:
                    self.hist = cv2.normalize(0.95 * self.hist + 0.05 * hist, None,
                                              alpha=1.0, norm_type=cv2.NORM_L1)
        return found

    def _reacquire(self, dets: list, frame, now: float):
        """The tracker gave the person a new id: accept a similar-looking one near where they went."""
        if self.hist is None or self.last_center is None:
            return None
        h, w = frame.shape[:2]
        gone = now - self.last_seen
        max_dist = min(1.0, 0.25 + 0.1 * gone) * w        # allowed to wander further the longer they are gone
        best, best_sim = None, self.min_similarity
        for d in dets:
            if d["track_id"] is None or d["track_id"] == self.locked_id or d["name"] != self.name:
                continue
            if math.dist(d["center"], self.last_center) > max_dist:
                continue
            hist = appearance(frame, d["box"])
            if hist is None:
                continue
            sim = cv2.compareHist(self.hist, hist, cv2.HISTCMP_CORREL)
            if sim >= best_sim:
                best, best_sim = d, sim
        if best is not None:
            print(f"[LOCK] #{self.locked_id} -> #{best['track_id']} (look-alike {best_sim:.2f})")
            self.locked_id = best["track_id"]
        return best


def box_at(dets: list, px: float, py: float, frame_w: float):
    """The tracked box under a click: the smallest one containing the point, else the nearest centre
    within 8 % of the picture width (the person moved a little since the operator saw the frame)."""
    tracked = [d for d in dets if d["track_id"] is not None]
    inside = [d for d in tracked if d["box"][0] <= px <= d["box"][2] and d["box"][1] <= py <= d["box"][3]]
    if inside:
        return min(inside, key=lambda d: (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]))
    near = [(math.dist(d["center"], (px, py)), d["track_id"], d) for d in tracked]
    if near:
        dist, _, d = min(near, key=lambda t: t[:2])
        if dist <= 0.08 * frame_w:
            return d
    return None


def handle_control(data: bytes, lock: TargetLock, dets: list, now: float, size=None) -> None:
    """One packet from the ground station: lock / lock_at / release / follow. size = (width, height) of the frame."""
    try:
        obj = json.loads(data)
    except ValueError:
        return
    if not isinstance(obj, dict) or obj.get("type") != "track":
        return
    action = obj.get("action")
    if action in ("lock", "lock_at"):
        if action == "lock":
            det = next((d for d in dets if d["track_id"] is not None and d["track_id"] == obj.get("track_id")), None)
            what = f"track id {obj.get('track_id')!r}"
        else:
            x, y = obj.get("x"), obj.get("y")
            ok = size and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in (x, y))
            det = box_at(dets, x * size[0], y * size[1], size[0]) if ok else None
            what = f"anyone at ({x!r}, {y!r})"
        if det is None:
            print(f"[LOCK] ignored: no tracked person for {what} in the last frame")
            return
        lock.lock(det, now)
        print(f"[LOCK] locked #{det['track_id']} ({det['name']})")
    elif action == "release":
        if lock.locked_id is not None:
            print(f"[LOCK] released #{lock.locked_id}")
        lock.release()
    elif action == "follow":
        was = lock.follow(now)
        lock.set_follow(bool(obj.get("enabled")), now)
        if lock.follow(now) != was:               # silent when ignored (no lock) or just a keepalive
            print(f"[LOCK] follow {'ON' if lock.follow(now) else 'OFF'}")


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
    p.add_argument("--no-track", action="store_true", help="plain detection, no track ids and no picking")
    p.add_argument("--tracker", default="bytetrack.yaml",
                   help="bytetrack.yaml (light) or botsort.yaml (camera-motion compensation, heavier)")
    p.add_argument("--classes", nargs="+", metavar="NAME",
                   help="only detect/track these classes, e.g. --classes person (default: all the model knows)")
    p.add_argument("--control-port", type=int, default=5011,
                   help="UDP port for lock/release/follow from the ground station (0 = off)")
    p.add_argument("--autonomy-port", type=int, default=5012,
                   help="UDP port on 127.0.0.1 where the locked person is sent to the autonomy loop (0 = off)")
    p.add_argument("--reacquire", type=float, default=10.0,
                   help="seconds to look for the locked person after losing them, then release the lock")
    p.add_argument("--similarity", type=float, default=0.5,
                   help="how much a new track must look like the locked person to take over (0..1)")
    p.add_argument("--follow-timeout", type=float, default=3.0,
                   help="following stops this many seconds after the last 'follow' message from the ground station")
    p.add_argument("--source", default="0", help="camera index, /dev/videoN, video file or URL")
    p.add_argument("--cam-width", type=int, default=1280, help="resolution requested from the camera")
    p.add_argument("--cam-height", type=int, default=720)
    p.add_argument("--cam-fps", type=float, default=30)
    p.add_argument("--no-mjpg", action="store_true", help="don't ask the camera for MJPG")
    p.add_argument("--stream-port", type=int, default=8080,
                   help="HTTP port for the MJPEG stream with boxes drawn in, for the web frontend (0 = off)")
    p.add_argument("--burn-in", action="store_true",
                   help="draw the boxes into the MJPEG video (default: clean video, the dashboard draws the boxes)")
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
    class_ids = None
    if args.classes:
        by_name = {str(n).lower(): i for i, n in model.names.items()}
        unknown = [c for c in args.classes if c.lower() not in by_name]
        if unknown:
            raise SystemExit(f"Model has no class {unknown} - it knows: {sorted(by_name)}")
        class_ids = [by_name[c.lower()] for c in args.classes]

    track = not args.no_track
    lock = TargetLock(args.reacquire, args.similarity, args.follow_timeout)
    control_sock = None
    if track and args.control_port:
        control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            control_sock.bind(("0.0.0.0", args.control_port))
        except OSError as e:
            raise SystemExit(f"Could not listen for lock commands on UDP {args.control_port}: {e}")
        control_sock.setblocking(False)
        print(f"Lock commands <- UDP {args.control_port}")
    autonomy_addr = ("127.0.0.1", args.autonomy_port) if track and args.autonomy_port else None

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
    # Replies from the backend (lock/release/follow) come back to this socket's address, which is what makes
    # them work through NAT - so it must be readable without blocking the YOLO loop
    det_sock.setblocking(False)

    overlay = Overlay()
    stream = None
    if args.stream_port:
        try:
            stream = StreamServer(args.stream_port, cam, overlay, args.video_width, args.quality, args.video_fps,
                                  args.burn_in)
            stream.start()
            print(f"Video with boxes -> http://<this machine>:{args.stream_port}/stream.mjpg")
        except OSError as e:
            print(f"[STREAM] could not listen on TCP {args.stream_port}: {e} - web video is off")

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
            if track:
                # persist=True: the tracker remembers the people from the previous frame
                r = model.track(frame, persist=True, tracker=args.tracker, classes=class_ids,
                                conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
            else:
                r = model(frame, classes=class_ids, conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
            inference_ms = (time.time() - t0) * 1000

            detections = []
            for i, box in enumerate(r.boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                detections.append({
                    "id": i,
                    "track_id": int(box.id[0]) if box.id is not None else None,
                    "name": r.names[int(box.cls[0])],
                    "conf": round(float(box.conf[0].item()), 3),
                    "box": [round(x1), round(y1), round(x2), round(y2)],
                    "center": [round(cx), round(cy)],
                    "offset": [round(2 * cx / w - 1, 3), round(2 * cy / h - 1, 3)],
                })

            now = time.time()
            # lock / lock_at / release / follow: from gs_viewer on --control-port, and from the backend on the
            # socket the detections go out on
            for sock in ((control_sock, det_sock) if track else ()):
                while sock is not None:
                    try:
                        data, _ = sock.recvfrom(4096)
                    except (BlockingIOError, InterruptedError):
                        break
                    except OSError:
                        break
                    handle_control(data, lock, detections, now, (w, h))
            target = lock.update(detections, frame, now) if track else None
            overlay.set({"time": now, "width": w, "height": h, "detections": detections,
                         "locked_id": lock.locked_id, "state": lock.state, "follow": lock.follow(now)})

            msg = {"type": "detections", "timestamp": now, "frame": fid,
                   "width": w, "height": h, "inference_ms": round(inference_ms, 1),
                   "locked_id": lock.locked_id, "lock_state": lock.state, "follow": lock.follow(now),
                   "detections": detections}
            try:
                det_sock.sendto(json.dumps(msg).encode(), det_addr)
                last_error = None
            except OSError as e:
                if str(e) != last_error:
                    print(f"[DET] send failed: {e}")
                    last_error = str(e)

            if autonomy_addr:                     # only the locked person goes to the flight logic
                feed = {"type": "target", "timestamp": now, "frame": fid, "width": w, "height": h,
                        "locked_id": lock.locked_id, "state": lock.state,
                        "detected": target is not None, "follow": lock.follow(now)}
                if target is not None:
                    feed["conf"], feed["box"] = target["conf"], target["box"]
                try:
                    det_sock.sendto(json.dumps(feed).encode(), autonomy_addr)
                except OSError:
                    pass                          # autonomy loop not running - fine

            for d in detections:
                tag = " <== LOCKED" if d.get("locked") else ""
                print(d["id"], f"#{d['track_id']}", d["name"], f"{d['conf']:.2f}",
                      f"center ({d['center'][0]}, {d['center'][1]})" + tag)

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
        if stream is not None:
            stream.stop()
        cam.running = False
        cam.join(timeout=1)
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
