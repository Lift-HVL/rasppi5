# Ground Station Dashboard

React dashboard for HVL Lift telemetry. It reads vehicle state from the MAVLink WebSocket bridge and displays flight state, attitude, GPS, battery, speed, and video.

## Install

```powershell
npm install
```

## Run

```powershell
npm run dev
```

Open:

```text
http://localhost:5173
```

## MAVLink Bridge URL

Default dashboard setting:

```text
ws://127.0.0.1:8000/ws
```

That matches the recommended bridge command:

```powershell
cd ..\mavlink-bridge
python ws_server.py --udp-host 127.0.0.1 --udp-port 14550 --ws-host 127.0.0.1 --ws-port 8000 --forward 127.0.0.1:14552
```

If the bridge runs on another computer, change the dashboard setting to:

```text
ws://<bridge-machine-ip>:8000/ws
```

## Expected Data Flow

```text
Mission Planner / SITL -> mavlink-bridge/ws_server.py -> dashboard
                                      |
                                      v
                                   rasppi5
```

The dashboard consumes normalized telemetry from `mavlink-bridge/ws_server.py`. It also has fallback parsing for common raw MAVLink messages:

- `HEARTBEAT`
- `GLOBAL_POSITION_INT`
- `GPS_RAW_INT`
- `SYS_STATUS`
- `VFR_HUD`
- `ATTITUDE`
- `NAMED_VALUE_FLOAT` from `rasppi5`

## Settings

Use the Settings page to edit:

- Bridge WebSocket URL
- vehicle alert thresholds
- video URL
- display units and geofence values

The serial, UDP, and TCP fields describe backend link settings, but this frontend does not open serial or UDP directly from the browser. The browser should normally use the WebSocket bridge.

## Checks

```powershell
npm run typecheck
```
