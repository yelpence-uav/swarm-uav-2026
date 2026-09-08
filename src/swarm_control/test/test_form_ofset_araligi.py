# Copyright 2026 Yelpence
"""CUSTOM ofset cerceveleri ARDI ARDINA gonderilemez.

8 EYLUL 2026 — 3 UCAKLA CUSTOM FORMASYON MESH'TEN HIC GECMIYORDU.

CUSTOM (juri dizilisi) ofsetleri formulden turetilemez, `TIP_FORM_OFSET`
cerceveleriyle ACIKCA tasinir; paket basina 2 slot, yani 3 ucakta IKI
cerceve. Eskiden ikisi de arka arkaya UART'a yaziliyordu. Firmware ise
TIP BASINA hiz limiti uyguluyor:

    firmware/esp32_mesh/TX DRONE/src/main.cpp:306  MESH_GONDERIM_MIN_MS 50
    firmware/esp32_mesh/TX DRONE/src/main.cpp:420  mesh_tip_gecebilir(...)

Iki cerceve AYNI TIP ve aralarinda mikrosaniye var -> IKINCISI HER
SEFERINDE dusuyordu. Alicida montaj tamamlanmiyor (3 slotun 2'si),
200 ms sonraki yeni baslik yarim montaji BILEREK siliyor. Sonuc:
slot 2'nin ofseti mesh'e HIC cikmiyor, takipciler formasyon komutunu
HIC ALMIYOR. Lider etkilenmiyor (loopback seri porta ugramiyor).

Sahadaki gorunum: "ilk QR'a gidildikten sonra SADECE LIDER irtifa
degistirdi." Hicbir logda hata yok.

Bu dosya duzeltmenin iki yanini da kilitliyor:
  ① ayni tur icinde iki ofset cercevesi ayni anda CIKMAZ
  ② birakilan aralik firmware'in limitinden BUYUK (kaynagindan okunur)
"""

import os
import re

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.esp32_bridge_node import (
    Esp32BridgeNode,
    _FORM_OFSET_ARALIK_S,
)

_CUSTOM = 99


class _Kayitci:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass


class _Komut:
    """FormationCommand yerine gecen kabuk (conftest mesajlari taklit ediyor)."""

    def __init__(self, ajanlar=(1, 2, 3), tip=_CUSTOM, **kw):
        n = len(ajanlar)
        self.formation_type = tip
        self.agent_ids = list(ajanlar)
        # Her ajana FARKLI ofset: bir cerceve dusunce hangi slotun
        # kaybedildigi testte gorulebilsin.
        self.offset_x = [float(i) for i in range(n)]
        self.offset_y = [float(-i) for i in range(n)]
        self.offset_z = [0.0] * n
        self.center_x = 10.0
        self.center_y = 20.0
        self.center_z = -15.0
        self.heading_deg = 30.0
        self.spacing_m = 7.0
        self.max_speed_mps = 0.0
        self.__dict__.update(kw)


def _dugum(mesh_hz=0.0):
    """Esp32BridgeNode'u __init__ CAGIRMADAN kurar (conftest deseni).

    mesh_hz=0.0 -> hiz kapisi KAPALI; ofset araligini tek basina sinamak
    icin. Kapinin kendisi ayri testlerde aciliyor.
    """
    from swarm_control.esp32_bridge.formasyon_montaj import FormasyonMontaj
    d = object.__new__(Esp32BridgeNode)
    d._agent_id = 1
    d._lider_id = 1
    d._kanat_alfa_deg = 45.0
    d._formasyon_gonderilen = 0
    d._formasyon_lider_degil = 0
    d._formasyon_seyreltilen = 0
    d._formasyon_son_mesh = 0.0
    d._formasyon_mesh_min_aralik_s = (1.0 / mesh_hz) if mesh_hz > 0 else 0.0
    d._form_ofset_kuyruk = __import__('collections').deque()
    d._form_ofset_son_gonderim = 0.0
    d._form_ofset_iptal = 0
    d._formasyon_montaj = FormasyonMontaj()
    d.gonderilen = []
    d.yayinlanan = []
    d._uart_yaz = lambda tip, aid, yuk: d.gonderilen.append((tip, yuk))
    d._formasyon_yayinla = lambda tam: d.yayinlanan.append(tam)
    d._lider_miyim = lambda: True
    d.get_logger = _Kayitci
    return d


