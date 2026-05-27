"""kinematic_fusion_node.py — komşu telemetrisinin EMA tabanlı füzyonu.

ESP32 mesh üzerinden gelen komşu drone telemetrisi (AgentStatus) hafif
gürültülüdür: paket kaybı, ESP-NOW kanal jitter'ı ve int32 (1.1cm) tabanlı
quantization adımları sürekli küçük zıplamalar üretir. Bu düğüm her komşu
için Üstel Hareketli Ortalama (EMA = Exponential Moving Average) ile
konum ve hızı yumuşatır; collision_avoidance (ORCA/APF) ve
formation_control'ün titremeden çalışmasını sağlar.

GİRİŞ TOPIC'LERİ:
    /swarm/internal/drone{self_id}/status   (kendi durumumuz, agent_fsm)
    /swarm/public/drone{neighbor_id}/status (her komşu, esp32_bridge)

ÇIKIŞ TOPIC'LERİ (her komşu için):
    /swarm/agent/drone{self_id}/neighbor/drone{neighbor_id}  (LOKAL)

YAYIN MANTIĞI:
    Timer 10Hz tetiklenir. Her komşu için son alınan AgentStatus'a EMA
    uygulanmış değerler ile NeighborInfo doldurulur. data_age_ms eşiği
    aşıldıysa link_active=false işaretlenir; collision_avoidance bu
    bayrağı görünce o komşuyu hesaba katmaz (INTERFACE_CONTRACT m.9).

KULLANIM:
    ros2 run swarm_perception kinematic_fusion --ros-args \\
        -p agent_id:=1 -p neighbor_ids:=[2,3]
"""

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

from swarm_interfaces.msg import AgentStatus, NeighborInfo


# INTERFACE_CONTRACT madde 8: avoidance hesabından çıkarılan state'ler
# DETACHED=7, PRECISION_LANDING=8, LANDED=13, FAILSAFE=14
_AVOIDANCE_DISI_STATELER = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_LANDED,
    AgentStatus.STATE_FAILSAFE,
})

# Bilinen tüm geçerli state değerleri (AgentStatus.STATE_* sabitleri 0-15).
# Bunun dışında bir değer gelirse firmware bozuk veri gönderiyor demektir;
# UNKNOWN'a düşür ki avoidance yanlış geçmesin.
_GECERLI_STATELER = frozenset(range(0, 16))

# Akıllı mantığa "saçma değer" sayılan konum sınırı (m).
# Yarışma sahası birkaç yüz metre; 100 km'lik bir değer sensör glitch'i ya
# da bozuk paket demektir. Bu eşiğin üstündeki ölçüm reddedilir.
_MAKUL_KONUM_SINIR = 100_000.0  # 100 km
_MAKUL_HIZ_SINIR = 200.0        # 200 m/s (uçak değil, sürü drone)


def _sayisal_gecerli(*degerler: float) -> bool:
    """Verilen değerlerin hiçbiri NaN veya Inf değilse True."""
    for v in degerler:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _makul_aralikta(
    pos_x: float, pos_y: float, pos_z: float,
    vel_x: float, vel_y: float, vel_z: float,
) -> bool:
    """Konum/hız değerleri fiziksel olarak makul aralıkta mı?"""
    if (abs(pos_x) > _MAKUL_KONUM_SINIR
            or abs(pos_y) > _MAKUL_KONUM_SINIR
            or abs(pos_z) > _MAKUL_KONUM_SINIR):
        return False
    if (abs(vel_x) > _MAKUL_HIZ_SINIR
            or abs(vel_y) > _MAKUL_HIZ_SINIR
            or abs(vel_z) > _MAKUL_HIZ_SINIR):
        return False
    return True


# Komşu/own status için BEST_EFFORT — kayıp paket tolere edilir
_TELEMETRI_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)


