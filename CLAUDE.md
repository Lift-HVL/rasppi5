# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Autonomous drone (quadcopter) control system for Raspberry Pi 5. The drone communicates with an ArduPilot flight controller over serial (UART) using MAVLink, runs YOLOv8-based target detection, and navigates via a Finite State Machine.

## Running

```bash
python main.py
```

No build step. Dependencies (install manually or via future requirements.txt):
- `pymavlink` — MAVLink protocol
- `ultralytics` — YOLOv8
- `opencv-python` — computer vision

## Architecture

The system is organized around three layers:

**1. FSM layer (`fsm/`)** — Core control flow. `FSMController` in `fsm.py` manages state transitions triggered by `Event` enum values. States: BOOT → STANDBY → ARMED → TAKEOFF → HOVER → AUTONOMY/MANUAL → LAND/RTL. The FSM is not yet wired into `main.py`; it is defined but not running.

**2. Autopilot layer (`autopilot/`)** — MAVLink interface.
- `mavlink_client.py` — connects to the flight controller, calls `update_vehicle_state()` in a loop
- `vehicle_state.py` — dataclass holding live telemetry (position, battery, mode, armed status)
- `commands.py` — sends flight commands (arm, takeoff, land, set mode, etc.)

**3. Autonomy layer (`autonomy/`)** — Behavior implementations.
- `target_detection.py` — working YOLOv8 pipeline; confidence threshold 0.8, classifies detections as left/right of frame (hardcoded frame width 1000 px)
- `search.py`, `travel.py`, `planner.py` — stubs, not yet implemented

## Configuration

All tunable parameters are in `config.py`:

| Key | Default | Meaning |
|-----|---------|---------|
| `CONNECTION_STRING` | `/dev/ttyAMA0` | Serial port to flight controller |
| `BAUDRATE` | `57600` | MAVLink baud rate |
| `TAKEOFF_ALTITUDE` | `10` | Target altitude in meters |
| `FSM_UPDATE_RATE` | `0.05` | FSM tick period (50 Hz) |
| `LOW_BATTERY_THRESHOLD` | `20` | % battery for warning |
| `CRITICAL_BATTERY_THRESHOLD` | `10` | % battery for failsafe |
| `YOLO_MODEL_PATH` | `yolov8m.pt` | Model file (also `my_model.pt` available) |

## Current Development State

- Target detection pipeline works end-to-end.
- FSM framework is fully defined but not integrated into the main loop.
- `search.py`, `travel.py`, `planner.py`, `camera.py`, `health_monitor.py` are empty stubs.
- Next integration step: instantiate `FSMController` and `MAVLinkClient` in `main.py` and drive the FSM from real telemetry events.