def _ofsetler(d):
    return [y for (t, y) in d.gonderilen if t == pp.TIP_FORM_OFSET]


def _pencereyi_ac(d):
    """Ofset araligini gecmis say — gercek saati beklemeden."""
    d._form_ofset_son_gonderim -= (_FORM_OFSET_ARALIK_S + 0.01)


# ------------------------------------------------------- asil duzeltme

def test_UC_UCAKTA_IKI_OFSET_AYNI_ANDA_CIKMAZ():
    """🔴 Kusurun ta kendisi: eskiden ikisi de ayni anda yazilirdi."""
    d = _dugum()
    d._on_formation_out(_Komut())
    assert len(_ofsetler(d)) == 1, 'iki ofset cercevesi ARDI ARDINA cikti'
    assert len(d._form_ofset_kuyruk) == 1, 'ikincisi kuyrukta bekletilmedi'


def test_ikinci_cerceve_ARALIK_DOLUNCA_cikar():
    """Kuyruk bosalir — cerceve kaybolmuyor, sadece geciktiriliyor."""
    d = _dugum()
    d._on_formation_out(_Komut())
    d._form_ofset_kuyrugu_isle()                 # aralik dolmadi
    assert len(_ofsetler(d)) == 1
    _pencereyi_ac(d)
    d._form_ofset_kuyrugu_isle()
    assert len(_ofsetler(d)) == 2
    assert not d._form_ofset_kuyruk


def test_HER_SLOT_MESH_E_CIKIYOR():
    """Uc slotun ofseti de gercekten gidiyor — slot 2 dahil.

    Eski kodda slot 2 firmware'de dusuyor ve montaj HIC tamamlanmiyordu.
    """
    d = _dugum()
    d._on_formation_out(_Komut())
    _pencereyi_ac(d)
    d._form_ofset_kuyrugu_isle()
    goruldu = set()
    for yuk in _ofsetler(d):
        v = pp.form_ofset_coz(yuk)
        for i in range(v.slot_sayisi):
            goruldu.add(v.slot_bas + i)
    assert goruldu == {0, 1, 2}, f'eksik slot: {goruldu}'


def test_ARALIK_FIRMWARE_LIMITINDEN_BUYUK():
    """🔴 Olcut UYDURULMADI — firmware kaynagindan okunuyor.

    Firmware'de limit degisirse (ya da bu sabit kucultulurse) test duser.
    Aksi halde iki sayi birbirinden habersiz kayar ve cerceve ARADA BIR
    duser — en kotu ariza turu, cunku bazen calisir.
    """
    kok = os.path.abspath(__file__)
    for _ in range(6):
        kok = os.path.dirname(kok)
        yol = os.path.join(kok, 'firmware', 'esp32_mesh',
                           'TX DRONE', 'src', 'main.cpp')
        if os.path.isfile(yol):
            break
    else:
        import pytest
        pytest.skip('firmware kaynagi bulunamadi')

    with open(yol, encoding='utf-8', errors='replace') as f:
        m = re.search(r'#define\s+MESH_GONDERIM_MIN_MS\s+(\d+)', f.read())
    assert m, 'MESH_GONDERIM_MIN_MS firmware de bulunamadi'
    limit_s = int(m.group(1)) / 1000.0
    assert _FORM_OFSET_ARALIK_S > limit_s, (
        f'aralik {_FORM_OFSET_ARALIK_S:.3f} s, firmware limiti {limit_s:.3f} s'
    )


