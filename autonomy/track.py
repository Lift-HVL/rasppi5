from __future__ import annotations

from typing import TYPE_CHECKING

from autopilot.commands import AutopilotCommands
from config import YAW_RATE_MAX, YAW_KP, YAW_DEADBAND, FORWARD_SPEED, BBOX_REACH_THRESHOLD, YAW_INTEGRAL_MAX, YAW_KI
import time

if TYPE_CHECKING:   # only for hints - importing it would load ultralytics and open the camera
    from autonomy.target_detection import TargetDetector

class TargetTracker:
    def __init__(self, detector: TargetDetector, commands: AutopilotCommands, follow: bool = False):
        self.detector = detector
        self.commands = commands
        self.follow = follow        # True: keep following a person, never report "reached"
        self.integral = 0.0         # Integral term for PI control
        self.last_time = None       # To track time between updates for integral calculation

    def stop(self) -> None:
        """Stop turning and moving (target lost, following switched off) and reset the regulator."""
        self.commands.set_yaw_rate(0)
        self.commands.set_forward_speed(0)
        self.integral = 0.0
        self.last_time = None

    def update(self) -> bool:
        """
        Two-phase tracking:
          1. Centering — yaw until the target is horizontally centered.
          2. Approach  — fly forward until the target's bounding box fills
                         BBOX_REACH_THRESHOLD of the frame height (proxy for distance).
        Returns True when the target is reached, or if no target is detected.
        In follow mode "reached" only stops the forward motion; the tracker keeps running so the
        drone moves again as soon as the person walks away. It then returns True only when the
        target is gone.
        Call after detector.update() has already been called this tick.
        """
        if not self.detector.target_detected:
            self.stop()                             # also resets integral and timing
            return True

        pixel_error = self.detector.target_pixel_x - self.detector.center_x

        dt = time.time() - self.last_time if self.last_time is not None else 0  # Time since last update
        self.integral += pixel_error * dt                                            # Accumulate integral term
        self.integral = max(-YAW_INTEGRAL_MAX, min(YAW_INTEGRAL_MAX, self.integral))      # Prevent integral windup (overshoot)
        self.last_time = time.time()                                            # Update last_time for next iteration
        
        # Phase 1: center the target horizontally before advancing
        if abs(pixel_error) > YAW_DEADBAND:
            yaw_rate = max(-YAW_RATE_MAX, min(YAW_RATE_MAX, YAW_KP * pixel_error + YAW_KI * self.integral))
            self.commands.set_yaw_rate(yaw_rate)
            self.commands.set_forward_speed(0)
            return False
            
        # Target is centered — stop yaw and begin / continue approach
        self.commands.set_yaw_rate(0)
        self.integral = 0.0  # Reset integral once centered to prevent overshoot on approach

        frame_height = self.detector.center_y * 2  # center_y == height / 2
        bbox_fraction = (
            self.detector.target_bbox_height / frame_height if frame_height > 0 else 0
        )

        if bbox_fraction >= BBOX_REACH_THRESHOLD:
            self.commands.set_forward_speed(0)
            return not self.follow  # Within reach (follow mode: keep tracking)

        self.commands.set_forward_speed(FORWARD_SPEED)
        return False