import { useEffect, useMemo, useState } from 'react';
import { useSettings } from '~/hooks/useSettings';
import type { GroundStationSettings } from '~/hooks/useSettings';

function Section({ title, description, children }: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="mb-4">
        <h2 className="text-gray-200 font-medium text-sm">{title}</h2>
        {description && <p className="text-gray-600 text-xs mt-0.5">{description}</p>}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label className="text-gray-300 text-xs font-medium">{label}</label>
        {hint && <p className="text-gray-600 text-[11px] mt-0.5">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function TextInput({ value, onChange, placeholder }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-gray-500 w-56"
    />
  );
}

function NumberInput({ value, onChange, min, max, step = 1, suffix }: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        value={value}
        onChange={e => {
          const next = Number(e.target.value);
          if (!Number.isNaN(next)) onChange(next);
        }}
        min={min}
        max={max}
        step={step}
        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 outline-none focus:border-gray-500 w-24 text-right"
      />
      {suffix && <span className="text-gray-600 text-xs">{suffix}</span>}
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`relative flex h-5 w-9 items-center rounded-full transition-colors border ${
        value ? 'bg-green-900 border-green-700' : 'bg-gray-800 border-gray-700'
      }`}
      role="switch"
      aria-checked={value}
    >
      <span className={`h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${value ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  );
}

function SelectInput<T extends string>({ value, onChange, options }: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value as T)}
      className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 outline-none focus:border-gray-500"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function validateSettings(s: GroundStationSettings): string[] {
  const errors: string[] = [];
  if (s.batteryCriticalPercent >= s.batteryWarnPercent)
    errors.push('Battery critical threshold must be lower than battery warning threshold.');
  if (s.maxAltitude <= 0) errors.push('Max altitude must be greater than 0.');
  if (s.maxSpeed <= 0) errors.push('Max speed must be greater than 0.');
  if (s.takeoffAltitude <= 0) errors.push('Takeoff altitude must be greater than 0.');
  return errors;
}

export default function SettingsPage() {
  const { settings, replaceSettings, resetSettings } = useSettings();
  const [draft, setDraft] = useState<GroundStationSettings>(settings);
  const [saved, setSaved] = useState(false);

  useEffect(() => { setDraft(settings); }, [settings]);

  const dirty = useMemo(() => !deepEqual(draft, settings), [draft, settings]);
  const errors = useMemo(() => validateSettings(draft), [draft]);

  function set<K extends keyof GroundStationSettings>(key: K, value: GroundStationSettings[K]) {
    setDraft(prev => ({ ...prev, [key]: value }));
  }

  function applyAll() {
    if (errors.length) return;
    replaceSettings(draft);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-gray-950 p-4">
      <div className="max-w-3xl mx-auto space-y-4">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-gray-200 font-semibold text-lg">Settings</h1>
            <p className="text-gray-600 text-xs">Dashboard display and alert configuration</p>
          </div>
          <div className="flex items-center gap-2">
            {saved && <span className="text-green-400 text-xs">Saved</span>}
            <button
              onClick={() => { if (confirm('Reset all settings to defaults?')) resetSettings(); }}
              className="px-3 py-1.5 rounded border border-gray-700 text-gray-400 text-xs hover:text-gray-200 hover:border-gray-500 transition-colors"
            >
              Reset defaults
            </button>
            <button
              onClick={applyAll}
              disabled={!dirty || errors.length > 0}
              className="px-3 py-1.5 rounded border border-green-700 text-green-300 text-xs hover:text-green-100 hover:border-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Apply
            </button>
          </div>
        </div>

        {errors.length > 0 && (
          <div className="bg-red-950 border border-red-900 rounded p-3 text-xs text-red-200 space-y-1">
            {errors.map(msg => <p key={msg}>{msg}</p>)}
          </div>
        )}

        {/* Video */}
        <Section title="Video Feed" description="MJPEG stream displayed in the dashboard">
          <Field label="Stream URL" hint="e.g. http://192.168.1.x:8080/stream">
            <TextInput
              value={draft.videoUrl}
              onChange={v => set('videoUrl', v)}
              placeholder="http://192.168.1.x:8080/stream"
            />
          </Field>
        </Section>

        {/* Flight parameters */}
        <Section title="Flight Parameters" description="Reference values matching config.py on the drone">
          <Field label="Takeoff Altitude" hint="Target altitude in main.py (TAKEOFF_ALTITUDE)">
            <NumberInput value={draft.takeoffAltitude} onChange={v => set('takeoffAltitude', v)} min={1} max={200} suffix="m" />
          </Field>
          <Field label="RTL Altitude" hint="Altitude to reach before returning to launch">
            <NumberInput value={draft.rtlAltitude} onChange={v => set('rtlAltitude', v)} min={10} max={200} suffix="m" />
          </Field>
          <Field label="Min Satellites" hint="GPS satellite count below which a warning is shown (MIN_SATELLITES)">
            <NumberInput value={draft.minSatellites} onChange={v => set('minSatellites', v)} min={3} max={20} />
          </Field>
        </Section>

        {/* Chart limits */}
        <Section title="Chart Limits" description="Upper bounds for the telemetry charts on the dashboard">
          <Field label="Max Altitude" hint="Ceiling for the altitude chart">
            <NumberInput value={draft.maxAltitude} onChange={v => set('maxAltitude', v)} min={10} max={500} suffix="m" />
          </Field>
          <Field label="Max Speed" hint="Ceiling for the ground speed chart">
            <NumberInput value={draft.maxSpeed} onChange={v => set('maxSpeed', v)} min={1} max={50} suffix="m/s" />
          </Field>
          <Field label="Geofence Radius" hint="Distance from home for geofence warnings">
            <NumberInput value={draft.geofenceRadius} onChange={v => set('geofenceRadius', v)} min={50} max={5000} step={50} suffix="m" />
          </Field>
        </Section>

        {/* Display */}
        <Section title="Display Preferences">
          <Field label="Units">
            <SelectInput
              value={draft.units}
              onChange={v => set('units', v)}
              options={[
                { value: 'metric', label: 'Metric (m, m/s)' },
                { value: 'imperial', label: 'Imperial (ft, mph)' },
              ]}
            />
          </Field>
          <Field label="Coordinate Format">
            <SelectInput
              value={draft.coordFormat}
              onChange={v => set('coordFormat', v)}
              options={[
                { value: 'decimal', label: 'Decimal degrees' },
                { value: 'dms', label: 'Deg / Min / Sec' },
              ]}
            />
          </Field>
        </Section>

        {/* Alert thresholds */}
        <Section title="Alert Thresholds" description="Values that trigger colour warnings in the UI">
          <Field label="Battery Warning" hint="Yellow alert (LOW_BATTERY_THRESHOLD in config.py)">
            <NumberInput value={draft.batteryWarnPercent} onChange={v => set('batteryWarnPercent', v)} min={10} max={80} suffix="%" />
          </Field>
          <Field label="Battery Critical" hint="Red alert (CRITICAL_BATTERY_THRESHOLD in config.py)">
            <NumberInput value={draft.batteryCriticalPercent} onChange={v => set('batteryCriticalPercent', v)} min={5} max={30} suffix="%" />
          </Field>
          <Field label="RSSI Warning" hint="Signal strength below which a warning is shown">
            <NumberInput value={draft.rssiWarnDbm} onChange={v => set('rssiWarnDbm', v)} min={-120} max={-40} suffix="dBm" />
          </Field>
        </Section>

        {/* Safety */}
        <Section title="Safety Behaviours" description="Automated failsafe responses">
          <Field label="RTL on Signal Loss" hint="Show RTL recommendation when link is lost">
            <Toggle value={draft.rtlOnSignalLoss} onChange={v => set('rtlOnSignalLoss', v)} />
          </Field>
          <Field label="RTL on Low Battery" hint="Show RTL recommendation when battery hits critical threshold">
            <Toggle value={draft.rtlOnLowBattery} onChange={v => set('rtlOnLowBattery', v)} />
          </Field>
          <Field label="Geofence Enabled" hint="Alert when vehicle exceeds geofence radius">
            <Toggle value={draft.geofenceEnabled} onChange={v => set('geofenceEnabled', v)} />
          </Field>
          <Field label="Geofence Action" hint="Response when geofence is breached">
            <SelectInput
              value={draft.geofenceAction}
              onChange={v => set('geofenceAction', v)}
              options={[
                { value: 'warn', label: 'Warn only' },
                { value: 'rtl', label: 'Return to launch' },
                { value: 'land', label: 'Land immediately' },
              ]}
            />
          </Field>
        </Section>

        <div className="text-center text-gray-700 text-xs pb-4">
          HVL Lift Ground Station — settings stored in browser local storage
        </div>
      </div>
    </div>
  );
}
