import { useEffect, useRef, useState } from 'react';
import type { LogEntry, LogLevel } from '~/types/vehicle';

const INITIAL_LOGS: LogEntry[] = [
  { id: 1, timestamp: Date.now() - 120000, level: 'INFO', source: 'SYSTEM', message: 'Ground station initialized' },
  { id: 2, timestamp: Date.now() - 110000, level: 'INFO', source: 'GPS', message: 'GPS fix acquired — 13 satellites, HDOP 0.8' },
  { id: 3, timestamp: Date.now() - 100000, level: 'INFO', source: 'BATT', message: 'Battery health OK — 22.4V, 72%' },
  { id: 4, timestamp: Date.now() - 95000, level: 'INFO', source: 'FSM', message: 'State transition: IDLE → PREFLIGHT' },
  { id: 5, timestamp: Date.now() - 90000, level: 'INFO', source: 'PREFLIGHT', message: 'IMU calibration complete' },
  { id: 6, timestamp: Date.now() - 85000, level: 'INFO', source: 'PREFLIGHT', message: 'Compass calibration OK' },
  { id: 7, timestamp: Date.now() - 80000, level: 'WARN', source: 'WIND', message: 'Wind speed elevated — 6.2 m/s at 180°' },
  { id: 8, timestamp: Date.now() - 75000, level: 'INFO', source: 'FSM', message: 'State transition: PREFLIGHT → ARMED' },
  { id: 9, timestamp: Date.now() - 70000, level: 'INFO', source: 'MOTORS', message: 'Motor arming sequence complete' },
  { id: 10, timestamp: Date.now() - 65000, level: 'INFO', source: 'FSM', message: 'State transition: ARMED → TAKEOFF' },
  { id: 11, timestamp: Date.now() - 60000, level: 'INFO', source: 'CTRL', message: 'Takeoff initiated — target altitude 30.0m' },
  { id: 12, timestamp: Date.now() - 55000, level: 'INFO', source: 'CTRL', message: 'Target altitude reached — 30.2m AGL' },
  { id: 13, timestamp: Date.now() - 50000, level: 'INFO', source: 'FSM', message: 'State transition: TAKEOFF → MISSION' },
  { id: 14, timestamp: Date.now() - 45000, level: 'DEBUG', source: 'NAV', message: 'Waypoint 1/5 reached — moving to next' },
  { id: 15, timestamp: Date.now() - 40000, level: 'DEBUG', source: 'NAV', message: 'Waypoint 2/5 reached — moving to next' },
  { id: 16, timestamp: Date.now() - 35000, level: 'WARN', source: 'BATT', message: 'Battery at 75% — monitoring' },
  { id: 17, timestamp: Date.now() - 30000, level: 'INFO', source: 'FSM', message: 'State transition: MISSION → LOITER' },
  { id: 18, timestamp: Date.now() - 25000, level: 'INFO', source: 'CTRL', message: 'Loiter engaged at (60.3914, 5.3229)' },
  { id: 19, timestamp: Date.now() - 10000, level: 'INFO', source: 'LINK', message: 'Telemetry uplink nominal — RSSI -62 dBm' },
];

let nextId = INITIAL_LOGS.length + 1;

const MOCK_MESSAGES: Array<[LogLevel, string, string]> = [
  ['DEBUG', 'NAV', 'Position hold active — deviation < 0.5m'],
  ['INFO', 'LINK', `Telemetry ping — RSSI -63 dBm`],
  ['DEBUG', 'BATT', 'Power consumption 8.1A at 22.4V'],
  ['INFO', 'GPS', 'GPS signal nominal — 13 sats'],
  ['WARN', 'WIND', 'Gust detected — 7.1 m/s'],
  ['DEBUG', 'IMU', 'Attitude stable — pitch -1.1° roll 2.0°'],
  ['INFO', 'CTRL', 'Control loop iteration nominal'],
];

const LEVEL_COLORS: Record<LogLevel, string> = {
  DEBUG: 'text-gray-500',
  INFO: 'text-sky-400',
  WARN: 'text-yellow-400',
  ERROR: 'text-red-400',
};

const LEVEL_BG: Record<LogLevel, string> = {
  DEBUG: 'bg-gray-900',
  INFO: 'bg-sky-950/30',
  WARN: 'bg-yellow-950/30',
  ERROR: 'bg-red-950/40',
};

function formatTs(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}.${d.getMilliseconds().toString().padStart(3, '0')}`;
}

const ALL_LEVELS: LogLevel[] = ['DEBUG', 'INFO', 'WARN', 'ERROR'];

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>(INITIAL_LOGS);
  const [filter, setFilter] = useState<LogLevel | 'ALL'>('ALL');
  const [search, setSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Simulate incoming log entries
  useEffect(() => {
    const id = setInterval(() => {
      const [level, source, msg] = MOCK_MESSAGES[Math.floor(Math.random() * MOCK_MESSAGES.length)];
      setLogs(prev => [...prev.slice(-500), {
        id: nextId++,
        timestamp: Date.now(),
        level,
        source,
        message: msg,
      }]);
    }, 2500);
    return () => clearInterval(id);
  }, []);

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
      <div className="flex items-center gap-3 shrink-0">
        <div>
          <h1 className="text-gray-200 font-semibold text-lg">System Logs</h1>
          <p className="text-gray-600 text-xs">{logs.length} entries — live stream</p>
        </div>

        {/* Level counters */}
        <div className="flex gap-2 ml-4">
          {ALL_LEVELS.map(lvl => (
            <span key={lvl} className={`text-xs font-mono ${LEVEL_COLORS[lvl]}`}>
              {lvl} {counts[lvl] ?? 0}
            </span>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Search */}
          <input
            type="text"
            placeholder="Search…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-gray-500 w-40"
          />

          {/* Level filter */}
          <select
            value={filter}
            onChange={e => setFilter(e.target.value as typeof filter)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 outline-none"
          >
            <option value="ALL">All levels</option>
            {ALL_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>

          {/* Auto-scroll toggle */}
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

          {/* Clear */}
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
        ref={listRef}
        onScroll={e => {
          const el = e.currentTarget;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          setAutoScroll(atBottom);
        }}
        className="flex-1 overflow-y-auto rounded-lg border border-gray-800 font-mono text-xs"
      >
        {/* Column headers */}
        <div className="sticky top-0 z-10 grid bg-gray-900 border-b border-gray-800 px-3 py-1.5 text-gray-600"
          style={{ gridTemplateColumns: '90px 50px 80px 1fr' }}>
          <span>TIME</span>
          <span>LEVEL</span>
          <span>SOURCE</span>
          <span>MESSAGE</span>
        </div>

        {filtered.length === 0 && (
          <div className="p-8 text-center text-gray-700">No log entries match filters</div>
        )}

        {filtered.map(entry => (
          <div
            key={entry.id}
            className={`grid px-3 py-0.5 border-b border-gray-900 hover:bg-gray-800/50 transition-colors ${LEVEL_BG[entry.level]}`}
            style={{ gridTemplateColumns: '90px 50px 80px 1fr' }}
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
