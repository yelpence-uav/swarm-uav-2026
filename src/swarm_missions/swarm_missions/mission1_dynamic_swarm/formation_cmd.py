"""formation_cmd.py — Lider slot ataması (Görev 1 otonom akış)."""

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
    """Ajanları en yakın slotlara atar; agent_ids sırasında baz ofset döner."""
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
