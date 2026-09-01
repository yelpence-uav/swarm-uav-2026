"""
mavros_command_sender.py

FSM kararlarini MAVROS uzerinden PX4'e ileten komut gondericisi.

Kullanilan MAVROS arayuzleri:
- {ns}/mavros/cmd/arming            (servis) -> arm/disarm
- {ns}/mavros/cmd/set_home          (servis) -> HOME kaydini yeniden yaz
- {ns}/mavros/set_mode              (servis) -> OFFBOARD/AUTO.LAND/RTL
- {ns}/mavros/setpoint_raw/local    (topic)  -> pozisyon/hiz + yaw
- {ns}/mavros/global_position/set_gp_origin (topic) -> ortak NED origin

Ic hesap NED'dir; MAVROS ROS tarafinda ENU bekler. Setpoint'ler
_ned_to_enu / _yaw_ned_to_enu ile tek noktada cevrilir.
"""

import math

from geographic_msgs.msg import GeoPointStamped

from mavros_msgs.msg import PositionTarget
from mavros_msgs.srv import CommandBool, CommandHome, SetMode

# PX4 ucus modu string'leri (SetMode.custom_mode)
_MODE_OFFBOARD = 'OFFBOARD'
_MODE_AUTO_LOITER = 'AUTO.LOITER'
_MODE_AUTO_LAND = 'AUTO.LAND'
_MODE_AUTO_RTL = 'AUTO.RTL'

# type_mask hazir kombinasyonlari (PositionTarget IGNORE_* sabitlerinden).
# "Yok say" bitleri OR'lanir; kalan alanlar aktif olur.
_PT = PositionTarget
# Sadece pozisyon + yaw (hiz, ivme, yaw_rate yok):
_MASK_POSITION = (
    _PT.IGNORE_VX | _PT.IGNORE_VY | _PT.IGNORE_VZ
    | _PT.IGNORE_AFX | _PT.IGNORE_AFY | _PT.IGNORE_AFZ
    | _PT.IGNORE_YAW_RATE
)
# Sadece hiz + yaw (pozisyon, ivme, yaw_rate yok):
_MASK_VELOCITY = (
    _PT.IGNORE_PX | _PT.IGNORE_PY | _PT.IGNORE_PZ
    | _PT.IGNORE_AFX | _PT.IGNORE_AFY | _PT.IGNORE_AFZ
    | _PT.IGNORE_YAW_RATE
)
# Pozisyon + hiz feedforward + yaw (yalniz ivme ve yaw_rate yok):
_MASK_POS_VEL = (
    _PT.IGNORE_AFX | _PT.IGNORE_AFY | _PT.IGNORE_AFZ
    | _PT.IGNORE_YAW_RATE
)

