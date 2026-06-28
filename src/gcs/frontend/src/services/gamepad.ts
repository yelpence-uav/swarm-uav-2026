/**
 * Browser Gamepad API'den joystick okuma — Görev 2 için.
 *
 * Standart gamepad layout (Xbox/PS):
 *   axes[0] = sol stick LR  (-1 sol, +1 sağ)
 *   axes[1] = sol stick UD  (-1 yukarı, +1 aşağı)   ← invert et
 *   axes[2] = sağ stick LR
 *   axes[3] = sağ stick UD                          ← invert et
 *   buttons[4] = L1 (sol shoulder)
 *   buttons[5] = R1 (sağ shoulder)  ← deadman önerisi
 *
 * Tipik bağlama:
 *   pitch_cmd     ← sol stick UD invert
 *   roll_cmd      ← sol stick LR
 *   yaw_cmd       ← sağ stick LR
 *   throttle_cmd  ← sağ stick UD invert
 *   deadman       ← R1
 */

const DEAD_ZONE = 0.08;

export interface GamepadFrame {
  connected: boolean;
  pad_index: number | null;
  pad_id: string | null;

  pitch_cmd: number;       // [-1, +1]
  roll_cmd: number;
  yaw_cmd: number;
  throttle_cmd: number;

  deadman_pressed: boolean;     // R1 default
  emergency_button: boolean;    // BACK/SELECT
}

const EMPTY: GamepadFrame = {
  connected: false,
  pad_index: null,
  pad_id: null,
  pitch_cmd: 0,
  roll_cmd: 0,
  yaw_cmd: 0,
  throttle_cmd: 0,
  deadman_pressed: false,
  emergency_button: false,
};

function clip(v: number): number {
  if (Math.abs(v) < DEAD_ZONE) return 0;
  return Math.max(-1, Math.min(1, v));
}

/** Aktif ilk gamepad'i okur. Yoksa connected=false döner. */
export function readGamepad(): GamepadFrame {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (let i = 0; i < pads.length; i++) {
    const p = pads[i];
    if (p && p.connected) {
      return {
        connected: true,
        pad_index: i,
        pad_id: p.id,
        roll_cmd: clip(p.axes[0] ?? 0),
        pitch_cmd: clip(-(p.axes[1] ?? 0)),       // invert
        yaw_cmd: clip(p.axes[2] ?? 0),
        throttle_cmd: clip(-(p.axes[3] ?? 0)),    // invert
        deadman_pressed: !!(p.buttons[5]?.pressed),  // R1
        emergency_button: !!(p.buttons[8]?.pressed), // BACK/SELECT
      };
    }
  }
  return EMPTY;
}
