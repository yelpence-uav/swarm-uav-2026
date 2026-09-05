# Copyright 2026 Yelpence
"""Semi-autonomous suru kontrol koordinator dugumu."""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from std_msgs.msg import Bool, Float32MultiArray, String, UInt8

from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_UNKNOWN,
    FORMATION_V,
    compute_slot_offsets,
    rotate_offset,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    ElectionResult,
    FormationCommand,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from . import canli_param
from . import morf_kilidi
from . import slot_atama
from . import tek_yayinci
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
    # Morf kilidini dusuren cubuk esigi. rc_eksen.OLU_BANT (0.03) zaten
    # yukarida uygulandigi icin buraya ulasan her sey GERCEK girdidir;
    # 0.05 yalnizca gurultuye karsi ince bir pay.
    _MORF_CUBUK_ESIGI = 0.05

    """Gorev 2 yari otonom suru kontrol koordinatoru."""

    def __init__(self) -> None:
        super().__init__('mode_manager_node')

        self._declare_params()

        self._ctx = ModeContext(
            agent_ids=self._agent_ids,
            # Suru basligi bu kimligin pusulasindan alinir
            # (konumdan_tohumla). 0 = bilinmiyor -> ortalama.
            lider_id=(self._lider_id or 0),
            sitl_mode=self._sitl_mode,
        )
        # Limitleri ctx'e paramdan yaz (tek kaynak). Kumandadan gelen
        # max_* alanlari > 0 ise _on_control_command yine EZEBILIR —
        # o kanal hakem/pilot ayari icin bilerek acik birakildi.
        self._ctx.max_speed_mps = self._max_speed_mps
        self._ctx.max_accel_mps2 = self._max_accel_mps2
        self._ctx.max_accel_z_mps2 = self._max_accel_z_mps2
        self._ctx.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        self._ctx.max_tilt_deg = self._max_tilt_deg
        self._ctx.kalkis_esik_m = self._kalkis_esik_m
        self._ctx.kalkis_irtifa_m = self._kalkis_irtifa_m
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

        # G2-K9 / madde 29 — GOREV ONCESI CANLI AYAR.
        self.add_on_set_parameters_callback(self._param_degisti)

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
        # B6 ivme rampasi. Tek kaynak `ucus_ayarlari` MOD_IVME /
        # MOD_DIKEY_IVME; gerekce mode_context.compute_centroid_delta.
        self.declare_parameter('max_accel_mps2', 1.3, _dnm)
        self.declare_parameter('max_accel_z_mps2', 1.0, _dnm)
        self.declare_parameter('max_speed_mps', 2.0, _dnm)
        self.declare_parameter('max_yaw_rate_deg_s', 25.0, _dnm)
        self.declare_parameter('max_tilt_deg', 15.0, _dnm)
        # Slot geometrisi formation_node/kopru/sekans ile AYNI aci —
        # eskiden asagida math.radians(45.0) GOMULUYDU.
        self.declare_parameter('wing_alpha_deg', 45.0, _dnm)
        # B15 KALKIS KAPISI: bu yuksekligin ALTINDA hicbir tarif/setpoint
        # yayinlanmaz. Tek kaynak `ucus_ayarlari` MOD_KALKIS_ESIK.
        self.declare_parameter('kalkis_esik_m', 2.0, _dnm)
        # 🔴 KUMANDADAN KALKIS IRTIFASI (madde 25). TEST irtifasindan
        # (MOD_TEST_IRTIFA_M) AYRI parametre: sartname "belirlenen irtifaya
        # (Orn: 15m)" diyor ve hakem baska bir sayi soyleyebilir; manevra
        # testinin genligi bundan etkilenmemeli. Tek kaynak
        # `ucus_ayarlari` MOD_KALKIS_IRTIFA -> baslat.sh env.
        self.declare_parameter('kalkis_irtifa_m', 8.0, _dnm)
        # 🔴 FORMASYON MORFU AYRI HIZ — 1 Eylul 2026, ucusta olculdu.
        # Gerekce ve aritmetik: ucus_ayarlari.MOD_MORF_HIZ_MPS
        # 🔴 MESH KOMUTUNDA deadman_timeout_s TASINMIYOR — 1 Eylul 2026.
        # Gerekce ve olcum: asagida `_on_control_command`.
        self.declare_parameter('deadman_zaman_asimi_s', 0.5)
        self.declare_parameter('morf_hiz_mps', 0.6)
        self.declare_parameter('morf_sure_s', 25.0)
        # B3: mission_fsm kapaliyken FSM'i READY'ye ulastirir. VARSAYILAN
        # FALSE — yarisma profilinde ADIM 6 acilinca kapatilir.
        self.declare_parameter('test_hazir_atla', False)
        # SABIT LIDER (KARAR-17). consensus ile AYNI degeri almali;
        # 0 = kapali -> lider ElectionResult'tan ogrenilir (eski yol).
        self.declare_parameter('sabit_lider', 0)

        # SIRALI: slot atamasi kimlik SIRASINA bagli (slot i <-> agent_ids[i],
        # Macar YOK — KARAR-11) ve bu liste SURU_KADRO'dan geliyor. Kadro
        # "3 1" diye yazilirsa slot 0 ylp02'ye giderdi ve hicbir yerde hata
        # gorunmezdi. Siralamak bu sessiz bagimliligi kaldirir; _init_default_
        # offsets de artik deterministik.
        self._agent_ids = sorted(
            int(a) for a in self.get_parameter('agent_ids').value
        )
        self._agent_id = int(self.get_parameter('agent_id').value)
        # TEK-YAYINCI (3 Eylul kume-toplanma olayi): tarifi yalniz lider
        # basar. None = election henuz gelmedi -> min(agent_ids) yedegi.
        #
        # 🔴 SABIT LIDER VARSA ELECTION BEKLENMEZ — 4 Eylul 2026, UCUSTA
        # OLCULDU. O ucusta ylp01'in mode_manager'i uctan uca `lider=None`
        # kaldi: ElectionResult mesh'ten HIC ULASMADI (lider onu yalnizca
        # bir kez, secim aninda yayinliyor ve ESP-NOW kaybi %6,7-21,7
        # olculdu). Dogru davrandi ama SEBEBI TESADUFTU: yedek yol
        # min(agent_ids)=1 veriyordu ve sabit lider de 1'di.
        #
        # Tesadufun bozuldugu hal: kadro (1,3) + sabit lider 3 olsaydi
        # yedek yol 1 derdi -> YANLIS UCAK yayinci olur, gercek lider
        # susar, formasyon SESSIZCE kurulmazdi. 4 Eylul'un belirtisiyle
        # birebir ayni tablo. Bu yuzden consensus'un bildigi kimlik
        # mode_manager'a da AYNI parametreden veriliyor; mesh'e bagimli
        # olmaktan cikiyor.
        self._sabit_lider = int(self.get_parameter('sabit_lider').value)
        self._lider_id: int | None = (
            self._sabit_lider if self._sabit_lider > 0 else None
        )
        self._tek_yayinci_uyarildi = False
        self._son_islenen_aralik: float | None = None
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
        self._max_accel_mps2 = float(
            self.get_parameter('max_accel_mps2').value
        )
        self._max_accel_z_mps2 = float(
            self.get_parameter('max_accel_z_mps2').value
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
        self._deadman_zaman_asimi_s = float(
            self.get_parameter('deadman_zaman_asimi_s').value)
        self._morf_hiz_mps = float(self.get_parameter('morf_hiz_mps').value)
        self._morf_sure_s = float(self.get_parameter('morf_sure_s').value)
        # Morf kilidinin bitis ani (time.monotonic). 0.0 = morf yok.
        self._morf_bitis_s = 0.0
        self._kalkis_irtifa_m = float(
            self.get_parameter('kalkis_irtifa_m').value
        )
        self._test_hazir_atla = bool(
            self.get_parameter('test_hazir_atla').value
        )

    def _param_degisti(self, params):
        """ros2 param set icin dogrulama ve UYGULAMA (G2-K9, madde 29).

        Kapinin kendisi saf modulde (canli_param.py) — birim testle
        kilitli olmasi sart, cunku yanlis acilmasi kalkis kapisini ya da
        ARM yetkisini canli canli devre disi birakmak demek.

        🔴 NEDEN BU GERI CAGRI GEREKLI (30 Agustos 2026'da olculdu): bu
        dugumde geri cagri YOKTU ve butun parametreler __init__'te
        `self._*`'a KOPYALANIYOR. Yani `ros2 param set` calisiyor, "Set
        parameter successful" yaziyor ve dugum ESKI DEGERI kullanmaya
        devam ediyordu — G2-K9'un tarif ettigi "SSH ile canli param" yolu
        SESSIZ BIR NO-OP olurdu. Saha gununde hakem "aralik 5 m" der,
        YKI'de deger degisir, suru 7 m'de ucar ve kimse anlamaz.
        """
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            try:
                deger = canli_param.dogrula(
                    p.name, p.value, canli_param.MODE_MANAGER_CANLI)
            except canli_param.ParamRed as e:
                return SetParametersResult(successful=False, reason=str(e))

            if p.name == 'default_spacing_m':
                self._default_spacing_m = deger
                self._init_default_offsets()
            elif p.name == 'kalkis_irtifa_m':
                # Havadayken degistirmek anlamsiz ama zararsiz: olcut
                # yalniz TAKEOFF'ta okunuyor ve capa px4_bridge'de zaten
                # kurulmus durumda. Yine de gorunur olsun diye uyariyoruz.
                if self._ctx.kalkis_komutu_verildi:
                    self.get_logger().warning(
                        '[mode_manager] kalkis_irtifa_m UCUS SIRASINDA '
                        'degistirildi — bu kalkisa ETKI ETMEZ, hedef '
                        "px4_bridge'de zaten capalandi."
                    )
                self._kalkis_irtifa_m = deger
                self._ctx.kalkis_irtifa_m = deger
            # 🔴 SURU DAVRANIS AYARLARI — 5 Eylul 2026.
            # HEM `self._*` HEM `self._ctx.*` yazilir. Ikisi de gerekli:
            # __init__ degeri ctx'e KOPYALIYOR (satir 86-90) ve hareket/
            # manevra matematigi ctx'ten okuyor. Yalniz birini yazmak
            # yukaridaki docstring'in anlattigi SESSIZ NO-OP'un aynisini
            # uretirdi — "ayar gitti" gorunur, davranis degismez.
            elif p.name == 'max_speed_mps':
                self._max_speed_mps = deger
                self._ctx.max_speed_mps = deger
            elif p.name == 'max_yaw_rate_deg_s':
                self._max_yaw_rate_deg_s = deger
                self._ctx.max_yaw_rate_deg_s = deger
            elif p.name == 'max_tilt_deg':
                self._max_tilt_deg = deger
                self._ctx.max_tilt_deg = deger
            elif p.name == 'morf_hiz_mps':
                # ctx'te karsiligi YOK: morf hizi yayin aninda
                # `_morf_hizini_uygula` icinde okunuyor.
                self._morf_hiz_mps = deger

            self.get_logger().warning(
                f'[mode_manager] CANLI AYAR: {p.name} = {deger:g}'
            )
        return SetParametersResult(successful=True)

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

        # 🔴 INIS KOMUTU px4_bridge'E DOGRUDAN GIDER — 30 Agustos 2026.
        #
        # Bu konuda BIRDEN COK URETICI VAR (agent_fsm, esp32_bridge,
        # precision_landing) ve bu CLAUDE.md §4'e AYKIRI DEGIL: §4 kurali
        # 50 Hz'de akan SETPOINT akislari icin. Burasi ayrik bir komut
        # posta kutusu; tekrarlanan 'land' px4_bridge'de etkisiz
        # (px4_bridge.py:1397 capalari temizleyip AUTO.LAND'e gecer).
        self._komut_pub = self.create_publisher(
            String,
            f'/swarm/agent/drone{self._agent_id}/commands',
            _RELIABLE_QOS,
        )
        # 🔴 FORMASYONSUZ ofsetlerin DONDURULMUS kopyasi (31 Agu kusuru,
        # gerekce _publish_formation_command icindeki FORMATION_UNKNOWN
        # dalinda). None = henuz olculmedi / dondurma cozuldu.
        self._donmus_ofsetler: tuple[list, list, list] | None = None
        self._son_inis_komutu: float | None = None
        self._son_kalkis_komutu: float | None = None

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

        # --- MADDE 29: GOREV 2 ARALIK/IRTIFA (31 Agustos 2026) -----------
        # YKI "Gorev 2 baslat"a basmadan once iki sayi soruyor; degerler
        # mesh'te BASLAT paketiyle geliyor ve esp32_bridge burada duyuruyor.
        # Mandalli QoS: dugum sonradan acilsa bile son ayari alir.
        self.create_subscription(
            Float32MultiArray,
            '/swarm/public/mission/g2_ayar',
            self._on_g2_ayar,
            QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
            ),
        )

        self.create_subscription(
            SwarmState,
            '/swarm/public/state',
            self._on_swarm_state,
            _RELIABLE_QOS,
        )

        # --- TEK-YAYINCI (3 Eylul 2026): lider bilgisi -------------------
        # Iki kaynak: kendi consensus'um (internal) + mesh'ten gelen
        # (public, esp32_bridge basar). Ikisi de RELIABLE+TRANSIENT_LOCAL
        # (consensus_node.py:118 ve bridge _ELECTION_QOS ile ayni) —
        # VOLATILE abone SESSIZCE bos kalirdi, form_yayinla dersi.
        _el_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            ElectionResult,
            '/swarm/internal/election/result',
            self._on_election,
            _el_qos,
        )
        self.create_subscription(
            ElectionResult,
            '/swarm/public/election/result',
            self._on_election,
            _el_qos,
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

            # 🔴 KAPI ONCESI VERILEN FORMASYON KAYBOLUYORDU — 5 Eylul 2026,
            # SAHADA OLCULDU.
            #
            # BELIRTI (operator): "cizgi formasyonunda yere dizdim, aralik 6
            # verdim, kalktilar ve KALKTIKLARI YERDE BEKLEDILER. Aralarinda
            # 11 m vardi, 6 m'ye dusurmediler."
            #
            # ZINCIR: VrB acik + SwC cizgide -> formasyon_kilidi YENI_ACILDI
            # -> formation_change_requested -> _handle_formation_change
            # `ctx.active_formation = 3` YAZDI ama _publish_formation_command
            # kapida (`not kalkis_tamam`) DUSTU. Istek bir KENAR oldugu icin
            # ayni tick'te temizlendi. Kapi sonradan acildiginda kimse tarifi
            # yeniden istemiyordu -> suru UNKNOWN'da kaldi, olculen 11 m
            # donduruldu. Kayitta cizgi (tip 3) komutu HIC YOK; ilk komut
            # operator SwC'yi V'ye cevirdiginde (tip 2) cikti.
            #
            # Hicbir yerde hata yoktu: kapi sessizce dusuruyordu.
            #
            # COZUM: kapi acilirken aktif bir formasyon KAYITLIYSA tarifi
            # YENIDEN uret. Tekrar-yutucuyu (`_son_islenen_aralik`) bilerek
            # sifirliyoruz, yoksa "ayni tip + ayni aralik" diye elenirdi.
            # Merkez/baslik bu noktada TAZE (konumdan_tohumla yeni kostu),
            # yani eski params'i saklamak yerine yolu yeniden isletmek
            # dogru olani.
            if ctx.active_formation in (1, 2, 3):
                self.get_logger().warning(
                    '[mode_manager] KAPI ONCESI istenen formasyon YENIDEN '
                    f'uygulaniyor: tip={ctx.active_formation} '
                    f'aralik={ctx.requested_spacing_m or self._default_spacing_m:g} m '
                    '(kalkistan once verilen tarif kapida dusmustu)'
                )
                self._son_islenen_aralik = None
                ctx.requested_formation = ctx.active_formation
                ctx.formation_change_requested = True
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
                    "[mode_manager] UCAKLARIN YAW'LARI DAGINIK "
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
            # 🔴 MANEVRA-MORF ALT-FAZI (kilit açık + formasyon değişimi,
            # 4 Eylül operatör): manevra modundan ÇIKMADAN formasyon
            # değiştirilebilsin. Morf sürerken manevra SUSAR ve eğim
            # sıfırlanır; formation_node morf eder (susturma aşağıda kalkar).
            # Böylece manevra ile morf HİÇ aynı anda basmaz (iki-üretici
            # çakışması önlenir) ve eğikken morf olmaz. Morf bitince manevra
            # kendiliğinden döner (dizilim korunur). Morf süresi/hızı morf
            # kilidiyle ortak (_morf_bitis_s, _handle_formation_change).
            if self._morf_bitis_s > time.monotonic():
                ctx.maneuver_pitch_deg = 0.0
                ctx.maneuver_roll_deg = 0.0
            else:
                self._dispatch_maneuver(dt)
        elif ctx.state == ModeState.HOLD:
            self._dispatch_hold()
        elif ctx.state == ModeState.READY:
            self._dispatch_hold()

        if ctx.formation_change_requested:
            self._handle_formation_change()

        # 🔴 PILOT SwD'YE DOKUNDU AMA YETKI YOK — SESSIZ KALMA.
        # 30 Agustos'un asil dersi kapinin kendisi degil, kapinin sebebini
        # SOYLEMEMESIYDI (kalkis kapisi aylarca kapali kalabilirdi ve
        # kimse fark etmezdi). Pilot SwD'yi kaldirip hicbir sey olmadigini
        # gorurse nedenini burada bulur.
        if (ctx.takeoff_requested
                and ctx.state == ModeState.PREFLIGHT
                and not ctx.kalkis_yetkisi_var()):
            self.get_logger().error(
                '[mode_manager] SwD KALKIS istendi ama YETKI YOK: gorev '
                f"YKI'den baslatilmadi (mission_state={ctx.mission_state}, "
                'beklenen 8). G2-K10 ucuncu kapi. Madde 27+28 gerekiyor.',
                throttle_duration_sec=2.0,
            )

        ctx.takeoff_requested = False
        ctx.land_requested = False
        ctx.rtl_requested = False
        ctx.emergency_stop_requested = False
        ctx.formation_change_requested = False

        # 🔴 INIS KOMUTUNU 1 Hz TEKRARLA — tek atislik iptal kabul edilemez.
        # Ucu birden gercek: (a) kumanda komutu mesh'e 200 ms'lik joystick
        # kapisindan geciyor, tek tick'lik bayrak kapiya takilabilir
        # (b) px4_bridge yeniden baslamis olabilir (c) agent_fsm ARMED'a
        # girerse 'offboard' yollar (agent_fsm_node.py:306) ve AUTO.LAND
        # px4_bridge'in pilot-modu kapisina TAKILMAZ — yani inis IPTAL
        # OLURDU. Tekrar ucunu de kapatir; 'land' px4_bridge'de etkisizdir.
        if ctx.state in self._INIS_DURUMLARI and (
                self._son_inis_komutu is None
                or now - self._son_inis_komutu >= 1.0):
            self._inis_komutu_gonder('tekrar')

        # 🔴 KALKIS KOMUTUNU DA TEKRARLA — AMA YALNIZ KAPI ACILANA KADAR.
        #
        # Neden tekrar: px4_bridge OFFBOARD'i _ARM_OFFBOARD_BEKLEME_S icinde
        # aktiflestiremezse ARM'i GONDERMEZ ve akisi kapatir (px4_bridge.py:
        # 645-655) — tek atislik bir kalkis orada sessizce olurdu. Tekrar,
        # mod kabul edilene kadar yeniden dener. Ikisi de etkisiz-tekrar
        # guvenli (:1313, :1377).
        #
        # Neden `not kalkis_tamam` ile SINIRLI: kapi acildiginda ucaklar
        # armli ve 2 m ustundedir. O noktadan sonra `takeoff` tekrari
        # TEHLIKELI olurdu — px4_bridge yeniden baslamis olsaydi capasi
        # bos olurdu ve hedefi O ANKI (havadaki) z'ye gore kurup ucagi BIR
        # H DAHA tirmandirirdi. Tekrarin degerli oldugu pencere yerdeki
        # pencere; orada biter.
        if (ctx.state == ModeState.TAKEOFF
                and not ctx.kalkis_tamam
                and ctx.kalkis_komutu_verildi
                and (self._son_kalkis_komutu is None
                     or now - self._son_kalkis_komutu >= 1.0)):
            self._kalkis_komutu_gonder('tekrar')

        # formation_node susturması: mode_manager /raw'a KENDİSİ yazarken
        # (MANEVRA her zaman; HOLD yalnız eğik pozdayken) formasyon susar,
        # aksi hâlde formasyon sürücüdür (MOVEMENT tarif üzerinden gider).
        #
        # INIS/ACIL durumlarinda da susar ve bu kalkis kapisina BAGLI
        # DEGIL: mode_manager o durumlarda /raw'a hic yazmaz, ama
        # formation_node yazmaya devam ederdi. px4_bridge o setpoint'i
        # akitmaz (_offboard_streaming=False) — ancak biri offboard'i geri
        # acarsa ucak birden formasyon slotuna FIRLAR. Susturmak bu
        # pencereyi kapatir. formation_node 3 sn tazelenmezse zaten birakir.
        sustur = Bool()
        sustur.data = ctx.state in self._INIS_DURUMLARI or (
            # 🔴 TIRMANIS SIRASINDA FORMASYON SUSAR (madde 25).
            # CLAUDE.md §9 madde 8: "irtifadan once yatay hareket YOK".
            # mode_manager TAKEOFF'ta zaten hicbir sey yayinlamiyor, ama
            # formation_node'un elinde ONCEKI denemeden kalma bir tarif
            # olabilir; px4_bridge taze setpoint'i kalkis hedefinin ONUNE
            # alir (px4_bridge.py:705) ve tirmanis yerine yatay kacis olur.
            # Susturmak bu pencereyi kapatir — inis durumlarindaki (d)
            # kusurunun ayni sinifi.
            ctx.state == ModeState.TAKEOFF
        ) or (
            ctx.kalkis_tamam and (
                # MANEVRA'da formation_node susar — AMA manevra-morf
                # alt-fazında DEĞİL: o an formation_node morf etmeli
                # (manevra susuyor, yukarıdaki dispatch'te dispatch atlanır).
                (ctx.state == ModeState.MANEUVER
                 and self._morf_bitis_s <= time.monotonic())
                or (ctx.state in (ModeState.HOLD, ModeState.READY)
                    and (ctx.maneuver_pitch_deg != 0.0
                         or ctx.maneuver_roll_deg != 0.0))
            )
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
        # 🔴 IVME RAMPASINI SIFIRLA — B6, 31 Agustos 2026.
        # MOVEMENT disina cikarken hiz durumu BAYATLAR. MOVEMENT'tan
        # cikis yalnizca SwA birakilinca oluyor (mode_transitions
        # ._from_movement: `not command_active`), yani "suru DURSUN"
        # anlaminda. Sifirlanmazsa SwA tekrar acildiginda suru ESKI
        # hizindan devam eder ve SICRAR.
        #
        # ⚠️ MOVEMENT'a GIRERKEN sifirlamiyoruz cunku zaten 0'dan
        # baslamis olur; cubuk merkezdeyken rampa da 0'da durur.
        if state != ModeState.MOVEMENT:
            self._ctx.hiz_rampasini_sifirla()
            # Morf kilidi de dusuruluyor: MOVEMENT disinda formasyon
            # tarifi yayinlanmiyor, kilit bir sonraki ucusa TASINMAMALI.
            self._morf_bitis_s = 0.0
        if state == ModeState.TAKEOFF:
            # 🔴 YER BASLIGINI MANDALLA — 5 Eylul 2026, bag'den olculdu.
            # Buraya girildiginde ucak HALA YERDE (kalkis komutu asagida
            # gonderiliyor). Tirmanista yaw 27 dereceye kadar savruluyor ve
            # kalkis kapisi o salinimin ortasinda ornekliyordu; sonuc yerdeki
            # yonun 17,4 derece SOLU idi. Yerdeki olcum +-0,05 derece
            # kararli. Gerekce ve bag izi: mode_context.konumdan_tohumla.
            if self._ctx.yer_basligini_mandalla():
                self.get_logger().info(
                    '[mode_manager] YER BASLIGI mandallandi: '
                    f'{self._ctx.yer_heading_deg:.1f} deg '
                    f'(lider={self._ctx.lider_id}) — '
                    'tirmanis salinimi bu degeri DEGISTIRMEZ'
                )
            else:
                self.get_logger().warning(
                    '[mode_manager] YER BASLIGI mandallanamadi (eksik ajan '
                    'durumu) — baslik kalkis kapisinda olculecek, tirmanis '
                    'salinimi yansiyabilir'
                )
            # 🔴 KUMANDADAN KALKIS — madde 25, G2-K10 secenek (a).
            #
            # SwD tek harekette `arm` + `takeoff:H`. Komut agent_fsm'e
            # DEGIL, px4_bridge'e DOGRUDAN gider — inis yolunun (madde 24)
            # aynisi ve ayni gerekce: agent_fsm'in `pending_state` yolu
            # duruma bagli ve tek tick yasiyor, iptal/kalkis yetkisi buna
            # emanet edilemez. Ayrintili gerekce _kalkis_komutu_gonder'de.
            #
            # 🔴 EVENT_MISSION_STARTED HALA YAYINLANMIYOR — 30 Agustos 2026
            # saha olayindan sonra kaldirildi ve GERI GELMIYOR.
            #
            # NE OLDU: SwD kalkis konumuna alindi -> mesh -> uc mode_manager
            # TAKEOFF'a girdi -> buradan EVENT_MISSION_STARTED yayinlandi ->
            # agent_fsm (kalkis_olayla=false, "gecis modu") olayi ARM'a
            # cevirdi -> px4_bridge OFFBOARD + ARM yapip arm z'sini KILITLEDI
            # -> PERVANESIZ ucak o irtifayi tutamayinca konum denetleyicisinin
            # integrali sardi, gaz tirmandi, PX4 kendini "flying" saydi ve
            # YAZILIM DISARM'INI REDDETTI (MAV_RESULT=1). Kumandadan inis yolu
            # da yok (asagidaki LANDING dali yalniz olay yayinliyor). Olay
            # ancak agent_fsm'in ARMED->IDLE zaman asimiyla (42-95 sn) bitti.
            # DURUM.md §3'un belgeledigi tuzagin birebir tekrari.
            #
            # NEDEN KALDIRILDI: EVENT_MISSION_STARTED guided yolun ARM
            # TETIGI. mode_manager gorev baslaticisi DEGIL, mod yoneticisi;
            # o olayi yayinlamasi "SwD'ye dokunmak suruyu ARM eder" demek.
            #
            # Kalkis yetkisi artik ACIKCA tasarlandi (G2-K10, madde 25):
            # olay yoluyla degil, px4_bridge'e DOGRUDAN komutla ve UC
            # KAPIYLA. Fark, arm'in gizli olmasi degil ORTUK olmasiydi.
            # Zemin z'lerini KOMUT ANINDA dondur — "irtifaya ulasildi"
            # olcutu buna gore (bkz. ctx.kalkis_zeminini_tohumla).
            self._ctx.kalkis_zeminini_tohumla()
            self._kalkis_komutu_gonder('kumandadan kalkis')

        elif state == ModeState.READY:
            # 🔴 KONTROL PILOTA GECIYOR — CENTROID'I TAZELE (madde 25).
            #
            # Kalkis kapisi 2 m'de aciliyor ve centroid'i ORADA tohumluyor.
            # Kumandadan kalkista READY ise 0.8 x hedef irtifada (8 m icin
            # 6,4 m) geliyor. Arada centroid TAZELENMIYOR (_on_swarm_state
            # kapi acildiktan sonra bilerek yazmiyor) — yani READY'nin ilk
            # _dispatch_hold'u center_z olarak hala 2 m'yi yayinlardi ve
            # suru kontrol devralinir alinmaz 2 m'ye GERI DALARDI. Ayni sey
            # x/y icin de gecerli: tirmanista birkac metre suruklenme olur
            # ve bayat centroid yanal bir sicrama komutu olurdu.
            #
            # Ofsetler de olculen geometriden tazelenir — pilot ilk is
            # MANEVRA'ya gecerse gomulu ucgen egilmesin (B7'nin ayni tuzagi;
            # kapi acilisindaki tohumlamanin birebir esi).
            # Centroid tazeleniyor: formasyonsuz ofset dondurmasi da
            # COZULMELI. Ikisi ayni ana ait olmazsa ofsetler bir
            # centroid'e, merkez baska bir ana ait olur ve dizilim kayar.
            self._donmus_ofsetler = None
            if self._ctx.konumdan_tohumla():
                olculen = self._ctx.olculen_ofsetler()
                if len(olculen) == len(self._agent_ids):
                    self._formation_offsets = olculen
                self.get_logger().info(
                    '[mode_manager] READY — centroid ucaklarin O ANKI '
                    f'konumundan tazelendi: ({self._ctx.centroid_x:.1f}, '
                    f'{self._ctx.centroid_y:.1f}, {self._ctx.centroid_z:.1f}) '
                    f'heading={self._ctx.formation_heading_deg:.1f} deg'
                )
            else:
                # Buraya dusmek "bir ajanin durumu hic gelmemis" demek;
                # PREFLIGHT kapisi bunu zaten eliyor. Sessiz kalirsa suru
                # bayat centroid'e uyar — o yuzden ERROR.
                self.get_logger().error(
                    '[mode_manager] READY girisinde centroid TAZELENEMEDI '
                    '(eksik ajan durumu) — bayat centroid kullanilacak.'
                )
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
            # 🔴 FORMASYON OLUŞMAZ — dizilim OLDUĞU GİBİ KALIR (operatör,
            # 3 Eylül): manevra modu yalnız stick anlamını değiştirir,
            # uçakları yeniden dizmez. Centroid+ofseti O ANKİ konumdan
            # tazele — READY'deki aynı tuzak (satır 693-695): MOVEMENT'ta
            # centroid güncellenir ama ofsetler bayat kalır; ikisi farklı
            # ana ait olursa manevraya geçince dizilim SIÇRAR (sahada
            # ölçüldü: "manevraya geçince pozisyon değişiyor"). Tazeleme
            # setpoint'i mevcut pozisyona sabitler → uçak kımıldamaz, sonra
            # stick eğimi z'yi modüle eder.
            self._donmus_ofsetler = None
            if self._ctx.konumdan_tohumla():
                olculen = self._ctx.olculen_ofsetler()
                if len(olculen) == len(self._agent_ids):
                    self._formation_offsets = olculen
                self.get_logger().info(
                    '[mode_manager] Manevra modu aktif — dizilim korundu, '
                    f'centroid+ofset O ANKİ konumdan tazelendi: '
                    f'({self._ctx.centroid_x:.1f}, {self._ctx.centroid_y:.1f}, '
                    f'{self._ctx.centroid_z:.1f})'
                )
            else:
                self.get_logger().error(
                    '[mode_manager] Manevra modu aktif AMA konum tohumlanamadı '
                    '(bir ajanın durumu yok) — bayat centroid/ofsetle '
                    'devam, dizilim kayabilir.'
                )

        elif state == ModeState.HOLD:
            self.get_logger().info(
                '[mode_manager] HOLD modu'
            )

        elif state == ModeState.LANDING:
            # 🔴 OLAY YOLU TEK BASINA YETMIYOR — 30 Agustos 2026 saha olayi.
            #
            # Pilot kumandanin hicbir tusuyla inis veremedi. Sebep OLCULDU:
            # zincir aslinda VAR —
            #     LANDING -> EVENT_EMERGENCY_LAND (target_agent_id=0)
            #     -> agent_fsm._on_event -> ctx.pending_state = LANDING
            # ama agent_transitions.py'de `pending_state == LANDING`
            # YALNIZ UC DURUMDAN kabul ediliyor: IN_SWARM (:207),
            # RETURN_HOME (:316), FAILSAFE (:387). Olay sirasinda ucaklar
            # ARMED'daydi; _from_armed bu istegi HIC GORMEZ ve
            # agent_fsm_node.py:232 tick sonunda pending_state'i KOSULSUZ
            # temizler — istek tek tick yasayip SESSIZCE kaybolur.
            #
            # Iptal yolu duruma bagli OLAMAZ. px4_bridge tek PX4 yazicisi
            # ve oradaki 'land' dali kosulsuzdur. Komut ORAYA gider.
            # Olay yine de yayinlanir ki agent_fsm gorebildigi durumdayken
            # kendi durumunu gercege esitlesin (yoksa hala "ucuyorum"
            # sanip ARMED'a girip 'offboard' yollar).
            self._inis_komutu_gonder('kumandadan inis')
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 iniş komutu',
            )

        elif state == ModeState.RTL:
            # 🔴 RTL UCURULMUYOR — CLAUDE.md §9: "HOME kaymasi cozulmeden
            # RTL'li ucus YOK, inis `land` ile". Gorev 2 tasariminda RTL
            # salteri de yok (G2-K7); sartname §5.2 madde 11 donusunu
            # PILOT ucuruyor. Bu duruma yine de girilirse ucak havada
            # surucusuz kalmasin diye projenin onayli iptali uygulanir.
            #
            # EVENT_RTL_TRIGGERED BILEREK YAYINLANMIYOR: agent_fsm onu
            # RETURN_HOME'a cevirir ve RETURN_HOME 'offboard' komutu
            # yollar (agent_fsm_node.py:316) — bu inisi IPTAL EDERDI.
            self.get_logger().error(
                '[mode_manager] RTL istendi ama RTL UCURULMUYOR '
                '(HOME kaymasi P0, CLAUDE.md §9) — LAND uygulaniyor.'
            )
            self._inis_komutu_gonder('RTL istendi -> land')
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_WARNING,
                'Görev 2 RTL istendi — HOME kayması nedeniyle LAND',
            )

        elif state == ModeState.EMERGENCY:
            # Acil durumda da DISARM DEGIL land — CLAUDE.md §9:
            # "Havadaki ucaga disarm gonderme. Motoru kesmek dusmek
            # demektir. Iptal her zaman land."
            self._inis_komutu_gonder('acil durum')
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
            self.get_logger().info(
                '[mode_manager] COMPLETED — yeni denemeye hazir olmak icin '
                'SwD YUKARI alinacak ve butun ucaklar DISARM olacak (B19). '
                'Konteyner yeniden baslatmak GEREKMIYOR.'
            )

        elif state == ModeState.IDLE and old_state == ModeState.COMPLETED:
            # 🔴 B19 — IKINCI DENEME icin ucus defterini TEMIZLE.
            # Hangi alanin neden temizlendigi: ctx.ucus_durumunu_sifirla.
            self._ctx.ucus_durumunu_sifirla()
            self._morf_bitis_s = 0.0
            self._son_kalkis_komutu = None
            self._son_inis_komutu = None
            self._init_default_offsets()
            self.get_logger().warning(
                '[mode_manager] COMPLETED -> IDLE: ucus defteri sifirlandi '
                '(kalkis kapisi KAPANDI, zemin referansi silindi). Gorev '
                "hala baslatilmissa PREFLIGHT'e gecilir ve SwD beklenir."
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
        # TEKRAR MI? Mesh komutlari degisim bayragini surekli tasiyor —
        # ayni degisim 50 ms'de bir yeniden isleniyordu (1 Eylul olcumu:
        # morf kilidi surekli tazelendi, log boguldu). Gercek degisim
        # degilse (ayni tip + ayni aralik) hicbir sey yapma.
        if self._son_islenen_aralik is not None and \
                not tek_yayinci.degisim_islenir_mi(
                    ctx.requested_formation, ctx.active_formation,
                    spacing, self._son_islenen_aralik):
            ctx.formation_change_requested = False
            return
        self._son_islenen_aralik = spacing
        # 🔴 MORF KILIDI — bu andan itibaren slot hizi MOD_MORF_HIZ.
        # 31 Agustos ucusunda morf tam hizla kosuldu: iki ucak 1,2 saniyede
        # 2,71 m/s'e cikip 4,13 m/s ile kapandi ve 1,65 m'ye yaklastilar.
        # Kacinma dogru calisti ama 4 m'lik esikte 2,38 m'si frenlemeye
        # gitti. Hizi dusurmek o frenlemeyi 0,20 m'ye indiriyor.
        yeni_kilit = self._morf_bitis_s <= 0.0
        self._morf_bitis_s = time.monotonic() + self._morf_sure_s
        if yeni_kilit:
            self.get_logger().warning(
                f'[mode_manager] MORF KILIDI ACIK — slot hizi '
                f'{self._morf_hiz_mps:.2f} m/s (seyir '
                f'{self._ctx.max_speed_mps:.1f} m/s degil), en gec '
                f'{self._morf_sure_s:.0f} sn sonra duser'
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

    def _on_election(self, msg: ElectionResult) -> None:
        yeni = int(msg.new_leader_id)
        # Sabit lider acikken aykiri secim sonucu UYGULANMAZ: consensus da
        # ayni kimligi reddediyor, iki dugum ayrisirsa tarif basan ucak ile
        # mesh kapisini acan ucak farkli olurdu (CLAUDE.md §4).
        if self._sabit_lider > 0 and yeni != self._sabit_lider:
            self.get_logger().warning(
                f'[mode_manager] SABIT LIDER: drone{yeni} secim sonucu '
                f'REDDEDILDI (sabit={self._sabit_lider})',
                throttle_duration_sec=10.0,
            )
            return
        if yeni != self._lider_id:
            self._lider_id = yeni
            # Suru basligi liderin pusulasindan turuyor: ctx de bilmeli,
            # yoksa kalkis kapisi eski/bos kimlikle tohumlar.
            self._ctx.lider_id = yeni
            self._tek_yayinci_uyarildi = False  # lider degisti, bir kez soyle
            self.get_logger().info(
                f'[mode_manager] TEK-YAYINCI: lider artik {yeni} '
                f'(ben={self._agent_id}) — tarif '
                f'{"BENDE" if yeni == self._agent_id else "liderde"}'
            )

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        ctx = self._ctx

        ctx.command_valid = msg.command_valid
        ctx.deadman_pressed = msg.deadman_pressed
        # 🔴 0 = "BELIRTILMEDI" -> KENDI politikami kullan. 1 Eylul 2026,
        # UCUSTA OLCULDU ve suru hareketini TAMAMEN olduren hataydi.
        #
        # OLAY: operator formasyon kurup ileri pitch verdi, YALNIZ pilot
        # ucagi hareket etti. Kayittan (209513-209537): cubuk ±0,73'e
        # kadar giderken ylp00 2,82 m yol aldi, ylp01 0,40 m, ylp02 0,25 m
        # — yani ikisi de YERINDE DURDU.
        #
        # ZINCIR: `deadman_timed_out()` "elapsed > deadman_timeout_s"
        # diyor. esp32_bridge mesh paketinden SwarmControlCommand kurarken
        # bu alani DOLDURMUYOR (mesh'te yok), yani komsulara 0.0 gidiyor.
        # 0 ile kosul her zaman dogru -> `command_active` HEP FALSE ->
        # `mode_transitions._from_ready` MOVEMENT dondurmuyor -> ucak
        # READY'de kalip `compute_hold_command` yayinliyor (merkez sabit,
        # max_speed 0.0). Olculdu: komsulara giden FormationCommand'in
        # merkezi tum ucus boyunca (+6.32,-1.43)'te dondu, hiz=0.00.
        #
        # Formasyon DEGISIMI calisiyordu cunku o `command_active`e bagli
        # degil — bu yuzden ariza "yarim calisiyor" gibi gorunup gozden
        # kacti.
        #
        # NEDEN TASIMA KATMANINDA DEGIL BURADA DUZELTILDI: esp32_bridge'in
        # kendi kurali "tasima katmani politika uretmemeli"
        # (requested_spacing_m'de birebir ayni gerekce). Zaman asimi bir
        # POLITIKA; alici kendi degerini bilir.
        #
        # 0.5 sn OLCUMLE secildi: mesh komut araliginda en kotu bosluk
        # 0,203 sn (200 ornek, std 0,05) — 2,5 kat pay.
        #
        # ⚠️ FAIL-SAFE YONU KORUNDU: deger 0 kalsaydi suru HIC hareket
        # etmezdi (tehlikesiz ama islevsiz). Buradaki yedek de sonlu bir
        # zaman asimi; "sinirsiz" DEGIL. Link koparsa suru yine durur.
        ctx.deadman_timeout_s = (
            msg.deadman_timeout_s if msg.deadman_timeout_s > 0.0
            else self._deadman_zaman_asimi_s
        )

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

        # Emniyet ACIK (deadman_pressed) ama paket GECERSIZ.
        #
        # 🔴 30 Agustos 2026: burada YORUM ile KOD CELISIYORDU. Yorum
        # "aksiyon isteklerini KORU!" diyordu, kod ise `return` edip
        # land/rtl/acil dahil HEPSINI dusuruyordu.
        #
        # Celiski B18 gaz kapisiyla TEHLIKEYE dondu: o kapi command_valid'i
        # false yapan YENI bir sebep. Yani "SwA acik, gaz ortada degil"
        # halinde pilot LAND VEREMEZDI — oysa CLAUDE.md "iptal her zaman
        # land" diyor ve land tek gercek iptal yolumuz.
        #
        # ILKELI AYRIM: IPTAL aksiyonlari (land/rtl/acil) HER ZAMAN gecer,
        # GIT aksiyonu (takeoff) GECMEZ. Gecersiz bir pakette "kalk" demek
        # yanlis, "in" demek her zaman dogru.
        if not msg.command_valid:
            ctx.pitch_cmd = 0.0
            ctx.roll_cmd = 0.0
            ctx.yaw_cmd = 0.0
            ctx.throttle_cmd = 0.0
            if msg.land:
                ctx.land_requested = True
            if msg.rtl:
                ctx.rtl_requested = True
            if msg.emergency_stop:
                ctx.emergency_stop_requested = True
            # takeoff BILEREK YOK — gecersiz pakette kalkis istenmez.
            ctx.last_valid_command_time = time.monotonic()
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

    def _on_g2_ayar(self, msg: Float32MultiArray) -> None:
        """Gorev 2 baslatma ayarini uygular (aralik / irtifa).

        🔴 HAVADAYKEN UYGULANMAZ. Sartname ayari GOREV ONCESI veriyor ve
        operator de YKI'de BASLAT'a basmadan once giriyor. Havada
        uygulamak iki ayri tehlike acardi:
          * IRTIFA: kalkis irtifasi zaten kullanilmis olur, degistirmek
            anlamsiz; ama TAKEOFF'a geri donulurse yanlis hedefe tirmanir.
          * ARALIK: sürü havadayken aralik degisirse formasyon ISTENMEDEN
            morf eder — 31 Agustos'ta bunun ne demek oldugunu gorduk.
        Kapi `kalkis_tamam` mandaliyla: bir kez havalanildiysa kapali.

        0.0 = "operator bos birakti" -> o alan icin varsayilan KORUNUR.
        Sinirlar ve gerekceleri: canli_param.g2_ayar_dogrula.
        """
        v = list(msg.data)

        def _al(i):
            return v[i] if len(v) > i else 0.0

        # Kisa dizi GERIYE UYUMLU: eski YKI yalniz [aralik, irtifa]
        # yolluyordu, verilmeyen alan 0 = belirtilmedi sayilir.
        try:
            aralik, irtifa = canli_param.g2_ayar_dogrula(_al(0), _al(1))
            morf, hareket, yaw, egim = canli_param.g2_suru_ayari_dogrula(
                _al(2), _al(3), _al(4), _al(5))
        except canli_param.ParamRed as e:
            self.get_logger().error(f'[mode_manager] GOREV 2 AYARI RED: {e}')
            return

        if self._ctx.kalkis_tamam:
            self.get_logger().warning(
                '[mode_manager] GOREV 2 AYARI YOK SAYILDI — suru HAVADA. '
                f'(aralik={aralik:g} irtifa={irtifa:g}) Ayar yalniz kalkis '
                'oncesi uygulanir; inip tekrar baslatmak gerekir.'
            )
            return

        # 🔴 ALANLARA DOGRUDAN YAZMIYORUZ — ROS PARAMETRESINDEN GECIYORUZ.
        # 31 Agustos 2026, UCAKTA OLCULDU: dogrudan yazan ilk surumde
        # dugum 9.0 m kullanirken `ros2 param get default_spacing_m`
        # hala 7.0 diyordu. Sahada bu sekilde bir saat yakilir: operator
        # parametreye bakip "ayar gitmemis" der, oysa gitmistir.
        # Ikinci ve daha sinsi kazanc: parametre geri cagrisi
        # `_init_default_offsets()` cagiriyor — dogrudan yazan surumde
        # `_formation_offsets` ESKI aralikta kaliyordu, yani FORMATION_
        # UNKNOWN dalinda suru yeni araligi HIC gormeyecekti.
        istekler, uygulanan = [], []
        if aralik != canli_param.BELIRTILMEDI:
            istekler.append(
                Parameter('default_spacing_m', Parameter.Type.DOUBLE, aralik))
            uygulanan.append(f'aralik={aralik:.1f} m')
        if irtifa != canli_param.BELIRTILMEDI:
            istekler.append(
                Parameter('kalkis_irtifa_m', Parameter.Type.DOUBLE, irtifa))
            uygulanan.append(f'irtifa={irtifa:.1f} m')
        # 5 Eylul 2026 — dort suru davranis ayari, ayni yoldan.
        # Ayni gerekce: DOGRUDAN ALANA YAZMIYORUZ, ROS parametresinden
        # geciyoruz ki `ros2 param get` ile gorulen deger ile dugumun
        # kullandigi deger AYRISMASIN (31 Agustos dersi, yukarida).
        for ad, deger, birim in (
                ('morf_hiz_mps', morf, 'm/s'),
                ('max_speed_mps', hareket, 'm/s'),
                ('max_yaw_rate_deg_s', yaw, 'deg/s'),
                ('max_tilt_deg', egim, 'deg')):
            if deger != canli_param.BELIRTILMEDI:
                istekler.append(
                    Parameter(ad, Parameter.Type.DOUBLE, float(deger)))
                uygulanan.append(f'{ad}={deger:g} {birim}')
        if istekler:
            sonuclar = self.set_parameters(istekler)
            red = [f'{i.name}: {s.reason}'
                   for i, s in zip(istekler, sonuclar) if not s.successful]
            if red:
                self.get_logger().error(
                    '[mode_manager] GOREV 2 AYARI PARAMETREDE REDDEDILDI: '
                    + ' · '.join(red))
                return
            # ctx.requested_spacing_m'i parametre geri cagrisi YAZMIYOR
            # (orasi `_default_spacing_m` + ofsetlerle ilgileniyor), o
            # yuzden burada ayrica yaziliyor: formasyon komutunu suren
            # alan bu.
            if aralik != canli_param.BELIRTILMEDI:
                self._ctx.requested_spacing_m = aralik
        if uygulanan:
            self.get_logger().warning(
                '[mode_manager] GOREV 2 AYARI UYGULANDI: '
                + ' · '.join(uygulanan)
            )
        else:
            self.get_logger().info(
                '[mode_manager] Gorev 2 ayari bos geldi — varsayilanlar '
                f'korunuyor (aralik={self._default_spacing_m:.1f} m, '
                f'irtifa={self._kalkis_irtifa_m:.1f} m)'
            )

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

    def _morf_hizini_uygula(self, istenen: float) -> float:
        """Morf suruyorsa slot hizini MOD_MORF_HIZ ile sinirlar.

        🔴 KAPI DISPATCH'E DEGIL YAYIN SINIRINA KONULDU — B15 kalkis
        kapisiyla ayni gerekce: ileride eklenen her yeni formasyon yolu
        kendiliginden yavaslamis olur, birinin hatirlamasi gerekmez.

        Karar mantigi ve NEDEN oyle: `morf_kilidi.hiz_sinirla`. Burada
        yalnizca durum tutuluyor ve log yaziliyor — sayilar orada,
        testleri de orada.
        """
        ctx = self._ctx
        cubuk = max(abs(ctx.pitch_cmd), abs(ctx.roll_cmd),
                    abs(ctx.throttle_cmd))
        hiz, self._morf_bitis_s, sebep = morf_kilidi.hiz_sinirla(
            istenen, self._morf_hiz_mps, self._morf_bitis_s,
            time.monotonic(), cubuk, self._MORF_CUBUK_ESIGI,
        )
        if sebep == morf_kilidi.SEBEP_CUBUK:
            self.get_logger().warning(
                f'[mode_manager] MORF KILIDI DUSTU — cubukla hareket '
                f'istendi ({cubuk:.2f}). Slot hizi seyir hizina dondu; '
                f'aksi halde formasyon merkezin gerisinde kalirdi.'
            )
        elif sebep == morf_kilidi.SEBEP_SURE:
            self.get_logger().info(
                '[mode_manager] morf kilidi suresi doldu — slot hizi '
                'seyir hizina dondu'
            )
        return hiz

    def _publish_formation_command(self, params: dict) -> None:
        # 🔴 B15 KALKIS KAPISI — kapi kapaliyken TEK BIR tarif bile disari
        # cikmaz. Kapi dispatch'e degil YAYIN SINIRINA konuldu: boylece
        # ileride eklenen her yeni yol da kendiliginden kapali kalir.
        # Kapali kalma sebebi ve tehlike: mode_context.kalkis_kapisi_degerlendir
        if not self._ctx.kalkis_tamam:
            return

        # 🔴 TEK-YAYINCI (3 Eylul kume-toplanma olayi): tarifi yalniz lider
        # basar; takipcilerin formation_node'u liderinkini MESH'ten alir.
        # Uc yayin noktasi da (movement/hold/degisim) bu tek siniri kullanir.
        if not tek_yayinci.tarif_yayinlanir_mi(
                self._agent_id, self._lider_id, self._agent_ids):
            if not self._tek_yayinci_uyarildi:
                self._tek_yayinci_uyarildi = True
                self.get_logger().info(
                    f'[mode_manager] TEK-YAYINCI: bu ucak tarif BASMAZ '
                    f'(ben={self._agent_id}, lider={self._lider_id}) — '
                    f'formation_node tarifi mesh\'ten alir'
                )
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
        msg.max_speed_mps = self._morf_hizini_uygula(
            float(params.get('max_speed_mps', 0.0)))
        msg.source_module = 'mode_manager'

        num_agents = len(self._agent_ids)
        # 🔴 LIDER HER ZAMAN SLOT 0 — 4 Eylul 2026, operator karari (Gorev 2).
        #
        # Slot atamasi kimlik sirasina bagli: compute_slot_offsets() slot 0'i
        # ilk uretir ve o slot UC formasyonun da tepe/merkez noktasidir
        # (cizgi -> hattin ortasi, okbasi -> uc, V -> arka koseg). Yani
        # "lider ortada" demek "lider agent_ids[0]" demek.
        #
        # Buraya kadar geldiysek BU UCAK LIDERDIR: hemen yukaridaki
        # tek_yayinci kapisi lider olmayani return ettiriyor. O yuzden
        # liderin kimligini ayrica cozmeye gerek yok — kendimizi basa
        # aliyoruz. Kalani sirali; boylece tarif deterministik ve
        # ucaklar arasi bit-birebir ayni.
        #
        # Mesh'te de korunur: TIP_FORMASYON payload'i `slot_ajan[i] = i.
        # slottaki ajan` seklinde SIRAYI tasiyor (packet_parser:1085) ve
        # alici ofsetleri ayni sirada yeniden uretiyor. Protokol degismedi.
        # 🔴 EN YAKIN SLOT — 5 Eylul 2026. Lider slot 0'a SABIT, kalanlar
        # en yakin slota. Onceden sira KIMLIKTEN geliyordu ve ucaklarin
        # yere hangi sirayla dizildigine bagliydi; tutmadigi anda ucaklar
        # birbirinin USTUNDEN geciyordu (olcum: ylp01 11,72 m yol, ylp00'in
        # uzerinden, kacinmanin kapali oldugu 2-3 m'de). Gerekce ve saha
        # sayilari: slot_atama.py basligi.
        #
        # Slot dunya konumlari ancak ofsetler hesaplandiktan sonra bilinir,
        # bu yuzden ilk once KIMLIK sirasiyla ofsetleri uretiyoruz; asagida
        # (ofset blogunun sonunda) sira en-yakina gore yeniden kuruluyor.
        msg.agent_ids = tek_yayinci.lider_onde(
            self._agent_id, self._agent_ids)

        if ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI) and num_agents > 0:
            # Gercek bir formasyona geciliyor: formasyonsuz dondurmasi
            # ARTIK GECERSIZ. Cozulmezse formasyondan cikip tekrar
            # formasyonsuza donuldugunde ESKI dizilim geri gelirdi.
            self._donmus_ofsetler = None
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
                # EN YAKIN SLOT: ofsetler (govde cercevesi) hazir, artik
                # slotlarin DUNYA konumu hesaplanabilir ve ajanlar en yakin
                # slota atanabilir. Lider slot 0'da sabit kalir.
                konumlar = {
                    a: (float(st.pos_x), float(st.pos_y))
                    for a, st in self._ctx.agent_statuses.items()
                }
                slot_xy = slot_atama.slot_dunya_konumlari(
                    offsets, msg.center_x, msg.center_y, msg.heading_deg)
                yeni_sira = slot_atama.slot_sirasi(
                    self._agent_id, msg.agent_ids, konumlar, slot_xy)
                if list(yeni_sira) != list(msg.agent_ids):
                    self.get_logger().info(
                        f'[mode_manager] EN YAKIN SLOT: atama '
                        f'{list(msg.agent_ids)} -> {list(yeni_sira)} '
                        '(lider slot 0 sabit)'
                    )
                    msg.agent_ids = list(yeni_sira)

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
            # 🔴 FORMASYONSUZ = "OLDUGUN YERDE KAL". IKI KUSUR VARDI ve
            # 31 Agustos 2026'da UC UCAKLI KALKISTA ISIRDI: ucaklar
            # 8,38 m'den 0,36 m'ye kapandi, operator elle indirdi.
            #
            # (1) Ofsetler HER YAYINDA yeniden olculuyordu (~19 Hz).
            # (2) Olcum DUNYA cercevesinde yapiliyor, tuketim FORMASYON
            #     cercevesinde: formation_node._publish_setpoint gomulu
            #     ofseti heading ile DONDURUYOR (rotate_offset cagrisi).
            #
            # Ikisi birlesince kapali bir dongu olusuyor:
            #     olc(dunya) -> hedef = merkez + Rot(+212 deg) * ofset
            #     -> ucak donen hedefin pesinden yetisemiyor, geriden geliyor
            #     -> yeniden olc -> ofset TEKRAR donduruluyor
            #     -> yaricap her turda kuculuyor
            # Yani ICE DOGRU SARMAL. Rosbag'den olculen slot mesafeleri:
            #     t=1,05 sn   8,38 / 6,92 / 7,44 m   <- dogru, gercek ayrim
            #     t=3,69 sn   2,24 / 2,45 / 1,31 m
            #     t=3,79 sn   1,75 / 2,20 / 0,94 m
            # Kacinma 3 m altinda kapali (altitude_gate_m) oldugu icin
            # hicbir sey durdurmadi.
            #
            # DUZELTME IKI PARCALI:
            #   a) TERS DONDURME — Rot(-heading) ile gomuyoruz; boylece
            #      formation_node'un Rot(+heading)'i ofseti dunya
            #      cercevesine GERI getirir, hedef = ucagin kendi konumu,
            #      kimse kimildamaz. Tek basina dongyu kirar.
            #   b) DONDURMA — yine de BIR KEZ olcup sabitliyoruz. Surekli
            #      yeniden olcum "formasyon"u anlamsizlastirir: suruklenme
            #      birikir ve dizilim sessizce bozulur.
            # Dondurma READY girisinde cozulur (orada centroid de tazeleniyor;
            # ikisi AYNI ana bagli olmak zorunda, yoksa ofsetler bir
            # centroid'e, merkez baska bir ana ait olur).
            #
            # ⚠️ rotate_offset formation_node ile AYNI fonksiyon, bilerek:
            # iki ayri kopya isaret ya da eksen sirasinda sessizce kayabilir.
            ctx = self._ctx
            if self._donmus_ofsetler is not None and len(
                    self._donmus_ofsetler[0]) == num_agents:
                ox, oy, oz = (list(v) for v in self._donmus_ofsetler)
                has_telemetry = True
            else:
                ox, oy, oz = [], [], []
                has_telemetry = False
                ters_h = -math.radians(ctx.formation_heading_deg)
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
                        dunya_x = float(status.pos_x - ctx.centroid_x)
                        dunya_y = float(status.pos_y - ctx.centroid_y)
                        fx, fy = rotate_offset(dunya_x, dunya_y, ters_h)
                        ox.append(fx)
                        oy.append(fy)
                        oz.append(0.0)
                if has_telemetry and len(ox) == num_agents:
                    self._donmus_ofsetler = (list(ox), list(oy), list(oz))
                    self.get_logger().info(
                        '[mode_manager] formasyonsuz ofsetler OLCULDU ve '
                        f'DONDURULDU (heading {ctx.formation_heading_deg:.1f} '
                        'deg ile ters dondurulup gomuldu): '
                        + ' '.join(f'a{a}=({x:+.2f},{y:+.2f})'
                                   for a, x, y in zip(msg.agent_ids, ox, oy))
                    )

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

    _INIS_DURUMLARI = (
        ModeState.LANDING,
        ModeState.RTL,
        ModeState.EMERGENCY,
    )

    def _kalkis_komutu_gonder(self, sebep: str) -> None:
        """px4_bridge'e `arm` + `takeoff:H` yayinlar (G2-K10 secenek a).

        🔴 UCUNCU KAPI BURADA. Gecis kapisi (_from_preflight) durum
        degistirmeyi engelliyor; ASIL kilit bu — komutun uretildigi tek yer.
        B15'in dersi birebir aynidir: kapi dispatch'e degil YAYIN SINIRINA
        konur, boylece ileride eklenen her yeni yol da kendiliginden kapali
        kalir. Bir gun biri "TAKEOFF'a su yoldan da girilsin" derse arm
        yetkisi yine bu satirdan gecmek zorunda.

        SIRA ONEMLI — once `arm`, sonra `takeoff:H`:
          * `arm` dali OFFBOARD'i isteyip aktiflesince ARM gonderiyor ve
            YATAY KILIDIN referansini (`_arm_z`) kuruyor
            (px4_bridge.py:1320-1329). Kilit ARM'dan baslar, takeoff'tan
            degil — 2 Agustos'ta arm ile takeoff arasindaki 6,2 saniyede
            ucak yerde konum tutmaya calisip yan yatmisti.
          * `takeoff:H` yatay capayi donduruyor ve hedefi HER UCAGIN KENDI
            zeminine goreli kuruyor (px4_bridge.py:1384-1389). Sartname
            senaryo madde 5 "baslangic formasyonunu koruyarak yukselir"
            diyor; capa sayesinde tirmanis DIKEY — ucaklar hesaplanan
            slotlara kosmuyor, hakemlerin dizdigi yerden kalkiyor.

        Ikisi de TEKRARA DAYANIKLI: px4_bridge armliyken `arm`'i yok sayar
        (:1313), capa kuruluyken `takeoff`i yok sayar (:1377).
        """
        if not self._ctx.kalkis_yetkisi_var():
            self.get_logger().error(
                "[mode_manager] KALKIS KOMUTU URETILMEDI — gorev YKI'den "
                'BASLATILMADI (mission_state='
                f'{self._ctx.mission_state}, beklenen 8=SEMI_AUTONOMOUS). '
                'G2-K10: SwD tek basina suruyu ARMLAYAMAZ. Sirasiyla madde '
                '27 (mission_fsm) ve 28 (YKI BASLAT butonu) gerekiyor; yer '
                'testinde /swarm/internal/mission/state konusuna 8 basilir.',
                throttle_duration_sec=2.0,
            )
            return
        if self._agent_id == 0:
            self.get_logger().error(
                '[mode_manager] KALKIS KOMUTU GONDERILEMEDI — agent_id=0. '
                'baslat.sh -p agent_id:=${AGENT_ID} gecirmek ZORUNDA.',
                throttle_duration_sec=2.0,
            )
            return

        for komut in ('arm', f'takeoff:{self._ctx.kalkis_irtifa_m:.1f}'):
            m = String()
            m.data = komut
            self._komut_pub.publish(m)
        self._son_kalkis_komutu = time.monotonic()
        # Kalkisi BIZ suruyoruz: TAKEOFF'un bitis olcutu artik hedef irtifa
        # (mode_transitions._from_takeoff), 2 m'lik yayin kapisi DEGIL.
        self._ctx.kalkis_komutu_verildi = True
        self.get_logger().warning(
            f'[mode_manager] px4_bridge -> arm + takeoff:'
            f'{self._ctx.kalkis_irtifa_m:.1f} ({sebep})',
            throttle_duration_sec=2.0,
        )

    def _inis_komutu_gonder(self, sebep: str) -> None:
        """px4_bridge'e dogrudan 'land' yayinlar.

        Iptal yolu AJANIN DURUMUNDAN BAGIMSIZ olmak zorunda; gerekcesi
        _on_state_entry'deki LANDING yorumunda (30 Agustos saha olayi).
        """
        if self._agent_id == 0:
            # Konu /swarm/agent/drone0/commands olurdu, dinleyen yok:
            # inis SESSIZCE kaybolur. Bu, kapatmaya calistigimiz kusurun
            # ta kendisi — o yuzden WARNING degil ERROR.
            self.get_logger().error(
                '[mode_manager] INIS KOMUTU GONDERILEMEDI — agent_id=0. '
                'baslat.sh -p agent_id:=${AGENT_ID} gecirmek ZORUNDA.',
                throttle_duration_sec=2.0,
            )
            return
        m = String()
        m.data = 'land'
        self._komut_pub.publish(m)
        self._son_inis_komutu = time.monotonic()
        self.get_logger().warning(
            f'[mode_manager] px4_bridge -> land ({sebep})',
            throttle_duration_sec=2.0,
        )

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
