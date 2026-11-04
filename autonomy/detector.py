"""Pick the target source for the autonomy loop from config.DETECTOR_SOURCE."""

from config import DETECTOR_SOURCE


def create_detector():
    if DETECTOR_SOURCE == "local":
        from autonomy.target_detection import TargetDetector     # imports ultralytics, opens the camera
        return TargetDetector()
    from autonomy.remote_target import RemoteTargetDetector
    return RemoteTargetDetector()
