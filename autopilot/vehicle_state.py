import math
from dataclasses import dataclass
from typing import Optional
import time
from pymavlink import mavutil

_FSM_STATE_NAMES = {
    1: "PREFLIGHT",  # BOOT
    2: "IDLE",       # STANDBY
    3: "ARMED",      # ARMED
    4: "TAKEOFF",    # TAKEOFF
    5: "LOITER",     # HOVER
    6: "IDLE",       # MANUAL
    7: "MISSION",    # AUTONOMY
    8: "EMERGENCY",  # FAILSAFE
    9: "LANDING",    # LAND
    10: "RTL",       # RTL
}
_AUTONOMY_NAMES = {
    1: "AUTO",       # SEARCH
    2: "AUTO",       # TRAVEL
    3: "OFFBOARD",   # TRACK
}


@dataclass
class VehicleState:
    connected: bool = False
    last_heartbeat_time: float = 0.0
    
    armed: bool = False
    mode: str = "UNKNOWN"
    system_status: str = "UNKNOWN"
    
    altitude_relative_m: float = 0.0
    altitude_absolute_m: float = 0.0
    
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    heading_deg: Optional[float] = None
    
    groundspeed_m_s: float = 0.0
    airspeed_m_s: float = 0.0
    climb_rate_m_s: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0

    battery_voltage_v: Optional[float] = None
    battery_remaining_pct: Optional[int] = None
    battery_current_a: Optional[float] = None

    gps_fix_type: int = 0
    satellites_visible: int = 0
    gps_ok: bool = False

    rssi_dbm: Optional[int] = None

    ekf_ok: bool = True
    in_air: bool = False

    # App telemetry injected via NAMED_VALUE_FLOAT from air Pi
    fsm_state_name: str = "IDLE"
    autonomy_name: str = "MANUAL"
    app_target_detected: bool = False
    app_target_confidence: float = 0.0
    app_target_pixel_x: float = 0.0
    app_target_bbox_height: float = 0.0
    
    def mark_heartbeat(self) -> None:
        self.connected = True
        self.last_heartbeat_time = time.time()
        
    def heartbeat_timeout(self, timeout_s: float = 2.0) -> bool:
        return (time.time() - self.last_heartbeat_time) > timeout_s
    
    def is_takeoff_ready(self) -> bool:
        return (
            self.connected
            and self.gps_ok
            and self.battery_remaining_pct is not None
            and self.battery_remaining_pct > 20
        )
        
    def update_from_message(self, msg, master=None) -> None:
        msg_type = msg.get_type()
        
        if msg_type == 'HEARTBEAT':
            self.mark_heartbeat()
            self.armed = bool(
                msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            )
            
            if master is not None:
                try: 
                    self.mode = mavutil.mode_string_v10(msg)  # Get mode name from the message
                except Exception:
                    self.mode = "UNKNOWN"
                    
        elif msg_type == 'GLOBAL_POSITION_INT':
            self.latitude = msg.lat / 1e7
            self.longitude = msg.lon / 1e7
            self.altitude_relative_m = msg.relative_alt / 1000.0
            self.altitude_absolute_m = msg.alt / 1000.0
            self.heading_deg = None if msg.hdg == 65535 else msg.hdg / 100.0
            
        elif msg_type == "GPS_RAW_INT":
            self.gps_fix_type = msg.fix_type
            self.satellites_visible = msg.satellites_visible
            self.gps_ok = self.gps_fix_type >= 3
            
        elif msg_type == "SYS_STATUS":
            self.battery_voltage_v = msg.voltage_battery / 1000.0
            self.battery_remaining_pct = msg.battery_remaining
            if msg.current_battery != -1:
                self.battery_current_a = msg.current_battery / 100.0

        elif msg_type == "VFR_HUD":
            self.groundspeed_m_s = msg.groundspeed
            self.airspeed_m_s = msg.airspeed
            self.climb_rate_m_s = msg.climb
            self.heading_deg = float(msg.heading)

        elif msg_type == "ATTITUDE":
            self.pitch_deg = math.degrees(msg.pitch)
            self.roll_deg = math.degrees(msg.roll)

        elif msg_type == "RADIO_STATUS":
            if msg.rssi != 255:
                self.rssi_dbm = msg.rssi - 120  # SiK approximation

        elif msg_type == "NAMED_VALUE_FLOAT":
            key = msg.name
            if isinstance(key, bytes):
                key = key.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
            else:
                key = key.split("\x00", 1)[0]
            val = float(msg.value)
            if key == "fsm_state":
                self.fsm_state_name = _FSM_STATE_NAMES.get(int(val), "IDLE")
            elif key == "autonomy":
                self.autonomy_name = _AUTONOMY_NAMES.get(int(val), "MANUAL")
            elif key == "tgt_det":
                self.app_target_detected = val >= 0.5
            elif key == "tgt_conf":
                self.app_target_confidence = val
            elif key == "tgt_px_x":
                self.app_target_pixel_x = val
            elif key == "tgt_bbox_h":
                self.app_target_bbox_height = val

        elif msg_type == "EKF_STATUS_REPORT":
            flags = msg.flags
            self.ekf_ok = bool(flags & 0x1F == 0x1F)
    