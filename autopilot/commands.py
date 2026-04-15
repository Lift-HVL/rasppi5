from pymavlink import mavutil
import time

class AutopilotCommands:
    def __init__(self, master):
        self.master = master

    def set_mode(self, mode_name: str) -> None:
        print(f"Setting mode to {mode_name}...")
        mode_mapping = self.master.mode_mapping()

        if mode_mapping is None or mode_name not in mode_mapping:
            raise ValueError(f"Unknown mode: {mode_name}")

        mode_id = mode_mapping[mode_name]

        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

    def arm(self) -> None:
        print("Arming the vehicle...")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1,
            0, 0, 0, 0, 0, 0
        )

    def disarm(self) -> None:
        print("Disarming the vehicle...")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0,
            0, 0, 0, 0, 0, 0
        )

    def takeoff(self, altitude: float) -> None:
        print(f"Initiating takeoff to {altitude} meters...")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0,
            0, 0, altitude
        )

    def rtl(self) -> None:
        print("Returning to launch...")
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            0,
            0, 0, 0, 0, 0, 0, 0
        )

    def land(self) -> None:
        print("Landing...")
        self.set_mode("LAND")

    def loiter(self) -> None:
        print("Switching to LOITER...")
        self.set_mode("LOITER")

    def guided(self) -> None:
        print("Switching to GUIDED...")
        self.set_mode("GUIDED")

    def set_yaw_rate(self, yaw_rate_deg_s: float) -> None:
        """Rotate the drone at the given yaw rate (deg/s). Positive = clockwise."""
        import math
        yaw_rate_rad_s = math.radians(yaw_rate_deg_s)
        # ArduPilot may ignore yaw_rate-only targets. Keep velocity dimensions active
        # (commanded as zero) and control yaw via yaw_rate.
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_X_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_Y_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_Z_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
        )
        self.master.mav.set_position_target_local_ned_send(
            0,
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            type_mask,
            0, 0, 0,
            0, 0, 0,
            0, 0, 0,
            0, yaw_rate_rad_s
        )

    def move_velocity(self, north: float, east: float, down: float) -> None:
        self.master.mav.set_position_target_local_ned_send(
            0,
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000111111000111,
            0, 0, 0,
            north, east, down,
            0, 0, 0,
            0, 0
        )

    def move_for_duration(
        self,
        north: float,
        east: float,
        down: float,
        duration: float,
        rate_hz: float = 10.0
    ) -> None:
        print(
            f"Moving with velocity "
            f"(N={north}, E={east}, D={down}) for {duration} seconds..."
        )
        period = 1.0 / rate_hz
        start = time.time()

        while time.time() - start < duration:
            self.move_velocity(north, east, down)
            time.sleep(period)
