# Copyright 2026 Yelpence
"""Rol yeniden dagitim cekirdegi."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_UNKNOWN = 0
ROLE_LEADER = 1
ROLE_FOLLOWER = 2
ROLE_STANDBY = 3
ROLE_DETACHED = 4

STATE_IN_SWARM = 5
STATE_EXECUTING_TASK = 6
STATE_STANDBY = 15

_MEMBER_STATES = frozenset({STATE_IN_SWARM, STATE_EXECUTING_TASK})

DEGRADATION_OK = 'OK'
DEGRADATION_FORMATION = 'FORMATION_DEGRADED'
DEGRADATION_NAV = 'NAV_DEGRADED'


@dataclass
class RosterEntry:
    """Tek ajanin uyelik/rol kaydi."""

    agent_id: int
    state: int = 0
    role: int = ROLE_UNKNOWN
    origin_synced: bool = False
    fresh: bool = False


@dataclass
class RoleReallocation:
    """Rol karari sonucu."""

    role_map: dict[int, int] = field(default_factory=dict)
    changed_ids: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ReallocatorParams:
    """Yeniden dagitim ayarlari."""

    min_active_for_formation: int = 3
    min_active_for_navigation: int = 2


def _eligible(entry: RosterEntry) -> bool:
    """Ajan lider adayi olmaya uygun mu?."""
    return entry.origin_synced and entry.fresh


class TaskReallocator:
    """Uyelik ve rol yeniden dagiticisi."""

    def __init__(self, params: ReallocatorParams | None = None) -> None:
        self.p = params or ReallocatorParams()
        self._roster: dict[int, RosterEntry] = {}

    def update_agent(
        self,
        agent_id: int,
        *,
        state: int,
        origin_synced: bool = False,
        fresh: bool = True,
    ) -> None:
        """Ajan durumunu gunceller."""
        entry = self._roster.get(agent_id)
        if entry is None:
            entry = RosterEntry(agent_id=agent_id)
            self._roster[agent_id] = entry
        entry.state = state
        entry.origin_synced = origin_synced
        entry.fresh = fresh

    def remove_agent(self, agent_id: int) -> None:
        """Ajan kaydini siler."""
        self._roster.pop(agent_id, None)

    def get_entry(self, agent_id: int) -> RosterEntry | None:
        """Ajan kaydini doner."""
        return self._roster.get(agent_id)

    def active_member_ids(self) -> list[int]:
        """Aktif uye olan ajanlari doner."""
        return sorted(
            e.agent_id for e in self._roster.values()
            if _eligible(e)
            and e.state in _MEMBER_STATES
            and e.role != ROLE_DETACHED
        )

    def member_count(self) -> int:
        """Aktif uye sayisini doner."""
        return len(self.active_member_ids())

    def has_leader(self) -> bool:
        """Aktif uyeler icinde lider var mi?."""
        members = set(self.active_member_ids())
        return any(
            e.agent_id in members and e.role == ROLE_LEADER
            for e in self._roster.values()
        )

    def degradation_status(self) -> str:
        """Asgari IHA kurallarina gore bozulma durumunu doner."""
        n = self.member_count()
        if n >= self.p.min_active_for_formation:
            return DEGRADATION_OK
        if n >= self.p.min_active_for_navigation:
            return DEGRADATION_FORMATION
        return DEGRADATION_NAV

    def detach(self, target_id: int) -> RoleReallocation:
        """Ajanı suruden ayirir."""
        r = RoleReallocation()
        entry = self._roster.get(target_id)
        if entry is None:
            r.notes.append('unknown_agent:%d' % target_id)
            return r
        was_leader = entry.role == ROLE_LEADER
        entry.role = ROLE_DETACHED
        r.role_map[target_id] = ROLE_DETACHED
        r.changed_ids.append(target_id)
        if was_leader:
            r.notes.append('leader_lost')
        self._note_degradation(r)
        return r

    def rejoin(self, target_id: int) -> RoleReallocation:
        """Ayrilan ajani suruye geri dahil eder."""
        r = RoleReallocation()
        entry = self._roster.get(target_id)
        if entry is None:
            r.notes.append('unknown_agent:%d' % target_id)
            return r
        entry.role = ROLE_FOLLOWER
        r.role_map[target_id] = ROLE_FOLLOWER
        r.changed_ids.append(target_id)
        self._note_degradation(r)
        return r

    def sync_standby_roles(self) -> RoleReallocation:
        """Yerde bekleyen yedeklerin rolunu gunceller."""
        r = RoleReallocation()
        for entry in self._roster.values():
            if entry.state == STATE_STANDBY and entry.role != ROLE_STANDBY:
                entry.role = ROLE_STANDBY
                r.role_map[entry.agent_id] = ROLE_STANDBY
                r.changed_ids.append(entry.agent_id)
        return r

    def apply_leader(self, leader_id: int) -> RoleReallocation:
        """Secilen lideri rol tablosuna uygular."""
        r = RoleReallocation()
        if leader_id not in self.active_member_ids():
            r.notes.append('leader_not_member:%d' % leader_id)
            return r
        self._set_leader(leader_id, r)
        r.notes.append('leader_applied:%d' % leader_id)
        return r

    def elect_leader(
        self, pinned_leader: int | None = None,
    ) -> RoleReallocation:
        """Yedek secim mekanizmasi calistirir."""
        r = RoleReallocation()
        leader = self._choose_leader(pinned_leader)
        if leader is None:
            r.notes.append('no_eligible_leader')
            return r
        self._set_leader(leader, r)
        r.notes.append('leader_elected:%d' % leader)
        return r

    def _choose_leader(self, pinned: int | None) -> int | None:
        """Lider adayini secer."""
        members = self.active_member_ids()
        if pinned is not None and pinned in members:
            return pinned
        return members[0] if members else None

    def _set_leader(self, leader_id: int, r: RoleReallocation) -> None:
        """Liderlik rollerini uygular."""
        for agent_id in self.active_member_ids():
            entry = self._roster[agent_id]
            desired = (
                ROLE_LEADER if agent_id == leader_id else ROLE_FOLLOWER
            )
            if entry.role != desired:
                entry.role = desired
                r.role_map[agent_id] = desired
                if agent_id not in r.changed_ids:
                    r.changed_ids.append(agent_id)

    def _note_degradation(self, r: RoleReallocation) -> None:
        """Bozulma notlarini ekler."""
        status = self.degradation_status()
        if status != DEGRADATION_OK:
            r.notes.append('degradation:%s' % status)
