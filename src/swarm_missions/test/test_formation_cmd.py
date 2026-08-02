"""formation_cmd birim testleri — lider slot ataması."""

import math

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
)

from swarm_missions.mission1_dynamic_swarm.formation_cmd import (
    build_slot_assignment,
)

FORMATION_CIZGI = 3
_ALPHA = math.radians(45.0)


def test_returns_one_offset_per_agent():
    """Her ajan için bir (dx, dy, dz) ofseti döner."""
    offs = build_slot_assignment(
        FORMATION_CIZGI, [1, 2, 3], [], (0.0, 0.0, -10.0),
        spacing=5.0, alpha_rad=_ALPHA,
    )
    assert len(offs) == 3
    assert all(len(o) == 3 for o in offs)


def test_identity_when_positions_missing():
    """Konum verisi yoksa kimlik (rank) ataması yapılır."""
    offs = build_slot_assignment(
        FORMATION_CIZGI, [1, 2, 3], [], (0.0, 0.0, -10.0),
        spacing=5.0, alpha_rad=_ALPHA,
    )
    # Çizgi: rank0 daima merkez.
    assert offs[0] == (0.0, 0.0, 0.0)


def test_hungarian_assigns_agent_to_its_own_slot():
    """Ajan bir slotun dünya konumundaysa o slota atanır (min hareket)."""
    agent_ids = [1, 2, 3]
    center = (10.0, 20.0, -10.0)
    slots = compute_slot_offsets(FORMATION_CIZGI, 3, 5.0, _ALPHA)
    order = [2, 0, 1]
    positions = [
        (center[0] + slots[j][0], center[1] + slots[j][1], center[2])
        for j in order
    ]
    offs = build_slot_assignment(
        FORMATION_CIZGI, agent_ids, positions, center,
        spacing=5.0, alpha_rad=_ALPHA,
    )
    for (px, py, _pz), (ox, oy, _oz) in zip(positions, offs):
        assert abs(ox - (px - center[0])) < 1e-6
        assert abs(oy - (py - center[1])) < 1e-6


def test_tilt_changes_geometry():
    """Roll eğimi uygulanınca ofset z bileşenleri değişir (model B)."""
    flat = build_slot_assignment(
        FORMATION_CIZGI, [1, 2, 3], [], (0.0, 0.0, -10.0),
        spacing=5.0, alpha_rad=_ALPHA,
    )
    tilted = build_slot_assignment(
        FORMATION_CIZGI, [1, 2, 3], [], (0.0, 0.0, -10.0),
        spacing=5.0, alpha_rad=_ALPHA, tilt_roll_deg=15.0,
    )
    assert [o[2] for o in flat] != [o[2] for o in tilted]
