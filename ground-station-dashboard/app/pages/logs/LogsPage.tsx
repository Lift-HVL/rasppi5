import { useEffect, useRef, useState } from 'react';
import type { LogEntry, LogLevel } from '~/types/vehicle';
import type { VehicleState } from '~/types/vehicle';
import { useVehicleState } from '~/hooks/useVehicleState';
import { useSettings } from '~/hooks/useSettings';

const LEVEL_COLORS: Record<LogLevel, string> = {
  DEBUG: 'text-gray-500',
  INFO:  'text-sky-400',
  WARN:  'text-yellow-400',
  ERROR: 'text-red-400',
};

const LEVEL_BG: Record<LogLevel, string> = {
  DEBUG: 'bg-gray-900',
  INFO:  'bg-sky-950/30',
  WARN:  'bg-yellow-950/30',
  ERROR: 'bg-red-950/40',
};

function formatTs(ts: number): string {
  const d = new Date(ts);
  return [
    d.getHours().toString().padStart(2, '0'),
    d.getMinutes().toString().padStart(2, '0'),
    d.getSeconds().toString().padStart(2, '0'),
  ].join(':') + '.' + d.getMilliseconds().toString().padStart(3, '0');
}

const ALL_LEVELS: LogLevel[] = ['DEBUG', 'INFO', 'WARN', 'ERROR'];


