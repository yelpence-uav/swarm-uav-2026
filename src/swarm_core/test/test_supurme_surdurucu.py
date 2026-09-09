# Copyright 2026 Yelpence
"""Takipci mesh boslugunda supurme rampasini SURDURUR — bas-cek biter.

🔴 8 EYLUL 2026, operator: "lider olmayan diger dronelar inis sirasinda
bas cek yapiyorlar... butun dronelar meshten bagimsiz yavasca inip
kalksalar... ama meshten arada bir kontrol etsinler, cok bir fark
olmasin irtifalarda."

Bu dosya uc sozu kilitliyor:
  ① bosluk boyunca rampa SURER (donma yok, sicrama yok)
  ② her mesh paketinde deger MESHE GERI SENKRONLANIR (mesh dogruluk kaynagi)
  ③ sapma tavana dayanirsa BEKLENIR — hizlanma YOK

③'un gerekcesi olcum: 8 Eylul'de tirmanma itki payinin dar oldugu
gorulduğu icin (ylp00 gaz 1.000'e dayadi, komut edilen irtifaya cikamadi)
geri kalani hizlandirmak degil, oneyi durdurmak secildi.
"""

from swarm_core.formation_control.supurme_surdurucu import (
    SAPMA_TAVANI_M,
    SupurmeSurdurucu,
)

HIZ = 1.5          # GOREV_QR_ARAMA_DIKEY_HIZ_MPS
ARALIK = 0.2       # 5 Hz mesh


def _iki_paket(s, t0=100.0, z0=-15.0, hiz=HIZ):
    """Ardisik iki hedef -> hiz cikarilir (NED: +z asagi = alcalma)."""
    s.hedef_geldi(t0, z0, 0.0, 0.0)
    s.hedef_geldi(t0 + ARALIK, z0 + hiz * ARALIK, 0.0, 0.0)
    return t0 + ARALIK, z0 + hiz * ARALIK


# ------------------------------------------------------------ asil kusur

def test_BOSLUKTA_RAMPA_SURER_DONMAZ():
    """🔴 Kusurun ta kendisi: eskiden son hedefte DONUYORDU."""
    s = SupurmeSurdurucu()
    t, z = _iki_paket(s)
    assert s.aktif
    # 0.6 sn'lik bosluk (sahada olculen medyan 622 ms)
    beklenen = z + HIZ * 0.6
    assert abs(s.z(t + 0.6) - beklenen) < 1e-6


def test_SICRAMA_YOK_SUREKLI():
    """Ardisik anlar arasinda adim, hiz x dt kadar olmali."""
    s = SupurmeSurdurucu()
    t, _ = _iki_paket(s)
    onc = s.z(t)
    for i in range(1, 4):
        simdi = t + i * 0.1
        yeni = s.z(simdi)
        assert abs(yeni - onc) <= HIZ * 0.1 + 1e-9
        onc = yeni


def test_HER_PAKETTE_MESHE_SENKRON():
    """Mesh dogruluk kaynagi: paket gelince deger TAM ona esitlenir."""
    s = SupurmeSurdurucu()
    t, z = _iki_paket(s)
    s.z(t + 0.5)                                   # arada surduruldu
    s.hedef_geldi(t + 0.6, -12.0, 0.0, 0.0)        # mesh farkli bir deger dedi
    assert s.z(t + 0.6) == -12.0


# ------------------------------------------- BEKLE, hizlanma yok (③)

def test_SAPMA_TAVANINDA_BEKLER():
    """Uzun boslukta sicrama yerine BEKLEME — dikeyde gecikme guvenlidir."""
    s = SupurmeSurdurucu()
    t, z = _iki_paket(s)
    uzak = s.z(t + 10.0)                           # 10 sn bosluk
    assert abs(uzak - z) == SAPMA_TAVANI_M
    assert s.tavana_dayanma_sayisi >= 1


def test_TAVAN_IKI_YONDE_DE_GECERLI():
    """Tirmanista da ayni sinir — isaret bagimsiz."""
    s = SupurmeSurdurucu()
    t, z = _iki_paket(s, hiz=-HIZ)                 # yukari
    assert abs(s.z(t + 10.0) - z) == SAPMA_TAVANI_M


def test_HIZLANMA_YOK():
    """Sapma buyudukce hiz ARTMAZ; tavanda sabit kalir."""
    s = SupurmeSurdurucu()
    t, z = _iki_paket(s)
    a = s.z(t + 5.0)
    b = s.z(t + 50.0)
    assert a == b                                   # ikisi de tavanda


# ------------------------------------------------- yanlis yerde ACILMAZ

def test_SEYIRDE_SURDURME_KAPALI():
    """Yatay merkez oynuyorsa supurme degil SEYIR var — dikey uydurma YOK."""
    s = SupurmeSurdurucu()
    s.hedef_geldi(100.0, -15.0, 0.0, 0.0)
    s.hedef_geldi(100.2, -14.7, 5.0, 0.0)          # 5 m yatay kaydi
    assert s.aktif is False
    assert s.z(100.8) == -14.7                     # son deger, uydurma yok


def test_DURGUN_HEDEFTE_SURDURME_KAPALI():
    """Irtifa degismiyorsa rampa yok — surdurulecek bir sey de yok."""
    s = SupurmeSurdurucu()
    s.hedef_geldi(100.0, -15.0, 0.0, 0.0)
    s.hedef_geldi(100.2, -15.0, 0.0, 0.0)
    assert s.aktif is False


def test_COK_HIZLI_DEGISIM_SUPURME_SAYILMAZ():
    """3 m/s ustu bir sicrama supurme degildir (formasyon/QR komutu olabilir)."""
    s = SupurmeSurdurucu()
    s.hedef_geldi(100.0, -15.0, 0.0, 0.0)
    s.hedef_geldi(100.2, -15.0 + 5.0, 0.0, 0.0)    # 25 m/s
    assert s.aktif is False


def test_ESKI_ORNEK_GUVENILMEZ():
    """Iki hedef arasi cok uzunsa hiz tahmini yapilmaz."""
    s = SupurmeSurdurucu()
    s.hedef_geldi(100.0, -15.0, 0.0, 0.0)
    s.hedef_geldi(110.0, -10.0, 0.0, 0.0)          # 10 sn arayla
    assert s.aktif is False


# --------------------------------------------------------------- yasam

def test_ILK_PAKETTEN_ONCE_KOMUT_YOK():
    """Hicbir hedef gelmediyse surdurucu sessiz kalmali."""
    assert SupurmeSurdurucu().z(100.0) is None


def test_TEK_PAKETLE_SURDURME_ACILMAZ():
    """Hiz iki ornek ister; tek pakette son deger doner."""
    s = SupurmeSurdurucu()
    s.hedef_geldi(100.0, -15.0, 0.0, 0.0)
    assert s.aktif is False
    assert s.z(100.5) == -15.0


def test_SIFIRLA_SURDURMEYI_KAPATIR():
    """Supurme bitince (QR okundu) surdurme kapanmali."""
    s = SupurmeSurdurucu()
    _iki_paket(s)
    assert s.aktif
    s.sifirla()
    assert s.aktif is False
    assert s.z(200.0) is None
