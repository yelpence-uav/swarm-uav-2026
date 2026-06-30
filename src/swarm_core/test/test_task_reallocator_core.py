"""task_reallocator_core birim testleri (ROS'suz, deterministik).

Risk raporundaki kritik güvenlik yollarını doğrular:
  K2 — uygunluk filtresi (NaN/origin/EKF/bayat) atamayı engeller.
  K3 — kademeli bozulma: lider/yedek/min-İHA senaryoları.
  O1 — determinizm (aynı girdi → aynı atama).
  Şartname — detach kalan rank'leri dondurur; sabit-slot modeli.
"""

import math

from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
)
from swarm_core.task_reallocator.task_reallocator_core import (
    DEGRADATION_FORMATION,
    DEGRADATION_NAV,
    DEGRADATION_OK,
    ROLE_DETACHED,
    ROLE_FOLLOWER,
    ROLE_LEADER,
    ROLE_STANDBY,
    Reallocation,
    ReallocatorParams,
    STATE_IN_SWARM,
    STATE_STANDBY,
    TaskReallocator,
)


def _add(tr, agent_id, x, y, state=STATE_IN_SWARM, ok=True):
    """Tam-uygun bir ajan ekler (testler için kısayol)."""
    tr.update_agent(
        agent_id,
        state=state,
        pos_x=x,
        pos_y=y,
        origin_synced=ok,
        pos_valid=ok,
        fresh=ok,
    )


def _make3():
    """3 uygun aktif ajanlı bir reallocator döner."""
    tr = TaskReallocator(ReallocatorParams(formation_size=3, spacing_m=5.0))
    _add(tr, 1, 0.0, 0.0)
    _add(tr, 2, -3.0, 5.0)
    _add(tr, 3, -3.0, -5.0)
    return tr


# --------------------------------------------------------------------- #
#  assign_formation                                                     #
# --------------------------------------------------------------------- #
def test_assign_formation_all_ranked_and_leader_at_zero():
    """Tüm aktif ajanlar rank alır; rank 0 lider olur."""
    tr = _make3()
    r = tr.assign_formation(FORMATION_OKBASI, heading_rad=0.0)
    assert set(r.rank_map) == {1, 2, 3}
    assert sorted(r.rank_map.values()) == [0, 1, 2]
    leaders = [a for a, role in r.role_map.items() if role == ROLE_LEADER]
    assert len(leaders) == 1
    assert r.rank_map[leaders[0]] == 0


def test_assign_formation_minimizes_travel():
    """Ajan zaten slotuna yakınsa o slota atanır (Macar optimalliği)."""
    tr = _make3()
    r = tr.assign_formation(FORMATION_OKBASI, heading_rad=0.0)
    # Ajan 1 merkeze (0,0) en yakın → rank 0 (merkez slot).
    assert r.rank_map[1] == 0


def test_assign_formation_deterministic():
    """Aynı girdi iki kez → aynı atama (O1 determinizm)."""
    r1 = _make3().assign_formation(FORMATION_OKBASI, 0.0)
    r2 = _make3().assign_formation(FORMATION_OKBASI, 0.0)
    assert r1.rank_map == r2.rank_map
    assert r1.role_map == r2.role_map


def test_pinned_leader_forced_to_rank_zero():
    """pinned_leader rank 0'a sabitlenir."""
    tr = _make3()
    r = tr.assign_formation(FORMATION_OKBASI, 0.0, pinned_leader=3)
    assert r.rank_map[3] == 0
    assert r.role_map[3] == ROLE_LEADER


# --------------------------------------------------------------------- #
#  K2 — uygunluk filtresi                                               #
# --------------------------------------------------------------------- #
def test_nan_position_excluded():
    """NaN konumlu ajan atamaya girmez (EKF diverge koruması)."""
    tr = _make3()
    _add(tr, 4, float('nan'), 0.0)
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert 4 not in r.rank_map


