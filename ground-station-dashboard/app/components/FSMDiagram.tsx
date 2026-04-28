import type { FSMState, AutonomySubstate } from '~/types/vehicle';

interface Props {
  currentState: FSMState;
  substate: AutonomySubstate;
}

const NW = 84;
const NH = 30;
const HW = NW / 2;
const HH = NH / 2;

type NodeDef = { id: FSMState; label: string; cx: number; cy: number };

const NODES: NodeDef[] = [
  { id: 'BOOT',     label: 'BOOT',     cx: 63,  cy: 72  },
  { id: 'STANDBY',  label: 'STANDBY',  cx: 193, cy: 72  },
  { id: 'ARMED',    label: 'ARMED',    cx: 323, cy: 72  },
  { id: 'TAKEOFF',  label: 'TAKEOFF',  cx: 453, cy: 72  },
  { id: 'HOVER',    label: 'HOVER',    cx: 453, cy: 192 },
  { id: 'AUTONOMY', label: 'AUTONOMY', cx: 323, cy: 192 },
  { id: 'RTL',      label: 'RTL',      cx: 193, cy: 192 },
  { id: 'LAND',     label: 'LAND',     cx: 63,  cy: 192 },
  { id: 'FAILSAFE', label: 'FAILSAFE', cx: 258, cy: 258 },
];

// MANUAL is entered from AUTONOMY (and HOVER), annotated at AUTONOMY position
const MANUAL_CX = 323;

type Arrow = { x1: number; y1: number; x2: number; y2: number; dashed?: boolean };

const ARROWS: Arrow[] = [
  // Boot sequence (top row, left → right)
  { x1: 63+HW, y1: 72, x2: 193-HW, y2: 72 },
  { x1: 193+HW, y1: 72, x2: 323-HW, y2: 72 },
  { x1: 323+HW, y1: 72, x2: 453-HW, y2: 72 },
  // TAKEOFF → HOVER (straight down — altitude reached)
  { x1: 453, y1: 72+HH, x2: 453, y2: 192-HH },
  // HOVER → AUTONOMY (left, top channel)
  { x1: 453-HW, y1: 187, x2: 323+HW, y2: 187 },
  // AUTONOMY → HOVER (right, return channel)
  { x1: 323+HW, y1: 197, x2: 453-HW, y2: 197 },
  // AUTONOMY → RTL → LAND (bottom row, continuing left)
  { x1: 323-HW, y1: 192, x2: 193+HW, y2: 192 },
  { x1: 193-HW, y1: 192, x2: 63+HW, y2: 192 },
  // LAND → STANDBY (left side, up)
  { x1: 63, y1: 192-HH, x2: 63, y2: 72+HH },
  // FAILSAFE paths (dashed orange) — from AUTONOMY position
  { x1: 323, y1: 192+HH, x2: 258, y2: 258-HH, dashed: true },
  { x1: 258-HW, y1: 258, x2: 63+HW, y2: 192+HH, dashed: true },
];

const SUBSTATE_LABELS: Record<AutonomySubstate, string> = {
  NONE:   'None',
  SEARCH: 'Search',
  TRAVEL: 'Travel',
  TRACK:  'Track',
};

function nodeColor(id: FSMState, active: boolean) {
  if (!active) return { fill: '#0f172a', stroke: '#334155', text: '#64748b' };
  if (id === 'FAILSAFE') return { fill: '#7f1d1d', stroke: '#ef4444', text: '#fca5a5' };
  return { fill: '#14532d', stroke: '#22c55e', text: '#bbf7d0' };
}

