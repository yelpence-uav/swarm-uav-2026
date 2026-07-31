# Copyright 2026 Yelpence
"""BASİT ÇARPIŞMA KAÇINMASI — komşudan iten alan (APF).

NEDEN AYRI BİR DÜĞÜM
Repoda `swarm_core/collision_avoidance` zaten var ve APF uyguluyor, ama
çalışması için `kinematic_fusion`'ın ürettiği `NeighborInfo`'ya ve
`FormationCommand`'a bağlı — yani sahada hiç koşmamış zincirin iki halkası
daha devreye girmek zorunda. Uçuş öncesi o zincire girmek, teşhisi zor bir
alana girmek demek. Bu düğüm o zincire HİÇ dokunmuyor: komşunun durumunu
`esp32_bridge`'in mesh'ten alıp zaten yayınladığı konudan doğrudan okuyor.

NEDEN DRONE'DA, YERDE DEĞİL
Kaçınmada gecikme doğrudan tepki mesafesine dönüşür: 4 m/s'te 500 ms = 2 m.
Yer istasyonundan kaçınma hesaplamak hem bu gecikmeyi ekler hem mesh'e
sürekli komut trafiği bindirir hem de yer bağlantısı koptuğunda ölür.
Burada drone'un kendi döngüsünde, komşu verisi zaten elindeyken hesaplanıyor.

NEREYE GİRİYOR
    esp32_bridge → /drone_N/control/setpoint/raw
                        ↓  (bu düğüm)
                   /drone_N/control/setpoint → px4_bridge

esp32_bridge'in çıkışı `/raw`'a yönlendirilmeden bu düğüm devrede DEĞİLDİR
ve hiçbir şeyi bozmaz — yayını kimse dinlemez.

ALGORİTMA (APF, yalnız yatay)
Komşu `d0`'dan yakınsa ondan UZAĞA bir itme vektörü üretilir. Büyüklük
`d0`'da sıfırdan başlar, `hard`'da doyuma ulaşır; arada smoothstep ile
yumuşak geçer — basamak fonksiyonu kullanmak setpoint'te sıçrama yaratır
ve uçak sarsılır.

Dikeye BİLEREK dokunulmuyor. İki sebep: (1) irtifa ayrımı bizim yedek
çarpışma garantimiz, kaçınma onu bozmamalı; (2) yatay itme gözle
izlenebilir, dikey itme videoda ve testte ayırt edilmesi zor.

GÜVENLİK SINIRLARI — hepsi bilerek muhafazakâr
* Toplam sapma `max_itme_m` ile kelepçeli. APF çarpışmasızlığı GARANTİ
  ETMEZ; kelepçe olmadan bir hata uçağı görev alanının dışına yollayabilir.
* Komşu verisi `bayat_s`'ten eskiyse YOK SAYILIR. Bayat konuma göre itmek,
  komşunun artık orada olmadığı bir yerden kaçmak demektir.
* Komşu yoksa, veri bayatsa veya itme sıfırsa ham setpoint AYNEN geçer.
  Yani düğümün arızası "kaçınma yok"tur, "kontrol yok" değil.
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles

from swarm_interfaces.msg import AgentSetpoint, AgentStatus


def _smoothstep(t: float) -> float:
    """0..1 arasını yumuşak geçirir (türevi uçlarda sıfır)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def itme_vektoru(kendi, komsular, d0: float, hard: float, f_sat: float):
    """Komşulardan gelen toplam yatay itmeyi (kuzey, doğu) döner.

    SAF FONKSİYON — ROS'suz test edilebilsin diye ayrı tutuldu.

    Args:
        kendi: (kuzey, doğu) kendi konumumuz.
        komsular: [(kuzey, doğu), ...] komşu konumları.
        d0: itmenin başladığı yarıçap (m).
        hard: itmenin doyuma ulaştığı yarıçap (m).
        f_sat: doygunluktaki itme büyüklüğü (m).

    Returns:
        (kuzey, doğu) toplam itme vektörü, metre.
    """
    tk = td = 0.0
    for kk, kd in komsular:
        dk = kendi[0] - kk
        dd = kendi[1] - kd
        d = math.hypot(dk, dd)
        if d >= d0:
            continue
        if d < 1e-3:
            # Tam üst üste: yön tanımsız. Keyfi bir yöne it — hiç itmemekten
            # iyidir, ve bu durum zaten patolojik.
            tk += f_sat
            continue
        buyukluk = f_sat if d <= hard else f_sat * _smoothstep((d0 - d) / (d0 - hard))
        tk += buyukluk * dk / d
        td += buyukluk * dd / d
    return tk, td