class _EmaDurum:
    """Bir komşu için EMA filtre durumu (konum + hız).

    Sönümleme katsayıları (alpha) konum ve hız için ayrı tutulur:
    konum yavaş değişir, düşük alpha ile sıkı yumuşatma yeter;
    hız hızlı değişir, yüksek alpha ile gecikme azaltılır.

    NaN/Inf gelen ölçümler reddedilir (skip) ve filtre durumu korunur;
    bu sayede tek bir bozuk paket geçmiş tahminleri kirletmez.
    """

    def __init__(self, alpha_pos: float, alpha_vel: float) -> None:
        self.alpha_pos = alpha_pos
        self.alpha_vel = alpha_vel
        # Başlangıçta tahmin yok; ilk geçerli ölçümde "warm start"
        self.x: float | None = None
        self.y: float | None = None
        self.z: float | None = None
        self.vx: float | None = None
        self.vy: float | None = None
        self.vz: float | None = None
        # Sayısal sağlık: son güncellemede tüm değerler geçerli miydi?
        self.son_olcum_gecerli: bool = False

    def guncelle(self, msg: AgentStatus) -> bool:
        """Yeni AgentStatus geldiğinde EMA tahminlerini günceller.

        Returns:
            bool: Ölçüm geçerliyse True; NaN/Inf veya makul aralık
                dışıysa False (filtreye dokunulmaz).
        """
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
        """Filtre durumunu sıfırlar (uzun süre veri yoksa)."""
        self.x = self.y = self.z = None
        self.vx = self.vy = self.vz = None
        self.son_olcum_gecerli = False

    def hazir(self) -> bool:
        """Tüm eksenler için warm start tamam mı?"""
        return None not in (self.x, self.y, self.z,
                            self.vx, self.vy, self.vz)

    @staticmethod
    def _ema(eski: float | None, yeni: float, alpha: float) -> float:
        """EMA tek satır: ilk ölçümse warm start, değilse karış."""
        if eski is None:
            return float(yeni)
        return alpha * float(yeni) + (1.0 - alpha) * eski


