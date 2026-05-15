"""mission_context.py — Mission FSM'nin tum anlık durumu tek bir yerde.

MissionContext bir hafiza kutusudur.
  mission_fsm_node icindeki callback'ler bu kutuya YAZAR.
  mission_transitions icindeki fonksiyonlar bu kutudan OKUR.

ROS2 import'u yoktur; bu sayede birim testleri ROS2 kurulu olmadan calisir.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .mission_states import MissionState, MissionType, QrTaskStep


# AgentStatus.msg'den import edilmeden kullanmak icin sabit degerler.
# UYARI: AgentStatus.msg degisirse burasi da guncellenmelidir.
_AGENT_STATE_IN_SWARM = 5   # drone surude, goreve hazir
_AGENT_STATE_LANDING = 12   # drone inis surecinde
_AGENT_STATE_LANDED = 13    # drone yerde, motor kapali


@dataclass
class MissionContext:
    """
    Mission FSM'nin tum anlık durumunu tutar.

    Bu sinifin tek ornegi vardir; MissionFsmNode.__init__'te olusturulur.

    Zorunlu argümanlar:
        agent_ids: Surudeki drone ID listesi, ornegin [1, 2, 3]

    Istege bagli argümanlar:
        team_id:   QR mesaji filtrelemede kullanilir
        sitl_mode: True ise GPS/origin/home kontrolleri atlanir

    Ornek:
        ctx = MissionContext(agent_ids=[1, 2, 3], team_id='YELPENCE')
    """

    # ------------------------------------------------------------------
    # ZORUNLU ALANLAR
    # ------------------------------------------------------------------

    agent_ids: list  # hangi drone'larin mesajini bekliyoruz

    # ------------------------------------------------------------------
    # ISTEGE BAGLI ALANLAR
    # ------------------------------------------------------------------

    team_id: str = ""        # QR mesajindaki team_id ile eslesmelidir
    sitl_mode: bool = False  # True → simulasyon modu

    # ------------------------------------------------------------------
    # FSM DURUMU
    # ------------------------------------------------------------------

    # Dogrudan degistirme; set_state() kullan; aksi halde bayraklar temizlenmez.
    state: MissionState = MissionState.UNKNOWN
    mission_type: MissionType = MissionType.UNKNOWN
    state_entry_time: float = field(default_factory=time.monotonic)

    # ------------------------------------------------------------------
    # AJAN DURUMLARI
    # ------------------------------------------------------------------

    # { agent_id: AgentStatus } — her ajan kendi topic'inden mesaj gonderir
    agent_statuses: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # QR TAKIP
    # ------------------------------------------------------------------

    last_accepted_qr_seq: int = 0     # ayni QR'in iki kez islenmesini onler
    current_qr: Optional[Any] = None  # aktif QRMissionData; None ise QR henuz okunmadi
    qr_task_step: QrTaskStep = QrTaskStep.NONE

    # PAUSED state'ine girerken hangi state'teydiniz?
    # _from_paused() RESUME gelince buraya doner.
    pause_return_state: MissionState = MissionState.NAVIGATE_TO_QR

    # _on_state_entry(WAIT_AT_QR) tarafindan set edilir: time.monotonic() + qr.wait_s
    wait_deadline: Optional[float] = None

    # ------------------------------------------------------------------
    # ASENKRON EYLEM BAYRAKLARI
    # ------------------------------------------------------------------
    # Icra node'lari isi bitince event yayinlar; _on_event() bu bayraklari set eder.
    # set_state() her geciste bunlari temizler.

    action_done: bool = False     # is bitti mi?
    action_success: bool = False  # is basarili miydi?

    # ------------------------------------------------------------------
    # EVENT BAYRAKLARI
    # ------------------------------------------------------------------

    event_formation_reached: bool = False   # suru navigasyon hedefine vardi
    event_rotation_completed: bool = False  # formasyon rotasyonu tamamlandi

    # ------------------------------------------------------------------
    # FORMASYON TAKIP
    # ------------------------------------------------------------------

    current_formation_type: int = 1   # baslangic formasyon tipi (OKBASI=1)
    current_spacing_m: float = 5.0    # drone'lar arasi mesafe (metre)

    # ------------------------------------------------------------------
    # KONTROL
    # ------------------------------------------------------------------

    # GCS'ten gelen son TriggerMission.command degeri.
    # 0=yok, 1=START, 2=ABORT, 3=PAUSE, 4=RESUME, 5=RTL, 6=LAND
    pending_command: int = 0

    abort_reason: str = ""  # ABORTED state event mesajina yazilir

    # ------------------------------------------------------------------
    # GOREV 2 (SEMI_AUTONOMOUS)
    # ------------------------------------------------------------------

    latest_control_cmd: Optional[Any] = None  # son SwarmControlCommand mesaji
    last_control_cmd_time: float = 0.0

    # =================================================================
    # YARDIMCI METODLAR
    # =================================================================

    def set_state(self, new_state: MissionState) -> None:
        """
        State gecisini uygular ve gecici bayraklari sifirlar.

        Dogrudan ctx.state = ... yapma; bu metodu kullan.

        Args:
            new_state: Gecilecek hedef MissionState.
        """
        self.state = new_state
        self.state_entry_time = time.monotonic()
        self.action_done = False
        self.action_success = False
        self.event_formation_reached = False
        self.event_rotation_completed = False
        # EXECUTE_QR_TASK disindaki state'lerde NONE yayinlamak daha net sinyal verir.
        self.qr_task_step = QrTaskStep.NONE

    def time_in_state(self) -> float:
        """
        Su anki state'te kac saniye gectigini doner.

        time.monotonic() kullanilir; sistem saati degisimlerinden etkilenmez.

        Returns:
            Gecen sure (saniye, float).
        """
        return time.monotonic() - self.state_entry_time

    # ------------------------------------------------------------------
    # AJAN DURUM KONTROL METODLARI
    # ------------------------------------------------------------------

    @property
    def all_agents_seen(self) -> bool:
        """
        Tum beklenen ajan ID'lerinden en az bir mesaj alinip alinmadigini doner.

        Returns:
            Tum ID'ler agent_statuses'te varsa True; eksik varsa False.
        """
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_state(self, state_value: int) -> bool:
        """
        Tum ajanlarin verilen AgentStatus durum degerinde olup olmadigini doner.

        Args:
            state_value: Beklenen integer deger (ornegin 5=IN_SWARM).

        Returns:
            Tum ajanlar bu state'teyse True; hic ajan yoksa False.
        """
        if not self.agent_statuses:
            return False
        return all(s.state == state_value for s in self.agent_statuses.values())

    def all_agents_in_swarm(self) -> bool:
        """
        Tum ajanlarin IN_SWARM(5) state'inde olup olmadigini doner.

        NEREDE KULLANILIR:
            _from_synchronized_takeoff(): tum drone'lar IN_SWARM olunca
            NAVIGATE_TO_QR veya SEMI_AUTONOMOUS'a gec.
        """
        return self.all_agents_in_state(_AGENT_STATE_IN_SWARM)

    def all_agents_landing(self) -> bool:
        """
        Tum ajanlarin LANDING(12) state'inde olup olmadigini doner.

        NEREDE KULLANILIR:
            _from_return_home(): drone'lar alcalmaya baslarsa LANDING'e gec.
        """
        return self.all_agents_in_state(_AGENT_STATE_LANDING)

    def all_agents_landed(self) -> bool:
        """
        Tum ajanlarin LANDED(13) state'inde olup olmadigini doner.

        NEREDE KULLANILIR:
            _from_landing(): hepsi indi -> MISSION_COMPLETE.
        """
        return self.all_agents_in_state(_AGENT_STATE_LANDED)

    def all_agents_healthy(self) -> bool:
        """
        Tum ajanlarin healthy=True olup olmadigini doner.

        Returns:
            Tum ajanlar saglikli ise True; hic ajan yoksa False.
        """
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def all_agents_origin_synced(self) -> bool:
        """
        Tum ajanlarda NED koordinat orijininin senkronize olup olmadigini doner.

        Returns:
            Tum ajanlar origin_synced=True ise True; hic ajan yoksa False.
        """
        if not self.agent_statuses:
            return False
        return all(s.origin_synced for s in self.agent_statuses.values())

    def all_agents_home_set(self) -> bool:
        """
        Tum ajanlarda RTL icin home pozisyonunun set olup olmadigini doner.

        Returns:
            Tum ajanlar home_set=True ise True; hic ajan yoksa False.
        """
        if not self.agent_statuses:
            return False
        return all(s.home_set for s in self.agent_statuses.values())

    def all_agents_gps_ok(self) -> bool:
        """
        Tum ajanlarda GPS kalitesinin arming icin yeterli olup olmadigini doner.

        Kriterler: gps_fix_type >= 3 (3D fix) VE gps_hdop < 1.5

        Returns:
            Tum ajanlar GPS kriterlerini karsiliyorsa True; hic ajan yoksa False.
        """
        if not self.agent_statuses:
            return False
        return all(
            s.gps_fix_type >= 3 and s.gps_hdop < 1.5
            for s in self.agent_statuses.values()
        )
