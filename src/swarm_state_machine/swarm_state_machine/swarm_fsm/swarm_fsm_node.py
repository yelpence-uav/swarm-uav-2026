# Copyright 2026 Yelpence
"""ROS2 node that runs the FSM for the swarm."""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    LeaderHeartbeat,
    SwarmOrigin,
    SwarmState as SwarmStateMsg,
    SystemEvent,
)

# swarm_core'dan geliyor: formasyon geometrisi ve secim sirasi TEK kaynakta
# dursun. Kopyalamak CLAUDE.md §9'un yasakladigi sey — formation_node ile
# swarm_fsm ayni formasyonu farkli hesaplarsa metrik sessizce yalan soyler.
from swarm_core.consensus.election import seq_kabul
from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    rotate_offset,
)

from .swarm_context import AgentStatusCache, SwarmContext
from .swarm_states import (
    AIRBORNE_SWARM_STATES,
    FormationType,
    SwarmState,
)
from .swarm_transitions import evaluate_transitions
from ..agent_fsm.agent_states import AgentState, FORMATION_ACTIVE_STATES

_M_PER_DEG_LAT = 111_320.0

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# BEST_EFFORT: agent status proxy'den (/public) BEST_EFFORT geliyor (kayıplı
# kanal). RELIABLE abone best-effort yayıncıyla eşleşmez → status alınamaz.
_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# --- Sağlık eşikleri ---
_AGENT_STALE_TIMEOUT_S = 3.0
_FORMATION_STABLE_THRESHOLD_M = 1.5
_FORMATION_REACHED_THRESHOLD_M = 1.0


