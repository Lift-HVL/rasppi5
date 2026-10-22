from utils.logger import Logger
from utils.keyboard import KeyboardListener
import sys
import os
import time
import socket
import json

from autonomy.target_detection import TargetDetector
from autonomy.track import TargetTracker

from autopilot.mavlink_client import MAVLinkClient
from autopilot.vehicle_state import VehicleState
from autopilot.commands import AutopilotCommands

from fsm.controller import FSMController
from fsm.event_generator import EventGenerator
from fsm.event import Event
from fsm.states import State, Autonomy

from config import UPDATE_RATE

import math
from collections import deque
from pymavlink import mavutil

# ==================================================
# Extra telemetry: attitude, STATUSTEXT, EKF, vibration ...
# ==================================================

SEVERITY = {
    0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR",
    4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG",
}

# Fields added to VehicleState (sent in the telemetry "vehicle" block)
EXTRA_FIELDS = [
    # Attitude
    "roll_deg", "pitch_deg", "yaw_deg",
    "roll_rate_dps", "pitch_rate_dps", "yaw_rate_dps",
    # VFR_HUD
    "airspeed_m_s", "throttle_pct",
    # SYS_STATUS
    "battery_current_a", "cpu_load_pct", "prearm_ok", "sensors_unhealthy",
    # GPS quality
    "gps_hdop",
    # EKF
    "ekf_flags", "ekf_vel_var", "ekf_pos_var", "ekf_compass_var",
    # Vibration
    "vibe_x", "vibe_y", "vibe_z", "vibe_clipping",
]

# Message -> rate (Hz) to ask ArduPilot for
STREAMS = {
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE: 10,
    mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD: 4,
    mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS: 2,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT: 2,
    mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT: 2,
    mavutil.mavlink.MAVLINK_MSG_ID_VIBRATION: 2,
}

PREARM_BIT = mavutil.mavlink.MAV_SYS_STATUS_PREARM_CHECK

# Sensor bits worth naming when unhealthy
SENSOR_NAMES = {
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_GYRO: "gyro",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_ACCEL: "accel",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_MAG: "compass",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_ABSOLUTE_PRESSURE: "baro",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_GPS: "gps",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_RC_RECEIVER: "rc",
    mavutil.mavlink.MAV_SYS_STATUS_AHRS: "ahrs",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_BATTERY: "battery",
    mavutil.mavlink.MAV_SYS_STATUS_SENSOR_MOTOR_OUTPUTS: "motors",
}


def init_extra_state(vs, max_texts: int = 20) -> None:
    for f in EXTRA_FIELDS:
        if not hasattr(vs, f):
            setattr(vs, f, None)
    vs.status_texts = deque(maxlen=max_texts)


def request_streams(master) -> None:
    for msg_id, hz in STREAMS.items():
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            msg_id, int(1e6 / hz), 0, 0, 0, 0, 0,
        )


def apply_extra(vs, msg) -> None:
    t = msg.get_type()

    if t == "ATTITUDE":
        vs.roll_deg = math.degrees(msg.roll)
        vs.pitch_deg = math.degrees(msg.pitch)
        vs.yaw_deg = math.degrees(msg.yaw) % 360
        vs.roll_rate_dps = math.degrees(msg.rollspeed)
        vs.pitch_rate_dps = math.degrees(msg.pitchspeed)
        vs.yaw_rate_dps = math.degrees(msg.yawspeed)

    elif t == "VFR_HUD":
        vs.airspeed_m_s = msg.airspeed
        vs.throttle_pct = msg.throttle

    elif t == "SYS_STATUS":
        vs.battery_current_a = msg.current_battery / 100.0 if msg.current_battery >= 0 else None
        vs.cpu_load_pct = msg.load / 10.0
        present = msg.onboard_control_sensors_present
        enabled = msg.onboard_control_sensors_enabled
        health = msg.onboard_control_sensors_health
        if present & PREARM_BIT:
            vs.prearm_ok = bool(health & PREARM_BIT)
        vs.sensors_unhealthy = [
            name for bit, name in SENSOR_NAMES.items()
            if (present & enabled & bit) and not (health & bit)
        ]

    elif t == "GPS_RAW_INT":
        vs.gps_hdop = msg.eph / 100.0 if msg.eph != 65535 else None

    elif t == "EKF_STATUS_REPORT":
        vs.ekf_flags = msg.flags
        vs.ekf_vel_var = msg.velocity_variance
        vs.ekf_pos_var = msg.pos_horiz_variance
        vs.ekf_compass_var = msg.compass_variance

    elif t == "VIBRATION":
        vs.vibe_x = msg.vibration_x
        vs.vibe_y = msg.vibration_y
        vs.vibe_z = msg.vibration_z
        vs.vibe_clipping = msg.clipping_0 + msg.clipping_1 + msg.clipping_2

    elif t == "STATUSTEXT":
        text = msg.text.decode(errors="ignore") if isinstance(msg.text, bytes) else msg.text
        text = text.rstrip("\x00").strip()
        if text:
            severity = SEVERITY.get(msg.severity, str(msg.severity))
            vs.status_texts.append({"time": time.time(), "severity": severity, "text": text})
            print(f"[FC {severity}] {text}")


