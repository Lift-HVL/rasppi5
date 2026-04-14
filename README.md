# HVL Lift — Autonomous Drone System

> Autonomous quadcopter control software for Raspberry Pi 5, built by [HVL Lift](https://github.com/Lift-HVL).  
> Uses MAVLink to talk to an ArduPilot flight controller, YOLOv8 for real-time target detection, and a Finite State Machine to manage flight modes.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3 |
| Autopilot protocol | MAVLink / pymavlink |
| Object detection | YOLOv8 (Ultralytics) |
| Computer vision | OpenCV |
| Hardware | Raspberry Pi 5 + ArduPilot FC |

---

## Architecture

The system is split into three layers that work together:

```
┌─────────────────────────────────────────────────────┐
│                     main.py                         │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌────────────┐ ┌─────────────────┐
│   autonomy/ │ │    fsm/    │ │   autopilot/    │
│             │ │            │ │                 │
│  target_    │ │ FSMCtrl    │ │ MAVLinkClient   │
│  detection  │ │ states     │ │ VehicleState    │
│  search*    │ │ events     │ │ Commands        │
│  travel*    │ │            │ │                 │
│  planner*   │ └────────────┘ └─────────────────┘
└─────────────┘
                    sensors/
               camera*  health_monitor*

* = stub, not yet implemented
```

**FSM States and transitions:**

```
BOOT ──(INIT_OK)──► STANDBY ──(ARM)──► ARMED ──(TAKEOFF_CMD)──► TAKEOFF
                       ▲                  │                          │
                       │               (DISARM)               (ALTITUDE_REACHED)
                       │                  │                          ▼
                  (LANDED_DISARM)          └────────────────────► HOVER
                       │                                         │     │
                     LAND ◄─────────────────────────────(LAND)──┘     │
                       ▲                                         │     │
                       │                              (START_SEARCH)  (START_TRAVEL)
                  (CRITICAL_FAULT)                               ▼
                       │                                     AUTONOMY
                    FAILSAFE ◄────────────(FAULT)─────────────────┘
                       │
               (RECOVERABLE_FAULT)
                       ▼
                      RTL ──(HOME_REACHED)──► LAND
```

---

## File Structure

```
rasppi5/
│
├── main.py                      # Entry point
├── config.py                    # All tunable parameters
│
├── autonomy/                    # Autonomous behaviours
│   ├── target_detection.py      # YOLOv8 real-time detection (working)
│   ├── search.py                # Search pattern logic (stub)
│   ├── travel.py                # Waypoint travel logic (stub)
│   └── planner.py               # Mission planner (stub)
│
├── fsm/                         # Finite State Machine
│   ├── fsm.py                   # FSMController — handles all state transitions
│   ├── states.py                # State and Autonomy enums
│   └── event.py                 # Event enum (triggers for the FSM)
│
├── autopilot/                   # MAVLink drone interface
│   ├── mavlink_client.py        # Connection + non-blocking message polling
│   ├── vehicle_state.py         # Live telemetry dataclass
│   └── commands.py              # Flight commands (arm, takeoff, land, move…)
│
├── sensors/                     # Sensor interfaces (stubs)
│   ├── camera.py
│   └── health_monitor.py
│
└── models/                      # ML model weights
    ├── yolov8m.pt               # YOLOv8 medium (base model)
    └── my_model.pt              # Custom trained model
```

---

## Setup

**1. Install dependencies**

```bash
pip install pymavlink ultralytics opencv-python
```

**2. Configure connection** in `config.py`:

```python
CONNECTION_STRING = '/dev/ttyAMA0'   # UART to flight controller
BAUDRATE          = 57600
TAKEOFF_ALTITUDE  = 10               # metres
YOLO_MODEL_PATH   = 'yolov8m.pt'    # or 'my_model.pt'
```

**3. Run**

```bash
python main.py
```

Press `q` to quit the detection window.

---

## Roadmap

### Phase 1 — Core integration
- [ ] Wire `FSMController` and `MAVLinkClient` into `main.py`
- [ ] Drive FSM transitions from live MAVLink telemetry (battery, GPS, heartbeat)
- [ ] Connect target detection output to FSM events

### Phase 2 — Autonomy behaviours
- [ ] Implement `search.py` — area search pattern (e.g. lawnmower / spiral)
- [ ] Implement `travel.py` — waypoint navigation to a GPS target
- [ ] Implement `planner.py` — mission sequencing (search → travel → land)

### Phase 3 — Sensors & safety
- [ ] Implement `camera.py` — abstract camera interface (USB / CSI / RTSP)
- [ ] Implement `health_monitor.py` — heartbeat timeout, battery, GPS, EKF checks → emit FAULT events
- [ ] Add geofence / safe-zone enforcement

### Phase 4 — Polish & reliability
- [ ] Replace hardcoded frame width (1000 px) in `target_detection.py` with dynamic `cap.get()`
- [ ] Add `requirements.txt`
- [ ] Add simulation / SITL test setup (ArduPilot SITL + MAVProxy)
- [ ] Logging system (file + console) instead of bare `print()` calls
