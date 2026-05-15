/**
 * Backend WebSocket payload tipleri.
 *
 * DroneState alanları backend/core/state_store.py ile birebir uyumlu olmalı.
 * SwarmState alanları backend/connections/ros_bridge.py:swarm_state_to_dict ile.
 * Enum sabitleri swarm_interfaces .msg dosyalarından kopyalanır — kontrat
 * değişirse buradaki sabitler de güncellenmeli.
 */

// --- DroneState ---------------------------------------------------------------

export interface DroneState {
  drone_id: number;
  name: string;
  sysid: number;

  connected: boolean;
  last_message_time: number;

  // Faz 1-4 alanları (UI hâlâ bunları gösterir)
  armed: boolean;
  mode: string;

  lat: number;
  lon: number;
  alt_m: number;

  battery_percent: number;
  battery_voltage: number;

  gps_fix_type: number;
  gps_satellites: number;

  groundspeed_mps: number;
  yaw_deg: number;

  // Faz 5: AgentStatus zenginliği
  state: number;            // STATE_* enum (16 değer)
  role: number;             // ROLE_* enum (LEADER/FOLLOWER/STANDBY/DETACHED)
  flight_mode: number;      // FLIGHT_MODE_* enum (PX4 nav_state karşılığı)

  offboard_active: boolean;
  pilot_override_active: boolean;
  failsafe_active: boolean;
  healthy: boolean;

  pos_x: number;
  pos_y: number;
  pos_z: number;            // negatif = yukarı (NED)
  vel_x: number;
  vel_y: number;
  vel_z: number;

  roll_deg: number;
  pitch_deg: number;

  battery_current_a: number;
  gps_hdop: number;

  home_set: boolean;
  home_lat: number;
  home_lon: number;
  home_alt_amsl_m: number;

  imu_healthy: boolean;
  mag_healthy: boolean;
  baro_healthy: boolean;
  estimator_ok: boolean;
  xy_valid: boolean;
  z_valid: boolean;
  v_xy_valid: boolean;

  origin_synced: boolean;

  rc_link_ok: boolean;
  kill_switch_active: boolean;
  rc_signal_failsafe_active: boolean;

  oscillation_detected: boolean;
  unstable_flight: boolean;

  status_text: string;
}

// --- AgentStatus.STATE_* enum ------------------------------------------------

export const AGENT_STATE_LABELS: Record<number, string> = {
  0: "Bilinmiyor",
  1: "Boşta",
  2: "Arming",
  3: "Armed",
  4: "Kalkış",
  5: "Sürüde",
  6: "Görev İcra",
  7: "Ayrıldı",
  8: "Hassas İniş",
  9: "Yeniden Katılma Bekleniyor",
  10: "Sürüye Katılıyor",
  11: "Eve Dönüş",
  12: "İniş",
  13: "İndi",
  14: "Failsafe",
  15: "Standby",
};

export const AGENT_ROLE_LABELS: Record<number, string> = {
  0: "?",
  1: "Lider",
  2: "Takipçi",
  3: "Yedek",
  4: "Ayrılmış",
};

// --- SwarmState (global sürü durumu) -----------------------------------------

export interface SwarmState {
  swarm_state: number;         // SWARM_* enum
  leader_id: number;
  active_agent_count: number;
  active_formation: number;    // FORMATION_* enum

  mission_active: boolean;
  formation_reached: boolean;
  formation_stable: boolean;
  emergency_active: boolean;

  centroid: [number, number, number];  // NED
  formation_heading_deg: number;
  formation_max_error_m: number;
  formation_avg_error_m: number;
  formation_heading_error_deg: number;

  active_mission: string;
  status_text: string;

  current_qr_id: number;
  current_qr_seq: number;

  last_event: {
    type: number;
    severity: number;
    source: number;
    value: number;
    message: string;
  };
}

export const SWARM_STATE_LABELS: Record<number, string> = {
  0: "Bilinmiyor",
  1: "Boşta",
  2: "Formasyon Kuruluyor",
  3: "Navigasyon",
  4: "Görev İcra",
  5: "Rotasyon",
  6: "İniş",
  7: "Eve Dönüş",
  8: "Failsafe",
  9: "Görev Tamamlandı",
};

export const FORMATION_LABELS: Record<number, string> = {
  0: "?",
  1: "Ok Başı",
  2: "V",
  3: "Çizgi",
  99: "Özel",
};

// --- Alert (mevcut AlertManager + SystemEvent köprüsü) -----------------------

export type AlertSeverity = "info" | "warning" | "critical";

export interface Alert {
  drone_id: number;
  severity: AlertSeverity;
  code: string;
  message: string;
  timestamp: number;
}

// --- WebSocket payload --------------------------------------------------------

export interface TelemetryPayload {
  drones: DroneState[];
  alerts: Alert[];
  swarm_state: SwarmState | null;   // mavlink-sim modunda veya henüz mesaj gelmediyse null
}
