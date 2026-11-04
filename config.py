import os

# Connection parameters
# Production (air Pi -> flight controller serial): '/dev/ttyAMA0'
# Ground-station bridge fan-out target: 'udpin:127.0.0.1:14552'
CONNECTION_STRING = 'udpin:127.0.0.1:14551'
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

# Where the autonomy loop gets its target from:
#   'remote' - the person locked in the ground station (Detection/detection.py owns the camera + YOLO
#              and tracks; the autonomy loop only reads the locked target over local UDP)
#   'local'  - autonomy/target_detection.py opens the camera itself (cannot run together with detection.py)
DETECTOR_SOURCE = os.environ.get('DETECTOR_SOURCE', 'remote')
TARGET_FEED_PORT = 5012      # detection.py -> autonomy (127.0.0.1): locked target, every YOLO run
TARGET_FEED_TIMEOUT = 1.0    # s without a feed packet before the target counts as lost
TRACK_CONTROL_PORT = 5011    # ground station -> detection.py: lock / release / follow
FOLLOW_MODE = DETECTOR_SOURCE == 'remote'  # keep following instead of stopping when "within reach"
TRACK_UPDATE_RATE = 0.1      # s - loop period while tracking (UPDATE_RATE is too slow for the PI regulator)

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
