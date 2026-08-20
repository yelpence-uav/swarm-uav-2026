# Copyright 2026 Yelpence
"""P0.12(b): LAND/RTL/DISARM bekleyen GOTO'lari kuyruktan dusurur.

OLCULEN ARIZA (20 Agustos 2026, kod okunarak dogrulandi):
`_guided_gonder` kuyruk ayiklamasini YALNIZ ayni hedefe giden TIP_GOTO icin
yapiyordu; `land` bir TIP_KOMUT oldugu icin bekleyen GOTO tekrarlari kuyrukta
KALIYORDU. Guided komutlar 4 kopya gonderildigi ve gorev kosucusu 0.2 sn'de
bir goto POST ettigi icin iptal aninda kuyrukta tipik olarak 3-4 GOTO oluyor.

Zincir: land -> ucak AUTO.LAND'e gecer ve _guided_hedef=None olur; ~0.25 sn
sonra bayat GOTO varir; `_isle_goto` KOSULSUZ `_guided_string('offboard')`
yollayip `_guided_hedef`i YENIDEN kurar -> PX4 AUTO.LAND'dan cikip OFFBOARD'a
doner ve yurutucu ucagi eski hedefe geri surer. 10 Hz'lik `_guided_hedef_tekrar`
o hedefi surekli tazeledigi icin px4_bridge'in 0.5 sn bayatlama korumasi da
hic tetiklenmez: ucak bayat hedefte ASILI KALIR.

En kotu hali iptal aninda: operator kesmek istiyor, boru hatti ucagi hedefe
geri cekiyor.
"""

from unittest.mock import MagicMock

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.esp32_bridge_node import Esp32BridgeNode


def _kopru():
    """ROS'suz minimal kopru — yalniz kuyruk alanlari."""
    n = object.__new__(Esp32BridgeNode)
    n._guided_kuyruk = []
    n.get_logger = MagicMock()
    return n


def _goto(n, hedef, yuk=b'x'):
    n._guided_gonder(pp.TIP_GOTO, hedef, yuk)


def _komut(n, hedef, flag):
    n._guided_gonder(pp.TIP_KOMUT, hedef, b'k', bayrak=flag)


def _bayraklar(n, hedef):
    return [k.get('bayrak', 0) for k in n._guided_kuyruk
            if k['tip'] == pp.TIP_KOMUT and k['hedef'] == hedef]


def _tipler(n):
    return [(k['tip'], k['hedef']) for k in n._guided_kuyruk]


# --- ASIL ARIZA -------------------------------------------------------------

def test_land_bekleyen_gotolari_dusurur():
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert (pp.TIP_GOTO, 1) not in _tipler(n), 'bayat GOTO kuyrukta kaldi'
    assert (pp.TIP_KOMUT, 1) in _tipler(n), 'land kuyruga girmedi'


def test_rtl_de_dusurur():
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_RTL)
    assert (pp.TIP_GOTO, 1) not in _tipler(n)


def test_disarm_da_dusurur():
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_DISARM)
    assert (pp.TIP_GOTO, 1) not in _tipler(n)


# --- KAPSAM: yalniz O UCAK -------------------------------------------------

def test_diger_ucagin_gotosuna_DOKUNMAZ():
    """Bir ucagi indirmek digerinin gorevini kesmemeli."""
    n = _kopru()
    _goto(n, 1)
    _goto(n, 3)
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert (pp.TIP_GOTO, 3) in _tipler(n), 'diger ucagin GOTOsu dusuruldu'
    assert (pp.TIP_GOTO, 1) not in _tipler(n)


# --- BOZULMAMASI GEREKENLER -------------------------------------------------

def test_takeoff_gotolari_DUSURMEZ():
    """Yalniz iptal komutlari ayiklar; takeoff/arm sirasi bozulmamali."""
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_TAKEOFF)
    assert (pp.TIP_GOTO, 1) in _tipler(n)


def test_arm_gotolari_DUSURMEZ():
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_ARM)
    assert (pp.TIP_GOTO, 1) in _tipler(n)


# --- BAYAT TAKEOFF (20 Agustos'ta SAHADA olculdu) --------------------------
#
#   784.475  land
#   784.779  takeoff:10.0     <- LAND'den 0.3 sn SONRA
#   785.182  takeoff:10.0     <- LAND'den 0.7 sn SONRA
#
# Havadaki karsiligi: inis komutu verilir, ucak alcalmaya baslar, bayat
# takeoff varir ve ucak GERI TIRMANIR.

def test_land_bekleyen_TAKEOFFU_dusurur():
    n = _kopru()
    _komut(n, 1, pp.KOMUT_FLAG_TAKEOFF)
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert pp.KOMUT_FLAG_TAKEOFF not in _bayraklar(n, 1), 'bayat takeoff kaldi'
    assert pp.KOMUT_FLAG_LAND in _bayraklar(n, 1), 'land kuyruga girmedi'


def test_disarm_bekleyen_ARMI_dusurur():
    """18 Agustos'ta olculen 'disarm kavgasi'nin kok nedeni."""
    n = _kopru()
    _komut(n, 1, pp.KOMUT_FLAG_ARM)
    _komut(n, 1, pp.KOMUT_FLAG_DISARM)
    assert pp.KOMUT_FLAG_ARM not in _bayraklar(n, 1), 'bayat arm kaldi'
    assert pp.KOMUT_FLAG_DISARM in _bayraklar(n, 1)


def test_rtl_de_takeoffu_dusurur():
    n = _kopru()
    _komut(n, 1, pp.KOMUT_FLAG_TAKEOFF)
    _komut(n, 1, pp.KOMUT_FLAG_RTL)
    assert pp.KOMUT_FLAG_TAKEOFF not in _bayraklar(n, 1)


def test_land_GOTO_ve_TAKEOFFU_birlikte_dusurur():
    n = _kopru()
    _goto(n, 1)
    _komut(n, 1, pp.KOMUT_FLAG_TAKEOFF)
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert (pp.TIP_GOTO, 1) not in _tipler(n)
    assert pp.KOMUT_FLAG_TAKEOFF not in _bayraklar(n, 1)


def test_land_DIGER_ucagin_takeoffuna_dokunmaz():
    """Bir ucagi indirmek digerinin kalkisini kesmemeli."""
    n = _kopru()
    _komut(n, 3, pp.KOMUT_FLAG_TAKEOFF)
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert pp.KOMUT_FLAG_TAKEOFF in _bayraklar(n, 3), 'diger ucagin takeoffu dustu'


def test_iptal_komutlari_BIRBIRINI_ayiklamaz():
    """land/rtl/disarm farkli niyetler — her biri ucaga ULASMALI."""
    n = _kopru()
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    _komut(n, 1, pp.KOMUT_FLAG_RTL)
    _komut(n, 1, pp.KOMUT_FLAG_DISARM)
    assert len(_bayraklar(n, 1)) == 3, 'iptal komutlari birbirini ezdi'


def test_eski_davranis_korundu_yeni_goto_eskisini_ezer():
    """Ayni hedefe yeni GOTO gelince eskisinin tekrarlari anlamsiz — atilir."""
    n = _kopru()
    _goto(n, 1, b'eski')
    _goto(n, 1, b'yeni')
    kayitlar = [k for k in n._guided_kuyruk if k['tip'] == pp.TIP_GOTO]
    assert len(kayitlar) == 1
    assert kayitlar[0]['payload'] == b'yeni'


def test_bos_kuyrukta_land_patlamaz():
    n = _kopru()
    _komut(n, 1, pp.KOMUT_FLAG_LAND)
    assert _tipler(n) == [(pp.TIP_KOMUT, 1)]
