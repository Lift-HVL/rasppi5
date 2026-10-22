"""main2.py - Pi side of the ground-station link (see README "Pi integration").

Connects to ArduPilot, then runs one non-blocking loop that:
  1. reads every MAVLink message (the only place recv_match is called)
  2. sends telemetry JSON to the backend over UDP (default 5 Hz)
  3. receives command JSON on the SAME socket, sends it to the flight controller,
     and replies {"type": "ack", "id": ..., "ok": ...} when COMMAND_ACK arrives
     (or ok=false after 2 s without one)

Commands: arm, disarm, takeoff, land, rtl, goto, motor_test, motor_test_stop

Usage (on the Pi):
    python3 main2.py --gs 192.168.1.11
    python3 main2.py --gs 192.168.1.11 --port 5005 --rate 5 --connect /dev/ttyAMA0

UDP only: the backend must run with INGEST_PROTOCOL=udp.
"""

import argparse
import json
import math
import socket
import sys
import time
from collections import deque

from pymavlink import mavutil

from autopilot.mavlink_client import MAVLinkClient
from config import CONNECTION_STRING

GROUND_STATION_IP = "192.168.1.11"   # backend address - override with --gs
GROUND_STATION_PORT = 5005
ACK_TIMEOUT_S = 2.0
STREAM_REFRESH_S = 30.0              # re-request streams in case the FC rebooted

M = mavutil.mavlink

# message name -> rate (Hz) requested with MAV_CMD_SET_MESSAGE_INTERVAL
STREAMS_HZ = {
    "ATTITUDE": 10,
    "GLOBAL_POSITION_INT": 5,
    "VFR_HUD": 5,
    "SYS_STATUS": 2,
    "GPS_RAW_INT": 2,
    "VIBRATION": 2,
    "EKF_STATUS_REPORT": 2,
    "SERVO_OUTPUT_RAW": 4,
    "ESC_TELEMETRY_1_TO_4": 4,
    "ESC_TELEMETRY_5_TO_8": 4,
}


def short_enum(enum: str, value: int, prefix: str) -> str:
    entry = M.enums.get(enum, {}).get(value)
    return entry.name.replace(prefix, "") if entry else str(value)