def hook_extra_telemetry(master, vs) -> None:
    """Run apply_extra on every MAVLink message the client reads, without changing mavlink_client.py."""
    original_recv_msg = master.recv_msg

    def recv_msg_with_extra():
        msg = original_recv_msg()
        if msg is not None and msg.get_type() != "BAD_DATA":
            apply_extra(vs, msg)
        return msg

    master.recv_msg = recv_msg_with_extra

def _inject_app_telemetry(client: MAVLinkClient, fsm: FSMController, detector) -> None:
    """Send FSM/autonomy/detection state as NAMED_VALUE_FLOAT so the ground dashboard sees it."""
    client.send_named_float("fsm_state",  float(fsm.current_state.value))
    client.send_named_float("autonomy",   float(fsm.current_autonomy.value if fsm.current_autonomy else 0))
    client.send_named_float("tgt_det",    1.0 if detector.target_detected else 0.0)
    client.send_named_float("tgt_conf",   detector.target_confidence if detector.target_detected else 0.0)
    client.send_named_float("tgt_px_x",  detector.target_pixel_x if detector.target_detected else 0.0)
    client.send_named_float("tgt_bbox_h", detector.target_bbox_height if detector.target_detected else 0.0)


VEHICLE_FIELDS = [
    "connected", "last_heartbeat_time", "armed", "mode", "system_status",
    "altitude_relative_m", "altitude_absolute_m", "latitude", "longitude",
    "heading_deg", "groundspeed_m_s", "climb_rate_m_s",
    "battery_voltage_v", "battery_remaining_pct",
    "gps_fix_type", "satellites_visible", "gps_ok", "ekf_ok", "in_air",
] + EXTRA_FIELDS

STATUS_TEXTS_SENT = 10  # last N flight-controller messages included in every packet

def build_telemetry(vehicle_state, fsm, detector) -> dict:
    next_state = getattr(fsm, "next_state", None)
    texts = list(getattr(vehicle_state, "status_texts", []))[-STATUS_TEXTS_SENT:]
    return {
        "type": "telemetry",
        "timestamp": time.time(),
        "fsm": {
            "current_state": fsm.current_state.name,
            "next_state": next_state.name if next_state else None,
            "autonomy": fsm.current_autonomy.name if fsm.current_autonomy else None,
        },
        "vehicle": {f: getattr(vehicle_state, f, None) for f in VEHICLE_FIELDS},
        "attitude": {
            "roll_deg": getattr(vehicle_state, "roll_deg", None),
            "pitch_deg": getattr(vehicle_state, "pitch_deg", None),
            "yaw_deg": getattr(vehicle_state, "yaw_deg", None),
        },
        "status_texts": texts,
        "target": {
            "detected": detector.target_detected,
            "confidence": detector.target_confidence if detector.target_detected else 0.0,
        },
    }




