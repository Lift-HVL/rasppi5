from enum import Enum, auto

class State(Enum):
    BOOT = auto()                   # Drone is booting up
    STANDBY = auto()                # Drone is on standby, waiting for commands
    ARMED = auto()                  # Drone is armed and ready to take off
    TAKEOFF = auto()                # Drone is taking off
    HOVER = auto()                  # Drone is hovering in place
    MANUAL = auto()                 # Drone is in manual control mode
    FAIL = auto()                   # Drone has encountered a failure
    ABORT_TAKEOFF = auto()          # Takeoff has been aborted
    MOVE_CAMERA = auto()            # Drone is moving its camera
    
    