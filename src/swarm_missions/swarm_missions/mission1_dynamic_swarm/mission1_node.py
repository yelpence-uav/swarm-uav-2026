"""mission1_node.py — Görev 1 dinamik sürü orkestratör ROS2 node'u."""

import math

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import Bool, Float32MultiArray, UInt8

from swarm_interfaces.action import ExecuteManeuver
from swarm_interfaces.msg import (
    AgentStatus,
    FormationCommand,
    MissionTarget,
    QRMissionData,
    SwarmOrigin,
    SwarmState,
    SystemEvent,
)

from .orchestrator import (
    DetachCmd,
    FormationReachedCmd,
    FormationTargetCmd,
    ManeuverCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
    QrReachedCmd,
    RotationCompletedCmd,
)

# MissionState.RETURN_HOME sayisal degeri (orchestrator._S_RETURN_HOME ile
# birebir). Yalnizca teshis logunu bu fazla sinirlamak icin kullanilir.
_SYNCHRONIZED_TAKEOFF_STATE = 3
_RETURN_HOME_STATE = 9

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# origin latched yayınlanır; geç başlayan mission1 son değeri alsın.
_LATCHED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


# Ajan telemetrisi BEST_EFFORT yayınlanır; RELIABLE ile abone olunursa QoS
# uyuşmazlığı yüzünden hiç veri gelmez.
_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# Ayar konusu MANDALLI: yayin bir kez yapiliyor ve bu dugum gec abone
# olabilir. esp32_bridge tarafiyla birebir ayni profil olmali, yoksa QoS
# uyusmazligindan mesaj HIC gelmez ve hicbir hata gorunmez.
_AYAR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class Mission1Node(Node):
    """Görev 1 orkestratör node'u — faz okur, komut üretip icra eder."""

    def __init__(self) -> None:
        """Parametreler, orchestrator, I/O ve tick döngüsünü kurar."""
        super().__init__('mission1_dynamic_swarm')

        self._declare_params()

        self._orch = Mission1Orchestrator(OrchestratorConfig(
            default_formation_type=self._default_formation_type,
            default_spacing_m=self._default_spacing_m,
            wing_alpha_rad=math.radians(self._wing_alpha_deg),
            maneuver_duration_s=self._maneuver_duration_s,
            full_agent_count=len(self._agent_ids),
            gorev_formasyon=int(self.get_parameter('gorev_formasyon').value),
            gorev_aralik_m=float(self.get_parameter('gorev_aralik_m').value),
            donus_yaw_deg=float(self.get_parameter('donus_yaw_deg').value),
            donus_katman_m=float(self.get_parameter('donus_katman_m').value),
            toplanma_katman_m=float(
                self.get_parameter('toplanma_katman_m').value),
            dagilma_hiz_mps=float(
                self.get_parameter('dagilma_hiz_mps').value),
            gorev_kurulum_hiz_mps=float(
                self.get_parameter('gorev_kurulum_hiz_mps').value),
            qr_okuma_irtifa_m=float(
                self.get_parameter('qr_okuma_irtifa_m').value),
        ))

        # HOME kilidi icin beklenen kadro (bkz. _on_swarm_state).
        self._cfg_full_agent_count = len(self._agent_ids)
        self._mission_state = 0
        self._state_entry_time = self._now_s()
        self._qr_step = 0
        self._current_qr = None
        self._last_qr_seq = 0
        # Son işlenen QR'ın NUMARASI (qr_id). Ayırt edici bu; qr_seq her vision
        # node'unda bağımsız sayıldığından farklı QR'lar aynı seq'i taşıyabilir.
        self._last_qr_id = 0
        self._leader_id = 0
        self._centroid = (0.0, 0.0, 0.0)
        self._agent_ids_live = list(self._agent_ids)
        self._positions = []
        self._home_xy = None
        self._have_swarm_state = False
        self._yaw_deg = None   # kalkış heading'i / snapshot referansı
        # Kalkis denetimi icin kendi telemetrimiz (bkz. _kalkis_denetle).
        self._alt_amsl_m = None
        self._home_alt_amsl_m = 0.0
        self._gps_fix_type = 0
        self._vel_z = 0.0
        self._kalkis_bildirildi = False
        self._seq = 0

        self._setup_io()
        self._maneuver_client = ActionClient(
            self, ExecuteManeuver,
            f'/drone_{self._agent_id}/maneuver/execute',
        )

        self._timer = self.create_timer(1.0 / self._tick_hz, self._tick)

        self.get_logger().info(
            f'Mission1Node başladı: agent_id={self._agent_id} '
            f'takım={self._team_id} tick={self._tick_hz}Hz'
        )

    # --- Başlatma ------------------------------------------------------------

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('team_id', '752825')
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('default_formation_type', 1)
        self.declare_parameter('default_spacing_m', 5.0)
        self.declare_parameter('wing_alpha_deg', 45.0)
        self.declare_parameter('maneuver_duration_s', 3.0)
        # --- GOREV 1 UCUS PROFILI (operator, 2 Eylul gecesi) ---------------
        # Hepsi KAPALI varsayilanla geliyor: gorev_formasyon=0 ve
        # donus_yaw_deg=0 ile davranis eskisinin AYNISI (sartname yolu).
        # Acmak icin baslat.sh -p ... gecirir.
        self.declare_parameter('gorev_formasyon', 0)
        self.declare_parameter('gorev_aralik_m', 7.0)
        self.declare_parameter('donus_yaw_deg', 0.0)
        self.declare_parameter('donus_katman_m', 5.0)
        # Toplanma merdiveni — kalkistan ilk formasyona gecerken dikey
        # ayirma. 0.0 = KAPALI (davranis eskisinin aynisi).
        self.declare_parameter('toplanma_katman_m', 0.0)
        self.declare_parameter('dagilma_hiz_mps', 1.0)
        self.declare_parameter('gorev_kurulum_hiz_mps', 0.0)
        # 🔴 KALKIS IRTIFASI — agent_fsm'in target_altitude_m'i ile AYNI
        # olmak ZORUNDA. Ikisi ayrisirsa gorev node'u "ulastim" derken
        # agent_fsm baska bir sayiya bakar; ikisi de sessizce yanilir.
        # Tek kaynak: ucus_ayarlari.py GOREV_KALKIS_IRTIFA_M -> baslat.sh
        # her iki dugume de AYNI degeri geciriyor.
        self.declare_parameter('kalkis_irtifa_m', 10.0)
        # QR OKUMA IRTIFASI — NAVIGATE bacaginin hedef irtifasi.
        # Tek kaynak: ucus_ayarlari.py GOREV_QR_OKUMA_IRTIFA_M -> baslat.sh.
        self.declare_parameter('qr_okuma_irtifa_m', 10.0)
        self.declare_parameter('kalkis_tolerans_m', 0.5)
        self.declare_parameter('kalkis_dikey_hiz_esik_mps', 0.5)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._agent_ids = [int(a) for a in self.get_parameter('agent_ids').value]
        self._team_id = str(self.get_parameter('team_id').value)
        self._tick_hz = float(self.get_parameter('tick_hz').value)
        self._default_formation_type = int(
            self.get_parameter('default_formation_type').value
        )
        self._default_spacing_m = float(
            self.get_parameter('default_spacing_m').value
        )
        self._wing_alpha_deg = float(
            self.get_parameter('wing_alpha_deg').value
        )
        self._maneuver_duration_s = float(
            self.get_parameter('maneuver_duration_s').value
        )
        self._kalkis_irtifa_m = float(
            self.get_parameter('kalkis_irtifa_m').value
        )
        self._kalkis_tolerans_m = float(
            self.get_parameter('kalkis_tolerans_m').value
        )
        self._kalkis_dikey_hiz_esik = float(
            self.get_parameter('kalkis_dikey_hiz_esik_mps').value
        )

    def _setup_io(self) -> None:
        """Abonelik ve yayıncıları kurar."""
        self.create_subscription(
            UInt8, '/swarm/public/mission/state',
            self._on_mission_state, _RELIABLE_QOS,
        )
        self.create_subscription(
            UInt8, '/swarm/public/mission/qr_step',
            self._on_qr_step, _RELIABLE_QOS,
        )
        self.create_subscription(
            QRMissionData, '/swarm/public/perception/qr_data',
            # BEST_EFFORT SART — mesh kaynagi esp32_bridge _MESH_QOS ile
            # yayinliyor; RELIABLE abone QR verisini HIC almaz.
            self._on_qr_data, _BEST_EFFORT_QOS,
        )
        # BASLANGIC FORMASYONU YKI'DEN (4 Eylul 2026). Onceden
        # `gorev_formasyon` yalnizca baslat.sh parametresiydi: operator
        # formasyonu degistirmek icin dosyaya yazip konteyneri restart
        # etmek zorundaydi.
        # ⚠️ MANDALLI QoS (TRANSIENT_LOCAL) SART: ayar BASLAT tetiginden
        # once yayinlaniyor ve bu dugum gec abone olabilir. VOLATILE
        # olsaydi ayari kacirir, suru eski formasyonla toplanir ve
        # operator sectigini sanardi.
        self.create_subscription(
            Float32MultiArray, '/swarm/public/mission/g1_ayar',
            self._on_g1_ayar, _AYAR_QOS,
        )
        self.create_subscription(
            SwarmState, '/swarm/public/state',
            self._on_swarm_state, _RELIABLE_QOS,
        )
        self.create_subscription(
            MissionTarget, '/swarm/public/mission/next_target',
            self._on_next_target, _RELIABLE_QOS,
        )
        self.create_subscription(
            SwarmOrigin, '/swarm/public/origin',
            self._on_origin, _LATCHED_QOS,
        )

        # Kendi telemetrimiz — YALNIZ yaw için (kalkış referansı).
        self.create_subscription(
            AgentStatus, f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_telemetry, _BEST_EFFORT_QOS,
        )

        self._formation_pub = self.create_publisher(
            FormationCommand, '/swarm/path_planning/target', _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

        # 🔴 KALKIS TAMAM — gorev node'unun agent_fsm'e verdigi TEK sinyal.
        # Setpoint DEGIL, karar. Boylece §4 tek-uretici kurali bozulmuyor:
        # setpoint'i yine formation_node/collision_avoidance uretiyor,
        # burasi yalniz "hedef irtifadayim" diyor.
        self._kalkis_pub = self.create_publisher(
            Bool, '/swarm/internal/mission/kalkis_tamam', _RELIABLE_QOS,
        )

    # --- Abonelik callback'leri ----------------------------------------------

    def _now_s(self) -> float:
        """Node saatini saniye cinsinden döner (sim-time uyumlu)."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_mission_state(self, msg: UInt8) -> None:
        """Güncel MissionState'i saklar; faz değişiminde süre sayacını sıfırlar."""
        new_state = int(msg.data)
        if new_state != self._mission_state:
            self._state_entry_time = self._now_s()
        self._mission_state = new_state

    def _on_qr_step(self, msg: UInt8) -> None:
        """Güncel QrTaskStep'i saklar."""
        self._qr_step = int(msg.data)

    def _on_qr_data(self, msg: QRMissionData) -> None:
        """QR görev verisini saklar; aynı QR tekrar tekrar işlenmez."""
        if self._team_id and msg.team_id != self._team_id:
            return
        if not msg.decoded or not msg.valid:
            return
        qr_id = int(msg.qr_id)
        if qr_id and qr_id == self._last_qr_id:
            return
        self._last_qr_id = qr_id
        self._last_qr_seq = int(msg.qr_seq)
        self._current_qr = msg

    def _on_g1_ayar(self, msg: Float32MultiArray) -> None:
        """YKİ'nin seçtiği başlangıç formasyonunu uygular.

        data = [formasyon_tipi, aralik_m]. 0 = "belirtilmedi" → o alan için
        `baslat.sh`'ten gelen parametre KORUNUR (geriye uyumlu).

        ⚠️ YALNIZ FORMASYON KURULMADAN ÖNCE ETKİLİ. `_gorev_formasyonunu_uygula`
        formasyonu bir kez kurup `gorev_formasyon_kuruldu` bayrağını
        dikiyor; sonrasında gelen ayar BİLEREK yok sayılıyor — görev
        ortasında başlangıç formasyonunu değiştirmek QR'ın dayattığı
        formasyonu ezerdi.
        """
        v = list(msg.data)
        frm = int(v[0]) if len(v) > 0 else 0
        aralik = float(v[1]) if len(v) > 1 else 0.0
        if self._orch._st.gorev_formasyon_kuruldu:
            self.get_logger().warning(
                f'[gorev1] baslangic formasyonu ayari GEC GELDI '
                f'(tip={frm}) — formasyon zaten kuruldu, yok sayiliyor'
            )
            return
        if frm > 0:
            self._orch._cfg.gorev_formasyon = frm
        if aralik > 0.0:
            self._orch._cfg.gorev_aralik_m = aralik
        self.get_logger().warning(
            f'[gorev1] YKI baslangic formasyonu: tip='
            f'{self._orch._cfg.gorev_formasyon} '
            f'aralik={self._orch._cfg.gorev_aralik_m:.1f} m'
        )

    def _on_swarm_state(self, msg: SwarmState) -> None:
        """Lider, centroid ve aktif ajan konumlarını saklar."""
        self._leader_id = int(msg.leader_id)
        self._centroid = (
            float(msg.centroid_x), float(msg.centroid_y), float(msg.centroid_z),
        )
        self._agent_ids_live = [int(a) for a in msg.active_agent_ids]
        self._positions = [
            (float(x), float(y), float(z))
            for x, y, z in zip(msg.agent_pos_x, msg.agent_pos_y, msg.agent_pos_z)
        ]
        self._have_swarm_state = True
        # Home = kalkış centroid'i (XY); RETURN_HOME buraya döner.
        #
        # 🔴 KONUMLAR GECERLI OLMADAN KILITLEME — 3 Eylul 2026 saha olayi.
        #
        # Eski kosul yalniz `active_agent_count > 0` idi. Sonucu olculdu:
        # ilk SwarmState centroid'i (0,0) ile geldi (konumlar heniz akmiyor)
        # ve HOME ORIGIN'E KILITLENDI. Kalkis merkezi (+3.4, -3.9) oldugu
        # halde RETURN_HOME sürüyü (0,0)'a cagirdi:
        #     "RETURN_HOME: home=(0.0, 0.0) centroid=(3.4, -3.9) mesafe=5.2m"
        # Yani "kalktigi yere in" 5 metre yanlis noktaya donusuyordu ve
        # HICBIR YERDE hata gorunmuyordu — home_xy_set=True diyordu.
        #
        # Yeni kosul UC SART: kadro tam, konum listesi dolu ve centroid
        # dejenere degil. Biri tutmazsa BEKLER; kalkis oncesi bol bol
        # SwarmState geliyor, gec kilitlenmek zararsiz — YANLIS kilitlenmek
        # degil.
        if self._home_xy is None:
            n_bekl = self._cfg_full_agent_count or len(self._agent_ids)
            konum_ok = (len(self._positions) >= n_bekl
                        and int(msg.active_agent_count) >= n_bekl)
            merkez_ok = (abs(float(msg.centroid_x)) > 1e-6
                         or abs(float(msg.centroid_y)) > 1e-6)
            if konum_ok and merkez_ok:
                self._home_xy = (
                    float(msg.centroid_x), float(msg.centroid_y))
                self.get_logger().info(
                    f'[gorev1] HOME kilitlendi: '
                    f'({self._home_xy[0]:+.1f}, {self._home_xy[1]:+.1f}) '
                    f'— {int(msg.active_agent_count)} ucak, konum listesi dolu'
                )

    def _on_telemetry(self, msg: AgentStatus) -> None:
        """Kendi yaw'ımızı ve kalkış irtifa alanlarını saklar."""
        self._yaw_deg = float(msg.heading_deg)
        self._alt_amsl_m = float(msg.alt_amsl_m)
        self._home_alt_amsl_m = float(msg.home_alt_amsl_m)
        self._gps_fix_type = int(msg.gps_fix_type)
        self._vel_z = float(msg.vel_z)

    def _on_next_target(self, msg: MissionTarget) -> None:
        """mission_fsm'in çözdüğü sıradaki hedefi orchestrator'a iletir."""
        self._orch.set_next_target(msg.valid, msg.lat_deg, msg.lon_deg)
        self.get_logger().info(
            f'Sonraki hedef: QR{msg.qr_id} valid={msg.valid}'
        )

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """Geçerli SwarmOrigin'i orchestrator'a iletir."""
        if msg.valid:
            self._orch.set_origin(msg.origin_lat_deg, msg.origin_lon_deg)

    # --- Ana döngü -----------------------------------------------------------

    def _kalkis_denetle(self) -> None:
        """SYNCHRONIZED_TAKEOFF'ta "hedef irtifaya ulastim" kararini VERIR.

        🔴 NEDEN GOREV NODE'UNDA — 2 Eylul 2026, sahada olculdu.

        Bu karar agent_fsm'deydi (agent_health_monitor.py) ve YANLIS SIFIRDAN
        olcuyordu:
            px4_bridge  hedef = mevcut_z - 10.0      -> ARM noktasina goreli
            agent_fsm   ulasti = pos_z <= -(10-0.5)  -> NED ORIGIN'e mutlak
        NED origin yerde degil, paylasilan suru origin'i (alt=1216.96 m AMSL);
        ucaklar ondan ~1.3-1.6 m asagida armlaniyor. Olculdu: ylp00 arm z=1.56,
        hedef NED -8.44, agent_fsm -9.50 bekliyordu -> 1.06 m acik; ylp02
        arm z=1.32 -> 0.80 m acik. Iki ucak da 10.0 m'ye cikip STABIL durdu
        (kaydedilen irtifa 9.9 / 10.0, sabit) ama "ulastim" HIC diyemedi ve
        30 sn sonra TAKEOFF timeout -> FAILSAFE. Ucusta hicbir sorun yoktu;
        yalniz olcum sifiri yanlisti.

        Ayni hata bu depoda UCUNCU kez: esp32_bridge'de POSE icin, sonra
        collision_avoidance'ta irtifa kapisi icin duzeltilmisti
        (collision_avoidance_node.py:438 yorumu), agent_fsm'de kalmisti.

        Dogru olcum home'a GORELI: alt_amsl_m - home_alt_amsl_m. Kaynak
        kanitli — bu gece collision_avoidance ayni degeri 9.9/10.0 diye
        DOGRU okudu. Koruma da oradan birebir alindi (satir 443): home
        irtifasi 0 ya da fix < 3 ise irtifa BILINMIYOR sayilir ve karar
        VERILMEZ; yoksa alt_amsl'in kendisi (~1217 m) "ulastim" sanilirdi.

        Yayin bir EMIR degil bir KARAR: agent_fsm bunu yalniz TAKEOFF
        durumundayken dinler, kendi 30 sn zaman asimi guvenlik agi olarak
        yerinde kalir.
        """
        if self._mission_state != _SYNCHRONIZED_TAKEOFF_STATE:
            self._kalkis_bildirildi = False
            return
        if self._alt_amsl_m is None:
            return
        if (self._home_alt_amsl_m == 0.0 or self._gps_fix_type < 3
                or not math.isfinite(self._alt_amsl_m)):
            return

        irtifa = self._alt_amsl_m - self._home_alt_amsl_m
        if irtifa < self._kalkis_irtifa_m - self._kalkis_tolerans_m:
            return
        if abs(self._vel_z) >= self._kalkis_dikey_hiz_esik:
            return          # hala tirmaniyor/aliyor — oturmasini bekle

        m = Bool()
        m.data = True
        self._kalkis_pub.publish(m)
        if not self._kalkis_bildirildi:
            self._kalkis_bildirildi = True
            self.get_logger().warning(
                f'[gorev1] KALKIS TAMAM: irtifa={irtifa:.2f} m '
                f'(hedef {self._kalkis_irtifa_m:.1f} -'
                f'{self._kalkis_tolerans_m:.1f}) '
                f'dikey_hiz={self._vel_z:.2f} m/s — agent_fsm IN_SWARM'
            )

    def _tick(self) -> None:
        """tick_hz'de: bağlamı topla, karar al, komutları icra et."""
        # Kalkis karari swarm_state'ten ONCE: kalkis sirasinda /swarm/public/
        # state heniz akmiyor olabilir ve asagidaki erken donus bu karari
        # sessizce bloklardi — kilitlenmenin ta kendisi.
        self._kalkis_denetle()

        if not self._have_swarm_state:
            return

        home_xy = self._home_xy or (self._centroid[0], self._centroid[1])
        home = (home_xy[0], home_xy[1], self._centroid[2])

        # RETURN_HOME teshisi: sartname madde 18 sürünün formasyonu bozmadan
        # home'a inmesini ister, ama olculdu ki suru RETURN_HOME'da hic hareket
        # etmiyor (komut edilen hiz ~0.01 m/s, ev 22.8 m uzakta). Iki ihtimal:
        #   (1) _home_xy hic set edilmemis -> yukaridaki yedek "su anki centroid"i
        #       ev sayar; hedef = mevcut konum -> mesafe 0 -> hiz 0 (SESSIZ hata),
        #   (2) ev dogru ama komut iletilmiyor.
        # Bu satir ikisini ayirir: home ile centroid AYNI ise (1), degilse (2).
        if self._mission_state == _RETURN_HOME_STATE:
            dn = home[0] - self._centroid[0]
            de = home[1] - self._centroid[1]
            self.get_logger().warn(
                f'RETURN_HOME: home=({home[0]:.1f}, {home[1]:.1f}) '
                f'centroid=({self._centroid[0]:.1f}, {self._centroid[1]:.1f}) '
                f'mesafe={math.hypot(dn, de):.1f}m '
                f'home_xy_set={self._home_xy is not None}',
                throttle_duration_sec=3.0,
            )

        inp = OrchestratorInput(
            mission_state=self._mission_state,
            qr_step=self._qr_step,
            is_leader=(self._leader_id == self._agent_id),
            agent_ids=list(self._agent_ids_live),
            positions=list(self._positions),
            centroid=self._centroid,
            home=home,
            qr=self._current_qr,
            time_in_state=self._now_s() - self._state_entry_time,
            swarm_yaw_deg=self._yaw_deg,
        )

        for cmd in self._orch.decide(inp):
            self._execute(cmd)

        # Teşhis: NAVIGATE'te en yakın dronun QR'a uzaklığı — kontrolün
        # gerçekte kaç metreye yaklaştığını (yakınsama eğrisi) görmek için.
        notu = self._orch.donus_notu
        if notu and inp.is_leader:
            self.get_logger().info(f'[gorev1] {notu}')

        d = self._orch.qr_distance_m
        if inp.is_leader and d >= 0.0:
            self.get_logger().info(
                f'QR mesafe: {d:.2f}m', throttle_duration_sec=2.0
            )

        # QR'ın istediği irtifa izinli bandın dışındaysa banda sığdırıldı: o
        # irtifada uçmuyoruz, görünür olsun.
        clamp = self._orch.altitude_clamped
        if inp.is_leader and clamp is not None:
            self.get_logger().warn(
                f'QR {clamp[0]:.0f}m irtifa istedi; izinli bant dışı, '
                f'{clamp[1]:.0f}m uygulandı.',
                throttle_duration_sec=5.0,
            )

    def _execute(self, cmd) -> None:
        """Orchestrator komutunu ilgili aktüatör kanalına yönlendirir."""
        if isinstance(cmd, FormationTargetCmd):
            self._publish_formation(cmd)
        elif isinstance(cmd, ManeuverCmd):
            self._send_maneuver(cmd)
        elif isinstance(cmd, DetachCmd):
            self._publish_member_event(
                SystemEvent.EVENT_MEMBER_DETACH_STARTED,
                cmd.target_agent_id, 'ayrılma', value=cmd.detach_wait_s,
            )
        elif isinstance(cmd, QrReachedCmd):
            self._publish_arrival_event(cmd.distance_m)
        elif isinstance(cmd, FormationReachedCmd):
            self._publish_formation_reached_event(cmd)
        elif isinstance(cmd, RotationCompletedCmd):
            self._publish_rotation_completed_event(cmd)

    # --- Komut icrası --------------------------------------------------------

    def _publish_formation(self, cmd: FormationTargetCmd) -> None:
        """Formasyon hedefini path_planner'a FormationCommand olarak yayınlar."""
        m = FormationCommand()
        m.stamp = self.get_clock().now().to_msg()
        m.sequence_num = self._seq
        self._seq += 1
        m.formation_type = int(cmd.formation_type)
        m.center_x = float(cmd.center[0])
        m.center_y = float(cmd.center[1])
        m.center_z = float(cmd.center[2])
        m.heading_deg = float(cmd.heading_deg)
        m.spacing_m = float(cmd.spacing_m)
        m.use_current_centroid = bool(cmd.use_current_centroid)
        m.use_current_altitude = bool(cmd.use_current_altitude)
        m.rotate_towards_target = bool(cmd.rotate_towards_target)
        m.hold_after_reached = False
        m.agent_ids = [int(a) for a in cmd.agent_ids]
        m.offset_x = [float(o[0]) for o in cmd.offsets]
        m.offset_y = [float(o[1]) for o in cmd.offsets]
        m.offset_z = [float(o[2]) for o in cmd.offsets]
        m.max_speed_mps = float(getattr(cmd, 'max_speed', 0.0))
        m.source_module = 'mission1_dynamic_swarm'
        self._formation_pub.publish(m)
        self.get_logger().info(
            f'FormationCommand: tip={m.formation_type} '
            f'merkez=({m.center_x:.1f},{m.center_y:.1f},{m.center_z:.1f}) '
            f'heading={m.heading_deg:.0f} rotate={m.rotate_towards_target}'
        )

    def _send_maneuver(self, cmd: ManeuverCmd) -> None:
        """Lokal maneuver_executor'a ExecuteManeuver hedefi gönderir."""
        if not self._maneuver_client.server_is_ready():
            self.get_logger().warn(
                'maneuver_executor action sunucusu hazır değil; '
                'manevra gönderilemedi'
            )
            return
        goal = ExecuteManeuver.Goal()
        goal.stamp = self.get_clock().now().to_msg()
        goal.sequence_num = self._seq
        self._seq += 1
        goal.maneuver_type = int(cmd.maneuver_type)
        goal.pitch_deg = float(cmd.pitch_deg)
        goal.roll_deg = float(cmd.roll_deg)
        goal.yaw_deg = float(cmd.yaw_deg)
        goal.keep_centroid_fixed = True
        goal.hold_after_complete = bool(cmd.hold_after_complete)
        goal.duration_s = float(cmd.duration_s)
        goal.source_agent_id = self._agent_id
        goal.source_module = 'mission1_dynamic_swarm'
        self._maneuver_client.send_goal_async(goal).add_done_callback(
            self._on_maneuver_response
        )
        self.get_logger().info(
            f'Manevra gönderildi: pitch={goal.pitch_deg:.0f} '
            f'roll={goal.roll_deg:.0f} yaw={goal.yaw_deg:.0f}'
        )

    def _on_maneuver_response(self, future) -> None:
        """Manevra hedefinin kabul/ret sonucunu loglar."""
        try:
            handle = future.result()
        except Exception as exc:  # noqa: BLE001 - log ve devam
            self.get_logger().warn(f'Manevra hedefi başarısız: {exc}')
            return
        if not handle.accepted:
            self.get_logger().warn('Manevra hedefi reddedildi')

    def _publish_member_event(
        self, event_type: int, target_agent_id: int, label: str,
        value: float = 0.0,
    ) -> None:
        """Üye yönetim olayını (detach) SystemEvent olarak yayınlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.target_agent_id = int(target_agent_id)
        m.value = float(value)
        m.source_module = 'mission1_dynamic_swarm'
        m.message = f'Sürüden {label} başlatıldı: ajan {target_agent_id}'
        self._event_pub.publish(m)
        self.get_logger().info(f'{label} event: ajan {target_agent_id}')

    def _publish_rotation_completed_event(self, cmd) -> None:
        """Formasyon rotasyonu tamamlandı → EVENT_ROTATION_COMPLETED."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_ROTATION_COMPLETED
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.value = float(cmd.max_error_m)
        m.source_module = 'mission1_dynamic_swarm'
        m.message = f'Rotasyon tamamlandı (hata {cmd.max_error_m:.2f}m)'
        self._event_pub.publish(m)

        if cmd.timed_out:
            self.get_logger().warn(
                f'Rotasyon yakınsamadan süre aşımıyla geçildi; '
                f'hata {cmd.max_error_m:.2f}m (sürü yarı dönük olabilir)'
            )
        elif not cmd.clean:
            self.get_logger().warn(
                f'Rotasyon tamamlandı ama slot hatası büyük: '
                f'{cmd.max_error_m:.2f}m'
            )
        else:
            self.get_logger().info(
                f'Rotasyon tamamlandı (hata {cmd.max_error_m:.2f}m) '
                f'-> navigasyona geçiliyor'
            )

    def _publish_formation_reached_event(self, cmd) -> None:
        """QR alt-görevi (formasyon/irtifa) tamamlandı → EVENT_FORMATION_REACHED."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_FORMATION_REACHED
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.value = float(cmd.max_error_m)
        m.source_module = 'mission1_dynamic_swarm'
        m.message = f'Formasyon kuruldu (hata {cmd.max_error_m:.2f}m)'
        self._event_pub.publish(m)

        if cmd.timed_out:
            self.get_logger().warn(
                f'Formasyon yakınsamadan süre aşımıyla geçildi; '
                f'hata {cmd.max_error_m:.2f}m'
            )
        elif not cmd.clean:
            self.get_logger().warn(
                f'Formasyon kuruldu ama slot hatası büyük: '
                f'{cmd.max_error_m:.2f}m (bir dron takılmış olabilir)'
            )
        else:
            self.get_logger().info(
                f'Formasyon kuruldu (hata {cmd.max_error_m:.2f}m) '
                f'-> sonraki QR adımı'
            )

    def _publish_arrival_event(self, distance_m: float) -> None:
        """Okuyucu dron QR'a varınca EVENT_FORMATION_REACHED yayınlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_FORMATION_REACHED
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.value = float(distance_m)
        m.source_module = 'mission1_dynamic_swarm'
        m.message = f'QR varış: okuyucu dron {distance_m:.2f}m'
        self._event_pub.publish(m)
        self.get_logger().info(f'QR varış event: {distance_m:.2f}m')


def main(args=None) -> None:
    """ros2 run giriş noktası."""
    rclpy.init(args=args)
    node = Mission1Node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
