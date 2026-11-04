from ultralytics import YOLO

model = YOLO("best.pt")
model.export(format="hailo", name="hailo8l", imgsz=640, data="path/to/data.yaml")
