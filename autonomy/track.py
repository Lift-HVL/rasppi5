from autopilot.commands import AutopilotCommands
from autonomy.target_detection import TargetDetector
from config import YAW_RATE_MAX, YAW_GAIN, YAW_DEADBAND, FORWARD_SPEED, BBOX_REACH_THRESHOLD

class TargetTracker:
    def __init__(self, detector: TargetDetector, commands: AutopilotCommands):
        self.detector = detector
        self.commands = commands

    def update(self) -> bool:
        """
        Two-phase tracking:
          1. Centering — yaw until the target is horizontally centered.
          2. Approach  — fly forward until the target's bounding box fills
                         BBOX_REACH_THRESHOLD of the frame height (proxy for distance).
        Returns True when the target is reached, or if no target is detected.
        Call after detector.update() has already been called this tick.
        """
        if not self.detector.target_detected:
            self.commands.set_yaw_rate(0)
            self.commands.set_forward_speed(0)
            return True

        pixel_error = self.detector.target_pixel_x - self.detector.center_x

        # Phase 1: center the target horizontally before advancing
        if abs(pixel_error) > YAW_DEADBAND:
            yaw_rate = max(-YAW_RATE_MAX, min(YAW_RATE_MAX, YAW_GAIN * pixel_error))
            self.commands.set_yaw_rate(yaw_rate)
            self.commands.set_forward_speed(0)
            return False

        # Target is centered — stop yaw and begin / continue approach
        self.commands.set_yaw_rate(0)

        frame_height = self.detector.center_y * 2  # center_y == height / 2
        bbox_fraction = (
            self.detector.target_bbox_height / frame_height if frame_height > 0 else 0
        )

        if bbox_fraction >= BBOX_REACH_THRESHOLD:
            self.commands.set_forward_speed(0)
            return True  # Within reach

        self.commands.set_forward_speed(FORWARD_SPEED)
        return False