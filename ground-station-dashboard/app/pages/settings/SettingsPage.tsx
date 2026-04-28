import { useEffect, useMemo, useState } from 'react';
import { useMavlinkLink, validateMavlinkSettings } from '~/hooks/useMavlinkLink';
import { useSettings } from '~/hooks/useSettings';
import type { GroundStationSettings, MavlinkLinkSettings, MavlinkTransport } from '~/hooks/useSettings';

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

function validateCrossField(settings: GroundStationSettings): string[] {
  const errors: string[] = [];
  if (settings.batteryCriticalPercent >= settings.batteryWarnPercent) {
    errors.push('Battery critical threshold must be lower than battery warning threshold.');
  }
  if (settings.maxAltitude <= 0) errors.push('Max altitude must be greater than 0.');
  if (settings.maxSpeed <= 0) errors.push('Max speed must be greater than 0.');
  return errors;
}

function sourceLabel(cfg: MavlinkLinkSettings): string {
  if (cfg.transport === 'serial') return `SERIAL:${cfg.serialPort || '-'}`;
  if (cfg.transport === 'udp') return `UDP:${cfg.udpHost || '-'}:${cfg.udpPort}`;
  if (cfg.transport === 'tcp') return `TCP:${cfg.tcpHost || '-'}:${cfg.tcpPort}`;
  return 'WS BRIDGE';
}

