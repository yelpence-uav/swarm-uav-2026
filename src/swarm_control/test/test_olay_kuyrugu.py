# Copyright 2026 Yelpence
"""Olay yolunun bütçe, tekrar ve sıra numarası mantığı.

Zaman DISARIDAN veriliyor, yani testler gercek zaman beklemiyor — 10 saniyelik
bir davranis 10 saniye surmuyor. `rtk_pure.h` ve `ca_core.py` ile ayni kalip.
"""

from swarm_control.esp32_bridge.olay_kuyrugu import (
    BoslukIzleyici,
    OlayKuyrugu,
)


def _kuyruk(**kw):
    k = OlayKuyrugu(**kw)
    k.basla(1000.0)
    return k


def test_butce_asilinca_DUSMEZ_bekler():
    """27 Agustos operator karari: "ilk gelen hemen gonderilirken digeri
    sirada bekler." Gecikme kabul edilebilir, KAYIP edilemez."""
    k = _kuyruk(butce_hz=1.0, patlama=1, tekrar=1)
    for i in range(5):
        assert k.ekle(bytes([i]) * 16, 1000.0) is True     # hicbiri dusmedi
    assert k.dusen == 0
    assert k.bekleyen_sayisi() == 5

    # Ayni anda YALNIZ butce kadari cikar
    assert len(k.hazir_olanlar(1000.0)) == 1
    assert len(k.hazir_olanlar(1000.5)) == 0               # yarim saniye yetmez
    assert len(k.hazir_olanlar(1001.0)) == 1               # bir saniye sonra
    assert k.bekleyen_sayisi() == 3


def test_bekleyenler_SIRASIYLA_cikiyor():
    """Kuyruk gelis sirasini korur."""
    k = _kuyruk(butce_hz=1.0, patlama=1, tekrar=1)
    for i in range(3):
        k.ekle(bytes([i]) * 16, 1000.0)
    cikan = []
    for t in range(4):
        cikan += k.hazir_olanlar(1000.0 + t)
    assert [c[0] for c in cikan] == [0, 1, 2]              # gelis sirasi korundu


def test_kuyruk_DOLARSA_dusurur_ve_sayar():
    """Sinirsiz kuyruk bellegi sisirir ve saatlerce eski olaylari
    'taze' diye yollardi."""
    k = _kuyruk(butce_hz=1.0, patlama=1, kuyruk_derinlik=3)
    assert [k.ekle(b'x' * 16, 1000.0) for _ in range(5)] == [True] * 3 + [False] * 2
    assert k.dusen == 2
    assert k.bekleyen_sayisi() == 3


def test_TEPE_YUK_butceyi_asmiyor():
    """Kuyrugun mesh icin asil faydasi: tepe yuk = surekli hal.
    Kova+patlama anlik 12 cerceve salabiliyordu."""
    k = _kuyruk(butce_hz=1.0, patlama=1, tekrar=3, tekrar_aralik_s=0.25)
    for i in range(20):
        k.ekle(bytes([i]) * 16, 1000.0)
    # Tek bir anda cikan gonderim sayisi: 1 yeni + o an zamani gelen tekrarlar
    ilk = len(k.hazir_olanlar(1000.0))
    assert ilk == 1, f"anlik patlama: {ilk}"


def test_jeton_zamanla_doluyor():
    """Jeton kovasi butce hiziyla dolar."""
    k = _kuyruk(butce_hz=1.0, patlama=2, tekrar=1)
    for i in range(4):
        k.ekle(bytes([i]) * 16, 1000.0)
    assert len(k.hazir_olanlar(1000.0)) == 2      # patlama hakki
    assert len(k.hazir_olanlar(1000.4)) == 0
    assert len(k.hazir_olanlar(1001.0)) == 1      # jeton doldu


def test_dusenler_sayiliyor():
    """Sessizce dusurmek defterin 'tamam' gorunmesi demek olurdu."""
    k = _kuyruk(butce_hz=1.0, patlama=1, kuyruk_derinlik=1)
    k.ekle(b'a' * 16, 1000.0)
    for _ in range(5):
        k.ekle(b'b' * 16, 1000.0)
    assert k.dusen == 5


