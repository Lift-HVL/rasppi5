# HVL Lift — Autonomous Drone System

> Autonomous quadcopter control software for Raspberry Pi 5 (air Pi), built by [HVL Lift](https://github.com/Lift-HVL).  
> Communicates with an ArduPilot flight controller over UART using MAVLink, runs YOLOv8-based real-time target detection, and manages all flight logic through a Finite State Machine.  
> Includes a ground-station WebSocket server and React dashboard accessible from any browser on the same network.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3 |
| Autopilot protocol | MAVLink / pymavlink |
| Object detection | YOLOv8 (Ultralytics) |
| Computer vision | OpenCV |
| Ground station server | FastAPI + uvicorn |
| Dashboard frontend | React Router 7 + TailwindCSS |
| Hardware | Raspberry Pi 5 + ArduPilot FC |

---

## Architecture

The system runs a single control loop in `main.py` that ties three layers together at a fixed update rate:

```
┌──────────────────────────────────────────────────────────────────┐
│                           main.py                                │
│                                                                  │
│  ① Drain MAVLink buffer → update VehicleState                   │
│  ② Run YOLO detection + display camera frame                    │
│  ③ Read terminal keypress → operator FSM events                 │
│  ④ generate_event(vehicle_state, fsm, detector) → FSM event     │
│  ⑤ fsm.handle_event(event) → state transition                   │
│  ⑥ Dispatch autonomy behaviour for current FSM sub-mode         │
│  ⑦ Inject FSM + target telemetry → MAVLink (NAMED_VALUE_FLOAT)  │
│  ⑧ Log iteration + sleep to maintain UPDATE_RATE                │
└───────────┬──────────────────┬──────────────────┬───────────────┘
            ▼                  ▼                  ▼
   ┌─────────────────┐  ┌────────────┐  ┌──────────────────┐
   │   autopilot/    │  │    fsm/    │  │    autonomy/     │
   │                 │  │            │  │                  │
   │ MAVLinkClient   │  │ Controller │  │ TargetDetector   │
   │ VehicleState    │  │ States     │  │ TargetTracker    │
   │ Commands        │  │ Events     │  │ Search*          │
   └─────────────────┘  │ EventGen   │  └──────────────────┘
                        └────────────┘
                             sensors/           utils/
                        Camera  HealthMonitor  Logger  KeyboardListener

* = in progress
```

`ground_station` starts as a background daemon thread inside `main.py`. It shares the same `VehicleState`, `FSMController`, and `TargetDetector` instances directly — no UDP or inter-process communication needed.

```
Flight controller ──(serial /dev/ttyAMA0)──► main.py
                                                 │ shared object references
                                                 ▼
                                         ground_station (background thread)
                                                 │ WebSocket /ws  (port 8000)
                                                 ▼
                                          Browser dashboard
                                         (any PC on same WLAN)
```

### Main loop detail

Each iteration of the loop in `main.py`:

1. **Poll MAVLink** — drains all pending serial messages into `VehicleState` (non-blocking).
2. **Detect** — runs one YOLO frame via `TargetDetector.update()` and displays the annotated frame in an OpenCV window.
3. **Operator input** — `KeyboardListener` reads single keypresses from the terminal (non-blocking). Keys are mapped directly to FSM events (see [Operator Controls](#operator-controls)).
4. **Generate event** — `EventGenerator.generate()` inspects `VehicleState`, the current FSM state/sub-mode, and the detector to produce a single `Event` each tick.
5. **Drive FSM** — the event (if any) is passed to `FSMController.handle_event()`, which updates `current_state` and `current_autonomy`.
6. **Dispatch autonomy** — branches on `fsm.current_autonomy`: `TRACK` calls `TargetTracker.update()` and fires `TASK_COMPLETED` when target is reached.
7. **Inject telemetry** — `MAVLinkClient.send_named_float()` injects FSM state, autonomy sub-state, and target detection data into the MAVLink stream as `NAMED_VALUE_FLOAT` messages, making them available to the ground station dashboard.
8. **Log + sleep** — `Logger` writes a timestamped status line to file, then sleeps to maintain `UPDATE_RATE`.

---

## FSM — States & Transitions

```
                        ┌──────────────────────────────────┐
                        │             BOOT                 │
                        │  (waits for INIT_OK / INIT_FAIL) │
                        └────────────┬─────────────────────┘
                                     │ INIT_OK
                                     ▼
                                  STANDBY ◄──────────────────────────┐
                                     │ ARM                            │
                                     ▼                                │
                                   ARMED ──(DISARM)──────────────────┘
                                     │ TAKEOFF_CMD
                                     ▼
                                  TAKEOFF ──(TAKEOFF_ABORT)──► LAND
                                     │ ALTITUDE_REACHED
                                     ▼
             ┌──────────────────── HOVER ──────────────────────────┐
             │ START_SEARCH /           │ MANUAL_OVERRIDE           │ LAND
             │ RESUME_SEARCH            ▼                           ▼
             │                       MANUAL                       LAND
             │                         │ MANUAL_DONE               │ LANDED_DISARM
             ▼                         └──────────► HOVER          ▼
          AUTONOMY                                             STANDBY
    ┌─────────────┐
    │   SEARCH    │ ◄── START_SEARCH / TARGET_LOST
    │             │
    │   START_TRACK (target detected)
    │             │
    │   TRACK     │ ──── TargetTracker runs each tick
    │             │      (PI yaw to center → advance → within reach → TASK_COMPLETED)
    └─────────────┘
             │ TASK_COMPLETED / TASK_PAUSED
             └──────────────────► HOVER


  Any state ──(FAULT)──► FAILSAFE ──(RECOVERABLE_FAULT)──► RTL ──(HOME_REACHED)──► LAND
                                 └──(CRITICAL_FAULT)────────────────────────────► LAND
                                 └──(RESET_ON_GND)─────────────────────────────► STANDBY
```

### Events reference

| Event | Source | Trigger |
|-------|--------|---------|
| `INIT_OK` | auto | First heartbeat received after boot |
| `INIT_FAIL` | auto | Initialization error |
| `ARM` / `DISARM` | auto | Arming state change from telemetry |
| `TAKEOFF_CMD` | operator | Takeoff command issued |
| `ALTITUDE_REACHED` | auto | `altitude_relative_m ≥ TAKEOFF_ALTITUDE` |
| `TAKEOFF_ABORT` | operator | Takeoff sequence cancelled |
| `START_SEARCH` | operator | `s` key while in `HOVER` |
| `RESUME_SEARCH` | operator | Resume paused search |
| `START_TRACK` | auto | Target detected while in `Autonomy.SEARCH` |
| `RESUME_TRACK` | operator | Resume paused tracking |
| `TARGET_LOST` | auto | Target disappears while in `Autonomy.SEARCH` or `Autonomy.TRACK` |
| `TASK_COMPLETED` | auto | Target reached (`TargetTracker.update()` returns `True`) |
| `TASK_PAUSED` | operator | Autonomy task suspended |
| `MANUAL_OVERRIDE` / `MANUAL_DONE` | auto | Pilot takes / releases manual control |
| `LAND` | operator | `l` key |
| `LANDED_DISARM` | auto | Drone on ground and disarmed |
| `HOME_REACHED` | auto | RTL home position reached |
| `FAULT` | auto | Heartbeat timeout, GPS loss, or EKF failure |
| `RECOVERABLE_FAULT` | auto | Battery ≤ `LOW_BATTERY_THRESHOLD` (20 %) |
| `CRITICAL_FAULT` | auto | Battery ≤ `CRITICAL_BATTERY_THRESHOLD` (10 %) |
| `RESET_ON_GND` | operator | `r` key while in `FAILSAFE` |

---

## Target Tracking

`TargetTracker` in `autonomy/track.py` runs whenever `current_autonomy == Autonomy.TRACK`. It operates in two sequential phases each tick, with a PI regulator controlling yaw:

```
target_detected?
    NO  → reset PI state, stop yaw + forward → return True (done)
    YES ↓

pixel_error > YAW_DEADBAND?
    YES → Phase 1: PI yaw toward target, hold position
    NO  ↓

Phase 2: target is centered
    bbox_height / frame_height >= BBOX_REACH_THRESHOLD?
        YES → stop forward → return True (target reached → TASK_COMPLETED)
        NO  → set_forward_speed(FORWARD_SPEED) → continue approaching
```

**PI regulator:**
- Output = `YAW_KP × pixel_error + YAW_KI × integral`
- Integral accumulates `pixel_error × dt` each tick, clamped to `±YAW_INTEGRAL_MAX` (anti-windup)
- Integral and timer reset to zero when target is lost, preventing stale error from affecting the next sighting
- Output clamped to `±YAW_RATE_MAX`

**Forward control** uses `set_forward_speed()` with `MAV_FRAME_BODY_NED` so "forward" always means the drone's current nose direction regardless of heading.

**Proximity detection** uses bounding box height as a distance proxy — no rangefinder required. Tune `BBOX_REACH_THRESHOLD` to match the desired stop distance.

---

## Operator Controls

Controls are read from the **terminal window** each loop tick via `KeyboardListener` (no need to focus the camera window).

| Key | Action | Condition |
|-----|--------|-----------|
| `t` | Takeoff (`TAKEOFF_CMD`) | FSM must be in `ARMED` |
| `s` | Start search (`START_SEARCH`) | FSM must be in `HOVER` |
| `l` | Land (`LAND`) | Any state |
| `r` | Reset from failsafe (`RESET_ON_GND`) | FSM must be in `FAILSAFE` |
| `q` | Quit cleanly | Any state |

---

## Ground Station Dashboard

`ground_station.py` runs as a separate process on the same Pi. It listens for a MAVLink UDP fan-out from `main.py`, aggregates all telemetry (including FSM state and target detection injected via `NAMED_VALUE_FLOAT`), and serves a React dashboard at port 8000.

Any browser on the same WLAN can open `http://<pi-ip>:8000` to see live telemetry.

**Build the frontend once** (requires Node.js on the development machine; the built files are served statically by Python):

```bash
cd ground-station-dashboard
npm install
npm run build
```

The dashboard server starts automatically when `main.py` runs — no separate process needed. `ground_station.start()` is called inside `main()` and launches a daemon thread serving the FastAPI app on port 8000.

---

## File Structure

```
rasppi5/
│
├── main.py                      # Entry point & main control loop
├── ground_station.py            # Ground station WebSocket server + dashboard host
├── config.py                    # All tunable parameters
├── requirements.txt             # Python dependencies
│
├── autopilot/                   # MAVLink drone interface
│   ├── mavlink_client.py        # Connection, heartbeat, send_named_float
│   ├── vehicle_state.py         # Live telemetry dataclass (GPS, battery, attitude, FSM…)
│   └── commands.py              # Flight commands: arm, takeoff, land, yaw, velocity
│
├── fsm/                         # Finite State Machine
│   ├── controller.py            # FSMController — all state transitions
│   ├── states.py                # State and Autonomy enums
│   ├── event.py                 # Event enum (all FSM triggers)
│   └── event_generator.py       # Maps VehicleState + detector + health → Event each tick
│
├── autonomy/                    # Autonomous behaviours
│   ├── target_detection.py      # YOLOv8 real-time detection pipeline
│   ├── track.py                 # PI-regulated target tracker: yaw to center → advance
│   └── search.py                # Lawnmower search pattern (in progress)
│
├── sensors/                     # Sensor interfaces
│   ├── camera.py                # Camera abstraction (decouples source from detector)
│   └── health_monitor.py        # GPS fix and EKF health checks → FAULT events
│
├── utils/                       # Utilities
│   ├── logger.py                # Timestamped file logging each loop iteration
│   └── keyboard.py              # Non-blocking terminal keyboard listener (Linux + Windows)
│
├── ground-station-dashboard/    # React dashboard frontend source
│   ├── app/                     # React Router routes, components, hooks
│   ├── public/                  # Static assets
│   ├── package.json
│   └── build/client/            # Built SPA served by ground_station.py (git-ignored)
│
└── models/                      # ML model weights
    ├── yolov8m.pt               # YOLOv8 medium (base)
    └── my_model.pt              # Custom trained model
```

---

## Configuration

All tunable values live in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CONNECTION_STRING` | `/dev/ttyAMA0` | MAVLink connection to flight controller |
| `BAUDRATE` | `57600` | MAVLink baud rate |
| `CONNECTION_TIMEOUT` | `10.0` | Seconds to wait for heartbeat before continuing |
| `CAMERA_INDEX` | `0` | OpenCV camera index |
| `TAKEOFF_ALTITUDE` | `10` | Target takeoff altitude (metres) |
| `UPDATE_RATE` | `1` | Main loop period in seconds |
| `YOLO_UPDATE_RATE` | `0.2` | Target detection interval in seconds (5 Hz) |
| `LOW_BATTERY_THRESHOLD` | `20` | Battery % that triggers `RECOVERABLE_FAULT` |
| `CRITICAL_BATTERY_THRESHOLD` | `10` | Battery % that triggers `CRITICAL_FAULT` |
| `MIN_SATELLITES` | `6` | Minimum satellites for healthy GPS |
| `YOLO_MODEL_PATH` | `models/yolov8m.pt` | YOLO model file |
| `YAW_KP` | `0.1` | PI proportional gain (deg/s per pixel) |
| `YAW_KI` | `0.01` | PI integral gain |
| `YAW_RATE_MAX` | `30.0` | Maximum yaw rate (deg/s) |
| `YAW_DEADBAND` | `20.0` | Pixel error below which yaw stops |
| `YAW_INTEGRAL_MAX` | `100.0` | Anti-windup clamp on PI integral term |
| `FORWARD_SPEED` | `1.5` | Approach speed once target is centered (m/s) |
| `BBOX_REACH_THRESHOLD` | `0.4` | Bounding box height fraction that means "within reach" |
| `LOG_DIR` | `logs` | Directory for log files |

---

## Setup

**1. Install Python dependencies**

```bash
pip install -r requirements.txt
```

**2. Build the dashboard frontend** (on the development machine, once)

```bash
cd ground-station-dashboard
npm install
npm run build
cd ..
```

**3. Configure connection** in `config.py`

```python
CONNECTION_STRING = '/dev/ttyAMA0'   # serial to flight controller
BAUDRATE          = 57600
TAKEOFF_ALTITUDE  = 10
YOLO_MODEL_PATH   = 'models/yolov8m.pt'
```

**4. Run**

```bash
python main.py
```

Open `http://<pi-ip>:8000` in any browser on the same network. The dashboard starts automatically alongside the main control loop.

Press `q` in the `main.py` terminal or `Ctrl+C` to shut down cleanly.

---

## Telemetry tracked by VehicleState

| Field | Source MAVLink message | Description |
|-------|------------------------|-------------|
| `connected` | `HEARTBEAT` | Whether the flight controller is reachable |
| `armed` | `HEARTBEAT` | Motor arm status |
| `mode` | `HEARTBEAT` | Flight mode string (e.g. `GUIDED`, `LOITER`) |
| `altitude_relative_m` | `GLOBAL_POSITION_INT` | Height above takeoff point (m) |
| `altitude_absolute_m` | `GLOBAL_POSITION_INT` | Height above sea level (m) |
| `latitude` / `longitude` | `GLOBAL_POSITION_INT` | GPS coordinates (degrees) |
| `heading_deg` | `GLOBAL_POSITION_INT` / `VFR_HUD` | Compass heading (degrees) |
| `gps_fix_type` | `GPS_RAW_INT` | Fix type (3 = 3D fix) |
| `gps_ok` | `GPS_RAW_INT` | `True` when fix type ≥ 3 |
| `satellites_visible` | `GPS_RAW_INT` | Number of visible satellites |
| `battery_voltage_v` | `SYS_STATUS` | Battery voltage (V) |
| `battery_remaining_pct` | `SYS_STATUS` | Battery percentage |
| `battery_current_a` | `SYS_STATUS` | Battery current draw (A) |
| `groundspeed_m_s` | `VFR_HUD` | Horizontal speed (m/s) |
| `airspeed_m_s` | `VFR_HUD` | Airspeed (m/s) |
| `climb_rate_m_s` | `VFR_HUD` | Vertical speed (m/s, positive = climb) |
| `pitch_deg` / `roll_deg` | `ATTITUDE` | Attitude angles (degrees) |
| `rssi_dbm` | `RADIO_STATUS` | Radio link signal strength (dBm) |
| `ekf_ok` | `EKF_STATUS_REPORT` | `True` when all EKF health flags are set |
| `fsm_state_name` | `NAMED_VALUE_FLOAT` (`fsm_state`) | Current FSM state label |
| `autonomy_name` | `NAMED_VALUE_FLOAT` (`autonomy`) | Current autonomy sub-state |
| `app_target_detected` | `NAMED_VALUE_FLOAT` (`tgt_det`) | Whether a target is currently detected |
| `app_target_confidence` | `NAMED_VALUE_FLOAT` (`tgt_conf`) | YOLO detection confidence |
| `app_target_pixel_x` | `NAMED_VALUE_FLOAT` (`tgt_px_x`) | Target pixel X position in frame |
| `app_target_bbox_height` | `NAMED_VALUE_FLOAT` (`tgt_bbox_h`) | Target bounding box height (pixels) |

---

## Roadmap

### Phase 1 — Core integration ✅
- [x] Wire `FSMController` and `MAVLinkClient` into `main.py`
- [x] Drive FSM transitions from live MAVLink telemetry (battery, GPS, heartbeat)
- [x] `event_generator.py` maps vehicle state to FSM events each tick

### Phase 2 — Autonomy behaviours ✅
- [x] `START_TRACK` event auto-generated when target appears during `Autonomy.SEARCH`
- [x] `TARGET_LOST` event auto-generated when target disappears during `Autonomy.SEARCH` or `Autonomy.TRACK`
- [x] `track.py` — `TargetTracker` with PI regulator: yaws to center, then advances until `BBOX_REACH_THRESHOLD`
- [x] `TASK_COMPLETED` fired automatically when target is reached
- [x] FSM autonomy dispatch in `main.py` — branches on `fsm.current_autonomy`
- [ ] Implement `search.py` — non-blocking lawnmower `update()` method (in progress)
- [ ] Wire `Autonomy.SEARCH` dispatch in `main.py` once `search.py` is complete

### Phase 3 — Sensors & safety ✅
- [x] `health_monitor.py` — GPS fix and EKF health checks wired into `event_generator.py`
- [x] `camera.py` — camera abstraction decoupling source from `TargetDetector`
- [x] `EKF_STATUS_REPORT` MAVLink message handled in `vehicle_state.py`

### Phase 4 — Polish & reliability ✅
- [x] Non-blocking startup — times out after `CONNECTION_TIMEOUT` if no autopilot found
- [x] Terminal keyboard input via `KeyboardListener` (no camera window focus needed)
- [x] `r` key resets FSM from `FAILSAFE` to `STANDBY` after reconnection
- [x] Structured logging via `utils/logger.py`
- [x] PI regulator in `track.py` with anti-windup and reset on target loss
- [x] `requirements.txt` added

### Phase 5 — Ground station dashboard ✅
- [x] `VehicleState` extended with attitude, airspeed, RSSI, battery current, FSM/autonomy/target fields
- [x] FSM + target telemetry injected into MAVLink stream via `NAMED_VALUE_FLOAT`
- [x] `ground_station.py` — FastAPI WebSocket server broadcasting telemetry at 5 Hz
- [x] React dashboard served as static SPA from the Pi
- [x] Dashboard starts as a background thread in `main.py` — shares `VehicleState`, `FSMController`, and `TargetDetector` directly, no UDP needed
- [ ] Tweak `track.py` — zone-based yaw speeds (closer to center = slower correction)
