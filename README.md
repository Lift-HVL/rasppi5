# HVL Lift — Autonomous Drone System

> Autonomous quadcopter control software for Raspberry Pi 5, built by [HVL Lift](https://github.com/Lift-HVL).  
> Communicates with an ArduPilot flight controller over UART using MAVLink, runs YOLOv8-based real-time target detection, and manages all flight logic through a Finite State Machine.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3 |
| Autopilot protocol | MAVLink / pymavlink |
| Object detection | YOLOv8 (Ultralytics) |
| Computer vision | OpenCV |
| Hardware | Raspberry Pi 5 + ArduPilot FC |

---

## Architecture

The system runs a single control loop in `main.py` that ties three layers together at a fixed update rate:

```
┌──────────────────────────────────────────────────────────────────┐
│                           main.py                                │
│                                                                  │
│  ① Drain MAVLink buffer → update VehicleState                   │
│  ② Run YOLO detection + handle operator keypresses              │
│  ③ generate_event(vehicle_state, fsm, detector) → FSM event     │
│  ④ fsm.handle_event(event) → state transition                   │
│  ⑤ Dispatch autonomy behaviour for current FSM sub-mode         │
│  ⑥ Sleep to maintain UPDATE_RATE                                 │
└───────────┬──────────────────┬──────────────────┬───────────────┘
            ▼                  ▼                  ▼
   ┌─────────────────┐  ┌────────────┐  ┌──────────────────┐
   │   autopilot/    │  │    fsm/    │  │    autonomy/     │
   │                 │  │            │  │                  │
   │ MAVLinkClient   │  │ Controller │  │ TargetDetector   │
   │ VehicleState    │  │ States     │  │ TargetTracker    │
   │ Commands        │  │ Events     │  │ search*          │
   └─────────────────┘  │ EventGen   │  └──────────────────┘
                        └────────────┘
                                             sensors/
                                        camera  health_monitor

* = stub, not yet implemented
```

### Main loop detail

Each iteration of the loop in `main.py`:

1. **Poll MAVLink** — drains all pending serial messages into `VehicleState` (non-blocking). Handles `HEARTBEAT`, `GLOBAL_POSITION_INT`, `GPS_RAW_INT`, `SYS_STATUS`, and `VFR_HUD`.
2. **Detect + input** — runs one YOLO frame via `TargetDetector.update()`, displays it in a window, and reads any keypress. Operator keys are translated directly into FSM events (see [Operator Controls](#operator-controls)).
3. **Generate event** — `EventGenerator.generate()` inspects `VehicleState`, the current FSM state/sub-mode, and the detector to produce a single `Event` each tick. Priority order: connection fault → init → arm/disarm → altitude → landing → battery → target detection.
4. **Drive FSM** — the event (if any) is passed to `FSMController.handle_event()`, which updates `current_state` and `current_autonomy`.
5. **Dispatch autonomy** — if `current_state == AUTONOMY` and `current_autonomy == TRACK`, calls `TargetTracker.update()`. SEARCH and TRAVEL dispatch points are present but call stubs.
6. **Timing** — `UPDATE_RATE` (default `1 s`) keeps loop cadence stable.

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
    │             │      (yaw to center → advance → within reach)
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
| `START_SEARCH` | operator | `s` key while hovering |
| `RESUME_SEARCH` | operator | Resume paused search |
| `START_TRAVEL` / `RESUME_TRAVEL` | operator | Begin / resume waypoint travel |
| `START_TRACK` | auto | Target detected while in `Autonomy.SEARCH` |
| `RESUME_TRACK` | operator | Resume paused tracking |
| `TARGET_LOST` | auto | Target disappears while in `Autonomy.SEARCH` |
| `TASK_COMPLETED` / `TASK_PAUSED` | auto | Autonomy task ended or suspended |
| `MANUAL_OVERRIDE` / `MANUAL_DONE` | auto | Pilot takes / releases manual control |
| `LAND` | operator | `l` key |
| `LANDED_DISARM` | auto | Drone on ground and disarmed |
| `HOME_REACHED` | auto | RTL home position reached |
| `FAULT` | auto | Heartbeat timeout |
| `RECOVERABLE_FAULT` | auto | Battery ≤ `LOW_BATTERY_THRESHOLD` (20 %) |
| `CRITICAL_FAULT` | auto | Battery ≤ `CRITICAL_BATTERY_THRESHOLD` (10 %) |
| `RESET_ON_GND` | auto | Manual ground reset |

---

## Target Tracking

`TargetTracker` in `autonomy/track.py` runs whenever `current_autonomy == Autonomy.TRACK`. It operates in two sequential phases each tick:

```
target_detected?
    NO  → stop yaw + stop forward → return (done)
    YES ↓

pixel_error > YAW_DEADBAND?
    YES → Phase 1: yaw toward target (proportional), hold position
    NO  ↓

Phase 2: target is centered
    bbox_height / frame_height >= BBOX_REACH_THRESHOLD?
        YES → stop forward → return True (target reached)
        NO  → set_forward_speed(FORWARD_SPEED) → continue approaching
```

- **Yaw control** uses `set_yaw_rate()` with proportional gain (`YAW_GAIN`) clamped to `±YAW_RATE_MAX`.
- **Forward control** uses `set_forward_speed()` in `MAV_FRAME_BODY_NED` so "forward" always means the drone's current nose direction.
- **Proximity detection** uses bounding box height as a distance proxy — no rangefinder required. Tune `BBOX_REACH_THRESHOLD` to match the desired stop distance.

---

## Operator Controls

Controls are read from the OpenCV camera window each loop tick. The window must have focus for keypresses to register.

| Key | Action | Condition |
|-----|--------|-----------|
| `s` | Start search (`START_SEARCH`) | FSM must be in `HOVER` |
| `l` | Land (`LAND`) | Any state |
| `q` | Quit cleanly | Any state |

---

## File Structure

```
rasppi5/
│
├── main.py                      # Entry point & main control loop
├── config.py                    # All tunable parameters
├── requirements.txt             # Python dependencies
│
├── autopilot/                   # MAVLink drone interface
│   ├── mavlink_client.py        # Serial connection + non-blocking message polling
│   ├── vehicle_state.py         # Live telemetry dataclass (GPS, battery, altitude…)
│   └── commands.py              # Flight commands: arm, takeoff, land, yaw, velocity
│
├── fsm/                         # Finite State Machine
│   ├── controller.py            # FSMController — all state transitions
│   ├── states.py                # State and Autonomy enums
│   ├── event.py                 # Event enum (all FSM triggers)
│   └── event_generator.py      # Maps live VehicleState + detector → Event each tick
│
├── autonomy/                    # Autonomous behaviours
│   ├── target_detection.py      # YOLOv8 real-time detection pipeline
│   ├── track.py                 # Two-phase target tracker: yaw to center → advance
│   └── search.py                # Area search pattern (stub)
│
├── sensors/                     # Sensor interfaces 
│   ├── camera.py                # Camera abstraction
│   └── health_monitor.py        # EKF / GPS / heartbeat checks
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
| `CONNECTION_STRING` | `/dev/ttyAMA0` | UART serial port to flight controller |
| `BAUDRATE` | `57600` | MAVLink baud rate |
| `LISTEN_PORT` | `14550` | UDP listen port (GCS / SITL) |
| `CAMERA_INDEX` | `0` | OpenCV camera index |
| `TAKEOFF_ALTITUDE` | `10` | Target takeoff altitude (metres) |
| `UPDATE_RATE` | `1` | Main loop period in seconds |
| `YOLO_UPDATE_RATE` | `0.2` | Target detection interval in seconds (5 Hz) |
| `LOW_BATTERY_THRESHOLD` | `20` | Battery % that triggers `RECOVERABLE_FAULT` |
| `CRITICAL_BATTERY_THRESHOLD` | `10` | Battery % that triggers `CRITICAL_FAULT` |
| `YOLO_MODEL_PATH` | `models/yolov8m.pt` | YOLO model file |
| `YAW_RATE_MAX` | `30.0` | Maximum yaw rate (deg/s) |
| `YAW_GAIN` | `0.05` | Proportional gain: deg/s per pixel of error |
| `YAW_DEADBAND` | `20.0` | Pixel error below which yaw stops |
| `FORWARD_SPEED` | `1.5` | Approach speed once target is centered (m/s) |
| `BBOX_REACH_THRESHOLD` | `0.4` | Bounding box height fraction that means "within reach" |
| `DISTANCE_THRESHOLD` | `10.0` | Reserved for rangefinder-based proximity (metres) |

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure connection** in `config.py`

```python
CONNECTION_STRING = '/dev/ttyAMA0'   # UART port to flight controller
BAUDRATE          = 57600
TAKEOFF_ALTITUDE  = 10               # metres
YOLO_MODEL_PATH   = 'models/yolov8m.pt'    # or 'my_model.pt'
```

**3. Run**

```bash
python main.py
```

Press `Ctrl+C` or `q` in the camera window to shut down cleanly.

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
| `heading_deg` | `GLOBAL_POSITION_INT` | Compass heading (degrees) |
| `gps_fix_type` | `GPS_RAW_INT` | Fix type (3 = 3D fix) |
| `gps_ok` | `GPS_RAW_INT` | `True` when fix type ≥ 3 |
| `satellites_visible` | `GPS_RAW_INT` | Number of visible satellites |
| `battery_voltage_v` | `SYS_STATUS` | Battery voltage (V) |
| `battery_remaining_pct` | `SYS_STATUS` | Battery percentage |
| `groundspeed_m_s` | `VFR_HUD` | Horizontal speed (m/s) |
| `climb_rate_m_s` | `VFR_HUD` | Vertical speed (m/s, positive = climb) |

---

## Roadmap

### Phase 1 — Core integration ✅
- [x] Wire `FSMController` and `MAVLinkClient` into `main.py`
- [x] Drive FSM transitions from live MAVLink telemetry (battery, GPS, heartbeat)
- [x] `event_generator.py` maps vehicle state to FSM events each tick

### Phase 2 — Autonomy behaviours
- [x] `START_TRACK` event auto-generated when target appears during `Autonomy.SEARCH`
- [x] `TARGET_LOST` event auto-generated when target disappears during `Autonomy.SEARCH`
- [x] `track.py` — `TargetTracker` yaws to center, then advances until `BBOX_REACH_THRESHOLD`
- [x] FSM autonomy dispatch in `main.py` — branches on `fsm.current_autonomy`
- [x] Operator keyboard input — `s` starts search, `l` lands, `q` quits
- [ ] Implement `search.py` — area search pattern (e.g. lawnmower / spiral)

### Phase 3 — Sensors & safety
- [x] Implement `health_monitor.py` — GPS fix and EKF health checks → emit `FAULT` events
- [x] Implement `camera.py` — abstract camera interface (USB / CSI / RTSP)

### Phase 4 — Polish & reliability
- [x] Dynamic frame dimensions in `target_detection.py` (uses `frame.shape`)
- [x] Add `requirements.txt`
- [x] Replace bare `print()` calls with a structured logging system
