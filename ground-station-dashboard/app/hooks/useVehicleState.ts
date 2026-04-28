import { useState, useEffect, useRef, useCallback } from 'react';
import type { FSMState, AutonomySubstate, GPSFixType, VehicleState } from '~/types/vehicle';

type ServerPayload = {
  connected?: boolean;
  armed?: boolean;
  mode?: string;
  altitude_relative_m?: number;
  altitude_absolute_m?: number;
  latitude?: number;
  longitude?: number;
  heading_deg?: number;
  groundspeed_m_s?: number;
  airspeed_m_s?: number;
  climb_rate_m_s?: number;
  pitch_deg?: number;
  roll_deg?: number;
  gps_fix_type?: number;
  gps_ok?: boolean;
  satellites_visible?: number;
  battery_remaining_pct?: number;
  battery_voltage_v?: number;
  battery_current_a?: number;
  rssi_dbm?: number;
  distance_to_home_m?: number;
  timestamp?: number;
  fsm_state?: FSMState;
  autonomy_substate?: AutonomySubstate;
  target_detected?: boolean;
  target_confidence?: number;
};

// ArduPilot mode string → FSMState fallback (used when fsm_state is absent)
const MODE_TO_FSM: Record<string, FSMState> = {
  STABILIZE: 'MANUAL', ACRO: 'MANUAL', SPORT: 'MANUAL', DRIFT: 'MANUAL',
  ALT_HOLD: 'HOVER', POSHOLD: 'HOVER', LOITER: 'HOVER', BRAKE: 'HOVER',
  AUTO: 'AUTONOMY', GUIDED: 'AUTONOMY', CIRCLE: 'AUTONOMY',
  FOLLOW: 'AUTONOMY', ZIGZAG: 'AUTONOMY', AVOID_ADSB: 'AUTONOMY',
  RTL: 'RTL', SMART_RTL: 'RTL', AUTO_RTL: 'RTL',
  LAND: 'LAND', AUTOROTATE: 'LAND',
  THROW: 'TAKEOFF',
};

const MODE_TO_SUBSTATE: Record<string, AutonomySubstate> = {
  AUTO: 'SEARCH', GUIDED: 'TRACK',
};

function mapPayload(d: ServerPayload): Partial<VehicleState> {
  const out: Partial<VehicleState> = {};

  if (d.connected           != null) out.connected        = d.connected;
  if (d.latitude            != null) out.latitude         = d.latitude;
  if (d.longitude           != null) out.longitude        = d.longitude;
  if (d.altitude_absolute_m != null) out.altitude         = d.altitude_absolute_m;
  if (d.altitude_relative_m != null) out.relativeAltitude = d.altitude_relative_m;
  if (d.groundspeed_m_s     != null) out.groundSpeed      = d.groundspeed_m_s;
  if (d.airspeed_m_s        != null) out.airSpeed         = d.airspeed_m_s;
  if (d.climb_rate_m_s      != null) out.climbRate        = d.climb_rate_m_s;
  if (d.heading_deg         != null) { out.heading = d.heading_deg; out.yaw = d.heading_deg; }
  if (d.pitch_deg           != null) out.pitch            = d.pitch_deg;
  if (d.roll_deg            != null) out.roll             = d.roll_deg;
  if (d.gps_fix_type        != null) out.gpsFixType       = d.gps_fix_type as GPSFixType;
  if (d.satellites_visible  != null) out.gpsSatellites    = d.satellites_visible;
  if (d.battery_remaining_pct != null) out.batteryPercent = d.battery_remaining_pct;
  if (d.battery_voltage_v   != null) out.batteryVoltage   = d.battery_voltage_v;
  if (d.battery_current_a   != null) out.batteryCurrent   = d.battery_current_a;
  if (d.rssi_dbm            != null) out.rssi             = d.rssi_dbm;
  if (d.distance_to_home_m  != null) out.distanceToHome   = d.distance_to_home_m;
  if (d.timestamp           != null) out.timestamp        = d.timestamp * 1000;

  // ArduPilot mode as fallback when no real FSM state is present
  if (d.mode != null && d.fsm_state == null) {
    out.fsmState         = MODE_TO_FSM[d.mode]      ?? 'STANDBY';
    out.autonomySubstate = MODE_TO_SUBSTATE[d.mode] ?? 'NONE';
    if (d.armed && out.fsmState === 'STANDBY') out.fsmState = 'ARMED';
  }

  // Real FSM state from ground_station.py — always takes priority
  if (d.fsm_state         != null) out.fsmState         = d.fsm_state;
  if (d.autonomy_substate != null) out.autonomySubstate = d.autonomy_substate;

  return out;
}

const DISCONNECTED_STATE: VehicleState = {
  connected: false,
  lastHeartbeat: 0,
  fsmState: 'STANDBY',
  autonomySubstate: 'NONE',
  batteryVoltage: 0,
  batteryCurrent: 0,
  batteryPercent: 0,
  gpsFixType: 0,
  gpsSatellites: 0,
  latitude: 0,
  longitude: 0,
  altitude: 0,
  relativeAltitude: 0,
  groundSpeed: 0,
  airSpeed: 0,
  heading: 0,
  climbRate: 0,
  pitch: 0,
  roll: 0,
  yaw: 0,
  rssi: 0,
  distanceToHome: 0,
  timestamp: 0,
};

export function useVehicleState(wsUrl?: string): VehicleState {
  const url = wsUrl || (typeof window !== 'undefined' ? `ws://${window.location.host}/ws` : undefined);

  const [state, setState] = useState<VehicleState>({ ...DISCONNECTED_STATE });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (!url) return;
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setState(prev => ({ ...prev, connected: true }));

      ws.onmessage = event => {
        try {
          const data = JSON.parse(event.data as string) as ServerPayload;
          setState(prev => ({ ...prev, ...mapPayload(data), lastHeartbeat: Date.now() }));
        } catch {}
      };

      ws.onclose = () => {
        setState({ ...DISCONNECTED_STATE });
        reconnectRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    } catch {
      setState({ ...DISCONNECTED_STATE });
      reconnectRef.current = setTimeout(connect, 5000);
    }
  }, [url]);

  useEffect(() => {
    if (!url) return;
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect, url]);

  return state;
}