export default function LogsPage() {
  const vs = useVehicleState();
  const { settings } = useSettings();

  const [logs, setLogs]           = useState<LogEntry[]>([]);
  const [filter, setFilter]       = useState<LogLevel | 'ALL'>('ALL');
  const [search, setSearch]       = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const nextId     = useRef(1);
  const prevSnap   = useRef<VehicleState | null>(null);

  function push(...entries: Omit<LogEntry, 'id'>[]) {
    setLogs(prev => {
      const withIds = entries.map(e => ({ ...e, id: nextId.current++ }));
      return [...prev.slice(-900), ...withIds];
    });
  }

  // Detect vehicle-state events and convert to log entries
  useEffect(() => {
    const prev = prevSnap.current;
    const cur  = vs;
    prevSnap.current = cur;

    const t = Date.now();
    const mk = (level: LogLevel, source: string, message: string) =>
      ({ timestamp: t, level, source, message });

    const batch: Omit<LogEntry, 'id'>[] = [];

    if (prev === null) {
      // First tick — report initial state if already connected
      if (cur.connected) {
        batch.push(mk('INFO', 'LINK', 'Telemetry stream connected'));
        batch.push(mk('INFO', 'GPS',
          `GPS ${cur.gpsFixType >= 3 ? 'fix OK' : 'no fix'} — ${cur.gpsSatellites} satellites`));
        if (cur.batteryPercent > 0) {
          batch.push(mk('INFO', 'BATT',
            `Battery ${cur.batteryPercent.toFixed(0)}% — ${cur.batteryVoltage.toFixed(1)} V`));
        }
        batch.push(mk('INFO', 'FSM', `Current state: ${cur.fsmState}`));
      }
    } else {
      // --- Connection ---
      if (!prev.connected && cur.connected) {
        batch.push(mk('INFO', 'LINK', 'Telemetry stream connected'));
      } else if (prev.connected && !cur.connected) {
        batch.push(mk('ERROR', 'LINK', 'Connection lost — waiting for heartbeat'));
      }

      // --- FSM state transition ---
      if (prev.fsmState !== cur.fsmState) {
        batch.push(mk('INFO', 'FSM',
          `State transition: ${prev.fsmState} → ${cur.fsmState}`));

        if (cur.fsmState === 'ARMED') {
          batch.push(mk('INFO', 'MOTORS', 'Motor arming sequence complete'));
        } else if (cur.fsmState === 'TAKEOFF') {
          batch.push(mk('INFO', 'CTRL',
            `Takeoff initiated — target ${settings.takeoffAltitude} m AGL`));
        } else if (cur.fsmState === 'HOVER') {
          batch.push(mk('INFO', 'CTRL',
            `Hover engaged at ${cur.relativeAltitude.toFixed(1)} m AGL`));
        } else if (cur.fsmState === 'LAND') {
          batch.push(mk('INFO', 'CTRL',
            `Landing from ${cur.relativeAltitude.toFixed(1)} m AGL`));
        } else if (cur.fsmState === 'RTL') {
          batch.push(mk('WARN', 'FSM',
            `RTL initiated — ${cur.relativeAltitude.toFixed(1)} m AGL`));
        } else if (cur.fsmState === 'FAILSAFE') {
          batch.push(mk('ERROR', 'FSM',
            'FAILSAFE triggered — check battery and link quality'));
        } else if (cur.fsmState === 'STANDBY') {
          if (prev.fsmState === 'LAND') {
            batch.push(mk('INFO', 'FSM', 'Landing complete — disarmed'));
          }
        }
      }

      // --- Autonomy substate change ---
      if (prev.autonomySubstate !== cur.autonomySubstate) {
        if (cur.autonomySubstate !== 'NONE') {
          const descriptions: Record<string, string> = {
            SEARCH: 'Search pattern started',
            TRAVEL: 'Travelling to waypoint',
            TRACK:  'Target tracking engaged',
          };
          batch.push(mk('INFO', 'AUTO',
            descriptions[cur.autonomySubstate] ?? `Autonomy → ${cur.autonomySubstate}`));
        } else if (prev.autonomySubstate !== 'NONE') {
          batch.push(mk('INFO', 'AUTO', 'Autonomy paused — returning to hover'));
        }
      }

      // --- Battery threshold crossings ---
      const battWarn = settings.batteryWarnPercent;
      const battCrit = settings.batteryCriticalPercent;
      if (cur.batteryPercent > 0) {
        if (prev.batteryPercent > battWarn && cur.batteryPercent <= battWarn) {
          batch.push(mk('WARN', 'BATT',
            `Battery low: ${cur.batteryPercent.toFixed(0)}% — ${cur.batteryVoltage.toFixed(1)} V — consider RTL`));
        }
        if (prev.batteryPercent > battCrit && cur.batteryPercent <= battCrit) {
          batch.push(mk('ERROR', 'BATT',
            `Battery critical: ${cur.batteryPercent.toFixed(0)}% — ${cur.batteryVoltage.toFixed(1)} V`));
        }
      }

      // --- GPS fix change ---
      if (prev.gpsFixType < 3 && cur.gpsFixType >= 3) {
        batch.push(mk('INFO', 'GPS',
          `GPS fix acquired — ${cur.gpsSatellites} satellites, type ${cur.gpsFixType}`));
      } else if (prev.gpsFixType >= 3 && cur.gpsFixType < 3) {
        batch.push(mk('WARN', 'GPS',
          `GPS fix lost — ${cur.gpsSatellites} satellites remaining`));
      } else if (Math.abs(prev.gpsSatellites - cur.gpsSatellites) >= 3 && cur.gpsFixType >= 3) {
        batch.push(mk('DEBUG', 'GPS',
          `Satellite count: ${cur.gpsSatellites} (fix type ${cur.gpsFixType})`));
      }

      // --- RSSI warning ---
      const rssiWarn = settings.rssiWarnDbm;
      if (cur.rssi !== 0 && prev.rssi > rssiWarn && cur.rssi <= rssiWarn) {
        batch.push(mk('WARN', 'LINK',
          `RSSI low: ${cur.rssi.toFixed(0)} dBm — signal degraded`));
      }
      if (cur.rssi !== 0 && prev.rssi <= rssiWarn && cur.rssi > rssiWarn) {
        batch.push(mk('INFO', 'LINK',
          `RSSI recovered: ${cur.rssi.toFixed(0)} dBm`));
      }
    }

    if (batch.length > 0) push(...batch);
  }, [vs]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs, autoScroll]);

  const filtered = logs.filter(e => {
    if (filter !== 'ALL' && e.level !== filter) return false;
    if (search && !e.message.toLowerCase().includes(search.toLowerCase()) &&
        !e.source.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const counts = logs.reduce((acc, e) => {
    acc[e.level] = (acc[e.level] ?? 0) + 1;
    return acc;
  }, {} as Record<LogLevel, number>);

  return (
    <div className="flex flex-col gap-3 p-3 h-[calc(100vh-3rem)] bg-gray-950">
      {/* Header */}
      <div className="flex items-center gap-3 shrink-0 flex-wrap">
        <div>
          <h1 className="text-gray-200 font-semibold text-lg">System Logs</h1>
          <p className="text-gray-600 text-xs">{logs.length} entries — live from drone</p>
        </div>

        <div className="flex gap-3 ml-4">
          {ALL_LEVELS.map(lvl => (
            <span key={lvl} className={`text-xs font-mono ${LEVEL_COLORS[lvl]}`}>
              {lvl} {counts[lvl] ?? 0}
            </span>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="text"
            placeholder="Search…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-gray-500 w-40"
          />
          <select
            value={filter}
            onChange={e => setFilter(e.target.value as typeof filter)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 outline-none"
          >
            <option value="ALL">All levels</option>
            {ALL_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <button
            onClick={() => setAutoScroll(v => !v)}
            className={`px-2 py-1 rounded text-xs border transition-colors ${
              autoScroll
                ? 'border-green-700 bg-green-950 text-green-400'
                : 'border-gray-700 text-gray-500'
            }`}
          >
            Auto-scroll
          </button>
          <button
            onClick={() => setLogs([])}
            className="px-2 py-1 rounded text-xs border border-gray-700 text-gray-500 hover:text-gray-300 hover:border-gray-500 transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Log list */}
      <div
        onScroll={e => {
          const el = e.currentTarget;
          setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}
        className="flex-1 overflow-y-auto rounded-lg border border-gray-800 font-mono text-xs"
      >
        <div
          className="sticky top-0 z-10 grid bg-gray-900 border-b border-gray-800 px-3 py-1.5 text-gray-600"
          style={{ gridTemplateColumns: '90px 50px 70px 1fr' }}
        >
          <span>TIME</span>
          <span>LEVEL</span>
          <span>SOURCE</span>
          <span>MESSAGE</span>
        </div>

        {filtered.length === 0 && (
          <div className="p-8 text-center text-gray-700">
            {vs.connected ? 'Waiting for events…' : 'No connection — logs appear when drone connects'}
          </div>
        )}

        {filtered.map(entry => (
          <div
            key={entry.id}
            className={`grid px-3 py-0.5 border-b border-gray-900 hover:bg-gray-800/50 ${LEVEL_BG[entry.level]}`}
            style={{ gridTemplateColumns: '90px 50px 70px 1fr' }}
          >
            <span className="text-gray-600">{formatTs(entry.timestamp)}</span>
            <span className={`font-semibold ${LEVEL_COLORS[entry.level]}`}>{entry.level}</span>
            <span className="text-gray-400">{entry.source}</span>
            <span className="text-gray-300">{entry.message}</span>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
