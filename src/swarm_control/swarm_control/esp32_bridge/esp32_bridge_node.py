"""esp32_bridge.py — ESP32 mesh ↔ ROS2 köprüsü (ana node).

Gerçek donanımda network_proxy'nin yerini alır: komşu drone'lardan
ESP-NOW mesh üzerinden gelip ESP32'nin UART'a yazdığı paketleri çözer,
ROS2 topic'lerine yayınlar. Ters yönde, bu drone'dan çıkması gereken
mesajları (origin, kendi pozisyonu) ESP32'ye UART üzerinden gönderir.

UART protokolü (firmware ile AYNI):
    [tip][iha_id][payload 16B][crc16 2B] -> COBS encode -> 0x00 ayraç

İŞLEYİŞ:
1. Arka plan thread'i seri porttan okur, 0x00'da çerçeve keser,
   COBS çözer, CRC doğrular, tipe göre parse eder.
2. Komşu TIP_POSE / TIP_DURUM -> AgentStatus cache güncellenir ve
   /swarm/public/drone{id}/status'a yayınlanır.
3. TIP_ORIGIN -> /swarm/public/origin'e SwarmOrigin yayınlanır.
4. Abonelikler (RPi -> ESP32): /swarm/internal/origin ve kendi
   telemetri topic'i UART'a yazılır.

KULLANIM:
    ros2 run swarm_control esp32_bridge --ros-args \\
        -p agent_id:=1 -p serial_port:=/dev/ttyUSB0
"""

import threading

import rclpy
import serial
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    LeaderHeartbeat,
    SwarmControlCommand,
    SwarmOrigin,
    SystemEvent,
)

from . import packet_parser as pp
from .cobs import cobs_decode, cobs_encode
from .crc16 import crc16

# Mesh telemetrisi için BEST_EFFORT — kayıp paket tolere edilir
_MESH_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# Origin için RELIABLE + TRANSIENT_LOCAL — geç katılan da son değeri alır
_ORIGIN_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

# LeaderHeartbeat: RELIABLE + VOLATILE, depth=5 (contract madde 3.1)
_HEARTBEAT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

# ElectionResult: RELIABLE + TRANSIENT_LOCAL, depth=10 (geç gelen alır)
_ELECTION_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# SystemEvent: RELIABLE, event tabanlı
_EVENT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_FRAME_DELIM = 0x00

# Firmware durum_veri_t.durum -> AgentStatus.state eşleşmesi.
# ORCA/APF, state 7/8/13/14 olan komşuları avoidance hesabından çıkarır
# (INTERFACE_CONTRACT madde 8). DURUM_AYRILDI -> STATE_DETACHED kritik:
# AYRILDI/INDI olan drone'a çarpışma önleme yapılmamalı, aksi halde
# şartname madde 13 ihlali ve -20*N çarpışma cezası riski oluşur.
_DURUM_AKTIF = 1
_DURUM_AYRILDI = 2
_DURUM_INDI = 3
_DURUM_STATE_MAP = {
    _DURUM_AKTIF: AgentStatus.STATE_IN_SWARM,    # 5
    _DURUM_AYRILDI: AgentStatus.STATE_DETACHED,  # 7
    _DURUM_INDI: AgentStatus.STATE_LANDED,       # 13
}


def _kirp_int16(deger: float) -> int:
    """float değeri int16 aralığına (-32768..32767) kırpıp tamsayı döner."""
    return max(-32768, min(32767, int(deger)))


