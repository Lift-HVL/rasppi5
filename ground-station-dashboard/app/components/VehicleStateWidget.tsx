import type { VehicleState } from '~/types/vehicle';
import { GPS_FIX_LABELS } from '~/types/vehicle';

interface Props {
  state: VehicleState;
  warnBatteryPct?: number;
  criticalBatteryPct?: number;
}

function Row({ label, value, tone }: { label: string; value: string; tone?: 'green' | 'yellow' | 'red' | 'default' }) {
  const colors: Record<string, string> = {
    green: 'text-green-400',
    yellow: 'text-yellow-400',
    red: 'text-red-400',
    default: 'text-gray-200',
  };
  return (
    <div className="flex justify-between items-center py-1 border-b border-gray-800 last:border-0">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className={`text-xs font-mono font-medium ${colors[tone ?? 'default']}`}>{value}</span>
    </div>
  );
}

function BatteryBar({ pct, warn, critical }: { pct: number; warn: number; critical: number }) {
  const color = pct <= critical ? 'bg-red-500' : pct <= warn ? 'bg-yellow-500' : 'bg-green-500';
  return (
    <div className="h-1.5 w-full rounded-full bg-gray-800 mt-1">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

function formatCoord(deg: number, isLat: boolean): string {
  const abs = Math.abs(deg);
  const dir = isLat ? (deg >= 0 ? 'N' : 'S') : (deg >= 0 ? 'E' : 'W');
  return `${abs.toFixed(5)}° ${dir}`;
}

export function VehicleStateWidget({ state, warnBatteryPct = 30, criticalBatteryPct = 15 }: Props) {
  const batTone = state.batteryPercent <= criticalBatteryPct
    ? 'red'
    : state.batteryPercent <= warnBatteryPct
    ? 'yellow'
    : 'green';

  const rssiTone = state.rssi < -85 ? 'red' : state.rssi < -75 ? 'yellow' : 'green';
  const gpsTone = state.gpsFixType >= 3 ? 'green' : state.gpsFixType === 2 ? 'yellow' : 'red';
  const secAgo = Math.floor((Date.now() - state.lastHeartbeat) / 1000);

  return (
    <div className="flex flex-col gap-1 h-full">
      {/* Connection header */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`h-2 w-2 rounded-full ${state.connected ? 'bg-green-500' : 'bg-red-500'} shrink-0`} />
        <span className={`text-xs font-medium ${state.connected ? 'text-green-400' : 'text-red-400'}`}>
          {state.connected ? 'Connected' : 'Disconnected'}
        </span>
        <span className="text-gray-600 text-xs ml-auto">{secAgo}s ago</span>
      </div>

      {/* Section: Power */}
      <p className="text-gray-600 text-[10px] uppercase tracking-widest mb-1">Power</p>
      <Row label="Battery" value={`${state.batteryPercent.toFixed(0)}%`} tone={batTone} />
      <BatteryBar pct={state.batteryPercent} warn={warnBatteryPct} critical={criticalBatteryPct} />
      <Row label="Voltage" value={`${state.batteryVoltage.toFixed(2)} V`} tone={batTone} />
      <Row label="Current" value={`${state.batteryCurrent.toFixed(1)} A`} />

      {/* Section: GPS */}
      <p className="text-gray-600 text-[10px] uppercase tracking-widest mt-3 mb-1">GPS</p>
      <Row label="Fix" value={`${GPS_FIX_LABELS[state.gpsFixType]} (${state.gpsSatellites} sat)`} tone={gpsTone} />
      <Row label="Latitude" value={formatCoord(state.latitude, true)} />
      <Row label="Longitude" value={formatCoord(state.longitude, false)} />
      <Row label="Alt AMSL" value={`${state.altitude.toFixed(1)} m`} />
      <Row label="Alt AGL" value={`${state.relativeAltitude.toFixed(1)} m`} />

      {/* Section: Motion */}
      <p className="text-gray-600 text-[10px] uppercase tracking-widest mt-3 mb-1">Motion</p>
      <Row label="Ground Speed" value={`${state.groundSpeed.toFixed(1)} m/s`} />
      <Row label="Air Speed" value={`${state.airSpeed.toFixed(1)} m/s`} />
      <Row label="Climb Rate" value={`${state.climbRate >= 0 ? '+' : ''}${state.climbRate.toFixed(1)} m/s`}
        tone={Math.abs(state.climbRate) > 3 ? 'yellow' : 'default'} />
      <Row label="Heading" value={`${state.heading.toFixed(0)}°`} />
      <Row label="Dist to Home" value={`${state.distanceToHome.toFixed(0)} m`} />

      {/* Section: Signal */}
      <p className="text-gray-600 text-[10px] uppercase tracking-widest mt-3 mb-1">Signal</p>
      <Row label="RSSI" value={`${state.rssi.toFixed(0)} dBm`} tone={rssiTone} />
    </div>
  );
}
