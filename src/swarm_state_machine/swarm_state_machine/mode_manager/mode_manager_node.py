# Copyright 2026 Yelpence
"""Semi-autonomous suru kontrol koordinator dugumu."""

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

from std_msgs.msg import Bool, UInt8

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_UNKNOWN,
    FORMATION_V,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from .maneuver_mode import compute_agent_setpoints, compute_hold_setpoints
from .mode_context import ModeContext
from .mode_states import ControlMode, ModeState
from .mode_transitions import evaluate_transitions
from .movement_mode import compute_formation_command, compute_hold_command

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class ModeManagerNode(Node):
    """Gorev 2 yari otonom suru kontrol koordinatoru."""

    def __init__(self) -> None:
        super().__init__('mode_manager_node')

        self._declare_params()

        self._ctx = ModeContext(
            agent_ids=self._agent_ids,
            sitl_mode=self._sitl_mode,
        )
        # Limitleri ctx'e paramdan yaz (tek kaynak). Kumandadan gelen
        # max_* alanlari > 0 ise _on_control_command yine EZEBILIR —
        # o kanal hakem/pilot ayari icin bilerek acik birakildi.
        self._ctx.max_speed_mps = self._max_speed_mps
        self._ctx.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        self._ctx.max_tilt_deg = self._max_tilt_deg
        self._ctx.kalkis_esik_m = self._kalkis_esik_m
        self._ctx.test_hazir_atla = self._test_hazir_atla

        self._last_tick_time = time.monotonic()
        self._formation_offsets: dict[int, tuple[float, float, float]] = {}
        self._init_default_offsets()

        self._setpoint_sequence = 0

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'ModeManagerNode baslatildi: {self._agent_ids}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve okur."""
        # Sayisal skalerler dynamic_typing ile — formasyon_sekans'ta iki
        # kez sahada olculen tuzak: `-p x:=90` YAML'da INTEGER'dir ve
        # double bekleyen declare dugumu ACILISTA oldurur.
        from rcl_interfaces.msg import ParameterDescriptor
        _dnm = ParameterDescriptor(dynamic_typing=True)
        self.declare_parameter('agent_ids', [1, 2, 3])
        # KENDI kimligim — kendi durumumu YEREL kaynaktan almak icin
        # sart (bkz. _setup_subscribers). 0 = bilinmiyor.
        self.declare_parameter('agent_id', 0, _dnm)
        self.declare_parameter('tick_hz', 20.0, _dnm)
        self.declare_parameter('sitl_mode', False)
        # LIMITLER TEK KAYNAKTAN (ucus_ayarlari MOD_* -> baslat.sh env).
        # Ilk yazimda ModeContext gomulu varsayilanlariyla kosuyordu —
        # 14 Agustos dersinin ayni sinifi (MAKS_EGIM_DEG kazasi).
        self.declare_parameter('default_spacing_m', 7.0, _dnm)
        self.declare_parameter('max_speed_mps', 2.0, _dnm)
        self.declare_parameter('max_yaw_rate_deg_s', 25.0, _dnm)
        self.declare_parameter('max_tilt_deg', 15.0, _dnm)
        # Slot geometrisi formation_node/kopru/sekans ile AYNI aci —
        # eskiden asagida math.radians(45.0) GOMULUYDU.
        self.declare_parameter('wing_alpha_deg', 45.0, _dnm)
        # B15 KALKIS KAPISI: bu yuksekligin ALTINDA hicbir tarif/setpoint
        # yayinlanmaz. Tek kaynak `ucus_ayarlari` MOD_KALKIS_ESIK.
        self.declare_parameter('kalkis_esik_m', 2.0, _dnm)
        # B3: mission_fsm kapaliyken FSM'i READY'ye ulastirir. VARSAYILAN
        # FALSE — yarisma profilinde ADIM 6 acilinca kapatilir.
        self.declare_parameter('test_hazir_atla', False)

        self._agent_ids = list(
            self.get_parameter('agent_ids').value
        )
        self._agent_id = int(self.get_parameter('agent_id').value)
        self._tick_hz = float(
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode = bool(
            self.get_parameter('sitl_mode').value
        )
        self._default_spacing_m = float(
            self.get_parameter('default_spacing_m').value
        )
        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._max_yaw_rate_deg_s = float(
            self.get_parameter('max_yaw_rate_deg_s').value
        )
        self._max_tilt_deg = float(
            self.get_parameter('max_tilt_deg').value
        )
        self._wing_alpha_rad = math.radians(float(
            self.get_parameter('wing_alpha_deg').value
        ))
        self._kalkis_esik_m = float(
            self.get_parameter('kalkis_esik_m').value
        )
        self._test_hazir_atla = bool(
            self.get_parameter('test_hazir_atla').value
        )

    def _init_default_offsets(self) -> None:
        """Varsayilan formasyon ofsetlerini olusturur."""
        s = self._default_spacing_m
        if len(self._agent_ids) >= 3:
            self._formation_offsets = {
                self._agent_ids[0]: (s, 0.0, 0.0),
                self._agent_ids[1]: (-s / 2, -s, 0.0),
                self._agent_ids[2]: (-s / 2, s, 0.0),
            }
        elif len(self._agent_ids) == 2:
            self._formation_offsets = {
                self._agent_ids[0]: (0.0, -s / 2, 0.0),
                self._agent_ids[1]: (0.0, s / 2, 0.0),
            }
        else:
            for aid in self._agent_ids:
                self._formation_offsets[aid] = (0.0, 0.0, 0.0)

    def _setup_publishers(self) -> None:
        """Yayinci kanallarini olusturur."""
        self._formation_pub = self.create_publisher(
            FormationCommand,
            '/swarm/internal/formation/target',
            _RELIABLE_QOS,
        )

        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _RELIABLE_QOS,
        )

        # ÇIKIŞ /raw'A — /control/setpoint DEĞİL (28 Ağu düzeltmesi).
        # /control/setpoint kaçınmanın ÇIKIŞ konusu; oraya yazmak
        # collision_avoidance ile İKİ ÜRETİCİ çakışmasıydı (CLAUDE.md §4)
        # ve manevra sırasında kaçınma katmanını BAYPAS ediyordu. /raw'a
        # yazınca CA zorunlu aktarım katı olarak arada kalır (formasyon
        # zinciriyle aynı yol). Her uçağın mode_manager'ı yalnız KENDİ
        # uçağının konusunda tüketici bulur (ROS_LOCALHOST_ONLY);
        # yabancı-id konuları yerel ve boş kalır.
        self._setpoint_pubs: dict[int, rclpy.publisher.Publisher] = {}
        for aid in self._agent_ids:
            pub = self.create_publisher(
                AgentSetpoint,
                f'/drone_{aid}/control/setpoint/raw',
                _BEST_EFFORT_QOS,
            )
            self._setpoint_pubs[aid] = pub

        # MANEVRA/HOLD-eğik sırasında formation_node'u susturan bayrak.
        # Görev 1'de aynı işi qr_step=MANEUVER yapıyor; Görev 2'de mission
        # zinciri kapalı olduğundan bu kanal eklendi (28 Ağu). Bayrak her
        # tick yayınlanır; formation_node 3 sn tazelenmezse KENDİLİĞİNDEN
        # bırakır (mode_manager ölürse sürücüsüz kalınmasın).
        self._sustur_pub = self.create_publisher(
            Bool,
            '/swarm/internal/mode/formasyon_sustur',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abone kanallarini olusturur."""
        # 🔴 KENDI DURUMUM /swarm/public/drone{ben}/status'TAN GELMEZ.
        #
        # 30 Agustos 2026 sahada olculdu: o konunun YAYINCI SAYISI 0.
        # Sebep tasarim — ic_dis_kopru tablosu "drone{N}/status BILEREK
        # haric" diyor; ucagin kendi durumu kendi public konusuna
        # koprulenmiyor, oraya yalniz mesh'ten KOMSULARIN durumu dusuyor.
        #
        # Sonucu agirdi: all_agents_seen() asla True olmuyordu, yani
        # KALKIS KAPISI (B15) HICBIR ZAMAN ACILAMAZDI ve mode_manager
        # havada da hicbir sey yayinlamazdi. Gorev 2 komple olu olurdu ve
        # hicbir yerde hata gorunmezdi.
        #
        # Cozum: kendi durumu /swarm/internal/drone{ben}/status'tan (10 Hz),
        # komsularinki mesh'ten public'ten.
        #
        # ⚠️ ONCE /swarm/agent/drone{ben}/telemetry SECILMISTI (formation_node
        # deseni) ve YANLISTI — olculdu:
        #     /swarm/agent/drone1/telemetry   state: 0  healthy: false
        #     /swarm/internal/drone1/status   state: 1  healthy: true
        # Ilki px4_bridge'in HAM telemetrisi; `state` (ajan FSM durumu) ve
        # `healthy` alanlarini DOLDURMUYOR. formation_node'a yetiyor cunku o
        # yalniz KONUM okuyor; mode_manager ise all_agents_healthy() ve
        # all_agents_in_swarm() icin ikisini de okuyor ve ikisi de yanlis
        # gelirdi (PREFLIGHT -> TAKEOFF hic gecmezdi).
        #
        # Ayrica /swarm/internal/drone{N}/status TAM OLARAK mesh'e giden
        # kayit: kendimizi komsularin gordugu ile AYNI alanlardan okumus
        # oluyoruz (simetri).
        for aid in self._agent_ids:
            if aid == self._agent_id:
                konu = f'/swarm/internal/drone{aid}/status'
            else:
                konu = f'/swarm/public/drone{aid}/status'
            self.create_subscription(
                AgentStatus,
                konu,
                lambda msg, a=aid: self._on_agent_status(msg, a),
                _BEST_EFFORT_QOS,
            )
            self.get_logger().info(f'ajan {aid} durumu <- {konu}')

        if self._agent_id == 0:
            self.get_logger().error(
                'agent_id VERILMEDI (0). Kendi durumum public konudan '
                'beklenecek ve ORASI BOS — kalkis kapisi HIC ACILMAZ. '
                'baslat.sh -p agent_id:=${AGENT_ID} gecirmeli.'
            )

        self.create_subscription(
            SwarmControlCommand,
            '/swarm/public/control/command',
            self._on_control_command,
            _BEST_EFFORT_QOS,
        )

        self.create_subscription(
            UInt8,
            '/swarm/internal/mission/state',
            self._on_mission_state,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SwarmState,
            '/swarm/public/state',
            self._on_swarm_state,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SystemEvent,
            '/swarm/internal/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

    def _tick(self) -> None:
        """Tick dongusu."""
        now = time.monotonic()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        ctx = self._ctx

        # B15 KALKIS KAPISI — evaluate_transitions'tan ONCE degerlendirilir,
        # cunku _from_takeoff ctx.kalkis_tamam'i okuyor (B3 test yolu).
        _kapi_onceydi = ctx.kalkis_tamam
        ctx.kalkis_kapisi_degerlendir()
        # 🔴 KAPI NEDEN KAPALI — sessiz kalmasi 30 Agustos'ta bir kusuru
        # gizlemisti (kendi durumu hic gelmiyordu ve kimse fark etmiyordu).
        # Kapali kaldigi surece 10 saniyede bir SEBEBINI soyler.
        if not ctx.kalkis_tamam:
            eksik = [a for a in self._agent_ids if a not in ctx.agent_statuses]
            disarm = [
                a for a in self._agent_ids
                if a in ctx.agent_statuses
                and not bool(getattr(ctx.agent_statuses[a], 'armed', False))
            ]
            if eksik:
                sebep = f'durumu HIC GELMEYEN ajan: {eksik}'
            elif disarm:
                sebep = f'DISARM ajanlar: {disarm}'
            else:
                alcak = {
                    a: round(-float(ctx.agent_statuses[a].pos_z), 1)
                    for a in self._agent_ids
                    if -float(ctx.agent_statuses[a].pos_z) < ctx.kalkis_esik_m
                }
                sebep = (f'esigin ({ctx.kalkis_esik_m:.1f} m) altindaki '
                         f'ajanlar: {alcak}' if alcak else 'bilinmiyor')
            self.get_logger().info(
                f'[mode_manager] kalkis kapisi KAPALI — {sebep}',
                throttle_duration_sec=10.0,
            )
        if ctx.kalkis_tamam and not _kapi_onceydi:
            # Ofsetleri de OLCULEN geometriyle tohumla — pilot ilk is
            # MANEVRA'ya gecerse gomulu ucgen egilmesin (bkz. docstring).
            olculen = ctx.olculen_ofsetler()
            if len(olculen) == len(self._agent_ids):
                self._formation_offsets = olculen
            self.get_logger().info(
                f'[mode_manager] KALKIS KAPISI ACILDI (esik '
                f'{ctx.kalkis_esik_m:.1f} m) — centroid ucaklarin KENDI '
                f'konumundan tohumlandi: ({ctx.centroid_x:.1f}, '
                f'{ctx.centroid_y:.1f}, {ctx.centroid_z:.1f}) '
                f'heading={ctx.formation_heading_deg:.1f} deg '
                f'(tutarlilik {ctx.kalkis_heading_tutarlilik:.2f})'
            )
            # B17: ucaklar ayni yone bakmiyorsa ortalama heading anlamli
            # degil ve formasyon devir aninda beklenmedik yerlesir.
            if ctx.kalkis_heading_tutarlilik < 0.9:
                self.get_logger().warning(
                    '[mode_manager] UCAKLARIN YAW\'LARI DAGINIK '
                    f'(tutarlilik {ctx.kalkis_heading_tutarlilik:.2f} < 0.90) — '
                    f'formasyon heading={ctx.formation_heading_deg:.1f} deg '
                    'olarak tohumlandi ama bu ortalama zayif. Ucaklar ayni '
                    'yone bakacak sekilde dizilmeliydi.'
                )

        next_state = evaluate_transitions(ctx)
        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        if ctx.state == ModeState.MOVEMENT:
            self._dispatch_movement(dt)
        elif ctx.state == ModeState.MANEUVER:
            self._dispatch_maneuver(dt)
        elif ctx.state == ModeState.HOLD:
            self._dispatch_hold()
        elif ctx.state == ModeState.READY:
            self._dispatch_hold()

        if ctx.formation_change_requested:
            self._handle_formation_change()

        ctx.takeoff_requested = False
        ctx.land_requested = False
        ctx.rtl_requested = False
        ctx.emergency_stop_requested = False
        ctx.formation_change_requested = False

        # formation_node susturması: mode_manager /raw'a KENDİSİ yazarken
        # (MANEVRA her zaman; HOLD yalnız eğik pozdayken) formasyon susar,
        # aksi hâlde formasyon sürücüdür (MOVEMENT tarif üzerinden gider).
        sustur = Bool()
        sustur.data = ctx.kalkis_tamam and (
            ctx.state == ModeState.MANEUVER
            or (ctx.state in (ModeState.HOLD, ModeState.READY)
                and (ctx.maneuver_pitch_deg != 0.0
                     or ctx.maneuver_roll_deg != 0.0))
        )
        self._sustur_pub.publish(sustur)

    def _transition(self, new_state: ModeState) -> None:
        """Durum gecisini uygular."""
        old = self._ctx.state
        self._ctx.set_state(new_state)

        self.get_logger().info(
            f'[mode_manager] {old.name} -> {new_state.name}'
        )

        self._on_state_entry(new_state, old)

    def _on_state_entry(
        self, state: ModeState, old_state: ModeState
    ) -> None:
        """Yeni durum giris eylemlerini calistirir."""
        if state == ModeState.TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 kalkış başlıyor',
            )

        elif state == ModeState.READY:
            self._pub_event(
                SystemEvent.EVENT_FORMATION_REACHED,
                SystemEvent.SEVERITY_INFO,
                'Sürü hazır, kumanda bekleniyor',
            )

        elif state == ModeState.MOVEMENT:
            self.get_logger().info(
                '[mode_manager] Hareket modu aktif'
            )

        elif state == ModeState.MANEUVER:
            self.get_logger().info(
                '[mode_manager] Manevra modu aktif'
            )

        elif state == ModeState.HOLD:
            self.get_logger().info(
                '[mode_manager] HOLD modu'
            )

        elif state == ModeState.LANDING:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 iniş komutu',
            )

        elif state == ModeState.RTL:
            self._pub_event(
                SystemEvent.EVENT_RTL_TRIGGERED,
                SystemEvent.SEVERITY_WARNING,
                'Görev 2 RTL',
            )

        elif state == ModeState.EMERGENCY:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_EMERGENCY,
                'Görev 2 acil durum',
            )

        elif state == ModeState.COMPLETED:
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 tamamlandı',
            )

    def _dispatch_movement(self, dt: float) -> None:
        """Sürü hareket modunu yurutur."""
        params = compute_formation_command(self._ctx, dt)
        self._publish_formation_command(params)

        self._ctx.centroid_x = params['center_x']
        self._ctx.centroid_y = params['center_y']
        self._ctx.centroid_z = params['center_z']
        self._ctx.formation_heading_deg = params['heading_deg']

    def _dispatch_maneuver(self, dt: float) -> None:
        """Manevra modunu yurutur."""
        result = compute_agent_setpoints(
            self._ctx, dt, self._formation_offsets,
        )
        setpoints, new_heading, pitch_deg, roll_deg = result

        for sp in setpoints:
            self._publish_agent_setpoint(sp)

        self._ctx.formation_heading_deg = new_heading
        self._ctx.maneuver_pitch_deg = pitch_deg
        self._ctx.maneuver_roll_deg = roll_deg

    def _dispatch_hold(self) -> None:
        """HOLD durumunu yurutur."""
        if (self._ctx.maneuver_pitch_deg != 0.0
                or self._ctx.maneuver_roll_deg != 0.0):
            setpoints = compute_hold_setpoints(
                self._ctx, self._formation_offsets,
            )
            for sp in setpoints:
                self._publish_agent_setpoint(sp)
        else:
            params = compute_hold_command(self._ctx)
            self._publish_formation_command(params)

    def _handle_formation_change(self) -> None:
        """Formasyon degisikligi talebini isler."""
        ctx = self._ctx
        def_spacing = getattr(self, '_default_spacing_m', 5.0)
        spacing = (
            ctx.requested_spacing_m
            if ctx.requested_spacing_m > 0.0
            else def_spacing
        )
        self.get_logger().info(
            f'Formasyon degisikligi: {ctx.requested_formation}, spacing: {spacing}m'
        )
        ctx.active_formation = ctx.requested_formation
        ctx.requested_spacing_m = spacing

        params = {
            'center_x': ctx.centroid_x,
            'center_y': ctx.centroid_y,
            'center_z': ctx.centroid_z,
            'heading_deg': ctx.formation_heading_deg,
            'formation_type': ctx.requested_formation,
            'spacing_m': spacing,
            'max_speed_mps': ctx.max_speed_mps,
            'use_current_centroid': False,
            'use_current_altitude': True,
        }
        self._publish_formation_command(params)
        ctx.formation_change_requested = False

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        self._ctx.agent_statuses[agent_id] = msg

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        ctx = self._ctx

        ctx.command_valid = msg.command_valid
        ctx.deadman_pressed = msg.deadman_pressed
        ctx.deadman_timeout_s = msg.deadman_timeout_s

        ctx.command_valid = bool(msg.command_valid)
        ctx.deadman_pressed = bool(msg.deadman_pressed)

        # SwA YUKARI (deadman_pressed == False): Emniyet kilitli, TÜM istekleri sıfırla!
        if not msg.deadman_pressed:
            ctx.pitch_cmd = 0.0
            ctx.roll_cmd = 0.0
            ctx.yaw_cmd = 0.0
            ctx.throttle_cmd = 0.0
            ctx.takeoff_requested = False
            ctx.land_requested = False
            ctx.rtl_requested = False
            ctx.emergency_stop_requested = False
            ctx.formation_change_requested = False
            return

        # Emniyet açık (deadman_pressed == True), ancak paket geçersiz (örn. GCS heartbeat):
        # Eksenleri sıfırla ama aksiyon isteklerini KORU! (_tick tarafından işlenip temizlenir)
        if not msg.command_valid:
            ctx.pitch_cmd = 0.0
            ctx.roll_cmd = 0.0
            ctx.yaw_cmd = 0.0
            ctx.throttle_cmd = 0.0
            return

        try:
            ctx.control_mode = ControlMode(msg.mode)
        except ValueError:
            ctx.control_mode = ControlMode.UNKNOWN

        ctx.pitch_cmd = msg.pitch_cmd
        ctx.roll_cmd = msg.roll_cmd
        ctx.yaw_cmd = msg.yaw_cmd
        ctx.throttle_cmd = msg.throttle_cmd

        if msg.takeoff:
            ctx.takeoff_requested = True
        if msg.land:
            ctx.land_requested = True
        if msg.rtl:
            ctx.rtl_requested = True
        if msg.emergency_stop:
            ctx.emergency_stop_requested = True

        if msg.formation_change_requested:
            ctx.formation_change_requested = True
            ctx.requested_formation = msg.requested_formation
            # 0 = belirtilmedi -> uzerine YAZMA (asagidaki max_speed_mps /
            # max_yaw_rate_deg_s ile ayni kural). Kosulsuz atama spacing=0.0'i
            # ctx'e tasiyordu ve compute_slot_offsets() "spacing > 0 olmali"
            # diye ValueError atiyordu; formasyon degisikligi komple dusuyordu.
            # Mesh tarafi da 0'i "belirtilmedi" olarak tasiyor (30 Temmuz,
            # komut_veri_t.talep_spacing_dm).
            if msg.requested_spacing_m > 0.0:
                ctx.requested_spacing_m = msg.requested_spacing_m

        if msg.max_speed_mps > 0.0:
            ctx.max_speed_mps = msg.max_speed_mps
        if msg.max_yaw_rate_deg_s > 0.0:
            ctx.max_yaw_rate_deg_s = msg.max_yaw_rate_deg_s
        if msg.max_tilt_deg > 0.0:
            ctx.max_tilt_deg = msg.max_tilt_deg

        ctx.command_sequence_num = msg.sequence_num
        ctx.last_valid_command_time = time.monotonic()

    def _on_mission_state(self, msg: UInt8) -> None:
        self._ctx.mission_state = msg.data
        if msg.data == 10:  # MissionState.LANDING
            self._ctx.land_requested = True
        elif msg.data == 9:  # MissionState.RETURN_HOME
            self._ctx.rtl_requested = True

    def _on_swarm_state(self, msg: SwarmState) -> None:
        ctx = self._ctx

        # KALKIS KAPISI acildiktan SONRA centroid mode_manager'in KENDI
        # entegratorudur; disaridan yazmak suruyu isinlatir. Kapi acilirken
        # zaten ucaklarin kendi konumundan tohumlandi (B15). Kapi kapaliyken
        # izlemeye devam — o sirada zaten hicbir sey yayinlanmiyor.
        # ESKIDEN kosul (IDLE, PREFLIGHT, TAKEOFF, READY) idi; READY'de
        # swarm_fsm'in (0,0,0) centroid'i iyi tohumu EZEBILIYORDU (B16).
        if not ctx.kalkis_tamam:
            ctx.centroid_x = msg.centroid_x
            ctx.centroid_y = msg.centroid_y
            ctx.centroid_z = msg.centroid_z
            ctx.formation_heading_deg = msg.formation_heading_deg

        # active_formation mode_manager tarafindan kumanda/GCS secimiyle yonetilir
        ctx.formation_reached = msg.formation_reached
        ctx.formation_stable = msg.formation_stable

    def _on_event(self, msg: SystemEvent) -> None:
        """Baska dugumlerin acil olaylarini istege cevirir.

        🔴 B8 (30 Agustos 2026) — KENDI OLAYINA TEPKI VERME.
        Bu dugum /swarm/internal/events/system'e hem YAZIYOR hem ABONE.
        Eskiden kendi yayinini da isliyordu ve RTL durumu TEK TIK yasiyordu:

            _on_state_entry(RTL) -> EVENT_RTL_TRIGGERED yayinlanir
              -> _on_event kendi olayini duyar -> land_requested = True
              -> land kapisi RTL'i DISLAMIYOR -> hemen LANDING

        Cozum land kapisina RTL eklemek DEGIL: CLAUDE.md "iptal her zaman
        land" diyor ve pilotun SwD ile verdigi inis komutu RTL'i
        KESEBILMELI. Dogru cozum kaynagi susturmak.

        Ikinci kusur: iki olay tipi de HEM rtl HEM land istegi kuruyordu.
        RTL olayi inis istemez, acil inis olayi RTL istemez — ayrildi.
        """
        if msg.source_module == 'mode_manager':
            return

        eid = msg.event_type

        if eid == SystemEvent.EVENT_RTL_TRIGGERED:
            self._ctx.emergency_stop_requested = False
            self._ctx.rtl_requested = True
        elif eid == SystemEvent.EVENT_EMERGENCY_LAND:
            self._ctx.emergency_stop_requested = False
            self._ctx.land_requested = True

    def _publish_formation_command(self, params: dict) -> None:
        # 🔴 B15 KALKIS KAPISI — kapi kapaliyken TEK BIR tarif bile disari
        # cikmaz. Kapi dispatch'e degil YAYIN SINIRINA konuldu: boylece
        # ileride eklenen her yeni yol da kendiliginden kapali kalir.
        # Kapali kalma sebebi ve tehlike: mode_context.kalkis_kapisi_degerlendir
        if not self._ctx.kalkis_tamam:
            return

        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._ctx.command_sequence_num

        ftype = params.get('formation_type', 0)
        spacing = float(params.get('spacing_m', 0.0))
        if spacing <= 0.0:
            spacing = float(getattr(self, '_default_spacing_m', 5.0))
        if spacing <= 0.0:
            spacing = 5.0

        msg.formation_type = ftype
        msg.center_x = params.get('center_x', 0.0)
        msg.center_y = params.get('center_y', 0.0)
        msg.center_z = params.get('center_z', 0.0)
        msg.heading_deg = params.get('heading_deg', 0.0)
        msg.spacing_m = spacing
        msg.use_current_centroid = params.get(
            'use_current_centroid', False
        )
        msg.use_current_altitude = params.get(
            'use_current_altitude', False
        )
        msg.hold_after_reached = True
        msg.max_speed_mps = params.get('max_speed_mps', 0.0)
        msg.source_module = 'mode_manager'

        num_agents = len(self._agent_ids)
        msg.agent_ids = [int(a) for a in self._agent_ids]

        if ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI) and num_agents > 0:
            try:
                # wing_alpha paramdan — 45.0 GOMULUYDU (28 Agu): formasyon
                # zincirinin geri kalani KANAT_ALFA_DEG'i paylasirken bu
                # dugum ayrisirsa slot geometrisi sessizce kayardi.
                alpha = self._wing_alpha_rad
                offsets = compute_slot_offsets(ftype, num_agents, spacing, alpha)
                msg.offset_x = [float(o[0]) for o in offsets]
                msg.offset_y = [float(o[1]) for o in offsets]
                msg.offset_z = [float(o[2]) for o in offsets]
                self._last_valid_offsets_x = list(msg.offset_x)
                self._last_valid_offsets_y = list(msg.offset_y)
                self._last_valid_offsets_z = list(msg.offset_z)

                # 🔴 B7 (KARAR-11 #5) — MANEVRA'nin kullandigi ofsetleri
                # BURADA tazele. Onceden _formation_offsets yalniz
                # _init_default_offsets()'te bir kez kuruluyordu ve
                # _handle_formation_change onu HIC guncellemiyordu: formasyon
                # degistirip manevraya gecince gomulu ESKI ofsetler egilir,
                # x-y de onlara gore basilirdi -> ucaklar yeni formasyon
                # konumlarina ISINLANMAYA kalkardi.
                # Senkron noktasi TEK ve slot geometrisinin hesaplandigi tek
                # yer burasi; iki ayri kopya birbirinden kayamaz.
                # Slot i <-> agent_ids[i] (kimlik sirasi; Macar YOK, KARAR-11).
                self._formation_offsets = {
                    aid: (
                        float(msg.offset_x[i]),
                        float(msg.offset_y[i]),
                        float(msg.offset_z[i]),
                    )
                    for i, aid in enumerate(msg.agent_ids)
                }
            except Exception as e:
                self.get_logger().error(f'Slot offset hesaplama hatası: {e}')
                msg.offset_x = [0.0] * num_agents
                msg.offset_y = [0.0] * num_agents
                msg.offset_z = [0.0] * num_agents
        elif ftype == FORMATION_UNKNOWN:
            # Formasyonsuz (FORMATION_UNKNOWN): Dronelar bağımsız hareket eder
            ox, oy, oz = [], [], []
            ctx = self._ctx
            has_telemetry = False
            for aid in msg.agent_ids:
                status = ctx.agent_statuses.get(aid)
                is_pos_valid = (
                    status is not None and (
                        getattr(status, 'position_valid', False)
                        or status.pos_x != 0.0
                        or status.pos_y != 0.0
                    )
                )
                if is_pos_valid:
                    has_telemetry = True
                    ox.append(float(status.pos_x - ctx.centroid_x))
                    oy.append(float(status.pos_y - ctx.centroid_y))
                    oz.append(0.0)

            if has_telemetry and len(ox) == num_agents:
                msg.offset_x = ox
                msg.offset_y = oy
                msg.offset_z = oz
                self._last_valid_offsets_x = list(ox)
                self._last_valid_offsets_y = list(oy)
                self._last_valid_offsets_z = list(oz)
            elif (
                hasattr(self, '_last_valid_offsets_x')
                and len(self._last_valid_offsets_x) == num_agents
            ):
                msg.offset_x = list(self._last_valid_offsets_x)
                msg.offset_y = list(self._last_valid_offsets_y)
                msg.offset_z = list(self._last_valid_offsets_z)
            else:
                msg.offset_x = [0.0] * num_agents
                msg.offset_y = [0.0] * num_agents
                msg.offset_z = [0.0] * num_agents

        self._formation_pub.publish(msg)

    def _publish_agent_setpoint(self, sp: dict) -> None:
        # 🔴 B15 KALKIS KAPISI — bkz. _publish_formation_command.
        if not self._ctx.kalkis_tamam:
            return

        agent_id = sp['agent_id']
        pub = self._setpoint_pubs.get(agent_id)
        if pub is None:
            return

        self._setpoint_sequence += 1

        msg = AgentSetpoint()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._setpoint_sequence
        msg.agent_id = agent_id

        msg.source = AgentSetpoint.SOURCE_MANEUVER_EXECUTOR
        msg.priority = AgentSetpoint.PRIORITY_MANEUVER

        msg.x = sp['x']
        msg.y = sp['y']
        msg.z = sp['z']
        msg.heading_deg = sp['heading_deg']

        msg.position_valid = True
        msg.heading_valid = True

        msg.max_speed_mps = self._ctx.max_speed_mps

        msg.source_module = 'mode_manager'

        pub.publish(msg)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.source_module = 'mode_manager'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ModeManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
