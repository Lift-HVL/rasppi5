import { useEffect, useRef, useState } from 'react';
import { useVehicleState } from '~/hooks/useVehicleState';
import { useSettings } from '~/hooks/useSettings';
import type { DetectionBbox } from '~/types/vehicle';

// ── helpers ──────────────────────────────────────────────────────────────────

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

function ConfBar({ value, color = '#22c55e' }: { value: number; color?: string }) {
  return (
    <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-150"
        style={{ width: `${(value * 100).toFixed(1)}%`, backgroundColor: color }}
      />
    </div>
  );
}

// Mini sparkline for confidence history
function Sparkline({ data, height = 40 }: { data: number[]; height?: number }) {
  if (data.length < 2) return <div style={{ height }} className="flex items-center justify-center text-gray-700 text-[10px]">Collecting data…</div>;

  const W = 400;
  const H = height;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - v * H;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      {/* grid lines */}
      {[0.25, 0.5, 0.75].map(t => (
        <line key={t} x1={0} y1={H - t * H} x2={W} y2={H - t * H} stroke="#1f2937" strokeWidth={1} />
      ))}
      <polyline points={pts} fill="none" stroke="#22c55e" strokeWidth={1.5} strokeLinejoin="round" />
      {/* current value dot */}
      {data.length > 0 && (
        <circle
          cx={W}
          cy={H - data[data.length - 1] * H}
          r={3}
          fill="#22c55e"
        />
      )}
    </svg>
  );
}

// ── camera + canvas overlay ───────────────────────────────────────────────────

function CameraWithOverlay({
  streamUrl,
  detected,
  confidence,
  bbox,
  className: cls,
  frameWidth,
  frameHeight,
}: {
  streamUrl?: string;
  detected: boolean;
  confidence: number;
  bbox: DetectionBbox | null;
  className?: string;
  frameWidth: number;
  frameHeight: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    const canvas    = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const cw = container.clientWidth;
    const ch = container.clientHeight;
    canvas.width  = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);

    if (!detected || !bbox) return;

    // Compute displayed rect for object-fit: contain
    let displayW = cw;
    let displayH = ch;
    let offsetX  = 0;
    let offsetY  = 0;

    if (frameWidth > 0 && frameHeight > 0) {
      const containerAspect = cw / ch;
      const videoAspect     = frameWidth / frameHeight;
      if (videoAspect > containerAspect) {
        displayW = cw;
        displayH = cw / videoAspect;
      } else {
        displayH = ch;
        displayW = ch * videoAspect;
      }
      offsetX = (cw - displayW) / 2;
      offsetY = (ch - displayH) / 2;
    }

    const x1 = offsetX + bbox.x1 * displayW;
    const y1 = offsetY + bbox.y1 * displayH;
    const x2 = offsetX + bbox.x2 * displayW;
    const y2 = offsetY + bbox.y2 * displayH;

    // Bounding box
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth   = 2;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

    // Corner accents
    const corner = Math.min(16, (x2 - x1) * 0.15, (y2 - y1) * 0.15);
    ctx.lineWidth = 3;
    [
      [x1, y1,  corner,  corner],
      [x2, y1, -corner,  corner],
      [x1, y2,  corner, -corner],
      [x2, y2, -corner, -corner],
    ].forEach(([px, py, dx, dy]) => {
      ctx.beginPath();
      ctx.moveTo(px + dx, py);
      ctx.lineTo(px, py);
      ctx.lineTo(px, py + dy);
      ctx.stroke();
    });

    // Confidence label
    ctx.fillStyle    = 'rgba(0,0,0,0.6)';
    const label      = `${(confidence * 100).toFixed(0)}%`;
    ctx.font         = 'bold 13px monospace';
    const textW      = ctx.measureText(label).width;
    ctx.fillRect(x1, y1 - 20, textW + 10, 20);
    ctx.fillStyle    = '#22c55e';
    ctx.fillText(label, x1 + 5, y1 - 5);

    // Center crosshair on target
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    ctx.strokeStyle = 'rgba(34,197,94,0.5)';
    ctx.lineWidth   = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(cx, offsetY); ctx.lineTo(cx, offsetY + displayH); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(offsetX, cy); ctx.lineTo(offsetX + displayW, cy); ctx.stroke();
    ctx.setLineDash([]);

  }, [detected, bbox, confidence, frameWidth, frameHeight]);

  const hasUrl = !!streamUrl;

  return (
    <div ref={containerRef} className={`relative bg-black rounded overflow-hidden ${cls ?? ''}`}>
      {hasUrl && !errored ? (
        <img
          src={streamUrl}
          alt="Camera feed"
          className="w-full h-full object-contain"
          onError={() => setErrored(true)}
        />
      ) : (
        <div className="flex flex-col items-center justify-center w-full h-full gap-3 text-gray-700 min-h-[200px]">
          <svg className="w-12 h-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
              d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <p className="text-xs">{errored ? 'Stream unavailable' : 'No video URL — configure in Settings'}</p>
        </div>
      )}

      {/* Canvas overlay for bounding boxes */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full pointer-events-none"
      />

      {/* LIVE indicator */}
      {hasUrl && !errored && (
        <div className="absolute top-2 left-2 flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] text-red-400 font-medium">LIVE</span>
        </div>
      )}

      {/* Detection badge */}
      {detected && (
        <div className="absolute top-2 right-2 flex items-center gap-1 bg-green-950/80 border border-green-700 rounded px-2 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-[10px] text-green-300 font-medium">TARGET LOCKED</span>
        </div>
      )}
    </div>
  );
}

