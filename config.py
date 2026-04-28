import os

# Connection parameters
# Production (air Pi -> flight controller serial): '/dev/ttyAMA0'
# SITL / MissionPlanner (configure MP outbound UDP to 127.0.0.1:14552): 'udpin:0.0.0.0:14552'
CONNECTION_STRING = 'udpin:0.0.0.0:14552'
BAUDRATE = 57600
CONNECTION_TIMEOUT = 10.0  # seconds to wait for heartbeat before assuming no connection

# Camera parameters
CAMERA_INDEX = 0  # Index of the camera to use (0 for default)

# Flight parameters
TAKEOFF_ALTITUDE = 10

# Timing
UPDATE_RATE = 1  # seconds
YOLO_UPDATE_RATE = 0.2  # seconds

# Safety
LOW_BATTERY_THRESHOLD = 20
CRITICAL_BATTERY_THRESHOLD = 10
MIN_SATELLITES = 6

# Autonomy model
YOLO_MODEL_PATH = 'models/yolov8m.pt'  # Path to the YOLO model for target detection

# Autonomy parameters
YAW_DEADBAND = 20.0         # pixels - stop rotation when this close to center
FORWARD_SPEED = 1.5        # m/s - forward approach speed once target is centered
BBOX_REACH_THRESHOLD = 0.4 # fraction of frame height the bbox must fill to be "within reach"
YAW_KP = 0.1               # Proportional gain for yaw control
YAW_KI = 0.01              # Integral gain for yaw control
YAW_RATE_MAX = 30.0        # deg/s - maximum rotation speed
YAW_INTEGRAL_MAX = 100.0   # Maximum integral term to prevent windup

# Utility parameters
LOG_DIR = 'logs'  # Directory to save logs and images
