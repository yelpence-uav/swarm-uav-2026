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
  speed?: number;
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

/** Uçuş parametreleri — Ayarlar sekmesi + takeoff/goto varsayılanları. */
export interface FlightParams {
  default_altitude_m: number;
  default_speed_ms: number;
  min_nav_altitude_m: number;
}

async function reqJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new CommandFailure(await res.text().catch(() => res.statusText), res.status);
  }
  return res.json();
}

export const params = {
  get: () => reqJson<FlightParams>("/params", "GET"),
  update: (patch: Partial<FlightParams>) => reqJson<FlightParams>("/params", "PUT", patch),
};

export interface RtkResetSonuc {
  status: string;
  action: string;
  kip: string;
  uyari: string;
}

/** RTK baz istasyonu bakımı.
 *
 * reset: u-blox alıcısını yeniden başlatır. Komut seri porta doğrudan
 * gitmez — portun sahibi yki_rtcm_reader.py, komut ona ROS üzerinden
 * iletilir ve UBX-CFG-RST'i o yazar.
 *
 * ⚠️ RTCM akışı birkaç saniye kesilir, uçaklar RTK-FIX düşürür.
 * Havadayken çağırma.
 */
export const rtk = {
  reset: (kip: "sicak" | "ilik" | "soguk" = "sicak") =>
    reqJson<RtkResetSonuc>(`/rtk/reset?kip=${kip}`, "POST"),
};

export interface GunlukKaydi {
  sira: number;
  zaman: number;      // unix epoch (saniye)
  drone_id: number;   // 0 = sistem geneli
  siddet: "info" | "warning" | "critical" | "emergency";
  kod: string;        // event_43, link_timeout, pi_disk ...
  mesaj: string;
}

export interface GunlukCevap {
  kayitlar: GunlukKaydi[];
  son_sira: number;
  aktif: boolean;     // false = arka ucta defter kurulmamis
}

/** Uçuş ve sistem olay defteri.
 *
 * ARTIMLI OKUMA: elindeki en buyuk `sira`yi `sonra` ile geri gonder, yalniz
 * yeni kayitlar doner. Defter binlerce satira ulassa bile her sorgu birkac
 * yuz bayt tasir. `sonra=0` tum defteri (limit kadarini) verir.
 *
 * drone verilirse o drone'un kayitlari + sistem geneli (drone_id=0) doner;
 * "Pi diski doldu" o drone'u ilgilendirir, ayri sekmede aranmamali.
 */
export const gunluk = {
  oku: (opts?: {
    drone?: number;
    minSiddet?: string;
    sonra?: number;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (opts?.drone !== undefined) q.set("drone", String(opts.drone));
    if (opts?.minSiddet) q.set("min_siddet", opts.minSiddet);
    if (opts?.sonra) q.set("sonra", String(opts.sonra));
    if (opts?.limit) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return reqJson<GunlukCevap>(`/loglar${qs ? "?" + qs : ""}`, "GET");
  },
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

// Mission + Swarm Control endpoint'leri

export const MISSION_ID = {
  DYNAMIC_SWARM: 1,         // Görev 1
  SEMI_AUTONOMOUS: 2,       // Görev 2
  // TEST: yarismada YOK. Gecici saha testlerini YKI'den koşturmak icin
  // ayrilmis slot (29 Agustos 2026, operator). Su an HENUZ BAGLI DEGIL —
  // neyi tetikleyecegi kararlasinca burasi ve MissionPanel doldurulacak.
  // 90+ araligi bilerek: sartnamedeki gorev kimlikleriyle carpismasin.
  TEST: 90,
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

// --- Kanit ucusu kosucusu (gorev_kanit_ucus.py) -----------------------------
// NOT (29 Agustos 2026): YKI'deki KosucuPanel karti operator istegiyle
// KALDIRILDI, ama bu istemci BILEREK duruyor — KARAR-11 test merdiveni
// adim 1 "kosucu `manevra` senaryosu + panel butonu" istiyor, yani gunler
// icinde geri gelecek. Arka uctaki /api/kosucu ucu da yerinde.
// Kartin kendisi: `git show 38c0f3f:src/gcs/frontend/src/components/KosucuPanel/KosucuPanel.tsx`
// Backend bu betigi ayri bir surec olarak calistiriyor; buradan yalnizca
// baslat / durdur / durum sorulur. Durdur = SIGINT = ucaklar INER.

export interface KosucuVarsayilan {
  senaryo: string;
  dronelar: string;
  lider: number;
}

export interface KosucuDurum {
  varsayilan?: KosucuVarsayilan;
  calisiyor: boolean;
  kuru: boolean;
  durduruluyor: boolean;
  komut: string;
  gecen_s: number;
  cikis_kodu: number | null;
  satirlar: string[];
  mesaj?: string;
}

export interface KosucuBaslatBody {
  senaryo?: string;
  dronelar?: string;
  lider?: number;
  kuru: boolean;
  kacinma?: boolean;
  harita?: boolean;
}

export const kosucuApi = {
  /**
   * FİLO VARSAYILANLARI BİLEREK BURADA YOK — verilmeyen alan hiç
   * gönderilmez, backend kendi varsayılanını uygular (kosucu.py BaslatBody).
   *
   * 2 AĞUSTOS: burada `dronelar ?? "2,3"` ve `lider ?? 2` sabitlenmişti.
   * Filo 1,3'e döndüğünde backend güncellendi ama BU SATIRLAR onu eziyordu:
   * düğmeye basınca görev düşmüş olan d2'yi çağırıp ön kontrolde patlıyordu.
   * Aynı bilgi iki yerde durduğu için biri güncellenip diğeri unutulmuştu.
   * Tek kaynak backend olsun diye alanlar koşullu gönderiliyor.
   */
  baslat: (body: KosucuBaslatBody) =>
    postJson<KosucuDurum>(`/kosucu/baslat`, {
      ...(body.senaryo !== undefined && { senaryo: body.senaryo }),
      ...(body.dronelar !== undefined && { dronelar: body.dronelar }),
      ...(body.lider !== undefined && { lider: body.lider }),
      kuru: body.kuru,
      ...(body.kacinma !== undefined && { kacinma: body.kacinma }),
      ...(body.harita !== undefined && { harita: body.harita }),
    }),

  durdur: () => postJson<KosucuDurum>(`/kosucu/durdur`, {}),

  durum: async (satir = 60): Promise<KosucuDurum> => {
    const r = await fetch(`${API_BASE}/kosucu/durum?satir=${satir}`);
    if (!r.ok) throw new Error(`kosucu/durum HTTP ${r.status}`);
    return (await r.json()) as KosucuDurum;
  },
};

// --- RPi anlik durumu (YALNIZ SSH) ------------------------------------------
// 🔴 Bu veri MESH'TEN GECMEZ (operator karari, 29 Agustos 2026). Arka uc her
// istekte SSH ile olcuyor; SSH yoksa `ssh_ok:false` doner ve arayuz "bilinmiyor"
// gosterir. Deger UYDURULMAZ, bayat deger de gosterilmez.
export interface RpiDurum {
  drone_id: number;
  ad?: string;
  ssh_ok: boolean;
  hata?: string;
  zaman?: number;
  degerler: Record<string, number | string>;
}

export const rpi = {
  /** Tek drone'un Pi saglik degerleri. SSH round-trip: tipik 1-3 sn. */
  oku: (droneId: number) => reqJson<RpiDurum>(`/rpi/${droneId}`, "GET"),
};
