import { useState, useCallback } from 'react';

export interface GroundStationSettings {
  videoUrl: string;
  maxAltitude: number;
  maxSpeed: number;
  takeoffAltitude: number;
  geofenceRadius: number;
  rtlAltitude: number;
  units: 'metric' | 'imperial';
  coordFormat: 'decimal' | 'dms';
  batteryWarnPercent: number;
  batteryCriticalPercent: number;
  rssiWarnDbm: number;
  minSatellites: number;
  rtlOnSignalLoss: boolean;
  rtlOnLowBattery: boolean;
  geofenceEnabled: boolean;
  geofenceAction: 'warn' | 'rtl' | 'land';
}

export const DEFAULT_SETTINGS: GroundStationSettings = {
  videoUrl: '',
  maxAltitude: 120,
  maxSpeed: 15,
  takeoffAltitude: 10,
  geofenceRadius: 500,
  rtlAltitude: 50,
  units: 'metric',
  coordFormat: 'decimal',
  batteryWarnPercent: 20,
  batteryCriticalPercent: 10,
  rssiWarnDbm: -80,
  minSatellites: 6,
  rtlOnSignalLoss: true,
  rtlOnLowBattery: true,
  geofenceEnabled: true,
  geofenceAction: 'rtl',
};

const STORAGE_KEY = 'lift-hvl-gs-settings';

function loadSettings(): GroundStationSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<GroundStationSettings>) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function useSettings() {
  const [settings, setSettingsState] = useState<GroundStationSettings>(loadSettings);

  const persistSettings = useCallback((next: GroundStationSettings) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
  }, []);

  const updateSettings = useCallback((partial: Partial<GroundStationSettings>) => {
    setSettingsState(prev => {
      const next = { ...prev, ...partial };
      persistSettings(next);
      return next;
    });
  }, [persistSettings]);

  const replaceSettings = useCallback((next: GroundStationSettings) => {
    setSettingsState(next);
    persistSettings(next);
  }, [persistSettings]);

  const resetSettings = useCallback(() => {
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
    setSettingsState(DEFAULT_SETTINGS);
  }, []);

  return { settings, updateSettings, replaceSettings, resetSettings };
}
