from dataclasses import dataclass, field
from typing import Optional
import time
from pymavlink import mavutil

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
            self.ekf_ok = bool(flags & 0x1F == 0x1F)  # Check if all EKF status flags are set (0b11111)
    