class KinematicFusionNode(Node):
    """Komşu telemetrisini EMA ile yumuşatan ROS2 düğümü."""

    def __init__(self) -> None:
        super().__init__('kinematic_fusion')

        # ----- Parametreler -----
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('neighbor_ids', [2, 3])
        self.declare_parameter('alpha_pos', 0.3)
        self.declare_parameter('alpha_vel', 0.5)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('stale_threshold_ms', 500)
        # Filtre reset eşiği: bu kadar saniye veri yoksa filtreyi
        # tamamen sıfırla (eski state şişmemiş gerçekliği bozmasın)
        self.declare_parameter('reset_threshold_s', 5.0)
        # Kendi durumumuzu da eski sayma eşiği (clock jump koruması)
        self.declare_parameter('self_stale_ms', 1000)

        self._self_id = int(self.get_parameter('agent_id').value)
        self._neighbor_ids = [
            int(x) for x in self.get_parameter('neighbor_ids').value
        ]
        alpha_pos = float(self.get_parameter('alpha_pos').value)
        alpha_vel = float(self.get_parameter('alpha_vel').value)
        rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self._stale_ms = int(self.get_parameter('stale_threshold_ms').value)
        self._reset_s = float(self.get_parameter('reset_threshold_s').value)
        self._self_stale_ms = int(self.get_parameter('self_stale_ms').value)

        # Parametre doğrulama: erken patla, sahaya yanlış kod gitmesin
        if not 1 <= self._self_id <= 254:
            raise ValueError(
                f'agent_id 1-254 arasında olmalı: {self._self_id}'
            )
        if not self._neighbor_ids:
            raise ValueError('neighbor_ids boş olamaz')
        if self._self_id in self._neighbor_ids:
            raise ValueError(
                "neighbor_ids içinde kendi agent_id'n olamaz"
            )
        if len(self._neighbor_ids) != len(set(self._neighbor_ids)):
            raise ValueError('neighbor_ids tekrarsız olmalı')
        for nid in self._neighbor_ids:
            if not 1 <= nid <= 254:
                raise ValueError(
                    f'neighbor_id 1-254 arasında olmalı: {nid}'
                )
        if not 0.0 < alpha_pos <= 1.0 or not 0.0 < alpha_vel <= 1.0:
            raise ValueError('alpha_pos ve alpha_vel (0, 1] aralığında olmalı')
        if rate_hz <= 0.0:
            raise ValueError('publish_rate_hz pozitif olmalı')
        if self._stale_ms <= 0 or self._self_stale_ms <= 0:
            raise ValueError('stale eşikleri pozitif olmalı')
        if self._reset_s <= 0:
            raise ValueError('reset_threshold_s pozitif olmalı')

        # ----- Durum -----
        # Kendi son AgentStatus'umuz — relative değer için gerekli
        self._self_status: AgentStatus | None = None
        self._self_son_alim: Time | None = None
        # Komşu ID -> son alınan AgentStatus (ham)
        self._son_ham: dict[int, AgentStatus] = {}
        # Komşu ID -> EMA filtre durumu
        self._filtreler: dict[int, _EmaDurum] = {
            nid: _EmaDurum(alpha_pos, alpha_vel) for nid in self._neighbor_ids
        }
        # Komşu ID -> son alım zamanı (ROS Time)
        self._son_alim: dict[int, Time] = {}
        # Tanı sayaçları (log/dashboard için)
        self._red_nan = 0          # NaN/Inf yüzünden reddedilen güncelleme
        self._red_yas = 0          # yaşlı veri yüzünden link_active=false
        self._red_origin = 0       # origin senkron eksikliği
        self._red_state = 0        # state avoidance dışı
        self._red_validity = 0     # PX4 validity flag false
        self._reset_filtre = 0     # filtre sıfırlama sayısı

        # ----- Abonelikler -----
        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._self_id}/status',
            self._on_self_status,
            _TELEMETRI_QOS,
        )
        for nid in self._neighbor_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{nid}/status',
                lambda msg, n=nid: self._on_neighbor_status(n, msg),
                _TELEMETRI_QOS,
            )

        # ----- Yayıncılar (komşu başına) -----
        # ROS2 topic isim kuralı: token rakamla başlayamaz; bu yüzden
        # bridge'in stiline uyup 'drone' öneki kullanıyoruz
        # (/swarm/agent/drone1/neighbor/drone2 gibi).
        self._yayincilar: dict[int, object] = {}
        for nid in self._neighbor_ids:
            topic = (
                f'/swarm/agent/drone{self._self_id}/neighbor/drone{nid}'
            )
            self._yayincilar[nid] = self.create_publisher(
                NeighborInfo, topic, _TELEMETRI_QOS
            )

        # ----- Timer (yayın frekansı) -----
        self.create_timer(1.0 / rate_hz, self._yayin_timer)
        # ----- Tanı timer'ı (5sn'de bir sayaçları log'la) -----
        self.create_timer(5.0, self._tani_timer)

        self.get_logger().info(
            f'kinematic_fusion başlatıldı: self_id={self._self_id} '
            f'komşular={self._neighbor_ids} alpha_pos={alpha_pos} '
            f'alpha_vel={alpha_vel} rate={rate_hz}Hz'
        )

    def _tani_timer(self) -> None:
        """5sn'de bir savunma sayaçlarını log'la; canlı sistemde takip için."""
        try:
            ozet = (
                f'tanı: red_nan={self._red_nan} '
                f'red_yas={self._red_yas} '
                f'red_origin={self._red_origin} '
                f'red_state={self._red_state} '
                f'red_validity={self._red_validity} '
                f'reset={self._reset_filtre}'
            )
            self.get_logger().info(ozet)
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tanı log hata: {e}')

    # ---------- Callback'ler ----------
    def _on_self_status(self, msg: AgentStatus) -> None:
        """Kendi agent_fsm durumumuzu saklar; relative hesabı için.

        Tüm beklenmeyen hatalar yakalanır — callback istisna fırlatırsa
        rclpy executor'u bir sonraki callback'e geçer ama hatayı görmek
        için log basmak gerekir.
        """
        try:
            self._on_self_status_inner(msg)
        except Exception as e:  # noqa: BLE001 - tüm hataları yakala
            self.get_logger().error(
                f'_on_self_status hata: {type(e).__name__}: {e}'
            )

    def _on_self_status_inner(self, msg: AgentStatus) -> None:
        if not _sayisal_gecerli(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self._red_nan += 1
            self.get_logger().warning(
                'kendi AgentStatus NaN/Inf içeriyor, atlandı'
            )
            return
        if not _makul_aralikta(
            msg.pos_x, msg.pos_y, msg.pos_z,
            msg.vel_x, msg.vel_y, msg.vel_z,
        ):
            self._red_nan += 1
            self.get_logger().warning(
                'kendi AgentStatus fiziksel sınır dışı, atlandı'
            )
            return
        self._self_status = msg
        self._self_son_alim = self.get_clock().now()

    def _on_neighbor_status(self, nid: int, msg: AgentStatus) -> None:
        """Komşudan AgentStatus geldiğinde EMA'yı günceller (try'lı)."""
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
        """Asıl mantık (try dışında çağrılır)."""
        now = self.get_clock().now()

        # Filtre reset gerekiyor mu? (uzun süre veri yok)
        if nid in self._son_alim:
            bos_gecen_s = (
                (now - self._son_alim[nid]).nanoseconds / 1e9
            )
            if bos_gecen_s > self._reset_s:
                self._filtreler[nid].sifirla()
                self._reset_filtre += 1
                self.get_logger().info(
                    f'komşu {nid} filtre sıfırlandı '
                    f'({bos_gecen_s:.1f}s veri yoktu)'
                )

        # Geçersiz değer reddi (NaN, Inf, fiziksel sınır dışı)
        gecerli = self._filtreler[nid].guncelle(msg)
        if not gecerli:
            self._red_nan += 1
            self.get_logger().warning(
                f'komşu {nid} AgentStatus geçersiz/sınır dışı, atlandı'
            )
            return

        self._son_ham[nid] = msg
        self._son_alim[nid] = now

    # ---------- Yayın ----------
    def _yayin_timer(self) -> None:
        """10Hz tetiklenir; her komşu için NeighborInfo yayınlar.

        Try sarmalama içeride komşu başına yapılır; bir komşudaki sorun
        diğerlerinin yayınını durdurmamalı.
        """
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
            if (now.nanoseconds // 1_000_000_000) % 5 == 0:
                self.get_logger().warning(
                    f'kendi durum {self_yas_ms}ms eski, yayın atlandı'
                )
            return

        for nid in self._neighbor_ids:
            if nid not in self._son_ham:
                continue
            # Komşu başına izolasyon — biri patlasa diğerleri devam etsin
            try:
                mesaj = self._neighbor_info_olustur(nid, now)
                self._yayincilar[nid].publish(mesaj)
            except Exception as e:  # noqa: BLE001
                self.get_logger().error(
                    f'komşu {nid} yayını başarısız: '
                    f'{type(e).__name__}: {e}'
                )

    def _neighbor_info_olustur(self, nid: int, now: Time) -> NeighborInfo:
        """EMA çıktısı + tüm geçerlilik kontrolleri ile NeighborInfo üretir.

        link_active=false yapan koşullar (INTERFACE_CONTRACT madde 8-9-12):
            - data_age_ms > stale_threshold (eski paket)
            - kendi origin_synced=false (NED hesabı anlamsız)
            - komşu origin_synced=false (komşunun NED'i kendi origin'inde)
            - komşu state ∈ {DETACHED, PRECISION_LANDING, LANDED, FAILSAFE}
            - komşu xy_valid=false veya z_valid=false (PX4 güvenmiyor)
            - komşu mesh_link_ok=false (komşunun mesh'i kopuk)
            - EMA henüz warm start tamamlamamış (en az 1 geçerli paket lazım)
            - sayısal sonuç NaN/Inf çıkarsa (son güvenlik ağı)

        link_active=false durumlarında relative değerler **yine doldurulur**;
        downstream (örn. GCS dashboard) eski son değeri görebilir.
        Ama collision_avoidance/formation_control link_active'i kontrol
        etmek ZORUNDADIR (kontrat m.9).
        """
        ham = self._son_ham[nid]
        filtre = self._filtreler[nid]
        son_alim = self._son_alim[nid]
        self_msg = self._self_status

        msg = NeighborInfo()
        msg.stamp = now.to_msg()
        msg.self_agent_id = self._self_id
        msg.neighbor_agent_id = nid
        # State aralık kontrolü — firmware bozuk state gönderirse UNKNOWN'a
        # düşür ki downstream'in enum eşleştirmesi patlamasın
        if ham.state in _GECERLI_STATELER:
            msg.neighbor_state = ham.state
        else:
            msg.neighbor_state = AgentStatus.STATE_UNKNOWN
            self.get_logger().warning(
                f'komşu {nid} bilinmeyen state={ham.state}, '
                f'UNKNOWN olarak işaretlendi'
            )
        msg.link_type = 'esp-now'

        # ----- data_age_ms (clock jump koruması: negatif olmaz) -----
        yas_ns = (now - son_alim).nanoseconds
        msg.data_age_ms = max(0, yas_ns // 1_000_000)

        # ----- link_active: tüm koşulları birleştir -----
        link_ok = True
        nedenler = []

        if msg.data_age_ms > self._stale_ms:
            link_ok = False
            self._red_yas += 1
            nedenler.append(f'yas={msg.data_age_ms}ms')

        if not self_msg.origin_synced:
            link_ok = False
            self._red_origin += 1
            nedenler.append('self.origin_synced=false')
        elif not ham.origin_synced:
            link_ok = False
            self._red_origin += 1
            nedenler.append('neighbor.origin_synced=false')

        if ham.state in _AVOIDANCE_DISI_STATELER:
            link_ok = False
            self._red_state += 1
            nedenler.append(f'state={ham.state}')

        if (not ham.xy_valid or not ham.z_valid
                or not ham.v_xy_valid):
            link_ok = False
            self._red_validity += 1
            nedenler.append('px4_validity=false')

        if hasattr(ham, 'mesh_link_ok') and not ham.mesh_link_ok:
            link_ok = False
            nedenler.append('neighbor.mesh_link_ok=false')

        if not filtre.hazir():
            link_ok = False
            nedenler.append('filtre_warm_start_bekliyor')

        # ----- Filtrelenmiş NEIGHBOR konum/hız (mutlak NED) -----
        f_x = filtre.x if filtre.x is not None else ham.pos_x
        f_y = filtre.y if filtre.y is not None else ham.pos_y
        f_z = filtre.z if filtre.z is not None else ham.pos_z
        f_vx = filtre.vx if filtre.vx is not None else ham.vel_x
        f_vy = filtre.vy if filtre.vy is not None else ham.vel_y
        f_vz = filtre.vz if filtre.vz is not None else ham.vel_z

        # ----- Relative değerler (komşu - kendi) -----
        rel_x = float(f_x - self_msg.pos_x)
        rel_y = float(f_y - self_msg.pos_y)
        rel_z = float(f_z - self_msg.pos_z)
        rel_vx = float(f_vx - self_msg.vel_x)
        rel_vy = float(f_vy - self_msg.vel_y)
        rel_vz = float(f_vz - self_msg.vel_z)

        # ----- Son güvenlik ağı: sayısal taşma/NaN -----
        if not _sayisal_gecerli(
            rel_x, rel_y, rel_z, rel_vx, rel_vy, rel_vz
        ):
            link_ok = False
            nedenler.append('numeric_invalid')
            # Sıfırla (NaN downstream'i çökertmesin)
            rel_x = rel_y = rel_z = 0.0
            rel_vx = rel_vy = rel_vz = 0.0

        msg.relative_x = rel_x
        msg.relative_y = rel_y
        msg.relative_z = rel_z
        msg.relative_vx = rel_vx
        msg.relative_vy = rel_vy
        msg.relative_vz = rel_vz

        # Öklid mesafesi (collision avoidance ana girdi)
        msg.distance_m = float(math.sqrt(
            rel_x * rel_x + rel_y * rel_y + rel_z * rel_z
        ))

        msg.link_active = link_ok

        # Debug seviyesinde link iptal nedenlerini bas (log flood değil)
        if not link_ok and nedenler:
            self.get_logger().debug(
                f'komşu {nid} link_active=false: {", ".join(nedenler)}'
            )

        # RSSI ve paket kaybı: kinematic_fusion bu bilgilere doğrudan
        # erişmiyor (bridge mesh_diag'ta tutuyor). İleride bridge'ten
        # event/topic ile gelebilir; şimdilik nötr değerler.
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
            f'rclpy.spin sırasında hata: {type(e).__name__}: {e}'
        )
    finally:
        node.destroy_node()
        # Sinyal işleyici zaten shutdown yapmış olabilir (SIGTERM/timeout)
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
