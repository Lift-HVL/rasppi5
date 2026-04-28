import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useVehicleState } from '~/hooks/useVehicleState';
import { useSettings } from '~/hooks/useSettings';

const DEFAULT_CENTER: [number, number] = [60.37, 5.33]; // Bergen, Norway

function droneIcon(heading: number) {
  return L.divIcon({
    html: `
      <div style="width:28px;height:28px;transform:rotate(${heading}deg);transform-origin:center;display:flex;align-items:center;justify-content:center;">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <polygon points="14,2 22,26 14,20 6,26" fill="#22c55e" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      </div>`,
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function homeIcon() {
  return L.divIcon({
    html: `
      <div style="width:20px;height:20px;display:flex;align-items:center;justify-content:center;">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="10" cy="10" r="8" fill="#facc15" stroke="#fff" stroke-width="2"/>
          <text x="10" y="14" text-anchor="middle" font-size="10" font-family="monospace" fill="#000" font-weight="bold">H</text>
        </svg>
      </div>`,
    className: '',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

function MapController({
  lat, lon, follow,
}: { lat: number; lon: number; follow: boolean }) {
  const map = useMap();
  const firstFix = useRef(false);

  useEffect(() => {
    if (lat === 0 && lon === 0) return;
    if (!firstFix.current) {
      map.setView([lat, lon], 17);
      firstFix.current = true;
    } else if (follow) {
      map.setView([lat, lon]);
    }
  }, [lat, lon, follow, map]);

  return null;
}

const MAX_TRAIL = 600;

export default function MapPage() {
  const vs = useVehicleState();
  const { settings } = useSettings();

  const hasGPS = vs.latitude !== 0 || vs.longitude !== 0;
  const lat = hasGPS ? vs.latitude : DEFAULT_CENTER[0];
  const lon = hasGPS ? vs.longitude : DEFAULT_CENTER[1];

  const [follow, setFollow] = useState(true);
  const [showTrail, setShowTrail] = useState(true);
  const [showGeofence, setShowGeofence] = useState(settings.geofenceEnabled);
  const [trail, setTrail] = useState<[number, number][]>([]);
  const [home, setHome] = useState<[number, number] | null>(null);

  useEffect(() => {
    if (!hasGPS) return;
    if (!home) setHome([lat, lon]);
    setTrail(prev => {
      const last = prev[prev.length - 1];
      if (last && last[0] === lat && last[1] === lon) return prev;
      const next = [...prev, [lat, lon] as [number, number]];
      return next.length > MAX_TRAIL ? next.slice(-MAX_TRAIL) : next;
    });
  }, [lat, lon, hasGPS]);

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] bg-gray-950">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-800 shrink-0 flex-wrap text-xs">
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${vs.connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
          <span className={vs.connected ? 'text-green-400' : 'text-red-400'}>
            {vs.connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>

        <div className="h-4 w-px bg-gray-700" />

        {hasGPS ? (
          <span className="text-gray-300 font-mono">
            {lat.toFixed(6)}°, {lon.toFixed(6)}°
          </span>
        ) : (
          <span className="text-yellow-500">No GPS fix</span>
        )}

        <div className="h-4 w-px bg-gray-700" />
        <span className="text-gray-500">ALT</span>
        <span className="text-gray-200 font-mono">{vs.relativeAltitude.toFixed(1)} m</span>

        <div className="h-4 w-px bg-gray-700" />
        <span className="text-gray-500">HDG</span>
        <span className="text-gray-200 font-mono">{vs.heading.toFixed(0)}°</span>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setShowTrail(v => !v)}
            className={`px-2.5 py-1 rounded border text-xs transition-colors ${
              showTrail
                ? 'border-blue-700 bg-blue-950 text-blue-300'
                : 'border-gray-700 text-gray-500 hover:text-gray-300'
            }`}
          >
            Trail
          </button>
          <button
            onClick={() => setShowGeofence(v => !v)}
            className={`px-2.5 py-1 rounded border text-xs transition-colors ${
              showGeofence
                ? 'border-orange-700 bg-orange-950 text-orange-300'
                : 'border-gray-700 text-gray-500 hover:text-gray-300'
            }`}
          >
            Geofence
          </button>
          <button
            onClick={() => setFollow(v => !v)}
            className={`px-2.5 py-1 rounded border text-xs transition-colors ${
              follow
                ? 'border-green-700 bg-green-950 text-green-300'
                : 'border-gray-700 text-gray-500 hover:text-gray-300'
            }`}
          >
            Follow
          </button>
          <button
            onClick={() => {
              setTrail([]);
              setHome(hasGPS ? [lat, lon] : null);
            }}
            className="px-2.5 py-1 rounded border border-gray-700 text-gray-500 hover:text-gray-300 text-xs transition-colors"
          >
            Clear trail
          </button>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 min-h-0">
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={13}
          className="h-full w-full"
          zoomControl={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <MapController lat={lat} lon={lon} follow={follow} />

          {/* Geofence circle around home */}
          {showGeofence && home && (
            <Circle
              center={home}
              radius={settings.geofenceRadius}
              pathOptions={{ color: '#f97316', weight: 1.5, dashArray: '6 4', fillColor: '#f97316', fillOpacity: 0.04 }}
            />
          )}

          {/* Flight trail */}
          {showTrail && trail.length > 1 && (
            <Polyline
              positions={trail}
              pathOptions={{ color: '#38bdf8', weight: 2, opacity: 0.7 }}
            />
          )}

          {/* Home marker */}
          {home && (
            <Marker position={home} icon={homeIcon()} />
          )}

          {/* Drone marker */}
          {hasGPS && (
            <Marker position={[lat, lon]} icon={droneIcon(vs.heading)} />
          )}
        </MapContainer>
      </div>
    </div>
  );
}
