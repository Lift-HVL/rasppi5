from fsm.states import State, Autonomy
from fsm.event import Event


class FSMController:
    def __init__(self, commands):
        self.commands = commands
        self.current_state = State.BOOT
        self.next_state = self.current_state
        self.current_autonomy = None
        self.next_autonomy = self.current_autonomy

    def handle_event(self, event):
        self.next_state = self.current_state
        self.next_autonomy = self.current_autonomy

        """Determine the next state and autonomy based on the current state and incoming event."""
        match self.current_state:
            case State.BOOT:
                if event == Event.INIT_OK:
                    self.next_state = State.STANDBY
                elif event == Event.INIT_FAIL:
                    self.next_state = State.FAILSAFE

            case State.STANDBY:
                if event == Event.ARM:
                    self.next_state = State.ARMED

            case State.ARMED:
                if event == Event.DISARM:
                    self.next_state = State.STANDBY
                elif event == Event.TAKEOFF_CMD:
                    self.next_state = State.TAKEOFF
                elif event == Event.FAULT:
                    self.next_state = State.FAILSAFE
                elif event == Event.RESET_ON_GND:
                    self.next_state = State.STANDBY

            case State.TAKEOFF:
                if event == Event.ALTITUDE_REACHED:
                    self.next_state = State.HOVER
                elif event == Event.TAKEOFF_ABORT:
                    self.next_state = State.LAND
                elif event == Event.FAULT:
                    self.next_state = State.FAILSAFE

            case State.HOVER:
                if event == Event.START_SEARCH:
                    self.next_state = State.AUTONOMY
                    self.next_autonomy = Autonomy.SEARCH
                elif event == Event.START_TRAVEL:
                    self.next_state = State.AUTONOMY
                    self.next_autonomy = Autonomy.TRAVEL
                elif event == Event.RESUME_SEARCH:
                    self.next_state = State.AUTONOMY
                    self.next_autonomy = Autonomy.SEARCH
                elif event == Event.RESUME_TRAVEL:
                    self.next_state = State.AUTONOMY
                    self.next_autonomy = Autonomy.TRAVEL
                elif event == Event.MANUAL_OVERRIDE:
                    self.next_state = State.MANUAL
                    self.next_autonomy = None
                elif event == Event.LAND:
                    self.next_state = State.LAND
                    self.next_autonomy = None
                elif event == Event.FAULT:
                    self.next_state = State.FAILSAFE
                    self.next_autonomy = None

            case State.MANUAL:
                if event == Event.MANUAL_DONE:
                    self.next_state = State.HOVER
                elif event == Event.FAULT:
                    self.next_state = State.FAILSAFE
                elif event == Event.LAND:
                    self.next_state = State.LAND

            case State.AUTONOMY:
                if event == Event.START_SEARCH:
                    self.next_autonomy = Autonomy.SEARCH
                elif event == Event.START_TRAVEL:
                    self.next_autonomy = Autonomy.TRAVEL
                elif event == Event.RESUME_SEARCH:
                    self.next_autonomy = Autonomy.SEARCH
                elif event == Event.RESUME_TRAVEL:
                    self.next_autonomy = Autonomy.TRAVEL
                elif event == Event.START_TRACK:
                    self.next_autonomy = Autonomy.TRACK
                elif event == Event.RESUME_TRACK:
                    self.next_autonomy = Autonomy.TRACK
                elif event == Event.TARGET_ACQUIRED:
                    self.next_autonomy = Autonomy.TRACK
                elif event == Event.TARGET_LOST:
                    self.next_autonomy = Autonomy.SEARCH
                elif event == Event.START_TRAVEL:
                    self.next_autonomy = Autonomy.TRAVEL
                elif event == Event.TASK_PAUSED:
                    self.next_state = State.HOVER
                    self.next_autonomy = None
                elif event == Event.TASK_COMPLETED:
                    self.next_state = State.HOVER
                    self.next_autonomy = None
                elif event == Event.MANUAL_OVERRIDE:
                    self.next_state = State.MANUAL
                    self.next_autonomy = None
                elif event == Event.FAULT:
                    self.next_state = State.FAILSAFE
                    self.next_autonomy = None
                elif event == Event.LAND:
                    self.next_state = State.LAND
                    self.next_autonomy = None

            case State.FAILSAFE:
                if event == Event.CRITICAL_FAULT:
                    self.next_state = State.LAND
                    self.next_autonomy = None
                elif event == Event.RECOVERABLE_FAULT:
                    self.next_state = State.RTL
                    self.next_autonomy = None
                elif event == Event.RESET_ON_GND:
                    self.next_state = State.STANDBY
                    self.next_autonomy = None

            case State.LAND:
                if event == Event.LANDED_DISARM:
                    self.next_state = State.STANDBY
                    self.next_autonomy = None

            case State.RTL:
                if event == Event.HOME_REACHED:
                    self.next_state = State.LAND
                    self.next_autonomy = None

        self.apply_transition()

    def apply_transition(self):
        """Apply the state transition by updating the current state and autonomy to the next values."""
        self.current_state = self.next_state
        self.current_autonomy = self.next_autonomy