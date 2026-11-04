"""gs_viewer.py - ground station: receive the video and the YOLO boxes from detection.py
and draw the boxes on the video.

    pip install opencv-python numpy
    python3 gs_viewer.py
    python3 gs_viewer.py --video-port 5600 --det-port 5010 --record flight.mp4

    python3 gs_viewer.py --sync          # boxes line up exactly, video is delayed instead

Keys in the window:  q = quit   b = boxes on/off   d = sync on/off   s = save a snapshot
Picking one person (detection.py must run with tracking, the default):
    left click on a person = lock that person (green box, the drone only has eyes for them)
    x = release the lock           f = following on/off (the drone only moves while this is ON)
Following is a dead-man's switch: this window repeats "follow" twice a second, so it stops by itself
if the window or the link dies. The lock/follow commands go to the Pi at --control-port (5011); the
Pi's address is taken from the detection packets (or set it with --pi).

Boxes are matched to the video by frame id. YOLO is usually slower than the video:
  normal: live video, newest boxes on top ("lag" = how many frames older the boxes are)
  --sync: the video is delayed by the YOLO time, so each frame gets its own boxes
Boxes older than --max-age seconds are hidden (normal mode).
"""

import argparse
import json
import socket
import struct
import time
from collections import OrderedDict

import cv2
import numpy as np

HEADER = struct.Struct("!2sIHHH")
MAGIC = b"CF"


def newer(a: int, b: int) -> bool:
    """True if frame id a is newer than b (uint32 wrap-around safe)."""
    return 0 < (a - b) & 0xFFFFFFFF < 0x80000000


def id_diff(a: int, b: int) -> int:
    """a - b for frame ids, as a signed number."""
    d = (a - b) & 0xFFFFFFFF
    return d - 0x100000000 if d >= 0x80000000 else d


class FrameAssembler:
    """Collects video packets; returns (frame id, jpeg) when every chunk of a frame has arrived.
    Unfinished frames older than a finished one are dropped, so the video never lags."""

    def __init__(self, max_pending: int = 8):
        self.pending = {}
        self.last_done = None
        self.max_pending = max_pending

    def add(self, packet: bytes):
        if len(packet) < HEADER.size:
            return None
        magic, fid, idx, count, _ = HEADER.unpack_from(packet)
        if magic != MAGIC or count == 0 or idx >= count:
            return None
        if self.last_done is not None and not newer(fid, self.last_done):
            if (self.last_done - fid) & 0xFFFFFFFF > 1000:      # sender restarted
                self.last_done, self.pending = None, {}
            else:
                return None
        entry = self.pending.setdefault(fid, [count, {}])
        entry[1][idx] = packet[HEADER.size:]
        if len(entry[1]) < entry[0]:
            if len(self.pending) > self.max_pending:
                del self.pending[min(self.pending, key=lambda f: (f - fid + 0x80000000) & 0xFFFFFFFF)]
            return None
        jpeg = b"".join(entry[1][i] for i in range(entry[0]))
        for f in list(self.pending):
            if f == fid or not newer(f, fid):
                del self.pending[f]
        self.last_done = fid
        return fid, jpeg


class Receiver:
    """Non-blocking reader for both UDP streams."""

    def __init__(self, video_port: int, det_port: int, history: int = 120):
        self.video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        self.video.bind(("0.0.0.0", video_port))
        self.video.setblocking(False)
        self.det = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.det.bind(("0.0.0.0", det_port))
        self.det.setblocking(False)
        self.asm = FrameAssembler()
        self.dets = OrderedDict()        # frame id -> (arrival time, detection message)
        self.history = history
        self.latest_det = None           # (arrival time, message)
        self.pi_host = None              # where the detection packets come from

    def poll(self):
        """Read everything waiting. Returns the newest finished (frame id, jpeg) or None."""
        newest = None
        while True:
            try:
                data, _ = self.video.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            done = self.asm.add(data)
            if done:
                newest = done
        while True:
            try:
                data, addr = self.det.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            try:
                msg = json.loads(data)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("type") != "detections":
                continue
            self.pi_host = addr[0]
            entry = (time.time(), msg)
            self.dets[msg.get("frame")] = entry
            while len(self.dets) > self.history:
                self.dets.popitem(last=False)
            if self.latest_det is None or not isinstance(msg.get("frame"), int) \
                    or not isinstance(self.latest_det[1].get("frame"), int) \
                    or newer(msg["frame"], self.latest_det[1]["frame"]) \
                    or abs(id_diff(msg["frame"], self.latest_det[1]["frame"])) > 1000:
                self.latest_det = entry
        return newest

    def detections_at_or_before(self, frame_id: int, max_frames: int = 90):
        """Boxes for this frame, or else for the closest earlier frame YOLO looked at."""
        best, best_diff = None, None
        for f, (_, msg) in self.dets.items():
            if not isinstance(f, int):
                continue
            d = id_diff(frame_id, f)
            if 0 <= d <= max_frames and (best_diff is None or d < best_diff):
                best, best_diff = msg, d
        return best

    def detections_for(self, frame_id: int, max_age: float):
        """Boxes for this exact frame if we have them, else the newest boxes (if fresh enough)."""
        if frame_id in self.dets:
            return self.dets[frame_id][1]
        if self.latest_det and time.time() - self.latest_det[0] <= max_age:
            return self.latest_det[1]
        return None


