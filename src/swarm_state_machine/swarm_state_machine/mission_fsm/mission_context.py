# Copyright 2026 Yelpence
"""mission_fsm_node ve mission_transitions icin ortak bellek."""

from dataclasses import dataclass, field
import time
from typing import Any, Optional

from .mission_states import MissionState, MissionType, QrTaskStep

_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDING = 12
_AGENT_STATE_LANDED = 13
# Ajanın "sürüyle birlikte" sayıldığı durumlar: havada, formasyonda (IN_SWARM)
# ya da QR görevini icra ediyor (EXECUTING_TASK). Bunların DIŞINDAKİ her durum
# (ayrıldı, iniyor, yerde bekliyor, tekrar arm oluyor, kalkıyor, failsafe)
# sürünün eksik olduğu anlamına gelir.
_AGENT_STATES_WITH_SWARM = frozenset({5, 6})


@dataclass
class MissionContext:
    """mission_fsm_node ve mission_transitions için ortak bellek."""

    agent_ids: list
    # NAVIGATE_TO_QR zaman asimi — YAPILANDIRILABILIR (2 Eylul 2026).
    # Yarisma varsayilani 300 sn: QR'a UCARAK gitmek zaman aliyor. Ama
    # QR'siz bir SINAMA ucusunda sürü o 300 saniyeyi formasyonda ASILI
    # geciriyor — hicbir bilgi uretmeden pil yakiyor ve ucusu 6.5 dakikaya
    # cikariyor. Test ucuslari icin kisaltilabilsin diye ctx'e alindi;
    # mission_transitions artik sabit yerine BUNU okuyor.
    navigate_timeout_s: float = 300.0
    # Hedef BILINMIYORKEN NAVIGATE'te beklenen sure. 0 = kod varsayilani
    # (_ROUTE_UNKNOWN_GRACE_S). QR tablosu yokken suru bu kadar formasyonda
    # asili durur, sonra RETURN_HOME'a gecer. Gelistirme ucuslarinda kisa
    # tutulur: operator disaridan "takildi mi?" ayrimini yapamiyor ve
    # bekleyemeyip elle land veriyor (2 Eylul, iki ucus boyle kesildi).
    rota_bilinmeyen_s: float = 0.0

    team_id: str = ''
    sitl_mode: bool = False

    state: MissionState = MissionState.UNKNOWN
    mission_type: MissionType = MissionType.UNKNOWN
    state_entry_time: float = field(default_factory=time.monotonic)

    agent_statuses: dict = field(default_factory=dict)

    last_accepted_qr_seq: int = 0
    # İşlenmekte olan QR'ın numarası. Tekrar okumaları elemek içindir; ayırt
    # edici ölçüt budur (qr_seq yayıncıya özeldir, sürüde her dronun kendi
    # sayacı vardır).
    last_accepted_qr_id: int = 0
    current_qr: Optional[Any] = None
    qr_task_step: QrTaskStep = QrTaskStep.NONE

    qr_coord_table: dict = field(default_factory=dict)
    next_qr_target: Optional[tuple] = None
    route_unknown: bool = False

    pause_return_state: MissionState = MissionState.NAVIGATE_TO_QR
    wait_deadline: Optional[float] = None
    # QR ALT-ADIMLARI ARASI BEKLEME (4 Eylul 2026).
    # Sartname QR belgesi `w`'yi "GOREVLER ARASI bekleme suresi" diye
    # tanimliyor ve sirayi sayiyor:
    #   1 formasyona gec  2 w bekle  3 manevra  4 w bekle
    #   5 irtifa          6 w bekle  7 sonraki QR
    # Yani uc gorevlik pakette `w` UC KEZ uygulaniyor. Bizde yalnizca
    # SONUNCUSU vardi (WAIT_AT_QR); aradaki iki bekleme eksikti, yani
    # w=4 icin 12 saniye yerine 4 saniye tutuyorduk.
    # Onemi: hakem her komut edilen durumu gorup puanliyor. Formasyonu
    # kurup hemen manevraya gecersek o formasyon net tutulmus sayilmayabilir.
    qr_step_bekleme_bitis: Optional[float] = None

    action_done: bool = False
    action_success: bool = False

    event_formation_reached: bool = False
    event_rotation_completed: bool = False

    # Şartname madde 17: QR çözülemezse eve dönüp rotayı baştan başlat.
    # restart_pending, RETURN_HOME'un başarısızlık (QR okunamadı) kaynaklı
    # olduğunu belirtir. max_restarts=0 → SINIRSIZ (şartname sınır koymaz);
    # >0 verilirse deneme sayısını sınırlar.
    restart_pending: bool = False
    restart_count: int = 0
    max_restarts: int = 0

    pending_command: int = 0
    abort_reason: str = ''

    def set_state(self, new_state: MissionState) -> None:
        """Durum gecisini uygular."""
        self.state = new_state
        self.state_entry_time = time.monotonic()
        self.action_done = False
        self.action_success = False
        self.event_formation_reached = False
        self.event_rotation_completed = False
        self.qr_task_step = QrTaskStep.NONE
        # Sifirlanmazsa yeni QR'in ilk adimi ONCEKI QR'in bekleme
        # damgasini devralir ve ya hic beklemez ya sonsuza kadar bekler.
        self.qr_step_bekleme_bitis = None

    def time_in_state(self) -> float:
        """Mevcut duruma giristen bu yana gecen saniyeyi doner."""
        return time.monotonic() - self.state_entry_time

    def lookup_qr_position(self, qr_id: int) -> Optional[tuple]:
        """QR numarasindan koordinati cozer."""
        return self.qr_coord_table.get(int(qr_id))

    @property
    def all_agents_seen(self) -> bool:
        """Her ajan icin en az bir durum mesaji alindiysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_state(self, state_value: int) -> bool:
        """Her ajan verilen AgentStatus state degerini bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == state_value for s in self.agent_statuses.values()
        )

    def all_agents_in_swarm(self) -> bool:
        """Tum ajanlar STATE_IN_SWARM ise True."""
        return self.all_agents_in_state(_AGENT_STATE_IN_SWARM)

    def swarm_incomplete(self) -> bool:
        """Sürüyle birlikte olmayan bir ajan varsa True."""
        if not self.agent_statuses:
            return False
        return any(
            s.state not in _AGENT_STATES_WITH_SWARM
            for s in self.agent_statuses.values()
        )

    def all_agents_landing(self) -> bool:
        """Tum ajanlar STATE_LANDING ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDING)

    def all_agents_landed(self) -> bool:
        """Tum ajanlar STATE_LANDED ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDED)

    def all_agents_healthy(self) -> bool:
        """Her ajan healthy=True bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def all_agents_origin_synced(self) -> bool:
        """Tum ajanlar SwarmOrigin'i uyguladiysa True."""
        if not self.agent_statuses:
            return False
        return all(
            s.origin_synced for s in self.agent_statuses.values()
        )

    def all_agents_home_set(self) -> bool:
        """Tum ajanlarin home_set'i True ise True."""
        if not self.agent_statuses:
            return False
        return all(s.home_set for s in self.agent_statuses.values())

    def all_agents_gps_ok(self) -> bool:
        """Tum ajanlarda 3D GPS fix ve HDOP < 1.5 ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.gps_fix_type >= 3 and s.gps_hdop < 1.5
            for s in self.agent_statuses.values()
        )
