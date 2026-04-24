import time

from pymavlink import mavutil
from config import CONNECTION_STRING, BAUDRATE, CONNECTION_TIMEOUT

class MAVLinkClient:
    def __init__(self, connection_string: str = None, baudrate: int = None):
        conn = connection_string or CONNECTION_STRING
        self.master = None
        last_error = None
        for candidate in self._connection_candidates(conn):
            try:
                self.master = mavutil.mavlink_connection(
                    candidate,
                    baud=baudrate or BAUDRATE,
                )
                if candidate != conn:
                    print(f"MAVLink bind fallback: {conn} -> {candidate}")
                break
            except PermissionError as exc:
                last_error = exc
                continue

        if self.master is None:
            raise RuntimeError(
                f"Unable to open MAVLink connection '{conn}' ({last_error}). "
                "On Windows, UDP ports can be blocked/reserved. "
                "Set a different port, e.g. 'udpin:127.0.0.1:14552'."
            ) from last_error

    @staticmethod
    def _connection_candidates(conn: str) -> list[str]:
        """Build a short list of connection fallbacks for UDP input on Windows."""
        if not conn.startswith("udpin:"):
            return [conn]
        try:
            endpoint = conn[len("udpin:"):]
            host, port_text = endpoint.rsplit(":", 1)
            port = int(port_text)
        except (ValueError, IndexError):
            return [conn]

        candidates = [conn]
        hosts = [host]
        if host == "0.0.0.0":
            hosts.append("127.0.0.1")

        for host_candidate in hosts:
            for port_candidate in range(port, port + 10):
                candidate = f"udpin:{host_candidate}:{port_candidate}"
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

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

    def send_named_float(self, name: str, value: float) -> None:
        """Inject a NAMED_VALUE_FLOAT into the MAVLink stream (routed to GCS by ArduPilot)."""
        self.master.mav.named_value_float_send(
            int(time.time() * 1000) & 0xFFFFFFFF,
            name.encode("ascii"),
            float(value),
        )

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
