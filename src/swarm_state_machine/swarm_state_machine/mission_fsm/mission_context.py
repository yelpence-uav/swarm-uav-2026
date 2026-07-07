"""mission_context.py — MissionFSM çalışma zamanı durum kabı."""

from dataclasses import dataclass, field
import time
from typing import Any, Optional

from .mission_states import MissionState, MissionType, QrTaskStep

# AgentStatus.msg STATE_* sabitleriyle eşleşmeli.
_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDING = 12
_AGENT_STATE_LANDED = 13


@dataclass
class MissionContext:
    """mission_fsm_node ve mission_transitions için ortak bellek.

    mission_fsm_node'daki callback'ler bu nesneye yazar.
    mission_transitions fonksiyonları yalnızca okur.

    Args:
        agent_ids (list): Aktif drone ID'leri, örn. [1, 2, 3].
        team_id (str): QR filtrelemesinde kullanılan takım ID'si.
        sitl_mode (bool): True ise GPS/origin/home kontrolleri atlanır.
    """

    agent_ids: list

    team_id: str = ''
    sitl_mode: bool = False

    state: MissionState = MissionState.UNKNOWN
    mission_type: MissionType = MissionType.UNKNOWN
    state_entry_time: float = field(default_factory=time.monotonic)

    agent_statuses: dict = field(default_factory=dict)

    last_accepted_qr_seq: int = 0
    current_qr: Optional[Any] = None
    qr_task_step: QrTaskStep = QrTaskStep.NONE

    # QR konum tablosu (Akış B) — operatör YKİ'den girer, mesh/proxy ile ulaşır.
    # Anahtar: QR numarası (int) -> değer: (lat_deg, lon_deg). Şartname yalnız
    # enlem/boylam paylaşır; irtifa QR görev komutundan (alt) gelir.
    qr_coord_table: dict = field(default_factory=dict)
    # current_qr.next_qr için tablodan çözülen hedef (lat_deg, lon_deg) ya da None.
    next_qr_target: Optional[tuple] = None
    # Rota çözülemedi: gidilmesi gereken QR'ın konumu tabloda yok. Şartname:
    # rota bilinemezse ev konumuna dön. Failsafe geçişi bu bayrağı okur.
    route_unknown: bool = False

    pause_return_state: MissionState = MissionState.NAVIGATE_TO_QR
    wait_deadline: Optional[float] = None

    action_done: bool = False
    action_success: bool = False

    event_formation_reached: bool = False
    event_rotation_completed: bool = False

    pending_command: int = 0
    abort_reason: str = ''

    def set_state(self, new_state: MissionState) -> None:
        """Durum geçişini uygular ve geçici bayrakları sıfırlar.

        Args:
            new_state (MissionState): Geçilecek hedef durum.
        """
        self.state = new_state
        self.state_entry_time = time.monotonic()
        self.action_done = False
        self.action_success = False
        self.event_formation_reached = False
        self.event_rotation_completed = False
        self.qr_task_step = QrTaskStep.NONE

    def time_in_state(self) -> float:
        """Mevcut duruma girişten bu yana geçen saniyeyi döner."""
        return time.monotonic() - self.state_entry_time

    def lookup_qr_position(self, qr_id: int) -> Optional[tuple]:
        """QR numarasından paylaşılan tablodan konumu çözer (Akış B lookup).

        QR mesajı yalnızca `next_qr` numarasını verir; o numaranın fiziksel
        konumu (lat/lon) operatörün YKİ'den girdiği bu tablodan bulunur.

        Args:
            qr_id (int): Aranan QR numarası (örn. current_qr.next_qr).

        Returns:
            Optional[tuple]: (lat_deg, lon_deg); tablo boşsa ya da numara
            tabloda yoksa None (rota bilinemez -> failsafe tetiklenmeli).
        """
        return self.qr_coord_table.get(int(qr_id))

    @property
    def all_agents_seen(self) -> bool:
        """Her ajan için en az bir durum mesajı alındıysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_state(self, state_value: int) -> bool:
        """Her ajan verilen AgentStatus state değerini bildiriyorsa True.

        Args:
            state_value (int): Karşılaştırılacak AgentStatus.STATE_* sabiti.

        Returns:
            bool: Henüz hiç durum alınmadıysa False.
        """
        if not self.agent_statuses:
            return False
        return all(
            s.state == state_value for s in self.agent_statuses.values()
        )

    def all_agents_in_swarm(self) -> bool:
        """Tüm ajanlar STATE_IN_SWARM ise True (kalkış tamamlandı)."""
        return self.all_agents_in_state(_AGENT_STATE_IN_SWARM)

    def all_agents_landing(self) -> bool:
        """Tüm ajanlar STATE_LANDING ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDING)

    def all_agents_landed(self) -> bool:
        """Tüm ajanlar STATE_LANDED ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDED)

    def all_agents_healthy(self) -> bool:
        """Her ajan healthy=True bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def all_agents_origin_synced(self) -> bool:
        """Tüm ajanlar paylaşılan SwarmOrigin'i uyguladıysa True."""
        if not self.agent_statuses:
            return False
        return all(
            s.origin_synced for s in self.agent_statuses.values()
        )

    def all_agents_home_set(self) -> bool:
        """Tüm ajanların geçerli RTL ev konumu varsa True."""
        if not self.agent_statuses:
            return False
        return all(s.home_set for s in self.agent_statuses.values())

    def all_agents_gps_ok(self) -> bool:
        """Tüm ajanlarda 3D GPS fix ve HDOP < 1.5 ise True.

        Returns:
            bool: Henüz hiç durum alınmadıysa False.
        """
        if not self.agent_statuses:
            return False
        return all(
            s.gps_fix_type >= 3 and s.gps_hdop < 1.5
            for s in self.agent_statuses.values()
        )
