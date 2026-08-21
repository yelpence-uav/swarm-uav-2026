# Copyright 2026 Yelpence
"""Hiz tabanli carpisma onleme filtresi."""

import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SystemEvent,
)

from .ca_core import CaParams, CollisionAvoidanceCore, NeighborObs
# KARAR-01 Secenek C: komsu verisi NeighborInfo/kinematic_fusion yerine ham
# AgentStatus'tan geliyor. NeighborInfo importu BILEREK kaldirildi — dursaydi
# "hangi kaynak kullaniliyor" sorusu koda bakinca belirsiz kalirdi.
from .komsu_adaptoru import agent_status_to_obs

_AVOIDANCE_DISI_STATELER = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_LANDED,
    AgentStatus.STATE_FAILSAFE,
})

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


class CollisionAvoidanceNode(Node):
    """Hiz tabanli carpisma onleme filtre node'u."""

    def __init__(self) -> None:
        super().__init__('collision_avoidance')

        self._declare_params()

        self._raw = None
        self._raw_stamp = 0.0

        self._cur_z = 0.0
        self._cur_vx = 0.0
        self._cur_vy = 0.0
        self._cur_vz = 0.0
        self._pos_ok = False
        # Kendi TAM durumum. Adaptor goreli vektoru hesaplarken kendi
        # lat/lon ve pos_x/pos_y'ime ihtiyac duyuyor; NeighborInfo yolunda
        # bu is kinematic_fusion'da yapildigi icin burada saklanmiyordu.
        self._ben: AgentStatus | None = None

        self._neighbors: dict[int, AgentStatus] = {}
        self._neighbor_rx: dict[int, float] = {}
        self._neighbor_subs = {}

        self._sequence_num = 0

        self._n_passthrough = 0
        self._n_avoid = 0
        self._n_skip_state = 0
        self._n_skip_stale = 0
        # Adaptorun atlama nedenleri (gecersiz/cerceve/sayisal). Kacinma
        # tetiklenmediginde "veri mi yoktu, cerceve mi tutmadi" sorusu
        # tahminle degil sayacla cevaplansin.
        self._n_skip_adaptor: dict[str, int] = {}
        self._n_gate_alt = 0
        self._last_active_log = 0.0
        # KORLUK IZLEME — P0.15. Bir komsuyu BIR KEZ gordugumuz an
        # `_komsu_gorulmus`e girer; ondan sonra kaybolmasi bir OLAYDIR.
        # Hic gorulmemis komsu (or. yerdeki ylp01) korluk sayilmaz.
        self._komsu_gorulmus: set[int] = set()
        self._korluk_bildirildi: set[int] = set()
        self._n_korluk = 0
        self._n_korluk_tut = 0
        self._korluk_tut_aktif = False

        self._ca = CollisionAvoidanceCore(CaParams(
            dt=1.0 / self._publish_rate_hz,
            d0=self._d0_m,
            hard=self._hard_m,
            r_min=self._r_min_m,
            f_sat=self._f_sat,
            c_dead=self._c_dead_mps,
            c_ref=self._c_ref_mps,
            c_damp=self._c_damp,
            damp_band=self._damp_band_m,
            k_tan=self._k_tan,
            v_max=self._v_max_mps,
            slew_normal=self._slew_normal,
            slew_emergency=self._slew_emergency,
        ))

        self._setup_io()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz, self._tick,
        )
        self.create_timer(5.0, self._diag_tick)

        self.get_logger().info(
            f'collision_avoidance baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('neighbor_ids', [0])
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('raw_timeout_s', 0.5)
        # NOT: 'neighbor_stale_ms' KALDIRILDI (KARAR-01 Secenek C). Gonderenin
        # kendi beyan ettigi yasa (NeighborInfo.data_age_ms) bakiyordu; ham
        # AgentStatus'ta oyle bir alan yok. Tazelik olcusu artik tek:
        # mesajin bize ULASTIGI an -> neighbor_rx_stale_s. Kullanilmayan bir
        # parametreyi tanimli birakmak "ayarladim ama bir sey olmadi" tuzagi.
        self.declare_parameter('neighbor_rx_stale_s', 0.5)
        self.declare_parameter('altitude_gate_m', 3.0)
        # KORLUK — P0.15, 21 Agustos 2026, UCUSTA OLCULDU.
        #
        # Mesh linki TEK YONLU olebiliyor: ylp02'nin ylp00'a giden yonu
        # 46.4 sn oldu, ters yon ayni anda kusursuz calisti (TUZAKLAR 2.15).
        # O sure boyunca operator ucaklari 3 METREYE kadar yaklastirdi ve
        # kacinma HIC tetiklenmedi — cunku ylp00 icin ortada komsu yoktu.
        #
        # Eski davranista bu SESSIZDI: kaybolan komsu yalniz `skip_stale`
        # sayacinda artiyor, 5 sn'de bir basilan tani satirinin icinde
        # kayboluyordu. 47 saniyelik korluk hicbir alarm uretmedi.
        #
        # korluk_alarm_s: bir komsuyu BIR KEZ gordukten sonra bu kadar sure
        #   goremezsek olay yayinlanir. 2.0 sn = neighbor_rx_stale_s'in
        #   (1.5) biraz ustu; normal mesh bosluklarinda (olculdu: p90 0.20 sn,
        #   maks 0.4 sn saglikli linkte) yanlis alarm uretmez.
        self.declare_parameter('korluk_alarm_s', 2.0)
        # korluk_tut_s: korluk bu kadar surerse YATAY HAREKET DURDURULUR.
        #   0 = kapali (yalniz alarm).
        #
        # Gerekcesi: komsuyu kaybetmek "engel yok" DEGIL, "nerede oldugunu
        # BILMIYORUM" demektir. Son gorulen yerden sonra komsu v_max ile
        # her yone gidebilir; 4 m/s'te 5 saniyede 20 m'lik bir belirsizlik
        # kuresi olusur ve o kureden kacmanin anlamli bir yonu yoktur.
        # Tek muhafazakar davranis: DUR ve bekle.
        #
        # 🔴 VARSAYILAN 0.0 = KAPALI — OPERATOR KARARI (21 Agustos 2026).
        #
        # Gerekce operatorun: korlukte ucagin kendi kendine durmasi yerine
        # OPERATORE haber verilsin, karari o versin. Ucus sirasinda gozu ve
        # kumandasi zaten ustunde; yazilimin sessizce yatay hareketi kesmesi
        # beklenmedik bir davranis olur ve pilotu sasirtir.
        #
        # Mekanizma DURUYOR ve test edilmis halde: gerekirse tek parametreyle
        # acilir (or. otonom finalde operator mudahalesi olmayacaksa):
        #     ros2 param set /collision_avoidance korluk_tut_s 5.0
        # ya da baslat.sh'e -p korluk_tut_s:=5.0
        #
        # 5.0 onerilen deger: saglikli linkte maks bosluk 0.4 sn olculdu,
        # yani normal isleyisin 12 kati. Gecici sarsinti ucagi durdurmaz.
        self.declare_parameter('korluk_tut_s', 0.0)
        self.declare_parameter('d0_m', 4.5)
        self.declare_parameter('hard_m', 2.0)
        self.declare_parameter('r_min_m', 1.5)
        self.declare_parameter('f_sat', 6.0)
        self.declare_parameter('c_dead_mps', 0.2)
        self.declare_parameter('c_ref_mps', 1.0)
        self.declare_parameter('c_damp', 0.7)
        self.declare_parameter('damp_band_m', 0.5)
        self.declare_parameter('k_tan', 0.9)
        self.declare_parameter('v_max_mps', 4.0)
        self.declare_parameter('slew_normal_mps2', 4.0)
        self.declare_parameter('slew_emergency_mps2', 30.0)

        gp = self.get_parameter
        self._agent_id = int(gp('agent_id').value)
        self._static_neighbor_ids = [
            int(x) for x in gp('neighbor_ids').value if int(x) > 0
        ]
        self._publish_rate_hz = float(gp('publish_rate_hz').value)
        self._raw_timeout_s = float(gp('raw_timeout_s').value)
        self._neighbor_rx_stale_s = float(gp('neighbor_rx_stale_s').value)
        self._altitude_gate_m = float(gp('altitude_gate_m').value)
        self._korluk_alarm_s = float(gp('korluk_alarm_s').value)
        self._korluk_tut_s = float(gp('korluk_tut_s').value)
        self._d0_m = float(gp('d0_m').value)
        self._hard_m = float(gp('hard_m').value)
        self._r_min_m = float(gp('r_min_m').value)
        self._f_sat = float(gp('f_sat').value)
        self._c_dead_mps = float(gp('c_dead_mps').value)
        self._c_ref_mps = float(gp('c_ref_mps').value)
        self._c_damp = float(gp('c_damp').value)
        self._damp_band_m = float(gp('damp_band_m').value)
        self._k_tan = float(gp('k_tan').value)
        self._v_max_mps = float(gp('v_max_mps').value)
        self._slew_normal = float(gp('slew_normal_mps2').value)
        self._slew_emergency = float(gp('slew_emergency_mps2').value)

        if not 1 <= self._agent_id <= 254:
            raise ValueError(f'agent_id 1-254 olmalı: {self._agent_id}')
        if self._publish_rate_hz <= 0.0:
            raise ValueError('publish_rate_hz pozitif olmalı')
        if not (self._r_min_m < self._hard_m < self._d0_m):
            raise ValueError('r_min < hard < d0 olmalı')

    def _setup_io(self) -> None:
        """Yayıncıları ve aboneleri oluşturur."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            self._on_raw_setpoint,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            # BEST_EFFORT SART — bu konunun mesh kaynagi esp32_bridge ve o
            # _MESH_QOS ile, yani BEST_EFFORT yayinliyor. RELIABLE abone +
            # BEST_EFFORT yayinci ESLESMEZ; konu SESSIZCE bos kalir ve dugum
            # mesh'ten gelen formasyon komutlarini HIC almaz.
            _BEST_EFFORT_QOS,
        )
        # KORLUK OLAYI — P0.15. Log YETMEZ: 21 Agustos'ta 47 saniyelik
        # korluk log'a yazildi ama ucus sirasinda kimse gormedi. YKI'nin
        # gorebilmesi icin olay sart.
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )
        self._ensure_neighbor_subs(self._static_neighbor_ids)

    def _ensure_neighbor_subs(self, agent_ids) -> None:
        """Komşu telemetri aboneliklerini garanti eder."""
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id or nid <= 0 or nid in self._neighbor_subs:
                continue
            # KARAR-01 Secenek C: kaynak /swarm/agent/.../neighbor/... yerine
            # mesh'ten gelen HAM durum. Bu topic'i esp32_bridge besliyor ve
            # _MESH_QOS ile, yani BEST_EFFORT yayinliyor — abone de BEST_EFFORT
            # olmak ZORUNDA. RELIABLE abone + BEST_EFFORT yayinci ESLESMEZ ve
            # konu SESSIZCE bos kalir; bu depoda ayni tuzaga birkac kez dusuldu.
            topic = f'/swarm/public/drone{nid}/status'
            self._neighbor_subs[nid] = self.create_subscription(
                AgentStatus,
                topic,
                lambda m, n=nid: self._on_neighbor(n, m),
                _BEST_EFFORT_QOS,
            )
            # Eski satir 'NeighborInfo aboneligi: droneN' yaziyordu — kaynak
            # degistigi icin YANILTICI oldu, gercek topic basiliyor.
            self.get_logger().info(f'komsu abonesi: {topic}')

    def _on_raw_setpoint(self, msg: AgentSetpoint) -> None:
        self._raw = msg
        self._raw_stamp = self.get_clock().now().nanoseconds * 1e-9

    def _on_agent_status(self, msg: AgentStatus) -> None:
        self._cur_z = float(msg.pos_z)
        self._cur_vx = float(msg.vel_x)
        self._cur_vy = float(msg.vel_y)
        self._cur_vz = float(msg.vel_z)
        self._pos_ok = bool(msg.xy_valid and msg.z_valid)
        self._ben = msg

    def _on_formation_command(self, msg: FormationCommand) -> None:
        self._ensure_neighbor_subs(msg.agent_ids)

    def _on_neighbor(self, nid: int, msg: AgentStatus) -> None:
        self._neighbors[nid] = msg
        self._neighbor_rx[nid] = self.get_clock().now().nanoseconds * 1e-9

    def _gather_obstacles(self, now: float) -> list[NeighborObs]:
        """Geçerli komşulardan gözlem listesi toplar.

        KARAR-01 Secenek C: girdi ham `AgentStatus`. `NeighborInfo`nun
        `link_active` ve `data_age_ms` alanlari burada YOK — tazelik olcusu
        tek: mesajin bize ULASTIGI an (`_neighbor_rx`). Bu daha durustur,
        cunku gonderenin kendi yas beyanina degil kendi olcumumuze dayanir.
        """
        obs: list[NeighborObs] = []
        if self._ben is None:
            # Kendi durumum gelmeden goreli hesap yapilamaz. Bu bir hata
            # degil, acilis anindaki normal durum.
            return obs

        for nid, st in self._neighbors.items():
            rx = self._neighbor_rx.get(nid, 0.0)
            if now - rx > self._neighbor_rx_stale_s:
                self._n_skip_stale += 1
                # Korluk KAYDI burada DEGIL — `_korluk_tara` yapiyor ve o
                # setpoint akisindan bagimsiz kosuyor. Bkz. oradaki not.
                continue
            if st.state in _AVOIDANCE_DISI_STATELER:
                self._n_skip_state += 1
                continue

            gozlem, neden = agent_status_to_obs(st, self._ben)
            if gozlem is None:
                self._n_skip_adaptor[neden] = (
                    self._n_skip_adaptor.get(neden, 0) + 1
                )
                continue
            obs.append(gozlem)
        return obs

    def _korluk_tara(self, now: float) -> None:
        """Komsu tazeligini tarar, korlugu baslatir/bitirir — P0.15.

        `_tick`ten HER TIK'TA cagrilir; setpoint akisina bagli DEGIL
        (gerekce `_tick` icinde yazili).
        """
        for nid in list(self._neighbors.keys()):
            yas = now - self._neighbor_rx.get(nid, 0.0)
            if yas > self._neighbor_rx_stale_s:
                # Daha once GORDUGUMUZ bir komsuyu kaybettiysek bu bir
                # guvenlik olayidir; hic gorulmemis komsu (or. yerdeki
                # ylp01) korluk sayilmaz.
                if nid in self._komsu_gorulmus:
                    self._korluk_kaydet(nid, yas, now)
                continue
            self._komsu_gorulmus.add(nid)
            if nid in self._korluk_bildirildi:
                self._korluk_bildirildi.discard(nid)
                self.get_logger().warning(
                    f'drone{nid} TEKRAR GORULUYOR ({yas:.2f} sn yasinda) — '
                    f'korluk bitti.'
                )
                self._olay(SystemEvent.SEVERITY_INFO, nid,
                           f'drone{nid} tekrar goruluyor, kacinma korlugu bitti')

    def _korluk_kaydet(self, nid: int, yas: float, now: float) -> None:
        """Kaybolan komsuyu olay olarak bildirir — P0.15, 21 Agustos 2026.

        NEDEN LOG YETMEZ: 21 Agustos ucusunda ylp00, ylp02'yi 46.4 saniye
        goremedi ve operator o sirada ucaklari 3 metreye kadar yaklastirdi.
        Kacinma tetiklenmedi cunku ortada komsu YOKTU. `esp32_bridge` durumu
        loga yazdi ama CA yalniz `skip_stale` sayacinda sessizce sayiyordu;
        ucus sirasinda bunu gorecek hicbir kanal yoktu.

        Alarm YALNIZ BIR KEZ basilir (komsu basina). Tekrar gorulunce
        `_korluk_bildirildi`den dusuyor, yani sonraki kopma yeniden bildirilir.
        """
        if nid in self._korluk_bildirildi:
            return
        if yas < self._korluk_alarm_s:
            return
        self._korluk_bildirildi.add(nid)
        self._n_korluk += 1
        self.get_logger().warning(
            f'🔴 KACINMA KORU: drone{nid} {yas:.1f} sndir gorulmuyor '
            f'(esik {self._korluk_alarm_s:.1f}). Bu komsuya karsi KORUMA YOK. '
            f'Mesh tek yonlu olmus olabilir — bkz. TUZAKLAR 2.15.'
        )
        # 🔴 SEVERITY_CRITICAL — operator karari (21 Agustos 2026).
        # YKI'de "KRİTİK" etiketi + SESLI alarm (AlertList.tsx:12,
        # alert-critical.wav) tetikliyor. Korluk = o komsuya karsi koruma
        # YOK demek; carpisma onlemenin sessizce devre disi kalmasi sesli
        # duyulmasi gereken bir seydir. WARNING sarı satirdi, kacabilirdi.
        self._olay(SystemEvent.SEVERITY_CRITICAL, nid,
                   f'KACINMA KORU: drone{nid} {yas:.1f} sndir gorulmuyor — '
                   f'BU KOMSUYA KARSI CARPISMA KORUMASI YOK')

    def _olay(self, severity: int, nid: int, mesaj: str) -> None:
        """Korluk olayini yayinlar (YKI gorsun diye)."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_COLLISION_RISK
        m.severity = severity
        m.source_agent_id = self._agent_id
        m.source_module = 'collision_avoidance'
        m.value = float(nid)
        m.message = mesaj
        self._event_pub.publish(m)

    def _tick(self) -> None:
        """ROS timer tetiklemesiyle ana döngüyü işletir."""
        try:
            # KORLUK TARAMASI SETPOINT AKISINDAN BAGIMSIZ — P0.15,
            # 21 Agustos 2026 aksami, YERDE olculdu.
            #
            # Ilk yazimda korluk tespiti `_gather_obstacles` icindeydi, o da
            # `_tick_inner`in ICINDE cagriliyor. Ama `_tick_inner` iki yerde
            # ERKEN CIKIYOR:
            #     if raw is None: return                     <- setpoint yok
            #     if now - _raw_stamp > _raw_timeout: return  <- bayat
            # Yani setpoint akmiyorsa korluk HIC TESPIT EDILMIYORDU.
            #
            # Sahada yakalandi: iki ucak yerde, ylp02'nin esp32_bridge'i
            # oldurulup mesh kesildi; komsu verisi gercekten durdu
            # (`ros2 topic hz` bos dondu) ama ylp00'da korluk=0 kaldi ve
            # hicbir uyari cikmadi.
            #
            # Bu yalniz test kolayligi degil: ucak HAVADA da setpoint akisi
            # kesilebilir (gorev bitti, bekleme evresi, YKI koptu) ve tam o
            # anda komsusunu kaybetmis olabilir. Korluk her durumda
            # bilinmeli — kacinmanin "acik mi" sorusundan bagimsiz bir
            # GUVENLIK bilgisi.
            self._korluk_tara(self.get_clock().now().nanoseconds * 1e-9)
            self._tick_inner()
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_tick hata: {type(e).__name__}: {e}'
            )

    def _tick_inner(self) -> None:
        raw = self._raw
        if raw is None:
            return
        now = self.get_clock().now().nanoseconds * 1e-9
        if now - self._raw_stamp > self._raw_timeout_s:
            return

        if (raw.priority >= AgentSetpoint.PRIORITY_FAILSAFE
                or raw.hold_position or raw.land_now or raw.rtl_now):
            self._relay(raw)
            return

        if not self._pos_ok:
            self._relay(raw)
            return

        if (self._altitude_gate_m > 0.0
                and (-self._cur_z) < self._altitude_gate_m):
            self._n_gate_alt += 1
            self._relay(raw)
            return

        obstacles = self._gather_obstacles(now)

        # KORLUKTE DUR — P0.15, 21 Agustos 2026.
        #
        # Komsuyu kaybetmek "engel yok" DEGIL, "nerede oldugunu BILMIYORUM"
        # demektir. Son gorulen yerden sonra komsu v_max ile HER YONE
        # gidebilir; 4 m/s'te 5 saniyede 20 m'lik bir belirsizlik kuresi
        # olusur ve o kureden kacmanin anlamli bir YONU yoktur — itme yonu
        # uydurmak, komsunun ustune gitme ihtimalini de tasir.
        #
        # Tek muhafazakar davranis: YATAY HAREKETI DURDUR ve bekle. Dikeye
        # DOKUNULMUYOR (irtifa ayrimi yedek garantimiz; ayrica tirmanis/inis
        # kesilirse ucak havada asili kalir).
        #
        # 21 Agustos'ta bu olmasa ne olurdu: ylp00 46 saniye kor kaldi ve o
        # sure boyunca hicbir sey degismedi. Formasyonda olsaydi kor uctan
        # komsusuna dogru YURUMEYE DEVAM ederdi.
        if self._korluk_tut_s > 0.0 and self._korluk_bildirildi:
            kor = sorted(self._korluk_bildirildi)
            yaslar = [now - self._neighbor_rx.get(n, 0.0) for n in kor]
            if max(yaslar) >= self._korluk_tut_s:
                if not self._korluk_tut_aktif:
                    self._korluk_tut_aktif = True
                    self.get_logger().warning(
                        f'🔴 KORLUK TUTMASI: drone{kor} {max(yaslar):.1f} '
                        f'sndir gorulmuyor -> YATAY HAREKET DURDURULDU. '
                        f'Dikey serbest; komsu tekrar gorulunce serbest kalir.'
                    )
                    self._olay(SystemEvent.SEVERITY_WARNING, kor[0],
                               f'KORLUK TUTMASI: drone{kor} gorulmuyor, '
                               f'yatay hareket durduruldu')
                dur = copy.deepcopy(raw)
                dur.stamp = self.get_clock().now().to_msg()
                dur.sequence_num = self._sequence_num
                self._sequence_num += 1
                dur.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
                dur.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
                dur.position_valid = False
                dur.vx = 0.0
                dur.vy = 0.0
                # vz KORUNUYOR: tirmanis/inis kesilmesin, irtifa ayrimi
                # bozulmasin. Ham setpoint hiz vermiyorsa 0 zaten dogru.
                dur.vz = float(raw.vz) if raw.velocity_valid else 0.0
                dur.velocity_valid = True
                dur.acceleration_valid = False
                dur.max_speed_mps = self._v_max_mps
                dur.source_module = 'collision_avoidance:korluk'
                self._setpoint_pub.publish(dur)
                self._ca.reset((0.0, 0.0, self._cur_vz))
                self._n_korluk_tut += 1
                return
        elif self._korluk_tut_aktif:
            self._korluk_tut_aktif = False
            self.get_logger().info(
                'korluk tutmasi KALKTI — komsular tekrar goruluyor.'
            )

        base = (
            (float(raw.vx), float(raw.vy), float(raw.vz))
            if raw.velocity_valid else (0.0, 0.0, 0.0)
        )
        v_cmd, risk = self._ca.compute(base, obstacles)

        if not risk:
            self._relay(raw, reset_core=False)
            return

        out = copy.deepcopy(raw)
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1
        out.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
        out.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
        out.position_valid = False
        out.vx = float(v_cmd[0])
        out.vy = float(v_cmd[1])
        out.vz = float(v_cmd[2])
        out.velocity_valid = True
        out.acceleration_valid = False
        out.max_speed_mps = self._v_max_mps
        out.source_module = 'collision_avoidance'

        self._setpoint_pub.publish(out)
        self._n_avoid += 1

        if now - self._last_active_log > 1.0:
            self.get_logger().warn(
                f'CA kacis aktif: v=({v_cmd[0]:.2f},{v_cmd[1]:.2f},'
                f'{v_cmd[2]:.2f}) m/s, {len(obstacles)} komsu etkide',
            )
            self._last_active_log = now

    def _relay(self, raw: AgentSetpoint, reset_core: bool = True) -> None:
        """Ham setpoint verisini doğrudan geçirir."""
        if reset_core:
            self._ca.reset((self._cur_vx, self._cur_vy, self._cur_vz))
        self._n_passthrough += 1
        self._setpoint_pub.publish(raw)

    def _diag_tick(self) -> None:
        """Tani verilerini loglar."""
        try:
            self.get_logger().info(
                f'tani: passthrough={self._n_passthrough} '
                f'avoid={self._n_avoid} '
                f'gate_alt={self._n_gate_alt} '
                f'skip_state={self._n_skip_state} '
                f'skip_stale={self._n_skip_stale} '
                f'skip_adaptor={self._n_skip_adaptor or "-"} '
                f'korluk={self._n_korluk} '
                f'korluk_tut={self._n_korluk_tut} '
                f'kor_komsu={sorted(self._korluk_bildirildi) or "-"} '
                f'komsu_veri={len(self._neighbors)}/'
                f'{len(self._neighbor_subs)} '
                f'ben={"var" if self._ben is not None else "YOK"}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tani log hata: {e}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CollisionAvoidanceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
