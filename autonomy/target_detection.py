"""Target detection functionality for the autonomous drone."""

import cv2
from ultralytics import YOLO
from config import YOLO_MODEL_PATH

model = YOLO(YOLO_MODEL_PATH)       # YOLO model for target detection

cap = cv2.VideoCapture(0)           # Capture video from the default camera

while True:
    ret, frame = cap.read()          # Read a frame from the camera
    if not ret: 
        break
    
    results = model(frame)           # Run the YOLO model on the frame
    
    for result in results:
        boxes = result.boxes       # Get detected bounding boxes
        
        for box in boxes: 
            # --- Location data ---
            x1, y1, x2, y2 = box.xyxy[0].tolist()  # Get bounding box coordinates
            cx, cy = box.xywh[0][:2].tolist()  # Get bounding box center coordinates
            w, h = box.xywh[0][2:].tolist()  # Get bounding box width and height
            
            conf = box.conf[0].item()  # Get confidence score (0 - 1)
            cls = int(box.cls[0].item())  # Get class ID of the detected object