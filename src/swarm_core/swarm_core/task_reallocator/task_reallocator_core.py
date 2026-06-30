"""task_reallocator_core.py — Rol/slot yeniden dağıtım çekirdeği.

Bu modül kasıtlı olarak ROS2'den bağımsızdır: tüm girdiler saf Python
veri yapılarıdır, böylece birim testler ROS runtime'ı olmadan koşar
(bkz. test/test_task_reallocator_core.py). Node katmanı yalnızca
AgentStatus/SystemEvent mesajlarını bu çekirdeğe besler.

═══════════════════════════════════════════════════════════════════════
MİMARİ: SABİT SLOT MODELİ (şartname uyumu)
═══════════════════════════════════════════════════════════════════════
Slot geometrisi DAİMA tasarım formasyon boyutu (``formation_size``) için
hesaplanır. Üyelik değişimi yalnızca hangi rank'in DOLU olduğunu değiştirir;
kalan üyelerin slot geometrisini ASLA yeniden hesaplamaz.

→ Şartname (s.13): "Sürüden bir İHA ayrıldığında geriye kalan sürü mevcut
  formasyonunu korumalıdır; formasyon düzeltmesi yapılmayacaktır."

Yani ``detach`` bir rank'i boşaltır, kalan rank'ler DONDURULUR. ``rejoin``
ve ``replace_with_standby`` boş rank'i doldurur. Hiçbir durumda kalan
ajanların offset'leri kaymaz.

═══════════════════════════════════════════════════════════════════════
EMNİYET: GİRDİ UYGUNLUK FİLTRESİ
═══════════════════════════════════════════════════════════════════════
Bir ajan ancak şu DÖRT koşul birden sağlanırsa atamaya/maliyet matrisine
girer (``_eligible``):
  - origin_synced : paylaşılan NED frame'ine kilitli (yoksa pos_x/y kendi
    lokal origin'ine göredir; global slot ataması yanlış olur).
  - pos_valid     : EKF konum tahmini geçerli (xy_valid + estimator_ok).
  - fresh         : telemetri bayat değil (node monotonic alış anına bakar).
  - finite        : pos_x/y NaN/Inf değil (EKF diverge koruması).
Aksi hâlde çöp/eski konum Macar algoritmasına girip yanlış slot → çarpışma
üretebilir.

LİTERATÜR / TASARIM:
- Macar (Kuhn-Munkres) algoritması: hareketi minimize eden optimal atama;
  ``formation_geometry.hungarian_assignment`` yeniden kullanılır (DRY).
- Slot geometrisi ``formation_geometry.compute_slot_offsets`` ile tek
  kaynaktan üretilir; bu modül geometriyi yeniden tanımlamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    hungarian_assignment,
    rotate_offset,
)


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

# Formasyon slotu işgal eden (rank atanabilir) state kümesi.
_ACTIVE_STATES = frozenset({STATE_IN_SWARM, STATE_EXECUTING_TASK})

# Kademeli bozulma etiketleri (şartname minimum-İHA kuralı).
DEGRADATION_OK = 'OK'
DEGRADATION_FORMATION = 'FORMATION_DEGRADED'
DEGRADATION_NAV = 'NAV_DEGRADED'

_RANK_UNASSIGNED = -1


@dataclass
class RosterEntry:
    """Tek ajanın yeniden-dağıtım defterindeki kaydı.

    ``rank`` ve ``role`` bu modül tarafından sahiplenilir; ``state`` ve
    konum/bayrak alanları node tarafından telemetriden güncellenir.

    Emniyet bayrakları varsayılan olarak ``False``'tur (muhafazakâr):
    node açıkça doğrulamadıkça ajan uygunluk filtresinden geçemez.
    """

    agent_id: int
    state: int = 0
    role: int = ROLE_UNKNOWN
    rank: int = _RANK_UNASSIGNED
    pos_x: float = 0.0
    pos_y: float = 0.0
    origin_synced: bool = False
    pos_valid: bool = False
    fresh: bool = False


@dataclass
class Reallocation:
    """Bir yeniden-dağıtım kararının sonucu (delta).

    ``changed_ids`` yalnızca bu işlemde rolü/rank'i değişen ajanları içerir;
    node bu listeye göre AssignRole/atama yayını yapar (gereksiz ağ yükü yok).
    """

    role_map: dict[int, int] = field(default_factory=dict)
    rank_map: dict[int, int] = field(default_factory=dict)
    offset_map: dict[int, tuple[float, float, float]] = field(
        default_factory=dict
    )
    changed_ids: list[int] = field(default_factory=list)
    activated_standby_id: int | None = None
    vacated_rank: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ReallocatorParams:
    """Yeniden-dağıtım ayar kümesi (ROS parametresi olarak açılır)."""

    formation_size: int = 3        # tasarım formasyon boyutu (sabit slot)
    spacing_m: float = 5.0         # ajanlar arası nominal mesafe (m)
    alpha_deg: float = 45.0        # Ok Başı/V kanat açısı (derece)
    min_active_for_formation: int = 3   # şartname: formasyon min 3 İHA
    min_active_for_navigation: int = 2  # şartname: navigasyon min 2 İHA


def _finite(*vals: float) -> bool:
    """Verilen değerlerin hiçbiri NaN/Inf değilse True döner."""
    for v in vals:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _eligible(entry: RosterEntry) -> bool:
    """Ajan atamaya girebilir mi? (origin+EKF+tazelik+finite)."""
    return (
        entry.origin_synced
        and entry.pos_valid
        and entry.fresh
        and _finite(entry.pos_x, entry.pos_y)
    )


def _hungarian_rect(
    cost: list[list[float]], n_rows: int, n_cols: int,
) -> list[int]:
    """Dikdörtgen maliyet için atama (sıfır-dolgu ile kareye tamamlar).

    Macar algoritması kare matris ister. Satır/sütun sayısı eşit değilse
    eksik taraf sıfır maliyetli kukla satır/sütunlarla doldurulur. Gerçek
    bir satıra kukla sütun düşerse (yalnızca n_rows > n_cols durumunda
    mümkündür) o satır için -1 (atanmadı) döner.

    Args:
        cost: n_rows × n_cols maliyet matrisi (kareler/öklid²).
        n_rows: Gerçek satır (ajan) sayısı.
        n_cols: Gerçek sütun (slot) sayısı.

    Returns:
        Uzunluğu n_rows olan liste; result[i] = atanan sütun ya da -1.
    """
    if n_rows == 0 or n_cols == 0:
        return [_RANK_UNASSIGNED] * n_rows
    m = max(n_rows, n_cols)
    big = [[0.0] * m for _ in range(m)]
    for i in range(n_rows):
        for j in range(n_cols):
            big[i][j] = cost[i][j]
    full = hungarian_assignment(big)
    out: list[int] = []
    for i in range(n_rows):
        col = full[i]
        out.append(col if col < n_cols else _RANK_UNASSIGNED)
    return out


class TaskReallocator:
    """Sabit-slot modelli rol/koordinat yeniden dağıtıcı.

    Kullanım:
        tr = TaskReallocator(ReallocatorParams(formation_size=3))
        tr.update_agent(1, state=IN_SWARM, pos_x=..., origin_synced=True,
                        pos_valid=True, fresh=True)
        r = tr.assign_formation(FORMATION_OKBASI, heading_rad=0.0)
        # üye değişiminde:
        tr.detach(2)
        tr.replace_with_standby(FORMATION_OKBASI, vacated_rank=r.vacated_rank)
    """

    def __init__(self, params: ReallocatorParams | None = None) -> None:
        """Reallocator'ı parametrelerle başlatır."""
        self.p = params or ReallocatorParams()
        self._roster: dict[int, RosterEntry] = {}

    # ------------------------------------------------------------------ #
    #  Roster bakımı (node telemetriden çağırır — atama TETİKLEMEZ)       #
    # ------------------------------------------------------------------ #
    def update_agent(
        self,
        agent_id: int,
        *,
        state: int,
        pos_x: float = 0.0,
        pos_y: float = 0.0,
        origin_synced: bool = False,
        pos_valid: bool = False,
        fresh: bool = True,
    ) -> None:
        """Bir ajanın state/konum/bayraklarını günceller.

        ``rank`` ve ``role`` bu metotça DEĞİŞTİRİLMEZ; onlar yeniden-dağıtım
        kararlarının sahipliğindedir.

        Args:
            agent_id: Ajan kimliği.
            state: AgentState enum değeri (int).
            pos_x: Paylaşılan NED kuzey bileşeni (m).
            pos_y: Paylaşılan NED doğu bileşeni (m).
            origin_synced: Paylaşılan NED origin'ine kilitli mi?
            pos_valid: EKF konum tahmini geçerli mi?
            fresh: Telemetri güncel mi (bayat değil)?
        """
        entry = self._roster.get(agent_id)
        if entry is None:
            entry = RosterEntry(agent_id=agent_id)
            self._roster[agent_id] = entry
        entry.state = state
        entry.pos_x = pos_x
        entry.pos_y = pos_y
        entry.origin_synced = origin_synced
        entry.pos_valid = pos_valid
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
    def active_count(self) -> int:
        """Formasyon slotu işgal eden (rank atanmış) ajan sayısı."""
        return sum(1 for e in self._roster.values() if e.rank >= 0)

    def active_ranked_ids(self) -> list[int]:
        """Rank atanmış ajanları rank sırasıyla döner."""
        ranked = sorted(
            (e for e in self._roster.values() if e.rank >= 0),
            key=lambda e: e.rank,
        )
        return [e.agent_id for e in ranked]

    def degradation_status(self) -> str:
        """Şartname minimum-İHA kuralına göre bozulma seviyesi.

        Returns:
            DEGRADATION_OK / _FORMATION / _NAV.
        """
        n = self.active_count()
        if n >= self.p.min_active_for_formation:
            return DEGRADATION_OK
        if n >= self.p.min_active_for_navigation:
            return DEGRADATION_FORMATION
        return DEGRADATION_NAV

    # ------------------------------------------------------------------ #
    #  Ana yeniden-dağıtım işlemleri                                      #
    # ------------------------------------------------------------------ #
    def assign_formation(
        self,
        formation_type: int,
        heading_rad: float,
        pinned_leader: int | None = None,
    ) -> Reallocation:
        """Tüm uygun aktif ajanlara rank/rol atar (ilk formasyon kurulumu).

        Hareketi minimize etmek için Macar algoritması kullanılır.
        ``pinned_leader`` verilirse o ajan rank 0'a sabitlenir (lider
        kararlılığı); aksi hâlde rank 0'a düşen ajan lider olur.

        Args:
            formation_type: FORMATION_* enum değeri.
            heading_rad: Formasyon yönü (radyan, NED).
            pinned_leader: Rank 0'a sabitlenecek ajan (opsiyonel).

        Returns:
            Reallocation: rol/rank/offset eşlemeleri ve notlar.
        """
        r = Reallocation()
        active = self._sorted_active()
        if not active:
            r.notes.append('no_eligible_agents')
            return r

        slots = self._slots(formation_type, r)
        if slots is None:
            return r

        targets = self._world_targets(active, slots, heading_rad)
        ranks = self._min_travel(active, targets, pinned_leader)

        for entry in active:
            rank = ranks.get(entry.agent_id, _RANK_UNASSIGNED)
            if rank < 0:
                r.notes.append('agent_unranked:%d' % entry.agent_id)
                continue
            self._apply_rank(entry, rank, slots[rank], r)

        self._assign_leader(pinned_leader, r)
        self._demote_standbys(r)
        self._append_degradation_note(r)
        return r

    def detach(self, target_id: int) -> Reallocation:
        """Bir ajanı sürüden çıkarır; kalan rank'leri DONDURUR.

        Şartname gereği geriye kalan sürü formasyonunu korur — bu metot
        diğer ajanların rank'ine/offset'ine dokunmaz.

        Args:
            target_id: Ayrılacak ajan kimliği.

        Returns:
            Reallocation: boşalan rank ve hedef ajanın yeni rolü.
        """
        r = Reallocation()
        entry = self._roster.get(target_id)
        if entry is None:
            r.notes.append('unknown_agent:%d' % target_id)
            return r
        was_leader = entry.role == ROLE_LEADER
        r.vacated_rank = entry.rank if entry.rank >= 0 else None
        entry.role = ROLE_DETACHED
        entry.rank = _RANK_UNASSIGNED
        r.role_map[target_id] = ROLE_DETACHED
        r.rank_map[target_id] = _RANK_UNASSIGNED
        r.changed_ids.append(target_id)
        if was_leader:
            # Liderlik boşaldı — node elect_leader() çağırmalı (en küçük id).
            r.notes.append('leader_lost')
        self._append_degradation_note(r)
        return r

    def replace_with_standby(
        self,
        formation_type: int,
        vacated_rank: int | None = None,
    ) -> Reallocation:
        """Boşalan rank'i yerdeki bir yedek (standby) ile doldurur.

        >3 İHA senaryosu: bir ajan ayrılınca yedek devreye girer ve
        ayrılanın bıraktığı sabit slotu devralır.

        Args:
            formation_type: FORMATION_* enum değeri.
            vacated_rank: Tercih edilen boş rank (None ise en küçük boş).

        Returns:
            Reallocation: etkinleşen yedek ve atadığı rank/offset.
        """
        r = Reallocation()
        rank = self._vacant_rank(vacated_rank)
        if rank is None:
            r.notes.append('no_vacant_rank')
            self._append_degradation_note(r)
            return r
        standby = self._pick_standby()
        if standby is None:
            r.notes.append('no_standby_available')
            self._append_degradation_note(r)
            return r
        offset = self._slot_offset(formation_type, rank, r)
        if offset is None:
            return r
        # Yedek FOLLOWER olarak slota oturur. Boşalan slot rank 0 olsa bile
        # liderlik buradan ATANMAZ; lider ayrı seçilir (elect_leader).
        self._apply_rank(standby, rank, offset, r)
        r.activated_standby_id = standby.agent_id
        r.vacated_rank = rank
        self._append_degradation_note(r)
        return r

    def rejoin(
        self,
        target_id: int,
        formation_type: int,
    ) -> Reallocation:
        """Ayrılmış bir ajanı en küçük boş rank'e geri oturtur.

        Args:
            target_id: Sürüye dönen ajan kimliği.
            formation_type: FORMATION_* enum değeri.

        Returns:
            Reallocation: atanan rank/rol/offset.
        """
        r = Reallocation()
        entry = self._roster.get(target_id)
        if entry is None:
            r.notes.append('unknown_agent:%d' % target_id)
            return r
        rank = self._vacant_rank(None)
        if rank is None:
            r.notes.append('no_vacant_rank')
            self._append_degradation_note(r)
            return r
        offset = self._slot_offset(formation_type, rank, r)
        if offset is None:
            return r
        self._apply_rank(entry, rank, offset, r)
        r.vacated_rank = rank
        self._append_degradation_note(r)
        return r

    def build_custom_offsets(
        self, formation_type: int,
    ) -> tuple[list[int], list[float], list[float], list[float]]:
        """Atama listelerini FormationCommand CUSTOM alanları için üretir.

        Yalnızca rank atanmış ajanları rank sırasıyla döner. Offset'ler
        body-frame'dir (heading döndürmesini tüketici uygular).

        Args:
            formation_type: FORMATION_* enum değeri.

        Returns:
            (agent_ids, offset_x, offset_y, offset_z) eşit uzunlukta.
        """
        ids: list[int] = []
        ox: list[float] = []
        oy: list[float] = []
        oz: list[float] = []
        try:
            slots = compute_slot_offsets(
                formation_type,
                self.p.formation_size,
                self.p.spacing_m,
                math.radians(self.p.alpha_deg),
            )
        except ValueError:
            return ids, ox, oy, oz
        ranked = sorted(
            (e for e in self._roster.values() if e.rank >= 0),
            key=lambda e: e.rank,
        )
        for entry in ranked:
            if 0 <= entry.rank < len(slots):
                dx, dy, dz = slots[entry.rank]
                ids.append(entry.agent_id)
                ox.append(dx)
                oy.append(dy)
                oz.append(dz)
        return ids, ox, oy, oz

    # ------------------------------------------------------------------ #
    #  Yardımcı metodlar                                                  #
    # ------------------------------------------------------------------ #
    def _sorted_active(self) -> list[RosterEntry]:
        """Uygun + aktif ajanları agent_id sırasıyla döner (determinizm)."""
        return sorted(
            (
                e for e in self._roster.values()
                if _eligible(e) and e.state in _ACTIVE_STATES
            ),
            key=lambda e: e.agent_id,
        )

    def _slots(
        self, formation_type: int, r: Reallocation,
    ) -> list[tuple[float, float, float]] | None:
        """Sabit formasyon boyutu için slot offsetlerini üretir."""
        try:
            return compute_slot_offsets(
                formation_type,
                self.p.formation_size,
                self.p.spacing_m,
                math.radians(self.p.alpha_deg),
            )
        except ValueError as exc:
            r.notes.append('invalid_formation:%s' % exc)
            return None

    def _slot_offset(
        self, formation_type: int, rank: int, r: Reallocation,
    ) -> tuple[float, float, float] | None:
        """Tek bir rank'in body-frame offset'ini döner."""
        slots = self._slots(formation_type, r)
        if slots is None:
            return None
        if rank < 0 or rank >= len(slots):
            r.notes.append('rank_out_of_range:%d' % rank)
            return None
        return slots[rank]

    def _world_targets(
        self,
        active: list[RosterEntry],
        slots: list[tuple[float, float, float]],
        heading_rad: float,
    ) -> list[tuple[float, float]]:
        """Her slot için dünya (NED) hedef XY konumunu hesaplar.

        Merkez, uygun aktif ajanların centroid'idir; offset heading kadar
        döndürülür (maliyet matrisi gerçek mesafeyle kurulur).
        """
        k = len(active)
        cx = sum(e.pos_x for e in active) / k
        cy = sum(e.pos_y for e in active) / k
        targets: list[tuple[float, float]] = []
        for (dx, dy, _dz) in slots:
            rx, ry = rotate_offset(dx, dy, heading_rad)
            targets.append((cx + rx, cy + ry))
        return targets

    def _min_travel(
        self,
        active: list[RosterEntry],
        targets: list[tuple[float, float]],
        pinned_leader: int | None,
    ) -> dict[int, int]:
        """Hareketi minimize eden agent_id→rank eşlemesini döner.

        ``pinned_leader`` rank 0'a sabitlenir; kalan ajanlar kalan slotlara
        Macar algoritmasıyla atanır.
        """
        ids = [e.agent_id for e in active]
        result: dict[int, int] = {}
        free_ranks = list(range(len(targets)))
        rows = list(active)
        if pinned_leader is not None and pinned_leader in ids:
            result[pinned_leader] = 0
            if 0 in free_ranks:
                free_ranks.remove(0)
            rows = [e for e in active if e.agent_id != pinned_leader]

        cost: list[list[float]] = []
        for entry in rows:
            row: list[float] = []
            for j in free_ranks:
                tx, ty = targets[j]
                dx = entry.pos_x - tx
                dy = entry.pos_y - ty
                row.append(dx * dx + dy * dy)
            cost.append(row)

        sub = _hungarian_rect(cost, len(rows), len(free_ranks))
        for idx, entry in enumerate(rows):
            col = sub[idx]
            result[entry.agent_id] = (
                free_ranks[col] if col >= 0 else _RANK_UNASSIGNED
            )
        return result

    def _apply_rank(
        self,
        entry: RosterEntry,
        rank: int,
        offset: tuple[float, float, float],
        r: Reallocation,
    ) -> None:
        """Bir ajana SLOT (rank/offset) uygular; rolü FOLLOWER yapar.

        Rank fiziksel slottur; liderlik ayrı bir karardır (``_set_leader`` /
        ``elect_leader``). Bu metot yalnızca yerleştirme yapar — bir slota
        oturan ajan varsayılan olarak takipçidir, liderlik buradan ATANMAZ.
        """
        entry.rank = rank
        entry.role = ROLE_FOLLOWER
        r.rank_map[entry.agent_id] = rank
        r.role_map[entry.agent_id] = entry.role
        r.offset_map[entry.agent_id] = offset
        if entry.agent_id not in r.changed_ids:
            r.changed_ids.append(entry.agent_id)

    def _occupied_ranks(self) -> set[int]:
        """Şu an dolu olan rank'lerin kümesi."""
        return {e.rank for e in self._roster.values() if e.rank >= 0}

    def _vacant_rank(self, prefer: int | None) -> int | None:
        """En küçük boş rank'i (ya da geçerliyse tercih edileni) döner."""
        occupied = self._occupied_ranks()
        if (
            prefer is not None
            and 0 <= prefer < self.p.formation_size
            and prefer not in occupied
        ):
            return prefer
        for j in range(self.p.formation_size):
            if j not in occupied:
                return j
        return None

    def _pick_standby(self) -> RosterEntry | None:
        """Uygun yedeklerden agent_id'si en küçük olanı döner."""
        cands = sorted(
            (
                e for e in self._roster.values()
                if e.state == STATE_STANDBY and _eligible(e)
            ),
            key=lambda e: e.agent_id,
        )
        return cands[0] if cands else None

    def _demote_standbys(self, r: Reallocation) -> None:
        """Yerdeki yedekleri ROLE_STANDBY'a sabitler (rank yok)."""
        for entry in self._roster.values():
            if entry.state == STATE_STANDBY and entry.role != ROLE_STANDBY:
                entry.role = ROLE_STANDBY
                entry.rank = _RANK_UNASSIGNED
                r.role_map[entry.agent_id] = ROLE_STANDBY
                r.rank_map[entry.agent_id] = _RANK_UNASSIGNED
                if entry.agent_id not in r.changed_ids:
                    r.changed_ids.append(entry.agent_id)

    def elect_leader(
        self, pinned_leader: int | None = None,
    ) -> Reallocation:
        """En küçük id'li UYGUN aktif ajanı lider yapar (yer tutucu seçim).

        Lider düştüğünde çağrılır. Şartname gereği FİZİKSEL slot DEĞİŞMEZ;
        yalnızca LİDER rolü devreder (yeni lider kendi rank'inde kalır, rank
        0 boş kalabilir). ``pinned_leader`` verilirse (consensus kararı) o
        ajan tercih edilir; aksi hâlde en küçük agent_id.

        Args:
            pinned_leader: Dışarıdan (consensus) dayatılan lider; opsiyonel.

        Returns:
            Reallocation: yalnızca rol değişimleri (slot korunur).
        """
        r = Reallocation()
        leader = self._choose_leader(pinned_leader)
        if leader is None:
            r.notes.append('no_eligible_leader')
            self._append_degradation_note(r)
            return r
        self._set_leader(leader, r)
        r.notes.append('leader_elected:%d' % leader)
        self._append_degradation_note(r)
        return r

    def apply_leader(self, leader_id: int) -> Reallocation:
        """Consensus'un seçtiği lideri rol defterine İŞLER (seçim YAPMAZ).

        Lider KARARI consensus'undur (Beyza/ElectionResult). Bu metot o
        kararı yalnızca uygular: leader_id → LİDER, diğer rank'liler →
        FOLLOWER. Fiziksel slot korunur (şartname).

        Args:
            leader_id: Consensus'un seçtiği lider ajan kimliği.

        Returns:
            Reallocation: rol değişimleri (slot korunur). Lider henüz rank
            almadıysa yalnızca not döner.
        """
        r = Reallocation()
        entry = self._roster.get(leader_id)
        if entry is None or entry.rank < 0:
            r.notes.append('leader_not_ranked:%d' % leader_id)
            return r
        self._set_leader(leader_id, r)
        r.notes.append('leader_applied:%d' % leader_id)
        return r

    def has_leader(self) -> bool:
        """Rank atanmış ajanlar arasında lider olup olmadığını döner."""
        return any(
            e.role == ROLE_LEADER and e.rank >= 0
            for e in self._roster.values()
        )

    def _eligible_active(self) -> list[RosterEntry]:
        """Uygun + rank atanmış ajanları agent_id sırasıyla döner."""
        return sorted(
            (
                e for e in self._roster.values()
                if _eligible(e) and e.rank >= 0
            ),
            key=lambda e: e.agent_id,
        )

    def _choose_leader(self, pinned: int | None) -> int | None:
        """Lider adayı: pinned (uygunsa) yoksa en küçük id'li güvenli aktif."""
        cands = self._eligible_active()
        ids = [e.agent_id for e in cands]
        if pinned is not None and pinned in ids:
            return pinned
        return cands[0].agent_id if cands else None

    def _assign_leader(self, pinned: int | None, r: Reallocation) -> None:
        """assign_formation içinde lideri belirler ve uygular."""
        leader = self._choose_leader(pinned)
        if leader is not None:
            self._set_leader(leader, r)

    def _set_leader(self, leader_id: int, r: Reallocation) -> None:
        """Tek lider bırakır: leader_id → LİDER, diğer rank'liler → FOLLOWER.

        Yalnızca rolü değişen ajan delta'ya yazılır; slot (rank) korunur.
        """
        for entry in self._roster.values():
            if entry.rank < 0:
                continue
            desired = (
                ROLE_LEADER if entry.agent_id == leader_id
                else ROLE_FOLLOWER
            )
            if entry.role != desired:
                entry.role = desired
                r.role_map[entry.agent_id] = desired
                r.rank_map[entry.agent_id] = entry.rank
                if entry.agent_id not in r.changed_ids:
                    r.changed_ids.append(entry.agent_id)

    def _append_degradation_note(self, r: Reallocation) -> None:
        """Bozulma seviyesi OK değilse not ekler (şartname min-İHA)."""
        status = self.degradation_status()
        if status != DEGRADATION_OK:
            r.notes.append('degradation:%s' % status)
