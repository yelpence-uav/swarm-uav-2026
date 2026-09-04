#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""Algı sonuçlarını JSON'a yazar — kamera sayfası onu gösterir.

NEDEN VAR (27 Ağustos 2026, operatör itirazı)
---------------------------------------------
"abi böyle elle neden yapıyorum, neden direkt qr okuma ve renk okuma
çalışmıyor şuanda."

Zincir zaten çalışıyordu — renk tespiti 5,5 Hz yayın yapıyordu. Eksik olan
şey sonucu GÖRMEKTİ: `ros2 topic echo` yazmak gerekiyordu. Operatör zaten
canlı video sayfasına bakıyor; QR metni ve renk tespiti orada çıkmalı.

KÖPRÜ NEDEN DOSYA: sayfa host'ta koşuyor ve ROS'u yok; ROS konteynerin
içinde. Arada `/ws` (konteyner) = `~/yelpence_ws` (host) bind mount'u var.
Bu düğüm oraya JSON yazıyor, sayfa okuyor. Ek bağımlılık yok, ek port yok.

YAZMA ATOMİK: geçici dosyaya yazıp `rename` ediyoruz. Sayfa 5 Hz okuyor;
yarım yazılmış bir dosyayı okursa JSON çözülmez ve kart boşalırdı.
"""

import json
import math
import os
import time

from mavros_msgs.msg import Altitude

from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParametersAtomically

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSPresetProfiles,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import LandingZoneDetection, QRMissionData

_RELIABLE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)
_BEST_EFFORT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

_RENK_ADLARI = {0: 'bilinmiyor', 1: 'KIRMIZI', 2: 'MAVI'}

# Irtifa bu sureden eskiyse "bilinmiyor" sayilir: bayat bir irtifayi banda
# yazmak, ucak coktan baska yerdeyken o banda sure eklemek olurdu.
# 1 sn secildi cunku bu pay dogrudan HATA olarak yaziliyor: 1 m/s alcalirken
# 1 sn bayatlik, sureyi bir metre yanlis banda kaydeder. MAVROS irtifasi
# ~10 Hz akiyor, yani 1 sn = ust uste 10 kayip mesaj; bu artik titreme
# degil gercek kesintidir ve sayfada "MAVROS yok" olarak GORUNUR --
# sessizce yanlis banda yazmaktansa gorunur sekilde bosluk birakiyoruz.
_IRTIFA_BAYAT_S = 1.0

# Bant sayacina eklenecek en buyuk adim. Daha buyugu duraklamadir (surec
# askida kaldi, saat sicradi); o sureyi banda yazmak paydayi sisirir.
_EN_BUYUK_ADIM_S = 1.0


class AlgiKopru(Node):
    """QR ve iniş bölgesi sonuçlarını dosyaya yazar."""

    def __init__(self) -> None:
        super().__init__('algi_kopru')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('cikti', '/ws/algi_durum.json')
        self.declare_parameter('ayar_dosyasi', '/ws/algi_ayar.json')
        self.declare_parameter('yazma_hz', 5.0)
        self.declare_parameter('bant_m', 1.0)

        self._agent_id = self.get_parameter('agent_id').value
        self._cikti = self.get_parameter('cikti').value
        self._ayar_dosyasi = self.get_parameter('ayar_dosyasi').value
        hz = float(self.get_parameter('yazma_hz').value)
        self._bant_m = max(0.5, float(self.get_parameter('bant_m').value))

        # SON ÇÖZÜLEN QR YAPIŞKAN tutuluyor. QR kareye bir saniye girip
        # çıkıyor; anlık durum gösterilseydi operatör tam da okunduğu anda
        # ekrana bakmak zorunda kalırdı. Yaşıyla birlikte gösteriliyor.
        self._son_qr: dict | None = None
        self._qr_sayaci = 0
        self._lz: dict | None = None

        # IRTIFA — "QR'i kac metreden okudu" (4 Eylul 2026, operator istegi)
        # Sayfa QR'i gosteriyordu ama irtifayi gostermiyordu; operator
        # okumayi gorup irtifayi QGC'den GOZLE eslemek zorunda kaliyordu.
        self._irtifa_m: float | None = None
        self._irtifa_an = 0.0
        self._en_yuksek_m: float | None = None

        # BANT TABLOSU {bant_no: {'okuma': n, 'sure_s': t}}
        # YUZDE VERMIYORUZ: vision_node QR mesajini YALNIZ okuma basarili
        # olunca yayinliyor (`for res in results`), yani paydayi -- denenen
        # kare sayisini -- bilmiyoruz. Varsayilan 5 Hz'den yuzde uydurmak
        # tam da okuma dusukken yaniltirdi: QR bulunamayinca zincir 2,3
        # Hz'e duser (KAMERA.md 6.5 olcumu), yani gercek payda kucuktur ve
        # uydurma yuzde oldugundan kotu gorunur. Onun yerine OKUMA/SN:
        # paydasi gercek gecen sure, banttan banda dogrudan karsilastirilir.
        self._bantlar: dict[int, dict] = {}
        self._bant_an: float | None = None
        self._son_sifirla = None

        self.create_subscription(
            QRMissionData, '/swarm/internal/perception/qr_data',
            self._qr_geldi, _RELIABLE_QOS)
        self.create_subscription(
            LandingZoneDetection,
            f'/drone_{self._agent_id}/perception/landing_zone',
            self._lz_geldi, _BEST_EFFORT_QOS)

        # SENSOR_DATA QoS SART. MAVROS telemetriyi BEST_EFFORT yayinlar;
        # RELIABLE bir abone hicbir sey almaz ve HATA DA VERMEZ -- belirti
        # yalnizca "irtifa hep bos" olur. (TUZAKLAR 2.1; bu tuzaga bu
        # projede daha once dusuldu.)
        self.create_subscription(
            Altitude, f'/drone_{self._agent_id}/mavros/altitude',
            self._irtifa_geldi, QoSPresetProfiles.SENSOR_DATA.value)

        # ESIK AYARI SAYFADAN — 27 Agustos 2026, operator istegi:
        # "en ufak rengi goruyor, kirmizi ve mavi gormesi lazim ve rengin
        # dairesel olmasi lazim". Dogru esik pede, irtifaya ve isiga bagli;
        # ancak sahada BAKARAK bulunur. Sayfa bir dosya yaziyor, bu dugum
        # onu izleyip vision_node'un parametrelerini set ediyor.
        # Neden dosya: sayfa host'ta ve ROS'u yok (bkz. sinifin baslik notu).
        # ATOMIK: tek tek set edilirse her parametre ayri geri cagri
        # tetikler ve arada KARISIK esik cifti olusur (alan gevsek ama
        # dairesellik hala siki gibi). Kisa surer ama o anin karesi yanlis
        # degerlendirilir. Atomik cagri hepsini tek seferde uygular.
        self._ayar_istemci = self.create_client(
            SetParametersAtomically, '/vision_node/set_parameters_atomically')
        self._son_ayar: dict | None = None

        self.create_timer(1.0 / hz, self._yaz)
        self.create_timer(1.0, self._ayari_izle)
        self.get_logger().info(
            f'AlgiKopru: agent_id={self._agent_id} -> {self._cikti}')

    def _qr_geldi(self, m: QRMissionData) -> None:
        # Irtifa OKUMANIN GELDIGI ANDA mandallaniyor. Sonradan zaman
        # damgasindan eslemek de olurdu ama sayfa canli bakiyor; alcalirken
        # bir saniyelik gecikme bir metre hata demek.
        simdi = time.time()
        self._qr_sayaci += 1
        h = self._irtifa_gecerli(simdi)
        bant = self._bant_no(h)
        if bant is not None:
            self._bant(bant)['okuma'] += 1
            if self._en_yuksek_m is None or h > self._en_yuksek_m:
                self._en_yuksek_m = h
        self._son_qr = {
            'an': simdi,
            'irtifa_m': round(h, 2) if h is not None else None,
            'detected': bool(m.detected),
            'decoded': bool(m.decoded),
            'valid': bool(m.valid),
            'raw_text': m.raw_text,
            'error_message': m.error_message,
            'qr_id': int(m.qr_id),
            'qr_seq': int(m.qr_seq),
            'team_id': m.team_id,
            'confidence': round(float(m.confidence), 3),
            'image_x': round(float(m.image_x), 4),
            'image_y': round(float(m.image_y), 4),
        }

    def _lz_geldi(self, m: LandingZoneDetection) -> None:
        self._lz = {
            'an': time.time(),
            'zone_detected': bool(m.zone_detected),
            'zone_count': int(m.zone_count),
            'renkler': [_RENK_ADLARI.get(c, str(c)) for c in m.zone_colors],
            # `zone_confidence` DAIRESELLIKTIR: kontur alani / en kucuk
            # cevreleyen dairenin alani. 1.0 = kusursuz daire, kare 0.64.
            'dairesellik': [round(float(g), 3) for g in m.zone_confidence],
            'yaricap_m': [round(float(r), 2) for r in m.zone_radius_m],
            'primary_valid': bool(m.primary_valid),
            'primary_color': _RENK_ADLARI.get(int(m.primary_color), '?'),
            'image_x': round(float(m.image_x), 4),
            'image_y': round(float(m.image_y), 4),
            'image_width': round(float(m.image_width), 4),
            'image_height': round(float(m.image_height), 4),
            'fov_deg': round(float(m.fov_deg), 1),
        }

    def _irtifa_geldi(self, m: Altitude) -> None:
        """MAVROS irtifasini saklar.

        `relative` = EVE gore irtifa; "kac metreden okudu" sorusunun
        cevabi budur. EKF home'u kilitlemeden once NaN gelebiliyor -- o
        zaman `local`e dusuluyor, o da yoksa ornek ATILIYOR. NaN'i sessizce
        saklamak bant tablosunu cope cevirirdi.
        """
        h = float(m.relative)
        if not math.isfinite(h):
            h = float(m.local)
        if not math.isfinite(h):
            return
        self._irtifa_m = h
        self._irtifa_an = time.time()

    def _irtifa_gecerli(self, simdi: float) -> float | None:
        """Taze ise irtifayi, degilse None doner."""
        if self._irtifa_m is None:
            return None
        if (simdi - self._irtifa_an) > _IRTIFA_BAYAT_S:
            return None
        return self._irtifa_m

    def _bant_no(self, h: float | None) -> int | None:
        """Irtifayi bant numarasina cevirir; yerdeki negatif gurultu elenir."""
        if h is None or h < 0.0:
            return None
        return int(h / self._bant_m)

    def _bant(self, no: int) -> dict:
        return self._bantlar.setdefault(no, {'okuma': 0, 'sure_s': 0.0})

    def _bandi_isle(self, simdi: float) -> None:
        """Gecen sureyi o anki irtifa bandina ekler -- PAYDA BUDUR.

        Okuma sayisi sureye bolununce okuma/sn cikiyor; boylece "10 m'de
        bir kere okudu" ile "10 m'de 20 saniyede 34 kere okudu" ayirt
        ediliyor. Ilki sans, ikincisi olcum.
        """
        onceki, self._bant_an = self._bant_an, simdi
        if onceki is None:
            return
        adim = simdi - onceki
        if not 0.0 < adim <= _EN_BUYUK_ADIM_S:
            return
        bant = self._bant_no(self._irtifa_gecerli(simdi))
        if bant is not None:
            self._bant(bant)['sure_s'] += adim

    def _bantlari_ver(self) -> list:
        """Sayfaya gidecek tablo; deger tasimayan bantlar atlanir."""
        cikti = []
        for no in sorted(self._bantlar):
            v = self._bantlar[no]
            if v['okuma'] == 0 and v['sure_s'] < 1.0:
                continue
            cikti.append({
                'alt_m': round(no * self._bant_m, 1),
                'ust_m': round((no + 1) * self._bant_m, 1),
                'okuma': v['okuma'],
                'sure_s': round(v['sure_s'], 1),
                # 1 sn'nin altinda BOLUNMUYOR: 0,2 sn'de tek okuma
                # "5 okuma/sn" gibi gorunur ve tabloyu yalanci yapardi.
                'okuma_hz': (round(v['okuma'] / v['sure_s'], 2)
                             if v['sure_s'] >= 1.0 else None),
            })
        return cikti

    def _sifirla(self) -> None:
        """Bant tablosunu ve okuma gecmisini sifirlar (sayfadaki dugme)."""
        self._bantlar.clear()
        self._bant_an = None
        self._en_yuksek_m = None
        self._qr_sayaci = 0
        self._son_qr = None

    def _ayari_izle(self) -> None:
        """Sayfanın yazdığı eşik dosyasını izler, değişince uygular."""
        try:
            with open(self._ayar_dosyasi, encoding='utf-8') as f:
                istek = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(istek, dict):
            return

        # SIFIRLAMA ONCE VE AYRI: sayfadaki dugme vision_node ayakta
        # olmasa da calismali. Sayfa artan bir sayac (Date.now()) yaziyor;
        # degistiginde tablo sifirlanir. Ayri dosya/port acmamak icin ayni
        # kopru dosyasi kullaniliyor.
        sifirla = istek.get('sifirla')
        if sifirla is not None and sifirla != self._son_sifirla:
            self._son_sifirla = sifirla
            self._sifirla()
            self.get_logger().info('bant tablosu sifirlandi')

        istek = {k: v for k, v in istek.items() if k != 'sifirla'}
        if not istek or istek == self._son_ayar:
            return
        if not self._ayar_istemci.service_is_ready():
            return                      # vision_node henuz ayakta degil

        params = []
        for ad in ('min_zone_area_frac', 'min_circularity',
                   'min_zone_area_px'):
            if ad in istek:
                params.append(Parameter(
                    name=ad,
                    value=ParameterValue(
                        type=ParameterType.PARAMETER_DOUBLE,
                        double_value=float(istek[ad]))))
        if not params:
            self._son_ayar = istek
            return

        istek_msg = SetParametersAtomically.Request()
        istek_msg.parameters = params
        self._ayar_istemci.call_async(istek_msg)
        self._son_ayar = istek
        self.get_logger().info(
            'esik istegi gonderildi: '
            + ', '.join(f'{p.name}={p.value.double_value}' for p in params))

    def _yaz(self) -> None:
        simdi = time.time()
        self._bandi_isle(simdi)
        h = self._irtifa_gecerli(simdi)
        veri = {
            'an': simdi,
            'agent_id': self._agent_id,
            'qr_sayaci': self._qr_sayaci,
            'qr': self._son_qr,
            'lz': self._lz,
            'esik': self._son_ayar,
            'irtifa_m': round(h, 2) if h is not None else None,
            'en_yuksek_okuma_m': (round(self._en_yuksek_m, 2)
                                  if self._en_yuksek_m is not None else None),
            'bant_m': self._bant_m,
            'bantlar': self._bantlari_ver(),
        }
        gecici = f'{self._cikti}.tmp'
        try:
            with open(gecici, 'w', encoding='utf-8') as f:
                json.dump(veri, f, ensure_ascii=False)
            os.replace(gecici, self._cikti)
            os.chmod(self._cikti, 0o644)      # host'taki sayfa okuyabilsin
        except OSError as e:
            self.get_logger().warn(f'yazilamadi: {e}',
                                   throttle_duration_sec=10.0)


def main(args=None) -> None:
    """Düğümü başlatır."""
    rclpy.init(args=args)
    dugum = AlgiKopru()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        dugum.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
