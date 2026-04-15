"""Target detection functionality for the autonomous drone."""

import cv2
from ultralytics import YOLO
from config import YOLO_MODEL_PATH


class TargetDetector:
    def __init__(self):
        self.model = YOLO(YOLO_MODEL_PATH) # Load the YOLO model for target detection
        self.cap = cv2.VideoCapture(0) # Capture video from the default camera
        
        self.target_detected = False # Flag to indicate if a target is currently detected
        self.target_confidence = 0.0 # Confidence score of the detected target
        self.target_position = () # Position of the detected target in the frame ("left" / "right" / "center")

    
    def update(self):
        ret, frame = self.cap.read() # Read a frame from the camera
        if not ret:
            return
        
        height, width = frame.shape[:2]
        center_x = width / 2
        center_y = height / 2
        
        print(center_x, center_y)
        
        results = self.model(frame) # Run the YOLO model on the frame
        
        self.target_detected = False # Reset target detected flag each update
        
        for result in results:
            boxes = result.boxes # Get detected bounding boxes
            
            for box in boxes:
                conf = box.conf[0].item() # Get confidence score (0 - 1)
                cls = int(box.cls[0].item()) # Get class ID of the detected object
                name = result.names[cls] # Get class name from the model's names list
                
                if conf > 0.8: # Only consider detections with confidence > 80% / filter weak detections
                    self.target_detected = True
                    x1, y1, x2, y2 = box.xyxy[0].tolist() # Get bounding box coordinates
                    self.target_position = box.xywh[0][:2].tolist() # Get bounding box center coordinates
                    
                    self.target_confidence = conf
                    
                    if self.target_position[0] < frame.shape[1] / 3: # Target is on the left side of the frame
                        self.target_position = "left"
                    elif self.target_position[0] > 2 * frame.shape[1] / 3: # Target is on the right side of the frame
                        self.target_position = "right"
                    else: # Target is in the center of the frame
                        self.target_position = "center"
                    
                    break # Only consider the first valid detection for now
    
    def release(self):
        self.cap.release() # Release the video capture object
        cv2.destroyAllWindows() # Close all OpenCV windows