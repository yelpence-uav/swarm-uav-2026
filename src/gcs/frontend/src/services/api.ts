/**
 * Backend REST komut endpoint'leri için ince wrapper.
 * WebSocket telemetri akışı `services/websocket.ts`'te ayrıdır.
 */

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  `http://${window.location.hostname}:8000/api`;

export type CommandAction =
  | "takeoff"
  | "land"
  | "rtl"
  | "loiter"
  | "arm"
  | "disarm";

export interface CommandResult {
  status: "queued" | "partial";
  drone_id?: number;
  action: string;
  submitted?: number[];
  failed?: number[];
}

export interface CommandError {
  status: "error";
  message: string;
  http_status?: number;
}

async function postCommand(
  path: string,
  query?: Record<string, string | number | boolean>,
): Promise<CommandResult> {
  const url = new URL(`${API_BASE}${path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString(), { method: "POST" });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new CommandFailure(text || res.statusText, res.status);
  }
  return res.json();
}

export class CommandFailure extends Error {
  http_status: number;
  constructor(msg: string, status: number) {
    super(msg);
    this.http_status = status;
  }
}

export const api = {
  takeoff: (droneId: number, altitude?: number) =>
    postCommand(
      `/command/${droneId}/takeoff`,
      altitude !== undefined ? { altitude } : undefined,
    ),
  land: (droneId: number) => postCommand(`/command/${droneId}/land`),
  rtl: (droneId: number) => postCommand(`/command/${droneId}/rtl`),
  loiter: (droneId: number) => postCommand(`/command/${droneId}/loiter`),
  arm: (droneId: number, force = false) =>
    postCommand(`/command/${droneId}/arm`, force ? { force: true } : undefined),
  disarm: (droneId: number, force = false) =>
    postCommand(
      `/command/${droneId}/disarm`,
      force ? { force: true } : undefined,
    ),

  // Bulk
  takeoffAll: (altitude?: number) =>
    postCommand(
      `/command/all/takeoff`,
      altitude !== undefined ? { altitude } : undefined,
    ),
  landAll: () => postCommand(`/command/all/land`),
  rtlAll: () => postCommand(`/command/all/rtl`),
  disarmAll: (force = false) =>
    postCommand(`/command/all/disarm`, force ? { force: true } : undefined),
};
