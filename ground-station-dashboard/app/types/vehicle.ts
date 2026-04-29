export type FSMState =
  | 'BOOT'
  | 'STANDBY'
  | 'ARMED'
  | 'TAKEOFF'
  | 'HOVER'
  | 'MANUAL'
  | 'AUTONOMY'
  | 'FAILSAFE'
  | 'LAND'
  | 'RTL';

export type AutonomySubstate = 'NONE' | 'SEARCH' | 'TRAVEL' | 'TRACK';

export type GPSFixType = 0 | 1 | 2 | 3 | 4;

export const GPS_FIX_LABELS: Record<GPSFixType, string> = {
  0: 'No GPS',
  1: 'No Fix',
  2: '2D Fix',
  3: '3D Fix',
  4: 'DGPS',
};

export interface DetectionBbox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface VehicleState {
  connected: boolean;
  lastHeartbeat: number;
  fsmState: FSMState;
  autonomySubstate: AutonomySubstate;
  batteryVoltage: number;
  batteryCurrent: number;
  batteryPercent: number;
  gpsFixType: GPSFixType;
  gpsSatellites: number;
  latitude: number;
  longitude: number;
  altitude: number;
  relativeAltitude: number;
  groundSpeed: number;
  airSpeed: number;
  heading: number;
  climbRate: number;
  pitch: number;
  roll: number;
  yaw: number;
  rssi: number;
  distanceToHome: number;
  timestamp: number;
  // AI / target detection
  targetDetected: boolean;
  targetConfidence: number;
  targetPosition: string;
  targetPixelX: number;
  targetBboxHeight: number;
  targetBbox: DetectionBbox | null;
  targetClassName: string;
  frameWidth: number;
  frameHeight: number;
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export interface LogEntry {
  id: number;
  timestamp: number;
  level: LogLevel;
  source: string;
  message: string;
}
