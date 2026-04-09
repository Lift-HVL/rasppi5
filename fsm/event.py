from enum import Enum, auto

class Event(Enum):
    INIT_OK = auto()                # Initialization successful
    INIT_FAIL = auto()              # Initialization failed
    ARM = auto()                    # Command to arm the drone
    DISARM = auto()                 # Command to disarm the drone
    TAKEOFF_CMD = auto()            # Command to take off
    LAND = auto()                   # Command to land
    LANDED = auto()                 # Landing successful
    ALTITUDE_REACHED = auto()       # Desired altitude reached
    START_SEARCH = auto()           # Command to start search pattern
    START_TRAVEL = auto()           # Command to start travel to location
    TASK_PAUSED = auto()            # Command to pause current task
    RESUME_SEARCH = auto()          # Command to resume paused search
    RESUME_TRAVEL = auto()          # Command to resume paused travel
    TASK_COMPLETED = auto()         # Current task completed
    MANUAL_OVERRIDE = auto()        # Manual override activated
    MANUAL_DONE = auto()            # Manual control completed
    TAKEOFF_ABORT = auto()          # Takeoff aborted
    RESET_ON_GND = auto()           # Reset while on the ground
    FAULT = auto()                  # Fault detected
    CRITICAL_FAULT = auto()         # Critical fault detected, requires immediate attention
    RECOVERABLE_FAULT = auto()      # Fault detected that can be recovered from
    HOME_REACHED = auto()           # Home position reached during RTL
    LANDED_DISARM = auto()          # Drone has landed andbeen disarmed