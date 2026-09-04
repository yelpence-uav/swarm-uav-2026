# Copyright 2026 Yelpence
"""Gorev 1 BASLANGIC FORMASYONU mesh'ten gidiyor mu (4 Eylul 2026).

Oncesinde `gorev_formasyon` YALNIZCA baslat.sh parametresiydi: operator
formasyonu degistirmek icin uc ucakta dosya yazip konteyner restart etmek
zorundaydi. Artik YKI'den seciliyor ve G1 BASLAT paketiyle gidiyor.

FIRMWARE'E DOKUNULMADI: TIP_GOREV (0x05) her iki whitelist'te ZATEN var ve
firmware paketin icine bakmiyor. Paketin `param1` ve `aralik` alanlari
Gorev 1'de zaten BOS duruyordu; yeni bir mesh tipi acilmadi.

Test iki yonu birden kilitliyor:
  * secim GERCEKTEN tasiniyor mu       (yoksa operator sectigini sanir)
  * 0 = "belirtilmedi" KORUNUYOR mu    (yoksa secmemek formasyonu sifirlar)
"""

from swarm_control.esp32_bridge import packet_parser as pp

_CIZGI = 3
_OKBASI = 1


def test_formasyon_ve_aralik_TASINIYOR():
    """param1 = formasyon tipi, aralik = metre — gidip geri geliyor."""
    ham = pp.gorev_paketle(
        pp.GOREV_TIP_G1_BASLAT, _CIZGI, 0, 0, aralik_m=7.0)
    g = pp.gorev_coz(ham)
    assert g.tip == pp.GOREV_TIP_G1_BASLAT
    assert g.param1 == _CIZGI
    assert abs(g.aralik_m - 7.0) < 1e-6


def test_SIFIR_belirtilmedi_demek():
    """Operatorun secim yapmamasi GECERLI: ucak varsayilanini korur."""
    g = pp.gorev_coz(pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, 0, 0, 0))
    assert g.param1 == 0
    assert g.aralik_m == 0.0


def test_PAKET_BOYUTU_DEGISMEDI():
    """16 baytlik sozlesme degismemeli.

    Degisirse cerceve dilimi kayar ve BUTUN alanlar sessizce yanlis
    okunur — firmware paketi opak tasidigi icin hicbir yerde hata
    gorunmez.
    """
    assert len(pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, _OKBASI, 0, 0,
                                aralik_m=6.0)) == 16
    assert len(pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, 0, 0, 0)) == 16


def test_ARALIK_TAVANI_SESSIZ_KIRPILMIYOR():
    """Aralik tavani sessizce kirpilmamali.

    Aralik 1 bayt desimetre tasiniyor, yani tavan 25.5 m. Ustu ValueError
    atmali; sessizce kirpmak "12 m istedim, 25.5 m uctu" sinifi bir hata
    uretirdi.
    """
    import pytest
    with pytest.raises(ValueError):
        pp.gorev_paketle(pp.GOREV_TIP_G1_BASLAT, _CIZGI, 0, 0,
                         aralik_m=30.0)


def test_G1_ile_G2_alt_tipleri_CAKISMIYOR():
    """G1 ve G2 alt tipleri cakismamali.

    Ayni pakette iki gorev tasiniyor; alt tipler karisirsa G1 BASLAT
    suruyu G2 moduna sokar — sessiz ve tam olarak yanlis.
    """
    hepsi = {pp.GOREV_TIP_G1_BASLAT, pp.GOREV_TIP_G1_DURDUR,
             pp.GOREV_TIP_G2_BASLAT, pp.GOREV_TIP_G2_DURDUR}
    assert len(hepsi) == 4