def test_origin_not_synced_excluded():
    """origin_synced=False ajan atamaya girmez (frame uyumsuz)."""
    tr = _make3()
    tr.update_agent(
        4, state=STATE_IN_SWARM, pos_x=1.0, pos_y=1.0,
        origin_synced=False, pos_valid=True, fresh=True,
    )
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert 4 not in r.rank_map


def test_stale_agent_excluded():
    """Bayat telemetrili ajan atamaya girmez."""
    tr = _make3()
    tr.update_agent(
        4, state=STATE_IN_SWARM, pos_x=1.0, pos_y=1.0,
        origin_synced=True, pos_valid=True, fresh=False,
    )
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert 4 not in r.rank_map


def test_no_eligible_agents_returns_note():
    """Hiç uygun ajan yoksa güvenli boş sonuç + not döner (patlamaz)."""
    tr = TaskReallocator(ReallocatorParams(formation_size=3))
    tr.update_agent(1, state=STATE_IN_SWARM)  # bayraklar False
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert r.rank_map == {}
    assert 'no_eligible_agents' in r.notes


# --------------------------------------------------------------------- #
#  Şartname — detach kalan rank'leri DONDURUR                           #
# --------------------------------------------------------------------- #
def test_detach_freezes_remaining_ranks():
    """Bir ajan ayrılınca kalanların rank'i değişmez (şartname s.13)."""
    tr = _make3()
    tr.assign_formation(FORMATION_OKBASI, 0.0)
    before = {a: tr.get_entry(a).rank for a in (1, 2, 3)}
    r = tr.detach(2)
    assert r.role_map[2] == ROLE_DETACHED
    assert tr.get_entry(2).rank == -1
    assert tr.get_entry(1).rank == before[1]
    assert tr.get_entry(3).rank == before[3]
    assert r.vacated_rank == before[2]


def test_detach_unknown_agent_safe():
    """Bilinmeyen ajan detach → patlamaz, not döner."""
    tr = _make3()
    r = tr.detach(99)
    assert any(n.startswith('unknown_agent') for n in r.notes)


# --------------------------------------------------------------------- #
#  K3 — yedek doldurma / rejoin / kademeli bozulma                      #
# --------------------------------------------------------------------- #
def test_standby_fills_vacated_rank():
    """>3 senaryo: yedek, ayrılanın boş slotunu devralır."""
    tr = TaskReallocator(ReallocatorParams(formation_size=3))
    _add(tr, 1, 0.0, 0.0)
    _add(tr, 2, -3.0, 5.0)
    _add(tr, 3, -3.0, -5.0)
    _add(tr, 4, -10.0, 0.0, state=STATE_STANDBY)
    asg = tr.assign_formation(FORMATION_OKBASI, 0.0)
    # Yedek, formasyon kurulumunda ROLE_STANDBY'a sabitlenir (rank yok).
    assert asg.role_map[4] == ROLE_STANDBY
    assert tr.get_entry(4).rank == -1
    det = tr.detach(2)
    rep = tr.replace_with_standby(FORMATION_OKBASI, det.vacated_rank)
    assert rep.activated_standby_id == 4
    assert tr.get_entry(4).rank == det.vacated_rank
    assert rep.role_map[4] == ROLE_FOLLOWER


def test_replace_without_standby_safe():
    """Yedek yoksa (tam 3 İHA) patlamaz, not döner."""
    tr = _make3()
    tr.assign_formation(FORMATION_OKBASI, 0.0)
    det = tr.detach(2)
    rep = tr.replace_with_standby(FORMATION_OKBASI, det.vacated_rank)
    assert rep.activated_standby_id is None
    assert 'no_standby_available' in rep.notes


def test_rejoin_takes_lowest_free_rank():
    """Ayrılan ajan döndüğünde en küçük boş rank'e oturur."""
    tr = _make3()
    tr.assign_formation(FORMATION_OKBASI, 0.0)
    det = tr.detach(2)
    # Ajan 2 tekrar uygun ve aktif hâle gelir.
    _add(tr, 2, -3.0, 5.0)
    rej = tr.rejoin(2, FORMATION_OKBASI)
    assert rej.rank_map[2] == det.vacated_rank


