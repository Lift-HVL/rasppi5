"""
Purpose: Check GPS and EKF (Extended Kalman Filter) used for state estimation.
If GPS signal is lost, or EKF is diverging, trigger an alert and switch to a safe mode (e.g., hover in place or return to home) until the issue is resolved.
This module can run in parallel with the main autonomy loop and continuously monitor the health of the navigation system.
"""

from typing import Optional
from fsm.event import Event

from config import MIN_SATELLITES

class HealthMonitor:
    def check (self, vehicle_state) -> Optional[Event]:
        # Check GPS signal strength
        if vehicle_state.gps_signal_strength is not None and vehicle_state.gps_signal_strength < 3:
            return Event.FAULT
        
        # Check EKF status
        if not vehicle_state.ekf_ok:
            return Event.FAULT
        
        # Check satellite count
        if vehicle_state.satellites_visible < MIN_SATELLITES:
            return Event.FAULT