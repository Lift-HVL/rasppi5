"""Logger utility for handling logging functionality."""

import time
from pathlib import Path

from autonomy.target_detection import TargetDetector
from autopilot.vehicle_state import VehicleState
from config import LOG_DIR
from fsm.controller import FSMController


class Logger:
    """Write timestamped status lines for each loop iteration"""

    def __init__(self) -> None:
        self.log_dir = Path(LOG_DIR)
        self.log_dir.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.log_file = self.log_dir / f"log_{timestamp}.txt"

    def write(self, line: str) -> None:
        """Append a single timestamped line to the current log file."""

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(f"{timestamp} - {line}\n")

    def log_iteration(self, vehicle_state: VehicleState, fsm: FSMController, target_detector: TargetDetector) -> None:
        """
        Log the current state of the system in a human-readable format.
        
        TODO: 
            - Consider logging in a structured format (e.g. JSON) for easier parsing and analysis later.
            - Add more fields as needed (e.g. GPS coordinates, error messages, etc.)
        """
        line = (
            f"Battery: {vehicle_state.battery_remaining_pct}% | "
            f"Satellites: {vehicle_state.satellites_visible} | "
            f"Mode: {vehicle_state.mode} | "
            f"Armed: {vehicle_state.armed} | "
            f"Altitude: {vehicle_state.altitude_relative_m:.1f}m | "
            f"FSM State: {fsm.current_state.name} | "
            f"FSM Substate: {fsm.current_autonomy.name if fsm.current_autonomy else 'N/A'} | "
            f"Target Detected: {target_detector.target_detected} | "
            f"Target Position: {target_detector.target_position} | "
            f"Target Confidence: {target_detector.target_confidence:.2f}"
        )
        self.write(line)