class Esp32BridgeNode(Node):
    """ESP32 mesh ↔ ROS2 köprü node'u."""

    def __init__(self) -> None:
        super().__init__('esp32_bridge')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)
        self._agent_id = int(self.get_parameter('agent_id').value)
        port = str(self.get_parameter('serial_port').value)
        baud = int(self.get_parameter('baud').value)

        # Komşu drone başına AgentStatus cache'i (POSE + DURUM birleşir)
        self._komsu_durum: dict[int, AgentStatus] = {}
        self._cache_lock = threading.Lock()

        # Komşu status yayıncıları drone_id'ye göre tembel oluşturulur
        self._status_pubs: dict[int, object] = {}

        self._origin_pub = self.create_publisher(
            SwarmOrigin, '/swarm/public/origin', _ORIGIN_QOS
        )
        self._control_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/public/control/command',
            _MESH_QOS,
        )
        self._leader_hb_pub = self.create_publisher(
            LeaderHeartbeat,
            '/swarm/public/leader/heartbeat',
            _HEARTBEAT_QOS,
        )
        self._election_pub = self.create_publisher(
            ElectionResult,
            '/swarm/public/election/result',
            _ELECTION_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/public/events/system',
            _EVENT_QOS,
        )

        # Seri portu aç
        try:
            self._ser = serial.Serial(port, baud, timeout=0.1)
            self.get_logger().info(f'Seri port açıldı: {port} @ {baud}')
        except serial.SerialException as exc:
            self.get_logger().error(f'Seri port açılamadı: {exc}')
            raise

        # RPi -> ESP32: kendi RTK konumunu mesh'e yaymak için
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_own_telemetry,
            _MESH_QOS,
        )

        # RPi -> ESP32: lider origin yayınını mesh'e iletmek için
        self.create_subscription(
            SwarmOrigin,
            '/swarm/internal/origin',
            self._on_origin_out,
            _ORIGIN_QOS,
        )

        # RPi -> ESP32: joystick komutu (Görev 2) mesh'e iletilecek
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            self._on_control_out,
            _MESH_QOS,
        )

        # RPi -> ESP32: lider kalp atışı (yalnızca aktif lider yayınlar)
        self.create_subscription(
            LeaderHeartbeat,
            '/swarm/internal/leader/heartbeat',
            self._on_leader_hb_out,
            _HEARTBEAT_QOS,
        )

        # RPi -> ESP32: lider seçim sonucu (yeni lider yayınlar)
        self.create_subscription(
            ElectionResult,
            '/swarm/internal/election/result',
            self._on_election_out,
            _ELECTION_QOS,
        )

        # Seri okuma thread'i
        self._calisiyor = True
        self._okuma_thread = threading.Thread(
            target=self._seri_oku_dongusu, daemon=True
        )
        self._okuma_thread.start()

        self.get_logger().info(
            f'Esp32BridgeNode başlatıldı: agent_id={self._agent_id}'
        )

    # =================================================================
    # SERİ OKUMA (arka plan thread)
    # =================================================================
    def _seri_oku_dongusu(self) -> None:
        """Seri porttan sürekli okur, 0x00'da çerçeve keser ve işler."""
        tampon = bytearray()
        while self._calisiyor:
            try:
                veri = self._ser.read(64)
            except serial.SerialException as exc:
                self.get_logger().error(f'Seri okuma hatası: {exc}')
                return

            for byte in veri:
                if byte == _FRAME_DELIM:
                    if tampon:
                        self._cerceve_isle(bytes(tampon))
                        tampon.clear()
                else:
                    tampon.append(byte)
                    if len(tampon) > 64:  # taşma koruması
                        tampon.clear()

    def _cerceve_isle(self, ham: bytes) -> None:
        """Bir COBS çerçevesini çözer, doğrular ve tipe göre yayınlar.

        Args:
            ham (bytes): 0x00 ayracı hariç tek bir COBS çerçevesi.
        """
        decoded = cobs_decode(ham)
        cerceve = pp.cerceve_coz(decoded)
        if cerceve is None:
            return  # CRC hatası veya eksik veri — sessizce at

        # Defansif: firmware kendi paketlerini ISR'da filtreler ama
        # bir hata olur da kendi paketimiz geri gelirse komşu yayını
        # yapmayalım (kendi pose'umuz px4_bridge'den geliyor).
        if cerceve.iha_id == 0 or cerceve.iha_id == self._agent_id:
            return

        if cerceve.tip == pp.TIP_POSE:
            self._isle_pose(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_DURUM:
            self._isle_durum(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_ORIGIN:
            self._isle_origin(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_KOMUT:
            self._isle_komut(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_LEADER_HB:
            self._isle_leader_hb(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_ELECTION:
            self._isle_election(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_RENK:
            self._isle_renk(cerceve.iha_id, cerceve.payload)
        # TIP_GOREV: QR çözümleme qr_detector'da yapılır; mesh üzerinden
        # taşınmasına şu an gerek yok (TODO: takım kararı).

    # =================================================================
    # MESH -> ROS2 İŞLEYİCİLERİ
    # =================================================================
    def _komsu_status_al(self, drone_id: int) -> AgentStatus:
        """Komşu için cache'teki AgentStatus'u döner, yoksa oluşturur."""
        status = self._komsu_durum.get(drone_id)
        if status is None:
            status = AgentStatus()
            status.agent_id = drone_id
            self._komsu_durum[drone_id] = status
        return status

    def _isle_pose(self, drone_id: int, payload: bytes) -> None:
        """TIP_POSE -> komşu AgentStatus konum alanlarını günceller."""
        pose = pp.pose_coz(payload)
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            status.lat_deg = pose.lat / 1e7
            status.lon_deg = pose.lon / 1e7
            status.alt_amsl_m = pose.alt_cm / 100.0
            status.heading_deg = pose.heading / 10.0
            status.vel_x = pose.vx / 100.0
            status.vel_y = pose.vy / 100.0
            self._yayinla_status(drone_id, status)

    def _isle_durum(self, drone_id: int, payload: bytes) -> None:
        """TIP_DURUM -> komşu AgentStatus sağlık alanlarını günceller.

        Firmware'in 3 seviyeli durum'u (AKTIF/AYRILDI/INDI) AgentStatus
        FSM state'ine eşleştirilir. ORCA/APF için kritik: AYRILDI/INDI
        olan komşulara avoidance hesabı yapılmamalı.
        """
        durum = pp.durum_coz(payload)
        # Bilinmeyen durum kodları STATE_UNKNOWN (0) olarak bırakılır;
        # contract gereği UNKNOWN, "aktif gibi davran" anlamına gelir.
        state = _DURUM_STATE_MAP.get(durum.durum, AgentStatus.STATE_UNKNOWN)
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            status.state = state
            status.armed = bool(durum.armed)
            status.gps_fix_type = durum.gps_fix_type
            status.battery_percent = float(durum.battery_pct)
            status.battery_voltage_v = durum.battery_volt
            status.estimator_ok = bool(durum.ekf_ok)
            status.imu_healthy = bool(durum.imu_ok)
            status.mag_healthy = bool(durum.mag_ok)
            status.baro_healthy = bool(durum.baro_ok)
            status.status_text = f'mesh durum={durum.durum} rssi={durum.rssi}'
            self._yayinla_status(drone_id, status)

    def _yayinla_status(self, drone_id: int, status: AgentStatus) -> None:
        """Komşu AgentStatus'u /swarm/public/drone{id}/status'a yayınlar.

        Not: _cache_lock tutulurken çağrılır.
        """
        status.stamp = self.get_clock().now().to_msg()
        pub = self._status_pubs.get(drone_id)
        if pub is None:
            pub = self.create_publisher(
                AgentStatus,
                f'/swarm/public/drone{drone_id}/status',
                _MESH_QOS,
            )
            self._status_pubs[drone_id] = pub
        pub.publish(status)

    def _isle_origin(self, leader_id: int, payload: bytes) -> None:
        """TIP_ORIGIN -> /swarm/public/origin'e SwarmOrigin yayınlar."""
        origin = pp.origin_coz(payload)
        msg = SwarmOrigin()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_agent_id = leader_id
        msg.origin_lat_deg = origin.lat_1e7 / 1e7
        msg.origin_lon_deg = origin.lon_1e7 / 1e7
        msg.origin_alt_amsl_m = origin.alt_mm / 1000.0
        msg.valid = True
        msg.sequence = origin.sequence
        self._origin_pub.publish(msg)

    def _isle_komut(self, source_id: int, payload: bytes) -> None:
        """TIP_KOMUT -> /swarm/public/control/command'a SwarmControlCommand.

        Joystick float32 değerleri int16*100 ile taşındığı için 100'e
        bölünerek geri çevrilir.
        """
        k = pp.komut_coz(payload)
        msg = SwarmControlCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.mode = k.alt_tip
        msg.roll_cmd = k.roll_x100 / 100.0
        msg.pitch_cmd = k.pitch_x100 / 100.0
        msg.yaw_cmd = k.yaw_x100 / 100.0
        msg.throttle_cmd = k.throttle_x100 / 100.0
        msg.takeoff = bool(k.flags & pp.KOMUT_FLAG_TAKEOFF)
        msg.land = bool(k.flags & pp.KOMUT_FLAG_LAND)
        msg.rtl = bool(k.flags & pp.KOMUT_FLAG_RTL)
        msg.emergency_stop = bool(k.flags & pp.KOMUT_FLAG_EMERGENCY)
        msg.formation_change_requested = bool(
            k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE
        )
        msg.command_valid = True
        msg.source_module = f'esp32_bridge_from_agent_{source_id}'
        self._control_pub.publish(msg)

    def _isle_leader_hb(self, source_id: int, payload: bytes) -> None:
        """TIP_LEADER_HB -> /swarm/public/leader/heartbeat'e yayın."""
        hb = pp.leader_hb_coz(payload)
        msg = LeaderHeartbeat()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_id = hb.leader_id
        msg.sequence_num = hb.sequence_num
        msg.election_round = hb.election_round
        msg.active_agent_count = hb.active_agent_count
        msg.mission_active = bool(hb.mission_active)
        self._leader_hb_pub.publish(msg)

    def _isle_election(self, source_id: int, payload: bytes) -> None:
        """TIP_ELECTION -> /swarm/public/election/result'a yayın."""
        e = pp.election_coz(payload)
        msg = ElectionResult()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = e.sequence_num
        msg.new_leader_id = e.new_leader_id
        msg.election_round = e.election_round
        msg.triggered_by_agent_id = e.triggered_by
        msg.reason = e.reason
        # 0 dolgu ID'lerini at — gerçekte onay verenler bunlar
        msg.confirmed_by_agent_ids = [
            i for i in e.confirmed_ids if i != 0
        ]
        self._election_pub.publish(msg)

    def _isle_renk(self, source_id: int, payload: bytes) -> None:
        """TIP_RENK -> SystemEvent.EVENT_COLOR_ZONE_DETECTED olarak yayın.

        Mesh üzerinden komşulardan gelen renk bölgesi tespitleri sürünün
        ortak hafızasına SystemEvent olarak yayımlanır. GPS koordinatları
        1e-7 derece tamsayı olduğu için NED pos_x/y'ye konmaz; mesaj
        string'inde taşınır.
        """
        r = pp.renk_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_COLOR_ZONE_DETECTED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(r.renk)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = f'renk={r.renk} lat_1e7={r.lat} lon_1e7={r.lon}'
        self._event_pub.publish(msg)

    # =================================================================
    # ROS2 -> MESH İŞLEYİCİLERİ (UART'a yaz)
    # =================================================================
    def _uart_yaz(self, tip: int, iha_id: int, payload: bytes) -> None:
        """Bir paketi çerçeveleyip (CRC+COBS) seri porta yazar.

        Args:
            tip (int): Paket tipi (TIP_*).
            iha_id (int): Kaynak drone kimliği.
            payload (bytes): 16 baytlık payload.
        """
        if len(payload) != 16:
            self.get_logger().warning('UART payload 16 byte değil, atlandı')
            return
        govde = bytes([tip, iha_id]) + payload
        crc = crc16(govde)
        cerceve = govde + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        try:
            self._ser.write(cobs_encode(cerceve))
        except serial.SerialException as exc:
            self.get_logger().error(f'Seri yazma hatası: {exc}')

    def _on_own_telemetry(self, msg: AgentStatus) -> None:
        """Kendi telemetrisini TIP_POSE olarak ESP32'ye gönderir."""
        payload = pp.pose_paketle(
            lat=int(msg.lat_deg * 1e7),
            lon=int(msg.lon_deg * 1e7),
            alt_cm=int(msg.alt_amsl_m * 100.0),
            heading=int(msg.heading_deg * 10.0),
            vx=int(msg.vel_x * 100.0),
            vy=int(msg.vel_y * 100.0),
        )
        self._uart_yaz(pp.TIP_POSE, self._agent_id, payload)

    def _on_origin_out(self, msg: SwarmOrigin) -> None:
        """Lider origin'ini TIP_ORIGIN olarak ESP32'ye gönderir."""
        payload = pp.origin_paketle(
            lat_1e7=int(msg.origin_lat_deg * 1e7),
            lon_1e7=int(msg.origin_lon_deg * 1e7),
            alt_mm=int(msg.origin_alt_amsl_m * 1000.0),
            sequence=msg.sequence,
        )
        self._uart_yaz(pp.TIP_ORIGIN, self._agent_id, payload)

    def _on_control_out(self, msg: SwarmControlCommand) -> None:
        """SwarmControlCommand'ı TIP_KOMUT olarak ESP32'ye gönderir.

        Görev 2 joystick akışı: int16 ölçeklemesi sınırı dışına çıkan
        değerler kırpılır.
        """
        flags = 0
        if msg.takeoff:
            flags |= pp.KOMUT_FLAG_TAKEOFF
        if msg.land:
            flags |= pp.KOMUT_FLAG_LAND
        if msg.rtl:
            flags |= pp.KOMUT_FLAG_RTL
        if msg.emergency_stop:
            flags |= pp.KOMUT_FLAG_EMERGENCY
        if msg.formation_change_requested:
            flags |= pp.KOMUT_FLAG_FORMATION_CHANGE

        payload = pp.komut_paketle(
            alt_tip=msg.mode,
            flags=flags,
            roll_x100=_kirp_int16(msg.roll_cmd * 100.0),
            pitch_x100=_kirp_int16(msg.pitch_cmd * 100.0),
            yaw_x100=_kirp_int16(msg.yaw_cmd * 100.0),
            throttle_x100=_kirp_int16(msg.throttle_cmd * 100.0),
        )
        self._uart_yaz(pp.TIP_KOMUT, self._agent_id, payload)

    def _on_leader_hb_out(self, msg: LeaderHeartbeat) -> None:
        """LeaderHeartbeat'i TIP_LEADER_HB olarak ESP32'ye gönderir."""
        payload = pp.leader_hb_paketle(
            leader_id=msg.leader_id,
            sequence_num=msg.sequence_num,
            election_round=msg.election_round,
            active_agent_count=msg.active_agent_count,
            mission_active=1 if msg.mission_active else 0,
        )
        self._uart_yaz(pp.TIP_LEADER_HB, self._agent_id, payload)

    def _on_election_out(self, msg: ElectionResult) -> None:
        """ElectionResult'ı TIP_ELECTION olarak ESP32'ye gönderir."""
        payload = pp.election_paketle(
            new_leader_id=msg.new_leader_id,
            election_round=msg.election_round,
            reason=msg.reason,
            triggered_by=msg.triggered_by_agent_id,
            sequence_num=msg.sequence_num,
            confirmed_ids=tuple(msg.confirmed_by_agent_ids),
        )
        self._uart_yaz(pp.TIP_ELECTION, self._agent_id, payload)

    # =================================================================
    # KAPANIŞ
    # =================================================================
    def destroy_node(self) -> bool:
        """Thread'i durdurur ve seri portu kapatır."""
        self._calisiyor = False
        if self._okuma_thread.is_alive():
            self._okuma_thread.join(timeout=1.0)
        if self._ser.is_open:
            self._ser.close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Esp32BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
