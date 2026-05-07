export interface DroneState {
  drone_id: number;
  name: string;
  sysid: number;

  connected: boolean;
  last_message_time: number;

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
}

export type AlertSeverity = "info" | "warning" | "critical";

export interface Alert {
  drone_id: number;
  severity: AlertSeverity;
  code: string;
  message: string;
  timestamp: number;
}

export interface TelemetryPayload {
  drones: DroneState[];
  alerts: Alert[];
}