def class_color(name: str):
    h = sum(ord(c) * 31 ** i for i, c in enumerate(name)) % 180
    hsv = np.uint8([[[h, 220, 255]]])
    return tuple(int(v) for v in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])


LOCK_COLOR = (0, 255, 0)


def draw_detections(img, msg) -> list:
    """Draw boxes from a detection message, scaled from camera pixels to this image.
    Returns the pickable boxes as (track_id, x1, y1, x2, y2) in image pixels."""
    h, w = img.shape[:2]
    sx = w / msg.get("width", w)
    sy = h / msg.get("height", h)
    locked_id = msg.get("locked_id")
    hits = []
    for d in msg.get("detections", []):
        x1, y1, x2, y2 = d["box"]
        p1 = (int(x1 * sx), int(y1 * sy))
        p2 = (int(x2 * sx), int(y2 * sy))
        tid = d.get("track_id")
        locked = tid is not None and tid == locked_id
        if tid is not None:
            hits.append((tid, p1[0], p1[1], p2[0], p2[1]))
        color = LOCK_COLOR if locked else class_color(d.get("name", "?"))
        cv2.rectangle(img, p1, p2, color, 4 if locked else 2)
        label = f"{d.get('name', '?')} {'#%d ' % tid if tid is not None else ''}{d.get('conf', 0):.2f}"
        if locked:
            label = "LOCKED " + label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = max(p1[1], th + 6)
        cv2.rectangle(img, (p1[0], ty - th - 6), (p1[0] + tw + 6, ty), color, -1)
        cv2.putText(img, label, (p1[0] + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cx, cy = d.get("center", ((x1 + x2) / 2, (y1 + y2) / 2))
        cv2.circle(img, (int(cx * sx), int(cy * sy)), 3, color, -1)
    return hits


def pick(hits, x: int, y: int):
    """Track id of the box under the click (the smallest one if boxes overlap), or None."""
    inside = [(abs(x2 - x1) * abs(y2 - y1), tid) for tid, x1, y1, x2, y2 in hits
              if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)]
    return min(inside)[1] if inside else None


class Control:
    """Sends lock / release / follow to detection.py on the Pi."""

    def __init__(self, port: int, pi_host=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port = port
        self.pi_host = pi_host

    def send(self, host, **fields) -> bool:
        host = self.pi_host or host
        if not host:
            print("No Pi address yet - nothing received from detection.py (or use --pi)")
            return False
        try:
            self.sock.sendto(json.dumps({"type": "track", **fields}).encode(), (host, self.port))
            return True
        except OSError as e:
            print(f"control send failed: {e}")
            return False


def main() -> None:
    p = argparse.ArgumentParser(description="Show the Pi video with YOLO boxes drawn on it")
    p.add_argument("--video-port", type=int, default=5600)
    p.add_argument("--det-port", type=int, default=5010)
    p.add_argument("--max-age", type=float, default=1.0, help="hide boxes older than this (s)")
    p.add_argument("--record", help="save the video with boxes to this .mp4 file")
    p.add_argument("--sync", action="store_true",
                   help="delay the video by the YOLO time so the boxes line up exactly")
    p.add_argument("--control-port", type=int, default=5011, help="UDP port on the Pi for lock/release/follow")
    p.add_argument("--pi", help="Pi address for lock commands (default: where the detections come from)")
    args = p.parse_args()

    rx = Receiver(args.video_port, args.det_port)
    control = Control(args.control_port, args.pi)
    print(f"Video on UDP {args.video_port}, detections on UDP {args.det_port} - "
          f"q quits, b toggles boxes, d toggles sync (now {'on' if args.sync else 'off'})")

    window = "lifthvl ground station"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    clicks = []                      # mouse clicks waiting to be handled in the main loop
    cv2.setMouseCallback(window, lambda ev, x, y, fl, pa: clicks.append((x, y))
                         if ev == cv2.EVENT_LBUTTONDOWN else None)
    hits = []                        # pickable boxes of the picture on screen
    follow_want = False              # operator wants following; re-sent twice a second
    follow_sent = 0.0
    frame, frame_id, frame_t = None, None, 0.0
    buffer = OrderedDict()           # frame id -> image, for --sync (newest last)
    newest_id = None
    delay = None                     # frames the boxes are behind the video (smoothed)
    sync = args.sync
    show_boxes = True
    writer = None
    v_fps, v_count, fps_t = 0.0, 0, time.time()
    det_rate, det_seen = 0.0, 0
    last_det_id = None

    try:
        while True:
            got = rx.poll()
            if got:
                fid, jpeg = got
                img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    newest_id, frame_t = fid, time.time()
                    buffer[fid] = img
                    while len(buffer) > 120:
                        buffer.popitem(last=False)
                    v_count += 1
            if rx.latest_det and rx.latest_det[1].get("frame") != last_det_id:
                last_det_id = rx.latest_det[1].get("frame")
                det_seen += 1
                # how far the boxes are behind the video right now
                if newest_id is not None and isinstance(last_det_id, int):
                    measured = max(0, id_diff(newest_id, last_det_id))
                    if measured < 120:
                        delay = measured if delay is None else 0.8 * delay + 0.2 * measured

            # pick the frame to show: the newest, or (sync) the one the boxes belong to
            if newest_id is not None:
                target = newest_id
                if sync and delay is not None:
                    target = (newest_id - round(delay)) & 0xFFFFFFFF
                shown = None
                for f in reversed(buffer):
                    if id_diff(target, f) >= 0:
                        shown = f
                        break
                if shown is None:
                    shown = next(iter(buffer))
                frame, frame_id = buffer[shown], shown

            if time.time() - fps_t >= 1:
                dt = time.time() - fps_t
                v_fps, det_rate = v_count / dt, det_seen / dt
                v_count, det_seen, fps_t = 0, 0, time.time()

            if frame is None:
                show = np.zeros((360, 640, 3), np.uint8)
                cv2.putText(show, f"Waiting for video on UDP {args.video_port}...", (20, 180),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            else:
                show = frame.copy()
                if not show_boxes:
                    msg = None
                elif sync:
                    msg = rx.detections_at_or_before(frame_id)
                else:
                    msg = rx.detections_for(frame_id, args.max_age)
                info = f"video {v_fps:.0f} fps | yolo {det_rate:.1f}/s"
                if sync:
                    info = f"SYNC delay {delay or 0:.0f} fr | " + info
                hits = []
                if msg is not None:
                    hits = draw_detections(show, msg)
                    lag = id_diff(frame_id, msg.get("frame", frame_id)) if isinstance(msg.get("frame"), int) else 0
                    info += f" | {len(msg.get('detections', []))} obj, lag {lag} fr"
                    if msg.get("inference_ms") is not None:
                        info += f", {msg['inference_ms']:.0f} ms"
                elif show_boxes:
                    info += " | no boxes"
                latest = rx.latest_det[1] if rx.latest_det else {}
                if latest.get("locked_id") is not None:
                    info += f" | LOCK #{latest['locked_id']} {latest.get('lock_state', '')}"
                    info += " | FOLLOW ON" if latest.get("follow") else " | follow off"
                stale = time.time() - frame_t > 1.0
                if stale:
                    info = "NO VIDEO SIGNAL"
                cv2.rectangle(show, (0, 0), (show.shape[1], 26), (0, 0, 0), -1)
                cv2.putText(show, info, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 0, 255) if stale else (0, 255, 0), 1)
                hint = "click = lock person | x = release | f = follow"
                cv2.putText(show, hint, (8, show.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (255, 255, 255), 1)
                if args.record and got:
                    if writer is None:
                        h, w = show.shape[:2]
                        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), 20, (w, h))
                    writer.write(show)

            # picking: a click locks the person under the cursor
            while clicks:
                x, y = clicks.pop(0)
                tid = pick(hits, x, y)
                if tid is None:
                    print("click: no tracked person there")
                elif control.send(rx.pi_host, action="lock", track_id=tid):
                    print(f"lock #{tid} requested")
                    follow_want = False          # following must be switched on again for a new person

            # the Pi turns following off itself when the lock is gone - mirror that
            if follow_want and rx.latest_det and rx.latest_det[1].get("locked_id") is None \
                    and time.time() - rx.latest_det[0] < 1.0:
                follow_want = False
            if follow_want and time.time() - follow_sent >= 0.5:
                control.send(rx.pi_host, action="follow", enabled=True)
                follow_sent = time.time()

            cv2.imshow(window, show)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("x"):
                follow_want = False
                control.send(rx.pi_host, action="release")
            if key == ord("f"):
                follow_want = not follow_want
                if follow_want:
                    follow_sent = 0.0            # send right away
                else:
                    control.send(rx.pi_host, action="follow", enabled=False)
                print(f"follow {'ON' if follow_want else 'off'}")
            if key == ord("b"):
                show_boxes = not show_boxes
            if key == ord("d"):
                sync = not sync
                print(f"sync {'on' if sync else 'off'}")
            if key == ord("s") and frame is not None:
                name = time.strftime("snapshot_%Y%m%d_%H%M%S.jpg")
                cv2.imwrite(name, show)
                print(f"saved {name}")
            if got is None:
                time.sleep(0.003)
    except KeyboardInterrupt:
        pass
    finally:
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
