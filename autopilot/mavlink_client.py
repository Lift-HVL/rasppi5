from pymavlink import mavutil
from config import CONNECTION_STRING, BAUDRATE

class MAVLinkClient:
    def __init__(self):
        self.master = mavutil.mavlink_connection(
            CONNECTION_STRING,
            baud=BAUDRATE,
        )

    def wait_heartbeat(self):
        """Wait for a heartbeat from the autopilot."""
        self.master.wait_heartbeat()
        print("Heartbeat received from autopilot")