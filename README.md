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

The system runs a single control loop in `main.py` that ties three layers together at a fixed update rate (default 50 Hz):

```
┌──────────────────────────────────────────────────────────────────┐
│                           main.py                                │
│                                                                  │
│  ① Drain MAVLink buffer → update VehicleState                   │
│  ② generate_event(vehicle_state, fsm) → FSM event               │
│  ③ fsm.handle_event(event) → state transition + command         │
│  ④ Sleep to maintain UPDATE_RATE                                 │
└───────────┬──────────────────┬──────────────────┬───────────────┘
            ▼                  ▼                  ▼
   ┌─────────────────┐  ┌────────────┐  ┌──────────────────┐
   │   autopilot/    │  │    fsm/    │  │    autonomy/     │
   │                 │  │            │  │                  │
   │ MAVLinkClient   │  │ Controller │  │ TargetDetector   │
   │ VehicleState    │  │ States     │  │ search*          │
   │ Commands        │  │ Events     │  │ travel*          │
   └─────────────────┘  │ EventGen   │  │ planner*         │
                        └────────────┘  └──────────────────┘
                                             sensors/
                                        camera*  health_monitor*

* = stub, not yet implemented
```

### Main loop detail

Each iteration of the loop in `main.py`:

1. **Poll MAVLink** — drains all pending serial messages into `VehicleState` (non-blocking). Handles `HEARTBEAT`, `GLOBAL_POSITION_INT`, `GPS_RAW_INT`, `SYS_STATUS`, and `VFR_HUD`.
2. **Generate event** — `event_generator.py` inspects `VehicleState` and the current FSM state to produce a single `Event` (heartbeat timeout → `FAULT`, boot + connected → `INIT_OK`, altitude reached → `ALTITUDE_REACHED`, battery thresholds → `CRITICAL_FAULT` / `RECOVERABLE_FAULT`).
3. **Drive FSM** — the event is passed to `FSMController.handle_event()`, which transitions state and can trigger autopilot commands.
4. **Timing** — `UPDATE_RATE` (default `0.05 s` = 20 Hz) keeps loop cadence stable.

---

## FSM — States & Transitions

```
                        ┌──────────────────────────────────┐
                        │             BOOT                 │
                        │  (waits for INIT_OK / INIT_FAIL) │
                        └────────────┬─────────────────────┘
                                     │ INIT_OK
                                     ▼
                                  STANDBY ◄──────────────────────┐
                                     │ ARM                        │
                                     ▼                            │
                                   ARMED ──(DISARM)──────────────┘
                                     │ TAKEOFF_CMD
                                     ▼
                                  TAKEOFF ──(TAKEOFF_ABORT)──► LAND
                                     │ ALTITUDE_REACHED
                                     ▼
             ┌──────────────────── HOVER ───────────────────────┐
             │ START_SEARCH /           │ MANUAL_OVERRIDE        │ LAND
             │ RESUME_SEARCH            ▼                        ▼
             │                       MANUAL                    LAND
             │ START_TRAVEL /          │ MANUAL_DONE             │ LANDED_DISARM
             ▼                         └──────────► HOVER        ▼
          AUTONOMY                                           STANDBY
    (SEARCH / TRAVEL sub-mode)
             │ TASK_COMPLETED / TASK_PAUSED
             └──────────────────► HOVER


  Any state ──(FAULT)──► FAILSAFE ──(RECOVERABLE_FAULT)──► RTL ──(HOME_REACHED)──► LAND
                                 └──(CRITICAL_FAULT)────────────────────────────► LAND
                                 └──(RESET_ON_GND)─────────────────────────────► STANDBY
```

### Events reference

