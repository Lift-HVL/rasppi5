from ultralytics import YOLO



model = YOLO("best.pt")

for r in model.predict(source=0, stream=True, show=True, verbose=False):
    for i, box in enumerate(r.boxes):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        name = r.names[int(box.cls[0])]
        conf = box.conf[0].item()
        print(i, name, f'{conf:.2f}', f'center ({cx:.0f}, {cy:.0f})')