# ------------------------------------------------------- bayat cerceve

def test_YENI_TUR_BAYAT_CERCEVEYI_ATAR():
    """Bayat ofset sadece gereksiz degil, ZARARLI.

    Alicinin `baslik_ekle`si yeni baslikta yarim montaji siliyor; geciken
    eski bir cerceve YENI montaja ESKI degerlerle yazilirdi. Yani kuyrukta
    kalan cerceve "gec gider" degil, "YANLIS gider".

    Sayi degil ICERIK sinaniyor: iki turun cerceve sayisi ayni olabilir,
    onemli olan kuyrukta ESKI turdan bir sey KALMAMASI.
    """
    d = _dugum()
    d._on_formation_out(_Komut())               # 1. tur: ofsetler 0,1,2
    assert len(d._form_ofset_kuyruk) == 1

    k2 = _Komut()
    k2.offset_x = [50.0, 51.0, 52.0]            # 2. tur: apayri ofsetler
    d._on_formation_out(k2)

    assert d._form_ofset_iptal == 1, 'bayat cerceve atilmadi'
    # Pencere daha acilmadigi icin YENI turun iki cercevesi de kuyrukta.
    kuzeyler = []
    for yuk in d._form_ofset_kuyruk:
        v = pp.form_ofset_coz(yuk)
        kuzeyler += [o[0] for o in v.slot_ofsetleri()][:v.slot_sayisi]
    assert kuzeyler == [50.0, 51.0, 52.0], f'eski tur kuyrukta kalmis: {kuzeyler}'


# ------------------------------------------------------------ hiz kapisi

def test_HIZ_KAPISI_TURU_ATLAR():
    """2 Hz kapisi: pencere kapaliyken tur komple atlanir ve SAYILIR."""
    d = _dugum(mesh_hz=2.0)
    d._on_formation_out(_Komut())
    once = len(d.gonderilen)
    d._on_formation_out(_Komut())
    assert len(d.gonderilen) == once
    assert d._formasyon_seyreltilen == 1


def test_HIZ_KAPISI_LOOPBACK_I_DE_DURDURUR():
    """Lider ve takipciler AYNI hedef akisini gormek zorunda.

    Yalniz mesh seyreltilseydi lider 5 Hz, takipciler 2 Hz hedef gorurdu
    ve aralarinda sistematik kayma olurdu. Loopback'in var olma sebebi
    zaten "butun suru BIREBIR ayni hedefi gorsun".
    """
    d = _dugum(mesh_hz=2.0)
    d._on_formation_out(_Komut())
    once = len(d.yayinlanan)
    d._on_formation_out(_Komut())
    assert len(d.yayinlanan) == once


def test_KAPI_KAPALIYKEN_HER_TUR_GECER():
    """formasyon_mesh_hz=0 -> eski davranis; geri donus yolu acik kalsin."""
    d = _dugum(mesh_hz=0.0)
    d._on_formation_out(_Komut())
    d._on_formation_out(_Komut())
    assert d._formasyon_gonderilen == 2
    assert d._formasyon_seyreltilen == 0


# --------------------------------------------------------- adlandirilmis

def test_ADLANDIRILMIS_FORMASYON_ETKILENMEDI():
    """CIZGI/V/OKBASI'nda ofset cercevesi YOK — o yol aynen kaliyor."""
    d = _dugum()
    d._on_formation_out(_Komut(tip=3))           # FORMATION_CIZGI
    assert _ofsetler(d) == []
    assert not d._form_ofset_kuyruk
    assert d._formasyon_gonderilen == 1


def test_IKI_UCAKTA_TEK_CERCEVE():
    """2 ajan -> tek ofset paketi; bu yuzden kusur 2 ucakta GORUNMUYORDU."""
    d = _dugum()
    d._on_formation_out(_Komut(ajanlar=(1, 2)))
    assert len(_ofsetler(d)) == 1
    assert not d._form_ofset_kuyruk
