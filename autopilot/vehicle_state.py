from dataclasses import dataclass, field
from typing import Optional
import time
from pymavlink import mavutil

<<<<<<< HEAD

_FSM_STATE_NAMES = {
    0: "UNKNOWN", 1: "BOOT", 2: "STANDBY", 3: "ARMED", 4: "TAKEOFF",
    5: "HOVER", 6: "MANUAL", 7: "AUTONOMY", 8: "FAILSAFE", 9: "LAND", 10: "RTL",
}
_AUTONOMY_NAMES = {0: "NONE", 1: "SEARCH", 2: "TRAVEL", 3: "TRACK"}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

=======
>>>>>>> parent of 7f84b08 (Added dashboard websocket server)
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
    climb_rate_m_s: float = 0.0
    
    battery_voltage_v: Optional[float] = None
    battery_remaining_pct: Optional[int] = None
    
    gps_fix_type: int = 0
    satellites_visible: int = 0
    gps_ok: bool = False
    
    ekf_ok: bool = True
    in_air: bool = False
<<<<<<< HEAD

    # App-level telemetry injected by the companion computer via NAMED_VALUE_FLOAT.
    # Only populated in flight; stays at defaults when connected to bare SITL.
    fsm_state_id: int = 0
    fsm_state_name: str = "UNKNOWN"
    autonomy_id: int = 0
    autonomy_name: str = "NONE"
    app_target_detected: bool = False
    app_target_confidence: float = 0.0
    app_target_pixel_x: float = 0.0
    app_target_bbox_height: float = 0.0

    @property
    def distance_to_home_m(self) -> Optional[float]:
        if None in (self.latitude, self.longitude, self.home_latitude, self.home_longitude):
            return None
        return _haversine(self.latitude, self.longitude, self.home_latitude, self.home_longitude)
=======
>>>>>>> parent of 7f84b08 (Added dashboard websocket server)
    
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
            
        elif msg_type == "VFR_HUD":
            self.groundspeed_m_s = msg.groundspeed
            self.climb_rate_m_s = msg.climb
            
        elif msg_type == "EKF_STATUS_REPORT":
            flags = msg.flags
<<<<<<< HEAD
            self.ekf_ok = bool(flags & 0x1F == 0x1F)

        elif msg_type == "NAMED_VALUE_FLOAT":
            key = msg.name
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            key = key.rstrip("\x00")
            val = msg.value
            if key == "fsm_state":
                self.fsm_state_id = int(val)
                self.fsm_state_name = _FSM_STATE_NAMES.get(int(val), "UNKNOWN")
            elif key == "autonomy":
                self.autonomy_id = int(val)
                self.autonomy_name = _AUTONOMY_NAMES.get(int(val), "NONE")
            elif key == "tgt_det":
                self.app_target_detected = bool(round(val))
            elif key == "tgt_conf":
                self.app_target_confidence = val
            elif key == "tgt_px_x":
                self.app_target_pixel_x = val
            elif key == "tgt_bbox_h":
                self.app_target_bbox_height = val
=======
            self.ekf_ok = bool(flags & 0x1F == 0x1F)  # Check if all EKF status flags are set (0b11111)
>>>>>>> parent of 7f84b08 (Added dashboard websocket server)
    