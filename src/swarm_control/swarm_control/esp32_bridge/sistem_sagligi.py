# Copyright 2026 Yelpence
"""Pi ana sistem sağlığı → olay. SAF mantık, ROS'suz.

NEDEN VAR (27 Agustos 2026, operator istegi)
--------------------------------------------
"Sadece ucus loglari disinda sistemle ilgili loglari da gormek istiyorum.
Mesela rpi sicakligi ... riskli bir dereceye gelirse kritik olan loglardan
olur."

VERI ZATEN TOPLANIYOR: `yelpence_izle.sh` 10 saniyede bir sicaklik, besleme
gerilimi, kisitlama bitleri, disk, bellek, yuk, konteyner ve ROS dugum
sayisini olcuyor. Ikinci bir izleme kurmuyoruz — var olani olay yoluna
bagliyoruz.

⚠️ HISTEREZIS SART. Tek esik olsaydi 70 civarinda gezinen bir sicaklik
saniyede bir olay uretir, butceyi doldurur ve GERCEK olaylarin dusmesine yol
acardi — 27 Agustos'ta `_diag_yayinla` ile tam olarak bu yasandi. Operator
de bunu kendiliginden dogru kurmustu: "50 dereceyi gecti / 45'in altina indi".

ESIK DEGERLERI OLCUME DAYANIYOR: Pi 5 bostayken 56-64 °C olctuk (27 Agustos,
uc ucak). 50 esigi surekli alarm verirdi. Gercek risk 80 ustu; Broadcom
kisitlamayi zaten 80'de devreye sokuyor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# SystemEvent siddet degerleri (msg dosyasiyla ayni).
SIDDET_INFO = 0
SIDDET_UYARI = 1
SIDDET_KRITIK = 2


@dataclass(frozen=True)
class Esik:
    """Tek bir sağlık ölçütü ve histerezis sınırları.

    yon='ust' : deger `ac`i GECINCE kotu, `kapa`nin ALTINA inince iyi
    yon='alt' : deger `ac`in ALTINA ininCE kotu, `kapa`yi gecince iyi
    """

    alan: str          # sistem_durum satirindaki anahtar
    olay_tipi: int
    ac: float
    kapa: float
    siddet: int
    yon: str = 'ust'

    def kotu_mu(self, deger: float, su_an_acik: bool) -> bool:
        """Değer kötü tarafta mı — histerezis, o anki duruma bakar."""
        if self.yon == 'ust':
            return deger >= self.ac if not su_an_acik else deger > self.kapa
        return deger <= self.ac if not su_an_acik else deger < self.kapa


# ⚠️ Bu tablo degistirilirse GEREKCESI de yazilmali. Sayilar keyfi degil:
# sicaklik 27 Agustos olcumunden (bosta 56-64 °C), gerilim/kisitlama
# Broadcom'un kendi esiginden, disk ise 26/27 Agustos'taki log taskinindan
# (tek oturumda 876 MB) geliyor.
ESIKLER: tuple[Esik, ...] = (
    Esik('t', 60, ac=80.0, kapa=75.0, siddet=SIDDET_KRITIK),   # sicaklik °C
    Esik('t', 60, ac=70.0, kapa=65.0, siddet=SIDDET_UYARI),
    Esik('disk', 62, ac=85.0, kapa=80.0, siddet=SIDDET_UYARI),
    Esik('mem', 63, ac=300.0, kapa=400.0, siddet=SIDDET_UYARI, yon='alt'),
    Esik('load', 64, ac=4.0, kapa=3.0, siddet=SIDDET_UYARI),
)


def satir_coz(satir: str) -> dict[str, float]:
    """`yelpence_izle.sh`'in `anahtar=deger` satırını sayıya çevirir.

    Sayiya cevrilemeyen alanlar (ip, ssid, dok, ts) ATLANIR — bu fonksiyon
    yalniz esik karsilastirmasi icin gerekli sayisal alanlari verir.
    `thr` onaltilik gelir (0x0), ozel olarak cozulur.
    """
    cikti: dict[str, float] = {}
    for parca in satir.split():
        if '=' not in parca:
            continue
        k, _, v = parca.partition('=')
        v = v.rstrip('%')
        if k == 'thr':
            try:
                cikti[k] = float(int(v, 16))
            except ValueError:
                pass
            continue
        try:
            cikti[k] = float(v)
        except ValueError:
            continue
    return cikti


@dataclass
class SistemSagligi:
    """Ölçümleri olaya çevirir. Yalnız DURUM DEĞİŞİMİNDE olay üretir."""

    esikler: tuple[Esik, ...] = ESIKLER
    _acik: dict[tuple[int, int], bool] = field(default_factory=dict, init=False)

    def degerlendir(self, olcum: dict[str, float]) -> list[tuple[int, int, float]]:
        """(olay_tipi, siddet, deger) listesi — yalnız DEĞİŞENLER.

        Ayni esik acik kaldigi surece tekrar olay uretilmez; bu, butcenin
        periyodik bir kaynak tarafindan yenmesini yapisal olarak engeller.
        """
        cikti: list[tuple[int, int, float]] = []

        for e in self.esikler:
            if e.alan not in olcum:
                continue
            anahtar = (e.olay_tipi, e.siddet)
            acik = self._acik.get(anahtar, False)
            kotu = e.kotu_mu(olcum[e.alan], acik)
            if kotu != acik:
                self._acik[anahtar] = kotu
                cikti.append((
                    e.olay_tipi,
                    e.siddet if kotu else SIDDET_INFO,
                    olcum[e.alan],
                ))

        # KISITLAMA / DUSUK GERILIM: esik yok, bit alani. Sifirdan farkliysa
        # kotu. Bu, gevsek guc baglantisinin en dogrudan gostergesi —
        # ylp02'nin PX soketi gibi arizalar Pi tarafinda buradan gorulurdu
        # (o vakada Pi hatti temizdi, yani ariza PX'e ozguydu).
        if 'thr' in olcum:
            anahtar = (61, SIDDET_KRITIK)
            acik = self._acik.get(anahtar, False)
            kotu = olcum['thr'] != 0.0
            if kotu != acik:
                self._acik[anahtar] = kotu
                cikti.append((61, SIDDET_KRITIK if kotu else SIDDET_INFO,
                              olcum['thr']))

        # ROS DUGUM SAYISI: beklenenin altina duserse bir sey olmus demektir.
        # Esik sabit degil — `ros` alani zaten "kac tane" diyor; sifir ya da
        # cok dusukse konteyner ya da dugumler dusmus.
        if 'ros' in olcum:
            anahtar = (66, SIDDET_KRITIK)
            acik = self._acik.get(anahtar, False)
            kotu = olcum['ros'] < 5 if not acik else olcum['ros'] < 8
            if kotu != acik:
                self._acik[anahtar] = kotu
                cikti.append((66, SIDDET_KRITIK if kotu else SIDDET_INFO,
                              olcum['ros']))

        return cikti
