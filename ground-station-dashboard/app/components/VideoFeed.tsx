import { useState } from 'react';

interface Props {
  url?: string;
  label?: string;
}

export function VideoFeed({ url, label = 'Camera Feed' }: Props) {
  const [errored, setErrored] = useState(false);
  const [overlayVisible, setOverlayVisible] = useState(true);

  const hasUrl = !!url;

  return (
    <div className="relative flex flex-col h-full bg-black rounded overflow-hidden border border-gray-800">
      {/* HUD overlay toggle */}
      <button
        onClick={() => setOverlayVisible(v => !v)}
        className="absolute top-2 right-2 z-10 px-2 py-0.5 bg-black/60 text-gray-400 text-[10px] rounded hover:text-gray-200 transition-colors"
      >
        {overlayVisible ? 'HUD ✕' : 'HUD'}
      </button>

      {/* Video content */}
      {hasUrl && !errored ? (
        <img
          src={url}
          alt="Video feed"
          className="w-full h-full object-cover"
          onError={() => setErrored(true)}
        />
      ) : (
        <div className="flex flex-col items-center justify-center flex-1 gap-3 text-gray-700 p-4 min-h-[180px]">
          <svg className="w-12 h-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
              d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <p className="text-xs text-center">
            {errored ? 'Stream unavailable' : 'No video URL configured'}
          </p>
          {!hasUrl && (
            <p className="text-[10px] text-gray-600 text-center">
              Set a stream URL in Settings
            </p>
          )}
        </div>
      )}

      {/* HUD overlay */}
      {overlayVisible && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
          <div className="flex justify-between items-end">
            <span className="text-[10px] text-gray-400 font-mono">{label}</span>
            <span className="text-[10px] text-gray-500 font-mono">
              {new Date().toLocaleString('nb-NO').split(' ').slice(4, 5).join('')} LT
            </span>
          </div>
        </div>
      )}

      {/* Live indicator */}
      {hasUrl && !errored && (
        <div className="absolute top-2 left-2 flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] text-red-400 font-medium">LIVE</span>
        </div>
      )}
    </div>
  );
}
