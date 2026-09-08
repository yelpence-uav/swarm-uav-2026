# Copyright 2026 Yelpence
"""CUSTOM ofsetleri ONBELLEKLENIR — bir cerceve dusunce komut atilmaz.

🔴 8 EYLUL 2026, GOREV 1'IN ILK ONBOARD UCUSUNDA OLCULDU.

CUSTOM'da bir formasyon komutu UC cerceve istiyor (baslik + 2 ofset) ve
alici ucunu de bekliyordu; biri dusunce komutun TAMAMI atiliyordu.
Takipcinin donus sirasinda ALDIGI hedef:

    21 mesaj / 29.4 sn = 0.72 Hz          (gonderim 2 Hz'di)
    aralik medyan 622 ms, MAX 12671 ms
    heading adimi medyan 6.5 deg, MAX 32.4 deg

32.4 derecelik tek adim, 7.5 m yaricapta 4.2 m'lik ani hedef sicramasi
demek. Kanat ucaklari hedefe atilip bekliyor, sonra yine atiliyor —
operatorun bildirdigi "bas-cek gibi salinim" bu. Setpoint ileribeslemesi
de dogruladi: |v| medyan 1.22 m/s, MAX 4.20 m/s.

COZUM: CUSTOM ofsetleri her turda AYNI (diziliş `frozen_offsets` ile
donmus); tur basina degisen yalniz merkez ve heading. Artik kaynak basina
son GECERLI ofset kumesi saklaniyor.
    once : komut icin 3/3 cerceve  -> tur basina basari ~%47
    sonra: ilk seferden sonra 1/3  -> ~%78
Gonderici, protokol ve firmware DEGISMEDI.
"""

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.formasyon_montaj import FormasyonMontaj

_CUSTOM = 99
_OFS = [(0.0, 0.0, 0.0), (5.0, 1.0, 0.0), (-5.0, -1.0, 0.0)]
_KAYNAK = 1


def _baslik(spacing=7.0):
    """Uc ajanli CUSTOM baslik cercevesi."""
    yuk, _ = pp.formasyon_paketle(
        formasyon_tipi=_CUSTOM, merkez_kuzey_m=10.0, merkez_dogu_m=-5.0,
        merkez_asagi_m=-15.0, heading_deg=30.0, spacing_m=spacing,
        slot_ajan=[1, 2, 3])
    return pp.formasyon_coz(yuk)


def _ofset_paketleri(ofsetler=None):
    """CUSTOM ofsetlerini iki cerceveye boler (paket basina 2 slot)."""
    o = ofsetler if ofsetler is not None else _OFS
    out = []
    for bas in (0, 2):
        yuk, _ = pp.form_ofset_paketle(bas, o[bas:bas + 2])
        out.append(pp.form_ofset_coz(yuk))
    return out


def _tam_tur(m, t, ofsetler=None):
    """Baslik + butun ofset cerceveleri — kayipsiz tur."""
    tam = m.baslik_ekle(_KAYNAK, _baslik(), t)
    for p in _ofset_paketleri(ofsetler):
        tam = m.ofset_ekle(_KAYNAK, p, t) or tam
    return tam


# ------------------------------------------------------- ilk tur / temel

def test_ILK_TUR_HALA_BUTUN_CERCEVELERI_ISTER():
    """Onbellek bosken eksik ofsetle komut URETILMEZ — uydurma yok."""
    m = FormasyonMontaj()
    assert m.baslik_ekle(_KAYNAK, _baslik(), 0.0) is None
    assert m.ofset_ekle(_KAYNAK, _ofset_paketleri()[0], 0.0) is None
    assert m.ofset_onbellek_kullanildi == 0


def test_TAM_TUR_ONBELLEGI_DOLDURUR():
    m = FormasyonMontaj()
    tam = _tam_tur(m, 0.0)
    assert tam is not None
    assert [tuple(o) for o in tam.ofsetler] == _OFS


# ------------------------------------------------------------ asil kusur

