# Copyright 2026 Yelpence
"""TAKIM SLOTU MESH'TEN GECER — sahada SSH gerekmesin.

🔴 9 EYLUL 2026, operator: "yarismada SSH ile baglanamayabilirim".

QR'in `team` tablosu takim NUMARASIYLA degil SLOT ile anahtarli ve slotu
HAKEM GOREV ANINDA veriyor. Slot yanlissa QR HIC okunmaz; tek gorunen
satir "Takim slotu N tabloda yok" olur.

Onceki tek ayar yolu ucaga ag uzerinden erisip `ros2 param set` yapmakti.
Sahada Wi-Fi olmayabilir; guvenilir tek hat MESH.

COZUM: slot, GOREV 1 BASLAT paketinin REZERV baytiyla gidiyor.
🔴 PAKET 16 BAYT KALDI — yeni mesh tipi ACILMADI, FIRMWARE DEGISMEDI.
Bu sart kritik: firmware tipe gore SABIT uzunluk bekliyor
(TX DRONE/main.cpp) ve tanimadigi tipi KOMPLE reddediyor (mesh_config.h
static_assert). Paket buyuseydi uc ESP32'yi yeniden yakmak gerekirdi.
"""

import struct

from swarm_control.esp32_bridge import packet_parser as pp


def test_PAKET_16_BAYT_KALDI():
    """🔴 En kritik sart: paket buyurse firmware paketi REDDEDER."""
    ham = pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, 2, 0, 0,
                           aralik_m=7.0, irtifa_m=15.0, takim_slot=3)
    assert len(ham) == 16, f'{len(ham)} bayt — firmware 16 bekliyor'


def test_SLOT_GIDIP_GERI_GELIYOR():
    """Yaz-oku turu: slot bozulmadan karsi tarafa varmali."""
    for slot in (1, 2, 5, 255):
        g = pp.gorev_coz(pp.gorev_paketle(
            pp.GOREV_TIP_G1_BASLAT, 0, 0, 0, takim_slot=slot))
        assert g.takim_slot == slot


def test_SIFIR_BELIRTILMEDI_DEMEK():
    """Slot verilmezse 0 gider; alici KENDI slotunu korur."""
    g = pp.gorev_coz(pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, 0, 0, 0))
    assert g.takim_slot == 0


def test_ESKI_ALANLAR_BOZULMADI():
    """Rezervden bayt yemek eski alanlari kaydirmis olabilir — kilitle."""
    g = pp.gorev_coz(pp.gorev_paketle(
        pp.GOREV_TIP_G1_BASLAT, 2, -3, 7, aralik_m=7.5, irtifa_m=15.0,
        morf_hiz_mps=1.5, hareket_hiz_mps=2.0, yaw_hiz_deg_s=12.0,
        egim_tavan_deg=30.0, takim_slot=4))
    assert g.tip == pp.GOREV_TIP_G1_BASLAT
    assert g.param1 == 2 and g.param2 == -3 and g.bekleme_suresi_s == 7
    assert abs(g.aralik_m - 7.5) < 0.05
    assert abs(g.irtifa_m - 15.0) < 0.05
    assert g.morf_hiz_dm == 15 and g.hareket_hiz_dm == 20
    assert g.yaw_hiz_ddeg == 120 and g.egim_tavan_deg == 30
    assert g.takim_slot == 4


def test_SINIR_DISI_SESSIZ_KIRPILMAZ():
    """Sessiz kirpma "3 dedim, 47 gitti" sinifi hata uretirdi."""
    try:
        pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, 0, 0, 0, takim_slot=300)
    except ValueError:
        return
    raise AssertionError('300 kabul edildi — sessizce kirpiliyor')


def test_FORMAT_REZERVDEN_YEDI():
    """Format dizesi hala 16 bayt uretmeli (struct duzeyinde)."""
    assert struct.calcsize(pp._GOREV_FMT) == 16
