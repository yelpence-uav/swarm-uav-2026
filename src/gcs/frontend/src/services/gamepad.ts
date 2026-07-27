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

      let swA = false;
      let swB = false;
      let swC = 1;
      let swD = false;

      if (isRcTx) {
        swA = ax4 > 0.0;
        swB = ax5 > 0.2; // Varsayılan SwB
        swC = 1;         // Varsayılan V
        swD = !!(p.buttons[2]?.pressed || p.buttons[3]?.pressed); // Varsayılan SwD

        // SwC (Formasyon 3-pos): 
        // Fiziksel ALT (Buton 0/8) -> 2 (ÇİZGİ)
        // Fiziksel ÜST (Buton 1/9) -> 1 (V FORMASYONU)
        // Fiziksel ORTA (Nötr / Hiçbiri) -> 0 (OK BAŞI)
        if (p.buttons[0]?.pressed || p.buttons[8]?.pressed) {
          swC = 2; // ALT = Çizgi
        } else if (p.buttons[1]?.pressed || p.buttons[9]?.pressed) {
          swC = 1; // ÜST = V Formasyonu
        } else {
          swC = 0; // ORTA = Ok Başı
        }

        // TÜM ŞALTERLER İÇİN İNTERAKTİF ÖĞRENİLMİŞ DONANIM HARİTASI
        try {
          // SwA (Emniyet)
          const aType = localStorage.getItem('rc_mapping_swA_type');
          const aIdx = Number(localStorage.getItem('rc_mapping_swA_idx') ?? -1);
          if (aType === 'axis' && aIdx >= 0) {
            swA = (p.axes[aIdx] ?? 0) > 0.2;
          } else if (aType === 'btn' && aIdx >= 0) {
            swA = !!p.buttons[aIdx]?.pressed;
          }

          // SwB (Mod)
          const bType = localStorage.getItem('rc_mapping_swB_type');
          const bIdx = Number(localStorage.getItem('rc_mapping_swB_idx') ?? -1);
          if (bType === 'axis' && bIdx >= 0) {
            swB = (p.axes[bIdx] ?? 0) > 0.2;
          } else if (bType === 'btn' && bIdx >= 0) {
            swB = !!p.buttons[bIdx]?.pressed;
          }

          // SwC (Formasyon)
          const cType = localStorage.getItem('rc_mapping_swC_type');
          const cIdx1 = Number(localStorage.getItem('rc_mapping_swC_idx1') ?? -1);
          const cIdx2 = Number(localStorage.getItem('rc_mapping_swC_idx2') ?? -1);
          if (cType === 'btn' && cIdx1 >= 0 && cIdx2 >= 0) {
            if (p.buttons[cIdx1]?.pressed) swC = 0;       // ORTA = Ok Başı
            else if (p.buttons[cIdx2]?.pressed) swC = 2;  // ALT = Çizgi
            else swC = 1;                                 // ÜST = V
          } else if (cType === 'axis' && cIdx1 >= 0) {
            const axVal = p.axes[cIdx1] ?? 0;
            if (axVal > -0.3 && axVal < 0.3) swC = 0;     // ORTA = Ok Başı
            else if (axVal > 0.3) swC = 2;                 // ALT = Çizgi
            else swC = 1;                                 // ÜST = V
          }

          // SwD (Kalkış/İniş)
          const dType = localStorage.getItem('rc_mapping_swD_type');
          const dIdx = Number(localStorage.getItem('rc_mapping_swD_idx') ?? -1);
          if (dType === 'axis' && dIdx >= 0) {
            swD = (p.axes[dIdx] ?? 0) > 0.2;
          } else if (dType === 'btn' && dIdx >= 0) {
            swD = !!p.buttons[dIdx]?.pressed;
          }
        } catch (_) {}
      } else {
        // Standard Xbox/PS Gamepad button mapping
        swA = !!(p.buttons[0]?.pressed || p.buttons[4]?.pressed);
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

      const deadman = swA;
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
