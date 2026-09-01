"""MAVROS RC girdisini SwarmControlCommand mesajına dönüştüren düğüm.

MAVROS'un /mavros/manual_control/control mesajını okur, normalize
ederek SwarmControlCommand mesajına dönüştürür ve
/swarm/internal/control/command'a yayınlar.

Contract (§4.2):
  joystick_interpreter_node.py → /swarm/internal/control/command
    [SwarmControlCommand.msg]
  → proxy → /swarm/public/control/command
  → mode_manager/movement_mode.py / mode_manager/maneuver_mode.py

Yayın frekansı: 20-50 Hz (contract'ta belirtilmiş).

GCS arayüzünden gelen mod değişimleri ve formasyon komutları bu
node tarafından SwarmControlCommand'a gömülür.
"""

from collections import namedtuple

from mavros_msgs.msg import ManualControl, RCIn
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from sensor_msgs.msg import Joy

from std_msgs.msg import Float32MultiArray
from swarm_interfaces.msg import SwarmControlCommand

from . import canli_param
from . import formasyon_kilidi
from . import rc_eksen
from .formasyon_kilidi import FormasyonKilidi
from .swc_debounce import SwcDebounce
from .swd_mandal import SwdMandal
from .tek_atis_seri import TekAtisSeri

_MavrosManual = namedtuple('_MavrosManual', [
    'pitch', 'roll', 'yaw', 'throttle',
    'aux1', 'aux2', 'aux3', 'aux4', 'aux5', 'aux6',
])

_PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# 🔴 KOMUT YAYINI RELIABLE — 30 Agustos 2026, SAHADA olculdu.
#
# Bu dugum BEST_EFFORT yayinliyordu ve `ic_dis_kopru` bu konuyu RELIABLE
# dinliyor (ic_dis_kopru.py:80 "butun internal yayincilar RELIABLE" — o
# tarama 15 Agustos'ta yapildi ve BU DUGUM O ZAMAN HIC KOSMUYORDU).
# RELIABLE abone + BEST_EFFORT yayinci ESLESMEZ ve mesaj akmaz.
#
# OLCULEN SONUC (ylp00, joystick anahtari acikken):
#     /swarm/internal/control/command   46.6 Hz
#     /swarm/public/control/command     HICBIR SEY
# Yani PILOTUN KENDI UCAGI cubuga cevap vermezdi; diger ikisi mesh'ten
# (esp32_bridge BEST_EFFORT dinliyor, eslesiyordu) alip cevap verirdi.
# Havada teshisi cok zor bir ariza.
#
# Neden yayinciyi degistiriyoruz, aboneyi degil: INTERFACE_CONTRACT §3.0.1
# "RELIABLE yayinci + BEST_EFFORT abone UYUMLU" diyor. RELIABLE yapinca
# ucu de calisiyor: ic_dis_kopru (RELIABLE) ✅ · esp32_bridge (BEST_EFFORT) ✅
# · rosbag2 (BEST_EFFORT) ✅. Konu ROS_LOCALHOST_ONLY ile yerel, kayip ~0.
_KOMUT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class JoystickInterpreterNode(Node):
    """MAVROS ManualControl - SwarmControlCommand dönüştürücü."""

    # =========================================================================
    # FLYSKY FS-I6X KUMANDA KANAL VE EŞİK DEĞERİ AYARLARI
    # Kumanda switch kanallarını değiştirmek istediğinizde
    # buradaki sabitleri güncelleyebilirsiniz:
    # =========================================================================
    AUX_SAFETY_CHANNEL = 'aux1'         # Emniyet Kilidi (SwA)
    AUX_MODE_CHANNEL = 'aux2'          # Mod Seçimi (SwB)
    AUX_FORMATION_CHANNEL = 'aux3'     # Formasyon Seçimi (SwC)
    AUX_TAKEOFF_LAND_CHANNEL = 'aux4'  # Kalkış / İniş (SwD)
    # 🔴 FORMASYON KILIDI (VrB) — 31 Agustos 2026, operator karari.
    # SwC'nin KAPALI konumu YOK: uc konumu da bir formasyon. Kumanda
    # acilir acilmaz salterin durdugu yer bir formasyon TALEBI olarak
    # okunuyordu (ucusta olculdu: kimse dokunmadan requested_formation
    # 0 -> 3 oldu ve formation_change_requested mesh'e cikti).
    # VrB potansiyometresi bos oldugu icin kilit olarak secildi.
    # OLCUM (kumanda_web /k, 31 Agu): VrB -> ch10 -> aux6, tam aralik
    # PWM 1000..2000, baska hicbir kanalda hareket yok (capraz karisma
    # genligi 0). Esik aux 800 ~ PWM 1900; tepe degeri 2000.
    AUX_FORM_KILIT_CHANNEL = 'aux6'    # Formasyon Kilidi (VrB)
    AUX_FORM_KILIT_ESIK = 800          # >800 (~PWM 1900) -> SwC CANLI

    # AUX 1 Emniyet Kilidi Eşik Değeri
    # >300  -> Emniyet AKTİF (komutlar çalışır)
    AUX_SAFETY_THRESH = 300

    # AUX 3 Formasyon Seçimi Eşik Değerleri (-1000..+1000 MAVROS aralığı)
    AUX_FORMATION_THRESH_LOW = -300    # <-300 -> Ok Başı (1)
    AUX_FORMATION_THRESH_HIGH = 300    # >300  -> Çizgi (3)
    # -300..+300 arası -> V Formasyonu (2)

    # AUX 4 Kalkış / İniş Eşik Değerleri
    AUX_TAKEOFF_THRESH = 300           # >300  -> Takeoff
    AUX_LAND_THRESH = -300             # <-300 -> Land
    # =========================================================================

    def __init__(self) -> None:
        super().__init__('joystick_interpreter_node')

        self._declare_params()

        self._sequence_num = 0
        self._active_mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        self._formation_change_requested = False
        self._requested_formation = 0
        self._requested_spacing_m = self._default_spacing_m
        # 🔴 SwC DEBOUNCE — madde 26, saha olcumuyle (swc_debounce.py).
        # Debounce'suz hali: hakem "cizgiye gec" der, salter ortadan
        # gecerken suru ONCE V'ye morf olmaya baslardi (en dar an 4,95 m,
        # kacinma girisi 4,0 m -> carpisma -20xN riski).
        self._swc = SwcDebounce(self._swc_debounce_ms)
        # 🔴 TEK ATISLIK BAYRAKLAR MESH'TE KAYBOLUYORDU — 31 Agustos, ucusla
        # olculdu: komut ~46 Hz yayinlaniyor, komsuya 12,6 Hz variyor.
        # Tek cerceve suren kalkis/formasyon istegi ~%75 dusuyordu ve ilk
        # pervaneli denemede YALNIZ pilot ucagi kalkti. Gerekce ve 600 ms'in
        # nereden geldigi: tek_atis_seri.py
        self._kalkis_seri = TekAtisSeri()
        self._formasyon_seri = TekAtisSeri()
        # SwD kenar/mandal mantigi saf modulde — birim testle kilitli.
        # Gerekce ve tasarim: swd_mandal.py dosya basligi.
        self._swd = SwdMandal(
            takeoff_esik=self.AUX_TAKEOFF_THRESH,
            land_esik=self.AUX_LAND_THRESH,
        )
        self._safety_active = False
        # Gaz kapisi mandali: SwA her acildiginda SIFIRLANIR, yani pilot
        # emniyeti her actiginda gazi bir kez merkeze getirmek ZORUNDA.
        self._gaz_merkezlendi = False
        # VrB formasyon kilidi. Saf mantik + saha olcumu ve 'neden
        # seviye degil gecis' gerekcesi: formasyon_kilidi.py basligi.
        self._form_kilidi = FormasyonKilidi(self.AUX_FORM_KILIT_ESIK)
        # Dikey yetki mandali — gerekce _on_joy icindeki blokta.
        self._dikey_yetki = False
        # 🔴 GOREV 2 ARALIGI HAVADA DEGISMEZ — madde 29 (31 Agustos 2026).
        # mode_manager._on_g2_ayar ayni kapiyi `ctx.kalkis_tamam` ile
        # koyuyor. Burada da OLMAK ZORUNDA: aralik ucusta ctx'e
        # mode_manager'in kendi alanindan DEGIL, her formasyon
        # degisikliginde joystick komutundan giriyor
        # (mode_manager_node ~914: `if msg.requested_spacing_m > 0`).
        # Yalniz mode_manager'da kapatilsa kapi KAGIT UZERINDE kalirdi:
        # havada gelen yeni aralik buraya yazilir, sonraki SwC
        # hareketinde formasyon ISTENMEDEN morf ederdi.
        #
        # ⚠️ Bu bir ISTEK mandali, olculmus "havadayim" degil — joystick
        # dugumu irtifayi gormuyor. Bilerek temkinli tarafa duruyor:
        # kalkis istendigi an kapanir, inis mandali gelince acilir.
        self._kalkis_istendi = False
        init_cmd = SwarmControlCommand()
        init_cmd.mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        init_cmd.command_valid = False
        init_cmd.deadman_pressed = False
        self._last_cmd = init_cmd
        self._last_input_time = self.get_clock().now()

        self._setup_publishers()
        self._g2_ayar_abone_ol()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._publish_hz,
            self._timer_callback,
        )

        # G2-K9 / madde 29 — GOREV ONCESI CANLI AYAR.
        self.add_on_set_parameters_callback(self._param_degisti)

        self.get_logger().info(
            f'JoystickInterpreterNode basladi: {self._deadman_channel}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        # dynamic_typing SART: `-p x:=7` YAML'da INTEGER'dir ve double
        # declare edilmis dugumu ACILISTA oldurur. Bu tuzak sahada IKI KEZ
        # yasandi (formasyon_sekans) ve bu dugum henuz hic kosmadi — ilk
        # kosacagi yer saha. Ayni sinif hatayi bekleyip yasamiyoruz.
        from rcl_interfaces.msg import ParameterDescriptor
        _dnm = ParameterDescriptor(dynamic_typing=True)
        self.declare_parameter('publish_hz', 30.0, _dnm)
        self.declare_parameter('deadman_channel', 'aux1')
        self.declare_parameter('deadman_threshold', 0.5, _dnm)
        self.declare_parameter('deadman_timeout_s', 0.5, _dnm)
        self.declare_parameter('max_speed_mps', 2.0, _dnm)
        self.declare_parameter('max_yaw_rate_deg_s', 30.0, _dnm)
        self.declare_parameter('max_tilt_deg', 15.0, _dnm)
        # B10: aralik GOMULU 5.0 idi ve `ucus_ayarlari` MOD_ARALIK=7.0 ile
        # celisiyordu. Belirti sessiz: ILK formasyon degisikliginde sürü
        # 7 m'den 5 m'ye kapanirdi. Ad `mode_manager` ile AYNI tutuldu.
        self.declare_parameter('default_spacing_m', 7.0, _dnm)
        # 🔴 GAZ MERKEZ KAPISI (30 Agu, saha olcumu + operator karari).
        # Gaz cubugu ortalanmiyor, dipte duruyor -> throttle_cmd = -1.0.
        # SwA acilinca suru ANINDA alcalirdi. Gerekce: rc_eksen.gaz_merkezde
        self.declare_parameter('gaz_merkez_pay', 0.2, _dnm)
        # SwC debounce esigi. Tek kaynak `ucus_ayarlari` MOD_SWC_DEBOUNCE_MS.
        # Sayinin gerekcesi ve SAHA OLCUMU: swc_debounce.py dosya basligi.
        self.declare_parameter('swc_debounce_ms', 500.0, _dnm)

        self._publish_hz = float(
            self.get_parameter('publish_hz').value
        )
        self._deadman_channel = str(
            self.get_parameter('deadman_channel').value
        )
        self._deadman_threshold = float(
            self.get_parameter('deadman_threshold').value
        )
        self._deadman_timeout_s = float(
            self.get_parameter('deadman_timeout_s').value
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
        self._default_spacing_m = float(
            self.get_parameter('default_spacing_m').value
        )
        self._gaz_merkez_pay = float(
            self.get_parameter('gaz_merkez_pay').value
        )
        self._swc_debounce_ms = float(
            self.get_parameter('swc_debounce_ms').value
        )

    def _param_degisti(self, params):
        """ros2 param set icin dogrulama ve UYGULAMA (G2-K9, madde 29).

        Kapi saf modulde (canli_param.py). Gerekce mode_manager'daki
        esiyle ayni: geri cagri olmadan parametreler __init__'te
        `self._*`'a kopyalaniyordu ve `ros2 param set` "successful" deyip
        HICBIR SEY yapmiyordu.
        """
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            try:
                deger = canli_param.dogrula(
                    p.name, p.value, canli_param.JOYSTICK_CANLI)
            except canli_param.ParamRed as e:
                return SetParametersResult(successful=False, reason=str(e))

            self._default_spacing_m = deger
            # ⚠️ IKISI DE YAZILMALI. Tele giden alan `_requested_spacing_m`;
            # yalniz `_default_spacing_m` guncellenseydi ayar kabul edilmis
            # gorunur ama SURUYE HIC ULASMAZDI (ayni sinif sessiz no-op).
            self._requested_spacing_m = deger
            self.get_logger().warning(
                f'[joystick] CANLI AYAR: aralik = {deger:g} m '
                f'(mesh uzerinden uc ucaga gider)'
            )
        return SetParametersResult(successful=True)

    def _swc_bolge(self, aux3_val) -> int:
        """Salterin ham degerini FORMATION_* sabitine cevirir (SwC).

        TEK YERDE: emniyet acik ve kapali dallari ayni esleme kullanmak
        ZORUNDA. Ayrisirlarsa kilit acildiginda deger degismis gorunur ve
        SAHTE bir formasyon degisimi tetiklenir.

        🔴 ORTA = V (B4, 30 Agustos 2026). Onceden FORMATION_UNKNOWN (0)
        idi ve bu SESSIZ BIR SARTNAME IHLALIYDI: sinifin kendi sabit
        yorumu "-300..+300 arasi -> V Formasyonu (2)" diyordu, _on_joy
        yorumu "Hicbiri = Ortada (V)" diyordu, ama kod 0 uretiyordu.
        Sonuc: V formasyonu kumandadan ULASILAMAZ. Ustelik esp32_bridge
        formasyon=0 ile gelen degisiklik bayragini BILEREK dusuruyor, yani
        talep mesh'e bile cikmiyordu. Sartname §5.2.2 ornek hakem
        direktifi birebir: "V formasyonuna gec".
        """
        if aux3_val < self.AUX_FORMATION_THRESH_LOW:
            return SwarmControlCommand.FORMATION_OKBASI
        if aux3_val > self.AUX_FORMATION_THRESH_HIGH:
            return SwarmControlCommand.FORMATION_CIZGI
        return SwarmControlCommand.FORMATION_V

    def _simdi_s(self) -> float:
        """Debounce icin saniye. ROS saati — sim zamaniyla da tutarli."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _g2_ayar_abone_ol(self) -> None:
        """Gorev 2 baslatma ayarindaki ARALIGI dinler (madde 29).

        🔴 BURASI ARALIGIN GERCEK KAYNAGI. mode_manager'daki deger yalniz
        yedek: her cerceve `cmd.requested_spacing_m` ile buradan bir sayi
        gidiyor ve mode_manager onu ">0 ise KABUL ET" kuraliyla aliyor.
        Yani yalniz mode_manager'a uygulasaydik, joystick bir sonraki
        cercevede ESKI araligi geri yazardi — sessiz ve tam olarak
        "hata vermeden yanlis sonuc" sinifi.

        Irtifa BURADA KULLANILMIYOR: kalkis irtifasi mode_manager'in isi.
        """
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

    def _on_g2_ayar(self, msg: Float32MultiArray) -> None:
        v = list(msg.data)
        try:
            aralik, _irtifa = canli_param.g2_ayar_dogrula(
                v[0] if v else 0.0, 0.0)
        except canli_param.ParamRed as e:
            self.get_logger().error(f'[joystick] GOREV 2 ARALIK RED: {e}')
            return
        if aralik == canli_param.BELIRTILMEDI:
            return
        if self._kalkis_istendi:
            self.get_logger().warning(
                f'[joystick] GOREV 2 ARALIGI YOK SAYILDI ({aralik:.1f} m) — '
                'kalkis istendi. Aralik yalniz kalkis oncesi degisir; '
                'havada degistirmek formasyonu istemeden morf ettirir.'
            )
            return
        # Esi mode_manager'daki gibi: ALANA DEGIL PARAMETREYE yaz.
        # Dogrudan yazilirsa `ros2 param get default_spacing_m` eski
        # degeri soyler ve operator "ayar gitmemis" sanir (31 Agu, ucakta
        # olculdu). Geri cagri iki alani da kendisi guncelliyor.
        sonuc = self.set_parameters(
            [Parameter('default_spacing_m', Parameter.Type.DOUBLE, aralik)])
        if not sonuc[0].successful:
            self.get_logger().error(
                '[joystick] GOREV 2 ARALIGI PARAMETREDE REDDEDILDI: '
                f'{sonuc[0].reason}')
            return
        self.get_logger().warning(
            f'[joystick] GOREV 2 ARALIGI UYGULANDI: {aralik:.1f} m '
            '(mesh uzerinden uc ucaga gider)'
        )

    def _setup_publishers(self) -> None:
        """Aciklama: SwarmControlCommand publisher'ını oluşturur."""
        self._cmd_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            _KOMUT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """MAVROS joystick, ROS2 Joy ve GERÇEK DRONE girdi abonelikleri."""
        self.create_subscription(
            ManualControl,
            '/mavros/manual_control/control',
            self._on_mavros_manual_control,
            _PX4_QOS,
        )
        self.create_subscription(
            Joy,
            '/joy',
            self._on_joy,
            10,
        )
        # Gerçek fiziksel drone kumanda bağlantısı (RC receiver -> PX4 ->
        # MAVROS)
        self.create_subscription(
            RCIn,
            '/mavros/rc/in',
            self._on_mavros_rc_in,
            _PX4_QOS,
        )

    def _on_manual_control(self, msg: '_MavrosManual') -> None:
        """Normalize girdiyi SwarmControlCommand'a cevirir."""
        cmd = SwarmControlCommand()
        cmd.stamp = self.get_clock().now().to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        deadman_value = self._read_aux_channel(msg)
        deadman_pressed = deadman_value > self._deadman_threshold
        cmd.command_valid = deadman_pressed
        cmd.deadman_pressed = deadman_pressed
        cmd.deadman_timeout_s = self._deadman_timeout_s

        # ======= EMNİYET KİLİDİ (AUX 1 - SwA) =======
        # SwA aktif değilse hiçbir komut çalışmaz (arm dahil)
        aux1_val = getattr(msg, self.AUX_SAFETY_CHANNEL, 0)
        self._safety_active = aux1_val > self.AUX_SAFETY_THRESH

        # Emniyet kilitliyken de aux durumlarını takip et.
        # Böylece kilit açıldığında sahte edge tetiklenmez.
        aux4_val = getattr(msg, self.AUX_TAKEOFF_LAND_CHANNEL, 0)
        aux3_val = getattr(msg, self.AUX_FORMATION_CHANNEL, 0)
        aux6_val = getattr(msg, self.AUX_FORM_KILIT_CHANNEL, 0)

        if not self._safety_active:
            # Emniyet kapandi -> gaz kapisi YENIDEN kurulur.
            self._gaz_merkezlendi = False
            # Ayni gerekce: emniyet kapandiysa dikey yetki de dusurulur.
            self._dikey_yetki = False
            # Formasyon kilidi de sifirlanir; emniyet tekrar acildiginda
            # VrB acik BILE OLSA SwC konumu yeniden taban alinir.
            self._form_kilidi.sifirla()
            # 🔴 SwD KENARLARI EMNIYET KAPALIYKEN DE ISLENIR — iptal
            # bayragi emniyete bagli OLAMAZ (G2-K7 iki kademeli iptal:
            # "SwA kapat -> HOLD" ve "SwD -> inis" BAGIMSIZ). Kalkis
            # kenari burada bilerek sayilmaz: emniyet kapaliyken kalkis yok.
            self._swd.guncelle(aux4_val, emniyet_acik=False)
            # SwC izlenmeye DEVAM eder ama degisim URETMEZ. Hizalanmasaydi
            # emniyet acildigi anda "bolge degisti" gorunur ve SAHTE bir
            # formasyon degisimi tetiklenirdi. ORTA = V (B4) eslemesi
            # emniyet kilitliyken de ayni olmak zorunda, tam bu yuzden.
            self._swc.esitle(self._swc_bolge(aux3_val), self._simdi_s())
            # Emniyet kapandi: bekleyen seriler DUSURULUR. Aksi halde
            # kapanistan hemen once basilan bir kalkis istegi, emniyet
            # kapaliyken bile mesh'e akmaya devam ederdi.
            self._kalkis_seri.sifirla()
            self._formasyon_seri.sifirla()

            cmd.command_valid = False
            cmd.deadman_pressed = False
            cmd.takeoff = False
            # 🔴 INIS BAYRAGI BURADA SIFIRLANMAZ (30 Agustos 2026).
            # Eskiden sifirlaniyordu: pilot once SwA'yi kapatip sonra SwD
            # ile inmek isterse komut HIC gitmiyordu.
            # mode_manager._on_control_command command_valid=False iken
            # land/rtl/emergency'i zaten koruyor — ama joystick tarafi
            # bayragi silince o koruma OLU KODDU.
            cmd.land = self._swd.inis_mandali
            cmd.rtl = False
            cmd.emergency_stop = False
            cmd.pitch_cmd = 0.0
            cmd.roll_cmd = 0.0
            cmd.yaw_cmd = 0.0
            cmd.throttle_cmd = 0.0
            cmd.mode = self._active_mode
            cmd.formation_change_requested = False
            cmd.requested_formation = self._requested_formation
            cmd.requested_spacing_m = self._requested_spacing_m
            cmd.max_speed_mps = self._max_speed_mps
            cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
            cmd.max_tilt_deg = self._max_tilt_deg
            cmd.source_module = 'joystick_interpreter'
            self._last_cmd = cmd
            self._last_input_time = self.get_clock().now()
            self._cmd_pub.publish(cmd)
            return

        # Mod Seçimi (AUX 2 - SwB: 0 -> Movement, 1 -> Maneuver)
        aux2_val = getattr(msg, self.AUX_MODE_CHANNEL, 0)
        if aux2_val > 0:
            self._active_mode = SwarmControlCommand.MODE_MANEUVER
        else:
            self._active_mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        cmd.mode = self._active_mode

        # 🔴 FORMASYON SECIMI (SwC) — DEBOUNCE'LI (madde 26).
        # Salter yeni bolgede `swc_debounce_ms` KARARLI kalmadan degisim
        # tetiklenmez. Saha olcumu ve 500 ms'nin gerekcesi:
        # swc_debounce.py dosya basligi (11 gecis, tavan 342 ms).
        #
        # 🔴 VrB KILIDI (31 Agu) — SwC ancak VrB TAM CEVRILIYKEN canli.
        # Uc dal da `esitle`/`guncelle` ayrimina dayaniyor; ayni desen
        # emniyet-kapali dalinda zaten kullaniliyor (swc_debounce.esitle
        # docstring'i). `esitle` salteri izlemeye devam eder ama degisim
        # URETMEZ, yani kilit acildiginda sahte tetikleme olmaz.
        swc_bolge = self._swc_bolge(aux3_val)
        kilit = self._form_kilidi.degerlendir(aux6_val)
        talep, degisim = formasyon_kilidi.talep_hesapla(
            kilit, swc_bolge, self._requested_formation)
        if talep == formasyon_kilidi.DEBOUNCE:
            # Kilit ACIK: karari SwcDebounce verir (madde 26).
            if self._swc.guncelle(swc_bolge, self._simdi_s()):
                self._requested_formation = self._swc.kararli
                self._formation_change_requested = True
        else:
            # KAPALI ya da YENI_ACILDI. Ikisinde de debounce'un kararli
            # bolgesi hizalanir; hizalanmasaydi bir sonraki `guncelle`
            # SAHTE bir degisim uretirdi (swc_debounce.esitle docstring'i).
            self._swc.esitle(swc_bolge, self._simdi_s())
            self._requested_formation = talep
            if degisim:
                self._formation_change_requested = True
                self.get_logger().warning(
                    f'formasyon kilidi (VrB) {kilit} -> talep={talep}: '
                    + ('FORMASYON KALDIRILDI — ucaklar bulundugu yeri tutar'
                       if talep == formasyon_kilidi.FORMASYON_YOK
                       else 'formasyon AKTIF')
                )
            elif kilit == formasyon_kilidi.KAPALI:
                self.get_logger().info(
                    'formasyon kilidi KAPALI (VrB cevrili degil) — formasyon '
                    'YOK, ucaklar bulundugu yeri tutar.',
                    throttle_duration_sec=10.0,
                )

        cmd.pitch_cmd = self._clamp(msg.pitch)
        cmd.roll_cmd = self._clamp(msg.roll)
        cmd.yaw_cmd = self._clamp(msg.yaw)
        # 🔴 GAZDA DA OLU BANT — 31 Agustos 2026. pitch/roll/yaw
        # `eksen_normalize` icinde olu banttan geciyor ama gaz AYRI yoldan
        # geliyor (`gaz_normalize` [0,1] -> burada -1..+1). Olu bant
        # olmasaydi, dikey yetki mandali acildiktan SONRA merkeze yakin
        # kalan kucuk bir sapma yavas tirmanma/alcalma uretirdi — pitch'te
        # olculen yatay kaymanin dikey ikizi.
        cmd.throttle_cmd = rc_eksen.olu_bant_uygula(
            self._clamp(msg.throttle * 2.0 - 1.0))
        # Kapilar cmd.throttle_cmd'i sifirlayabiliyor; merkez sinamasi
        # HAM deger uzerinden yapilmali, yoksa sifirlanan deger 'merkezde'
        # gorunup kapiyi kendi kendine acardi.
        ham_gaz = cmd.throttle_cmd

        # 🔴 GAZ MERKEZ KAPISI — emniyet acildiktan sonra gaz bir kez
        # merkeze gelene kadar HAREKET YOK. Bkz. rc_eksen.gaz_merkezde:
        # cubuk dipte durdugu icin throttle_cmd = -1.0 ve suru aninda
        # alcalirdi. Mandal: bir kez merkezlendikten sonra pilot gazi
        # serbestce kullanir (alcalma/tirmanma zaten onun komutu).
        if not self._gaz_merkezlendi:
            if rc_eksen.gaz_merkezde(cmd.throttle_cmd, self._gaz_merkez_pay):
                self._gaz_merkezlendi = True
                self.get_logger().info(
                    'gaz merkezlendi — suru komutlari ARTIK GECERLI'
                )
            else:
                # command_valid=False: mode_manager eksenleri sifirlar ve
                # command_active dustugu icin HOLD'a gecer. deadman_pressed
                # DOKUNULMAZ — emniyet acik, sorun gazin yerinde.
                cmd.command_valid = False
                cmd.pitch_cmd = 0.0
                cmd.roll_cmd = 0.0
                cmd.yaw_cmd = 0.0
                cmd.throttle_cmd = 0.0
                self.get_logger().warning(
                    'GAZ MERKEZDE DEGIL — suru BEKLIYOR. Gaz cubugunu orta '
                    'konuma getir (cubuk dipteyken sürü tam hizla alcalirdi).',
                    throttle_duration_sec=2.0,
                )

        # 🔴 DIKEY YETKI MANDALI — 31 Agustos 2026, UC UCAKLI KALKISTA
        # ISIRDI. B18 gaz-merkez kapisi TEK ATISLIK: yalniz SwA kapaninca
        # sifirlaniyor. Ucusta olculen zincir:
        #     kapi daha once saglanmis   -> command_valid = True
        #     cubuk dogal yerinde (dip)  -> throttle_cmd = -1,00 SABIT
        #     kalkis bitti, suru READY -> MOVEMENT
        #     -> dikey komut = -1,00 x 2,0 = SANIYEDE 2 m ALCAL
        # Rosbag: vz = +2,00 m/s (NED, doyumda) ve formasyon merkezinin
        # irtifasi ayni hizda kaciyordu (center_z 20,7 -> 22,3 m).
        #
        # NEDEN B18 YENIDEN KURULMUYOR: command_valid ayni zamanda G2-K10'un
        # UC KALKIS KAPISINDAN BIRI. Kalkis kenarinda sifirlansaydi kalkisin
        # KENDISI bloke olurdu. Bu yuzden AYRI mandal: yalniz DIKEY ekseni
        # tutar, command_valid'e ve kalkis kapisina DOKUNMAZ.
        #
        # Kalkis istegiyle sifirlanir (asagida). Tirmanisi mode_manager
        # suruyor, cubuk degil; dolayisiyla tirmanis boyunca dikey komutun
        # sifir olmasi ZARARSIZ. Pilot gazi ortaya getirdigi an yetki acilir.
        if not self._dikey_yetki:
            if rc_eksen.gaz_merkezde(ham_gaz, self._gaz_merkez_pay):
                self._dikey_yetki = True
                self.get_logger().info(
                    'dikey yetki ACIK — gaz merkezlendi, dikey komut gecerli'
                )
            else:
                cmd.throttle_cmd = 0.0
                self.get_logger().warning(
                    'DIKEY KOMUT TUTULUYOR — gaz cubugu merkezde degil '
                    f'({ham_gaz:+.2f}). Ortaya getir; cubuk dipteyken suru '
                    'tam hizla ALCALIRDI.',
                    throttle_duration_sec=3.0,
                )

        cmd.rtl = False
        cmd.emergency_stop = False

        # Kalkış / İniş (AUX 4 - SwD). Kenar degerlendirmesi TEK YERDE:
        # emniyet kapaliyken de calisan SwdMandal (swd_mandal.py).
        self._swd.guncelle(aux4_val, emniyet_acik=True)
        # Kenar TEK ATIS (swd_mandal), ama mesh'te yasamasi icin kisa bir
        # seriye cevriliyor. Mandal DEGIL: seri kendiliginden duser, yoksa
        # salter yukarida kaldikca surekli kalkis istenirdi.
        simdi_s = self._simdi_s()
        if self._swd.kalkisi_tuket():
            self._kalkis_seri.tetikle(simdi_s)
            # Kalkis istendi -> dikey yetki YENIDEN kurulur. Suru
            # irtifaya varip cubuklara yetki verdiginde gaz dipte olsa
            # bile dikey komut sifir olur (yukaridaki blok).
            self._dikey_yetki = False
            # Aralik kapisi kapanir (madde 29) — gerekce __init__'te.
            self._kalkis_istendi = True
        cmd.takeoff = self._kalkis_seri.aktif(simdi_s)
        cmd.land = self._swd.inis_mandali         # MANDAL
        if self._swd.inis_mandali:
            # Inis istendi -> yeni gorev icin aralik yeniden ayarlanabilir.
            self._kalkis_istendi = False
        # 🔴 KALKIS ARTIK GOREVI BASLATMIYOR — madde 25 / G2-K10 (30 Agu).
        #
        # Eskiden burada `_call_trigger_mission(1)` vardi, yani SwD once
        # gorevi baslatiyor sonra kalkis istiyordu. G2-K10'un ucuncu kapisi
        # "gorev YKI'den baslatilmis olacak" diyor; SwD gorevi kendisi
        # baslatabilseydi o kapi KENDI KENDINI ACAR ve tek salter uc ucagi
        # armlardi — 30 Agustos saha olayinin kapatmaya calistigimiz tam
        # sekli. G2-K8: YKI'nin izinli tek eylemi "gorevi baslat", senaryo
        # madde 4 ile madde 5 AYRI adimlar.
        #
        # 🔴 INIS DE mission_fsm'E SERVIS CAGIRMIYOR — madde 28 (30 Agu).
        #
        # Eskiden burada `_call_trigger_mission(6)` (COMMAND_LAND) vardi.
        # OLCULEN sebep: `ROS_LOCALHOST_ONLY=1` (baslat.sh:117), yani bu
        # servis istemcisi YALNIZ KENDI ucagindaki mission_fsm'e ulasir.
        # joystick yalniz ylp00'da kostugu icin sonuc ASIMETRIYDI:
        #     ylp00 mission_fsm -> LANDING -> MISSION_COMPLETE
        #     ylp01/ylp02       -> SEMI_AUTONOMOUS'ta KALIR
        # Ikinci denemede (gorev basina UC HAK) ylp00'in ucuncu kapisi
        # KAPALI, digerlerininki ACIK olurdu: SwD'ye basinca IKI UCAK
        # kalkar, biri yerde kalirdi. Sessiz ve pahali.
        #
        # Inis zaten mission_fsm'e ihtiyac duymuyor: SwD -> mesh -> UC
        # mode_manager -> her biri KENDI px4_bridge'ine 'land' (madde 24).
        # Dagitik yol simetrik, servis yolu degildi.

        # Formasyon talebi de TEK ATISTI ve ayni sebeple dusuyordu.
        # 🔴 YARISMA-KRITIK: hakem "cizgiye gec" der, talep komsulara
        # ~%75 ihtimalle ULASMAZDI.
        if self._formation_change_requested:
            self._formasyon_seri.tetikle(simdi_s)
        cmd.formation_change_requested = self._formasyon_seri.aktif(simdi_s)
        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m

        if self._formation_change_requested:
            self._formation_change_requested = False

        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg
        cmd.source_module = 'joystick_interpreter'

        self._last_cmd = cmd
        self._last_input_time = self.get_clock().now()
        self._cmd_pub.publish(cmd)

    def _timer_callback(self) -> None:
        """Kesintisiz 30 Hz komut akısı saglar."""
        if self._last_cmd is None:
            return

        now = self.get_clock().now()
        elapsed_s = (now - self._last_input_time).nanoseconds / 1e9

        cmd = SwarmControlCommand()
        cmd.stamp = now.to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        cmd.mode = self._last_cmd.mode
        cmd.pitch_cmd = self._last_cmd.pitch_cmd
        cmd.roll_cmd = self._last_cmd.roll_cmd
        cmd.yaw_cmd = self._last_cmd.yaw_cmd
        cmd.throttle_cmd = self._last_cmd.throttle_cmd
        cmd.deadman_timeout_s = self._deadman_timeout_s

        if elapsed_s > self._deadman_timeout_s:
            return

        cmd.command_valid = self._last_cmd.command_valid
        cmd.deadman_pressed = self._last_cmd.deadman_pressed

        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m
        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg
        cmd.source_module = 'joystick_interpreter'

        self._cmd_pub.publish(cmd)

    def _on_mavros_manual_control(self, msg: ManualControl) -> None:
        """MAVROS ManualControl'u normalize edip _on_manual_control'a verir.

        MAVLink MANUAL_CONTROL aralığı [-1000, 1000]; sürü [-1, 1].
        x=pitch, y=roll, r=yaw, z=throttle(0..1000). aux1..aux6 doğrudan.
        Aux aralıkları gerçek kumandayla kontrol edilmeli.
        """
        norm = _MavrosManual(
            pitch=self._clamp(msg.x / 1000.0),
            roll=self._clamp(msg.y / 1000.0),
            yaw=self._clamp(msg.r / 1000.0),
            throttle=self._clamp(msg.z / 1000.0, 0.0, 1.0),
            aux1=msg.aux1, aux2=msg.aux2, aux3=msg.aux3,
            aux4=msg.aux4, aux5=msg.aux5, aux6=msg.aux6,
        )
        self._on_manual_control(norm)

    def _on_mavros_rc_in(self, msg: RCIn) -> None:
        """GERÇEK DRONE: MAVROS RCIn sinyalini normalize edip işler.

        Pixhawk üzerindeki fiziksel SBUS/PPM alıcısından gelen veriler.
        Kanal aralığı tipik olarak [1000, 2000].
        Orta nokta 1500. _MavrosManual'a [-1, 1] veya raw aux [-1000, 1000]
        olacak şekilde ölçeklenir.
        """
        if len(msg.channels) < 8:
            return

        def map_channel_to_aux(pwm: int) -> int:
            # 1000 -> -1000, 1500 -> 0, 2000 -> 1000
            return int((pwm - 1500.0) * 2.0)

        # FlySky varsayılan Mod2: CH1:Roll, CH2:Pitch, CH3:Throttle, CH4:Yaw
        roll_pwm = msg.channels[0]
        pitch_pwm = msg.channels[1]
        throttle_pwm = msg.channels[2]
        yaw_pwm = msg.channels[3]

        aux1_pwm = msg.channels[4]  # SwA (Emniyet)
        aux2_pwm = msg.channels[5]  # SwB (Mod)
        aux3_pwm = msg.channels[6]  # SwC (Formasyon)
        aux4_pwm = msg.channels[7]  # SwD (Kalkış/İniş)

        throttle_norm = rc_eksen.gaz_normalize(throttle_pwm)

        # 🔴 ISARETLER SAHADA OLCULDU — 30 Agustos 2026, ylp00, FS-i6X #2.
        # Onceki kod "genellikle RCIn pitch ileri itince pwm duser" diye bir
        # VARSAYIMLA pitch'i negatifliyor, yaw'a dokunmuyordu. Olcum ikisinin
        # de YANLIS oldugunu gosterdi (3246 cerceve, tek yon denetimi temiz):
        #     ileri -> pitch 1974 (UST)  ·  saga -> roll 1981 (UST)
        #     saga  -> yaw   1014 (ALT)  <- TEK ters olan
        # Gerekce, olcum ve "kumanda degisirse ne yapilir": rc_eksen.py
        pitch_axis = rc_eksen.eksen_normalize(pitch_pwm, rc_eksen.TERS_PITCH)
        roll_axis = rc_eksen.eksen_normalize(roll_pwm, rc_eksen.TERS_ROLL)
        yaw_axis = rc_eksen.eksen_normalize(yaw_pwm, rc_eksen.TERS_YAW)

        norm = _MavrosManual(
            pitch=self._clamp(pitch_axis),
            roll=self._clamp(roll_axis),
            yaw=self._clamp(yaw_axis),
            throttle=throttle_norm,
            aux1=map_channel_to_aux(aux1_pwm),
            aux2=map_channel_to_aux(aux2_pwm),
            aux3=map_channel_to_aux(aux3_pwm),
            aux4=map_channel_to_aux(aux4_pwm),
            aux5=map_channel_to_aux(
                msg.channels[8]) if len(
                msg.channels) > 8 else 0,
            aux6=map_channel_to_aux(
                msg.channels[9]) if len(
                    msg.channels) > 9 else 0,
        )
        self._on_manual_control(norm)

    def _on_joy(self, msg: Joy) -> None:
        """ROS2 Joy mesajını normalize edip _on_manual_control'a verir.

        FlySky FS-i6X Dongle Channel Mapping (DOĞRULANMIŞ):
        - axes[0]: Roll (Sağ stick LR)
        - axes[1]: Pitch (Sağ stick UD)
        - axes[2]: Throttle (Sol stick UD)
        - axes[3]: Yaw (Sol stick LR)
        - axes[4]: SwA (2-pos: Emniyet)
        - axes[5]: SwC (3-pos: Formasyon)
        - axes[6]: SwB (2-pos: Mod)
        - axes[7]: SwD (2-pos: Kalkış/İniş)
        """
        roll = msg.axes[0] if len(msg.axes) > 0 else 0.0
        pitch = msg.axes[1] if len(msg.axes) > 1 else 0.0
        throttle = msg.axes[2] if len(msg.axes) > 2 else 0.0
        yaw = msg.axes[3] if len(msg.axes) > 3 else 0.0

        # SwA (Emniyet Kilidi): Yukarı = Buton 1 veya axis 4 < -0.2 (KİLİTLİ)
        # Aşağı  = Buton 2 (idx 1) veya axis 4 > 0.2 -> EMNİYET AÇIK (1000)
        btn_swa_up = bool(msg.buttons[0]) if len(msg.buttons) > 0 else False
        btn_swa_down = bool(msg.buttons[1]) if len(msg.buttons) > 1 else False
        axis_swa = msg.axes[4] if len(msg.axes) > 4 else 0.0

        if btn_swa_up or axis_swa < -0.2:
            aux1 = -1000
        elif btn_swa_down or axis_swa > 0.2:
            aux1 = 1000
        else:
            aux1 = -1000

        # SwB (Sürü Modu): Buton 2 (idx 2) = Yukarı (Movement), Buton 3 (idx 3)
        # = Aşağı (Maneuver)
        btn_swb_down = bool(msg.buttons[3]) if len(msg.buttons) > 3 else False
        aux2 = 1000 if btn_swb_down else -1000

        # SwC (Formasyon 3-pos): Buton 4 (idx 4) = Yukarı (Ok Başı), Buton 5
        # (idx 5) = Aşağı (Çizgi), Hiçbiri = Ortada (V)
        btn_swc_top = bool(msg.buttons[4]) if len(msg.buttons) > 4 else False
        btn_swc_bot = bool(msg.buttons[5]) if len(msg.buttons) > 5 else False
        if btn_swc_top and not btn_swc_bot:
            aux3 = -1000   # YUKARI = Ok Başı
        elif btn_swc_bot and not btn_swc_top:
            aux3 = 1000    # AŞAĞI = Çizgi
        else:
            aux3 = 0       # ORTA = V Formasyonu

        # SwD (Kalkış / İniş): Buton 6 (idx 6) = Yukarı (İniş), Buton 7 (idx 7)
        # = Aşağı (Kalkış)
        btn_swd_down = bool(msg.buttons[7]) if len(msg.buttons) > 7 else False
        aux4 = 1000 if btn_swd_down else -1000

        aux5 = 0
        aux6 = 0

        norm = _MavrosManual(
            pitch=self._clamp(pitch),
            roll=self._clamp(roll),
            yaw=self._clamp(yaw),
            throttle=self._clamp(throttle),
            aux1=int(aux1), aux2=int(aux2), aux3=int(aux3),
            aux4=int(aux4), aux5=int(aux5), aux6=int(aux6),
        )
        self._on_manual_control(norm)

    def _read_aux_channel(self, msg: '_MavrosManual') -> float:
        """Yapılandırılmış deadman kanalını okur."""
        channel_map = {
            'aux1': getattr(msg, 'aux1', 0.0),
            'aux2': getattr(msg, 'aux2', 0.0),
            'aux3': getattr(msg, 'aux3', 0.0),
            'aux4': getattr(msg, 'aux4', 0.0),
            'aux5': getattr(msg, 'aux5', 0.0),
            'aux6': getattr(msg, 'aux6', 0.0),
        }
        return channel_map.get(self._deadman_channel, 0.0)

    @staticmethod
    def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        """Değeri sınırlandırır."""
        return max(lo, min(hi, value))

    def set_control_mode(self, mode: int) -> None:
        """GCS mod değişimi."""
        self._active_mode = mode
        self.get_logger().info(
            f'Mod degisti: {mode}'
        )

    def set_formation(
        self, formation_type: int, spacing_m: float = 5.0
    ) -> None:
        """GCS formasyon değişimi."""
        self._formation_change_requested = True
        self._requested_formation = formation_type
        self._requested_spacing_m = spacing_m
        self.get_logger().info(
            f'Formasyon degisikligi: {formation_type}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = JoystickInterpreterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
