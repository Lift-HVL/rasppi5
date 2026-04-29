"""
Ground-station WebSocket server.

Launched as a background daemon thread by main.py via ground_station.start().
Reads telemetry directly from the shared VehicleState, FSMController, and
TargetDetector instances — no UDP or inter-process communication required.

Build the React dashboard once before running:
    cd ground-station-dashboard && npm install && npm run build

Open http://<pi-ip>:8000 in any browser on the same network.
"""

import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Set

import cv2
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from autopilot.vehicle_state import VehicleState
from fsm.states import State, Autonomy
from fsm.event import Event

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "ground-station-dashboard" / "build" / "client"

_FSM_LABELS = {
    State.BOOT:     "BOOT",
    State.STANDBY:  "STANDBY",
    State.ARMED:    "ARMED",
    State.TAKEOFF:  "TAKEOFF",
    State.HOVER:    "HOVER",
    State.MANUAL:   "MANUAL",
    State.AUTONOMY: "AUTONOMY",
    State.FAILSAFE: "FAILSAFE",
    State.LAND:     "LAND",
    State.RTL:      "RTL",
}
_AUTONOMY_LABELS = {
    Autonomy.SEARCH: "SEARCH",
    Autonomy.TRAVEL: "TRAVEL",
    Autonomy.TRACK:  "TRACK",
}

_COMMAND_MAP: dict[str, Event] = {
    "START_SEARCH":    Event.START_SEARCH,
    "START_TRAVEL":    Event.START_TRAVEL,
    "TASK_PAUSED":     Event.TASK_PAUSED,
    "LAND":            Event.LAND,
    "RESET_ON_GND":    Event.RESET_ON_GND,
    "MANUAL_OVERRIDE": Event.MANUAL_OVERRIDE,
    "MANUAL_DONE":     Event.MANUAL_DONE,
}

_vs: Optional[VehicleState] = None
_fsm = None
_detector = None
_commands = None

_clients: Set[WebSocket] = set()
_clients_lock = threading.Lock()


def _payload() -> dict:
    vs = _vs
    out = {
        "connected":             vs.connected,
        "armed":                 vs.armed,
        "mode":                  vs.mode,
        "latitude":              vs.latitude,
        "longitude":             vs.longitude,
        "altitude_absolute_m":   vs.altitude_absolute_m,
        "altitude_relative_m":   vs.altitude_relative_m,
        "heading_deg":           vs.heading_deg,
        "groundspeed_m_s":       vs.groundspeed_m_s,
        "airspeed_m_s":          vs.airspeed_m_s,
        "climb_rate_m_s":        vs.climb_rate_m_s,
        "pitch_deg":             vs.pitch_deg,
        "roll_deg":              vs.roll_deg,
        "gps_fix_type":          vs.gps_fix_type,
        "gps_ok":                vs.gps_ok,
        "satellites_visible":    vs.satellites_visible,
        "battery_remaining_pct": vs.battery_remaining_pct,
        "battery_voltage_v":     vs.battery_voltage_v,
        "battery_current_a":     vs.battery_current_a,
        "rssi_dbm":              vs.rssi_dbm,
        "timestamp":             time.time(),
    }
    if _fsm is not None:
        out["fsm_state"]         = _FSM_LABELS.get(_fsm.current_state, "IDLE")
        out["autonomy_substate"] = _AUTONOMY_LABELS.get(_fsm.current_autonomy, "NONE")
    if _detector is not None:
        out["target_detected"]    = _detector.target_detected
        out["target_confidence"]  = _detector.target_confidence if _detector.target_detected else 0.0
        out["target_position"]    = _detector.target_position if _detector.target_detected else ""
        out["target_pixel_x"]     = _detector.target_pixel_x
        out["target_bbox_height"] = _detector.target_bbox_height
        out["target_bbox"]        = _detector.target_bbox
        out["target_class_name"]  = _detector.target_class_name
        out["frame_width"]        = _detector.frame_width
        out["frame_height"]       = _detector.frame_height
    return out


async def _broadcast_loop() -> None:
    while True:
        await asyncio.sleep(0.2)  # 5 Hz
        with _clients_lock:
            if not _clients:
                continue
            snapshot = list(_clients)
        payload = json.dumps(_payload())
        dead: Set[WebSocket] = set()
        for ws in snapshot:
            try:
                await ws.send_text(payload)
            except (WebSocketDisconnect, Exception):
                dead.add(ws)
        with _clients_lock:
            _clients.difference_update(dead)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_broadcast_loop())
    yield


app = FastAPI(lifespan=_lifespan)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    with _clients_lock:
        _clients.add(ws)
    try:
        await ws.send_text(json.dumps(_payload()))
    except (WebSocketDisconnect, Exception):
        with _clients_lock:
            _clients.discard(ws)
        return
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        with _clients_lock:
            _clients.discard(ws)


@app.get("/video")
async def video_stream():
    """MJPEG stream of the latest camera frame from the detector."""
    async def _generate():
        while True:
            frame = _detector._raw_frame if _detector is not None else None
            if frame is not None:
                ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
            await asyncio.sleep(0.05)  # cap at 20 Hz

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/command")
async def post_command(payload: dict = Body(...)):
    cmd = payload.get("command", "")

    # Direct MAVLink commands — bypass FSM, talk to autopilot immediately
    if cmd == "ARM":
        if _commands is None:
            raise HTTPException(status_code=503, detail="Commands not available")
        _commands.arm()
        return {"ok": True, "command": cmd}

    if cmd == "DISARM":
        if _commands is None:
            raise HTTPException(status_code=503, detail="Commands not available")
        _commands.disarm()
        return {"ok": True, "command": cmd}

    if cmd == "RTL":
        if _commands is None:
            raise HTTPException(status_code=503, detail="Commands not available")
        _commands.rtl()
        if _fsm is not None:
            _fsm.handle_event(Event.RTL_CMD)
        return {"ok": True, "command": cmd}

    # FSM events
    if _fsm is None:
        raise HTTPException(status_code=503, detail="FSM not available")
    event = _COMMAND_MAP.get(cmd)
    if event is None:
        raise HTTPException(status_code=400, detail=f"Unknown command: {cmd!r}")
    _fsm.handle_event(event)
    return {"ok": True, "command": cmd}


if _STATIC_DIR.exists():
    _assets_dir = _STATIC_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/favicon.ico", include_in_schema=False)
    async def _favicon():
        return FileResponse(str(_STATIC_DIR / "favicon.ico"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str):
        return FileResponse(str(_STATIC_DIR / "index.html"))

else:
    logger.warning(
        "React build not found at %s — run: cd ground-station-dashboard && npm run build",
        _STATIC_DIR,
    )

    @app.get("/")
    async def _no_ui():
        return {"status": "running", "websocket": "/ws"}


def start(
    vehicle_state: VehicleState,
    fsm=None,
    detector=None,
    commands=None,
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "warning",
) -> None:
    """Start the dashboard server as a background daemon thread.

    Call once from main.py after creating VehicleState, FSMController, and
    TargetDetector. The server reads directly from the shared objects with no
    copying or inter-process communication.
    """
    global _vs, _fsm, _detector, _commands
    _vs = vehicle_state
    _fsm = fsm
    _detector = detector
    _commands = commands

    logger.info("Dashboard : http://%s:%d", host, port)
    print(f"Dashboard : http://{host}:{port}")

    threading.Thread(
        target=lambda: uvicorn.run(app, host=host, port=port, log_level=log_level),
        daemon=True,
        name="ground-station",
    ).start()
