"""
Purpose: decouple the camera source from TargetDetector, so the detector code can be reused if we switch to a different camera or image source in the future. 
The camera module is responsible for interfacing with OpenCV and providing frames to the detector, as well as displaying annotated frames and handling keypresses.
"""

import cv2
from numpy import ndarray as frame

class Camera:
    def __init__(self, source): 
        self.cap = cv2.VideoCapture(source) # Capture video from the specified source
        
    def read(self) -> tuple[bool, frame]:
        return self.cap.read() # Read a frame from the camera
    
    @property
    def width(self) -> int:
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) # Get the width of the video frames
    
    @property
    def height(self) -> int:
        return int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) # Get the height of the video frames
    
    @property
    def is_open(self) -> bool:
        return self.cap.isOpened() # Check if the video capture is successfully opened
    
    def release(self) -> None:
        self.cap.release() # Release the video capture object