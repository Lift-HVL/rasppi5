from enum import Enum, auto

class State(Enum):
    BOOT = auto()                   # Drone is booting up
    STANDBY = auto()                # Drone is on standby, waiting for commands
    ARMED = auto()                  # Drone is armed and ready to take off
    TAKEOFF = auto()                # Drone is taking off
    HOVER = auto()                  # Drone is hovering in place
    MANUAL = auto()                 # Drone is in manual control mode
    AUTONOMY = auto()               # Drone is in autonomous mode
    FAILSAFE = auto()               # Drone is in failsafe mode due to an error or loss of signal
    LAND = auto()                   # Drone is landing
    RTL = auto()                    # Drone is returning to launch point
    
class Autonomy(Enum):
    SEARCH = auto()                 # Drone is performing a search pattern
    TRAVEL = auto()                 # Drone is traveling to a specific location
    TRACK = auto()                  # Drone is tracking a detected target