export function FSMDiagram({ currentState, substate }: Props) {
  const isManual = currentState === 'MANUAL';

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="flex items-center gap-3 flex-wrap">
        {substate !== 'NONE' && (
          <>
            <span className="text-gray-500 text-xs">Autonomy:</span>
            <span className="px-2 py-0.5 rounded bg-blue-950 border border-blue-800 text-blue-300 text-xs font-medium">
              {SUBSTATE_LABELS[substate]}
            </span>
          </>
        )}
        {isManual && (
          <span className="px-2 py-0.5 rounded bg-gray-800 border border-gray-600 text-gray-300 text-xs">
            Manual override active
          </span>
        )}
        <span className="ml-auto text-gray-600 text-xs">Active state highlighted green</span>
      </div>

      <svg
        viewBox="0 0 540 290"
        className="w-full"
        style={{ maxHeight: 260 }}
        aria-label="Flight state machine diagram"
      >
        <defs>
          <filter id="glow-g" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#22c55e" floodOpacity="0.7" />
          </filter>
          <filter id="glow-r" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#ef4444" floodOpacity="0.7" />
          </filter>
          <marker id="ah" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="8"
            refX="8" refY="4" orient="auto">
            <polygon points="0 1, 8 4, 0 7" fill="#475569" />
          </marker>
          <marker id="ah-e" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="8"
            refX="8" refY="4" orient="auto">
            <polygon points="0 1, 8 4, 0 7" fill="#f97316" />
          </marker>
        </defs>

        {ARROWS.map((arrow, i) => (
          <line
            key={i}
            x1={arrow.x1} y1={arrow.y1}
            x2={arrow.x2} y2={arrow.y2}
            stroke={arrow.dashed ? '#f97316' : '#475569'}
            strokeWidth="1.5"
            strokeDasharray={arrow.dashed ? '5 3' : undefined}
            markerEnd={arrow.dashed ? 'url(#ah-e)' : 'url(#ah)'}
          />
        ))}

        {/* MANUAL ↔ HOVER bidirectional arrow */}
        <line x1={MANUAL_CX} y1={192 - HH - 2} x2={MANUAL_CX} y2={145}
          stroke="#64748b" strokeWidth="1" strokeDasharray="3 2" />
        <text x={MANUAL_CX + 4} y={163} fontSize={7} fill="#475569" fontFamily="ui-sans-serif, sans-serif">
          MANUAL
        </text>

        {NODES.map(node => {
          const active = node.id === currentState;
          const colors = nodeColor(node.id, active);
          const isFailsafe = node.id === 'FAILSAFE';
          const glowFilter = active ? (isFailsafe ? 'url(#glow-r)' : 'url(#glow-g)') : undefined;

          return (
            <g key={node.id} filter={glowFilter}>
              <rect
                x={node.cx - HW} y={node.cy - HH}
                width={NW} height={NH} rx={5}
                fill={colors.fill}
                stroke={isFailsafe && !active ? '#7c3014' : colors.stroke}
                strokeWidth={active ? 1.5 : 1}
                strokeDasharray={isFailsafe && !active ? '4 2' : undefined}
              />
              <text
                x={node.cx} y={node.cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={9} fontFamily="ui-monospace, monospace"
                fontWeight={active ? 700 : 400}
                fill={colors.text}
              >
                {node.label}
              </text>
              {active && (
                <circle cx={node.cx + HW - 8} cy={node.cy - HH + 6} r={2.5}
                  fill={isFailsafe ? '#ef4444' : '#22c55e'} />
              )}
            </g>
          );
        })}

        {/* MANUAL active indicator overlay on HOVER position */}
        {isManual && (
          <rect x={MANUAL_CX - HW} y={135} width={NW} height={20} rx={3}
            fill="#1e293b" stroke="#64748b" strokeWidth={1.5}
            filter="url(#glow-g)"
          />
        )}
        {isManual && (
          <text x={MANUAL_CX} y={145} textAnchor="middle" dominantBaseline="middle"
            fontSize={9} fontFamily="ui-monospace, monospace" fontWeight={700} fill="#e2e8f0">
            MANUAL
          </text>
        )}

        <text x={258} y={282} textAnchor="middle" fontSize={9} fill="#7c3014" fontFamily="ui-sans-serif, sans-serif">
          triggered from any active state
        </text>
        <text x={10} y={72} dominantBaseline="middle" fontSize={7} fill="#334155" fontFamily="ui-sans-serif, sans-serif">↑ GND</text>
        <text x={10} y={192} dominantBaseline="middle" fontSize={7} fill="#334155" fontFamily="ui-sans-serif, sans-serif">↓ GND</text>
      </svg>

      <div className="grid grid-cols-5 gap-1">
        {NODES.filter(n => n.id !== 'FAILSAFE').map(node => {
          const active = node.id === currentState;
          return (
            <div key={node.id}
              className={`text-center text-[10px] py-0.5 rounded border transition-all ${
                active ? 'border-green-700 bg-green-950 text-green-300 font-semibold'
                       : 'border-gray-800 text-gray-600'
              }`}
            >
              {node.id}
            </div>
          );
        })}
        {/* MANUAL in legend */}
        <div className={`text-center text-[10px] py-0.5 rounded border transition-all ${
          isManual ? 'border-green-700 bg-green-950 text-green-300 font-semibold'
                   : 'border-gray-800 text-gray-600'
        }`}>
          MANUAL
        </div>
        <div className={`text-center text-[10px] py-0.5 rounded border transition-all ${
          currentState === 'FAILSAFE'
            ? 'border-red-700 bg-red-950 text-red-300 font-semibold'
            : 'border-orange-950 text-orange-900'
        }`}>
          FAILSAFE
        </div>
      </div>
    </div>
  );
}
