import type { TelemetryPayload } from "../types/telemetry";

type Listener = (payload: TelemetryPayload) => void;
type StatusListener = (status: ConnectionStatus) => void;

export type ConnectionStatus = "connecting" | "open" | "closed";

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 5000;

export class TelemetryWS {
  private url: string;
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<StatusListener>();
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private stopped = false;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.stopped = false;
    this.openSocket();
  }

  disconnect(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  onMessage(cb: Listener): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  onStatus(cb: StatusListener): () => void {
    this.statusListeners.add(cb);
    return () => this.statusListeners.delete(cb);
  }

  private emitStatus(status: ConnectionStatus): void {
    for (const cb of this.statusListeners) cb(status);
  }

  private openSocket(): void {
    this.emitStatus("connecting");
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.emitStatus("open");
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as TelemetryPayload;
        for (const cb of this.listeners) cb(data);
      } catch (err) {
        console.warn("ws: bozuk JSON", err);
      }
    };

    ws.onclose = () => {
      this.ws = null;
      this.emitStatus("closed");
      if (!this.stopped) this.scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose zaten ardından tetiklenir
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_MS,
    );
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }
}