| Event | Trigger |
|-------|---------|
| `INIT_OK` | First heartbeat received after boot |
| `INIT_FAIL` | Initialization error |
| `ARM` / `DISARM` | Arming state change from telemetry |
| `TAKEOFF_CMD` | Takeoff command issued |
| `ALTITUDE_REACHED` | `altitude_relative_m ≥ TAKEOFF_ALTITUDE` |
| `TAKEOFF_ABORT` | Takeoff sequence cancelled |
| `START_SEARCH` / `RESUME_SEARCH` | Begin / resume area search |
| `START_TRAVEL` / `RESUME_TRAVEL` | Begin / resume waypoint travel |
| `TASK_COMPLETED` / `TASK_PAUSED` | Autonomy task ended or suspended |
| `MANUAL_OVERRIDE` / `MANUAL_DONE` | Pilot takes / releases manual control |
| `LAND` | Land command issued |
| `LANDED_DISARM` | Drone on ground and disarmed |
| `HOME_REACHED` | RTL home position reached |
| `FAULT` | Heartbeat timeout |
| `RECOVERABLE_FAULT` | Battery ≤ `LOW_BATTERY_THRESHOLD` (20 %) |
| `CRITICAL_FAULT` | Battery ≤ `CRITICAL_BATTERY_THRESHOLD` (10 %) |
| `RESET_ON_GND` | Manual ground reset |

---

## File Structure

```
rasppi5/
│
├── main.py                      # Entry point & main control loop
├── config.py                    # All tunable parameters
│
├── autopilot/                   # MAVLink drone interface
│   ├── mavlink_client.py        # Serial connection + non-blocking message polling
│   ├── vehicle_state.py         # Live telemetry dataclass (GPS, battery, altitude…)
│   └── commands.py              # Flight commands: arm, takeoff, land, move (NED velocity)
│
├── fsm/                         # Finite State Machine
│   ├── controller.py            # FSMController — all state transitions
│   ├── states.py                # State and Autonomy enums
│   ├── event.py                 # Event enum (all FSM triggers)
│   └── event_generator.py      # Maps live VehicleState → Event each loop tick
│
├── autonomy/                    # Autonomous behaviours
│   ├── target_detection.py      # YOLOv8 real-time detection pipeline (working)
│   ├── search.py                # Area search pattern (stub)
│   ├── travel.py                # Waypoint navigation (stub)
│   └── planner.py               # Mission sequencer (stub)
│
├── sensors/                     # Sensor interfaces (stubs)
│   ├── camera.py                # Camera abstraction (stub)
│   └── health_monitor.py        # EKF / GPS / heartbeat checks (stub)
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
| `TAKEOFF_ALTITUDE` | `10` | Target takeoff altitude (metres) |
| `UPDATE_RATE` | `0.05` | Main loop period in seconds (20 Hz) |
| `LOW_BATTERY_THRESHOLD` | `20` | Battery % that triggers `RECOVERABLE_FAULT` |
| `CRITICAL_BATTERY_THRESHOLD` | `10` | Battery % that triggers `CRITICAL_FAULT` |
| `YOLO_MODEL_PATH` | `yolov8m.pt` | YOLO model file |
| `YOLO_UPDATE_RATE` | `0.2` | Target detection interval in seconds (5 Hz) |

---

## Setup

**1. Install dependencies**

```bash
pip install pymavlink pyserial ultralytics opencv-python
```

**2. Configure connection** in `config.py`

```python
CONNECTION_STRING = '/dev/ttyAMA0'   # UART port to flight controller
BAUDRATE          = 57600
TAKEOFF_ALTITUDE  = 10               # metres
YOLO_MODEL_PATH   = 'yolov8m.pt'    # or 'my_model.pt'
```

**3. Run**

```bash
python main.py
```

Press `Ctrl+C` to shut down cleanly.

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
- [ ] Connect target detection output to FSM events
- [ ] Implement `search.py` — area search pattern (e.g. lawnmower / spiral)
- [ ] Implement `travel.py` — waypoint navigation to a GPS target
- [ ] Implement `planner.py` — mission sequencing (search → travel → land)

### Phase 3 — Sensors & safety
- [ ] Implement `camera.py` — abstract camera interface (USB / CSI / RTSP)
- [ ] Implement `health_monitor.py` — heartbeat timeout, GPS, EKF checks → emit `FAULT` events
- [ ] Add geofence / safe-zone enforcement

### Phase 4 — Polish & reliability
- [ ] Replace hardcoded frame width (1000 px) in `target_detection.py` with dynamic `cap.get()`
- [ ] Add `requirements.txt`
- [ ] Add SITL test setup (ArduPilot SITL + MAVProxy)
- [ ] Replace bare `print()` calls with a structured logging system
