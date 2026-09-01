# Copyright 2026 Yelpence
"""MADDE 29 — Gorev 2 aralik/irtifa mesh paketi. 31 Agustos 2026.

NEDEN VAR: sartname araligi ve kalkis irtifasini GOREV ONCESI veriyor
("Orn: 15m") ve hakem baska bir sayi soyleyebilir. O sayinin UC UCAGA
BIRDEN ulasmasinin tek yolu mesh: baslat.sh `ROS_LOCALHOST_ONLY=1` ile
kosuyor, yani YKI'nin ROS servisleri ucaklardan GORUNMUYOR.

Deger BASLAT paketinin KENDI icinde tasiniyor; ayri bir komut yolu
acilmiyor. Sartname §5.2 gorev sirasinda YKI mudahalesini basarisiz
sayiyor, yani "once ayari yolla, sonra baslat" iki ayri mesaj olarak
gonderilemezdi.

🔴 BU DOSYANIN KILITLEDIGI SESSIZ HATALAR:
  * paketin 16 baytlik mesh cercevesini asmasi (ESP-NOW payload'i sabit),
  * aralik 1 bayt desimetre oldugu icin 25.5 m ustunun SESSIZCE kirpilmasi
    ("12 m istedim, 2.5 m uctu" sinifi),
  * eski (ayarsiz) gondericinin paketinin yanlis cozulmesi.
"""

import struct

import pytest

from swarm_control.esp32_bridge import packet_parser as pp


def test_paket_16_BAYT_kaliyor():
    """Rezerv alandan yendi, cerceve BUYUMEDI.

    ESP-NOW payload'i sabit; bir bayt bile buyuse butun mesh protokolu
    (COBS cercevesi, CRC, firmware tarafi) degisirdi.
    """
    payload = pp.gorev_paketle(
        pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=9.0, irtifa_m=15.0)
    assert len(payload) == 16


def test_gidis_donus_aynen():
    g = pp.gorev_coz(pp.gorev_paketle(
        pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=9.0, irtifa_m=15.0))
    assert g.tip == pp.GOREV_TIP_G2_BASLAT
    assert g.aralik_m == pytest.approx(9.0)
    assert g.irtifa_m == pytest.approx(15.0)


def test_SIFIR_belirtilmedi_demek():
    """Operator kutuyu bos birakabilir; o alan icin varsayilan korunur."""
    g = pp.gorev_coz(pp.gorev_paketle(pp.GOREV_TIP_G2_BASLAT, 0, 0, 0))
    assert g.aralik_dm == 0 and g.irtifa_dm == 0
    assert g.aralik_m == 0.0 and g.irtifa_m == 0.0


def test_desimetre_cozunurlugu():
    """0.1 m adim; 7.5 gibi yarim metreler tam donmeli."""
    g = pp.gorev_coz(pp.gorev_paketle(
        pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=7.5, irtifa_m=5.5))
    assert g.aralik_m == pytest.approx(7.5)
    assert g.irtifa_m == pytest.approx(5.5)


def test_ARALIK_TAVANI_sessizce_kirpilmaz():
    """25.6 m -> ValueError. Kirpma "istedigimden farkli uctum" olurdu."""
    with pytest.raises(ValueError):
        pp.gorev_paketle(pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=25.6)
    # 25.5 tam tavan, gecmeli (255 dm)
    g = pp.gorev_coz(pp.gorev_paketle(
        pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=25.5))
    assert g.aralik_dm == 255


def test_NEGATIF_deger_reddedilir():
    """Isaretsiz alanlar; negatif deger struct'ta patlamadan once yakalanir."""
    with pytest.raises(ValueError):
        pp.gorev_paketle(pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, aralik_m=-1.0)
    with pytest.raises(ValueError):
        pp.gorev_paketle(pp.GOREV_TIP_G2_BASLAT, 0, 0, 0, irtifa_m=-1.0)


def test_ESKI_gondericinin_paketi_hala_cozulur():
    """Rezervi sifir olan eski paket = "ayar belirtilmedi".

    Uc ucagin firmware'i ayni anda guncellenmiyor; eski bir gonderici
    paketi 12 bayt sifir rezervle yolluyordu. Yeni cozucu bunu ayarsiz
    saymali, coplukten sayi uydurmamali.
    """
    eski = struct.pack('<BBbB', pp.GOREV_TIP_G2_BASLAT, 0, 0, 0) + b'\x00' * 12
    assert len(eski) == 16
    g = pp.gorev_coz(eski)
    assert g.aralik_m == 0.0 and g.irtifa_m == 0.0


def _kaynak(dosya: str) -> str:
    import os
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'esp32_bridge', dosya)
    with open(yol, encoding='utf-8') as f:
        return f.read()


def test_AYAR_BASLATMADAN_ONCE_yayinlanir():
    """🔴 SIRA: once ayar konusu, sonra baslatma Bool'u.

    Ters sirada mode_manager kalkis kapisini ESKI irtifayla acar ve suru
    yanlis yukseklige tirmanir — hata vermeden yanlis sonuc.
    """
    kaynak = _kaynak('esp32_bridge_node.py')
    i_ayar = kaynak.find('self._g2_ayar_pub.publish(ayar)')
    i_bool = kaynak.find('self._gorev_yayilim_pub.publish(m)')
    assert i_ayar > 0 and i_bool > 0, 'yayin cagrilari bulunamadi'
    assert i_ayar < i_bool, (
        'baslatma Bool\'u ayardan ONCE yayinlaniyor — suru eski irtifayla '
        'kalkabilir'
    )
