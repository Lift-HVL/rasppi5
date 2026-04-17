from logging import Logger
import sys
import os
import time

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

def main() -> None:
    print("Starting drone autonomy system...")

    # 1 - Set up MAVLink connection
    mavlink_client = MAVLinkClient()
    mavlink_client.wait_heartbeat()

    # 2 - Shared live vehicle state
    vehicle_state = VehicleState()

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
        key = target_detector.display()

        if key == ord('q'):
            break
        elif key == ord('s') and fsm.current_state == State.HOVER:
            print("[INPUT] START_SEARCH")
            fsm.handle_event(Event.START_SEARCH)
        elif key == ord('l'):
            print("[INPUT] LAND")
            fsm.handle_event(Event.LAND)

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
                tracker.update()
            print(f"[TRACK] target={target_detector.target_position} error={target_detector.target_pixel_x - target_detector.center_x:.0f}px conf={target_detector.target_confidence:.2f}")
            
        # ----------------------------------
        # 5 - Debug output
        # ----------------------------------
        print(
            f"[STATUS] \n"
            f"fsm = {fsm.current_state.name} \n"
            f"auto = {fsm.current_autonomy.name if fsm.current_autonomy else 'None'} \n"
            f"armed = {vehicle_state.armed} \n"
            f"mode = {vehicle_state.mode} \n"
            f"alt = {vehicle_state.altitude_relative_m:.1f} m \n"
            f"gps_ok = {vehicle_state.gps_ok} \n"
            f"battery = {vehicle_state.battery_remaining_pct} % \n"
            f"target = {target_detector.target_position if target_detector.target_detected else 'None'} \n"
            f"msgs = {processed_count}"
        )

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
