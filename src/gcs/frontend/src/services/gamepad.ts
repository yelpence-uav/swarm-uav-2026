/**
 * Browser Gamepad API'den joystick okuma - Görev 2 için.
 *
 * Standart gamepad layout (Xbox/PS):
 *   axes[0] = sol stick LR  (-1 sol, +1 sağ)
 *   axes[1] = sol stick UD  (-1 yukarı, +1 aşağı)   ← invert et
 *   axes[2] = sağ stick LR
 *   axes[3] = sağ stick UD                          ← invert et
 *   buttons[4] = L1 (sol shoulder)
 *   buttons[5] = R1 (sağ shoulder)  ← deadman önerisi
 *
 * Tipik bağlama (Mode 2):
 *   yaw_cmd       ← sol stick LR
 *   throttle_cmd  ← sol stick UD invert
 *   roll_cmd      ← sağ stick LR
 *   pitch_cmd     ← sağ stick UD invert
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

  swA: boolean;            // SwA (2-pos: Deadman/Safety)
  swB: boolean;            // SwB (2-pos: Mode - false=Movement, true=Maneuver)
  swC: number;             // SwC (3-pos: Formation - 0=Arrowhead, 1=V, 2=Line)
  swD: boolean;            // SwD (2-pos: false=Land, true=Takeoff)
  vrA: number;             // Knob VrA [-1, +1]
  vrB: number;             // Knob VrB [-1, +1]

  deadman_pressed: boolean;     // R1 default
  emergency_button: boolean;    // BACK/SELECT
  raw_axes?: number[];          // Diagnostics raw axes 4..7
  raw_btns?: number[];          // Diagnostics active button indices
  all_axes?: number[];          // Diagnostics full axes array
}

const EMPTY: GamepadFrame = {
  connected: false,
  pad_index: null,
  pad_id: null,
  pitch_cmd: 0,
  roll_cmd: 0,
  yaw_cmd: 0,
  throttle_cmd: 0,
  swA: false,
  swB: false,
  swC: 1,
  swD: false,
  vrA: 0,
  vrB: 0,
  deadman_pressed: false,
  emergency_button: false,
};

function clip(v: number): number {
  if (Math.abs(v) < DEAD_ZONE) return 0;
  return Math.max(-1, Math.min(1, v));
}

/** Aktif ilk gamepad'i okur. Yoksa connected=false döner. */
function applyDeadzone(v: number, dz: number = 0.04): number {
  if (Math.abs(v) < dz) return 0;
  return v > 0 ? (v - dz) / (1 - dz) : (v + dz) / (1 - dz);
}

function normalizeRcAxis(v: number): number {
  // FlySky PPM Dongles output ~ ±0.75 for full physical stick deflection
  const scaled = Math.max(-1, Math.min(1, v / 0.75));
  return applyDeadzone(scaled);
}

