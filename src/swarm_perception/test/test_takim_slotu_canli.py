# Copyright 2026 Yelpence
"""TAKIM SLOTU CANLI DEGISEBILMELI — konteyner yeniden baslatmadan.

🔴 9 EYLUL 2026, finale bir gun kala, operator karari.

QR'in `team` tablosu takim NUMARASIYLA degil SLOT ile anahtarli:

    {"qr":2,"w":4,"mis":[[...],[...]],"team":{"1":[2,5]}}
                                              ↑ ARANAN ANAHTAR

Ucak `str(team_slot)` ariyor. Slot yanlissa QR HIC okunmaz; tek gorunen
satir `Takim slotu N tabloda yok` olur. Hakem slotu GOREV ANINDA veriyor,
yani deger sahada ogreniliyor.

Eski davranis: slot dedektore ACILISTA gomuluyordu. Degistirmek konteyner
yeniden baslatmak demekti; o da QR KONUM TABLOSUNU siliyor ve operatorun
tabloyu tekrar sermesini gerektiriyordu — gorev aninda kabul edilemez.

Simdi `ros2 param set /vision_node team_slot N` aninda geciyor.
Saha araci: `deploy/yki/takim_slot.sh`.
"""

import pathlib
import sys
from unittest.mock import MagicMock

# pyzbar saha kutuphanesi laptopta yok; JSON ayristirma ondan BAGIMSIZ.
# test_qr_detector.py / test_leav_pas_gecme.py ile ayni yol.
sys.modules.setdefault('pyzbar', MagicMock())
sys.modules.setdefault('pyzbar.pyzbar', MagicMock())

from swarm_perception.vision_node.qr_detector import QRDetector  # noqa: E402

# vision_node_core ROS'a bagimli (rcl_interfaces); dizustunde import
# EDILEMEZ. O yuzden kaynak METIN olarak okunuyor — depodaki oteki
# dugum testleriyle ayni desen.
_KAYNAK = (pathlib.Path(__file__).resolve().parents[1] / 'swarm_perception'
           / 'vision_node' / 'vision_node_core.py').read_text()


def _govde(ad):
    k = _KAYNAK
    i = k.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = k.find('\n    def ', i + 1)
    return k[i:j if j > 0 else len(k)]


# ------------------------------------------------------------ asil istek

def test_SLOT_PARAM_GERI_CAGRIDA_ISLENIYOR():
    """🔴 Kusurun ta kendisi: slot yalniz aciliksta okunuyordu."""
    g = _govde('_on_param_degisti')
    assert "'team_slot'" in g, (
        'team_slot parametre geri cagrisinda islenmiyor — degistirmek icin '
        'konteyner yeniden baslatmak gerekir, o da QR tablosunu siler'
    )


def test_DEDEKTORE_YAZILIYOR():
    """Parametreyi kabul edip dedektore yazmazsan hicbir sey degismez."""
    g = _govde('_on_param_degisti')
    assert '_team_slot' in g and 'int(' in g


def test_DEGISIKLIK_LOGLANIYOR():
    """Sessiz degisiklik, sonra 'neden okumuyor' sorusuna donusur."""
    g = _govde('_on_param_degisti')
    i = g.find("'team_slot'")
    assert 'get_logger' in g[i:i + 900]


def test_ESIK_YOLU_BOZULMADI():
    """Inis bolgesi esikleri hala ayni geri cagriyla guncelleniyor."""
    g = _govde('_on_param_degisti')
    assert 'min_zone_area_px' in g and 'LandingZoneDetector' in g


# ------------------------------------------------- dedektor davranisi

def test_SLOT_DEGISINCE_BASKA_PAKET_OKUNUR():
    """Ayni QR, slot degisince BASKA gorev paketi vermeli."""
    d = QRDetector(team_slot=1)
    ham = ('{"qr":2,"w":4,"mis":[[["alt",12]],[["alt",25]]],'
           '"team":{"1":[1,5],"2":[2,0]}}')
    a = d._parse_qr_text(ham)
    assert a.get('next_qr') == 5, a
    d._team_slot = 2
    b = d._parse_qr_text(ham)
    assert b.get('next_qr') == 0, b
    assert a.get('altitude_agl_m') != b.get('altitude_agl_m')


def test_SLOT_TABLODA_YOKSA_SEBEP_YAZILIYOR():
    """Sahada gorulecek tek ipucu bu satir — kaybolmamali."""
    d = QRDetector(team_slot=7)
    r = d._parse_qr_text('{"qr":1,"w":1,"mis":[[]],"team":{"1":[1,2]}}')
    assert 'slot' in r.get('error_message', '').lower()


# --------------------------------------------------------- saha araci

def test_SAHA_ARACI_VAR():
    """Gorev aninda betik aranmaz; hazir ve calistirilabilir olmali."""
    yol = (pathlib.Path(__file__).resolve().parents[3]
           / 'deploy' / 'yki' / 'takim_slot.sh')
    assert yol.exists(), 'deploy/yki/takim_slot.sh yok'
    m = yol.read_text()
    assert 'ros2 param set /vision_node team_slot' in m
    assert '--oku' in m, 'mevcut degeri okuma yolu yok'
