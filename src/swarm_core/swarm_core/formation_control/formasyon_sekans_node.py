# Copyright 2026 Yelpence
"""Formasyon geçiş testi sekans düğümü — uçak-içi tarif kaynağı.

⚠️ GEÇİCİ TEST APARATI (28 Ağustos). mission1 zinciri sahaya alındığında
SİLİNECEK; kalıcı tarif üreticisi `mission1_node` → `path_planner`'dır.
Bu düğüm o zincirin yerde test edilemeyen kısmını (mission_fsm'in
IN_SWARM şartı → kalkis_olayla=true zorunluluğu) AÇMADAN, formasyon
geçişlerini SSH'siz uçurabilmek için var: YKİ'nin tek rolü "başlat".

NASIL ÇALIŞIR
    guided ARM → esp32_bridge uçakta EVENT_MISSION_STARTED üretir (mevcut
    mekanizma) → bu düğüm olayı duyar → kadrodaki HERKES hedef irtifaya
    çıkana kadar bekler (kalkış kapısı) → t0'dan itibaren zamanlanmış
    fazları (çizgi → ok başı → V) FormationCommand olarak
    /swarm/internal/formation/target'a basar → esp32_bridge lider
    kapısı + mesh + loopback → formation_node'lar uçakları sürer.

ÜÇ UÇAKTA DA KOŞAR (sıcak yedek) — mission1 orchestrator ile aynı desen:
durum makinesi herkeste ilerler, YAYINI YALNIZ LİDER yapar
(`_lider_id == agent_id`; ElectionResult'tan öğrenilir). Lider düşerse
yeni liderin sekansı kendi kaldığı fazdan yayına girer.

🔴 LİDER KAPISI BURADA, ÜRETİCİDE — köprü kapısı YETMEZ (G0'da, 28 Ağu
canlı uçakta ölçüldü): `ic_dis_kopru` `formation/target`'ı internal →
public KOŞULSUZ aktarıyor. Yayını köprü kapısına bırakan bir takipçi,
kendi tarifini kopru üzerinden KENDİ formation_node'una ulaştırır ve
liderin mesh'ten gelen tarifiyle yarıştırırdı. Uçmuş tasarım da aynı
sebeple üretici tarafında kapılı (orchestrator.py:334 is_leader).

⚠️ SÖZLEŞME: bu düğüm `suru_dugumleri`'nde `sekans` anahtarı AÇIKKEN her
guided ARM bir test başlangıcıdır. Normal uçuşa dönmeden anahtar
KALDIRILMALI (dosyadan `sekans` sil + restart). Bu bilinçli bir takas:
"teste özel ikinci bir başlat komutu" mesh'e yeni paket tipi ve dört
karta firmware flash'ı gerektirirdi (bkz. KARARLAR.md KARAR-09 notu).

İPTAL YOLLARI (bu düğüm hiçbirini engellemez):
    kumanda kill / YKİ land-RTL — AgentCommand kanalı, formasyon-sürer
    remap'ından etkilenmez (baslat.sh notu). Ayrıca 26 Ağustos uçuşunda
    ölçüldü: RTL, formasyon yayını sürerken uçağı sorunsuz indirdi.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    SystemEvent,
)

from . import formasyon_sekans_cekirdek as cek

# İÇ VERİYOLU SÖZLEŞMESİ: bütün internal yayıncılar RELIABLE
# (ic_dis_kopru.py:79-83, 15 Ağustos taraması). İlk yazım BEST_EFFORT
# yayınlıyordu ve G0'da (28 Ağu) canlı uçakta yakalandı: kopru'nun
# RELIABLE aboneliği "incompatible QoS" deyip HİÇ almıyordu. Köprü
# (esp32_bridge) BEST_EFFORT abone olduğu için RELIABLE yayın ikisiyle
# de uyumlu.
_IC_YAYIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# Mesh kaynaklı konuların abonelik profili (esp32_bridge _MESH_QOS ile aynı).
_MESH_ABONE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# ElectionResult QoS'u consensus_node/esp32_bridge ile birebir aynı olmak
# ZORUNDA (RELIABLE + TRANSIENT_LOCAL) — form_yayinla.sh:29-34 tuzağının
# dersi: profil uyuşmazsa konu SESSİZCE boş kalır.
_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# Durumlar — sıralı akış, geri dönüş yok (test aparatı basit kalsın).
_BEKLEME = 'BEKLEME'      # olay bekleniyor
_HAZIRLIK = 'HAZIRLIK'    # olay geldi, kadro irtifaya çıksın
_SEKANS = 'SEKANS'        # fazlar yayında
_BITTI = 'BITTI'          # çizelge bitti, yayın durdu (uçaklar son
#                           formasyonda asılı — formation_node son tarifi
#                           tutar; inişi YKİ/kumanda verir)
_IPTAL = 'IPTAL'          # kalkış kapısı zaman aşımı — hiç başlamadı


class FormasyonSekansNode(Node):
    """Zamanlanmış formasyon tarifi yayıncısı (geçici test aparatı)."""

    def __init__(self) -> None:
        super().__init__('formasyon_sekans')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('kadro', [1, 2, 3])
        self.declare_parameter('aralik_m', 7.0)
        self.declare_parameter('irtifa_m', 8.0)
        # heading_otomatik=true: heading kalkış diziliminden türetilir
        # (PCA — cekirdek.otomatik_heading_deg) ve kuru testin haritada
        # gösterdiğiyle aynı kuraldır. false → heading_deg aynen alınır.
        self.declare_parameter('heading_otomatik', True)
        self.declare_parameter('heading_deg', 0.0)
        # Varsayilanlar ucus_ayarlari.SEKANS_* ile AYNI TUTULUR; sahada
        # gecerli degerler baslat.sh'in env'inden gelir (tek kaynak).
        # 25/25/25 operator karari (28 Agu aksam) — kurulumun 25 sn'ye
        # sigip sigmadigini kuru test gercek yerlesimle denetliyor.
        self.declare_parameter('fazlar', ['cizgi', 'okbasi', 'v'])
        self.declare_parameter('faz_sure_s', [25.0, 25.0, 25.0])
        self.declare_parameter('yayin_hz', 2.0)
        # Kalkış kapısı: hedef irtifanın bu oranına ulaşmak yeter.
        # 1.0 yapılmaz — EKF z ile origin irtifası arasında ~1 m fark
        # ölçüldü (26 Ağustos: tarif -8, gerçek 8,8-9,3 m).
        self.declare_parameter('kalkis_esik_orani', 0.8)
        self.declare_parameter('kalkis_zaman_asimi_s', 90.0)
        # Faz GEÇİŞİ ancak bütün kadro verisi tazeyken yapılır: körken
        # reshape başlatmak, kaçınmanın göremediği bir yakınlaşma
        # üretebilir. Tutma süresi tavanı aşarsa geçişler DONDURULUR
        # (mevcut formasyon güvenli, sekanssız devam tehlikeli değil).
        self.declare_parameter('komsu_taze_s', 2.0)
        self.declare_parameter('gecis_bekleme_tavani_s', 15.0)
        # İlk faz kurulumu rastgele dağılımdan toparlanır (uzun yol,
        # boş alan) — seyir hızına yakın. Sonraki geçişler dar geçitli
        # (OKBAŞI→V'de 4,95 m) — mission1'in QR morph'u gibi yavaş.
        self.declare_parameter('kurulum_hiz_mps', 2.5)
        self.declare_parameter('gecis_hiz_mps', 1.5)
        # Macar maliyeti formation_node/köprü ile aynı geometriden
        # hesaplansın diye kanat açısı da aynı kaynaktan geçirilir
        # (baslat.sh KANAT_ALFA_DEG — üç tüketiciye de aynı değer gider).
        self.declare_parameter('kanat_alfa_deg', 45.0)
        # 🔴 YALNIZ G0 YER TESTİ: kalkış kapısının İRTİFA şartını atlar —
        # uçaklar yerdeyken (/ws/gozlem takılı, formation_node çıkışı uçağa
        # gitmez) tarif zinciri uçurulmadan ölçülebilsin. UÇUŞTA ASLA true
        # OLMAZ: yerde duran uçak kadroya dahil edilip formasyon merkezini
        # çarpıtır. baslat.sh bu parametreyi GEÇMİYOR; yalnız elle, G0
        # oturumunda verilir.
        self.declare_parameter('yer_testi_irtifa_atla', False)

        gp = self.get_parameter
        self._agent_id = int(gp('agent_id').value)
        self._kadro = sorted(int(a) for a in gp('kadro').value)
        self._aralik_m = float(gp('aralik_m').value)
        self._irtifa_m = float(gp('irtifa_m').value)
        self._heading_otomatik = bool(gp('heading_otomatik').value)
        self._heading_deg = float(gp('heading_deg').value)
        self._yayin_hz = float(gp('yayin_hz').value)
        self._kalkis_esik = float(gp('kalkis_esik_orani').value)
        self._kalkis_zaman_asimi = float(gp('kalkis_zaman_asimi_s').value)
        self._komsu_taze_s = float(gp('komsu_taze_s').value)
        self._gecis_tavani_s = float(gp('gecis_bekleme_tavani_s').value)
        self._kurulum_hiz = float(gp('kurulum_hiz_mps').value)
        self._gecis_hiz = float(gp('gecis_hiz_mps').value)
        self._alfa_deg = float(gp('kanat_alfa_deg').value)
        self._irtifa_atla = bool(gp('yer_testi_irtifa_atla').value)
        if self._irtifa_atla:
            self.get_logger().warn(
                'yer_testi_irtifa_atla=TRUE — kalkis kapisinin irtifa sarti '
                'VE olay bekleme ATLANIYOR. Bu yapilandirmayla UCULMAZ '
                '(yalniz G0 yer gozlemi, /ws/gozlem takiliyken).'
            )

        # Hatalı faz listesiyle SESSİZCE boş koşmak yok: plan açılışta
        # kurulur, bozuksa düğüm exception ile ölür ve baslat.sh logunda
        # görünür (uçuş öncesi G0'da yakalanır).
        self._plan = cek.faz_plani(
            [str(f) for f in gp('fazlar').value],
            [float(s) for s in gp('faz_sure_s').value],
        )

        # G0'da olay HIC BASILMAZ — bilerek. SystemEvent'i agent_fsm de
        # duyuyor ve ARM zincirini baslatiyor; yerde pervaneler takiliyken
        # istenmez. Olay→sekans sicramasi ayrica dogrulanmis durumda
        # (28 Agu G0-1: olay alindi, BEKLEME→HAZIRLIK gecisi loglandi).
        # FSM ise G0'da CALISMAK ZORUNDA: AgentStatus'un yayincisi o
        # (agent_fsm_node.py:122) — ilk denemede oldurulunce butun durum
        # zinciri sustu ve kalkis kapisi 'veri HIC gelmedi' dedi.
        self._durum = _HAZIRLIK if self._irtifa_atla else _BEKLEME
        self._olay_t: float | None = None
        self._t0: float | None = None
        self._merkez: tuple[float, float] | None = None
        self._faz_idx = 0
        self._faz_bas: float | None = None
        self._gecis_bekleme_bas: float | None = None
        self._gecisler_donduruldu = False
        self._faz_atama = None          # (agent_ids sıralı, ofsetler)
        self._seq = 0

        self._konum: dict[int, AgentStatus] = {}
        self._konum_rx: dict[int, float] = {}
        # Lider kimliği — 0 = bilinmiyor, kimse yayınlamaz (güvenli taraf:
        # tarif akmazsa uçaklar guided kalkış noktalarında asılı kalır).
        self._lider_id = 0

        self._cmd_pub = self.create_publisher(
            FormationCommand, '/swarm/internal/formation/target',
            _IC_YAYIN_QOS,
        )

        # Olay aboneliği agent_fsm ile birebir aynı (iki konu, depth 10):
        # EVENT_MISSION_STARTED'ı üreten esp32_bridge internal'a basıyor,
        # ic_dis_kopru public'e taşıyor — hangisi önce gelirse.
        for konu in (
            '/swarm/internal/events/system',
            '/swarm/public/events/system',
        ):
            self.create_subscription(SystemEvent, konu, self._on_olay, 10)

        # Lider bilgisi: internal = kendi consensus'umuz seçince,
        # public = mesh'ten (esp32_bridge TIP_ELECTION'ı çözüp basıyor).
        for konu in (
            '/swarm/internal/election/result',
            '/swarm/public/election/result',
        ):
            self.create_subscription(
                ElectionResult, konu, self._on_secim, _ELECTION_QOS
            )

        # Kadro konumları: public droneN/status hem komşuları (mesh) hem
        # kendimizi (ic_dis_kopru yerel döngüsü) kapsar. Kendi internal
        # akışımız yedek — kopru gecikirse kendi verimiz yine akar.
        for a in self._kadro:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{a}/status',
                self._durum_cb(a),
                _MESH_ABONE_QOS,
            )
        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._agent_id}/status',
            self._durum_cb(self._agent_id),
            _MESH_ABONE_QOS,
        )

        self.create_timer(1.0 / self._yayin_hz, self._tick)

        adlar = ' -> '.join(cek.tip_adi(t) for t, _s in self._plan)
        self.get_logger().info(
            f'formasyon_sekans hazir (GECICI TEST APARATI): kadro='
            f'{self._kadro} aralik={self._aralik_m} m irtifa='
            f'{self._irtifa_m} m sekans=[{adlar}] toplam='
            f'{cek.toplam_sure_s(self._plan):.0f} s — '
            f'guided ARM olayi bekleniyor'
        )

    # ------------------------------------------------------------------
    def _simdi(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def _durum_cb(self, aid: int):
        def _cb(msg: AgentStatus) -> None:
            self._konum[aid] = msg
            self._konum_rx[aid] = self._simdi()
        return _cb

    def _on_secim(self, msg: ElectionResult) -> None:
        yeni = int(msg.new_leader_id)
        if yeni != self._lider_id:
            self.get_logger().info(
                f'lider degisti: {self._lider_id} -> {yeni} '
                f'(yayin {"BIZDE" if yeni == self._agent_id else "onda"})'
            )
            self._lider_id = yeni

    def _on_olay(self, msg: SystemEvent) -> None:
        if msg.event_type != SystemEvent.EVENT_MISSION_STARTED:
            return
        if msg.target_agent_id not in (0, self._agent_id):
            return
        if self._durum != _BEKLEME:
            return
        self._olay_t = self._simdi()
        self._durum = _HAZIRLIK
        self.get_logger().info(
            'gorev basladi olayi alindi — kadro irtifaya cikana kadar '
            f'bekleniyor (esik {self._kalkis_esik * self._irtifa_m:.1f} m, '
            f'zaman asimi {self._kalkis_zaman_asimi:.0f} s)'
        )

    # ------------------------------------------------------------------
    def _kadro_verisi(self, simdi: float):
        """Kalkış kapısı için üç sözlüğü mevcut durumdan derler."""
        irtifalar = {}
        yaslar = {}
        senkron = {}
        for a in self._kadro:
            st = self._konum.get(a)
            if st is None:
                continue
            yaslar[a] = simdi - self._konum_rx.get(a, 0.0)
            # NED: pos_z aşağı pozitif → irtifa = -pos_z (origin'e göre).
            irtifalar[a] = -float(st.pos_z)
            senkron[a] = bool(st.origin_synced)
        return irtifalar, yaslar, senkron

    def _konumlar_xy(self) -> dict[int, tuple[float, float]]:
        return {
            a: (float(self._konum[a].pos_x), float(self._konum[a].pos_y))
            for a in self._kadro
            if a in self._konum
        }

    def _tick(self) -> None:
        simdi = self._simdi()
        if self._durum == _HAZIRLIK:
            self._hazirlik_tik(simdi)
        elif self._durum == _SEKANS:
            self._sekans_tik(simdi)

    # ------------------------------------------------------------------
    def _hazirlik_tik(self, simdi: float) -> None:
        if self._olay_t is None:
            # G0 yolu: olay yok, zaman asimi sayaci ilk tik'te baslar.
            self._olay_t = simdi
        irtifalar, yaslar, senkron = self._kadro_verisi(simdi)
        hazir, eksikler = cek.kalkis_hazir_mi(
            self._kadro, irtifalar, yaslar, senkron,
            self._irtifa_m, self._kalkis_esik, self._komsu_taze_s,
            irtifa_sart=not self._irtifa_atla,
        )
        if hazir:
            self._sekansi_baslat(simdi)
            return
        if simdi - self._olay_t > self._kalkis_zaman_asimi:
            self._durum = _IPTAL
            self.get_logger().error(
                'KALKIS KAPISI ZAMAN ASIMI — sekans HIC BASLAMADI. '
                f'Eksikler: {"; ".join(eksikler)}. Ucaklar oldugu yerde '
                'asili; inisi YKI/kumanda verir. Yeni deneme icin '
                'konteyner restart gerekir.'
            )
            return
        self.get_logger().warn(
            f'kalkis bekleniyor: {"; ".join(eksikler)}',
            throttle_duration_sec=5.0,
        )

    def _sekansi_baslat(self, simdi: float) -> None:
        konumlar = self._konumlar_xy()
        self._merkez = cek.agirlik_merkezi(konumlar)
        if self._heading_otomatik:
            self._heading_deg = cek.otomatik_heading_deg(konumlar)
        self._t0 = simdi
        self._faz_idx = 0
        self._faz_bas = simdi
        self._faz_atama = cek.atama(
            self._plan[0][0], konumlar, self._merkez,
            self._heading_deg, self._aralik_m, self._alfa_deg,
        )
        self._durum = _SEKANS
        self.get_logger().info(
            f'SEKANS BASLADI: merkez=({self._merkez[0]:+.1f},'
            f'{self._merkez[1]:+.1f}) heading={self._heading_deg:.1f} '
            f'(otomatik={self._heading_otomatik}) — '
            f'faz 0: {cek.tip_adi(self._plan[0][0])} '
            f'atama={self._faz_atama[0]}'
        )

    # ------------------------------------------------------------------
    def _sekans_tik(self, simdi: float) -> None:
        tip, sure = self._plan[self._faz_idx]
        if simdi - self._faz_bas >= sure and not self._gecisler_donduruldu:
            if self._faz_idx + 1 >= len(self._plan):
                self._durum = _BITTI
                self.get_logger().info(
                    'SEKANS BITTI — yayin durdu. Ucaklar son formasyonda '
                    'asili (formation_node son tarifi tutar); inis '
                    'YKI/kumandadan.'
                )
                return
            if self._gecise_izin_var(simdi):
                self._faza_gec(simdi)
            elif (self._gecis_bekleme_bas is not None
                    and simdi - self._gecis_bekleme_bas
                    > self._gecis_tavani_s):
                # Kadro verisi tazelenmedi: körken reshape RİSK, mevcut
                # formasyonda kalmak DEĞİL. Geçişler kalıcı durdurulur,
                # yayın mevcut fazda sürer — uçaklar güvenli dizilişte.
                self._gecisler_donduruldu = True
                self.get_logger().error(
                    'GECISLER DONDURULDU: kadro verisi '
                    f'{self._gecis_tavani_s:.0f} s icinde tazelenmedi. '
                    'Mevcut formasyon korunuyor; testi bitirip indirin.'
                )
        self._yayinla(simdi)

    def _gecise_izin_var(self, simdi: float) -> bool:
        _irt, yaslar, _snk = self._kadro_verisi(simdi)
        bayat = [
            a for a in self._kadro
            if yaslar.get(a, float('inf')) > self._komsu_taze_s
        ]
        if not bayat:
            self._gecis_bekleme_bas = None
            return True
        if self._gecis_bekleme_bas is None:
            self._gecis_bekleme_bas = simdi
        self.get_logger().warn(
            f'faz gecisi bekletiliyor — bayat veri: {bayat}',
            throttle_duration_sec=3.0,
        )
        return False

    def _faza_gec(self, simdi: float) -> None:
        self._faz_idx += 1
        self._faz_bas = simdi
        self._gecis_bekleme_bas = None
        tip = self._plan[self._faz_idx][0]
        konumlar = self._konumlar_xy()
        # Reshape ataması O ANKİ konumlardan — formation_node'un dağıtık
        # ataması da aynı girdiyle aynı Macar'ı koşacak (uyuşma → yerel).
        self._faz_atama = cek.atama(
            tip, konumlar, self._merkez,
            self._heading_deg, self._aralik_m, self._alfa_deg,
        )
        self.get_logger().info(
            f'FAZ GECISI -> {cek.tip_adi(tip)} '
            f'(t0+{simdi - self._t0:.0f} s) atama={self._faz_atama[0]}'
        )

    # ------------------------------------------------------------------
    def _yayinla(self, simdi: float) -> None:
        # LİDER KAPISI (üretici tarafı — dosya başlığındaki gerekçe).
        # Durum makinesi yukarıda zaten ilerledi; susan yalnız yayın.
        # Devir anında yeni lider kendi fazından kesintisiz devam eder.
        if self._lider_id != self._agent_id:
            self.get_logger().warn(
                f'lider degiliz (lider={self._lider_id}) — tarif yayini '
                f'susturuldu, durum makinesi sicak yedekte ilerliyor',
                throttle_duration_sec=10.0,
            )
            return
        tip, _sure = self._plan[self._faz_idx]
        agent_ids, ofsetler = self._faz_atama
        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._seq
        self._seq += 1
        msg.formation_type = int(tip)
        msg.center_x = float(self._merkez[0])
        msg.center_y = float(self._merkez[1])
        msg.center_z = -abs(self._irtifa_m)
        msg.heading_deg = float(self._heading_deg)
        msg.spacing_m = float(self._aralik_m)
        msg.use_current_centroid = False
        msg.use_current_altitude = False
        msg.rotate_towards_target = False
        msg.hold_after_reached = True
        msg.agent_ids = [int(a) for a in agent_ids]
        msg.offset_x = [float(o[0]) for o in ofsetler]
        msg.offset_y = [float(o[1]) for o in ofsetler]
        msg.offset_z = [float(o[2]) for o in ofsetler]
        msg.position_tolerance_m = 0.0
        msg.heading_tolerance_deg = 0.0
        msg.timeout_sec = 0.0
        # İlk faz = kurulum (uzun yol, boş alan); sonrakiler = dar geçit.
        msg.max_speed_mps = (
            self._kurulum_hiz if self._faz_idx == 0 else self._gecis_hiz
        )
        msg.source_module = 'formasyon_sekans'
        self._cmd_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FormasyonSekansNode()
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