def test_leader_detach_then_standby_notes_election():
    """Lider (rank 0) ayrılıp yedekle dolunca seçim notu eklenir."""
    tr = TaskReallocator(ReallocatorParams(formation_size=3))
    _add(tr, 1, 0.0, 0.0)
    _add(tr, 2, -3.0, 5.0)
    _add(tr, 3, -3.0, -5.0)
    _add(tr, 5, -10.0, 0.0, state=STATE_STANDBY)
    tr.assign_formation(FORMATION_OKBASI, 0.0, pinned_leader=1)
    det = tr.detach(1)
    assert det.vacated_rank == 0
    rep = tr.replace_with_standby(FORMATION_OKBASI, 0)
    assert 'leader_slot_filled_pending_election' in rep.notes


def test_degradation_thresholds():
    """Aktif sayı düştükçe bozulma seviyesi doğru raporlanır."""
    tr = _make3()
    tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert tr.degradation_status() == DEGRADATION_OK
    tr.detach(2)
    assert tr.degradation_status() == DEGRADATION_FORMATION
    tr.detach(3)
    assert tr.degradation_status() == DEGRADATION_NAV


# --------------------------------------------------------------------- #
#  Jeneriklik (şartname: N'den bağımsız)                                #
# --------------------------------------------------------------------- #
def test_generic_n_five():
    """5 ajanlı formasyonda tüm ajanlar benzersiz rank alır."""
    tr = TaskReallocator(ReallocatorParams(formation_size=5, spacing_m=5.0))
    coords = [(0, 0), (-3, 5), (-3, -5), (-6, 10), (-6, -10)]
    for i, (x, y) in enumerate(coords, start=1):
        _add(tr, i, float(x), float(y))
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert sorted(r.rank_map.values()) == [0, 1, 2, 3, 4]
    assert len(set(r.rank_map.values())) == 5


def test_cizgi_formation_assigns():
    """Çizgi formasyonu da sorunsuz atanır (alpha kullanılmaz)."""
    tr = _make3()
    r = tr.assign_formation(FORMATION_CIZGI, heading_rad=0.0)
    assert len(r.rank_map) == 3


# --------------------------------------------------------------------- #
#  build_custom_offsets                                                 #
# --------------------------------------------------------------------- #
def test_build_custom_offsets_rank_ordered():
    """Çıktı listeleri eşit uzunlukta ve rank sırasında."""
    tr = _make3()
    tr.assign_formation(FORMATION_OKBASI, 0.0)
    ids, ox, oy, oz = tr.build_custom_offsets(FORMATION_OKBASI)
    assert len(ids) == len(ox) == len(oy) == len(oz) == 3
    # Rank 0 (merkez) offset (0,0,0) olmalı.
    assert ids == tr.active_ranked_ids()
    assert math.isclose(ox[0], 0.0) and math.isclose(oy[0], 0.0)


def test_invalid_alpha_returns_note():
    """Geçersiz kanat açısı (Ok Başı) güvenli not döner, patlamaz."""
    tr = TaskReallocator(
        ReallocatorParams(formation_size=3, alpha_deg=1.0)
    )
    _add(tr, 1, 0.0, 0.0)
    _add(tr, 2, -3.0, 5.0)
    _add(tr, 3, -3.0, -5.0)
    r = tr.assign_formation(FORMATION_OKBASI, 0.0)
    assert any(n.startswith('invalid_formation') for n in r.notes)
    assert r.rank_map == {}


def test_reallocation_dataclass_defaults():
    """Reallocation boş başlatılabilir (alan varsayılanları sağlam)."""
    r = Reallocation()
    assert r.role_map == {}
    assert r.changed_ids == []
    assert r.activated_standby_id is None
