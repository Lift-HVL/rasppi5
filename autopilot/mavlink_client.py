from pymavlink import mavutil
from config import CONNECTION_STRING, BAUDRATE, CONNECTION_TIMEOUT

class MAVLinkClient:
    def __init__(self):
        self.master = mavutil.mavlink_connection(
            CONNECTION_STRING,
            baud=BAUDRATE,
        )

    def wait_heartbeat(self, timeout: float = CONNECTION_TIMEOUT) -> bool:
        """Wait for a heartbeat from the autopilot.

        Returns True if connected, False if timed out.
        """
        msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=timeout)
        if msg is None:
            print("No heartbeat received — running without autopilot connection")
            return False
        print("Heartbeat received from autopilot")
        return True

    def update_vehicle_state(self, state) -> bool:
        """Read one pending MAVLink message and apply it to a VehicleState.

        Returns True if a message was received and processed, False otherwise.
        Non-blocking: returns immediately when the receive buffer is empty.
        """
        msg = self.master.recv_match(blocking=False)
        if msg is None or msg.get_type() == 'BAD_DATA':
            return False
        state.update_from_message(msg, master=self.master)
        return True