def clean(obj):
    """Replace NaN/inf with None so the packet is valid JSON."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def request_streams(master) -> None:
    for name, hz in STREAMS_HZ.items():
        msg_id = getattr(M, f"MAVLINK_MSG_ID_{name}", None)
        if msg_id is None:
            continue
        master.mav.command_long_send(
            master.target_system, master.target_component,
            M.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            msg_id, int(1e6 / hz), 0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Telemetry: keep the latest of each message and build the JSON packet
# ---------------------------------------------------------------------------

class Telemetry:
    def __init__(self, master):
        self.master = master
        self.last = {}                      # message type -> latest message
        self.last_heartbeat = 0.0
        self.status_texts = deque(maxlen=10)

    def on_mavlink(self, msg) -> None:
        t = msg.get_type()
        if t == "BAD_DATA" or msg.get_srcSystem() != self.master.target_system:
            return
        if t == "HEARTBEAT":
            if msg.type == M.MAV_TYPE_GCS:
                return
            self.last_heartbeat = time.time()
        elif t == "STATUSTEXT":
            sev = short_enum("MAV_SEVERITY", msg.severity, "MAV_SEVERITY_")
            self.status_texts.append({"time": time.time(), "severity": sev, "text": msg.text})
            print(f"  FC [{sev}]: {msg.text}")
        self.last[t] = msg

    @property
    def mode(self):
        hb = self.last.get("HEARTBEAT")
        return mavutil.mode_string_v10(hb) if hb else None

    @property
    def armed(self):
        hb = self.last.get("HEARTBEAT")
        return bool(hb.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED) if hb else None

    def _sensors(self, s):
        """(prearm_ok, sensors_unhealthy) from SYS_STATUS."""
        if s is None:
            return None, []
        prearm_bit = M.MAV_SYS_STATUS_PREARM_CHECK
        prearm_ok = bool(s.onboard_control_sensors_health & prearm_bit) \
            if s.onboard_control_sensors_enabled & prearm_bit else None
        bad = (s.onboard_control_sensors_present & s.onboard_control_sensors_enabled
               & ~s.onboard_control_sensors_health)
        names = [short_enum("MAV_SYS_STATUS_SENSOR", bit, "MAV_SYS_STATUS_SENSOR_").lower()
                 for bit in M.enums["MAV_SYS_STATUS_SENSOR"]
                 if bit & bad and bit != prearm_bit and bit.bit_count() == 1]
        return prearm_ok, names

    def _motors(self) -> dict:
        motors = {}
        servo = self.last.get("SERVO_OUTPUT_RAW")
        if servo:
            pwm = [getattr(servo, f"servo{i}_raw", 0) for i in range(1, 9)]
            while pwm and pwm[-1] == 0:
                pwm.pop()
            motors["servo_output_raw"] = pwm
        esc = []
        for name in ("ESC_TELEMETRY_1_TO_4", "ESC_TELEMETRY_5_TO_8"):
            m = self.last.get(name)
            if m:
                esc += [{"rpm": m.rpm[i], "temperature_c": m.temperature[i],
                         "voltage_v": m.voltage[i] / 100, "current_a": m.current[i] / 100}
                        for i in range(4)]
        if esc:
            motors["esc"] = esc
        return motors

    def build(self) -> dict:
        g = self.last.get
        hb, pos, hud, sys_s = g("HEARTBEAT"), g("GLOBAL_POSITION_INT"), g("VFR_HUD"), g("SYS_STATUS")
        gps, att, vib, ekf = g("GPS_RAW_INT"), g("ATTITUDE"), g("VIBRATION"), g("EKF_STATUS_REPORT")

        prearm_ok, unhealthy = self._sensors(sys_s)
        alt_rel = pos.relative_alt / 1000 if pos else None
        roll = math.degrees(att.roll) if att else None
        pitch = math.degrees(att.pitch) if att else None
        yaw = math.degrees(att.yaw) % 360 if att else None
        ekf_need = M.EKF_ATTITUDE | M.EKF_VELOCITY_HORIZ | M.EKF_POS_HORIZ_ABS

        vehicle = {
            "connected": time.time() - self.last_heartbeat < 3.0,
            "last_heartbeat_time": self.last_heartbeat or None,
            "armed": self.armed,
            "mode": self.mode,
            "system_status": short_enum("MAV_STATE", hb.system_status, "MAV_STATE_") if hb else None,
            "altitude_relative_m": alt_rel,
            "altitude_absolute_m": pos.alt / 1000 if pos else None,
            "latitude": pos.lat / 1e7 if pos else None,
            "longitude": pos.lon / 1e7 if pos else None,
            "heading_deg": hud.heading if hud else None,
            "groundspeed_m_s": hud.groundspeed if hud else None,
            "climb_rate_m_s": hud.climb if hud else None,
            "throttle_pct": hud.throttle if hud else None,
            "battery_voltage_v": sys_s.voltage_battery / 1000 if sys_s else None,
            "battery_remaining_pct": sys_s.battery_remaining if sys_s and sys_s.battery_remaining >= 0 else None,
            "battery_current_a": sys_s.current_battery / 100 if sys_s and sys_s.current_battery >= 0 else None,
            "gps_fix_type": gps.fix_type if gps else None,
            "satellites_visible": gps.satellites_visible if gps and gps.satellites_visible != 255 else None,
            "gps_ok": gps.fix_type >= 3 if gps else False,
            "ekf_ok": (ekf.flags & ekf_need) == ekf_need if ekf else False,
            "in_air": bool(self.armed and alt_rel is not None and alt_rel > 0.3),
            "prearm_ok": prearm_ok,
            "sensors_unhealthy": unhealthy,
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
            "vibe_x": vib.vibration_x if vib else None,
            "vibe_y": vib.vibration_y if vib else None,
            "vibe_z": vib.vibration_z if vib else None,
            "vibe_clipping": vib.clipping_0 + vib.clipping_1 + vib.clipping_2 if vib else None,
        }
        packet = {
            "type": "telemetry",
            "timestamp": time.time(),
            "vehicle": vehicle,
            "status_texts": list(self.status_texts),
        }
        if att:
            packet["attitude"] = {"roll_deg": roll, "pitch_deg": pitch, "yaw_deg": yaw}
        motors = self._motors()
        if motors:
            packet["motors"] = motors
        return packet


# ---------------------------------------------------------------------------
# Commands: backend JSON -> MAVLink, COMMAND_ACK -> ack JSON
# ---------------------------------------------------------------------------

class CommandError(Exception):
    pass


class CommandHandler:
    def __init__(self, master, sock: socket.socket, telem: Telemetry):
        self.master = master
        self.sock = sock
        self.telem = telem
        self.pending = {}   # MAVLink command number -> (id, addr, deadline, name)

    # --- replies ---------------------------------------------------------
    def reply(self, addr, cmd_id: str, ok: bool, error: str | None = None) -> None:
        msg = {"type": "ack", "id": cmd_id, "ok": ok}
        if error:
            msg["error"] = error
        print(f"[CMD] ack id={cmd_id} ok={ok}" + (f" ({error})" if error else ""))
        try:
            self.sock.sendto(json.dumps(msg).encode(), addr)
        except OSError as e:
            print(f"[CMD] could not send ack: {e}")

    # --- incoming --------------------------------------------------------
    def handle(self, data: bytes, addr) -> None:
        try:
            obj = json.loads(data)
        except ValueError:
            print(f"[CMD] ignored non-JSON packet from {addr[0]}")
            return
        if not isinstance(obj, dict) or obj.get("type") != "command":
            return

        cmd_id = str(obj.get("id", ""))
        name = obj.get("command")
        print(f"[CMD] {addr[0]} id={cmd_id}: {name} {obj}")
        try:
            wait_for = self._dispatch(name, obj)
        except CommandError as e:
            self.reply(addr, cmd_id, False, str(e))
            return

        if wait_for is None:                       # goto: no COMMAND_ACK from the FC
            self.reply(addr, cmd_id, True)
            return
        old = self.pending.pop(wait_for, None)
        if old:
            self.reply(old[1], old[0], False, "Superseded by a newer command of the same kind")
        self.pending[wait_for] = (cmd_id, addr, time.time() + ACK_TIMEOUT_S, name)

    def on_ack(self, msg) -> None:
        if msg.get_srcSystem() != self.master.target_system:
            return
        if getattr(msg, "target_system", 0) not in (0, self.master.mav.srcSystem):
            return                                  # ack meant for another GCS
        if msg.result == M.MAV_RESULT_IN_PROGRESS:
            return
        entry = self.pending.pop(msg.command, None)
        if entry is None:
            return
        cmd_id, addr, _, _ = entry
        if msg.result == M.MAV_RESULT_ACCEPTED:
            self.reply(addr, cmd_id, True)
        else:
            result = short_enum("MAV_RESULT", msg.result, "")
            self.reply(addr, cmd_id, False, f"Flight controller replied {result}")

    def check_timeouts(self) -> None:
        now = time.time()
        for mav_cmd, (cmd_id, addr, deadline, name) in list(self.pending.items()):
            if now > deadline:
                del self.pending[mav_cmd]
                self.reply(addr, cmd_id, False,
                           f"No answer from the flight controller to '{name}' within {ACK_TIMEOUT_S:.0f} s")

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _num(obj: dict, key: str) -> float:
        if key not in obj or obj[key] is None:
            raise CommandError(f"Missing field '{key}'")
        try:
            return float(obj[key])
        except (TypeError, ValueError):
            raise CommandError(f"Field '{key}' must be a number")

    def _long(self, command: int, *params: float) -> int:
        p = list(params) + [0] * (7 - len(params))
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component, command, 0, *p)
        return command

    def _mode_id(self, mode: str) -> int:
        mode_id = (self.master.mode_mapping() or {}).get(mode)
        if mode_id is None:
            raise CommandError(f"Flight controller has no {mode} mode")
        return mode_id

    def _ensure_guided(self) -> None:
        """Takeoff and goto only work in GUIDED; switch first if needed."""
        if self.telem.mode != "GUIDED":
            self.master.set_mode(self._mode_id("GUIDED"))

    def _set_mode(self, mode: str) -> int:
        return self._long(M.MAV_CMD_DO_SET_MODE,
                          M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, self._mode_id(mode))

    # --- the commands ----------------------------------------------------
    def _dispatch(self, name, obj: dict) -> int | None:
        """Send the command. Returns the MAVLink command to wait for, or None if no ACK is expected."""
        if name == "arm":
            return self._long(M.MAV_CMD_COMPONENT_ARM_DISARM, 1)

        if name == "disarm":
            return self._long(M.MAV_CMD_COMPONENT_ARM_DISARM, 0)

        if name == "takeoff":
            alt = self._num(obj, "altitude")
            self._ensure_guided()
            return self._long(M.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, alt)

        if name == "land":
            return self._set_mode("LAND")

        if name == "rtl":
            return self._set_mode("RTL")

        if name == "goto":
            lat, lon = self._num(obj, "latitude"), self._num(obj, "longitude")
            alt = self._num(obj, "altitude")
            self._ensure_guided()
            position_only = 0b0000111111111000
            self.master.mav.set_position_target_global_int_send(
                0, self.master.target_system, self.master.target_component,
                M.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, position_only,
                int(lat * 1e7), int(lon * 1e7), alt,
                0, 0, 0, 0, 0, 0, 0, 0)
            return None

        if name == "motor_test":
            motor = self._num(obj, "motor")
            ttype = obj.get("throttle_type")
            if ttype == "percent":
                ttype_val = M.MOTOR_TEST_THROTTLE_PERCENT
            elif ttype == "pwm":
                ttype_val = M.MOTOR_TEST_THROTTLE_PWM
            else:
                raise CommandError("Field 'throttle_type' must be 'percent' or 'pwm'")
            return self._long(M.MAV_CMD_DO_MOTOR_TEST, motor, ttype_val,
                              self._num(obj, "throttle"), self._num(obj, "timeout"),
                              self._num(obj, "count"), M.MOTOR_TEST_ORDER_SEQUENCE)

        if name == "motor_test_stop":
            return self._long(M.MAV_CMD_DO_MOTOR_TEST, 1, M.MOTOR_TEST_THROTTLE_PERCENT,
                              0, 0, 0, M.MOTOR_TEST_ORDER_SEQUENCE)

        raise CommandError(f"Unknown command '{name}'")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(master, gs_addr, rate_hz: float) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))       # one socket: send telemetry AND receive commands
    sock.setblocking(False)

    telem = Telemetry(master)
    cmds = CommandHandler(master, sock, telem)

    period = 1.0 / rate_hz
    next_send = 0.0
    next_streams = 0.0
    last_send_error = None
    print(f"Sending telemetry to {gs_addr[0]}:{gs_addr[1]} at {rate_hz:g} Hz, "
          f"listening for commands on UDP port {sock.getsockname()[1]}")

    while True:
        now = time.time()
        if now >= next_streams:
            request_streams(master)
            next_streams = now + STREAM_REFRESH_S

        # 1 - every MAVLink message goes through here
        for _ in range(500):
            msg = master.recv_match(blocking=False)
            if msg is None:
                break
            telem.on_mavlink(msg)
            if msg.get_type() == "COMMAND_ACK":
                cmds.on_ack(msg)

        # 2 - commands from the backend
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError:          # e.g. ICMP "port unreachable" while the backend is down
                break
            cmds.handle(data, addr)
        cmds.check_timeouts()

        # 3 - telemetry
        if now >= next_send:
            next_send = now + period
            try:
                payload = json.dumps(clean(telem.build()), allow_nan=False)
                sock.sendto(payload.encode(), gs_addr)
                last_send_error = None
            except OSError as e:
                if str(e) != last_send_error:     # don't spam the same error
                    print(f"[UDP] send failed: {e}")
                    last_send_error = str(e)

        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pi <-> ground station link (telemetry + commands over UDP).")
    parser.add_argument("--connect", default=CONNECTION_STRING, help="MAVLink connection string")
    parser.add_argument("--gs", default=GROUND_STATION_IP, help="ground station (backend) IP")
    parser.add_argument("--port", type=int, default=GROUND_STATION_PORT, help="backend UDP port")
    parser.add_argument("--rate", type=float, default=5.0, help="telemetry rate in Hz (2-10)")
    args = parser.parse_args()

    print(f"Connecting to {args.connect}...")
    client = MAVLinkClient(args.connect)
    if not client.wait_heartbeat():
        print("FAILED: no heartbeat - check wiring, CONNECTION_STRING and baud rate")
        return 1

    master = client.master
    if master.target_component == 0:
        master.target_component = 1
    print(f"Connected: system {master.target_system}, component {master.target_component}")

    try:
        run(master, (args.gs, args.port), args.rate)
    except KeyboardInterrupt:
        print("Shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())