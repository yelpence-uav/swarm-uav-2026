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

/** Nokta-git hedefi: manuel NED (x/y/z, z=irtifa↑) VEYA harita/GPS (lat/lon/alt). */
export interface GotoTarget {
  x?: number;
  y?: number;
  z?: number;
  lat?: number;
  lon?: number;
  alt?: number;
  heading_deg?: number;
}

/**
 * Guided (tekil drone) uçuş komutları — ESP mesh üzerinden (connection_mode=ros2).
 * arm/takeoff/goto/rtl/land. Otonom görevden bağımsız operatör kontrolü.
 */
export const guided = {
  arm: (droneId: number) => postCommand(`/guided/${droneId}/arm`),
  disarm: (droneId: number) => postCommand(`/guided/${droneId}/disarm`),
  takeoff: (droneId: number, altitude: number) =>
    postCommand(`/guided/${droneId}/takeoff`, { altitude }),
  rtl: (droneId: number) => postCommand(`/guided/${droneId}/rtl`),
  land: (droneId: number) => postCommand(`/guided/${droneId}/land`),
  goto: (droneId: number, target: GotoTarget) =>
    postJson<CommandResult>(`/guided/${droneId}/goto`, target),
};

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

// --- Faz 5: Mission + Swarm Control endpoint'leri ----------------------------

export const MISSION_ID = {
  DYNAMIC_SWARM: 1,         // Görev 1
  SEMI_AUTONOMOUS: 2,       // Görev 2
} as const;

export const MISSION_COMMAND = {
  START: 1,
  ABORT: 2,
  PAUSE: 3,
  RESUME: 4,
  RTL: 5,
  LAND: 6,
} as const;

export interface TriggerMissionRequest {
  mission_id: number;
  command: number;
  team_id: string;
  parameters_json?: string;
}

export interface TriggerMissionResponse {
  success: boolean;
  message: string;
  mission_id: number;
  command: number;
}

export const SWARM_CONTROL_MODE = {
  UNKNOWN: 0,
  SWARM_MOVEMENT: 1,
  MANEUVER: 2,
} as const;

export const SWARM_FORMATION = {
  UNKNOWN: 0,
  OKBASI: 1,
  V: 2,
  CIZGI: 3,
} as const;

export interface SwarmControlBody {
  sequence_num: number;
  command_valid: boolean;
  deadman_pressed: boolean;
  deadman_timeout_s?: number;
  mode: number;
  pitch_cmd: number;
  roll_cmd: number;
  yaw_cmd: number;
  throttle_cmd: number;
  takeoff?: boolean;
  land?: boolean;
  rtl?: boolean;
  emergency_stop?: boolean;
  formation_change_requested?: boolean;
  requested_formation?: number;
  requested_spacing_m?: number;
  duration_s?: number;
  max_speed_mps?: number;
  max_yaw_rate_deg_s?: number;
  max_tilt_deg?: number;
  source_module?: string;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new CommandFailure(text || res.statusText, res.status);
  }
  return res.json() as Promise<T>;
}

export interface QRCoordsRequest {
  qr_ids: number[];
  lat_deg: number[];
  lon_deg: number[];
}

export interface QRCoordsResponse {
  published: boolean;
  count: number;
}

export const missionApi = {
  trigger: (req: TriggerMissionRequest) =>
    postJson<TriggerMissionResponse>(`/mission/trigger`, {
      mission_id: req.mission_id,
      command: req.command,
      team_id: req.team_id,
      parameters_json: req.parameters_json ?? "",
    }),

  // QR konum tablosunu sürüye gönder (latched). Paralel diziler eşit uzunlukta.
  sendQrCoords: (req: QRCoordsRequest) =>
    postJson<QRCoordsResponse>(`/mission/qr_coords`, req),
};

export const swarmApi = {
  control: (body: SwarmControlBody) =>
    postJson<{ published: boolean; sequence_num: number }>(
      `/swarm/control`,
      body,
    ),
};
