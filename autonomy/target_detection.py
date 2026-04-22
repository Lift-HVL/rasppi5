"""Target detection functionality for the autonomous drone."""

import cv2
from ultralytics import YOLO
from config import YOLO_MODEL_PATH, CAMERA_INDEX
from sensors.camera import Camera

class TargetDetector:
    def __init__(self):
        self.model = YOLO(YOLO_MODEL_PATH) # Load the YOLO model for target detection
        self.cap = Camera(CAMERA_INDEX) # Capture video from the default camera
        self.center_x = 0 # X coordinate of the center of the frame
        self.center_y = 0 # Y coordinate of the center of the frame
        
        self.target_detected = False # Flag to indicate if a target is currently detected
        self.target_confidence = 0.0 # Confidence score of the detected target
        self.target_position = () # Position of the detected target in the frame ("left" / "right" / "center")
        self.target_pixel_x = 0.0 # Actual pixel X coordinate of the detected target's center
        self.target_bbox_height = 0.0 # Bounding box height in pixels (proxy for distance)
        self._last_frame = None # Most recent annotated frame for display

    def update(self):
        ret, frame = self.cap.read() # Read a frame from the camera
        if not ret:
            return

        height, width = frame.shape[:2]
        self.center_x = width / 2
        self.center_y = height / 2

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
                    self.target_confidence = conf
                    cx, _, _, bh = box.xywh[0].tolist() # Bounding box center and dimensions in pixels
                    self.target_pixel_x = cx
                    self.target_bbox_height = bh

                    if cx < frame.shape[1] / 3: # Target is on the left side of the frame
                        self.target_position = "left"
                    elif cx > 2 * frame.shape[1] / 3: # Target is on the right side of the frame
                        self.target_position = "right"
                    else: # Target is in the center of the frame
                        self.target_position = "center"

                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{name} {conf:.2f}", (x1, y1 - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    break # Only consider the first valid detection for now

        self._last_frame = frame

    def display(self) -> int:
        """Show the latest frame. Returns the key pressed (0xFF masked), or -1 if no frame."""
        if self._last_frame is None:
            return -1
        cv2.imshow("Target Detection", self._last_frame)
        return cv2.waitKey(1) & 0xFF

    def release(self):
        self.cap.release() # Release the video capture object
        cv2.destroyAllWindows() # Close all OpenCV windows