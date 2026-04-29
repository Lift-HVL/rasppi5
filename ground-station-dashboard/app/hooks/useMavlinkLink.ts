import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface MavlinkLinkSettings {
  wsBridgeUrl: string;
  transport: 'serial' | 'udp' | 'tcp';
  serialPort: string;
  baudRate: number;
  udpHost: string;
  udpPort: number;
  tcpHost: string;
  tcpPort: number;
  heartbeatTimeoutMs: number;
  reconnectIntervalMs: number;
}

export interface MavlinkLinkStatus {
  connected: boolean;
  source: string;
  lastHeartbeatMs: number;
  heartbeatAgeMs: number;
  rxRateHz: number;
  txRateHz: number | null;
  packetLossPct: number | null;
  lastError: string | null;
  lastCommand: string | null;
}

export interface MavlinkValidationResult {
  ok: boolean;
  errors: string[];
}

type BridgePayload = {
  connected?: boolean;
  timestamp?: number;
  link_source?: string;
  source?: string;
  link_packet_loss_pct?: number;
  packet_loss_pct?: number;
  link_rx_rate_hz?: number;
  rx_rate_hz?: number;
  link_tx_rate_hz?: number;
  tx_rate_hz?: number;
};

function describeClose(code: number, reason: string, wasClean: boolean): string {
  const trimmedReason = reason.trim();
  if (trimmedReason) return `Bridge socket closed (${code}): ${trimmedReason}`;
  if (code === 1000 && wasClean) return 'Bridge socket closed.';
  if (code === 1006) return 'Bridge socket closed abnormally (1006). Check bridge URL, network, and backend WS server.';
  return `Bridge socket closed (${code}).`;
}

const EMPTY_STATUS: MavlinkLinkStatus = {
  connected: false,
  source: '-',
  lastHeartbeatMs: 0,
  heartbeatAgeMs: 0,
  rxRateHz: 0,
  txRateHz: null,
  packetLossPct: null,
  lastError: null,
  lastCommand: null,
};

const ALLOWED_BAUD_RATES = new Set([9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]);

function isPortValid(port: number): boolean {
  return Number.isInteger(port) && port >= 1 && port <= 65535;
}

function hasHost(value: string): boolean {
  return value.trim().length > 0;
}

function validateWsUrl(wsBridgeUrl: string): boolean {
  if (!wsBridgeUrl.trim()) return false;
  try {
    const parsed = new URL(wsBridgeUrl);
    return parsed.protocol === 'ws:' || parsed.protocol === 'wss:';
  } catch {
    return false;
  }
}

export function validateMavlinkSettings(cfg: MavlinkLinkSettings): MavlinkValidationResult {
  const errors: string[] = [];

  if (!validateWsUrl(cfg.wsBridgeUrl)) {
    errors.push('Bridge URL must be a valid ws:// or wss:// URL.');
  }

  if (cfg.transport === 'serial') {
    if (!cfg.serialPort.trim()) errors.push('Serial port is required for serial transport.');
    if (!ALLOWED_BAUD_RATES.has(cfg.baudRate)) {
      errors.push('Baud rate must be one of: 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600.');
    }
  }

  if (cfg.transport === 'udp') {
    if (!hasHost(cfg.udpHost)) errors.push('UDP host is required for UDP transport.');
    if (!isPortValid(cfg.udpPort)) errors.push('UDP port must be between 1 and 65535.');
  }

  if (cfg.transport === 'tcp') {
    if (!hasHost(cfg.tcpHost)) errors.push('TCP host is required for TCP transport.');
    if (!isPortValid(cfg.tcpPort)) errors.push('TCP port must be between 1 and 65535.');
  }

  if (!Number.isInteger(cfg.heartbeatTimeoutMs) || cfg.heartbeatTimeoutMs < 500 || cfg.heartbeatTimeoutMs > 30000) {
    errors.push('Heartbeat timeout must be an integer from 500 to 30000 ms.');
  }

  if (!Number.isInteger(cfg.reconnectIntervalMs) || cfg.reconnectIntervalMs < 200 || cfg.reconnectIntervalMs > 30000) {
    errors.push('Reconnect interval must be an integer from 200 to 30000 ms.');
  }

  return { ok: errors.length === 0, errors };
}

function extractStatusPatch(payload: BridgePayload): Partial<MavlinkLinkStatus> {
  const patch: Partial<MavlinkLinkStatus> = {};

  if (payload.connected != null) patch.connected = payload.connected;

  if (payload.timestamp != null) {
    patch.lastHeartbeatMs = payload.timestamp * 1000;
  }

  const source = payload.link_source ?? payload.source;
  if (typeof source === 'string' && source.trim()) patch.source = source;

  const packetLoss = payload.link_packet_loss_pct ?? payload.packet_loss_pct;
  if (typeof packetLoss === 'number') patch.packetLossPct = packetLoss;

  const rxRate = payload.link_rx_rate_hz ?? payload.rx_rate_hz;
  if (typeof rxRate === 'number') patch.rxRateHz = rxRate;

  const txRate = payload.link_tx_rate_hz ?? payload.tx_rate_hz;
  if (typeof txRate === 'number') patch.txRateHz = txRate;

  return patch;
}

