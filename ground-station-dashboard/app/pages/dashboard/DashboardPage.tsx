import { useVehicleState } from '~/hooks/useVehicleState';
import { useSettings } from '~/hooks/useSettings';
import { VehicleStateWidget } from '~/components/VehicleStateWidget';
import { FSMDiagram } from '~/components/FSMDiagram';
import { VideoFeed } from '~/components/VideoFeed';
import { AttitudeIndicator } from '~/components/AttitudeIndicator';
import { TelemetryChart } from '~/components/TelemetryChart';

function Panel({ title, children, className = '' }: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-gray-900 rounded-lg border border-gray-800 p-3 flex flex-col ${className}`}>
      {title && (
        <h2 className="text-gray-500 text-[10px] uppercase tracking-widest mb-3 shrink-0">{title}</h2>
      )}
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}

function StatusBar({ vs }: { vs: ReturnType<typeof useVehicleState> }) {
  const modeColors: Record<string, string> = {
    BOOT:     'text-blue-400',
    STANDBY:  'text-gray-400',
    ARMED:    'text-yellow-400',
    TAKEOFF:  'text-sky-400',
    HOVER:    'text-green-300',
    MANUAL:   'text-gray-300',
    AUTONOMY: 'text-green-400',
    FAILSAFE: 'text-red-400',
    LAND:     'text-yellow-300',
    RTL:      'text-orange-400',
  };

  return (
    <div className="flex items-center gap-4 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-xs shrink-0 flex-wrap">
      <div className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${vs.connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
        <span className={vs.connected ? 'text-green-400' : 'text-red-400'}>
          {vs.connected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">STATE</span>
        <span className={`font-semibold ${modeColors[vs.fsmState] ?? 'text-gray-300'}`}>
          {vs.fsmState}
        </span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">BAT</span>
        <span className={`font-mono ${vs.batteryPercent < 15 ? 'text-red-400' : vs.batteryPercent < 30 ? 'text-yellow-400' : 'text-green-400'}`}>
          {vs.batteryPercent.toFixed(0)}%
        </span>
        <span className="text-gray-600 font-mono ml-1">{vs.batteryVoltage.toFixed(1)}V</span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">GPS</span>
        <span className={`font-mono ${vs.gpsFixType >= 3 ? 'text-green-400' : 'text-yellow-400'}`}>
          {vs.gpsSatellites} sat
        </span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">ALT</span>
        <span className="text-gray-200 font-mono">{vs.relativeAltitude.toFixed(1)} m</span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">SPD</span>
        <span className="text-gray-200 font-mono">{vs.groundSpeed.toFixed(1)} m/s</span>
      </div>

      <div className="h-4 w-px bg-gray-700" />

      <div className="flex items-center gap-1">
        <span className="text-gray-600">RSSI</span>
        <span className={`font-mono ${vs.rssi < -80 ? 'text-red-400' : vs.rssi < -70 ? 'text-yellow-400' : 'text-green-400'}`}>
          {vs.rssi.toFixed(0)} dBm
        </span>
      </div>

      <div className="ml-auto text-gray-700 font-mono hidden lg:block">
        {new Date().toUTCString()}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { settings } = useSettings();
  const vs = useVehicleState();

  return (
    <div className="flex flex-col gap-3 p-3 h-[calc(100vh-3rem)] bg-gray-950 overflow-hidden">
      <StatusBar vs={vs} />

      {/* Main grid: vehicle state | FSM | video */}
      <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        <Panel title="Vehicle State" className="col-span-3 overflow-y-auto">
          <VehicleStateWidget
            state={vs}
            warnBatteryPct={settings.batteryWarnPercent}
            criticalBatteryPct={settings.batteryCriticalPercent}
          />
        </Panel>

        <Panel title="Flight State Machine" className="col-span-5">
          <FSMDiagram currentState={vs.fsmState} substate={vs.autonomySubstate} />
        </Panel>

        <Panel title="Video Feed" className="col-span-4">
          <VideoFeed url={settings.videoUrl || undefined} />
        </Panel>
      </div>

      {/* Bottom row: attitude + telemetry charts */}
      <div className="grid grid-cols-12 gap-3 shrink-0" style={{ height: 200 }}>
        <Panel title="Attitude" className="col-span-3">
          <AttitudeIndicator pitch={vs.pitch} roll={vs.roll} heading={vs.heading} />
        </Panel>

        <div className="col-span-9 grid grid-cols-4 gap-3">
          <TelemetryChart
            value={vs.relativeAltitude}
            label="Altitude AGL"
            unit="m"
            color="#38bdf8"
            minBound={0}
            maxBound={settings.maxAltitude}
          />
          <TelemetryChart
            value={vs.groundSpeed}
            label="Ground Speed"
            unit="m/s"
            color="#a78bfa"
            minBound={0}
            maxBound={settings.maxSpeed}
          />
          <TelemetryChart
            value={vs.batteryPercent}
            label="Battery"
            unit="%"
            color="#34d399"
            minBound={0}
            maxBound={100}
            warnBelow={settings.batteryWarnPercent}
          />
          <TelemetryChart
            value={vs.rssi}
            label="RSSI"
            unit="dBm"
            color="#fb923c"
            minBound={-110}
            maxBound={-20}
            warnBelow={settings.rssiWarnDbm}
          />
        </div>
      </div>
    </div>
  );
}