def main() -> None:
    print("Starting drone autonomy system...")
    GROUND_E = ("192.168.1.11", 5005)
    GROUND_D = ("192.168.1.185", 5005)
    GROUND_K = ("192.168.1.30", 5005)
       # the Mac's IP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    # 1 - Set up MAVLink connection
    mavlink_client = MAVLinkClient()
    mavlink_client.wait_heartbeat()
    if mavlink_client.master.target_component == 0:
        mavlink_client.master.target_component = 1

    # Ask ArduPilot for attitude, vibration, EKF etc.
    request_streams(mavlink_client.master)

    # 2 - Shared live vehicle state
    vehicle_state = VehicleState()
    init_extra_state(vehicle_state)
    hook_extra_telemetry(mavlink_client.master, vehicle_state)
    
    # 3 - Command interface to autopilot
    commands = AutopilotCommands(mavlink_client.master)

    # 4 - FSM controller
    fsm = FSMController(commands)
    
    # 5 - Event generator
    event_generator = EventGenerator()

    # 6 - Target detector and tracker
    target_detector = TargetDetector()
    tracker = TargetTracker(target_detector, commands)

    # 7 - Logger
    logger = Logger()

    # 8 - Keyboard listener (terminal input)
    keyboard = KeyboardListener()
    print("Controls: [s] start search  [l] land  [r] reset from failsafe  [q] quit")

    print("System initialized...")

    while True:
        loop_start = time.time()

        # ----------------------------------
        # 1 - Read and apply all pending MAVLink messages
        # ----------------------------------
        processed_count = 0
        while mavlink_client.update_vehicle_state(vehicle_state):
            processed_count += 1

        # ----------------------------------
        # 2 - Update target detector + handle operator keypresses
        # ----------------------------------
        target_detector.update()
        target_detector.display()

        key = keyboard.get_key()
        if key == 'q':
            break
        elif key == 's' and fsm.current_state == State.HOVER:
            print("[INPUT] START_SEARCH")
            fsm.handle_event(Event.START_SEARCH)
        elif key == 'l':
            print("[INPUT] LAND")
            fsm.handle_event(Event.LAND)
        elif key == 'r' and fsm.current_state == State.FAILSAFE:
            print("[INPUT] RESET_ON_GND")
            fsm.handle_event(Event.RESET_ON_GND)

        # ----------------------------------
        # 3 - Generate one high-level event from current data
        # ----------------------------------
        event = event_generator.generate(vehicle_state, fsm, target_detector)

        if event is not None:
            print(f"[EVENT] {event}")
            fsm.handle_event(event)

        # ----------------------------------
        # 4 - Execute autonomy behaviour for current state
        # ----------------------------------
        if target_detector.target_detected and fsm.current_state == State.AUTONOMY and fsm.current_autonomy == Autonomy.TRACK:
            if vehicle_state.mode != "GUIDED":  
                commands.guided()
            else:
                if tracker.update():
                    print("[TRACK] Target reached!")
                    fsm.handle_event(Event.TASK_COMPLETED)
            print(f"[TRACK] target={target_detector.target_position} error={target_detector.target_pixel_x - target_detector.center_x:.0f}px conf={target_detector.target_confidence:.2f}")
            
        # ----------------------------------
        # 5 - Debug output
        # ----------------------------------
        def _fmt(v, spec=".1f"):
            return format(v, spec) if isinstance(v, (int, float)) else "n/a"

        print(
            f"[STATUS] \n"
            f"fsm = {fsm.current_state.name} \n"
            f"auto = {fsm.current_autonomy.name if fsm.current_autonomy else 'None'} \n"
            f"armed = {vehicle_state.armed} \n"
            f"mode = {vehicle_state.mode} \n"
            f"alt = {vehicle_state.altitude_relative_m:.1f} m \n"
            f"roll/pitch = {_fmt(vehicle_state.roll_deg)} / {_fmt(vehicle_state.pitch_deg)} deg \n"
            f"gps_ok = {vehicle_state.gps_ok} \n"
            f"battery = {vehicle_state.battery_remaining_pct} % \n"
            f"prearm_ok = {vehicle_state.prearm_ok} \n"
            f"target = {target_detector.target_position if target_detector.target_detected else 'None'} \n"
            f"msgs = {processed_count}"
        )

        # ----------------------------------
        # 5.5 - Send status to ground station (Mac) over UDP
        # ----------------------------------
        try:
            payload = json.dumps(build_telemetry(vehicle_state, fsm, target_detector), default=str)
            sock.sendto(payload.encode(), GROUND_D)
            sock.sendto(payload.encode(), GROUND_E)
            sock.sendto(payload.encode(), GROUND_K)
        except OSError as e:
            print(f"[UDP] send failed: {e}")    

        _inject_app_telemetry(mavlink_client, fsm, target_detector)
        logger.log_iteration(vehicle_state, fsm, target_detector)

        # ----------------------------------
        # 6 - Keep loop timing stable
        # ----------------------------------
        elapsed = time.time() - loop_start
        sleep_time = max(0.0, UPDATE_RATE - elapsed)
        time.sleep(sleep_time)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(f"Error: {e}")
        raise