def test_tekrar_sayisi_ve_araligi():
    """Her olay `tekrar` kez gonderilir; ilki HEMEN, kalanlar aralikla."""
    k = _kuyruk(tekrar=3, tekrar_aralik_s=0.25)
    k.kuyrukla(b'x' * 16, 1000.0)

    assert k.hazir_olanlar(1000.0) == [b'x' * 16]     # 1. gonderim
    assert k.hazir_olanlar(1000.1) == []              # daha zamani yok
    assert k.hazir_olanlar(1000.25) == [b'x' * 16]    # 2.
    assert k.hazir_olanlar(1000.50) == [b'x' * 16]    # 3.
    assert k.hazir_olanlar(1000.99) == []             # bitti
    assert k.gonderilen == 3


def test_tekrar_bir_ise_tek_gonderim():
    """tekrar=1 ise olay bir kez gider."""
    k = _kuyruk(tekrar=1)
    k.kuyrukla(b'y' * 16, 1000.0)
    assert len(k.hazir_olanlar(1000.0)) == 1
    assert k.hazir_olanlar(1001.0) == []


def test_sira_no_sariyor():
    """Tek bayt: 255'ten sonra 0. YKI bosluk sayarken bunu bilmek ZORUNDA."""
    k = _kuyruk()
    for _ in range(255):
        k.sonraki_sira()
    assert k.sonraki_sira() == 0
    assert k.sonraki_sira() == 1


def test_dusen_raporu_periyodik():
    """Rapor 10 sn'de bir; ara sorgular None doner ve sayac SIFIRLANMAZ."""
    k = _kuyruk(butce_hz=1.0, patlama=1, kuyruk_derinlik=1)
    k.ekle(b'a' * 16, 1000.0)
    for _ in range(3):
        k.ekle(b'b' * 16, 1000.0)

    assert k.dusen_raporu(1005.0) is None          # daha 10 sn olmadi
    assert k.dusen == 3                            # sayac duruyor
    assert k.dusen_raporu(1010.0) == 3             # zamani geldi
    assert k.dusen == 0                            # sifirlandi
    assert k.dusen_raporu(1020.0) is None          # yeni dusen yok


def test_dusen_yoksa_rapor_yok():
    """Dusen yokken rapor uretilmez."""
    k = _kuyruk()
    assert k.dusen_raporu(2000.0) is None


def test_halka_tamponu_sinirli():
    """Halka, tekrar-isteme eklenirse eksik olayin cikacagi yer.
    Sinirsiz buyumemeli."""
    k = _kuyruk(halka=4, tekrar=1)
    for i in range(10):
        k.kuyrukla(bytes([i]) * 16, 1000.0 + i)
    icerik = k.halka_icerik()
    assert len(icerik) == 4
    assert icerik[-1] == bytes([9]) * 16           # en yenisi duruyor


def test_kuyruk_bosken_hazir_yok():
    """Bos kuyruk gonderim uretmez."""
    assert _kuyruk().hazir_olanlar(1000.0) == []


def test_ayni_anda_birden_cok_olay():
    """Iki olay ust uste geldiginde ikisi de kendi tekrarini tamamlar."""
    k = _kuyruk(tekrar=2, tekrar_aralik_s=0.25)
    k.kuyrukla(b'a' * 16, 1000.0)
    k.kuyrukla(b'b' * 16, 1000.0)
    assert sorted(k.hazir_olanlar(1000.0)) == [b'a' * 16, b'b' * 16]
    assert sorted(k.hazir_olanlar(1000.25)) == [b'a' * 16, b'b' * 16]
    assert k.hazir_olanlar(1001.0) == []
    assert k.gonderilen == 4


# =============================================================================
# BoslukIzleyici — alici tarafi
# =============================================================================


def test_kopyalar_eleniyor():
    """Tekrar mekanizmasi ayni sira_no'yu 3 kez yollar; ikisi kopyadir."""
    b = BoslukIzleyici()
    assert b.gelen(1, 5, 0.0) is True
    assert b.gelen(1, 5, 0.25) is False
    assert b.gelen(1, 5, 0.50) is False


def test_karisik_varis_YANLIS_ALARM_uretmiyor():
    """5 6 5 6 5 6 sirasi — tekrarlar ic ice gecmis. Kayip YOK."""
    b = BoslukIzleyici(bekleme_s=2.0)
    for sira, t in [(5, 0.0), (6, 0.1), (5, 0.25), (6, 0.35), (5, 0.5), (6, 0.6)]:
        b.gelen(1, sira, t)
    assert b.kayiplar(10.0) == []


