"""task_reallocator_core.py — Rol yeniden dağıtım çekirdeği (geometrisiz).

Slot/offset/Hungarian hesabı bu modülde YOKTUR; onu dağıtık olarak
formation_control yapar (şartname: merkezi algoritma eksik puan, dağıtık
tercih edilir). Bu çekirdek yalnızca ÜYELİK ve ROL yönetir: kim sürünün
üyesi, kim ayrıldı (detach), kim döndü (rejoin), kim lider/takipçi/yedek.

ROS'tan bağımsızdır; birim testler ROS runtime'ı olmadan koşar
(bkz. test/test_task_reallocator_core.py). Node katmanı yalnızca mesajları
bu çekirdeğe besler ve çıkan rolleri AssignRole ile dağıtır.

Rol sabitleri AssignRole.srv / AgentStatus ROLE_* ile birebir aynıdır.
Lider KARARI consensus'undur; bu çekirdek yalnızca UYGULAR (apply_leader);
consensus susarsa son çare olarak en küçük id'li üyeyi seçer (elect_leader).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Rol sabitleri (AssignRole.srv / AgentStatus ROLE_* ile birebir) ----
ROLE_UNKNOWN = 0
ROLE_LEADER = 1
ROLE_FOLLOWER = 2
ROLE_STANDBY = 3
ROLE_DETACHED = 4

# --- Ajan state sabitleri (agent_states.AgentState ile birebir) ---------
STATE_IN_SWARM = 5
STATE_EXECUTING_TASK = 6
STATE_STANDBY = 15

# Sürünün aktif üyesi sayılan state kümesi.
_MEMBER_STATES = frozenset({STATE_IN_SWARM, STATE_EXECUTING_TASK})

# Kademeli bozulma etiketleri (şartname minimum-İHA kuralı).
DEGRADATION_OK = 'OK'
DEGRADATION_FORMATION = 'FORMATION_DEGRADED'
DEGRADATION_NAV = 'NAV_DEGRADED'


@dataclass
class RosterEntry:
    """Tek ajanın üyelik/rol defterindeki kaydı.

    ``role`` bu çekirdek tarafından sahiplenilir; ``state`` ve bayraklar
    node tarafından telemetriden güncellenir. Bayraklar muhafazakâr olarak
    ``False`` başlar: node doğrulamadıkça ajan uygun sayılmaz.
    """

    agent_id: int
    state: int = 0
    role: int = ROLE_UNKNOWN
    origin_synced: bool = False
    fresh: bool = False


@dataclass
class RoleReallocation:
    """Bir rol kararının sonucu (yalnızca değişen roller + notlar).

    ``changed_ids`` yalnızca bu işlemde rolü değişen ajanları içerir; node
    bu listeye göre AssignRole gönderir (gereksiz servis çağrısı yok).
    """

    role_map: dict[int, int] = field(default_factory=dict)
    changed_ids: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ReallocatorParams:
    """Yeniden-dağıtım ayar kümesi (ROS parametresi olarak açılır)."""

    min_active_for_formation: int = 3   # şartname: formasyon min 3 İHA
    min_active_for_navigation: int = 2  # şartname: navigasyon min 2 İHA


def _eligible(entry: RosterEntry) -> bool:
    """Ajan geçerli bir üye/lider adayı mı? (origin senkron + taze)."""
    return entry.origin_synced and entry.fresh


class TaskReallocator:
    """Üyelik ve rol yeniden dağıtıcı (geometrisiz).

    Kullanım:
        tr = TaskReallocator(ReallocatorParams())
        tr.update_agent(1, state=IN_SWARM, origin_synced=True, fresh=True)
        tr.apply_leader(1)     # consensus lideri
        tr.detach(2)           # QR 'leav' → İHA 2 ayrıldı
        tr.rejoin(2)           # İHA 2 geri döndü
    """

    def __init__(self, params: ReallocatorParams | None = None) -> None:
        """Reallocator'ı parametrelerle başlatır."""
        self.p = params or ReallocatorParams()
        self._roster: dict[int, RosterEntry] = {}

    # ------------------------------------------------------------------ #
    #  Roster bakımı (node telemetriden çağırır — rol'e dokunmaz)         #
    # ------------------------------------------------------------------ #
    def update_agent(
        self,
        agent_id: int,
        *,
        state: int,
        origin_synced: bool = False,
        fresh: bool = True,
    ) -> None:
        """Bir ajanın state/bayraklarını günceller (rolü DEĞİŞTİRMEZ).

        Args:
            agent_id: Ajan kimliği.
            state: AgentState enum değeri (int).
            origin_synced: Paylaşılan NED origin'ine kilitli mi?
            fresh: Telemetri güncel mi (bayat değil)?
        """
        entry = self._roster.get(agent_id)
        if entry is None:
            entry = RosterEntry(agent_id=agent_id)
            self._roster[agent_id] = entry
        entry.state = state
        entry.origin_synced = origin_synced
        entry.fresh = fresh

    def remove_agent(self, agent_id: int) -> None:
        """Ajanı defterden tamamen siler (ör. kalıcı kayıp)."""
        self._roster.pop(agent_id, None)

    def get_entry(self, agent_id: int) -> RosterEntry | None:
        """Ajan kaydını döner (yoksa None)."""
        return self._roster.get(agent_id)

    # ------------------------------------------------------------------ #
    #  Sorgular                                                           #
    # ------------------------------------------------------------------ #
    def active_member_ids(self) -> list[int]:
        """Uygun, üye state'inde ve DETACHED olmayan ajanları döner.

        Üyelik hem state (IN_SWARM/EXECUTING) hem rol (DETACHED değil) ile
        belirlenir: detach rolü hemen değiştirir, state telemetriyle biraz
        sonra gelir — ikisini birlikte kontrol ederek anında doğru sonuç.
        """
        return sorted(
            e.agent_id for e in self._roster.values()
            if _eligible(e)
            and e.state in _MEMBER_STATES
            and e.role != ROLE_DETACHED
        )

    def member_count(self) -> int:
        """Aktif (DETACHED olmayan) üye sayısını döner."""
        return len(self.active_member_ids())

    def has_leader(self) -> bool:
        """Aktif üyeler arasında lider olup olmadığını döner."""
        members = set(self.active_member_ids())
        return any(
            e.agent_id in members and e.role == ROLE_LEADER
            for e in self._roster.values()
        )

    def degradation_status(self) -> str:
        """Şartname minimum-İHA kuralına göre bozulma seviyesini döner.

        Returns:
            DEGRADATION_OK / _FORMATION / _NAV.
        """
        n = self.member_count()
        if n >= self.p.min_active_for_formation:
            return DEGRADATION_OK
        if n >= self.p.min_active_for_navigation:
            return DEGRADATION_FORMATION
        return DEGRADATION_NAV

    # ------------------------------------------------------------------ #
    #  Üyelik değişimi (QR 'leav' / rejoin)                               #
    # ------------------------------------------------------------------ #
    def detach(self, target_id: int) -> RoleReallocation:
        """Bir ajanı sürüden çıkarır (rol DETACHED).

        Args:
            target_id: Ayrılacak ajan kimliği (QR 'leav' hedefi).

        Returns:
            RoleReallocation: hedefin yeni rolü + notlar. Lider ayrıldıysa
            'leader_lost' notu düşer (node elect_leader/consensus bekler).
        """
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
        """Ayrılmış bir ajanı sürüye geri katar (rol FOLLOWER).

        Args:
            target_id: Sürüye dönen ajan kimliği.

        Returns:
            RoleReallocation: hedefin yeni rolü + notlar.
        """
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
        """Yerdeki (STANDBY state) ajanların rolünü STANDBY yapar."""
        r = RoleReallocation()
        for entry in self._roster.values():
            if entry.state == STATE_STANDBY and entry.role != ROLE_STANDBY:
                entry.role = ROLE_STANDBY
                r.role_map[entry.agent_id] = ROLE_STANDBY
                r.changed_ids.append(entry.agent_id)
        return r

    # ------------------------------------------------------------------ #
    #  Liderlik (karar consensus'un; burada yalnızca UYGULANIR)           #
    # ------------------------------------------------------------------ #
    def apply_leader(self, leader_id: int) -> RoleReallocation:
        """Consensus'un seçtiği lideri işler (LİDER; diğer üyeler FOLLOWER).

        Lider KARARI consensus'undur (Beyza/ElectionResult). Bu metot o
        kararı yalnızca rol defterine yansıtır.

        Args:
            leader_id: Consensus'un seçtiği lider ajan kimliği.

        Returns:
            RoleReallocation: rol değişimleri. Lider üye değilse yalnız not.
        """
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
        """Yedek seçim: en küçük id'li uygun üyeyi lider yapar.

        Yalnızca consensus HİÇ konuşmadıysa çağrılır (son çare). Gerçek
        seçim consensus'undur; ``pinned_leader`` verilirse o tercih edilir.

        Returns:
            RoleReallocation: rol değişimleri + 'leader_elected' notu.
        """
        r = RoleReallocation()
        leader = self._choose_leader(pinned_leader)
        if leader is None:
            r.notes.append('no_eligible_leader')
            return r
        self._set_leader(leader, r)
        r.notes.append('leader_elected:%d' % leader)
        return r

    # ------------------------------------------------------------------ #
    #  Yardımcı metodlar                                                  #
    # ------------------------------------------------------------------ #
    def _choose_leader(self, pinned: int | None) -> int | None:
        """Lider adayı: pinned (uygunsa) yoksa en küçük id'li üye."""
        members = self.active_member_ids()
        if pinned is not None and pinned in members:
            return pinned
        return members[0] if members else None

    def _set_leader(self, leader_id: int, r: RoleReallocation) -> None:
        """Verilen lideri LİDER, diğer üyeleri FOLLOWER yapar (yalnız değişen)."""
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
        """Bozulma seviyesi OK değilse not ekler (şartname min-İHA)."""
        status = self.degradation_status()
        if status != DEGRADATION_OK:
            r.notes.append('degradation:%s' % status)