# POS + VEL + IVME ileri-beslemesi (20 Agustos 2026).
# NEDEN: 30 m bacakta olculdu — seyirde takip hatasi 0.05 m, ama HIZLANMADA
# tepe 1.12 m ve FRENLEMEDE asim 1.18 m. Ikisi de ayni sebepten: PX4 komut
# hizinin DEGISECEGINI bilmiyor, yalnizca anlik hizi goruyor ve farki konum
# terimiyle kapatmaya calisiyor. Yamuk profilin ivmesini dogrudan vermek tam
# bu bosluga karsilik geliyor.
# IGNORE_AF* bitleri YOK; digerleri _MASK_POS_VEL ile ayni.
_MASK_POS_VEL_ACC = (
    _PT.IGNORE_YAW_RATE
)
# KALKIS MASKESI — yatayda HIZ, dikeyde POZISYON.
#
# NEDEN AYRI BIR MASKE VAR (1 Agustos, ylp00 kalkista devrildi):
# Kalkis _MASK_POSITION ile yapiliyordu, yani ucak daha YERDEYKEN PX4 yatay
# KONUM tutuyordu. Konum tutmak "su noktada olmaliyim" demektir; EKF konumu
# sicradiginda PX4 gercek olmayan bir hatayi duzeltmeye calisir ve EGILIR.
# Olculdu: kestirim 1.42 m sicradi -> MPC_XY_P ile ~1.3 m/s talep -> ~14
# derece egim. Yerde duran, gazi kalkis itkisinde olan ucakta 14 derece
# pervaneyi yere sokar. Ucak devrildi, pervaneleri kirildi.
#
# Yatayda HIZ SIFIR komutu ayni amaci (yatayda kimildamasin) guderken bu
# tuzagi tasimaz: kovalanacak birikmis konum hatasi yoktur, kestirim
# sicramasi anlik bir hiz hatasi olarak gorunur ve egim kucuk kalir.
# Bedeli, ruzgarda yavas suruklenme — birkac saniyelik tirmanista onemsiz
# ve devrilmenin yanina bile yaklasmaz.
_MASK_KALKIS = (
    _PT.IGNORE_PX | _PT.IGNORE_PY          # yatay konum YOK SAY
    | _PT.IGNORE_VZ                        # dikey hizi degil konumu kullan
    | _PT.IGNORE_AFX | _PT.IGNORE_AFY | _PT.IGNORE_AFZ
    | _PT.IGNORE_YAW_RATE
)


def _ned_to_enu(x_ned: float, y_ned: float, z_ned: float) -> tuple:
    """NED konumu ENU'ya cevirir.

    x/y yer degistirir, z isaret degistirir; ayni formul ters yonde de
    calisir.

    Args:
        x_ned (float): NED X (Kuzey), metre.
        y_ned (float): NED Y (Dogu), metre.
        z_ned (float): NED Z (Asagi pozitif), metre.

    Returns:
        tuple: (x_enu, y_enu, z_enu) metre.
    """
    return y_ned, x_ned, -z_ned


def _yaw_ned_to_enu(yaw_ned: float) -> float:
    """NED yaw'i ENU yaw'ina cevirir (pi/2 - yaw, [-pi, pi] araliginda).

    Args:
        yaw_ned (float): NED yaw acisi, radyan.

    Returns:
        float: ENU yaw acisi, radyan, [-pi, pi].
    """
    yaw = math.pi / 2.0 - yaw_ned
    return (yaw + math.pi) % (2.0 * math.pi) - math.pi