def test_gercek_kayip_onay_suresinden_SONRA_bildiriliyor():
    b = BoslukIzleyici(bekleme_s=2.0)
    b.gelen(1, 5, 0.0)
    b.gelen(1, 8, 0.1)                       # 6 ve 7 atlandi
    assert b.kayiplar(1.0) == []             # onay suresi dolmadi
    assert b.kayiplar(3.0) == [(1, 2)]       # dolunca: 2 olay kayip
    assert b.kayiplar(9.0) == []             # bir kez bildirilir


def test_gec_gelen_kayip_SAYILMIYOR():
    """Atlanan sira gec de olsa gelirse kayip degildir."""
    b = BoslukIzleyici(bekleme_s=2.0)
    b.gelen(1, 5, 0.0)
    b.gelen(1, 7, 0.1)                       # 6 atlandi
    assert b.gelen(1, 6, 0.5) is True        # gecikmeli geldi
    assert b.kayiplar(5.0) == []             # kayip YOK


def test_sarma_sinirinda_dogru():
    """Sayac sarmasinda bosluk dogru sayilir."""
    b = BoslukIzleyici(bekleme_s=1.0)
    b.gelen(1, 254, 0.0)
    b.gelen(1, 1, 0.1)                       # 255 ve 0 atlandi
    assert b.kayiplar(2.0) == [(1, 2)]


def test_buyuk_atlama_kayip_SAYILMIYOR_ama_sessiz_de_gecmiyor():
    """200 -> 1 gecisi hem '56 kayip' hem 'sayac sifirlandi' diye okunabilir.

    Sira numarasindan AYIRT EDILEMEZ. Tahmin etmek yerine ayri sepete
    koyuyoruz: kayip sayilmiyor ama sicrama olarak BILDIRILIYOR.
    """
    b = BoslukIzleyici(bekleme_s=1.0, makul_kayip=16)
    b.gelen(1, 200, 0.0)
    b.gelen(1, 1, 0.1)
    assert b.kayiplar(5.0) == []             # uydurma kayip YOK
    assert b.sicramalar() == {1: 1}          # ama sessiz de degil


def test_droneler_birbirinden_bagimsiz():
    """Her drone kendi sayacini tasir."""
    b = BoslukIzleyici(bekleme_s=1.0)
    b.gelen(1, 5, 0.0)
    b.gelen(2, 90, 0.0)                      # baska drone, baska sayac
    b.gelen(1, 6, 0.1)
    b.gelen(2, 91, 0.1)
    assert b.kayiplar(5.0) == []


# =============================================================================
# Yineleme suzgeci — 27 Agustos canli testinde bulunan kusurun testi
# =============================================================================

def test_periyodik_kaynak_butceyi_YEMIYOR():
    """`_diag_yayinla` saniyede bir ayni olayi yayiyordu; aktarilinca butcenin
    TAMAMINI yiyor ve GERCEK olaylarin dusmesine yol aciyordu."""
    k = _kuyruk()
    anahtar = (0, 0, 0, 0.0)
    gecen = sum(0 if k.yinelenen_mi(anahtar, 1000.0 + i, 5.0) else 1
                for i in range(10))          # 10 saniyede saniyede bir
    assert gecen == 2                        # 5 sn'lik pencerede iki kez


def test_farkli_olaylar_birbirini_ENGELLEMIYOR():
    """Yineleme suzgeci olay bazinda calisir."""
    k = _kuyruk()
    assert k.yinelenen_mi((43, 2, 0, 3.88), 1000.0) is False
    assert k.yinelenen_mi((58, 1, 0, 0.0), 1000.0) is False   # baska olay
    assert k.yinelenen_mi((43, 2, 0, 3.88), 1000.1) is True   # ayni olay


def test_pencere_gecince_tekrar_gecer():
    """Yineleme penceresi dolunca olay yeniden gecer."""
    k = _kuyruk()
    a = (43, 2, 0, 1.0)
    assert k.yinelenen_mi(a, 1000.0, 5.0) is False
    assert k.yinelenen_mi(a, 1003.0, 5.0) is True     # pencere icinde
    assert k.yinelenen_mi(a, 1006.0, 5.0) is False    # pencere gecti


def test_yineleme_sozlugu_sinirsiz_buyumuyor():
    """Yineleme sozlugu tavanla sinirlidir."""
    k = _kuyruk()
    for i in range(500):
        k.yinelenen_mi((i, 0, 0, 0.0), 1000.0 + i * 30.0, 5.0)
    assert len(k._yineleme) <= 128
