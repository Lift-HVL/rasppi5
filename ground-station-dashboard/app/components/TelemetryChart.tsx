import { useEffect, useState } from 'react';

interface Props {
  value: number;
  label: string;
  unit: string;
  color: string;
  minBound?: number;
  maxBound?: number;
  bufferSize?: number;
  warnAbove?: number;
  warnBelow?: number;
}

const W = 260;
const H = 60;

export function TelemetryChart({
  value,
  label,
  unit,
  color,
  minBound,
  maxBound,
  bufferSize = 120,
  warnAbove,
  warnBelow,
}: Props) {
  const [buf, setBuf] = useState<number[]>(() => new Array(bufferSize).fill(value));

  useEffect(() => {
    setBuf(prev => [...prev.slice(-(bufferSize - 1)), value]);
  }, [value, bufferSize]);

  const min = minBound ?? Math.min(...buf);
  const max = maxBound ?? Math.max(...buf);
  const range = max === min ? 1 : max - min;

  const pts = buf
    .map((v, i) => {
      const x = (i / (bufferSize - 1)) * W;
      const y = H - ((v - min) / range) * (H - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const isWarning = (warnAbove !== undefined && value > warnAbove) ||
    (warnBelow !== undefined && value < warnBelow);

  const displayColor = isWarning ? '#f59e0b' : color;

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-3">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-gray-500 text-xs">{label}</span>
        <span className={`text-sm font-mono font-semibold ${isWarning ? 'text-yellow-400' : 'text-gray-200'}`}>
          {value.toFixed(1)}
          <span className="text-gray-500 text-xs ml-1">{unit}</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 50 }}>
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map(f => (
          <line key={f} x1={0} y1={H * (1 - f)} x2={W} y2={H * (1 - f)}
            stroke="#1e293b" strokeWidth="1" />
        ))}
        <polyline points={pts} fill="none" stroke={displayColor} strokeWidth="1.5" strokeLinejoin="round" />
        {/* Current value dot */}
        <circle cx={W} cy={H - ((value - min) / range) * (H - 6) - 3} r="2.5" fill={displayColor} />
      </svg>
      <div className="flex justify-between mt-0.5">
        <span className="text-[10px] text-gray-700">{min.toFixed(1)}</span>
        <span className="text-[10px] text-gray-700">{max.toFixed(1)}</span>
      </div>
    </div>
  );
}