class BasitKacinmaNode(Node):
    """Ham setpoint'i alır, komşudan iter, px4_bridge'e verir."""

    def __init__(self) -> None:
        super().__init__('basit_kacinma')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('komsu_idler', [2, 3])
        # d0 FORMASYON ARALIĞINDAN KÜÇÜK OLMALI. Aralık 12 m; d0 bundan
        # büyük olursa normal formasyonda bile sürekli itme üretir ve
        # uçaklar hedeflerine hiç oturmaz.
        self.declare_parameter('d0_m', 8.0)
        self.declare_parameter('hard_m', 4.0)
        self.declare_parameter('f_sat_m', 4.0)
        self.declare_parameter('max_itme_m', 6.0)
        self.declare_parameter('bayat_s', 1.5)

        self._aid = int(self.get_parameter('agent_id').value)
        self._d0 = float(self.get_parameter('d0_m').value)
        self._hard = float(self.get_parameter('hard_m').value)
        self._f_sat = float(self.get_parameter('f_sat_m').value)
        self._max_itme = float(self.get_parameter('max_itme_m').value)
        self._bayat = float(self.get_parameter('bayat_s').value)
        if not (0.0 < self._hard < self._d0):
            raise ValueError('hard_m < d0_m olmalı')

        qos = QoSPresetProfiles.SENSOR_DATA.value
        self._kendi = None            # (kuzey, doğu)
        self._komsu = {}              # id -> (kuzey, doğu, zaman)
        self._son_itme = (0.0, 0.0)

        self._pub = self.create_publisher(
            AgentSetpoint, f'/drone_{self._aid}/control/setpoint', qos)
        self.create_subscription(
            AgentSetpoint, f'/drone_{self._aid}/control/setpoint/raw',
            self._on_raw, qos)
        self.create_subscription(
            AgentStatus, f'/swarm/agent/drone{self._aid}/telemetry',
            self._on_kendi, qos)

        for nid in self.get_parameter('komsu_idler').value:
            nid = int(nid)
            if nid == self._aid:
                continue
            # esp32_bridge mesh'ten gelen komşu durumunu BURAYA yayınlıyor —
            # NeighborInfo'ya ve kinematic_fusion'a ihtiyaç yok.
            self.create_subscription(
                AgentStatus, f'/swarm/public/drone{nid}/status',
                lambda m, n=nid: self._on_komsu(n, m), qos)
            self.get_logger().info(f'komşu aboneliği: drone{nid}')

        self.create_timer(1.0, self._durum_yaz)
        self.get_logger().info(
            f'basit_kacinma başladı: agent={self._aid} '
            f'd0={self._d0} hard={self._hard} f_sat={self._f_sat} '
            f'max={self._max_itme}')

    # --- girişler ----------------------------------------------------------
    def _on_kendi(self, m: AgentStatus) -> None:
        self._kendi = (m.pos_x, m.pos_y)

    def _on_komsu(self, nid: int, m: AgentStatus) -> None:
        self._komsu[nid] = (m.pos_x, m.pos_y, self._simdi())

    def _simdi(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    # --- asıl iş -----------------------------------------------------------
    def _on_raw(self, msg: AgentSetpoint) -> None:
        """Ham setpoint'i itme ile düzeltip yayınlar.

        HER ÇIKIŞ YOLU BİR SETPOINT YAYINLAR. Sessizce düşürmek px4_bridge'in
        setpoint akışını kesmek demektir ve PX4 OFFBOARD'dan düşer — yani
        kaçınma düğümündeki bir hata uçağı failsafe'e sokar. Bu yüzden
        şüpheli her durumda ham setpoint AYNEN geçirilir.
        """
        cik = msg
        itme = (0.0, 0.0)

        if self._kendi is not None and msg.position_valid:
            t = self._simdi()
            taze = [(k, d) for (k, d, ts) in self._komsu.values()
                    if t - ts <= self._bayat]
            if taze:
                itme = itme_vektoru(self._kendi, taze,
                                    self._d0, self._hard, self._f_sat)
                # KELEPÇE: APF çarpışmasızlığı garanti etmez; sapmanın
                # büyüklüğü her koşulda sınırlı kalmalı.
                buy = math.hypot(*itme)
                if buy > self._max_itme:
                    itme = (itme[0] * self._max_itme / buy,
                            itme[1] * self._max_itme / buy)
                if buy > 1e-3:
                    cik = AgentSetpoint()
                    # Alanları tek tek kopyala: mesajı yerinde değiştirmek
                    # aynı nesneyi tutan başka aboneleri etkileyebilir.
                    for alan in msg.get_fields_and_field_types():
                        setattr(cik, alan, getattr(msg, alan))
                    cik.x = msg.x + itme[0]
                    cik.y = msg.y + itme[1]
                    # z'ye DOKUNULMUYOR — irtifa ayrımı yedek garantimiz.
                    cik.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
                    cik.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
                    cik.source_module = 'basit_kacinma'

        self._son_itme = itme
        self._pub.publish(cik)

    def _durum_yaz(self) -> None:
        if self._kendi is None:
            self.get_logger().warn('kendi konumum yok — kaçınma PASİF',
                                   throttle_duration_sec=10.0)
            return
        t = self._simdi()
        satir = []
        for nid, (k, d, ts) in sorted(self._komsu.items()):
            yas = t - ts
            mesafe = math.hypot(self._kendi[0] - k, self._kendi[1] - d)
            satir.append(f'd{nid}={mesafe:.1f}m'
                         + ('(BAYAT)' if yas > self._bayat else ''))
        if satir:
            self.get_logger().info(
                'komşu: ' + ' '.join(satir)
                + f'  itme=({self._son_itme[0]:+.2f},{self._son_itme[1]:+.2f})m',
                throttle_duration_sec=2.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    dugum = BasitKacinmaNode()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        dugum.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
