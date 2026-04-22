"""Search functionality for the autonomous drone."""
from autonomy.target_detection import TargetDetector
from autopilot.commands import AutopilotCommands


class Search:

    SEARCH_SPEED = 5.0      # m/s forward speed
    LANE_WIDTH = 20.0       # meters between passes
    AREA_SIZE = 100.0       # meters in each direction
    MOVE_RATE = 10.0        # Hz for velocity commands

    def __init__(self, detector: TargetDetector, commands: AutopilotCommands):
        self.detector = detector
        self.commands = commands

    def _move_until_target_or_done(
        self,
        north: float,
        east: float,
        distance: float,
    ) -> bool:
        """
        Move in a direction for a given distance (at SEARCH_SPEED).
        Returns True if a target was detected mid-move, False otherwise.
        """
        duration = distance / self.SEARCH_SPEED
        period = 1.0 / self.MOVE_RATE
        elapsed = 0.0

        while elapsed < duration:
            if self.detector.target_detected:
                self.commands.loiter()
                return True
            self.commands.move_velocity(north, east, 0.0)
            import time; time.sleep(period)
            elapsed += period

        return False

    def run(self) -> bool:
        """
        Lawnmower search pattern covering 100 m in each direction.
        Returns True if a target was found, False if area exhausted.
        
        Pattern (top-down view, starting at origin):
        
        Start --> [100m East] --> [step North] --> [100m West] --> [step North] --> ...
        """
        import time

        num_lanes = int(self.AREA_SIZE / self.LANE_WIDTH)  # 5 lanes
        heading = 1  # 1 = eastward, -1 = westward

        for lane in range(num_lanes):
            # --- sweep across 100 m ---
            target_found = self._move_until_target_or_done(
                north=0.0,
                east=self.SEARCH_SPEED * heading,
                distance=self.AREA_SIZE,
            )
            if target_found:
                return True

            # --- step one lane north (skip on last lane) ---
            if lane < num_lanes - 1:
                target_found = self._move_until_target_or_done(
                    north=self.SEARCH_SPEED,
                    east=0.0,
                    distance=self.LANE_WIDTH,
                )
                if target_found:
                    return True

            heading *= -1  # reverse direction for next sweep

        # Area fully searched, no target found
        self.commands.loiter()
        return False