export default function SettingsPage() {
  const { settings, replaceSettings, resetSettings } = useSettings();
  const [draft, setDraft] = useState<GroundStationSettings>(settings);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const dirty = useMemo(() => !deepEqual(draft, settings), [draft, settings]);
  const mavlinkValidation = useMemo(() => validateMavlinkSettings(draft.mavlink), [draft.mavlink]);
  const crossValidation = useMemo(() => validateCrossField(draft), [draft]);
  const allErrors = useMemo(() => [...mavlinkValidation.errors, ...crossValidation], [crossValidation, mavlinkValidation.errors]);

  const { status, formatted, busy, applyConfig, connect, disconnect, testLink } = useMavlinkLink(draft.mavlink.wsBridgeUrl || undefined);

  function set<K extends keyof GroundStationSettings>(key: K, value: GroundStationSettings[K]) {
    setDraft(prev => ({ ...prev, [key]: value }));
  }

  function setMavlink<K extends keyof MavlinkLinkSettings>(key: K, value: MavlinkLinkSettings[K]) {
    setDraft(prev => ({ ...prev, mavlink: { ...prev.mavlink, [key]: value } }));
  }

  async function applyAll() {
    setError(null);
    if (allErrors.length) {
      setError(allErrors[0]);
      return;
    }

    replaceSettings(draft);

    try {
      await applyConfig(draft.mavlink);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch {
      setSaved(true);
      setError('Settings saved locally. Backend link API is unavailable or not configured yet.');
      setTimeout(() => setSaved(false), 1500);
    }
  }

  async function runAction(action: 'test' | 'connect' | 'disconnect') {
    setError(null);

    if (action !== 'disconnect' && allErrors.length) {
      setError(allErrors[0]);
      return;
    }

    try {
      if (action === 'test') await testLink(draft.mavlink);
      if (action === 'connect') await connect(draft.mavlink);
      if (action === 'disconnect') await disconnect();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'MAVLink link command failed.';
      setError(message);
    }
  }

  const transport = draft.mavlink.transport;

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-gray-950 p-4">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-gray-200 font-semibold text-lg">Settings</h1>
            <p className="text-gray-600 text-xs">Ground station and MAVLink link configuration</p>
          </div>
          <div className="flex items-center gap-2">
            {saved && <span className="text-green-400 text-xs">Saved</span>}
            <button
              onClick={() => { if (confirm('Reset all settings to defaults?')) { resetSettings(); setError(null); } }}
              className="px-3 py-1.5 rounded border border-gray-700 text-gray-400 text-xs hover:text-gray-200 hover:border-gray-500 transition-colors"
            >
              Reset defaults
            </button>
            <button
              onClick={applyAll}
              disabled={!dirty || busy}
              className="px-3 py-1.5 rounded border border-green-700 text-green-300 text-xs hover:text-green-100 hover:border-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Apply
            </button>
          </div>
        </div>

        {(error || status.lastError || allErrors.length > 0) && (
          <div className="bg-red-950 border border-red-900 rounded p-3 text-xs text-red-200 space-y-1">
            {error && <p>{error}</p>}
            {!error && status.lastError && <p>{status.lastError}</p>}
            {!error && !status.lastError && allErrors.map(msg => <p key={msg}>{msg}</p>)}
          </div>
        )}

        <Section title="MAVLink Link" description="Configure transport and bridge endpoint used by the dashboard telemetry socket">
          <Field label="Transport" hint="Select how the backend should connect to the vehicle MAVLink stream">
            <SelectInput<MavlinkTransport>
              value={transport}
              onChange={v => setMavlink('transport', v)}
              options={[
                { value: 'ws-bridge', label: 'WebSocket Bridge' },
                { value: 'serial', label: 'Serial' },
                { value: 'udp', label: 'UDP' },
                { value: 'tcp', label: 'TCP' },
              ]}
            />
          </Field>

          <Field label="Bridge WebSocket URL" hint="UI telemetry endpoint and command channel">
            <TextInput
              value={draft.mavlink.wsBridgeUrl}
              onChange={v => setMavlink('wsBridgeUrl', v)}
              placeholder="ws://192.168.1.x:8000/ws"
            />
          </Field>

          {transport === 'serial' && (
            <>
              <Field label="Serial Port" hint="Backend-visible serial device path">
                <TextInput
                  value={draft.mavlink.serialPort}
                  onChange={v => setMavlink('serialPort', v)}
                  placeholder="/dev/ttyUSB0 or COM3"
                />
              </Field>
              <Field label="Baud Rate">
                <SelectInput<string>
                  value={String(draft.mavlink.baudRate)}
                  onChange={v => setMavlink('baudRate', Number(v))}
                  options={[
                    { value: '9600', label: '9600' },
                    { value: '19200', label: '19200' },
                    { value: '38400', label: '38400' },
                    { value: '57600', label: '57600' },
                    { value: '115200', label: '115200' },
                    { value: '230400', label: '230400' },
                    { value: '460800', label: '460800' },
                    { value: '921600', label: '921600' },
                  ]}
                />
              </Field>
            </>
          )}

          {transport === 'udp' && (
            <>
              <Field label="UDP Host" hint="Backend target host for MAVLink UDP stream">
                <TextInput value={draft.mavlink.udpHost} onChange={v => setMavlink('udpHost', v)} placeholder="127.0.0.1" />
              </Field>
              <Field label="UDP Port">
                <NumberInput value={draft.mavlink.udpPort} onChange={v => setMavlink('udpPort', v)} min={1} max={65535} />
              </Field>
            </>
          )}

          {transport === 'tcp' && (
            <>
              <Field label="TCP Host" hint="Backend target host for MAVLink TCP stream">
                <TextInput value={draft.mavlink.tcpHost} onChange={v => setMavlink('tcpHost', v)} placeholder="127.0.0.1" />
              </Field>
              <Field label="TCP Port">
                <NumberInput value={draft.mavlink.tcpPort} onChange={v => setMavlink('tcpPort', v)} min={1} max={65535} />
              </Field>
            </>
          )}

          <Field label="Heartbeat Timeout">
            <NumberInput value={draft.mavlink.heartbeatTimeoutMs} onChange={v => setMavlink('heartbeatTimeoutMs', v)} min={500} max={30000} suffix="ms" />
          </Field>
          <Field label="Reconnect Interval">
            <NumberInput value={draft.mavlink.reconnectIntervalMs} onChange={v => setMavlink('reconnectIntervalMs', v)} min={200} max={30000} suffix="ms" />
          </Field>
          <Field label="Autoconnect" hint="Backend should reconnect automatically when link is lost">
            <Toggle value={draft.mavlink.autoconnect} onChange={v => setMavlink('autoconnect', v)} />
          </Field>

          <div className="pt-2 border-t border-gray-800">
            <div className="flex items-center justify-between gap-2 mb-2">
              <h3 className="text-gray-300 text-xs font-medium">Link Controls</h3>
              <span className="text-[11px] text-gray-600">Source: {status.source !== '-' ? status.source : sourceLabel(draft.mavlink)}</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs mb-3">
              <div className="bg-gray-950 border border-gray-800 rounded px-2 py-1.5 flex items-center justify-between">
                <span className="text-gray-500">Status</span>
                <span className={status.connected ? 'text-green-400' : 'text-red-400'}>{status.connected ? 'Connected' : 'Disconnected'}</span>
              </div>
              <div className="bg-gray-950 border border-gray-800 rounded px-2 py-1.5 flex items-center justify-between">
                <span className="text-gray-500">Heartbeat Age</span>
                <span className="text-gray-300 font-mono">{formatted.heartbeatAgeLabel}</span>
              </div>
              <div className="bg-gray-950 border border-gray-800 rounded px-2 py-1.5 flex items-center justify-between">
                <span className="text-gray-500">RX Rate</span>
                <span className="text-gray-300 font-mono">{formatted.rxRateLabel}</span>
              </div>
              <div className="bg-gray-950 border border-gray-800 rounded px-2 py-1.5 flex items-center justify-between">
                <span className="text-gray-500">TX Rate</span>
                <span className="text-gray-300 font-mono">{formatted.txRateLabel}</span>
              </div>
              <div className="bg-gray-950 border border-gray-800 rounded px-2 py-1.5 flex items-center justify-between col-span-2">
                <span className="text-gray-500">Packet Loss</span>
                <span className="text-gray-300 font-mono">{formatted.packetLossLabel}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => void runAction('test')}
                disabled={busy}
                className="px-2.5 py-1 rounded border border-gray-700 text-gray-300 hover:text-gray-100 hover:border-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Test Link
              </button>
              <button
                onClick={() => void runAction('connect')}
                disabled={busy}
                className="px-2.5 py-1 rounded border border-green-800 text-green-300 hover:text-green-100 hover:border-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Connect
              </button>
              <button
                onClick={() => void runAction('disconnect')}
                disabled={busy}
                className="px-2.5 py-1 rounded border border-yellow-800 text-yellow-300 hover:text-yellow-100 hover:border-yellow-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Disconnect
              </button>
            </div>
          </div>
        </Section>

        <Section title="Connection" description="Video stream endpoint for UI preview">
          <Field label="Video Stream URL" hint="MJPEG stream URL (for example http://drone/stream)">
            <TextInput
              value={draft.videoUrl}
              onChange={v => set('videoUrl', v)}
              placeholder="http://192.168.1.x:8080/stream"
            />
          </Field>
        </Section>

        <Section title="Vehicle Parameters" description="Flight envelope limits used by dashboard alerts">
          <Field label="Max Altitude" hint="Absolute ceiling for geofence and alerts">
            <NumberInput value={draft.maxAltitude} onChange={v => set('maxAltitude', v)} min={10} max={500} suffix="m" />
          </Field>
          <Field label="Max Speed" hint="Speed warning threshold">
            <NumberInput value={draft.maxSpeed} onChange={v => set('maxSpeed', v)} min={1} max={50} suffix="m/s" />
          </Field>
          <Field label="Geofence Radius" hint="Distance from home for geofence warnings">
            <NumberInput value={draft.geofenceRadius} onChange={v => set('geofenceRadius', v)} min={50} max={5000} step={50} suffix="m" />
          </Field>
          <Field label="RTL Altitude" hint="Altitude to climb to before returning to launch">
            <NumberInput value={draft.rtlAltitude} onChange={v => set('rtlAltitude', v)} min={10} max={200} suffix="m" />
          </Field>
        </Section>

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

        <Section title="Alert Thresholds" description="Values that trigger warnings in the UI">
          <Field label="Battery Warning" hint="Yellow alert threshold">
            <NumberInput value={draft.batteryWarnPercent} onChange={v => set('batteryWarnPercent', v)} min={10} max={80} suffix="%" />
          </Field>
          <Field label="Battery Critical" hint="Red alert threshold">
            <NumberInput value={draft.batteryCriticalPercent} onChange={v => set('batteryCriticalPercent', v)} min={5} max={30} suffix="%" />
          </Field>
          <Field label="RSSI Warning" hint="Signal strength below which a warning shows">
            <NumberInput value={draft.rssiWarnDbm} onChange={v => set('rssiWarnDbm', v)} min={-120} max={-40} suffix="dBm" />
          </Field>
        </Section>

        <Section title="Safety Behaviors" description="Automated failsafe responses (requires backend support)">
          <Field label="RTL on Signal Loss" hint="Trigger RTL when link is lost">
            <Toggle value={draft.rtlOnSignalLoss} onChange={v => set('rtlOnSignalLoss', v)} />
          </Field>
          <Field label="RTL on Low Battery" hint="Trigger RTL when battery hits critical threshold">
            <Toggle value={draft.rtlOnLowBattery} onChange={v => set('rtlOnLowBattery', v)} />
          </Field>
          <Field label="Geofence Enabled" hint="Alert when vehicle exceeds geofence radius">
            <Toggle value={draft.geofenceEnabled} onChange={v => set('geofenceEnabled', v)} />
          </Field>
          <Field label="Geofence Action" hint="Action to take when geofence is breached">
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
          HVL Lift Ground Station - settings stored in browser local storage
        </div>
      </div>
    </div>
  );
}
