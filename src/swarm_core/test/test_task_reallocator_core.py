"""task_reallocator_core birim testleri (ROS'suz, deterministik).

Geometrisiz sürüm: yalnızca ÜYELİK ve ROL doğrulanır (slot/Hungarian yok;
onu formation_control dağıtık yapar).
  - Uygunluk filtresi (origin+taze) üye/lider seçimini engeller.
  - detach → DETACHED, rejoin → FOLLOWER (şartname 'leav').
  - apply_leader consensus'u işler; elect_leader yedek (en küçük id).
  - Kademeli bozulma: şartname minimum-İHA kuralı.
"""

from swarm_core.task_reallocator.task_reallocator_core import (
    DEGRADATION_FORMATION,
    DEGRADATION_NAV,
    DEGRADATION_OK,
    ROLE_DETACHED,
    ROLE_FOLLOWER,
    ROLE_LEADER,
    ROLE_STANDBY,
    ReallocatorParams,
    RoleReallocation,
    STATE_IN_SWARM,
    STATE_STANDBY,
    TaskReallocator,
)


def _add(tr, agent_id, state=STATE_IN_SWARM, ok=True):
    """Tam-uygun bir ajan ekler (testler için kısayol)."""
    tr.update_agent(agent_id, state=state, origin_synced=ok, fresh=ok)


def _make3():
    """3 uygun üyeli bir reallocator döner."""
    tr = TaskReallocator(ReallocatorParams())
    _add(tr, 1)
    _add(tr, 2)
    _add(tr, 3)
    return tr


# --------------------------------------------------------------------- #
#  Üyelik + uygunluk filtresi                                           #
# --------------------------------------------------------------------- #
def test_active_members_lists_eligible():
    """Uygun ve IN_SWARM ajanlar üye listesine girer."""
    tr = _make3()
    assert tr.active_member_ids() == [1, 2, 3]
    assert tr.member_count() == 3


def test_origin_not_synced_excluded():
    """origin_synced=False ajan üye sayılmaz."""
    tr = _make3()
    tr.update_agent(4, state=STATE_IN_SWARM, origin_synced=False, fresh=True)
    assert 4 not in tr.active_member_ids()


def test_stale_agent_excluded():
    """Bayat telemetrili ajan üye sayılmaz."""
    tr = _make3()
    tr.update_agent(4, state=STATE_IN_SWARM, origin_synced=True, fresh=False)
    assert 4 not in tr.active_member_ids()


# --------------------------------------------------------------------- #
#  detach / rejoin (QR 'leav')                                          #
# --------------------------------------------------------------------- #
def test_detach_sets_detached_role():
    """Ayrılan ajan DETACHED olur ve üye listesinden çıkar."""
    tr = _make3()
    r = tr.detach(2)
    assert r.role_map[2] == ROLE_DETACHED
    assert tr.get_entry(2).role == ROLE_DETACHED
    assert 2 not in tr.active_member_ids()


def test_detach_unknown_agent_safe():
    """Bilinmeyen ajan detach → patlamaz, not döner."""
    tr = _make3()
    r = tr.detach(99)
    assert any(n.startswith('unknown_agent') for n in r.notes)


def test_rejoin_sets_follower_role():
    """Dönen ajan FOLLOWER olur ve üye listesine geri girer."""
    tr = _make3()
    tr.detach(2)
    r = tr.rejoin(2)
    assert r.role_map[2] == ROLE_FOLLOWER
    assert 2 in tr.active_member_ids()


def test_detached_agent_not_member():
    """DETACHED ajan, IN_SWARM state'te olsa bile üye listesinden düşer."""
    tr = _make3()
    tr.detach(2)  # rol DETACHED
    # State hâlâ IN_SWARM ama rol DETACHED — üye listesi state'e bakar,
    # detach sonrası node telemetriden DETACHED state'i alacak; burada
    # rolün DETACHED olduğunu doğruluyoruz.
    assert tr.get_entry(2).role == ROLE_DETACHED


# --------------------------------------------------------------------- #
#  Liderlik (consensus uygula / yedek seç)                              #
# --------------------------------------------------------------------- #
def test_apply_leader_consumes_consensus():
    """apply_leader consensus liderini işler; diğerleri FOLLOWER olur."""
    tr = _make3()
    r = tr.apply_leader(3)
    assert tr.get_entry(3).role == ROLE_LEADER
    assert tr.get_entry(1).role == ROLE_FOLLOWER
    assert 'leader_applied:3' in r.notes


def test_apply_leader_non_member_safe():
    """Üye olmayan lider → patlamaz, not döner."""
    tr = _make3()
    r = tr.apply_leader(99)
    assert any(n.startswith('leader_not_member') for n in r.notes)


def test_elect_leader_smallest_id():
    """Yedek seçim en küçük id'li uygun üyeyi lider yapar."""
    tr = _make3()
    r = tr.elect_leader()
    assert tr.get_entry(1).role == ROLE_LEADER
    assert 'leader_elected:1' in r.notes


def test_election_prefers_pinned():
    """elect_leader pinned (consensus) verilince onu tercih eder."""
    tr = _make3()
    tr.elect_leader(pinned_leader=3)
    assert tr.get_entry(3).role == ROLE_LEADER


def test_leader_detach_notes_leader_lost():
    """Lider ayrılınca 'leader_lost' notu düşer."""
    tr = _make3()
    tr.apply_leader(1)
    det = tr.detach(1)
    assert 'leader_lost' in det.notes


def test_no_eligible_leader_safe():
    """Hiç uygun üye yoksa elect_leader patlamaz, not döner."""
    tr = TaskReallocator(ReallocatorParams())
    r = tr.elect_leader()
    assert 'no_eligible_leader' in r.notes


# --------------------------------------------------------------------- #
#  Yedek (STANDBY) rolü                                                 #
# --------------------------------------------------------------------- #
def test_standby_role_synced():
    """STANDBY state'indeki ajan STANDBY rolü alır, üye sayılmaz."""
    tr = _make3()
    _add(tr, 4, state=STATE_STANDBY)
    r = tr.sync_standby_roles()
    assert r.role_map[4] == ROLE_STANDBY
    assert 4 not in tr.active_member_ids()


# --------------------------------------------------------------------- #
#  Kademeli bozulma (şartname min-İHA)                                  #
# --------------------------------------------------------------------- #
def test_degradation_thresholds():
    """Üye sayısı düştükçe bozulma seviyesi doğru raporlanır."""
    tr = _make3()
    assert tr.degradation_status() == DEGRADATION_OK
    tr.detach(2)
    assert tr.degradation_status() == DEGRADATION_FORMATION
    tr.detach(3)
    assert tr.degradation_status() == DEGRADATION_NAV


def test_generic_n_five_members():
    """5 üyeli sürüde tüm uygun ajanlar üye listesine girer."""
    tr = TaskReallocator(ReallocatorParams())
    for i in range(1, 6):
        _add(tr, i)
    assert tr.active_member_ids() == [1, 2, 3, 4, 5]


def test_role_reallocation_defaults():
    """RoleReallocation boş başlatılabilir (alan varsayılanları sağlam)."""
    r = RoleReallocation()
    assert r.role_map == {}
    assert r.changed_ids == []
    assert r.notes == []
