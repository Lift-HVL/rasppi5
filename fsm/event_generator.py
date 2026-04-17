from fsm.event import Event
from fsm.states import State, Autonomy
from config import CRITICAL_BATTERY_THRESHOLD, LOW_BATTERY_THRESHOLD, TAKEOFF_ALTITUDE


class EventGenerator:
    def __init__(self):
        self._prev_armed = False
        self._prev_target_detected = False

    def generate(self, vehicle_state, fsm, target_detector=None):
        event = self._generate(vehicle_state, fsm, target_detector)

        # Update tracked state after generating the event
        self._prev_armed = vehicle_state.armed
        if target_detector is not None:
            self._prev_target_detected = target_detector.target_detected

        return event

    def _generate(self, vehicle_state, fsm, target_detector):
        # 1 - Connection loss
        if vehicle_state.heartbeat_timeout():
            return Event.FAULT

        # 2 - Init
        if fsm.current_state == State.BOOT and vehicle_state.connected:
            return Event.INIT_OK

        # 3 - Arm / Disarm transitions
        if vehicle_state.armed and not self._prev_armed:
            return Event.ARM
        if not vehicle_state.armed and self._prev_armed:
            return Event.DISARM

        # 4 - Takeoff complete
        if (
            fsm.current_state == State.TAKEOFF
            and vehicle_state.altitude_relative_m >= TAKEOFF_ALTITUDE
        ):
            return Event.ALTITUDE_REACHED

        # 5 - Landing complete
        if (
            fsm.current_state == State.LAND
            and vehicle_state.altitude_relative_m <= 0.1
        ):
            return Event.LANDED_DISARM

        # 6 - Battery
        if vehicle_state.battery_remaining_pct is not None:
            if vehicle_state.battery_remaining_pct <= CRITICAL_BATTERY_THRESHOLD:
                return Event.CRITICAL_FAULT
            elif vehicle_state.battery_remaining_pct <= LOW_BATTERY_THRESHOLD:
                return Event.RECOVERABLE_FAULT

        # 7 - Target detection (only while actively searching)
        if (
            fsm.current_state == State.AUTONOMY
            and fsm.current_autonomy == Autonomy.SEARCH
            and target_detector is not None
        ):
            if target_detector.target_detected and not self._prev_target_detected:
                return Event.START_TRACK
            if not target_detector.target_detected and self._prev_target_detected:
                return Event.TARGET_LOST

        return None
