import { useMemo } from 'react';

export type Attitude = { pitch: number; roll: number; heading: number };

const PX_PER_DEG = 4;
const PITCH_MARKS = [-20, -15, -10, -5, 0, 5, 10, 15, 20];

export function AttitudeIndicator({ pitch, roll, heading }: Attitude) {
  const clamped = Math.max(-25, Math.min(25, pitch));
  const hdg = ((heading % 360) + 360) % 360;
  const pitchOffset = clamped * PX_PER_DEG;

  const compassTicks = useMemo(() =>
    Array.from({ length: 36 }, (_, i) => i * 10), []);

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* Artificial horizon */}
      <div className="relative flex-1 overflow-hidden rounded-lg border border-gray-800 min-h-[140px]">
        {/* Animated horizon layer */}
        <div
          className="absolute inset-[-50%] origin-center"
          style={{
            transform: `rotate(${roll}deg) translateY(${pitchOffset}px)`,
            transition: 'transform 150ms ease-out',
          }}
        >
          {/* Sky */}
          <div className="absolute inset-0 bg-gradient-to-b from-sky-900 via-sky-800 to-sky-700" />
          {/* Ground */}
          <div className="absolute inset-0 translate-y-[50%] bg-gradient-to-b from-amber-900 via-amber-800 to-amber-900" />
          {/* Horizon line */}
          <div className="absolute left-0 right-0 top-1/2 h-px bg-white/60" />

          {/* Pitch ladder */}
          {PITCH_MARKS.map(mark => (
            <div
              key={mark}
              className="absolute left-0 right-0"
              style={{ top: `calc(50% - ${mark * PX_PER_DEG}px)` }}
            >
              <div className="flex items-center justify-center gap-2">
                <div className={`h-px bg-white/70 ${mark === 0 ? 'w-16' : 'w-8'}`} />
                <span className="text-white/70 text-[9px] font-mono w-6 text-center">{mark}</span>
                <div className={`h-px bg-white/70 ${mark === 0 ? 'w-16' : 'w-8'}`} />
              </div>
            </div>
          ))}
        </div>

        {/* Fixed overlay: crosshair + labels */}
        <div className="pointer-events-none absolute inset-0">
          {/* Fixed crosshair */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="relative h-0 w-20">
              <div className="absolute top-0 left-0 w-8 h-px bg-yellow-400" />
              <div className="absolute top-0 right-0 w-8 h-px bg-yellow-400" />
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-px h-2 bg-yellow-400 -translate-y-2" />
            </div>
          </div>
          {/* Roll indicator text */}
          <div className="absolute top-1.5 left-2 text-[10px] font-mono text-white/70">
            R {roll >= 0 ? '+' : ''}{roll.toFixed(1)}°
          </div>
          <div className="absolute top-1.5 right-2 text-[10px] font-mono text-white/70">
            P {pitch >= 0 ? '+' : ''}{pitch.toFixed(1)}°
          </div>
        </div>
      </div>

      {/* Heading tape */}
      <div className="relative overflow-hidden h-7 bg-gray-900 rounded border border-gray-800">
        <div className="absolute inset-0 flex items-center">
          <div
            className="flex items-center h-full"
            style={{
              transform: `translateX(calc(50% - ${(hdg / 360) * 360 * 2.8}px))`,
              transition: 'transform 150ms ease-out',
              width: `${36 * 10 * 2.8}px`,
            }}
          >
            {compassTicks.map(deg => (
              <div key={deg} className="flex flex-col items-center" style={{ width: 28, flexShrink: 0 }}>
                <div className="w-px h-2 bg-gray-600" />
                <span className="text-[8px] text-gray-400 font-mono mt-0.5">
                  {deg === 0 ? 'N' : deg === 90 ? 'E' : deg === 180 ? 'S' : deg === 270 ? 'W' : deg}
                </span>
              </div>
            ))}
          </div>
        </div>
        {/* Center marker */}
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-yellow-400 pointer-events-none" />
        <div className="absolute left-1/2 -translate-x-1/2 top-1 text-[9px] font-mono text-yellow-400 bg-gray-900 px-0.5">
          {hdg.toFixed(0)}°
        </div>
      </div>

      {/* Data row */}
      <div className="grid grid-cols-3 gap-1">
        {[
          { label: 'Pitch', value: `${pitch.toFixed(1)}°` },
          { label: 'Roll', value: `${roll.toFixed(1)}°` },
          { label: 'Heading', value: `${hdg.toFixed(0)}°` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-gray-900 rounded border border-gray-800 px-2 py-1 text-center">
            <div className="text-gray-600 text-[9px]">{label}</div>
            <div className="text-gray-200 text-xs font-mono font-medium">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