def test_OFSET_CERCEVESI_DUSSE_DE_KOMUT_URETILIR():
    """🔴 Kusurun ta kendisi: eskiden komutun TAMAMI atiliyordu."""
    m = FormasyonMontaj()
    _tam_tur(m, 0.0)                                   # onbellek dolsun
    tam = m.baslik_ekle(_KAYNAK, _baslik(), 1.0)       # ofsetler DUSTU
    assert tam is not None, 'ofset dusunce komut hala atiliyor'
    assert [tuple(o) for o in tam.ofsetler] == _OFS
    assert m.ofset_onbellek_kullanildi == 1


def test_ARKA_ARKAYA_KAYIPLARDA_DA_SURUYOR():
    """Uzun bir kayip serisinde her tur komut cikmali."""
    m = FormasyonMontaj()
    _tam_tur(m, 0.0)
    for i in range(1, 11):
        assert m.baslik_ekle(_KAYNAK, _baslik(), float(i)) is not None
    assert m.ofset_onbellek_kullanildi == 10


# ------------------------------------------------- BAYAT OFSET TUZAGI

def test_SAHIPSIZ_OFSET_ONBELLEGI_TAZELER():
    """🔴 Onbellegin kendi tuzagi: bayat ofset sonsuza kadar servis edilmesin.

    Onbellek devreye girince komut BASLIKLA tamamlaniyor; hemen ardindan
    gelen ofset cerceveleri "bekleyen montaj yok" diye dusuyordu. O hâlde
    onbellek ilk turdan sonra HIC tazelenmez ve diziliş gercekten
    degisirse BAYAT ofsetler sonsuza kadar gider — cozdugumuz kusurdan
    beter, sessiz bir yanlis.
    """
    m = FormasyonMontaj()
    _tam_tur(m, 0.0)
    yeni = [(1.0, 1.0, 0.0), (9.0, 2.0, 0.0), (-9.0, -2.0, 0.0)]
    # Baslik once gelir -> komut ESKI ofsetlerle tamamlanir (bir tur bayat).
    tam = m.baslik_ekle(_KAYNAK, _baslik(), 1.0)
    assert [tuple(o) for o in tam.ofsetler] == _OFS
    # Ardindan gelen SAHIPSIZ ofsetler onbellegi tazeler.
    for p in _ofset_paketleri(yeni):
        m.ofset_ekle(_KAYNAK, p, 1.0)
    # Sonraki tur ARTIK yeni diziliş.
    tam2 = m.baslik_ekle(_KAYNAK, _baslik(), 2.0)
    assert [tuple(o) for o in tam2.ofsetler] == yeni, 'onbellek tazelenmedi'


def test_KADRO_DEGISINCE_ONBELLEK_KULLANILMAZ():
    """Slot sayisi degistiyse eski ofsetler YANLIS dizilis demek olurdu."""
    m = FormasyonMontaj()
    _tam_tur(m, 0.0)
    yuk, _ = pp.formasyon_paketle(
        formasyon_tipi=_CUSTOM, merkez_kuzey_m=10.0, merkez_dogu_m=-5.0,
        merkez_asagi_m=-15.0, heading_deg=30.0, spacing_m=7.0,
        slot_ajan=[1, 2])                              # ARTIK IKI AJAN
    assert m.baslik_ekle(_KAYNAK, pp.formasyon_coz(yuk), 1.0) is None
    assert m.ofset_onbellek_kullanildi == 0


def test_ADLANDIRILMIS_FORMASYON_ETKILENMEDI():
    """CIZGI/V/OKBASI ofsetleri formulden turer — onbellek yolu hic islemez."""
    m = FormasyonMontaj()
    yuk, _ = pp.formasyon_paketle(
        formasyon_tipi=3, merkez_kuzey_m=0.0, merkez_dogu_m=0.0,
        merkez_asagi_m=-10.0, heading_deg=0.0, spacing_m=7.0,
        slot_ajan=[1, 2, 3])
    tam = m.baslik_ekle(_KAYNAK, pp.formasyon_coz(yuk), 0.0)
    assert tam is not None and tam.formasyon_tipi == 3
    assert m.ofset_onbellek_kullanildi == 0
