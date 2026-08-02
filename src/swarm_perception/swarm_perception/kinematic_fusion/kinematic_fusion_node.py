"""Komsularin telemetri verilerini EMA filtresi ile yumusatan ROS2 dugumu."""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from rclpy.time import Time

from swarm_interfaces.msg import AgentStatus, NeighborInfo, SwarmOrigin

_AVOIDANCE_DISI_STATELER = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_LANDED,
    AgentStatus.STATE_FAILSAFE,
})

_GECERLI_STATELER = frozenset(range(0, 16))
_MAKUL_KONUM_SINIR = 100.0
_MAKUL_HIZ_SINIR = 15.0


def _sayisal_gecerli(*degerler: float) -> bool:
    """Degerler NaN veya Inf degilse True doner."""
    for v in degerler:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _latlon_to_ned(
    lat: float, lon: float,
    origin_lat: float, origin_lon: float,
) -> tuple[float, float]:
    """GPS lat/lon → shared NED (kuzey, doğu) metre cinsinden."""
    R = 6_371_000.0
    north = math.radians(lat - origin_lat) * R
    east = math.radians(lon - origin_lon) * R * math.cos(math.radians(origin_lat))
    return north, east


def _makul_aralikta(
    pos_x: float, pos_y: float, pos_z: float,
    vel_x: float, vel_y: float, vel_z: float,
) -> bool:
    """Degerler makul sinirlar icindeyse True doner."""
    if (abs(pos_x) > _MAKUL_KONUM_SINIR
            or abs(pos_y) > _MAKUL_KONUM_SINIR
            or abs(pos_z) > _MAKUL_KONUM_SINIR):
        return False
    if (abs(vel_x) > _MAKUL_HIZ_SINIR
            or abs(vel_y) > _MAKUL_HIZ_SINIR
            or abs(vel_z) > _MAKUL_HIZ_SINIR):
        return False
    return True


_TELEMETRI_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)


