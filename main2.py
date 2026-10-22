"""Minimal connection test: connect to ArduPilot, send one simple command, confirm it worked.

Usage:
    python main2.py                      # switch to GUIDED mode (props do NOT spin)
    python main2.py --mode LOITER        # switch to another flight mode
    python main2.py --arm                # arm, wait a few seconds, disarm (PROPS WILL SPIN - remove them!)
    python main2.py --flight             # GUIDED -> arm -> take off to 2 m -> hover 5 s -> LAND (IT WILL FLY!)
    python main2.py --flight --alt 3 --hover-time 10
    python main2.py --connect /dev/ttyAMA0   # override CONNECTION_STRING from config.py
"""

import argparse
import sys
import time

from pymavlink import mavutil

from autopilot.mavlink_client import MAVLinkClient
from autopilot.commands import AutopilotCommands
from config import CONNECTION_STRING


def wait_for_mode(master, mode_name: str, timeout: float = 5.0) -> bool:
    """Watch incoming heartbeats until the autopilot reports the requested mode."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1.0)
        if msg is None or msg.get_srcSystem() != master.target_system:
            continue
        current = mavutil.mode_string_v10(msg)
        print(f"  autopilot mode: {current}")
        if current == mode_name:
            return True
    return False


def wait_for_ack(master, command: int, timeout: float = 5.0) -> bool:
    """Wait for COMMAND_ACK, printing any STATUSTEXT (pre-arm reasons etc.) meanwhile."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type=['COMMAND_ACK', 'STATUSTEXT'], blocking=True, timeout=1.0)
        if msg is None:
            continue
        if msg.get_type() == 'STATUSTEXT':
            print(f"  FC: {msg.text}")
            continue
        if msg.command != command:
            continue
        result = mavutil.mavlink.enums['MAV_RESULT'][msg.result].name
        print(f"  COMMAND_ACK: {result}")
        if msg.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            # Reasons often arrive just after the ACK - keep listening briefly
            end = time.time() + 2.0
            while time.time() < end:
                st = master.recv_match(type='STATUSTEXT', blocking=True, timeout=0.5)
                if st:
                    print(f"  FC: {st.text}")
            return False
        return True
    print("  no COMMAND_ACK received")
    return False


def request_position_stream(master, rate_hz: float = 5.0) -> None:
    """Ask ArduPilot to send GLOBAL_POSITION_INT so we can watch the altitude."""
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
        int(1e6 / rate_hz),  # interval in microseconds
        0, 0, 0, 0, 0
    )


def wait_for_altitude(master, target_m: float, timeout: float = 30.0) -> bool:
    """Wait until the relative altitude reaches 95% of the target."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1.0)
        if msg is None:
            continue
        alt = msg.relative_alt / 1000.0
        print(f"  altitude: {alt:.1f} m")
        if alt >= target_m * 0.95:
            return True
    return False


def wait_for_disarm(master, timeout: float = 60.0) -> bool:
    """Wait until the heartbeat reports the vehicle disarmed (ArduPilot auto-disarms after landing)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = master.recv_match(type=['HEARTBEAT', 'GLOBAL_POSITION_INT'], blocking=True, timeout=1.0)
        if msg is None:
            continue
        if msg.get_type() == 'GLOBAL_POSITION_INT':
            print(f"  altitude: {msg.relative_alt / 1000.0:.1f} m")
        elif msg.get_srcSystem() == master.target_system:
            if not msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                return True
    return False


def fly_test(master, commands: AutopilotCommands, altitude: float, hover_time: float) -> bool:
    """GUIDED -> arm -> takeoff -> hover -> LAND -> wait for disarm."""
    request_position_stream(master)

    commands.guided()
    if not wait_for_mode(master, "GUIDED"):
        print("FAILED: could not switch to GUIDED")
        return False

    commands.arm()
    if not wait_for_ack(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM):
        print("FAILED: arming rejected (check pre-arm messages in your ground station)")
        return False

    # Send takeoff right away: ArduPilot disarms again if it sits armed on the ground too long
    try:
        commands.takeoff(altitude)
        if not wait_for_ack(master, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF):
            print("FAILED: takeoff rejected - disarming")
            commands.disarm()
            return False

        if not wait_for_altitude(master, altitude):
            print("WARNING: target altitude not reached in time - landing anyway")
        else:
            print(f"Reached {altitude} m - hovering for {hover_time:.0f} s")
            time.sleep(hover_time)
    finally:
        # Always try to land, also on Ctrl+C or an unexpected error in the air
        commands.land()

    if not wait_for_disarm(master):
        print("WARNING: vehicle did not report disarmed - check it in your ground station")
        return False
    print("Landed and disarmed")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect to ArduPilot and send a simple command.")
    parser.add_argument("--connect", default=CONNECTION_STRING, help="MAVLink connection string")
    parser.add_argument("--mode", default="GUIDED", help="flight mode to switch to (default: GUIDED)")
    parser.add_argument("--arm", action="store_true", help="arm, wait, then disarm instead of changing mode")
    parser.add_argument("--arm-time", type=float, default=3.0, help="seconds to stay armed with --arm")
    parser.add_argument("--flight", action="store_true", help="arm, take off, hover, land")
    parser.add_argument("--alt", type=float, default=2.0, help="takeoff altitude in metres with --flight")
    parser.add_argument("--hover-time", type=float, default=5.0, help="seconds to hover with --flight")
    args = parser.parse_args()

    # 1 - Connect and wait for the autopilot's heartbeat
    print(f"Connecting to {args.connect}...")
    client = MAVLinkClient(args.connect)
    if not client.wait_heartbeat():
        print("FAILED: no heartbeat - check wiring, CONNECTION_STRING and baud rate")
        return 1

    master = client.master
    print(f"Connected: system {master.target_system}, component {master.target_component}")
    if master.target_component == 0:
        master.target_component = 1
    commands = AutopilotCommands(master)

    # 2 - Send the command and check that ArduPilot accepted it
    if args.flight:
        answer = input(f"Vehicle will ARM and FLY to {args.alt} m. Area clear? Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            print("Aborted")
            return 1
        if not fly_test(master, commands, args.alt, args.hover_time):
            return 1
    elif args.arm:
        commands.arm()
        if not wait_for_ack(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM):
            print("FAILED: arming rejected (check pre-arm messages in your ground station)")
            return 1
        print(f"Armed - disarming in {args.arm_time:.0f} s")
        time.sleep(args.arm_time)
        commands.disarm()
        wait_for_ack(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
    else:
        commands.set_mode(args.mode)
        if not wait_for_mode(master, args.mode):
            print(f"FAILED: autopilot did not switch to {args.mode}")
            return 1

    print("SUCCESS")
    return 0


if __name__ == '__main__':
    sys.exit(main())