export function useMavlinkLink(bridgeUrl?: string) {
  const [status, setStatus] = useState<MavlinkLinkStatus>(EMPTY_STATUS);
  const [busy, setBusy] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const messageCountRef = useRef(0);
  const previousCountRef = useRef(0);
  const stoppedRef = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setStatus(prev => {
        const now = Date.now();
        const sampledRate = messageCountRef.current - previousCountRef.current;
        previousCountRef.current = messageCountRef.current;
        return {
          ...prev,
          heartbeatAgeMs: prev.lastHeartbeatMs ? Math.max(0, now - prev.lastHeartbeatMs) : 0,
          rxRateHz: prev.rxRateHz > 0 ? prev.rxRateHz : sampledRate,
        };
      });
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const connectStatusSocket = useCallback(() => {
    if (!bridgeUrl || stoppedRef.current) return;
    clearTimeout(reconnectRef.current);

    try {
      const ws = new WebSocket(bridgeUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus(prev => ({ ...prev, connected: true, lastError: null }));
      };

      ws.onmessage = event => {
        messageCountRef.current += 1;
        try {
          const payload = JSON.parse(event.data as string) as BridgePayload;
          setStatus(prev => ({ ...prev, ...extractStatusPatch(payload), connected: true, lastError: null }));
        } catch {
          setStatus(prev => ({ ...prev, connected: true }));
        }
      };

      ws.onerror = () => {
        setStatus(prev => ({
          ...prev,
          connected: false,
          lastError: 'Bridge socket error. Check bridge URL, network reachability, and WS backend availability.',
        }));
      };

      ws.onclose = event => {
        if (wsRef.current === ws) wsRef.current = null;
        setStatus(prev => ({ ...prev, connected: false }));
        if (stoppedRef.current) return;
        setStatus(prev => ({ ...prev, lastError: describeClose(event.code, event.reason, event.wasClean) }));
        reconnectRef.current = setTimeout(connectStatusSocket, 3000);
      };
    } catch {
      setStatus(prev => ({ ...prev, connected: false, lastError: 'Failed to open bridge socket.' }));
      reconnectRef.current = setTimeout(connectStatusSocket, 5000);
    }
  }, [bridgeUrl]);

  useEffect(() => {
    stoppedRef.current = false;
    if (!bridgeUrl) {
      setStatus(EMPTY_STATUS);
      return;
    }

    connectStatusSocket();

    return () => {
      stoppedRef.current = true;
      clearTimeout(reconnectRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [bridgeUrl, connectStatusSocket]);

  const sendViaWebSocket = useCallback(async (action: string, config?: MavlinkLinkSettings): Promise<void> => {
    if (!bridgeUrl) {
      throw new Error('No bridge URL configured.');
    }

    await new Promise<void>((resolve, reject) => {
      let finished = false;
      let commandSocket: WebSocket | null = null;

      const done = (fn: () => void) => {
        if (finished) return;
        finished = true;
        fn();
      };

      try {
        commandSocket = new WebSocket(bridgeUrl);
      } catch {
        reject(new Error('Failed to open command socket.'));
        return;
      }

      const timeout = setTimeout(() => {
        done(() => {
          commandSocket?.close();
          reject(new Error('Command socket timeout.'));
        });
      }, 2500);

      commandSocket.onopen = () => {
        try {
          commandSocket?.send(JSON.stringify({ type: 'mavlink_link_command', action, config }));
          done(() => {
            clearTimeout(timeout);
            commandSocket?.close();
            resolve();
          });
        } catch {
          done(() => {
            clearTimeout(timeout);
            commandSocket?.close();
            reject(new Error('Failed to send command.'));
          });
        }
      };

      commandSocket.onerror = () => {
        done(() => {
          clearTimeout(timeout);
          commandSocket?.close();
          reject(new Error('Command socket error.'));
        });
      };
    });
  }, [bridgeUrl]);

  const command = useCallback(async (action: 'apply' | 'connect' | 'disconnect' | 'test', config?: MavlinkLinkSettings) => {
    setBusy(true);
    setStatus(prev => ({ ...prev, lastCommand: action, lastError: null }));

    try {
      const response = await fetch(`/api/mavlink/link/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config ? { config } : {}),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
    } catch {
      await sendViaWebSocket(action, config);
    } finally {
      setBusy(false);
    }
  }, [sendViaWebSocket]);

  const formatted = useMemo(() => {
    return {
      heartbeatAgeLabel: status.lastHeartbeatMs ? `${(status.heartbeatAgeMs / 1000).toFixed(1)} s` : '-',
      rxRateLabel: `${status.rxRateHz.toFixed(1)} Hz`,
      txRateLabel: status.txRateHz == null ? '-' : `${status.txRateHz.toFixed(1)} Hz`,
      packetLossLabel: status.packetLossPct == null ? '-' : `${status.packetLossPct.toFixed(1)}%`,
    };
  }, [status.heartbeatAgeMs, status.lastHeartbeatMs, status.packetLossPct, status.rxRateHz, status.txRateHz]);

  return {
    busy,
    status,
    formatted,
    applyConfig: (config: MavlinkLinkSettings) => command('apply', config),
    connect: (config?: MavlinkLinkSettings) => command('connect', config),
    disconnect: () => command('disconnect'),
    testLink: (config?: MavlinkLinkSettings) => command('test', config),
  };
}
