"""
Ground station dashboard server.

Connects to a MAVLink stream and serves a real-time browser dashboard via
WebSocket.

Usage
-----
Production (ground Pi with radio/wireless link on serial):
    python dashboard_server.py

SITL (MissionPlanner configured to push MAVLink Outbound → UDP 127.0.0.1:14551):
    python dashboard_server.py --sitl

Explicit connection string:
    python dashboard_server.py --connection /dev/ttyUSB0 --baud 57600
    python dashboard_server.py --connection udp:192.168.1.50:14551

Open http://<this-machine-ip>:8000 in any browser on the same LAN.
"""

import argparse
import asyncio
import json
import math
import threading
import time
from contextlib import asynccontextmanager
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from autopilot.mavlink_client import MAVLinkClient
from autopilot.vehicle_state import VehicleState
from config import CONNECTION_STRING, BAUDRATE, CONNECTION_TIMEOUT

# ---------------------------------------------------------------------------
# Shared state — written by the MAVLink thread, read by the async event loop.
# Simple attribute writes are GIL-safe; no explicit lock needed here.
# ---------------------------------------------------------------------------
vehicle_state = VehicleState()
_clients: Set[WebSocket] = set()

# ---------------------------------------------------------------------------
# HTML dashboard (single self-contained page)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HVL Lift — Ground Station</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: monospace; background: #0d0d0d; color: #ddd; padding: 24px; }
    h1 { color: #4af; margin-bottom: 20px; font-size: 1.3em; letter-spacing: 1px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }
    .card {
      background: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      padding: 14px 16px;
    }
    .card h2 {
      font-size: 0.72em;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #4af;
      margin-bottom: 10px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 5px 0;
      border-bottom: 1px solid #222;
      font-size: 0.9em;
    }
    .row:last-child { border-bottom: none; }
    .label { color: #666; }
    .value { font-weight: bold; }
    .ok   { color: #4f4; }
    .warn { color: #fa4; }
    .bad  { color: #f44; }
    #footer {
      margin-top: 18px;
      font-size: 0.75em;
      color: #444;
    }
  </style>
</head>
<body>
  <h1>HVL Lift — Ground Station</h1>
  <div class="grid">

    <div class="card">
      <h2>Link</h2>
      <div class="row"><span class="label">Connected</span><span class="value" id="connected">—</span></div>
      <div class="row"><span class="label">Mode</span><span class="value" id="mode">—</span></div>
      <div class="row"><span class="label">Armed</span><span class="value" id="armed">—</span></div>
    </div>

    <div class="card">
      <h2>Flight</h2>
      <div class="row"><span class="label">Altitude (rel)</span><span class="value" id="alt_rel">—</span></div>
      <div class="row"><span class="label">Altitude (abs)</span><span class="value" id="alt_abs">—</span></div>
      <div class="row"><span class="label">Groundspeed</span><span class="value" id="groundspeed">—</span></div>
      <div class="row"><span class="label">Climb rate</span><span class="value" id="climb">—</span></div>
      <div class="row"><span class="label">Heading</span><span class="value" id="heading">—</span></div>
    </div>

    <div class="card">
      <h2>GPS</h2>
      <div class="row"><span class="label">Fix</span><span class="value" id="gps_fix">—</span></div>
      <div class="row"><span class="label">Satellites</span><span class="value" id="satellites">—</span></div>
      <div class="row"><span class="label">Latitude</span><span class="value" id="lat">—</span></div>
      <div class="row"><span class="label">Longitude</span><span class="value" id="lon">—</span></div>
    </div>

    <div class="card">
      <h2>Battery</h2>
      <div class="row"><span class="label">Remaining</span><span class="value" id="battery_pct">—</span></div>
      <div class="row"><span class="label">Voltage</span><span class="value" id="battery_v">—</span></div>
    </div>

    <div class="card">
      <h2>Health</h2>
      <div class="row"><span class="label">EKF</span><span class="value" id="ekf">—</span></div>
      <div class="row"><span class="label">GPS OK</span><span class="value" id="gps_ok">—</span></div>
    </div>

    <div class="card">
      <h2>Drone App</h2>
      <div class="row"><span class="label">FSM State</span><span class="value" id="fsm_state">—</span></div>
      <div class="row"><span class="label">Autonomy</span><span class="value" id="autonomy">—</span></div>
      <div class="row"><span class="label">Target</span><span class="value" id="app_tgt_det">—</span></div>
      <div class="row"><span class="label">Confidence</span><span class="value" id="app_tgt_conf">—</span></div>
      <div class="row"><span class="label">Pixel X</span><span class="value" id="app_tgt_px_x">—</span></div>
      <div class="row"><span class="label">BBox height</span><span class="value" id="app_tgt_bbox_h">—</span></div>
    </div>

  </div>
  <div id="footer">Connecting to WebSocket…</div>

  <script>
    const ws = new WebSocket(`ws://${location.host}/ws`);
    const footer = document.getElementById('footer');

    ws.onopen  = () => footer.textContent = 'Connected';
    ws.onclose = () => footer.textContent = 'WebSocket closed — reload to reconnect';

    ws.onmessage = ({ data }) => {
      const d = JSON.parse(data);

      set('connected',   d.connected ? 'YES' : 'NO',       d.connected ? 'ok' : 'bad');
      set('mode',        d.mode);
      set('armed',       d.armed ? 'ARMED' : 'DISARMED',   d.armed ? 'warn' : 'ok');

      set('alt_rel',     fmt(d.altitude_relative_m, 1, ' m'));
      set('alt_abs',     fmt(d.altitude_absolute_m, 1, ' m'));
      set('groundspeed', fmt(d.groundspeed_m_s,     1, ' m/s'));
      set('climb',       fmt(d.climb_rate_m_s,      1, ' m/s'));
      set('heading',     d.heading_deg != null ? d.heading_deg.toFixed(0) + '°' : '—');

      set('gps_fix',    fixLabel(d.gps_fix_type),           d.gps_ok ? 'ok' : 'bad');
      set('satellites', d.satellites_visible,                d.satellites_visible >= 6 ? 'ok' : 'warn');
      set('lat',        d.latitude  != null ? d.latitude.toFixed(6)  : '—');
      set('lon',        d.longitude != null ? d.longitude.toFixed(6) : '—');

      const bpct = d.battery_remaining_pct;
      set('battery_pct', bpct != null ? bpct + '%' : '—',
          bpct == null ? '' : bpct <= 10 ? 'bad' : bpct <= 20 ? 'warn' : 'ok');
      set('battery_v',   fmt(d.battery_voltage_v, 2, ' V'));

      set('ekf',    d.ekf_ok  ? 'OK' : 'FAIL', d.ekf_ok  ? 'ok' : 'bad');
      set('gps_ok', d.gps_ok  ? 'OK' : 'FAIL', d.gps_ok  ? 'ok' : 'bad');

      set('fsm_state',    d.fsm_state,  fsmClass(d.fsm_state));
      set('autonomy',     d.autonomy === 'NONE' ? '—' : d.autonomy);
      set('app_tgt_det',  d.app_target_det  ? 'YES' : 'NO', d.app_target_det ? 'ok' : '');
      set('app_tgt_conf', d.app_target_det  ? (d.app_target_conf * 100).toFixed(0) + '%' : '—');
      set('app_tgt_px_x', d.app_target_det  ? d.app_target_px_x.toFixed(0) + ' px' : '—');
      set('app_tgt_bbox_h', d.app_target_det ? d.app_target_bbox_h.toFixed(0) + ' px' : '—');

      footer.textContent = 'Last update: ' + new Date().toLocaleTimeString();
    };

    function set(id, value, cls = '') {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent  = value ?? '—';
      el.className    = 'value ' + cls;
    }

    function fmt(val, decimals, unit) {
      return val != null ? val.toFixed(decimals) + unit : '—';
    }

    function fixLabel(t) {
      return ['NO FIX', 'NO FIX', '2D', '3D', 'DGPS', 'RTK FLOAT', 'RTK FIXED'][t] ?? String(t);
    }

    function fsmClass(state) {
      if (['FAILSAFE'].includes(state))                          return 'bad';
      if (['LAND', 'RTL', 'AUTONOMY', 'MANUAL'].includes(state)) return 'warn';
      if (['ARMED', 'TAKEOFF', 'HOVER', 'STANDBY'].includes(state)) return 'ok';
      return '';
    }
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

async def _broadcast_loop() -> None:
    """Push the latest vehicle state to all connected browsers at 5 Hz."""
    while True:
        await asyncio.sleep(0.2)
        if not _clients:
            continue
        payload = json.dumps({
            "connected":             vehicle_state.connected,
            "armed":                 vehicle_state.armed,
            "mode":                  vehicle_state.mode,
            "latitude":              vehicle_state.latitude,
            "longitude":             vehicle_state.longitude,
            "altitude_absolute_m":   vehicle_state.altitude_absolute_m,
            "altitude_relative_m":   vehicle_state.altitude_relative_m,
            "heading_deg":           vehicle_state.heading_deg,
            "groundspeed_m_s":       vehicle_state.groundspeed_m_s,
            "airspeed_m_s":          vehicle_state.airspeed_m_s,
            "climb_rate_m_s":        vehicle_state.climb_rate_m_s,
            "pitch_deg":             math.degrees(vehicle_state.pitch),
            "roll_deg":              math.degrees(vehicle_state.roll),
            "gps_fix_type":          vehicle_state.gps_fix_type,
            "satellites_visible":    vehicle_state.satellites_visible,
            "battery_remaining_pct": vehicle_state.battery_remaining_pct,
            "battery_voltage_v":     vehicle_state.battery_voltage_v,
            "battery_current_a":     vehicle_state.battery_current_a,
            "rssi_dbm":              vehicle_state.rssi_dbm,
            "distance_to_home_m":    vehicle_state.distance_to_home_m,
            "gps_ok":                vehicle_state.gps_ok,
            "ekf_ok":                vehicle_state.ekf_ok,
            "fsm_state":             vehicle_state.fsm_state_name,
            "autonomy":              vehicle_state.autonomy_name,
            "app_target_det":        vehicle_state.app_target_detected,
            "app_target_conf":       vehicle_state.app_target_confidence,
            "app_target_px_x":       vehicle_state.app_target_pixel_x,
            "app_target_bbox_h":     vehicle_state.app_target_bbox_height,
            "timestamp":             time.time(),
        })
        dead: Set[WebSocket] = set()
        for ws in _clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        _clients.difference_update(dead)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_broadcast_loop())
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return DASHBOARD_HTML


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        # Keep the connection open; browser sends nothing, so we just wait.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)


# ---------------------------------------------------------------------------
# MAVLink polling thread
# ---------------------------------------------------------------------------

def _mavlink_thread(connection_string: str, baudrate: int) -> None:
    """Connect to MAVLink and poll messages into vehicle_state at ~50 Hz."""
    print(f"[mavlink] Connecting to {connection_string} …")
    try:
        client = MAVLinkClient(connection_string=connection_string, baudrate=baudrate)
    except Exception as e:
        print(f"[mavlink] ERROR: could not open connection: {e}")
        return

    ok = client.wait_heartbeat(timeout=CONNECTION_TIMEOUT)
    if not ok:
        print(f"[mavlink] WARNING: no heartbeat received on {connection_string} — "
              "check connection string and that the vehicle/SITL is running.")
    else:
        print(f"[mavlink] Heartbeat received — streaming telemetry.")

    while True:
        try:
            client.update_vehicle_state(vehicle_state)
            if vehicle_state.connected and vehicle_state.heartbeat_timeout(timeout_s=3.0):
                vehicle_state.connected = False
                print("[mavlink] Heartbeat lost — vehicle disconnected.")
        except Exception as e:
            print(f"[mavlink] ERROR in poll loop: {e}")
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HVL Lift — Ground Station Dashboard Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python dashboard_server.py                          # production (uses CONNECTION_STRING from config)\n"
            "  python dashboard_server.py --sitl                   # SITL: listen on 0.0.0.0:14551 for MissionPlanner output\n"
            "  python dashboard_server.py --sitl 127.0.0.1         # SITL: listen on loopback only\n"
            "  python dashboard_server.py --connection /dev/ttyUSB0 --baud 57600\n"
        ),
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--sitl", metavar="BIND", nargs="?", const="0.0.0.0",
        help="SITL mode — listen on BIND:14551 for MAVLink pushed by MissionPlanner (default: 0.0.0.0)",
    )
    source.add_argument(
        "--connection", metavar="STRING",
        help="Explicit MAVLink connection string (e.g. /dev/ttyUSB0, udp:host:port)",
    )

    parser.add_argument(
        "--baud", type=int, default=BAUDRATE, metavar="RATE",
        help=f"Baud rate for serial connections (default: {BAUDRATE})",
    )
    parser.add_argument(
        "--port", type=int, default=8000, metavar="PORT",
        help="Dashboard HTTP/WebSocket server port (default: 8000)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = _parse_args()

    if args.sitl is not None:
        conn_str = f"udpin:{args.sitl}:14551"
        mode_label = f"SITL  ({conn_str})"
    elif args.connection:
        conn_str = args.connection
        mode_label = f"custom ({conn_str})"
    else:
        conn_str = CONNECTION_STRING
        mode_label = f"config ({conn_str})"

    print(f"[dashboard] MAVLink : {mode_label}")
    print(f"[dashboard] Serving : http://0.0.0.0:{args.port}")
    print(f"[dashboard] LAN URL : http://<this-machine-ip>:{args.port}")

    t = threading.Thread(target=_mavlink_thread, args=(conn_str, args.baud), daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
