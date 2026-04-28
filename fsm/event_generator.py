from fsm.event import Event
from fsm.states import State, Autonomy
from config import CRITICAL_BATTERY_THRESHOLD, LOW_BATTERY_THRESHOLD, TAKEOFF_ALTITUDE
from sensors.health_monitor import HealthMonitor

class EventGenerator:
    def __init__(self):
        self._prev_armed = False
        self._prev_target_detected = False
        self.health_monitor = HealthMonitor()  # Initialize health monitor

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

        # 4 - Takeoff initiated (altitude rising while armed — catches MissionPlanner / GCS commands)
        if (
            fsm.current_state == State.ARMED
            and vehicle_state.altitude_relative_m > 0.3
        ):
            return Event.TAKEOFF_CMD

        # 5 - Takeoff complete (reached target altitude OR stabilized at any meaningful altitude)
        if fsm.current_state == State.TAKEOFF and (
            vehicle_state.altitude_relative_m >= TAKEOFF_ALTITUDE
            or (vehicle_state.altitude_relative_m > 1.5 and abs(vehicle_state.climb_rate_m_s) < 0.2)
        ):
            return Event.ALTITUDE_REACHED

        # 5 - Landing complete
        if (
            fsm.current_state == State.LAND
            and vehicle_state.altitude_relative_m <= 0.1
        ):
            return Event.LANDED_DISARM

        # 6 - Battery (guard against -1 from simulators with no battery monitor)
        if vehicle_state.battery_remaining_pct is not None and vehicle_state.battery_remaining_pct >= 0:
            if vehicle_state.battery_remaining_pct <= CRITICAL_BATTERY_THRESHOLD:
                return Event.CRITICAL_FAULT
            elif vehicle_state.battery_remaining_pct <= LOW_BATTERY_THRESHOLD:
                return Event.RECOVERABLE_FAULT

        # 6.5 - RTL mode detected from autopilot (e.g. triggered by MissionPlanner)
        if (
            vehicle_state.mode in ("RTL", "SMART_RTL", "AUTO_RTL")
            and fsm.current_state in (State.HOVER, State.AUTONOMY, State.MANUAL)
        ):
            return Event.RTL_CMD

        # 6.6 - GPS and EKF health check
        health_event = self.health_monitor.check(vehicle_state)
        if health_event is not None:
            return health_event

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

        # 8 - Target lost while tracking
        if (
            fsm.current_state == State.AUTONOMY
            and fsm.current_autonomy == Autonomy.TRACK
            and target_detector is not None
        ):
            if not target_detector.target_detected and self._prev_target_detected:
                return Event.TARGET_LOST

        return None
