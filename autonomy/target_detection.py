"""Target detection functionality for the autonomous drone."""

import cv2
from ultralytics import YOLO
from config import YOLO_MODEL_PATH


def run():
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

                conf = box.conf[0].item()  # Get confidence score (0 - 1)
                cls = int(box.cls[0].item())  # Get class ID of the detected object
                name = result.names[cls]  # Get class name from the model's names list

                if conf > 0.8: # Only consider detections with confidence > 80% / filter weak detections
                    print(f"{name}: center=({cx:.0f}, {cy:.0f}), box=({x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f} -> {x2:.0f}, {y2:.0f}), confidence={conf:.2f}")
                    if cx >= 500: # Assuming frame width is 1000 pixels, this means the target is on the left side of the frame
                        print("Target is on the left side of the frame.")

                    if cx < 500: # Target is on the right side of the frame
                        print("Target is on the right side of the frame.")

                    # Draw on frame
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)  # Draw bounding box
                    cv2.putText(frame, f"{name} {conf:.2f}", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)  # Put class name and confidence on the frame

        cv2.imshow('Target Detection', frame)  # Display the frame with detections
        if cv2.waitKey(1) & 0xFF == ord('q'):  # Quit if 'q' is pressed
            break

    cap.release()  # Release the video capture object
    cv2.destroyAllWindows()  # Close all OpenCV windows
