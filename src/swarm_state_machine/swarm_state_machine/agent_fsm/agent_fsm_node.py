# Copyright 2026 Yelpence
"""ROS2 node that runs FSM for a single drone."""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from std_msgs.msg import Bool, String

from swarm_interfaces.msg import AgentStatus, SwarmOrigin, SystemEvent
from swarm_interfaces.srv import AssignRole

from .agent_context import AgentContext
from .agent_health_monitor import check as health_check
from .agent_states import AgentRole, AgentState, FlightMode
from .agent_transitions import evaluate_transitions
from .preflight_checker import run_preflight_checks

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_GROUND_VEL_THR = 0.3

# Pilot override status_text'i sabit: yazan ve TEMIZLEYEN aynı metni
# kullanmalı. Elle iki yere yazılırsa biri değişince metin asla temizlenmez
# ve sahada bayat kalır (30 Temmuz'da tam bu yaşandı).
_PILOT_OVERRIDE_METNI = 'Pilot override active'


class AgentFsmNode(Node):
    """Tek bir drone'un FSM node'u."""

    def __init__(self) -> None:
        super().__init__('agent_fsm_node')

        self._declare_params()

        self._ctx = AgentContext(
            agent_id=self._agent_id,
            sitl_mode=self._sitl_mode,
            battery_critical_voltage_v=self._batt_crit_v,
            pil_kesme_aktif=self._pil_kesme_aktif,
            target_altitude_m=self._target_altitude_m,
        )

        self._px4_landed = False
        self._prev_pilot_override = False

        self._setup_publishers()
        self._setup_subscribers()
        self._setup_services()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'AgentFsmNode baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('battery_critical_voltage_v', 13.6)
        self.declare_parameter('pil_kesme_aktif', True)
        self.declare_parameter('tick_hz', 10.0)
        self.declare_parameter('target_altitude_m', 10.0)
        # YER TESTI: gorev basladi olayi ARMED'a kadar goturur, TAKEOFF'a
        # GOTURMEZ. Pervanesiz yer testleri icin (bkz. asagida _on_event).
        self.declare_parameter('yer_testi', False)
        # kalkis_olayla=False: EVENT_MISSION_STARTED ajani yalniz ARMED'a
        # tasir, TAKEOFF'u TETIKLEMEZ — kalkis guided yoldan beklenir.
        # Gecis donemi ayari (19 Agustos 2026, P0.11 kopru karari): kalkis
        # otoritesi tek kaynakta kalsin diye (bkz. CLAUDE.md bolum 4 kurali:
        # bir konuya tek uretici; 'takeoff' komutunun da tek kaynagi olmali).
        # mission1 + agent_fsm kalkisi devraldiginda True yapilacak.
        #
        # VARSAYILAN False (20 Agustos 2026, denetim bulgusu): once True idi
        # ("eski davranis" gerekcesiyle) ve guvenli deger YALNIZ baslat.sh
        # argumanindan geliyordu. Parametre ulasmazsa (ucaktaki baslat.sh
        # eski kalmis, restart yapilmamis, dugum elle/teshis betiginden
        # baslatilmis) guided ARM komutsuz kalkis tetikliyordu; ustelik FSM
        # 'takeoff:10.0' capalayinca guided'in 20 m'lik kalkisi px4_bridge'de
        # SESSIZCE yutuluyordu (px4_bridge.py:1309-1311). Emniyet varsayilani
        # guvenli tarafta olmali: parametre kaybolursa kalkis KAPALI kalir.
        self.declare_parameter('kalkis_olayla', False)

        self._agent_id = self.get_parameter('agent_id').value
        self._sitl_mode = self.get_parameter('sitl_mode').value
        self._batt_crit_v = (
            self.get_parameter('battery_critical_voltage_v').value
        )
        self._pil_kesme_aktif = bool(
            self.get_parameter('pil_kesme_aktif').value
        )
        self._tick_hz = self.get_parameter('tick_hz').value
        self._target_altitude_m = (
            self.get_parameter('target_altitude_m').value
        )
        self._yer_testi = bool(self.get_parameter('yer_testi').value)
        self._kalkis_olayla = bool(
            self.get_parameter('kalkis_olayla').value
        )
        if self._yer_testi:
            self.get_logger().warn(
                '*** YER TESTI ACIK *** Gorev basladi olayi ARMED e kadar '
                'goturur, KALKIS KOMUTU GONDERILMEZ. Ucus icin '
                '/ws/yer_testi dosyasini SIL ve konteyneri yeniden baslat.'
            )

    def _setup_publishers(self) -> None:
        """Publisher'lari olusturur."""
        aid = self._agent_id
        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/internal/drone{aid}/status',
            10,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            10,
        )
        self._command_pub = self.create_publisher(
            String,
            f'/swarm/agent/drone{aid}/commands',
            10,
        )

    def _setup_subscribers(self) -> None:
        """Abonelikleri olusturur."""
        aid = self._agent_id

        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{aid}/telemetry',
            self._on_telemetry,
            10,
        )
        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            10,
        )
        self.create_subscription(
            SystemEvent,
            '/swarm/internal/events/system',
            self._on_event,
            10,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_origin,
            _ORIGIN_QOS,
        )

        # 🔴 KALKIS TAMAM — gorev node'undan (bkz. mission1_node
        # _kalkis_denetle). TAKEOFF'tan cikisin ikinci ve DOGRU yolu.
        # Buradaki kendi kapimiz (target_altitude_reached) NED origin'i
        # yer sanip 2 Eylul'de iki ucagi da 30 sn timeout'a dusurmustu.
        self.create_subscription(
            Bool,
            '/swarm/internal/mission/kalkis_tamam',
            self._on_kalkis_tamam,
            10,
        )

    def _setup_services(self) -> None:
        """Aciklama: AssignRole servisini kurar."""
        aid = self._agent_id
        self.create_service(
            AssignRole,
            f'/swarm/agent/drone{aid}/assign_role',
            self._handle_assign_role,
        )

    def _tick(self) -> None:
        """FSM ana dongusu."""
        ctx = self._ctx

        result = health_check(ctx)

        if result.critical_fault and ctx.state != AgentState.FAILSAFE:
            self.get_logger().error(
                f'[FAILSAFE] {result.reason}'
            )
            self._transition(AgentState.FAILSAFE)
            self._pub_event(
                result.event_type,
                SystemEvent.SEVERITY_EMERGENCY,
                result.reason,
            )
        elif result.safety_hold and not ctx.hold_active:
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'
            self.get_logger().warn(
                f'[agent {ctx.agent_id}] SAFETY HOLD tetiklendi: '
                f'{result.reason}'
            )
            # Kilit yalnız bu ajanı bağlasın diye target_agent_id veriyoruz.
            # Hedefsiz yayınlanınca bir ajanın güvenlik sorunu tüm sürüyü
            # kilitliyordu (alıcı tarafta is_mine kontrolü de eklendi).
            self._pub_event(
                SystemEvent.EVENT_SAFETY_HOLD,
                SystemEvent.SEVERITY_WARNING,
                result.reason,
                target_agent_id=ctx.agent_id,
            )
        elif result.warning:
            ctx.status_text = result.reason
            # KISILDI (2 Eylul): uyarilar artik check()'ten yukari
            # tasiniyor ve bu dal tick hizinda (10 Hz) calisabiliyor.
            # Kisilmasaydi dusuk pille saniyede onlarca satir yazilir,
            # gunluk disk bekcisini bosuna tetiklerdi.
            self.get_logger().warn(
                result.reason, throttle_duration_sec=5.0
            )

        next_s = evaluate_transitions(ctx)

        # ARMED'da takılma teşhisi: dron sessizce ARMED'da kalıp kalkamazsa
        # hangi şartın tutmadığını burada loglayıp görünür kılıyoruz.
        # hold_active/autonomous_paused da yazılıyor: bu ikisi kalkışı bloke
        # ediyordu ama eskiden hiçbir yere loglanmadığı için görünmezdi.
        if ctx.state == AgentState.ARMED and next_s is None:
            self.get_logger().warn(
                f'[agent {ctx.agent_id}] ARMED bekliyor: '
                f'mission_start={ctx.mission_start_sequence_active} '
                f'offboard={ctx.offboard_active} '
                f'sure={ctx.time_in_state():.1f}s '
                f'armed={ctx.armed} healthy={ctx.healthy} '
                f'hold_active={ctx.hold_active} '
                f'autonomous_paused={ctx.autonomous_control_paused}',
                throttle_duration_sec=3.0,
            )

        # IDLE'da ARMING reddi TEAMAMEN SESSIZDI (15 Agustos).
        #
        # _from_idle preflight'i cagirip hatalari `_` ile atiyor, ve tick
        # sonunda pending_state KOSULSUZ temizleniyor — yani istek tek tick
        # sans aliyor ve reddedilirse hicbir iz birakmadan kayboluyor.
        # ADIM 1 yer testinde "gorev basladi" uc kez yollandi, ucunde de olay
        # ulasti ama ucak IDLE'da kaldi ve NEDENI hicbir yerde yazmiyordu.
        # ARMED durumunun zaten boyle bir teshisi vardi (asagida), ayni seyi
        # burada da yapiyoruz.
        if (ctx.state == AgentState.IDLE
                and ctx.pending_state == AgentState.ARMING
                and next_s is None):
            _, sebepler = run_preflight_checks(ctx)
            self.get_logger().warn(
                f'[agent {ctx.agent_id}] ARMING REDDEDILDI — preflight: '
                f'{sebepler if sebepler else "(hata yok, baska bir sart)"}',
                throttle_duration_sec=2.0,
            )

        # 🔴 FAILSAFE SEBEBI YAZILIR — 2 Eylul 2026.
        # evaluate_transitions'in GENEL kapilari (healthy / offboard) sebep
        # YAZMADAN FAILSAFE dondurebiliyor. Bu gece iki ucak 27-28. saniyede
        # dustu ve logda TEK BIR sebep satiri yoktu; operator pil sandi,
        # dogrulamak icin 20 dakika log kazildi. Bir daha olmasin.
        if next_s == AgentState.FAILSAFE and ctx.state != AgentState.FAILSAFE:
            self.get_logger().error(
                f'[agent {ctx.agent_id}] FAILSAFE SEBEBI: '
                f'durum={ctx.state.name} sure={ctx.time_in_state():.1f}s '
                f'healthy={ctx.healthy} offboard={ctx.offboard_active} '
                f'pil={ctx.battery_voltage_v:.2f}V/'
                f'{ctx.battery_critical_voltage_v:.2f}V '
                f'kill={ctx.kill_switch_active} '
                f'px4_link={ctx.px4_link_ok} '
                f'px4_failsafe={ctx.failsafe_active} '
                f'xy={ctx.xy_valid} z={ctx.z_valid} vxy={ctx.v_xy_valid} '
                f'attitude_stable={ctx.attitude_stable}'
            )

        if next_s is not None and next_s != ctx.state:
            self._transition(next_s)

        is_failsafe_land = (
            ctx.state == AgentState.FAILSAFE
            and ctx.kill_switch_active
            and self._px4_landed
            and ctx.attitude_stable
        )
        if is_failsafe_land:
            self._transition(AgentState.LANDED)
            self._pub_event(
                SystemEvent.EVENT_AGENT_LANDED,
                SystemEvent.SEVERITY_INFO,
                'Kill switch: landed',
            )

        ctx.pending_state = None
        self._publish_status()

    def _transition(self, new_state: AgentState) -> None:
        """State gecisini uygular."""
        old = self._ctx.state
        self._ctx.set_state(new_state)

        if old == AgentState.ARMED and new_state == AgentState.TAKEOFF:
            self._ctx.mission_start_sequence_active = False

        # Rejoin: WAITING_REJOIN'den tekrar arm'a geçerken kalkış sekansını
        # yeniden etkinleştir (ARMED→TAKEOFF bu bayrağı bekler).
        # kalkis_olayla=False (geçiş dönemi) ise rejoin de kalkışı AÇMAZ —
        # kalkış otoritesi guided yolda kalır.
        if old == AgentState.WAITING_REJOIN and new_state == AgentState.ARMING:
            self._ctx.mission_start_sequence_active = self._kalkis_olayla

        self._dispatch_px4_command(new_state)

        self.get_logger().info(
            f'[agent {self._ctx.agent_id}] '
            f'{old.name} -> {new_state.name}'
        )

        # Ajan sürüden ayrıldığını sürüye duyurur. target_agent_id ayrılan
        # ajandır; task_reallocator rolleri buradan dağıtır, mission_fsm
        # detach adımını buradan ilerletir. Kaynak ajanın kendisi yayınlar.
        if new_state == AgentState.DETACHED:
            self._pub_event(
                SystemEvent.EVENT_AGENT_DETACHED,
                SystemEvent.SEVERITY_INFO,
                'Ajan sürüden ayrıldı',
                target_agent_id=self._ctx.agent_id,
            )

    def _dispatch_px4_command(self, state: AgentState) -> None:
        """State entry'sine karsilik gelen PX4 komutunu yayinlar."""
        if state == AgentState.ARMING:
            cmd = 'arm'
        elif state == AgentState.ARMED:
            cmd = 'offboard'
        elif state == AgentState.TAKEOFF:
            cmd = f'takeoff:{self._target_altitude_m}'
        elif state == AgentState.LANDING:
            cmd = 'land'
        elif state == AgentState.RETURN_HOME:
            # Nominal eve dönüş formasyonla, offboard'da yapılır: orchestrator
            # sürüyü home'a uçuran setpoint'leri yayınlar, çarpışma kaçınması
            # aktif kalır. Native RTL (return_home) yalnız gerçek offboard/link
            # kaybı failsafe'ine bırakıldı — burada offboard akışını sürdürürüz.  # noqa: E501
            cmd = 'offboard'
        else:
            return

        msg = String()
        msg.data = cmd
        self._command_pub.publish(msg)
        self.get_logger().info(
            f'[agent {self._ctx.agent_id}] CMD -> px4_bridge: {cmd}'
        )

    def _on_kalkis_tamam(self, msg: Bool) -> None:
        """Gorev node'u "hedef irtifadayim" dedi -> TAKEOFF'tan cik.

        🔴 2 Eylul 2026. Kendi kapimiz (_from_takeoff icindeki
        target_altitude_reached) irtifayi NED origin'den olcuyor; origin
        yerde degil, paylasilan suru origin'i. Ucak 10.0 m'ye cikip stabil
        dursa bile kapi acilmiyordu (olculdu: ylp00 1.06 m, ylp02 0.80 m
        acik) ve 30 sn sonra FAILSAFE. Gorev node'u ayni karari home'a
        GORELI irtifayla (alt_amsl - home_alt_amsl) veriyor.

        EMIR DEGIL: yalniz TAKEOFF durumundayken dinlenir. Kendi 30 sn
        zaman asimimiz guvenlik agi olarak YERINDE kalir — gorev node'u
        susarsa ucak yine failsafe'e duser, havada asili kalmaz.
        """
        if not msg.data:
            return
        if self._ctx.state != AgentState.TAKEOFF:
            return
        self._ctx.pending_state = AgentState.IN_SWARM
        if not getattr(self, '_kalkis_tamam_loglandi', False):
            self._kalkis_tamam_loglandi = True
            self.get_logger().info(
                f'[agent {self._ctx.agent_id}] gorev node: KALKIS TAMAM '
                f'-> IN_SWARM'
            )

    def _on_event(self, msg: SystemEvent) -> None:
        """Swarm event bus'tan gelen olaylari isler."""
        ctx = self._ctx
        aid = ctx.agent_id
        eid = msg.event_type
        tgt = msg.target_agent_id
        is_mine = tgt == 0 or tgt == aid

        if eid == SystemEvent.EVENT_MISSION_STARTED:
            # YER TESTI: mission_start_sequence_active KALKIS kapisidir.
            #   _from_armed: (mission_start_sequence_active and offboard_active
            #                 and stabilize suresi) -> TAKEOFF
            # Bayrak acikken bunu set ETMIYORUZ; FSM IDLE -> ARMING -> ARMED
            # yolunu normal yurutur (gercek preflight, gercek arm, gercek
            # AgentStatus) ama ARMED'da DURUR ve 'takeoff' komutu hic gitmez.
            #
            # Neden gerekli (15 Agustos): consensus lider secimi icin
            # ELIGIBLE_STATES sarti var ve IDLE o kumede yok; en dusuk uygun
            # durum ARMED. ARMED'a cikmanin tek yolu bu olay. Bayrak olmadan
            # olay ayni zamanda kalkisi tetikliyor ve pervanesiz yer testinde
            # motorlar ~30 sn bosta tam gazda kalip FAILSAFE'e dusuyordu.
            # kalkis_olayla=False (gecis donemi): olay ajani ARMED'a tasir
            # ama kalkis kapisini ACMAZ — 'takeoff' komutunun tek kaynagi
            # guided yol kalir (cift kalkis kaynagi = bolum-4 cakismasi).
            kalkis_izni = (not self._yer_testi) and self._kalkis_olayla
            if ctx.state == AgentState.IDLE:
                ctx.mission_start_sequence_active = kalkis_izni
                ctx.pending_state = AgentState.ARMING
            elif ctx.state == AgentState.ARMED:
                ctx.mission_start_sequence_active = kalkis_izni
            if not self._kalkis_olayla and not self._yer_testi:
                self.get_logger().info(
                    f'[agent {aid}] gecis modu: ARMED e kadar gidilecek, '
                    f'kalkis guided yoldan (kalkis_olayla=false)'
                )
            if self._yer_testi:
                self.get_logger().warn(
                    f'[agent {aid}] YER TESTI: ARMED e kadar gidilecek, '
                    f'kalkis komutu GONDERILMEYECEK.'
                )

        elif eid == SystemEvent.EVENT_RTL_TRIGGERED and is_mine:
            ctx.pending_state = AgentState.RETURN_HOME

        elif eid == SystemEvent.EVENT_EMERGENCY_LAND and is_mine:
            ctx.pending_state = AgentState.LANDING

        elif eid == SystemEvent.EVENT_SAFETY_HOLD and is_mine:
            # is_mine şart: filtre olmadan bir ajanın hold'u tüm sürüye
            # yayılıp hepsini kilitliyordu.
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'

        elif eid == SystemEvent.EVENT_FAILSAFE_CLEARED:
            ctx.hold_active = False
            self._handle_failsafe_cleared()

        elif eid == SystemEvent.EVENT_PX4_LINK_LOST:
            ctx.px4_link_ok = False

        elif eid == SystemEvent.EVENT_OFFBOARD_LOST:
            ctx.offboard_active = False

        elif eid == SystemEvent.EVENT_GCS_LINK_LOST:
            ctx.gcs_link_ok = False
            ctx.status_text = 'GCS link lost'

        elif eid == SystemEvent.EVENT_GCS_LINK_RESTORED:
            ctx.gcs_link_ok = True
            ctx.status_text = ''

        elif eid == SystemEvent.EVENT_MEMBER_DETACH_STARTED:
            if tgt == aid:
                ctx.pending_state = AgentState.DETACHED
                # Bekleme süresi (event value) saklanır; WAITING_REJOIN bu
                # süre dolunca kendi kendine tekrar arm olur.
                ctx.detach_wait_s = float(msg.value)

        elif eid == SystemEvent.EVENT_MEMBER_REJOIN_STARTED:
            if tgt == aid:
                passed, failures = run_preflight_checks(ctx)
                if passed:
                    ctx.pending_state = AgentState.REJOINING
                else:
                    ctx.status_text = (
                        'Rejoin preflight failed: '
                        + '; '.join(failures[:2])
                    )
                    self.get_logger().warn(
                        f'[agent {aid}] Rejoin preflight basarisiz'
                    )

        elif eid in (
            SystemEvent.EVENT_MANEUVER_STARTED,
            SystemEvent.EVENT_ROTATION_STARTED,
        ):
            if is_mine and ctx.state == AgentState.IN_SWARM:
                ctx.pending_state = AgentState.EXECUTING_TASK

        elif eid in (
            SystemEvent.EVENT_MANEUVER_COMPLETED,
            SystemEvent.EVENT_ROTATION_COMPLETED,
            SystemEvent.EVENT_FORMATION_REACHED,
        ):
            if is_mine and ctx.state == AgentState.EXECUTING_TASK:
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_MANEUVER_FAILED and is_mine:
            if ctx.state == AgentState.EXECUTING_TASK:
                ctx.status_text = 'Manevra başarısız, sürüye dönülüyor'
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_AGENT_JOIN_REQUEST and is_mine:
            ctx.wants_to_join = True

        elif eid == SystemEvent.EVENT_KILL_SWITCH_ACTIVATED:
            ctx.kill_switch_active = True

        elif eid == SystemEvent.EVENT_RC_LINK_LOST:
            ctx.rc_link_ok = False

        elif eid == SystemEvent.EVENT_OSCILLATION_DETECTED:
            ctx.oscillation_detected = True

        elif eid == SystemEvent.EVENT_UNSTABLE_FLIGHT:
            ctx.unstable_flight = True

        elif eid == SystemEvent.EVENT_MISSION_COMPLETED:
            if ctx.state == AgentState.LANDED:
                ctx.pending_state = AgentState.IDLE

        elif eid == SystemEvent.EVENT_ORIGIN_SYNCED:
            # Bilgi amaçlı olay; bayrağı BURADAN set etme. origin_synced'in
            # tek kaynağı px4_bridge telemetrisidir (frame gerçekten kuruldu
            # mu). Olayla set edersek, kurulmamışken 'senkronum' deriz.
            pass

        elif eid == SystemEvent.EVENT_GEOFENCE_VIOLATION:
            ctx.geofence_violated = True

    def _handle_failsafe_cleared(self) -> None:
        """FAILSAFE durumunu temizler."""
        ctx = self._ctx
        ctx.geofence_violated = False

        if ctx.state != AgentState.FAILSAFE:
            return

        if not ctx.armed:
            ctx.pending_state = AgentState.IDLE
        elif self._px4_landed:
            ctx.pending_state = AgentState.IDLE
        else:
            ctx.pending_state = AgentState.RETURN_HOME

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """Referans koordinat sistemini isler."""
        if msg.valid and msg.gps_fix_type >= 3:
            # origin_synced BURADA set EDİLMEZ: "ortak origin mesajını aldım"
            # ile "paylaşılan frame'i kurabildim" aynı şey değildir. PX4, EKF
            # init sonrası SET_GPS_GLOBAL_ORIGIN'i yok sayar; frame'i kurup
            # kuramadığımızı yalnız px4_bridge bilir ve telemetride bildirir.
            self._ctx.origin_sequence = msg.sequence

    def _handle_assign_role(
        self,
        request: AssignRole.Request,
        response: AssignRole.Response,
    ) -> AssignRole.Response:
        """Swarm manager'dan gelen rol atama istegini isler."""
        ctx = self._ctx

        role_map = {
            AssignRole.Request.ROLE_LEADER:   AgentRole.LEADER,
            AssignRole.Request.ROLE_FOLLOWER: AgentRole.FOLLOWER,
            AssignRole.Request.ROLE_STANDBY:  AgentRole.STANDBY,
            AssignRole.Request.ROLE_DETACHED: AgentRole.DETACHED,
        }
        new_role = role_map.get(request.role)

        if new_role is None:
            response.success = False
            response.message = f'Bilinmeyen rol: {request.role}'
            return response

        ctx.role = new_role

        if new_role == AgentRole.STANDBY:
            ctx.set_state(AgentState.STANDBY)

        response.success = True
        response.message = f'Rol atandı: {ctx.role.name}'
        self.get_logger().info(
            f'[agent {ctx.agent_id}] Rol: {ctx.role.name}'
        )
        return response

    def _on_telemetry(self, msg: AgentStatus) -> None:
        """Telemetry mesajini context'e yazar."""
        ctx = self._ctx
        prev_pilot = ctx.pilot_override_active

        # Ilk mesajla birlikte "artik veriye dayanarak karar verebilirim" isareti.  # noqa: E501
        # Bundan once saglik kontrolleri hukum vermez (bkz agent_context.py).
        ctx.telemetri_alindi = True
        ctx.px4_link_ok = msg.px4_link_ok
        ctx.armed = msg.armed
        ctx.offboard_enabled = msg.offboard_enabled
        ctx.offboard_active = msg.offboard_active
        if ctx.offboard_active:
            ctx.offboard_lost_since = None
        elif ctx.offboard_lost_since is None:
            ctx.offboard_lost_since = time.monotonic()

        ctx.flight_mode = FlightMode(msg.flight_mode)
        ctx.pilot_override_active = msg.pilot_override_active
        ctx.failsafe_active = msg.failsafe_active
        ctx.rc_signal_failsafe_active = msg.rc_signal_failsafe_active
        ctx.rc_link_ok = msg.rc_link_ok
        # Kill switch'i TELEMETRIDEN oku. Eskiden yalnizca
        # EVENT_KILL_SWITCH_ACTIVATED olayindan set ediliyordu ve o olayi
        # hicbir dugum uretmiyordu; ustelik o yol sadece True yapip hicbir
        # zaman geri almiyordu. Telemetri hem set hem clear'i doguru tasir:
        # px4_bridge her RC mesajinda kanal degerinden hesapliyor.
        ctx.kill_switch_active = msg.kill_switch_active
        # PX4 PREARM_CHECK biti (px4_bridge /diagnostics'ten cikariyor).
        # Bu satir olmadan ctx.ready_to_arm varsayilan False'ta kaliyor ve
        # _publish_status onu oyle yayinliyordu — YKİ'de "ARM EDILEMEZ"
        # uyarisi buton basilsa da hic kaybolmuyordu.
        ctx.ready_to_arm = msg.ready_to_arm

        ctx.battery_voltage_v = msg.battery_voltage_v
        ctx.battery_current_a = msg.battery_current_a
        ctx.battery_percent = msg.battery_percent

        ctx.pos_x = msg.pos_x
        ctx.pos_y = msg.pos_y
        ctx.pos_z = msg.pos_z
        ctx.vel_x = msg.vel_x
        ctx.vel_y = msg.vel_y
        ctx.vel_z = msg.vel_z
        # origin_synced'in TEK doğru kaynağı px4_bridge telemetrisidir:
        # paylaşılan frame gerçekten kurulabildi mi (ortak origin VE PX4'ün
        # geçerli global referansı). Burada üretilmez, aynen taşınır.
        ctx.origin_synced = bool(msg.origin_synced)

        ctx.roll_deg = msg.roll_deg
        ctx.pitch_deg = msg.pitch_deg
        ctx.heading_deg = msg.heading_deg

        ctx.gps_fix_type = msg.gps_fix_type
        ctx.gps_hdop = msg.gps_hdop
        ctx.gps_satellites = msg.gps_satellites
        ctx.lat_deg = msg.lat_deg
        ctx.lon_deg = msg.lon_deg
        ctx.alt_amsl_m = msg.alt_amsl_m

        ctx.home_set = msg.home_set
        ctx.home_lat_deg = msg.home_lat_deg
        ctx.home_lon_deg = msg.home_lon_deg
        ctx.home_alt_amsl_m = msg.home_alt_amsl_m

        ctx.imu_healthy = msg.imu_healthy
        ctx.mag_healthy = msg.mag_healthy
        ctx.baro_healthy = msg.baro_healthy

        ctx.estimator_ok = msg.estimator_ok
        ctx.xy_valid = msg.xy_valid
        ctx.z_valid = msg.z_valid
        ctx.v_xy_valid = msg.v_xy_valid

        all_valid = (
            msg.estimator_ok and msg.xy_valid
            and msg.z_valid and msg.v_xy_valid
        )
        if all_valid:
            ctx.estimator_stable_ticks += 1
        else:
            ctx.estimator_stable_ticks = 0

        self._px4_landed = (
            not ctx.armed and abs(ctx.vel_z) < _GROUND_VEL_THR
        )

        if ctx.pilot_override_active and not prev_pilot:
            ctx.autonomous_control_paused = True
            ctx.status_text = _PILOT_OVERRIDE_METNI
            self.get_logger().warn(
                f'[agent {ctx.agent_id}] PILOT OVERRIDE: '
                f'mod={ctx.flight_mode.name} — otonom geçişler DURDU '
                f'(evaluate_transitions autonomous_control_paused ile '
                f'None dönüyor)'
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_PILOT_OVERRIDE,
                SystemEvent.SEVERITY_WARNING,
                'Manuel mod tespit edildi',
            )
        elif not ctx.pilot_override_active:
            if ctx.autonomous_control_paused:
                self.get_logger().info(
                    f'[agent {ctx.agent_id}] pilot override kalktı '
                    f'(mod={ctx.flight_mode.name}) — otonomi devam ediyor'
                )
            ctx.autonomous_control_paused = False
            # Metni SADECE kendi yazdığımızsa temizliyoruz. Koşulsuz
            # temizlemek safety hold / sağlık uyarısı gibi daha önemli
            # mesajları ezerdi (status_text'in 20'den fazla yazarı var).
            if ctx.status_text == _PILOT_OVERRIDE_METNI:
                ctx.status_text = ''

        self._prev_pilot_override = ctx.pilot_override_active

    def _publish_status(self) -> None:
        """Aciklama: AgentContext'i AgentStatus mesajina donusturup yayinlar."""  # noqa: E501
        ctx = self._ctx
        m = AgentStatus()
        m.stamp = self.get_clock().now().to_msg()

        m.agent_id = ctx.agent_id
        m.role = int(ctx.role)
        m.state = int(ctx.state)

        m.px4_link_ok = ctx.px4_link_ok
        m.gcs_link_ok = ctx.gcs_link_ok

        m.armed = ctx.armed
        m.offboard_enabled = ctx.offboard_enabled
        m.offboard_active = ctx.offboard_active
        m.flight_mode = int(ctx.flight_mode)
        m.pilot_override_active = ctx.pilot_override_active

        m.failsafe_active = ctx.failsafe_active
        m.healthy = ctx.healthy

        m.battery_percent = ctx.battery_percent
        m.battery_voltage_v = ctx.battery_voltage_v
        m.battery_current_a = ctx.battery_current_a

        m.pos_x = ctx.pos_x
        m.pos_y = ctx.pos_y
        m.pos_z = ctx.pos_z
        m.vel_x = ctx.vel_x
        m.vel_y = ctx.vel_y
        m.vel_z = ctx.vel_z

        m.heading_deg = ctx.heading_deg
        m.roll_deg = ctx.roll_deg
        m.pitch_deg = ctx.pitch_deg

        m.gps_fix_type = ctx.gps_fix_type
        m.gps_hdop = ctx.gps_hdop
        m.gps_satellites = ctx.gps_satellites

        m.lat_deg = ctx.lat_deg
        m.lon_deg = ctx.lon_deg
        m.alt_amsl_m = ctx.alt_amsl_m

        m.home_set = ctx.home_set
        m.home_lat_deg = ctx.home_lat_deg
        m.home_lon_deg = ctx.home_lon_deg
        m.home_alt_amsl_m = ctx.home_alt_amsl_m

        m.imu_healthy = ctx.imu_healthy
        m.mag_healthy = ctx.mag_healthy
        m.baro_healthy = ctx.baro_healthy

        m.estimator_ok = ctx.estimator_ok
        m.xy_valid = ctx.xy_valid
        m.z_valid = ctx.z_valid
        m.v_xy_valid = ctx.v_xy_valid

        m.origin_synced = ctx.origin_synced
        m.origin_sequence = ctx.origin_sequence

        m.rc_link_ok = ctx.rc_link_ok
        m.kill_switch_active = ctx.kill_switch_active
        m.rc_signal_failsafe_active = ctx.rc_signal_failsafe_active

        m.oscillation_detected = ctx.oscillation_detected
        m.unstable_flight = ctx.unstable_flight

        m.wants_to_join = ctx.wants_to_join
        m.ready_to_arm = ctx.ready_to_arm

        m.status_text = ctx.status_text

        self._status_pub.publish(m)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
        target_agent_id: int = 0,
    ) -> None:
        """Aciklama: SystemEvent yayinlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = self._ctx.agent_id
        m.target_agent_id = target_agent_id
        m.source_module = 'agent_fsm'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AgentFsmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
