from autopilot.commands import AutopilotCommands
from autonomy.target_detection import TargetDetector
from config import YAW_RATE_MAX, YAW_GAIN, YAW_DEADBAND

class TargetTracker:
    def __init__(self, detector: TargetDetector, commands: AutopilotCommands):
        self.detector = detector
        self.commands = commands
        
    def update(self) -> bool:
        """
        Rotate to center the detected target horizontally.
        Returns True when centered (or target lost).
        """
        self.detector.update() # Update target detection
        
        if not self.detector.target_detected:
            self.commands.set_yaw_rate(0) # Stop rotation if no target
            return True
        
        pixel_error = self.detector.target_pixel_x - self.detector.center_x
        
        if abs(pixel_error) < YAW_DEADBAND:
            self.commands.set_yaw_rate(0) # Target is centered, stop rotation
            return True
        
        yaw_rate = max(-YAW_RATE_MAX, min(YAW_RATE_MAX, YAW_GAIN * pixel_error)) # Proportional control
        self.commands.set_yaw_rate(yaw_rate)
        return False