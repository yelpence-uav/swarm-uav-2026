"""mode_states.py — Görev 2 yarı otonom kontrol FSM durum sabitleri.

mode_manager_node bu enum'ları kullanarak mevcut durumu izler.
Şartname §5.2 — Yarı Otonom Sürü Kontrolü Görevi.
"""

from enum import IntEnum


class ModeState(IntEnum):
    """mode_manager FSM durum sabitleri.

    IDLE      — Görev 2 henüz başlamadı, mode_manager pasif.
    PREFLIGHT — mission_fsm SEMI_AUTONOMOUS'a geçti, drone kontrolleri.
    TAKEOFF   — Kumandadan kalkış komutu alındı, sürü kalkıyor.
    READY     — Sürü havada, formasyon kuruldu, joystick komutu bekleniyor.
    MOVEMENT  — Sürü Hareket Modu: formasyon korunur, centroid hareket eder.
    MANEUVER  — Manevra Modu: centroid sabit, formasyon eğilir/döndürülür.
    HOLD      — Deadman bırakıldı / timeout, sürü yerinde duruyor.
    LANDING   — Kumandadan iniş komutu geldi.
    RTL       — Eve dönüş tetiklendi.
    EMERGENCY — Acil durum / emergency_stop.
    COMPLETED — Tüm drone'lar indi, görev tamamlandı.
    """

    IDLE = 0
    PREFLIGHT = 1
    TAKEOFF = 2
    READY = 3
    MOVEMENT = 4
    MANEUVER = 5
    HOLD = 6
    LANDING = 7
    RTL = 8
    EMERGENCY = 9
    COMPLETED = 10


class ControlMode(IntEnum):
    """SwarmControlCommand.mode ile eşleşen kontrol modu sabitleri."""

    UNKNOWN = 0
    SWARM_MOVEMENT = 1
    MANEUVER = 2


# Havada olunabilecek state'ler — iniş kararlarında kullanılır.
AIRBORNE_MODE_STATES = frozenset({
    ModeState.READY,
    ModeState.MOVEMENT,
    ModeState.MANEUVER,
    ModeState.HOLD,
    ModeState.RTL,
})

# Joystick komutlarının işlendiği aktif state'ler.
ACTIVE_CONTROL_STATES = frozenset({
    ModeState.READY,
    ModeState.MOVEMENT,
    ModeState.MANEUVER,
    ModeState.HOLD,
})