export function readGamepad(): GamepadFrame {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (let i = 0; i < pads.length; i++) {
    const p = pads[i];
    if (p && p.connected) {
      const isRcTx = /flysky|opentx|edgetx|radiomaster|taranis|ppm|usb receiver|ppm|transmitter/i.test(p.id);

      let yaw = 0, throttle = 0, roll = 0, pitch = 0;
      if (isRcTx) {
        // FlySky FS-i6X / RC Transmitter USB dongle layout (Mode 2):
        // axes[0] = Roll (Sağ stick LR)
        // axes[1] = Pitch (Sağ stick UD)
        // axes[2] = Throttle (Sol stick UD)
        // axes[3] = Yaw (Sol stick LR)
        roll = normalizeRcAxis(p.axes[0] ?? 0);
        pitch = normalizeRcAxis(p.axes[1] ?? 0);
        throttle = normalizeRcAxis(p.axes[2] ?? 0);
        yaw = normalizeRcAxis(p.axes[3] ?? 0);
      } else {
        // Standard Gamepad (Xbox/PS) layout (Mode 2):
        // axes[0] = Yaw (Sol stick LR)
        // axes[1] = Throttle (Sol stick UD)
        // axes[2] = Roll (Sağ stick LR)
        // axes[3] = Pitch (Sağ stick UD)
        yaw = applyDeadzone(clip(p.axes[0] ?? 0));
        throttle = applyDeadzone(clip(-(p.axes[1] ?? 0)));
        roll = applyDeadzone(clip(p.axes[2] ?? 0));
        pitch = applyDeadzone(clip(-(p.axes[3] ?? 0)));
      }

      // FlySky FS-i6X Dongle Channel Mapping:
      // axes[0] = Roll
      // axes[1] = Pitch
      // axes[2] = Throttle
      // axes[3] = Yaw
      // axes[4] = SwA (2-pos: Deadman / Emniyet)
      // axes[5] = SwC (3-pos: Formasyon Ok Başı / V / Çizgi)
      // axes[6] = SwB (2-pos: Mode Hareket / Manevra)
      // axes[7] = SwD (2-pos: Kalkış / İniş)
      // axes[8] = VrA (Pot A)
      // axes[9] = VrB (Pot B)
      const ax4 = p.axes[4] ?? 0;
      const ax5 = p.axes[5] ?? 0;
      const ax6 = p.axes[6] ?? 0;
      const ax7 = p.axes[7] ?? 0;

      // Collect pressed button indices for live diagnostics
      const rawBtns: number[] = [];
      for (let bIdx = 0; bIdx < p.buttons.length; bIdx++) {
        if (p.buttons[bIdx]?.pressed) rawBtns.push(bIdx);
      }

      let swA = true;
      let swB = false;
      let swC = 1;
      let swD = false;
      let deadman = false;

      if (isRcTx) {
        // KUMANDA BUTON HARİTASI (Butonlar önceliklidir):
        // Buton 0 (idx 0) & Buton 1 (idx 1): SwA (Emniyet Kilidi)
        // Buton 2 (idx 2) & Buton 3 (idx 3): SwB (Sürü Modu)
        // Buton 4 (idx 4) & Buton 5 (idx 5): SwC (Formasyon Seçimi) - İkisi de basılı değilse ORTADA (1)
        // Buton 6 (idx 6) & Buton 7 (idx 7): SwD (Kalkış / İniş)

        const hasButtons = p.buttons.length >= 6;

        if (hasButtons) {
          // SwA (Emniyet Kilidi): Buton 0 (Yukarı/Kilitli), Buton 1 (Aşağı/Emniyet Açık)
          const isSwaDown = !!p.buttons[1]?.pressed;
          swA = !isSwaDown;
          deadman = isSwaDown;

          // SwB (Sürü Modu): Buton 2 (Yukarı/Movement -> swB=false), Buton 3 (Aşağı/Maneuver -> swB=true)
          swB = !!p.buttons[3]?.pressed;

          // SwC (Formasyon 3-pos): Buton 4 (Yukarı -> 0), Buton 5 (Aşağı -> 2), İkisi de basılı değilse (Ortada -> 1)
          const isSwCTop = !!p.buttons[4]?.pressed;
          const isSwCBot = !!p.buttons[5]?.pressed;

          if (isSwCTop && !isSwCBot) {
            swC = 0; // YUKARIDA = Ok Başı (0)
          } else if (isSwCBot && !isSwCTop) {
            swC = 2; // AŞAĞIDA = Çizgi (2)
          } else {
            swC = 1; // İKİSİ DE DEĞİLSE / ORTADA = V Formasyonu (1)
          }

          // SwD (Kalkış / İniş): Buton 6 (Yukarı/İniş -> swD=false), Buton 7 (Aşağı/Kalkış -> swD=true)
          swD = !!p.buttons[7]?.pressed;
        } else {
          // Eksen Tabanlı Yedek Kontrol (Axes Fallback)
          const isSwaDown = ax4 > 0.2;
          swA = !isSwaDown;
          deadman = isSwaDown;
          swB = ax6 > 0.2;
          if (ax5 < -0.2) swC = 0;
          else if (ax5 > 0.2) swC = 2;
          else swC = 1;
          swD = ax7 > 0.2;
        }
      } else {
        // Standard Xbox/PS Gamepad
        deadman = !!(p.buttons[4]?.pressed || p.buttons[5]?.pressed);
        swA = !deadman;
        swB = ax5 > 0.2;
        swD = !!(p.buttons[2]?.pressed || p.buttons[3]?.pressed);
        if (p.buttons[8]?.pressed) swC = 0;
        else if (p.buttons[9]?.pressed) swC = 2;
        else swC = 1;
      }

      // Collect full axes array for live diagnostics
      const allAxes = Array.from(p.axes).map(v => clip(v));

      // VrA & VrB knobs (Potentiometers): check axes 8/9 first, then 6/7, then 4/5
      const vrA = p.axes[8] !== undefined ? clip(p.axes[8]) : (p.axes[6] !== undefined ? clip(p.axes[6]) : 0);
      const vrB = p.axes[9] !== undefined ? clip(p.axes[9]) : (p.axes[7] !== undefined ? clip(p.axes[7]) : 0);

      const emergency = !!(p.buttons[8]?.pressed || p.buttons[9]?.pressed);

      return {
        connected: true,
        pad_index: i,
        pad_id: p.id,
        yaw_cmd: yaw,
        throttle_cmd: throttle,
        roll_cmd: roll,
        pitch_cmd: pitch,
        swA,
        swB,
        swC,
        swD,
        vrA,
        vrB,
        deadman_pressed: deadman,
        emergency_button: emergency,
        raw_axes: [ax4, ax5, ax6, ax7],
        raw_btns: rawBtns,
        all_axes: allAxes,
      };
    }
  }
  return EMPTY;
}
