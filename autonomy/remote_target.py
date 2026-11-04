"""Target source for the autonomy loop when Detection/detection.py owns the camera.

detection.py tracks every person with a tracker, the operator picks one in gs_viewer.py, and
detection.py sends ONLY that locked person to this process over local UDP. This class exposes the
same attributes as autonomy.target_detection.TargetDetector, so FSM, event generator and
TargetTracker work unchanged.
"""

import json
import socket
import time

from config import TARGET_FEED_PORT, TARGET_FEED_TIMEOUT


class RemoteTargetDetector:
    def __init__(self, port: int = TARGET_FEED_PORT, timeout: float = TARGET_FEED_TIMEOUT):
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.setblocking(False)

        # same attributes as TargetDetector
        self.center_x = 0.0
        self.center_y = 0.0
        self.target_detected = False
        self.target_confidence = 0.0
        self.target_position = ()
        self.target_pixel_x = 0.0
        self.target_bbox_height = 0.0

        # extras from the tracker
        self.locked_id = None            # track id the operator picked (None = nobody picked)
        self.lock_state = "idle"         # idle / tracking / lost
        self.follow_enabled = False      # operator switched following on (dead-man's switch, see detection.py)
        self.last_packet = 0.0

    def update(self) -> None:
        """Read every waiting packet (the newest wins) and mark the target lost if the feed went quiet."""
        msg = None
        while True:
            try:
                data, _ = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:              # e.g. ICMP port unreachable on some platforms
                break
            try:
                parsed = json.loads(data)
            except ValueError:
                continue
            if isinstance(parsed, dict) and parsed.get("type") == "target":
                msg = parsed

        if msg is not None:
            self.last_packet = time.time()
            self._apply(msg)
        elif time.time() - self.last_packet > self.timeout:
            # detection.py stopped: never keep flying on an old position
            self.target_detected = False
            self.follow_enabled = False
            self.lock_state = "idle"

    def _apply(self, msg: dict) -> None:
        width, height = msg.get("width") or 0, msg.get("height") or 0
        self.center_x, self.center_y = width / 2, height / 2
        self.locked_id = msg.get("locked_id")
        self.lock_state = msg.get("state", "idle")
        self.follow_enabled = bool(msg.get("follow"))

        if not msg.get("detected") or not width:
            self.target_detected = False
            return

        x1, y1, x2, y2 = msg["box"]
        cx = (x1 + x2) / 2
        self.target_detected = True
        self.target_confidence = float(msg.get("conf", 0.0))
        self.target_pixel_x = cx
        self.target_bbox_height = float(y2 - y1)
        if cx < width / 3:
            self.target_position = "left"
        elif cx > 2 * width / 3:
            self.target_position = "right"
        else:
            self.target_position = "center"

    def display(self) -> None:
        """Nothing to draw here - the ground station shows the video."""

    def release(self) -> None:
        self.sock.close()