// ── position indicator (left / center / right) ────────────────────────────────

function PositionIndicator({ position }: { position: string }) {
  const zones = ['left', 'center', 'right'] as const;
  return (
    <div className="flex gap-1">
      {zones.map(z => (
        <div
          key={z}
          className={`flex-1 h-6 rounded text-[9px] uppercase flex items-center justify-center font-mono transition-colors ${
            position === z
              ? 'bg-green-700 text-green-100'
              : 'bg-gray-800 text-gray-600'
          }`}
        >
          {z}
        </div>
      ))}
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function AIPage() {
  const vs = useVehicleState();
  const { settings } = useSettings();

  // Rolling confidence history (last 120 samples ≈ 24 s at 5 Hz)
  const [confHistory, setConfHistory] = useState<number[]>([]);
  const [detectionRate, setDetectionRate] = useState(0);
  const detCountRef  = useRef(0);
  const frameCountRef = useRef(0);

  useEffect(() => {
    frameCountRef.current += 1;
    if (vs.targetDetected) detCountRef.current += 1;

    setConfHistory(prev => {
      const next = [...prev, vs.targetDetected ? vs.targetConfidence : 0];
      return next.slice(-120);
    });

    if (frameCountRef.current > 0) {
      setDetectionRate(detCountRef.current / frameCountRef.current);
    }
  }, [vs.timestamp]);

  const hasDetector = vs.frameWidth > 0 || vs.targetDetected;
  const confPct     = (vs.targetConfidence * 100).toFixed(1);
  const bboxW       = vs.targetBbox ? ((vs.targetBbox.x2 - vs.targetBbox.x1) * (vs.frameWidth || 1)).toFixed(0) : '—';
  const bboxH       = vs.targetBboxHeight.toFixed(0);
  const distProxy   = vs.frameHeight > 0 && vs.targetBboxHeight > 0
    ? (vs.frameHeight / vs.targetBboxHeight).toFixed(2)
    : '—';

  return (
    <div className="flex flex-col gap-2 p-2 bg-gray-950 h-[calc(100vh-3rem)]">

      {/* Status bar */}
      <div className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 text-xs shrink-0 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${vs.connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
          <span className={vs.connected ? 'text-green-400' : 'text-red-400'}>
            {vs.connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="h-4 w-px bg-gray-700" />
        <div className="flex items-center gap-1">
          <span className="text-gray-600">MODEL</span>
          <span className="text-gray-300 font-mono">{hasDetector ? 'YOLOv8' : '—'}</span>
        </div>
        <div className="h-4 w-px bg-gray-700" />
        <div className="flex items-center gap-1">
          <span className="text-gray-600">FRAME</span>
          <span className="text-gray-300 font-mono">
            {vs.frameWidth > 0 ? `${vs.frameWidth}×${vs.frameHeight}` : '—'}
          </span>
        </div>
        <div className="h-4 w-px bg-gray-700" />
        <div className="flex items-center gap-1">
          <span className="text-gray-600">DET RATE</span>
          <span className={`font-mono ${detectionRate > 0.5 ? 'text-green-400' : detectionRate > 0.2 ? 'text-yellow-400' : 'text-gray-400'}`}>
            {(detectionRate * 100).toFixed(0)}%
          </span>
        </div>
        <div className="h-4 w-px bg-gray-700" />
        <div className="flex items-center gap-1">
          <span className="text-gray-600">TARGET</span>
          <span className={`font-mono font-semibold ${vs.targetDetected ? 'text-green-400' : 'text-gray-600'}`}>
            {vs.targetDetected ? (vs.targetClassName || 'DETECTED') : 'NONE'}
          </span>
        </div>
        {vs.targetDetected && (
          <>
            <div className="h-4 w-px bg-gray-700" />
            <div className="flex items-center gap-1">
              <span className="text-gray-600">CONF</span>
              <span className="text-green-400 font-mono">{confPct}%</span>
            </div>
            <div className="h-4 w-px bg-gray-700" />
            <div className="flex items-center gap-1">
              <span className="text-gray-600">POS</span>
              <span className="text-gray-200 font-mono uppercase">{vs.targetPosition || '—'}</span>
            </div>
          </>
        )}
      </div>

      {/* Main content */}
      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2">

        {/* Camera feed — left 8/12 cols */}
        <Panel title="Camera Feed" className="col-span-8">
          <CameraWithOverlay
            streamUrl={settings.videoUrl || '/video'}
            detected={vs.targetDetected}
            confidence={vs.targetConfidence}
            bbox={vs.targetBbox}
            frameWidth={vs.frameWidth}
            frameHeight={vs.frameHeight}
            className="h-full"
          />
        </Panel>

        {/* Debug panel — right 4/12 cols */}
        <div className="col-span-4 flex flex-col gap-2 min-h-0 overflow-y-auto">

          {/* Detection status */}
          <Panel title="Detection Status">
            <div className="flex flex-col gap-3">
              {/* Big indicator */}
              <div className={`rounded-lg border px-3 py-2 flex items-center gap-2 ${
                vs.targetDetected
                  ? 'border-green-700 bg-green-950/40'
                  : 'border-gray-700 bg-gray-900'
              }`}>
                <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${vs.targetDetected ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
                <span className={`text-sm font-semibold ${vs.targetDetected ? 'text-green-300' : 'text-gray-500'}`}>
                  {vs.targetDetected ? 'TARGET LOCKED' : 'SCANNING…'}
                </span>
                {vs.targetClassName && vs.targetDetected && (
                  <span className="ml-auto text-[10px] font-mono text-green-500 bg-green-950 px-1.5 py-0.5 rounded">
                    {vs.targetClassName}
                  </span>
                )}
              </div>

              {/* Confidence */}
              <div>
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-gray-500 uppercase tracking-wide">Confidence</span>
                  <span className={`font-mono ${vs.targetDetected ? 'text-green-400' : 'text-gray-600'}`}>
                    {vs.targetDetected ? `${confPct}%` : '—'}
                  </span>
                </div>
                <ConfBar
                  value={vs.targetDetected ? vs.targetConfidence : 0}
                  color={vs.targetConfidence > 0.9 ? '#22c55e' : vs.targetConfidence > 0.85 ? '#86efac' : '#facc15'}
                />
              </div>

              {/* Detection rate */}
              <div>
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-gray-500 uppercase tracking-wide">Detection Rate</span>
                  <span className="text-gray-300 font-mono">{(detectionRate * 100).toFixed(0)}%</span>
                </div>
                <ConfBar value={detectionRate} color="#60a5fa" />
              </div>
            </div>
          </Panel>

          {/* Position in frame */}
          <Panel title="Frame Position">
            <div className="flex flex-col gap-2">
              <PositionIndicator position={vs.targetDetected ? vs.targetPosition : ''} />
              <div className="grid grid-cols-2 gap-1 text-[10px]">
                {[
                  ['Pixel X', vs.targetDetected ? `${vs.targetPixelX.toFixed(0)} px` : '—'],
                  ['Frame Center', vs.frameWidth > 0 ? `${(vs.frameWidth / 2).toFixed(0)} px` : '—'],
                  ['Offset', vs.targetDetected && vs.frameWidth > 0
                    ? `${(vs.targetPixelX - vs.frameWidth / 2).toFixed(0)} px`
                    : '—'],
                  ['Normalized X', vs.targetDetected && vs.frameWidth > 0
                    ? `${((vs.targetPixelX / vs.frameWidth) * 100).toFixed(1)}%`
                    : '—'],
                ].map(([label, val]) => (
                  <div key={label} className="bg-gray-800 rounded px-2 py-1.5">
                    <div className="text-gray-500">{label}</div>
                    <div className="text-gray-200 font-mono mt-0.5">{val}</div>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          {/* Bounding box info */}
          <Panel title="Bounding Box">
            <div className="grid grid-cols-2 gap-1 text-[10px]">
              {[
                ['Width', `${bboxW} px`],
                ['Height', `${bboxH} px`],
                ['Dist Proxy', distProxy],
                ['Area', vs.targetBbox
                  ? `${((vs.targetBbox.x2 - vs.targetBbox.x1) * (vs.targetBbox.y2 - vs.targetBbox.y1) * 100).toFixed(1)}%`
                  : '—'],
                ['x1 y1', vs.targetBbox
                  ? `${(vs.targetBbox.x1 * 100).toFixed(1)}% ${(vs.targetBbox.y1 * 100).toFixed(1)}%`
                  : '—'],
                ['x2 y2', vs.targetBbox
                  ? `${(vs.targetBbox.x2 * 100).toFixed(1)}% ${(vs.targetBbox.y2 * 100).toFixed(1)}%`
                  : '—'],
              ].map(([label, val]) => (
                <div key={label} className="bg-gray-800 rounded px-2 py-1.5">
                  <div className="text-gray-500">{label}</div>
                  <div className={`font-mono mt-0.5 ${vs.targetDetected ? 'text-gray-200' : 'text-gray-600'}`}>{val}</div>
                </div>
              ))}
            </div>
            <p className="text-[9px] text-gray-700 mt-2">Dist Proxy = frame_h / bbox_h (higher = farther)</p>
          </Panel>

          {/* Confidence history */}
          <Panel title="Confidence History">
            <div className="flex flex-col gap-1">
              <div className="flex justify-between text-[9px] text-gray-600 font-mono mb-1">
                <span>100%</span>
                <span>← last 24 s</span>
              </div>
              <Sparkline data={confHistory} height={60} />
              <div className="flex justify-between text-[9px] text-gray-600 font-mono mt-0.5">
                <span>0%</span>
                <span>{confHistory.length} samples</span>
              </div>
            </div>
          </Panel>

          {/* Autonomy state */}
          <Panel title="Autonomy State">
            <div className="flex flex-col gap-1.5 text-[10px]">
              {[
                ['FSM State', vs.fsmState],
                ['Substate', vs.autonomySubstate],
                ['Alt AGL', `${vs.relativeAltitude.toFixed(1)} m`],
                ['Heading', `${vs.heading.toFixed(0)}°`],
              ].map(([label, val]) => (
                <div key={label} className="flex justify-between items-center">
                  <span className="text-gray-500">{label}</span>
                  <span className="text-gray-200 font-mono">{val}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
