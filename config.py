# Connection parameters
CONNECTION_STRING = 'udp:127.0.0.1:14551'
BAUDRATE = 57600
LISTEN_PORT = 14551

# Camera parameters
CAMERA_INDEX = 0  # Index of the camera to use (0 for default)

# Flight parameters
TAKEOFF_ALTITUDE = 10

# Timing
UPDATE_RATE = 1  # seconds
YOLO_UPDATE_RATE = 0.2 # seconds

# Safety
LOW_BATTERY_THRESHOLD = 20
CRITICAL_BATTERY_THRESHOLD = 10

# Autonomy model
YOLO_MODEL_PATH = 'yolov8m.pt'  # Path to the YOLO model for target detection

# Autonomy parameters
YAW_RATE_MAX = 30.0     # deg/s - maximum rotation speed
YAW_GAIN = 0.05         # deg/s per pixel of error
YAW_DEADBAND = 20.0     # pixels - stop rotation when this close to center