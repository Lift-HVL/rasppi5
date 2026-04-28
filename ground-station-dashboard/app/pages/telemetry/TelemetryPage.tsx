import { useVehicleState } from '~/hooks/useVehicleState';
import { useSettings } from '~/hooks/useSettings';
import { TelemetryChart } from '~/components/TelemetryChart';
import { AttitudeIndicator } from '~/components/AttitudeIndicator';

export default function TelemetryPage() {
  const { settings } = useSettings();
  const vs = useVehicleState();

  const charts = [
    {
      value: vs.relativeAltitude,
      label: 'Altitude AGL',
      unit: 'm',
      color: '#38bdf8',
      minBound: 0,
      maxBound: settings.maxAltitude,
    },
    {
      value: vs.altitude,
      label: 'Altitude AMSL',
      unit: 'm',
      color: '#7dd3fc',
      minBound: 0,
      maxBound: settings.maxAltitude + 100,
    },
    {
      value: vs.groundSpeed,
      label: 'Ground Speed',
      unit: 'm/s',
      color: '#a78bfa',
      minBound: 0,
      maxBound: settings.maxSpeed,
    },
    {
      value: vs.airSpeed,
      label: 'Air Speed',
      unit: 'm/s',
      color: '#c4b5fd',
      minBound: 0,
      maxBound: settings.maxSpeed,
    },
    {
      value: vs.climbRate,
      label: 'Climb Rate',
      unit: 'm/s',
      color: '#86efac',
      minBound: -6,
      maxBound: 6,
      warnAbove: 4,
      warnBelow: -4,
    },
    {
      value: vs.batteryVoltage,
      label: 'Battery Voltage',
      unit: 'V',
      color: '#34d399',
      minBound: 18,
      maxBound: 25.2,
      warnBelow: 21,
    },
    {
      value: vs.batteryCurrent,
      label: 'Battery Current',
      unit: 'A',
      color: '#6ee7b7',
      minBound: 0,
      maxBound: 60,
    },
    {
      value: vs.batteryPercent,
      label: 'Battery %',
      unit: '%',
      color: '#4ade80',
      minBound: 0,
      maxBound: 100,
      warnBelow: settings.batteryWarnPercent,
    },
    {
      value: vs.rssi,
      label: 'RSSI',
      unit: 'dBm',
      color: '#fb923c',
      minBound: -110,
      maxBound: -20,
      warnBelow: settings.rssiWarnDbm,
    },
    {
      value: vs.distanceToHome,
      label: 'Dist to Home',
      unit: 'm',
      color: '#fbbf24',
      minBound: 0,
      maxBound: settings.geofenceRadius,
      warnAbove: settings.geofenceRadius * 0.9,
    },
    {
      value: vs.pitch,
      label: 'Pitch',
      unit: '°',
      color: '#f87171',
      minBound: -30,
      maxBound: 30,
      warnAbove: 20,
      warnBelow: -20,
    },
    {
      value: vs.roll,
      label: 'Roll',
      unit: '°',
      color: '#fca5a5',
      minBound: -45,
      maxBound: 45,
      warnAbove: 35,
      warnBelow: -35,
    },
  ];

  return (
    <div className="flex flex-col gap-3 p-3 h-[calc(100vh-3rem)] bg-gray-950 overflow-hidden">
      {/* Page header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-gray-200 font-semibold text-lg">Telemetry</h1>
          <p className="text-gray-600 text-xs">Live sensor data — last 60 seconds</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${vs.connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
          <span className={`text-xs ${vs.connected ? 'text-green-400' : 'text-red-400'}`}>
            {vs.connected ? 'Live' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Main content */}
      <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        {/* Charts grid */}
        <div className="col-span-9 grid grid-cols-3 gap-3 content-start overflow-y-auto">
          {charts.map(c => (
            <TelemetryChart key={c.label} {...c} />
          ))}
        </div>

        {/* Right column: attitude + position */}
        <div className="col-span-3 flex flex-col gap-3 h-full">
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 flex-1 flex flex-col min-h-0">
            <h2 className="text-gray-500 text-[10px] uppercase tracking-widest mb-3 shrink-0">Attitude</h2>
            <div className="flex-1 min-h-0">
              <AttitudeIndicator pitch={vs.pitch} roll={vs.roll} heading={vs.heading} />
            </div>
          </div>

          <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 shrink-0">
            <h2 className="text-gray-500 text-[10px] uppercase tracking-widest mb-3">Position</h2>
            <div className="space-y-1">
              {[
                { label: 'Latitude', value: `${vs.latitude.toFixed(6)}°` },
                { label: 'Longitude', value: `${vs.longitude.toFixed(6)}°` },
                { label: 'Alt AMSL', value: `${vs.altitude.toFixed(2)} m` },
                { label: 'Alt AGL', value: `${vs.relativeAltitude.toFixed(2)} m` },
                { label: 'Heading', value: `${vs.heading.toFixed(1)}°` },
                { label: 'GPS Fix', value: `${vs.gpsSatellites} satellites` },
                { label: 'Distance Home', value: `${vs.distanceToHome.toFixed(1)} m` },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between py-0.5 border-b border-gray-800 last:border-0">
                  <span className="text-gray-600 text-xs">{label}</span>
                  <span className="text-gray-200 text-xs font-mono">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
