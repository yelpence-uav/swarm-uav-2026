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

import copy
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles

from swarm_interfaces.msg import AgentSetpoint, AgentStatus


def _smoothstep(t: float) -> float:
    """0..1 arasını yumuşak geçirir (türevi uçlarda sıfır)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# Teğet bileşenin ölçeklendiği referans yaklaşma hızı (m/s). Komşu bundan
# hızlı yaklaşıyorsa teğet tam açılır.
_REF_KAPANMA_MS = 1.5


def itme_vektoru(kendi, komsular, d0: float, hard: float, f_sat: float,
                 k_tan: float = 0.0):
    """Komşulardan gelen toplam yatay itmeyi (kuzey, doğu) döner.

    SAF FONKSİYON — ROS'suz test edilebilsin diye ayrı tutuldu.

    İki bileşen var:

    RADYAL — komşudan doğrudan uzağa. Tek başına yetmez: kafa kafaya bir
    yaklaşmada uçak dümdüz geri geri kaçar, yol vermez, ve sonunda ya
    sıkışır ya menzil dışına itilir.

    TEĞET — radyal itmenin 90° döndürülmüşü. "Kenara çekilip yol verme"
    hareketini bu üretir. YALNIZ komşu YAKLAŞIRKEN açılır (uzaklaşırken
    gereksiz), ve yaklaşma hızıyla orantılıdır.

    NEDEN KENDI HIZIMIZLA DEĞİL, YAKLAŞMA HIZIYLA ÖLÇEKLİYORUZ:
    repodaki ca_core._tangent teğeti KENDİ hızımıza bağlıyor ve biz
    asılı duruyorsak (hız ~0) teğeti hiç açmıyor. Oysa asılı dururken
    üstümüze gelen bir uçak, teğete en çok ihtiyaç duyduğumuz durum.

    HEP AYNI TARAFA: teğet yönü sabit (radyalin -90°'si). Havacılıktaki
    "sağa geç" kuralı gibi. Sebebi kritik — iki otonom uçak karşılaşırsa
    ikisi de aynı kuralı uygulayınca DOĞAL OLARAK ayrışırlar. Taraf
    duruma göre seçilseydi ikisi de aynı yönü seçip birbirini kovalardı.

    Args:
        kendi: (kuzey, doğu) kendi konumumuz.
        komsular: [(kuzey, doğu, kapanma_hizi), ...]. kapanma_hizi pozitifse
            komşu yaklaşıyor (m/s); negatifse uzaklaşıyor.
        d0: itmenin başladığı yarıçap (m).
        hard: itmenin doyuma ulaştığı yarıçap (m).
        f_sat: doygunluktaki itme büyüklüğü (m).
        k_tan: teğet bileşenin radyale oranı. 0 = kapalı.

    Returns:
        (kuzey, doğu) toplam itme vektörü, metre.
    """
    tk = td = 0.0
    for komsu in komsular:
        kk, kd = komsu[0], komsu[1]
        kapanma = komsu[2] if len(komsu) > 2 else 0.0
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
        ux, uy = dk / d, dd / d
        tk += buyukluk * ux
        td += buyukluk * uy
        if k_tan > 0.0 and kapanma > 0.0:
            w = min(1.0, kapanma / _REF_KAPANMA_MS)
            f = k_tan * w * buyukluk
            # Radyalin -90°'si. SABİT taraf — yukarıdaki gerekçe.
            tk += f * uy
            td += f * (-ux)
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
        # Teğet bileşen oranı. 0 = kapalı (yalnız radyal). 0.8 -> itme
        # yönü radyalden ~39° sapar, yani uçak geri geri kaçmak yerine
        # belirgin şekilde KENARA çekilir.
        self.declare_parameter('k_tan', 0.8)

        self._aid = int(self.get_parameter('agent_id').value)
        self._d0 = float(self.get_parameter('d0_m').value)
        self._hard = float(self.get_parameter('hard_m').value)
        self._f_sat = float(self.get_parameter('f_sat_m').value)
        self._max_itme = float(self.get_parameter('max_itme_m').value)
        self._bayat = float(self.get_parameter('bayat_s').value)
        self._k_tan = float(self.get_parameter('k_tan').value)
        if not (0.0 < self._hard < self._d0):
            raise ValueError('hard_m < d0_m olmalı')

        # KONTROL YOLU QoS: px4_bridge bu konuyu RELIABLE dinliyor,
        # esp32_bridge de varsayilan derinlik 10 (RELIABLE) ile yaziyor.
        # Ilk surumde SENSOR_DATA (BEST_EFFORT) kullanilmisti ve ROS
        # uyardi: "requesting incompatible QoS. No messages will be sent."
        # Yani dugum dogru hesaplayip yayinlayacak, px4_bridge HIC
        # almayacakti — sessiz ariza. Kanitlanmis olanla ayni tutuluyor.
        kontrol_qos = 10
        # Telemetri yolu BEST_EFFORT kalabilir: RELIABLE yayinci ile
        # BEST_EFFORT abone uyumludur, tersi degil.
        qos = QoSPresetProfiles.SENSOR_DATA.value
        self._kendi = None            # (kuzey, doğu)
        self._komsu = {}              # id -> (kuzey, doğu, zaman)
        self._kapanma = {}            # id -> yaklaşma hızı (m/s)
        self._son_itme = (0.0, 0.0)
        self._ham = None              # son gelen ham setpoint

        self._pub = self.create_publisher(
            AgentSetpoint, f'/drone_{self._aid}/control/setpoint', kontrol_qos)
        self.create_subscription(
            AgentSetpoint, f'/drone_{self._aid}/control/setpoint/raw',
            self._on_raw, kontrol_qos)
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

        # 10 Hz: komşu 4 m/s ile yaklaşsa tik başına 0.4 m ilerler — itme
        # yeterince sık güncellenir. Daha hızlısı mesh'e değil yalnız yerel
        # ROS'a yük bindirir, ama 10 Hz zaten fazlasıyla yeterli.
        self.create_timer(0.1, self._tik)
        self.create_timer(1.0, self._durum_yaz)
        self.get_logger().info(
            f'basit_kacinma başladı: agent={self._aid} '
            f'd0={self._d0} hard={self._hard} f_sat={self._f_sat} '
            f'max={self._max_itme} k_tan={self._k_tan}')

    # --- girişler ----------------------------------------------------------
    def _on_kendi(self, m: AgentStatus) -> None:
        self._kendi = (m.pos_x, m.pos_y)

    def _on_komsu(self, nid: int, m: AgentStatus) -> None:
        """Komşu konumunu ve YAKLAŞMA HIZINI günceller.

        Yaklaşma hızı, komşunun bildirdiği hızdan DEĞİL mesafenin
        değişiminden türetiliyor. Sebebi: mesh'in hız alanını güvenilir
        taşıdığını doğrulamadık, ama konumu taşıdığını ölçtük. Mesafe
        farkı ikimizin hareketini birden kapsar, yani biz de hareket
        etsek doğru çalışır.
        """
        t = self._simdi()
        yeni = (m.pos_x, m.pos_y)
        onceki = self._komsu.get(nid)
        if onceki is not None and self._kendi is not None:
            dt = t - onceki[2]
            if 0.02 < dt < 2.0:
                eski_d = math.hypot(self._kendi[0] - onceki[0],
                                    self._kendi[1] - onceki[1])
                yeni_d = math.hypot(self._kendi[0] - yeni[0],
                                    self._kendi[1] - yeni[1])
                ham = (eski_d - yeni_d) / dt          # + ise yaklaşıyor
                # Alçak geçiren süzgeç: tek örneklik GPS gürültüsü teğeti
                # rastgele tetiklemesin.
                onceki_k = self._kapanma.get(nid, 0.0)
                self._kapanma[nid] = 0.7 * onceki_k + 0.3 * ham
        self._komsu[nid] = (yeni[0], yeni[1], t)

    def _simdi(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    # --- asıl iş -----------------------------------------------------------
    def _on_raw(self, msg: AgentSetpoint) -> None:
        """Ham hedefi saklar. İşi zamanlayıcı yapar — sebebi aşağıda."""
        self._ham = msg

    def _tik(self) -> None:
        """Kaçınmayı SÜREKLİ hesaplar ve yayınlar.

        NEDEN ZAMANLAYICI, NEDEN GELEN MESAJ DEĞİL: esp32_bridge setpoint'i
        OLAY BAZLI yayınlıyor — her guided 'goto' komutunda bir kez, yani
        görevde ~10 saniyede bir. Kaçınmayı gelen mesaja bağlarsak komşu
        yaklaşırken hiçbir itme hesaplanmaz ve bir sonraki goto'ya kadar
        kör kalırız. Kaçınma sürekli çalışmak zorunda.

        HER TİK BİR SETPOINT YAYINLAR (ham hedef geldiyse). Sessizce
        düşürmek px4_bridge'in akışını kesmek demektir ve PX4 OFFBOARD'dan
        düşer — yani kaçınmadaki bir hata uçağı failsafe'e sokardı.
        Şüpheli her durumda ham setpoint AYNEN geçer.
        """
        msg = self._ham
        if msg is None:
            return                    # henüz hedef yok; px4_bridge kendi tutuyor

        cik = msg
        itme = (0.0, 0.0)

        if self._kendi is not None and msg.position_valid:
            t = self._simdi()
            taze = [(k, d, self._kapanma.get(nid, 0.0))
                    for nid, (k, d, ts) in self._komsu.items()
                    if t - ts <= self._bayat]
            if taze:
                # KELEPÇE _guncel_itme icinde uygulaniyor: APF
                # carpismasizligi garanti etmez, sapma her kosulda sinirli.
                itme = self._guncel_itme()
                buy = math.hypot(*itme)
                if buy > 1e-3:
                    # deepcopy: alanları tek tek setattr ile kopyalamak iç
                    # içe alanlarda sessizce bozulabilir. Mesajı YERİNDE
                    # değiştirmek de olmaz — aynı nesneyi tutan başka
                    # aboneler etkilenir.
                    cik = copy.deepcopy(msg)
                    cik.x = msg.x + itme[0]
                    cik.y = msg.y + itme[1]
                    # z'ye DOKUNULMUYOR — irtifa ayrımı yedek garantimiz.
                    cik.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
                    cik.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
                    cik.source_module = 'basit_kacinma'

        self._son_itme = itme
        self._pub.publish(cik)

    def _guncel_itme(self):
        """Anlik itmeyi hesaplar — ham hedef OLMASA DA.

        Asama-1 gozlem testi icin sart: remap yapilmadan dugum hicbir
        setpoint yayinlamaz, ama itmenin dogru hesaplandigini gormemiz
        gerekir. Ilk surumde itme yalniz hedef varken hesaplaniyordu ve
        gozlem modunda hep 0.00 goruluyordu.
        """
        if self._kendi is None:
            return (0.0, 0.0)
        t = self._simdi()
        taze = [(k, d, self._kapanma.get(nid, 0.0))
                for nid, (k, d, ts) in self._komsu.items()
                if t - ts <= self._bayat]
        if not taze:
            return (0.0, 0.0)
        it = itme_vektoru(self._kendi, taze, self._d0, self._hard,
                          self._f_sat, self._k_tan)
        buy = math.hypot(*it)
        if buy > self._max_itme:
            it = (it[0] * self._max_itme / buy, it[1] * self._max_itme / buy)
        return it

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
            kap = self._kapanma.get(nid, 0.0)
            satir.append(f'd{nid}={mesafe:.1f}m/{kap:+.1f}ms'
                         + ('(BAYAT)' if yas > self._bayat else ''))
        it = self._guncel_itme()
        durum = 'AKTIF' if self._ham is not None else 'gözlem'
        if satir:
            self.get_logger().info(
                f'[{durum}] komşu: ' + ' '.join(satir)
                + f'  itme=({it[0]:+.2f},{it[1]:+.2f}) |{math.hypot(*it):.2f}|m',
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
