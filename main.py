import time

from autonomy.target_detection import TargetDetector

from autopilot.mavlink_client import MAVLinkClient
from autopilot.vehicle_state import VehicleState
from autopilot.commands import AutopilotCommands

from fsm.controller import FSMController
from fsm.event_generator import EventGenerator
from fsm.states import State

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

    # 6 - Target detector
    target_detector = TargetDetector()

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
        # 2 - Update target detector
        # ----------------------------------
        target_detector.update()

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
        if fsm.current_state == State.AUTONOMY and target_detector.target_detected:
            if target_detector.target_detected:
                print(f"Target detected at {target_detector.target_position} with confidence {target_detector.target_confidence:.2f}")
                            

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