class SwarmFsmNode(Node):
    """Sürü seviyesi FSM node'u."""

    def __init__(self) -> None:
        super().__init__('swarm_fsm_node')

        self._declare_params()

        self._ctx = SwarmContext(
            expected_agent_count=self._expected_agent_count,
            sitl_mode=self._sitl_mode,
            heartbeat_timeout_s=self._heartbeat_timeout_ms / 1000.0,
            min_healthy_ratio=self._min_healthy_ratio,
        )

        # KAYNAK BASINA secim sirasi: {ajan: (incarnation, en_yuksek_seq)}.
        #
        # Onceden tek global sayac vardi ve su hataya aciti: consensus_node
        # yeniden baslayinca sequence_num 1'e doner, `1 <= max` oldugu icin
        # BUTUN secim mesajlari "bayat" sayilip sessizce dusuyordu —
        # swarm_fsm lider degisimlerine kalici olarak sagir kaliyordu.
        # `docker restart` sonrasi her seferinde olusan gercek bir durum.
        # consensus'ta bu zaten cozulmustu (election.seq_kabul); ayni
        # fonksiyon burada da kullaniliyor, iki yerde iki mantik olmasin.
        self._election_seen: dict[int, tuple[int, int]] = {}
        # Son gorulen formasyon komutu — kalite metriginin hedef kaynagi.
        self._son_formasyon: FormationCommand | None = None
        self._origin_lat = None
        self._origin_lon = None

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        # IKISI BIRDEN yaziliyor: 15 Agustos'ta bu iki sayinin ayni
        # parametreden gelmesi FORMING'de kalici takilma uretti ve logda
        # yalniz biri gorundugu icin teshis uzadi.
        self.get_logger().info(
            f'SwarmFsmNode baslatildi: kimlik araligi 1..'
            f'{self._agent_count}, beklenen ucak '
            f'{self._expected_agent_count}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanımlar ve okur."""
        # agent_count = KIMLIK ARALIGI (1..N). Abonelikler bundan turuyor:
        #   for aid in range(1, agent_count + 1) -> /swarm/public/drone{aid}/status
        # Ucaklarimiz 1 ve 3 (ylp01 yerde ama kimligi 2), yani yerde ucak
        # olsa bile 3 KALMALI — 2 yazilsa drone3 HIC dinlenmezdi.
        # agent_id = BU ucagin kimligi. 15 Agustos'a kadar bu dugumde YOKTU
        # ve sonucu tehlikeliydi: swarm_fsm yalniz /swarm/public/... dinliyor,
        # ucagin KENDI durumu ise oraya (bilerek) tasinmiyor — cunku kendi
        # status'unu kendi public konusuna dusurmek, kacinmanin ucagi komsu
        # sanip KENDINDEN kacmasina yol acardi (bkz. ic_dis_kopru.py).
        # Yani swarm_fsm yalnizca KOMSULARI goruyordu. Iki ucakla bu demek ki
        # tek komsu; o komsu 3 sn bayatlayinca (mesh ~%30 kayipli)
        #     active_agent_count == 0 and total > 0
        # dali tetikleniyor ve TUM SURUYE EVENT_EMERGENCY_LAND yayinlaniyor.
        # O dalin havada olma sarti da YOK. Kopru acilinca bu olay artik
        # agent_fsm'e gercekten ULASIYOR, yani zararsiz gurultu olmaktan
        # cikti. consensus ayni sorunu zaten kendi kaydini internal'dan
        # okuyarak cozmustu (consensus_node.py:139); ayni yol.
        self.declare_parameter('agent_id', 0)
        self.declare_parameter('agent_count', 3)
        # expected_agent_count = KAC UCAK GERCEKTEN UCUYOR. Ayri parametre
        # olmasinin sebebi (15 Agustos'ta olculdu): tek deger iki isi birden
        # yapamiyordu ve ikisi CELISIYORDU —
        #   formation_reached: active_agent_count >= expected  -> 2 >= 3 FALSE
        #   saglik orani     : healthy / expected < 0.5 -> SWARM FAILSAFE
        # Ilki FORMING'den cikmayi imkansiz kiliyor, ikincisi iki ucaktan
        # biri bozulunca (1/3 = 0.33) tum suruye ACIL INIS yayinliyordu.
        # 0 = "agent_count'u kullan" (eski davranis).
        self.declare_parameter('expected_agent_count', 0)
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('heartbeat_timeout_ms', 300.0)
        self.declare_parameter('min_healthy_ratio', 0.5)
        # Okbasi/V kanat acisi — formation_node ile AYNI olmali, yoksa iki
        # dugum ayni formasyonu farkli yerde sanir.
        self.declare_parameter('wing_alpha_deg', 45.0)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._agent_count = self.get_parameter('agent_count').value
        _beklenen = int(self.get_parameter('expected_agent_count').value)
        self._expected_agent_count = (
            _beklenen if _beklenen > 0 else self._agent_count
        )
        self._wing_alpha_rad = math.radians(
            float(self.get_parameter('wing_alpha_deg').value)
        )
        self._tick_hz = self.get_parameter('tick_hz').value
        self._sitl_mode = self.get_parameter('sitl_mode').value
        self._heartbeat_timeout_ms = (
            self.get_parameter('heartbeat_timeout_ms').value
        )
        self._min_healthy_ratio = (
            self.get_parameter('min_healthy_ratio').value
        )

    def _setup_publishers(self) -> None:
        """Aciklama: SwarmState ve SystemEvent publisher'larını oluşturur."""
        self._state_pub = self.create_publisher(
            SwarmStateMsg,
            '/swarm/internal/state',
            _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abonelikleri oluşturur."""
        for aid in range(1, self._agent_count + 1):
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                self._make_agent_cb(aid),
                _STATUS_QOS,
            )

        # KENDI durumu AYRICA internal'dan. Yukaridaki dongu yalniz komsulari
        # getirir; kendi status'umuz public'e tasinmiyor (kacinma bizi komsu
        # sanmasin diye). Bu abonelik olmadan iki ucakli surude tek komsu
        # bayatlayinca active_agent_count 0 oluyor ve tum suruye acil inis
        # yayinlaniyordu. agent_id verilmezse (0) atlanir — eski davranis.
        if self._agent_id > 0:
            self.create_subscription(
                AgentStatus,
                f'/swarm/internal/drone{self._agent_id}/status',
                self._make_agent_cb(self._agent_id),
                _STATUS_QOS,
            )

        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            LeaderHeartbeat,
            '/swarm/public/leader/heartbeat',
            self._on_heartbeat,
            _HEARTBEAT_QOS,
        )

        self.create_subscription(
            ElectionResult,
            '/swarm/public/election/result',
            self._on_election,
            _ELECTION_QOS,
        )

        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )

        # FORMASYON KOMUTU — 15 Agustos'a kadar bu abonelik YOKTU ve
        # ctx.active_formation hicbir yerde ATANMIYORDU. Sonucu: sabit
        # ofset bloklari (OKBASI 3 m / CIZGI 4 m) hic calismiyordu (olu kod),
        # compute_formation_quality her ajani MERKEZE gore olcuyordu ve
        # 12 m aralikta hata ~6 m cikiyordu. Esikler 1.5 / 1.0 m oldugu icin
        # formation_stable ve formation_reached HER ZAMAN False'ti — yani
        # suru FORMING'den hic cikamiyordu.
        # BEST_EFFORT — RELIABLE DEGIL. Kural: /swarm/public/... dinleyen
        # herkes BEST_EFFORT olmali, cunku o konularin mesh kaynagi
        # esp32_bridge ve o _MESH_QOS ile yani BEST_EFFORT yayinliyor.
        # RELIABLE abone + BEST_EFFORT yayinci ESLESMEZ ve konu SESSIZCE bos
        # kalir. Bu abonelik once RELIABLE yazildi ve uctaki tarama tam bunu
        # yakaladi (15 Agustos):
        #   "'/swarm/public/formation/target' offering incompatible QoS.
        #    No messages will be received from it. policy: RELIABILITY"
        # Ters yon sorunsuz: RELIABLE yayinci + BEST_EFFORT abone uyumlu,
        # o yuzden ic_dis_kopru RELIABLE yayinlamaya devam ediyor.
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _STATUS_QOS,
        )

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """Aktif formasyon komutunu saklar (kalite metrigi bunu kullanir)."""
        self._son_formasyon = msg
        try:
            self._ctx.active_formation = FormationType(int(msg.formation_type))
        except ValueError:
            self._ctx.active_formation = FormationType.UNKNOWN

    def _formasyon_ofsetleri(
        self,
    ) -> dict[int, tuple[float, float, float]] | None:
        """Aktif komuttan ajan basina hedef ofseti uretir (NED, merkeze gore).

        Iki kaynak, sirayla:
          1. Liderin komuta GOMDUGU atama (offset_x/y/z) — otoriter olan bu,
             cunku formation_node da onu kullaniyor (_leader_offsets).
          2. Yoksa formation_geometry.compute_slot_offsets ile agent_ids
             sirasina gore uret (fallback).

        Sonra iki islem:
          * heading kadar DONDUR — slot ofsetleri govde cercevesinde,
            formation_node da dunyaya cevirirken rotate_offset kullaniyor.
          * ORTALAMAYI CIKAR — slotlar lider merkezli (ilk slot 0,0,0),
            sifir ortalamali DEGIL. Iki ucaklik cizgide ortalama (0, s/2),
            yani 12 m aralikta 6 m SABIT YANLILIK. compute_formation_quality
            hedefi centroid + ofset olarak kurdugu icin bu yanlilik dogrudan
            hataya yaziliyordu. Ortalamayi cikarinca metrik saf SEKIL olcusu
            olur: "ajanlar birbirine gore dogru yerde mi" — mutlak konum
            hatasi navigasyonun isi, formasyon kalitesinin degil.
        """
        msg = self._son_formasyon
        if msg is None:
            return None
        ids = [int(a) for a in msg.agent_ids]
        if not ids:
            return None

        ham: list[tuple[float, float, float]] | None = None
        if (len(msg.offset_x) >= len(ids)
                and len(msg.offset_y) >= len(ids)
                and len(msg.offset_z) >= len(ids)):
            ham = [
                (float(msg.offset_x[i]),
                 float(msg.offset_y[i]),
                 float(msg.offset_z[i]))
                for i in range(len(ids))
            ]
        else:
            try:
                ham = list(compute_slot_offsets(
                    int(msg.formation_type), len(ids),
                    float(msg.spacing_m), self._wing_alpha_rad,
                ))
            except ValueError:
                return None

        heading_rad = math.radians(float(msg.heading_deg))
        donmus = []
        for (ox, oy, oz) in ham:
            wx, wy = rotate_offset(ox, oy, heading_rad)
            donmus.append((wx, wy, float(oz)))

        n = len(donmus)
        mx = sum(o[0] for o in donmus) / n
        my = sum(o[1] for o in donmus) / n
        mz = sum(o[2] for o in donmus) / n
        return {
            ids[i]: (donmus[i][0] - mx,
                     donmus[i][1] - my,
                     donmus[i][2] - mz)
            for i in range(n)
        }

    def _tick(self) -> None:
        """FSM ana dongusu."""
        ctx = self._ctx

        self._check_health()

        next_s = evaluate_transitions(ctx)
        if next_s is not None and next_s != ctx.swarm_state:
            self._transition(next_s)

        self._publish_state()

    def _check_health(self) -> None:
        """Sürü geneli sağlık kontrollerini çalıştırır."""
        if self._check_agent_health():
            return

        self._update_formation_metrics()

    def _check_agent_health(self) -> bool:
        """Ajanlarin saglik durumunu kontrol eder."""
        ctx = self._ctx
        if not ctx.agents:
            return False

        total = len(ctx.agents)

        stale = [
            aid for aid, a in ctx.agents.items()
            if a.is_stale(_AGENT_STALE_TIMEOUT_S)
        ]
        # 🔴 BU SAYI CANLILIK OLCER, formasyona uygunluk DEGIL. Tek sart
        # bayatlik; yerde IDLE'daki ucaklar da sayilir. Formasyona uygun
        # olanlar AYRI hesaplaniyor (active_agent_ids, ~satir 715, dort
        # sartli). Ikisi ayni mesajda benzer isimle durdugu icin 3 Eylul'de
        # mission1 karistirdi ve HOME'u (0,0)'a kilitledi. Sozlesme notu:
        # SwarmState.msg::active_agent_count.
        ctx.active_agent_count = total - len(stale)

        if ctx.active_agent_count == 0 and total > 0:
            if ctx.swarm_state != SwarmState.FAILSAFE:
                reason = 'Tüm ajanlarla iletişim kesildi'
                self.get_logger().error(
                    f'[SWARM FAILSAFE] {reason}'
                )
                self._transition(SwarmState.FAILSAFE)
                self._pub_event(
                    SystemEvent.EVENT_EMERGENCY_LAND,
                    SystemEvent.SEVERITY_EMERGENCY,
                    reason,
                )
            return True

        if (ctx.swarm_state in AIRBORNE_SWARM_STATES
                and ctx.active_agent_count > 0):
            healthy = ctx.count_healthy_agents()
            ratio = healthy / ctx.expected_agent_count
            if ratio < ctx.min_healthy_ratio:
                if ctx.swarm_state != SwarmState.FAILSAFE:
                    reason = (
                        f'Sağlıklı ajan oranı düşük: '
                        f'{healthy}/{ctx.expected_agent_count}'
                    )
                    self.get_logger().error(
                        f'[SWARM FAILSAFE] {reason}'
                    )
                    self._transition(SwarmState.FAILSAFE)
                    self._pub_event(
                        SystemEvent.EVENT_EMERGENCY_LAND,
                        SystemEvent.SEVERITY_EMERGENCY,
                        reason,
                    )
                return True

        kill_agents = [
            aid for aid, a in ctx.agents.items()
            if a.kill_switch_active and not a.is_stale()
        ]
        if (kill_agents
                and ctx.swarm_state in AIRBORNE_SWARM_STATES):
            if ctx.swarm_state != SwarmState.FAILSAFE:
                reason = (
                    f'Kill switch aktif: {kill_agents}'
                )
                self.get_logger().error(
                    f'[SWARM FAILSAFE] {reason}'
                )
                self._transition(SwarmState.FAILSAFE)
                self._pub_event(
                    SystemEvent.EVENT_KILL_SWITCH_ACTIVATED,
                    SystemEvent.SEVERITY_EMERGENCY,
                    reason,
                )
            return True

        failsafe_count = ctx.count_agents_in_state(AgentState.FAILSAFE)
        ctx.emergency_active = failsafe_count > 0

        if stale:
            self.get_logger().warn(
                f'[SWARM] Stale ajanlar: {stale}'
            )

        return False

    def _update_formation_metrics(self) -> None:
        """Centroid ve formasyon kalite metriklerini gunceller."""
        ctx = self._ctx
        ctx.compute_centroid()
        # B17 (30 Agustos 2026): formation_heading_deg TANIMLIYDI ama
        # hicbir yerde ATANMIYORDU — SwarmState kalici 0.0 tasiyordu.
        ctx.compute_heading()

        # Ofsetler artik AKTIF KOMUTTAN geliyor (aralik, heading ve atama
        # dahil). Onceki sabit sozlukler (OKBASI 3 m / CIZGI 4 m, ajan 1/2/3
        # gomulu) silindi: hem aralikimiz 12 m, hem de active_formation hic
        # atanmadigi icin o bloklar zaten HIC CALISMIYORDU.
        offsets = self._formasyon_ofsetleri()

        ctx.compute_formation_quality(target_offsets=offsets)

        ctx.formation_stable = (
            ctx.formation_max_error_m
            < _FORMATION_STABLE_THRESHOLD_M
        )

        if ctx.swarm_state == SwarmState.FORMING:
            ctx.formation_reached = (
                ctx.formation_max_error_m
                < _FORMATION_REACHED_THRESHOLD_M
                and ctx.formation_stable
                and ctx.active_agent_count
                >= ctx.expected_agent_count
            )

    def _transition(self, new_state: SwarmState) -> None:
        """Durum gecisini uygular."""
        old = self._ctx.swarm_state
        self._ctx.set_state(new_state)

        if new_state == SwarmState.IDLE:
            self._ctx.mission_active = False
            self._ctx.formation_reached = False
            self._ctx.rotation_active = False
            self._ctx.current_qr_id = 0
            self._ctx.current_qr_seq = 0

        elif new_state == SwarmState.MISSION_COMPLETE:
            self._ctx.mission_active = False
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev tamamlandı',
            )

        elif new_state == SwarmState.NAVIGATING:
            self._ctx.rotation_active = False

        elif new_state == SwarmState.FAILSAFE:
            self._ctx.emergency_active = True

        self.get_logger().info(
            f'[SWARM] {old.name} -> {new_state.name}'
        )

    def _make_agent_cb(self, agent_id: int):
        """Kapatma ile callback olusturur."""
        def _cb(msg: AgentStatus) -> None:
            self._on_agent_status(agent_id, msg)
        return _cb

    def _on_agent_status(
        self,
        agent_id: int,
        msg: AgentStatus,
    ) -> None:
        """Aciklama: AgentStatus telemetrisini context'e yazar."""
        cache = self._ctx.agents.get(agent_id)
        if cache is None:
            cache = AgentStatusCache(agent_id=agent_id)
            self._ctx.agents[agent_id] = cache

        cache.state = msg.state
        cache.role = msg.role
        cache.armed = msg.armed
        cache.healthy = msg.healthy
        cache.px4_link_ok = msg.px4_link_ok
        cache.gcs_link_ok = msg.gcs_link_ok
        cache.offboard_active = msg.offboard_active
        cache.failsafe_active = msg.failsafe_active
        cache.origin_synced = msg.origin_synced

        cache.pos_x = msg.pos_x
        cache.pos_y = msg.pos_y
        cache.pos_z = msg.pos_z
        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            cache.lat_deg = float(msg.lat_deg)
            cache.lon_deg = float(msg.lon_deg)
        cache.vel_x = msg.vel_x
        cache.vel_y = msg.vel_y
        cache.vel_z = msg.vel_z
        # B17: heading CACHE'E ALINMIYORDU, bu yuzden compute_heading()
        # yazilamiyordu ve formation_heading_deg kalici 0.0 idi.
        cache.heading_deg = msg.heading_deg
        cache.heading_deg = msg.heading_deg

        cache.battery_voltage_v = msg.battery_voltage_v
        cache.battery_percent = msg.battery_percent

        cache.oscillation_detected = msg.oscillation_detected
        cache.unstable_flight = msg.unstable_flight
        cache.kill_switch_active = msg.kill_switch_active
        cache.rc_link_ok = msg.rc_link_ok

        cache.last_update = time.monotonic()

    def _on_event(self, msg: SystemEvent) -> None:
        """Aciklama: SystemEvent olaylarini isler."""
        ctx = self._ctx
        eid = msg.event_type

        ctx.last_event_type = eid
        ctx.last_event_severity = msg.severity
        ctx.last_event_source = msg.source_agent_id
        ctx.last_event_value = msg.value
        ctx.last_event_has_position = msg.has_position
        if msg.has_position:
            ctx.last_event_pos_x = msg.pos_x
            ctx.last_event_pos_y = msg.pos_y
            ctx.last_event_pos_z = msg.pos_z
        ctx.last_event_message = msg.message

        if eid == SystemEvent.EVENT_FORMATION_REACHED:
            ctx.formation_reached = True

        elif eid == SystemEvent.EVENT_FORMATION_FAILED:
            ctx.formation_reached = False
            ctx.status_text = 'Formasyon başarısız'

        elif eid == SystemEvent.EVENT_ROTATION_STARTED:
            ctx.rotation_active = True

        elif eid == SystemEvent.EVENT_ROTATION_COMPLETED:
            ctx.rotation_active = False

        elif eid == SystemEvent.EVENT_MISSION_STARTED:
            ctx.mission_active = True
            ctx.active_mission = msg.message or 'active'

        elif eid == SystemEvent.EVENT_MISSION_COMPLETED:
            ctx.mission_active = False

        elif eid == SystemEvent.EVENT_QR_PARSED:
            ctx.current_qr_seq = (
                int(msg.value) if msg.value > 0 else 0
            )

        elif eid == SystemEvent.EVENT_RTL_TRIGGERED:
            if msg.target_agent_id == 0:
                ctx.pending_rtl = True

        elif eid == SystemEvent.EVENT_EMERGENCY_LAND:
            if msg.target_agent_id == 0:
                ctx.pending_land = True

        elif eid == SystemEvent.EVENT_FAILSAFE_CLEARED:
            ctx.emergency_active = False
            ctx.status_text = ''

        elif eid == SystemEvent.EVENT_LEADER_CHANGED:
            ctx.status_text = msg.message or 'Lider değişti'

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Swarm origin referansini kaydeder."""
        if msg.valid:
            self._origin_lat = float(msg.origin_lat_deg)
            self._origin_lon = float(msg.origin_lon_deg)

    def _to_shared_ned(self, lat: float, lon: float) -> tuple[float, float]:
        """GPS lat/lon to shared NED."""
        if self._origin_lat is None:
            return 0.0, 0.0
        d_lat = lat - self._origin_lat
        d_lon = lon - self._origin_lon
        north = d_lat * _M_PER_DEG_LAT
        cos_o = math.cos(math.radians(self._origin_lat))
        east = d_lon * _M_PER_DEG_LAT * cos_o
        return north, east

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Heartbeat sinyalini isler."""
        ctx = self._ctx
        ctx.leader_id = msg.leader_id
        ctx.last_heartbeat_time = time.monotonic()

        if msg.election_round > ctx.election_round:
            ctx.election_round = msg.election_round

    def _on_election(self, msg: ElectionResult) -> None:
        """Secim sonucunu isler."""
        ctx = self._ctx

        kaynak = int(msg.triggered_by_agent_id)
        inc = int(msg.incarnation)
        kabul, inc_degisti = seq_kabul(
            self._election_seen, kaynak, inc, int(msg.sequence_num)
        )
        if inc_degisti:
            self.get_logger().info(
                f'[SWARM] ajan {kaynak} yeniden başlamış '
                f'(incarnation -> {inc}), seq sayacı sıfırlandı'
            )
        if not kabul:
            self.get_logger().warn(
                f'[SWARM] Bayat election mesajı: kaynak={kaynak} '
                f'seq={msg.sequence_num}'
            )
            return

        self._election_seen[kaynak] = (inc, int(msg.sequence_num))

        old_leader = ctx.leader_id
        ctx.leader_id = msg.new_leader_id
        ctx.election_round = msg.election_round
        ctx.last_heartbeat_time = time.monotonic()

        if old_leader != msg.new_leader_id:
            self.get_logger().info(
                f'[SWARM] Lider değişti: {old_leader} -> '
                f'{msg.new_leader_id}'
            )
            self._pub_event(
                SystemEvent.EVENT_LEADER_CHANGED,
                SystemEvent.SEVERITY_INFO,
                f'Yeni lider: {msg.new_leader_id}',
            )

    def _publish_state(self) -> None:
        """Durumu yayinlar."""
        ctx = self._ctx
        m = SwarmStateMsg()
        m.stamp = self.get_clock().now().to_msg()

        m.swarm_state = int(ctx.swarm_state)
        m.leader_id = ctx.leader_id
        m.active_agent_count = ctx.active_agent_count
        m.active_formation = int(ctx.active_formation)

        m.mission_active = ctx.mission_active
        m.formation_reached = ctx.formation_reached
        m.formation_stable = ctx.formation_stable
        m.emergency_active = ctx.emergency_active

        m.centroid_x = ctx.centroid_x
        m.centroid_y = ctx.centroid_y
        m.centroid_z = ctx.centroid_z
        m.formation_heading_deg = ctx.formation_heading_deg

        m.formation_max_error_m = ctx.formation_max_error_m
        m.formation_avg_error_m = ctx.formation_avg_error_m
        m.formation_heading_error_deg = (
            ctx.formation_heading_error_deg
        )

        # agents[] boş — 250 byte ESP-NOW limiti (Kural 4)

        # active_agent_ids + paralel pozisyon dizileri.
        # Decision B: a.healthy tek bayrak (agent_fsm aggregate'i).
        active_agents = [
            a
            for a in sorted(ctx.agents.values(), key=lambda x: x.agent_id)
            if a.healthy
            and a.origin_synced
            and not a.is_stale()
            and a.state in FORMATION_ACTIVE_STATES
        ]
        # ⚠️ Bu liste active_agent_count ILE AYNI KUMEYI VERMEZ (yukarida
        # dort sart var, orada yalniz bayatlik). Bkz. SwarmState.msg.
        m.active_agent_ids = [a.agent_id for a in active_agents]

        shared_positions = []
        for a in active_agents:
            has_coords = a.lat_deg != 0.0 or a.lon_deg != 0.0
            if self._origin_lat is not None and has_coords:
                n, e = self._to_shared_ned(a.lat_deg, a.lon_deg)
                shared_positions.append((n, e, float(a.pos_z)))
            else:
                shared_positions.append(
                    (float(a.pos_x), float(a.pos_y), float(a.pos_z))
                )
        m.agent_pos_x = [p[0] for p in shared_positions]
        m.agent_pos_y = [p[1] for p in shared_positions]
        m.agent_pos_z = [p[2] for p in shared_positions]

        m.active_mission = ctx.active_mission
        m.status_text = ctx.status_text

        m.current_qr_id = ctx.current_qr_id
        m.current_qr_seq = ctx.current_qr_seq

        m.last_event_type = ctx.last_event_type
        m.last_event_severity = ctx.last_event_severity
        m.last_event_source = ctx.last_event_source
        m.last_event_value = ctx.last_event_value
        m.last_event_pos_x = ctx.last_event_pos_x
        m.last_event_pos_y = ctx.last_event_pos_y
        m.last_event_pos_z = ctx.last_event_pos_z
        m.last_event_has_position = ctx.last_event_has_position
        m.last_event_message = ctx.last_event_message

        self._state_pub.publish(m)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """Aciklama: SystemEvent yayinlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.source_module = 'swarm_fsm'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SwarmFsmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