class _EmaDurum:
    """Bir komsu icin konum ve hiz EMA filtresi."""

    def __init__(self, alpha_pos: float, alpha_vel: float) -> None:
        self.alpha_pos = alpha_pos
        self.alpha_vel = alpha_vel
        self.x: float | None = None
        self.y: float | None = None
        self.z: float | None = None
        self.vx: float | None = None
        self.vy: float | None = None
        self.vz: float | None = None
        self.son_olcum_gecerli = False

    def guncelle(self, msg: AgentStatus) -> bool:
        """Gelen telemetri verisine gore EMA durumunu gunceller."""
        if not _sayisal_gecerli(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self.son_olcum_gecerli = False
            return False
        if not _makul_aralikta(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self.son_olcum_gecerli = False
            return False
        self.x = self._ema(self.x, msg.pos_x, self.alpha_pos)
        self.y = self._ema(self.y, msg.pos_y, self.alpha_pos)
        self.z = self._ema(self.z, msg.pos_z, self.alpha_pos)
        self.vx = self._ema(self.vx, msg.vel_x, self.alpha_vel)
        self.vy = self._ema(self.vy, msg.vel_y, self.alpha_vel)
        self.vz = self._ema(self.vz, msg.vel_z, self.alpha_vel)
        self.son_olcum_gecerli = True
        return True

    def sifirla(self) -> None:
        """Filtreyi baslangic durumuna getirir."""
        self.x = self.y = self.z = None
        self.vx = self.vy = self.vz = None
        self.son_olcum_gecerli = False

    def hazir(self) -> bool:
        """Filtrenin baslangic tahminleri hazir mi?."""
        return None not in (self.x, self.y, self.z,
                            self.vx, self.vy, self.vz)

    @staticmethod
    def _ema(eski: float | None, yeni: float, alpha: float) -> float:
        """EMA filtresi adimini hesaplar."""
        if eski is None:
            return float(yeni)
        return alpha * float(yeni) + (1.0 - alpha) * eski


class KinematicFusionNode(Node):
    """Komsularin konum ve hizlarini EMA ile suzen ROS2 dugumu."""

    def __init__(self) -> None:
        super().__init__('kinematic_fusion')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('neighbor_ids', [2, 3])
        self.declare_parameter('alpha_pos', 0.3)
        self.declare_parameter('alpha_vel', 0.5)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('stale_threshold_ms', 300)
        self.declare_parameter('reset_threshold_s', 3.0)
        self.declare_parameter('self_stale_ms', 1000)

        self._self_id = int(self.get_parameter('agent_id').value)
        self._neighbor_ids = [
            int(x) for x in self.get_parameter('neighbor_ids').value
        ]
        alpha_pos = float(self.get_parameter('alpha_pos').value)
        alpha_vel = float(self.get_parameter('alpha_vel').value)
        rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self._stale_ms = int(
            self.get_parameter('stale_threshold_ms').value
        )
        self._reset_s = float(
            self.get_parameter('reset_threshold_s').value
        )
        self._self_stale_ms = int(
            self.get_parameter('self_stale_ms').value
        )

        if not 1 <= self._self_id <= 254:
            raise ValueError(
                f'agent_id 1-254 arasi olmali: {self._self_id}'
            )
        if not self._neighbor_ids:
            raise ValueError('neighbor_ids bos olamaz')
        if self._self_id in self._neighbor_ids:
            raise ValueError(
                "neighbor_ids icinde kendi agent_id'n olamaz"
            )
        if len(self._neighbor_ids) != len(set(self._neighbor_ids)):
            raise ValueError('neighbor_ids tekrarsiz olmalı')
        for nid in self._neighbor_ids:
            if not 1 <= nid <= 254:
                raise ValueError(
                    f'neighbor_id 1-254 arasi olmali: {nid}'
                )
        if not 0.0 < alpha_pos <= 1.0 or not 0.0 < alpha_vel <= 1.0:
            raise ValueError('alpha degerleri (0, 1] araliginda olmali')
        if rate_hz <= 0.0:
            raise ValueError('publish_rate_hz pozitif olmali')
        if self._stale_ms <= 0 or self._self_stale_ms <= 0:
            raise ValueError('stale esikleri pozitif olmali')
        if self._reset_s <= 0:
            raise ValueError('reset_threshold_s pozitif olmali')

        self._self_status: AgentStatus | None = None
        self._self_son_alim: Time | None = None
        self._son_ham: dict[int, AgentStatus] = {}
        self._filtreler: dict[int, _EmaDurum] = {
            nid: _EmaDurum(alpha_pos, alpha_vel)
            for nid in self._neighbor_ids
        }
        self._son_alim: dict[int, Time] = {}
        self._red_nan = 0
        self._red_yas = 0
        self._red_origin = 0
        self._red_state = 0
        self._red_validity = 0
        self._reset_filtre = 0
        self._son_self_stale_log_ts: Time | None = None

        # SwarmOrigin: shared NED göreli hesabı için ortak referans
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None

        # ----- Abonelikler -----
        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._self_id}/status',
            self._on_self_status,
            _TELEMETRI_QOS,
        )
        from rclpy.qos import DurabilityPolicy
        _origin_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_origin,
            _origin_qos,
        )
        for nid in self._neighbor_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{nid}/status',
                lambda msg, n=nid: self._on_neighbor_status(n, msg),
                _TELEMETRI_QOS,
            )

        self._yayincilar = {}
        for nid in self._neighbor_ids:
            topic = (
                f'/swarm/agent/drone{self._self_id}/neighbor/drone{nid}'
            )
            self._yayincilar[nid] = self.create_publisher(
                NeighborInfo, topic, _TELEMETRI_QOS
            )

        self.create_timer(1.0 / rate_hz, self._yayin_timer)
        self.create_timer(5.0, self._tani_timer)

        self.get_logger().info(
            f'kinematic_fusion baslatildi: self_id={self._self_id}'
        )

    def _tani_timer(self) -> None:
        """Tani verilerini periyodik olarak loglar."""
        try:
            ozet = (
                f'tani: red_nan={self._red_nan} '
                f'red_yas={self._red_yas} '
                f'red_origin={self._red_origin} '
                f'red_state={self._red_state} '
                f'red_validity={self._red_validity} '
                f'reset={self._reset_filtre}'
            )
            self.get_logger().info(ozet)
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tani log hata: {e}')

    # ---------- Callback'ler ----------
    def _on_origin(self, msg: SwarmOrigin) -> None:
        """Ortak referans noktasını saklar (shared NED göreli hesabı)."""
        if msg.valid:
            self._origin_lat = float(msg.origin_lat_deg)
            self._origin_lon = float(msg.origin_lon_deg)

    def _on_self_status(self, msg: AgentStatus) -> None:
        """Kendi durum verimizi kaydeder."""
        try:
            self._on_self_status_inner(msg)
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_on_self_status hata: {type(e).__name__}: {e}'
            )

    def _on_self_status_inner(self, msg: AgentStatus) -> None:
        if not _sayisal_gecerli(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self._red_nan += 1
            return
        if not _makul_aralikta(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self._red_nan += 1
            return
        self._self_status = msg
        self._self_son_alim = self.get_clock().now()

    def _on_neighbor_status(self, nid: int, msg: AgentStatus) -> None:
        """Komsu telemetri verisi geldikce filtreyi besler."""
        try:
            self._on_neighbor_status_inner(nid, msg)
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_on_neighbor_status({nid}) hata: '
                f'{type(e).__name__}: {e}'
            )

    def _on_neighbor_status_inner(
        self, nid: int, msg: AgentStatus,
    ) -> None:
        now = self.get_clock().now()

        if nid in self._son_alim:
            bos_gecen_s = (
                (now - self._son_alim[nid]).nanoseconds / 1e9
            )
            if bos_gecen_s > self._reset_s:
                self._filtreler[nid].sifirla()
                self._reset_filtre += 1

        gecerli = self._filtreler[nid].guncelle(msg)
        if not gecerli:
            self._red_nan += 1
            return

        self._son_ham[nid] = msg
        self._son_alim[nid] = now

    def _yayin_timer(self) -> None:
        """Hesaplanan komsularin bilgilerini yayinlar."""
        try:
            self._yayin_timer_inner()
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_yayin_timer hata: {type(e).__name__}: {e}'
            )

    def _yayin_timer_inner(self) -> None:
        if self._self_status is None or self._self_son_alim is None:
            return

        now = self.get_clock().now()
        self_yas_ms = max(
            0, (now - self._self_son_alim).nanoseconds // 1_000_000
        )
        if self_yas_ms > self._self_stale_ms:
            son_log = self._son_self_stale_log_ts
            if son_log is None or (
                (now - son_log).nanoseconds >= 5_000_000_000
            ):
                self.get_logger().warning(
                    f'kendi durum {self_yas_ms}ms eski'
                )
                self._son_self_stale_log_ts = now
            return

        for nid in self._neighbor_ids:
            if nid not in self._son_ham:
                continue
            try:
                mesaj = self._neighbor_info_olustur(nid, now)
                self._yayincilar[nid].publish(mesaj)
            except Exception as e:  # noqa: BLE001
                self.get_logger().error(
                    f'komşu {nid} yayini basarisiz: {e}'
                )

    def _neighbor_info_olustur(self, nid: int, now: Time) -> NeighborInfo:
        """Komsu verisini hazirlar ve link durumunu test eder."""
        ham = self._son_ham[nid]
        filtre = self._filtreler[nid]
        son_alim = self._son_alim[nid]
        self_msg = self._self_status

        msg = NeighborInfo()
        msg.stamp = now.to_msg()
        msg.self_agent_id = self._self_id
        msg.neighbor_agent_id = nid
        if ham.state in _GECERLI_STATELER:
            msg.neighbor_state = ham.state
        else:
            msg.neighbor_state = AgentStatus.STATE_UNKNOWN
        msg.link_type = 'esp-now'

        yas_ns = (now - son_alim).nanoseconds
        msg.data_age_ms = max(0, yas_ns // 1_000_000)

        link_ok = True
        if msg.data_age_ms > self._stale_ms:
            link_ok = False
            self._red_yas += 1

        if not self_msg.origin_synced:
            link_ok = False
            self._red_origin += 1
        elif not ham.origin_synced:
            link_ok = False
            self._red_origin += 1

        if ham.state in _AVOIDANCE_DISI_STATELER:
            link_ok = False
            self._red_state += 1

        if (not ham.xy_valid or not ham.z_valid
                or not ham.v_xy_valid):
            link_ok = False
            self._red_validity += 1

        if hasattr(ham, 'mesh_link_ok') and not ham.mesh_link_ok:
            link_ok = False

        if not filtre.hazir():
            link_ok = False

        f_x = filtre.x if filtre.x is not None else ham.pos_x
        f_y = filtre.y if filtre.y is not None else ham.pos_y
        f_z = filtre.z if filtre.z is not None else ham.pos_z
        f_vx = filtre.vx if filtre.vx is not None else ham.vel_x
        f_vy = filtre.vy if filtre.vy is not None else ham.vel_y
        f_vz = filtre.vz if filtre.vz is not None else ham.vel_z

        # ----- Relative değerler (komşu - kendi, shared NED) -----
        # GPS varsa ve origin kilitliyse shared NED'den hesapla:
        # her drone farklı local origin'de başladığı için local pos_x
        # farkı spawn offset'i içerir → hayalet hata. GPS→shared NED
        # çevirimi bu offset'i ortadan kaldırır.
        if (self._origin_lat is not None
                and ham.lat_deg != 0.0 and self_msg.lat_deg != 0.0):
            n_n, n_e = _latlon_to_ned(
                ham.lat_deg, ham.lon_deg,
                self._origin_lat, self._origin_lon,
            )
            s_n, s_e = _latlon_to_ned(
                self_msg.lat_deg, self_msg.lon_deg,
                self._origin_lat, self._origin_lon,
            )
            rel_x = float(n_n - s_n)
            rel_y = float(n_e - s_e)
        else:
            # Fallback: origin veya GPS yoksa eski yol (local fark)
            rel_x = float(f_x - self_msg.pos_x)
            rel_y = float(f_y - self_msg.pos_y)
        rel_z = float(f_z - self_msg.pos_z)
        rel_vx = float(f_vx - self_msg.vel_x)
        rel_vy = float(f_vy - self_msg.vel_y)
        rel_vz = float(f_vz - self_msg.vel_z)

        if not _sayisal_gecerli(
            rel_x, rel_y, rel_z, rel_vx, rel_vy, rel_vz
        ):
            link_ok = False
            rel_x = rel_y = rel_z = 0.0
            rel_vx = rel_vy = rel_vz = 0.0

        msg.relative_x = rel_x
        msg.relative_y = rel_y
        msg.relative_z = rel_z
        msg.relative_vx = rel_vx
        msg.relative_vy = rel_vy
        msg.relative_vz = rel_vz

        msg.distance_m = float(math.sqrt(
            rel_x * rel_x + rel_y * rel_y + rel_z * rel_z
        ))

        msg.link_active = link_ok
        msg.rssi = 0.0
        msg.packet_loss_percent = 0.0

        return msg


def main(args=None):
    rclpy.init(args=args)
    node = KinematicFusionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001
        node.get_logger().error(
            f'rclpy.spin sirasinda hata: {e}'
        )
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