class MavrosCommandSender:
    """FSM -> PX4 komut koprusu (MAVROS surumu).

    CommandSender ile ayni public arayuzu sunar; px4_bridge ayni cagrilari
    kullanabilir. Servis cagrilari call_async ile yapilir (executor'i
    bloklamamak icin).

    Kullanim:
        sender = MavrosCommandSender(node, namespace='/drone_1')
        sender.arm()
        sender.publish_position_setpoint(x, y, z, yaw_rad)
    """

    def __init__(self, node, namespace: str = '') -> None:
        """MAVROS servis istemcilerini ve publisher'lari olusturur.

        Args:
            node: ROS2 node (istemci/publisher olusturmak icin).
            namespace (str): mavros_node namespace'i, orn. '/drone_1'.
        """
        self._node = node
        ns = namespace

        # Servis istemcileri (arming + mod)
        self._arm_client = node.create_client(
            CommandBool, f'{ns}/mavros/cmd/arming'
        )
        self._mode_client = node.create_client(
            SetMode, f'{ns}/mavros/set_mode'
        )
        # HOME'u yeniden yazmak icin (bkz. set_home). Ayri istemci: arm ve
        # mod istemcileri uzerinden gitmez, farkli servis tipi.
        self._home_client = node.create_client(
            CommandHome, f'{ns}/mavros/cmd/set_home'
        )

        # Setpoint publisher (offboard akisi bu topic uzerinden gider)
        self._setpoint_pub = node.create_publisher(
            PositionTarget, f'{ns}/mavros/setpoint_raw/local', 10
        )

        # Ortak NED origin publisher
        self._origin_pub = node.create_publisher(
            GeoPointStamped, f'{ns}/mavros/global_position/set_gp_origin', 1
        )

    # =================================================================
    # ARM / DISARM  (CommandBool servisi)
    # =================================================================
    def arm(self) -> None:
        """Motorlari arm eder (CommandBool value=True)."""
        self._call_arming(True)

    def disarm(self) -> None:
        """Motorlari disarm eder (CommandBool value=False)."""
        self._call_arming(False)

    def _call_arming(self, value: bool) -> None:
        """Arming servisini bloklamadan cagirir.

        Args:
            value (bool): True=arm, False=disarm.
        """
        if not self._arm_client.service_is_ready():
            self._node.get_logger().warning(
                'arming servisi henuz hazir degil (mavros baglandi mi?)'
            )
            return
        req = CommandBool.Request()
        req.value = value
        etiket = 'ARM' if value else 'DISARM'
        future = self._arm_client.call_async(req)
        future.add_done_callback(
            lambda f: self._servis_sonucu(f, etiket)
        )

    def _servis_sonucu(self, future, etiket: str) -> None:
        """Arm/set_mode servis cevabini loglar.

        call_async sonucu okunmazsa PX4'un RET cevabi sessizce kaybolur:
        FSM iyimser sekilde ARMED'a gecer, arac aslinda arm olmamistir ve
        hata ancak 30 sn sonra "TAKEOFF timeout" olarak yuzeye cikar
        (olculdu: dron 2/3 boyle sessizce yerde kaldi). Burada cevabi
        acikca logluyoruz ki ret ANINDA ve sebebiyle gorunur olsun.

        Args:
            future: call_async'in dondurdugu Future.
            etiket (str): Log'da gorunecek komut adi, orn. 'ARM'.
        """
        log = self._node.get_logger()
        try:
            cevap = future.result()
        except Exception as exc:                     # noqa: BLE001
            log.error(f'{etiket} servis cagrisi HATA: {exc}')
            return

        basarili = getattr(cevap, 'success', None)
        if basarili is None:
            basarili = getattr(cevap, 'mode_sent', False)

        if basarili:
            log.info(f'{etiket} KABUL edildi')
        else:
            # MAV_RESULT: 1=TEMPORARILY_REJECTED, 2=DENIED, 3=UNSUPPORTED,
            # 4=FAILED. Ozellikle 1/2 preflight veya mod kaynakli rettir.
            kod = getattr(cevap, 'result', '?')
            log.error(f'{etiket} REDDEDILDI (MAV_RESULT={kod})')

    # =================================================================
    # MOD DEGISTIRME  (SetMode servisi)
    # =================================================================
    def set_offboard_mode(self) -> None:
        """OFFBOARD moduna gecer (bizim setpoint akisimizi takip et)."""
        self._call_set_mode(_MODE_OFFBOARD)

    def set_auto_loiter_mode(self) -> None:
        """AUTO.LOITER moduna gecer (havada sabit bekle)."""
        self._call_set_mode(_MODE_AUTO_LOITER)

    def _call_set_mode(self, custom_mode: str) -> None:
        """set_mode servisini bloklamadan cagirir.

        Args:
            custom_mode (str): PX4 mod string'i, orn. 'OFFBOARD'.
        """
        if not self._mode_client.service_is_ready():
            self._node.get_logger().warning(
                f'set_mode servisi hazir degil (mod: {custom_mode})'
            )
            return
        req = SetMode.Request()
        req.base_mode = 0
        req.custom_mode = custom_mode
        future = self._mode_client.call_async(req)
        future.add_done_callback(
            lambda f: self._servis_sonucu(f, f'MOD({custom_mode})')
        )

    # =================================================================
    # INIS / EVE DONUS  (PX4 AUTO modlari uzerinden)
    # =================================================================
    def takeoff(self, altitude_m: float = 10.0) -> None:
        """Kalkis. Offboard akisinda kalkis, irtifa setpoint'i ile yapilir;
        bu metot arayuz butunlugu icin durur (px4_bridge offboard tirmanis
        kullanir). AUTO.TAKEOFF gerekirse ileride eklenecek.

        Args:
            altitude_m (float): Hedef irtifa, metre (su an kullanilmiyor).
        """
        self._node.get_logger().info(
            'takeoff: offboard irtifa setpoint yolu kullaniliyor '
            f'(hedef {altitude_m:.1f} m)'
        )

    def land(self) -> None:
        """AUTO.LAND moduna gecer (bulundugu konumda in)."""
        self._call_set_mode(_MODE_AUTO_LAND)

    def return_home(self) -> None:
        """AUTO.RTL moduna gecer (home'a don)."""
        self._call_set_mode(_MODE_AUTO_RTL)

    # =================================================================
    # HOME YAZMA  (CommandHome servisi)
    # =================================================================
    def set_home(
        self,
        lat: float | None = None,
        lon: float | None = None,
        alt_amsl: float | None = None,
        yaw_deg: float = 0.0,
    ) -> None:
        """PX4'un HOME kaydini yeniden yazar (MAV_CMD_DO_SET_HOME).

        NEDEN VAR: 26 Agustos 2026'da RTL uc ucagi da yanlis home'lara
        goturdu (P0). O gune kadar home'u DUZELTMENIN hicbir yolu yoktu —
        yalnizca okunuyordu. Denetimi home_dogrulama.py yapar; duzeltmeyi
        bu metot yapar.

        🔴 BU METOT KENDILIGINDEN CAGRILMAZ. Ne px4_bridge ne baska bir
        dugum otomatik home yazar. Sebep: home'u HAVADA degistirmek RTL'in
        hedefini ucus ortasinda kaydirir — cozmeye calistigimiz hatanin
        daha kotusunu uretir. Cagri YERDE, operator karariyla yapilir
        (deploy/rpi/teshis/home_denetle.py --duzelt).

        ⚠️ ACIK lat/lon KULLANMA — SESSIZ YUVARLAMA VAR. CommandHome.srv'de
        latitude/longitude alanlari **float32**; Python tarafinda atama
        kirpmiyor, kirpma SERILESTIRMEDE oluyor ve hicbir uyari cikmiyor.
        Olculdu (1 Eylul 2026, rclpy serialize/deserialize round-trip):
            38.6906287, 39.1611271 -> 38.6906281, 39.1611290  = 0.180 m
        float32'nin bu enlemdeki adimi 0.42 m, yani en kotu ~0.3 m hata.
        Toleransimizin (1.0 m) altinda ama home'u "tam su noktaya yaz"
        diye cagiran biri bunu bilmeli. `current_gps=True` yolu bu
        yuvarlamadan TAMAMEN kacinir: koordinat tel uzerinden hic gecmez,
        PX4 kendi ic konumunu kullanir. VARSAYILAN yol odur.

        Args:
            lat (float | None): Home enlemi. None ise ucagin ANLIK GPS
                konumu kullanilir (current_gps=True).
            lon (float | None): Home boylami. lat None ise yok sayilir.
            alt_amsl (float | None): Home AMSL yuksekligi, metre.
            yaw_deg (float): Home yaw'i, derece. PX4 bunu yalnizca
                bilgi olarak tutar; RTL yonunu etkilemez.
        """
        if not self._home_client.service_is_ready():
            self._node.get_logger().warning(
                'set_home servisi hazir degil (mavros baglandi mi?)'
            )
            return
        req = CommandHome.Request()
        anlik = lat is None or lon is None
        req.current_gps = anlik
        req.yaw = float(yaw_deg)
        if not anlik:
            req.latitude = float(lat)
            req.longitude = float(lon)
            req.altitude = float(alt_amsl if alt_amsl is not None else 0.0)
            # Yuvarlamayi SESSIZ birakma (bkz. docstring): cagiran taraf
            # "tam su nokta" sanmasin, ~0.2-0.3 m kayabilecegini gorsun.
            self._node.get_logger().warning(
                'set_home ACIK koordinatla cagrildi — CommandHome float32 '
                'oldugu icin hedef ~0.2-0.3 m kayabilir (olculdu: 0.180 m). '
                'Mumkunse current_gps yolunu kullan.'
            )
        etiket = ('SET_HOME(anlik GPS)' if anlik
                  else f'SET_HOME({lat:.7f},{lon:.7f})')
        future = self._home_client.call_async(req)
        future.add_done_callback(
            lambda f: self._servis_sonucu(f, etiket)
        )

    # =================================================================
    # OFFBOARD MOD BILDIRIMLERI
    # MAVROS'ta ayri bir OffboardControlMode mesaji YOKTUR; kontrol turu
    # (pozisyon/hiz) dogrudan PositionTarget.type_mask ile belirlenir.
    # Bu yuzden asagidaki metotlar NO-OP'tur (px4_bridge arayuz uyumu icin
    # cagirir); gercek maske publish_*_setpoint icinde secilir. Offboard
    # "heartbeat", setpoint'i >2 Hz yayinlamanin kendisidir.
    # =================================================================
    def publish_offboard_position_mode(self) -> None:
        """No-op (maske publish_position_setpoint icinde secilir)."""
        return

    def publish_offboard_velocity_mode(self) -> None:
        """No-op (maske publish_velocity_setpoint icinde secilir)."""
        return

    def publish_offboard_position_velocity_mode(self) -> None:
        """No-op (maske publish_position_velocity_setpoint icinde secilir)."""
        return

    # =================================================================
    # SETPOINT YAYINI  (PositionTarget, NED -> ENU cevirisi burada)
    # =================================================================
    def _make_target(self, mask: int) -> PositionTarget:
        """Ortak PositionTarget iskeleti (zaman damgasi + cerceve + maske).

        Args:
            mask (int): type_mask (IGNORE_* bitleri).

        Returns:
            PositionTarget: doldurulmaya hazir mesaj.
        """
        msg = PositionTarget()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        # FRAME_LOCAL_NED: MAVROS ENU girdiyi PX4 NED'ine cevirir.
        msg.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
        msg.type_mask = mask
        return msg

    def publish_position_setpoint(
        self, x: float, y: float, z: float, yaw_rad: float = 0.0
    ) -> None:
        """Hedef pozisyon (NED girdi) + yaw yayinlar.

        Args:
            x (float): NED X (Kuzey), metre.
            y (float): NED Y (Dogu), metre.
            z (float): NED Z (Asagi pozitif), metre.
            yaw_rad (float): NED yaw, radyan.
        """
        e_x, e_y, e_z = _ned_to_enu(x, y, z)
        msg = self._make_target(_MASK_POSITION)
        msg.position.x = e_x
        msg.position.y = e_y
        msg.position.z = e_z
        msg.yaw = _yaw_ned_to_enu(yaw_rad)
        self._setpoint_pub.publish(msg)

    def publish_velocity_setpoint(
        self, vx: float, vy: float, vz: float, yaw_rad: float = 0.0
    ) -> None:
        """Saf hiz setpoint'i (NED girdi) + yaw yayinlar.

        Args:
            vx (float): NED X hizi (Kuzey), m/s.
            vy (float): NED Y hizi (Dogu), m/s.
            vz (float): NED Z hizi (Asagi pozitif), m/s.
            yaw_rad (float): NED yaw, radyan.
        """
        e_vx, e_vy, e_vz = _ned_to_enu(vx, vy, vz)
        msg = self._make_target(_MASK_VELOCITY)
        msg.velocity.x = e_vx
        msg.velocity.y = e_vy
        msg.velocity.z = e_vz
        msg.yaw = _yaw_ned_to_enu(yaw_rad)
        self._setpoint_pub.publish(msg)

    def publish_position_velocity_setpoint(
        self,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
        yaw_rad: float = 0.0,
        ax: float | None = None,
        ay: float | None = None,
        az: float | None = None,
    ) -> None:
        """Pozisyon + hiz (+ istege bagli IVME) feedforward + yaw yayinlar.

        Args:
            x (float): NED X (Kuzey), metre.
            y (float): NED Y (Dogu), metre.
            z (float): NED Z (Asagi pozitif), metre.
            vx (float): NED X hizi, m/s.
            vy (float): NED Y hizi, m/s.
            vz (float): NED Z hizi, m/s.
            yaw_rad (float): NED yaw, radyan.
            ax, ay, az (float | None): NED ivme ileri-beslemesi, m/s^2.
                Ucu de verilirse IGNORE_AF* bitleri kalkar ve PX4 ivmeyi
                ileri-besleme olarak kullanir. None ise eski davranis.
        """
        ivme_var = ax is not None and ay is not None and az is not None
        e_x, e_y, e_z = _ned_to_enu(x, y, z)
        e_vx, e_vy, e_vz = _ned_to_enu(vx, vy, vz)
        msg = self._make_target(
            _MASK_POS_VEL_ACC if ivme_var else _MASK_POS_VEL)
        msg.position.x = e_x
        msg.position.y = e_y
        msg.position.z = e_z
        msg.velocity.x = e_vx
        msg.velocity.y = e_vy
        msg.velocity.z = e_vz
        if ivme_var:
            # Ivme de bir VEKTOR — konum/hizla ayni NED->ENU donusumu.
            # (Isaret hatasi burada frenlemesi gereken ucagi hizlandirirdi.)
            e_ax, e_ay, e_az = _ned_to_enu(ax, ay, az)
            msg.acceleration_or_force.x = e_ax
            msg.acceleration_or_force.y = e_ay
            msg.acceleration_or_force.z = e_az
        msg.yaw = _yaw_ned_to_enu(yaw_rad)
        self._setpoint_pub.publish(msg)

    def publish_kalkis_setpoint(self, z: float, yaw_rad: float = 0.0) -> None:
        """KALKIS setpoint'i: yatayda hiz SIFIR, dikeyde hedef irtifa.

        Yatay konum GONDERILMEZ (bkz. _MASK_KALKIS). Ilk tirmanista konum
        tutmanin neden devirdigi orada anlatiliyor.

        Args:
            z (float): NED Z hedefi (Asagi pozitif), metre.
            yaw_rad (float): NED yaw, radyan.
        """
        _, _, e_z = _ned_to_enu(0.0, 0.0, z)
        msg = self._make_target(_MASK_KALKIS)
        msg.position.z = e_z
        msg.velocity.x = 0.0
        msg.velocity.y = 0.0
        msg.yaw = _yaw_ned_to_enu(yaw_rad)
        self._setpoint_pub.publish(msg)

    # =================================================================
    # ORTAK NED ORIGIN
    # =================================================================
    def set_gps_global_origin(
        self, lat_deg: float, lon_deg: float, alt_amsl_m: float
    ) -> None:
        """Tum suru icin ortak NED origin'i MAVROS uzerinden bildirir.

        GeoPointStamped, /mavros/global_position/set_gp_origin'e yayinlanir;
        MAVROS bunu SET_GPS_GLOBAL_ORIGIN MAVLink mesajina cevirir.

        Args:
            lat_deg (float): Enlem, derece.
            lon_deg (float): Boylam, derece.
            alt_amsl_m (float): AMSL irtifa, metre.
        """
        msg = GeoPointStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.position.latitude = lat_deg
        msg.position.longitude = lon_deg
        msg.position.altitude = alt_amsl_m
        self._origin_pub.publish(msg)
