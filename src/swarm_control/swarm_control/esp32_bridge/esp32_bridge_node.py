"""ESP32 mesh ile ROS2 arasinda UART koprusu kuran dugum.

ESP32'den gelen paketleri cozer, dogrular ve ROS2 topic'lerine yazar.
ROS2'den cikan mesajlari ise paketleyip ESP32 UART hattina yazar.
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

import serial

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

_MESH_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_ORIGIN_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

_HEARTBEAT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

_ELECTION_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_EVENT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_FRAME_DELIM = 0x00

_DURUM_BILINMIYOR = 0
_DURUM_BOSTA = 1
_DURUM_KALKIS = 2
_DURUM_SURUDE = 3
_DURUM_GOREV = 4
_DURUM_AYRILDI = 5
_DURUM_HASSAS_INIS = 6
_DURUM_KATILMA = 7
_DURUM_BEKLIYOR = 8
_DURUM_RTL = 9
_DURUM_INIS = 10
_DURUM_INDI = 11
_DURUM_FAILSAFE = 12
_DURUM_STANDBY = 13

_DURUM_STATE_MAP = {
    _DURUM_BILINMIYOR:  AgentStatus.STATE_UNKNOWN,
    _DURUM_BOSTA:       AgentStatus.STATE_IDLE,
    _DURUM_KALKIS:      AgentStatus.STATE_TAKEOFF,
    _DURUM_SURUDE:      AgentStatus.STATE_IN_SWARM,
    _DURUM_GOREV:       AgentStatus.STATE_EXECUTING_TASK,
    _DURUM_AYRILDI:     AgentStatus.STATE_DETACHED,
    _DURUM_HASSAS_INIS: AgentStatus.STATE_PRECISION_LANDING,
    _DURUM_KATILMA:     AgentStatus.STATE_REJOINING,
    _DURUM_BEKLIYOR:    AgentStatus.STATE_WAITING_REJOIN,
    _DURUM_RTL:         AgentStatus.STATE_RETURN_HOME,
    _DURUM_INIS:        AgentStatus.STATE_LANDING,
    _DURUM_INDI:        AgentStatus.STATE_LANDED,
    _DURUM_FAILSAFE:    AgentStatus.STATE_FAILSAFE,
    _DURUM_STANDBY:     AgentStatus.STATE_STANDBY,
}

_STATE_DURUM_MAP = {
    AgentStatus.STATE_UNKNOWN:           _DURUM_BILINMIYOR,
    AgentStatus.STATE_IDLE:              _DURUM_BOSTA,
    AgentStatus.STATE_ARMING:            _DURUM_KALKIS,
    AgentStatus.STATE_ARMED:             _DURUM_KALKIS,
    AgentStatus.STATE_TAKEOFF:           _DURUM_KALKIS,
    AgentStatus.STATE_IN_SWARM:          _DURUM_SURUDE,
    AgentStatus.STATE_EXECUTING_TASK:    _DURUM_GOREV,
    AgentStatus.STATE_DETACHED:          _DURUM_AYRILDI,
    AgentStatus.STATE_PRECISION_LANDING: _DURUM_HASSAS_INIS,
    AgentStatus.STATE_WAITING_REJOIN:    _DURUM_BEKLIYOR,
    AgentStatus.STATE_REJOINING:         _DURUM_KATILMA,
    AgentStatus.STATE_RETURN_HOME:       _DURUM_RTL,
    AgentStatus.STATE_LANDING:           _DURUM_INIS,
    AgentStatus.STATE_LANDED:            _DURUM_INDI,
    AgentStatus.STATE_FAILSAFE:          _DURUM_FAILSAFE,
    AgentStatus.STATE_STANDBY:           _DURUM_STANDBY,
}


def _kirp_int16(deger: float) -> int:
    """Float degeri int16 sinirlarina kirpar."""
    return max(-32768, min(32767, int(deger)))


class Esp32BridgeNode(Node):
    """ESP32 UART kopru dugumu."""

    def __init__(self) -> None:
        super().__init__('esp32_bridge')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)

        self._agent_id = int(
            self.get_parameter('agent_id').value
        )
        port = str(self.get_parameter('serial_port').value)
        baud = int(self.get_parameter('baud').value)

        if not 1 <= self._agent_id <= 254:
            raise ValueError(
                f'agent_id 1-254 arasi olmali: '
                f'{self._agent_id}'
            )

        if baud not in (
            9600, 19200, 38400, 57600, 115200, 230400, 460800
        ):
            self.get_logger().warning(
                f'Olagandisi baud: {baud}'
            )

        self._komsu_durum: dict[int, AgentStatus] = {}
        self._cache_lock = threading.Lock()
        self._status_pubs: dict[int, object] = {}

        self._alim_ok = 0
        self._crc_fail = 0
        self._gonderim_ok = 0
        self._gonderim_drop = 0
        self._komut_rx_seq = 0
        self._id_uyumsuz = 0
        self._son_origin: SwarmOrigin | None = None
        self._METRE_PER_DERECE_LAT = 111_320.0
        self._son_alim_ts = 0.0
        self._komsu_son_goruldu: dict[int, float] = {}

        self._son_pose_gonderim_ts = 0.0
        self._pose_periyot_s = 0.1
        self._son_durum_gonderim_ts = 0.0
        self._durum_periyot_s = 1.0

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
        self._event_pub_internal = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _EVENT_QOS,
        )
        self._event_pub_public = self.create_publisher(
            SystemEvent,
            '/swarm/public/events/system',
            _EVENT_QOS,
        )

        self._port = port
        self._baud = baud
        self._ser_lock = threading.Lock()
        self._ser: serial.Serial | None = None
        self._seri_ac()

        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._agent_id}/status',
            self._on_own_status,
            _MESH_QOS,
        )

        self.create_subscription(
            SwarmOrigin,
            '/swarm/internal/origin',
            self._on_origin_out,
            _ORIGIN_QOS,
        )

        self.create_subscription(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            self._on_control_out,
            _MESH_QOS,
        )

        self.create_subscription(
            LeaderHeartbeat,
            '/swarm/internal/leader/heartbeat',
            self._on_leader_hb_out,
            _HEARTBEAT_QOS,
        )

        self.create_subscription(
            ElectionResult,
            '/swarm/internal/election/result',
            self._on_election_out,
            _ELECTION_QOS,
        )

        self._calisiyor = True
        self._okuma_thread = threading.Thread(
            target=self._seri_oku_dongusu, daemon=True
        )
        self._okuma_thread.start()

        self._diag_timer = self.create_timer(
            1.0, self._diag_yayinla
        )

        self.get_logger().info(
            f'Esp32BridgeNode baslatildi: '
            f'agent_id={self._agent_id}'
        )

    def _diag_yayinla(self) -> None:
        """Saniye basina mesh saglik event'i yayinlar."""
        now = time.monotonic()
        with self._cache_lock:
            komsu_ts = list(
                self._komsu_son_goruldu.values()
            )
        aktif_komsu = sum(
            1 for ts in komsu_ts if now - ts < 5.0
        )
        son_alim_yas = (
            now - self._son_alim_ts
            if self._son_alim_ts > 0 else -1.0
        )
        link_ok = (
            self._ser is not None and self._ser.is_open
            and 0 <= son_alim_yas < 2.0
        )

        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_UNKNOWN
        msg.severity = (
            SystemEvent.SEVERITY_INFO if link_ok
            else SystemEvent.SEVERITY_WARNING
        )
        msg.source_agent_id = self._agent_id
        msg.source_module = 'esp32_bridge'
        msg.value = float(aktif_komsu)
        msg.has_position = False
        msg.message = (
            f'mesh_diag link_ok={int(link_ok)} '
            f'komsu={aktif_komsu} alim_ok={self._alim_ok} '
            f'crc_fail={self._crc_fail} '
            f'gonderim_ok={self._gonderim_ok} '
            f'gonderim_drop={self._gonderim_drop} '
            f'id_uyumsuz={self._id_uyumsuz} '
            f'son_alim_yas_s={son_alim_yas:.2f}'
        )
        self._event_pub_internal.publish(msg)

    def _seri_ac(self) -> bool:
        """Seri portu baglantisini acar."""
        with self._ser_lock:
            if self._ser is not None and self._ser.is_open:
                return True
            try:
                self._ser = serial.Serial(
                    self._port, self._baud, timeout=0.1
                )
                self.get_logger().info(
                    f'Seri port acildi: '
                    f'{self._port} @ {self._baud}'
                )
                self._mesh_olay_yayinla(
                    SystemEvent.SEVERITY_INFO,
                    f'mesh link restored ({self._port})',
                )
                return True
            except serial.SerialException as exc:
                self._ser = None
                self.get_logger().error(
                    f'Seri acilamadi ({self._port}): {exc}'
                )
                return False

    def _mesh_olay_yayinla(
        self, severity: int, mesaj: str
    ) -> None:
        """Link durum olaylarini yayinlar."""
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_UNKNOWN
        msg.severity = severity
        msg.source_agent_id = self._agent_id
        msg.source_module = 'esp32_bridge'
        msg.message = mesaj
        msg.value = 0.0
        msg.has_position = False
        self._event_pub_internal.publish(msg)

    def _seri_oku_dongusu(self) -> None:
        """Arka planda UART okumasi yapar."""
        tampon = bytearray()
        while self._calisiyor:
            if self._ser is None or not self._ser.is_open:
                time.sleep(1.0)
                self._seri_ac()
                continue
            try:
                veri = self._ser.read(64)
            except serial.SerialException as exc:
                self.get_logger().warning(
                    f'Seri okuma hatasi, tekrar denenecek: '
                    f'{exc}'
                )
                self._mesh_olay_yayinla(
                    SystemEvent.SEVERITY_WARNING,
                    f'mesh link lost (read): {exc}',
                )
                with self._ser_lock:
                    if self._ser is not None:
                        try:
                            self._ser.close()
                        except Exception:  # noqa: BLE001
                            pass
                    self._ser = None
                tampon.clear()
                continue

            for byte in veri:
                if byte == _FRAME_DELIM:
                    if tampon:
                        self._cerceve_isle(bytes(tampon))
                        tampon.clear()
                else:
                    tampon.append(byte)
                    if len(tampon) > 64:
                        tampon.clear()

    def _cerceve_isle(self, ham: bytes) -> None:
        """Cerceveyi cozer ve tipine gore dagitir."""
        decoded = cobs_decode(ham)
        cerceve = pp.cerceve_coz(decoded)
        if cerceve is None:
            self._crc_fail += 1
            return
        self._alim_ok += 1
        self._son_alim_ts = time.monotonic()
        with self._cache_lock:
            self._komsu_son_goruldu[cerceve.iha_id] = (
                self._son_alim_ts
            )

        if (cerceve.iha_id == 0 or
                cerceve.iha_id == self._agent_id):
            return

        if cerceve.tip == pp.TIP_POSE:
            self._isle_pose(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_DURUM:
            self._isle_durum(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_ORIGIN:
            self._isle_origin(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_KOMUT:
            self._isle_komut(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_LEADER_HB:
            self._isle_leader_hb(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_ELECTION:
            self._isle_election(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_RENK:
            self._isle_renk(
                cerceve.iha_id, cerceve.payload
            )
        elif cerceve.tip == pp.TIP_GOREV:
            self._isle_gorev(
                cerceve.iha_id, cerceve.payload
            )

    def _komsu_status_al(self, drone_id: int) -> AgentStatus:
        """Cache'den komsu statusunu doner veya olusturur."""
        status = self._komsu_durum.get(drone_id)
        if status is None:
            status = AgentStatus()
            status.agent_id = drone_id
            self._komsu_durum[drone_id] = status
        return status

    def _isle_pose(
        self, drone_id: int, payload: bytes
    ) -> None:
        """Konum pakedini cozer ve NED'e donusturur."""
        pose = pp.pose_coz(payload)
        lat_deg = pose.lat / 1e7
        lon_deg = pose.lon / 1e7
        alt_amsl_m = pose.alt_cm / 100.0
        vel_x_ned = pose.vx / 100.0
        vel_y_ned = pose.vy / 100.0
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            status.lat_deg = lat_deg
            status.lon_deg = lon_deg
            status.alt_amsl_m = alt_amsl_m
            status.heading_deg = pose.heading / 10.0
            status.vel_x = vel_x_ned
            status.vel_y = vel_y_ned
            status.vel_z = 0.0
            ned = self._gps_ned_cevir(
                lat_deg, lon_deg, alt_amsl_m
            )
            if ned is not None:
                status.pos_x = ned[0]
                status.pos_y = ned[1]
                status.pos_z = ned[2]
                status.origin_synced = True
                status.xy_valid = True
                status.z_valid = True
                status.v_xy_valid = True
            else:
                status.pos_x = 0.0
                status.pos_y = 0.0
                status.pos_z = 0.0
                status.origin_synced = False
                status.xy_valid = False
                status.z_valid = False
                status.v_xy_valid = False
            self._yayinla_status(drone_id, status)

    def _gps_ned_cevir(
        self, lat_deg: float, lon_deg: float,
        alt_amsl_m: float,
    ) -> tuple[float, float, float] | None:
        """GPS verisini flat-earth yaklasimiyla NED'e cevirir."""
        origin = self._son_origin
        if origin is None:
            return None
        olat = float(origin.origin_lat_deg)
        olon = float(origin.origin_lon_deg)
        oalt = float(origin.origin_alt_amsl_m)
        m_per_deg_lon = (
            self._METRE_PER_DERECE_LAT
            * math.cos(math.radians(olat))
        )
        pos_x = (
            (lat_deg - olat) * self._METRE_PER_DERECE_LAT
        )
        pos_y = (lon_deg - olon) * m_per_deg_lon
        pos_z = oalt - alt_amsl_m
        return (pos_x, pos_y, pos_z)

    def _isle_durum(
        self, drone_id: int, payload: bytes
    ) -> None:
        """Durum pakedini cozer ve status cache'e yazar."""
        durum = pp.durum_coz(payload)
        if durum.drone_id != drone_id:
            self._id_uyumsuz += 1
            self.get_logger().warning(
                f'DURUM ID uyumsuz: header={drone_id} '
                f'payload={durum.drone_id}'
            )
        state = _DURUM_STATE_MAP.get(
            durum.durum, AgentStatus.STATE_UNKNOWN
        )
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
            if hasattr(status, 'mesh_link_ok'):
                status.mesh_link_ok = bool(
                    durum.mesh_link_ok
                )
            if hasattr(status, 'mesh_node_count'):
                status.mesh_node_count = int(
                    durum.mesh_komsu_sayisi
                )
            status.status_text = (
                f'mesh durum={durum.durum} rssi={durum.rssi} '
                f'link={durum.mesh_link_ok} '
                f'komsu={durum.mesh_komsu_sayisi}'
            )
            self._yayinla_status(drone_id, status)

    def _yayinla_status(
        self, drone_id: int, status: AgentStatus
    ) -> None:
        """Komsu durumunu ROS2 uzerinden yayinlar."""
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

    def _isle_origin(
        self, leader_id: int, payload: bytes
    ) -> None:
        """Origin pakedini cozer ve public olarak yayinlar."""
        origin = pp.origin_coz(payload)
        msg = SwarmOrigin()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_agent_id = leader_id
        msg.origin_lat_deg = origin.lat_1e7 / 1e7
        msg.origin_lon_deg = origin.lon_1e7 / 1e7
        msg.origin_alt_amsl_m = origin.alt_mm / 1000.0
        msg.valid = True
        msg.gps_fix_type = 3
        msg.sequence = origin.sequence
        self._son_origin = msg
        self._origin_pub.publish(msg)

    def _isle_komut(
        self, source_id: int, payload: bytes
    ) -> None:
        """Komut pakedini cozer ve control yayini yapar."""
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
        msg.emergency_stop = bool(
            k.flags & pp.KOMUT_FLAG_EMERGENCY
        )
        msg.formation_change_requested = bool(
            k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE
        )
        msg.deadman_pressed = bool(
            k.flags & pp.KOMUT_FLAG_DEADMAN_PRESSED
        )
        msg.command_valid = True
        self._komut_rx_seq = (
            (self._komut_rx_seq + 1) & 0xFFFFFFFF
        )
        msg.sequence_num = self._komut_rx_seq
        msg.source_module = (
            f'esp32_bridge_from_agent_{source_id}'
        )
        self._control_pub.publish(msg)

    def _isle_leader_hb(
        self, source_id: int, payload: bytes
    ) -> None:
        """Lider hb pakedini cozer ve yayinlar."""
        hb = pp.leader_hb_coz(payload)
        msg = LeaderHeartbeat()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_id = hb.leader_id
        msg.sequence_num = hb.sequence_num
        msg.election_round = hb.election_round
        msg.active_agent_count = hb.active_agent_count
        msg.mission_active = bool(hb.mission_active)
        self._leader_hb_pub.publish(msg)

    def _isle_election(
        self, source_id: int, payload: bytes
    ) -> None:
        """Secim sonuc pakedini cozer ve yayinlar."""
        e = pp.election_coz(payload)
        msg = ElectionResult()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = e.sequence_num
        msg.new_leader_id = e.new_leader_id
        msg.election_round = e.election_round
        msg.triggered_by_agent_id = e.triggered_by
        msg.reason = e.reason
        msg.confirmed_by_agent_ids = [
            i for i in e.confirmed_ids if i != 0
        ]
        self._election_pub.publish(msg)

    def _isle_renk(
        self, source_id: int, payload: bytes
    ) -> None:
        """Renk algilama pakedini cozer ve event yayar."""
        r = pp.renk_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = (
            SystemEvent.EVENT_COLOR_ZONE_DETECTED
        )
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(r.renk)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = (
            f'renk={r.renk} lat_1e7={r.lat} lon_1e7={r.lon}'
        )
        self._event_pub_public.publish(msg)

    def _isle_gorev(
        self, source_id: int, payload: bytes
    ) -> None:
        """Gorev pakedini cozer ve event yayar."""
        g = pp.gorev_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_QR_PARSED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(g.tip)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = (
            f'gorev tip={g.tip} p1={g.param1} p2={g.param2} '
            f'bekleme={g.bekleme_suresi_s}s'
        )
        self._event_pub_public.publish(msg)

    def _uart_yaz(
        self, tip: int, iha_id: int, payload: bytes
    ) -> None:
        """Veriyi COBS ve CRC ile paketleyip UART'a yazar."""
        if len(payload) != 16:
            self.get_logger().warning(
                'UART payload 16 byte degil'
            )
            return
        govde = bytes([tip, iha_id]) + payload
        crc = crc16(govde)
        cerceve = govde + bytes(
            [(crc >> 8) & 0xFF, crc & 0xFF]
        )
        with self._ser_lock:
            if self._ser is None or not self._ser.is_open:
                self._gonderim_drop += 1
                return
            try:
                self._ser.write(cobs_encode(cerceve))
                self._gonderim_ok += 1
            except serial.SerialException as exc:
                self.get_logger().warning(
                    f'Seri yazma hatasi: {exc}'
                )
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._ser = None
                self._gonderim_drop += 1

    def _on_own_status(self, msg: AgentStatus) -> None:
        """Kendi telemetrimizi mesh'e yazar."""
        now = time.monotonic()

        # Pose 10Hz
        if (now - self._son_pose_gonderim_ts >=
                self._pose_periyot_s):
            self._son_pose_gonderim_ts = now
            payload = pp.pose_paketle(
                lat=int(msg.lat_deg * 1e7),
                lon=int(msg.lon_deg * 1e7),
                alt_cm=int(msg.alt_amsl_m * 100.0),
                heading=int(msg.heading_deg * 10.0),
                vx=int(msg.vel_x * 100.0),
                vy=int(msg.vel_y * 100.0),
            )
            self._uart_yaz(
                pp.TIP_POSE, self._agent_id, payload
            )

        # Durum 1Hz
        if (now - self._son_durum_gonderim_ts >=
                self._durum_periyot_s):
            self._son_durum_gonderim_ts = now
            durum_kodu = _STATE_DURUM_MAP.get(
                msg.state, _DURUM_BILINMIYOR
            )
            batt_pct = max(
                0, min(100, int(msg.battery_percent))
            )
            payload = pp.durum_paketle(
                drone_id=self._agent_id,
                durum=durum_kodu,
                armed=1 if msg.armed else 0,
                gps_fix_type=msg.gps_fix_type,
                battery_pct=batt_pct,
                battery_volt=float(msg.battery_voltage_v),
                ekf_ok=1 if msg.estimator_ok else 0,
                imu_ok=1 if msg.imu_healthy else 0,
                mag_ok=1 if msg.mag_healthy else 0,
                baro_ok=1 if msg.baro_healthy else 0,
                rssi=0,
                mesh_link_ok=1,
                mesh_komsu_sayisi=len(
                    self._komsu_son_goruldu
                ),
            )
            self._uart_yaz(
                pp.TIP_DURUM, self._agent_id, payload
            )

    def _on_origin_out(self, msg: SwarmOrigin) -> None:
        """Cikis origin mesajini mesh'e yazar."""
        if msg.valid and msg.gps_fix_type >= 3:
            self._son_origin = msg
        if not msg.valid:
            self.get_logger().warning(
                'SwarmOrigin gecersiz, mesh yayini es gecildi'
            )
            return
        if msg.gps_fix_type < 3:
            self.get_logger().warning(
                f'Origin GPS fix={msg.gps_fix_type} < 3, '
                f'mesh yayini es gecildi'
            )
            return
        payload = pp.origin_paketle(
            lat_1e7=int(msg.origin_lat_deg * 1e7),
            lon_1e7=int(msg.origin_lon_deg * 1e7),
            alt_mm=int(msg.origin_alt_amsl_m * 1000.0),
            sequence=msg.sequence,
        )
        self._uart_yaz(
            pp.TIP_ORIGIN, self._agent_id, payload
        )

    def _on_control_out(
        self, msg: SwarmControlCommand
    ) -> None:
        """Joystick komutlarini mesh'e yazar."""
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
        if msg.deadman_pressed:
            flags |= pp.KOMUT_FLAG_DEADMAN_PRESSED

        payload = pp.komut_paketle(
            alt_tip=msg.mode,
            flags=flags,
            roll_x100=_kirp_int16(msg.roll_cmd * 100.0),
            pitch_x100=_kirp_int16(msg.pitch_cmd * 100.0),
            yaw_x100=_kirp_int16(msg.yaw_cmd * 100.0),
            throttle_x100=_kirp_int16(
                msg.throttle_cmd * 100.0
            ),
        )
        self._uart_yaz(
            pp.TIP_KOMUT, self._agent_id, payload
        )

    def _on_leader_hb_out(self, msg: LeaderHeartbeat) -> None:
        """Lider kalp atisini mesh'e iletir."""
        payload = pp.leader_hb_paketle(
            leader_id=msg.leader_id,
            sequence_num=msg.sequence_num,
            election_round=msg.election_round,
            active_agent_count=msg.active_agent_count,
            mission_active=1 if msg.mission_active else 0,
        )
        self._uart_yaz(
            pp.TIP_LEADER_HB, self._agent_id, payload
        )

    def _on_election_out(self, msg: ElectionResult) -> None:
        """Secim sonucunu mesh'e iletir."""
        payload = pp.election_paketle(
            new_leader_id=msg.new_leader_id,
            election_round=msg.election_round,
            reason=msg.reason,
            triggered_by=msg.triggered_by_agent_id,
            sequence_num=msg.sequence_num,
            confirmed_ids=tuple(msg.confirmed_by_agent_ids),
        )
        self._uart_yaz(
            pp.TIP_ELECTION, self._agent_id, payload
        )

    def destroy_node(self) -> bool:
        """Node sonlanirken kaynaklari serbest birakir."""
        self.get_logger().info(
            f'Kapanis: alim_ok={self._alim_ok} '
            f'crc_fail={self._crc_fail} '
            f'gonderim_ok={self._gonderim_ok} '
            f'gonderim_drop={self._gonderim_drop}'
        )
        self._calisiyor = False
        if self._okuma_thread.is_alive():
            self._okuma_thread.join(timeout=2.0)
            if self._okuma_thread.is_alive():
                self.get_logger().warning(
                    'UART thread 2 sn icinde durmadi'
                )
        with self._ser_lock:
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception as exc:  # noqa: BLE001
                    self.get_logger().warning(
                        f'Seri kapatma hatasi: {exc}'
                    )
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
