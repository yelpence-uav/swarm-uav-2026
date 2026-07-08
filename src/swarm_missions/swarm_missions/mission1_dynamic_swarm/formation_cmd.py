"""formation_cmd.py — Lider slot ataması (Görev 1 otonom akış).

Lider, FormationCommand'ın ``agent_ids + offset_x/y/z`` alanlarını üretir;
her drone yalnızca kendi slotunu okur (formation_control böyle çalışır).
Bu modül o atamayı verir:

  1. compute_slot_offsets → formasyon geometrisi (heading=0 çerçevesi).
  2. hungarian_assignment → ajanları mevcut konumlarına EN YAKIN slotlara
     atar (toplam hareket minimize; sürü savrulmaz).
  3. apply_tilt (opsiyonel) → manevra sonrası açılı pozu ofsete gömer
     (model B): formation_control düz uygulasa bile eğik poz korunur.

Kontrol/geometri matematiği swarm_core.formation_geometry'de; burada yalnızca
liderin atama kararı var. ROS bağımlılığı yoktur → birim test edilebilir.
"""

import math

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    hungarian_assignment,
    rotate_offset,
)
from swarm_core.formation_control.manual_kinematics import apply_tilt


def build_slot_assignment(
    formation_type,
    agent_ids,
    positions,
    center,
    spacing,
    alpha_rad,
    heading_rad=0.0,
    tilt_pitch_deg=0.0,
    tilt_roll_deg=0.0,
):
    """Ajanları en yakın slotlara atar; agent_ids sırasında baz ofset döner.

    Slotlar heading=0 çerçevesinde üretilir çünkü formation_control ofseti
    kendi merkez+heading'i ile döndürür. Bu yüzden ATAMA maliyeti dünya
    çerçevesinde (heading uygulanmış slot konumları) hesaplanır, ama DÖNEN
    ofsetler bazdır (döndürülmemiş).

    Args:
        formation_type: FORMATION_* sabiti.
        agent_ids: Aktif ajan ID listesi (örn. [1, 2, 3]).
        positions: agent_ids ile aynı sırada (x, y, z) shared-NED konumları.
            Uzunluk agent_ids ile eşleşmezse konum-bağımsız kimlik ataması
            yapılır (index = rank).
        center: (cx, cy, cz) formasyon merkezi, shared NED.
        spacing: Ajanlar arası mesafe (metre).
        alpha_rad: Ok Başı/V kanat açısı (radyan); Çizgi'de kullanılmaz.
        heading_rad: Formasyon yönü (radyan).
        tilt_pitch_deg: Korunacak pitch eğimi (derece); 0 = eğim yok.
        tilt_roll_deg: Korunacak roll eğimi (derece); 0 = eğim yok.

    Returns:
        agent_ids sırasında (dx, dy, dz) baz ofset listesi.
    """
    n = len(agent_ids)
    slots = compute_slot_offsets(formation_type, n, spacing, alpha_rad)
    if tilt_pitch_deg != 0.0 or tilt_roll_deg != 0.0:
        slots = apply_tilt(slots, tilt_pitch_deg, tilt_roll_deg)

    # Konum verisi eksikse: atama yapılamaz, kimlik (rank) ataması dön.
    if len(positions) != n:
        return [
            (float(o[0]), float(o[1]), float(o[2])) for o in slots
        ]

    cx, cy = float(center[0]), float(center[1])

    # Dünya çerçevesinde slot XY konumları (heading uygulanmış) — atama
    # maliyeti için. Ofsetin z bileşeni dönmeden merkeze eklenir.
    world = []
    for (ox, oy, _oz) in slots:
        wx, wy = rotate_offset(ox, oy, heading_rad)
        world.append((cx + wx, cy + wy))

    cost = []
    for (px, py, _pz) in positions:
        row = [math.hypot(px - sx, py - sy) for (sx, sy) in world]
        cost.append(row)

    assignment = hungarian_assignment(cost)

    offsets = [(0.0, 0.0, 0.0)] * n
    for agent_idx, slot_idx in enumerate(assignment):
        ox, oy, oz = slots[slot_idx]
        offsets[agent_idx] = (float(ox), float(oy), float(oz))
    return offsets
