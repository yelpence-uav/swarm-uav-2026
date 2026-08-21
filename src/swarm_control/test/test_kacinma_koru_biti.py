# Copyright 2026 Yelpence
"""P0.16: kacinma korlugu YKI'ye ulasmiyordu — mesh'te TIP_EVENT yok.

21 AGUSTOS 2026 gecesi, uctan uca olculdu:

    ylp00 ca.log          KACINMA KORU: drone3 ...      VAR
    ylp00 public/events   KACINMA KORU: ...             VAR
    DIZUSTU public/events                               BOS
    YKI websocket "alerts"                              BOS

Kok neden: mesh protokolunde TIP_EVENT diye bir paket tipi YOK
(packet_parser 21 tip tasiyor, olay yok). esp32_bridge SystemEvent'leri
yalniz YAYINLIYOR; mesh'e gondermek icin abonelik hic kurulmamis. Yani
ucakta uretilen HICBIR olay YKI'ye ulasmiyor.

COZUM: DURUM paketinin `bayraklar2` alaninda BOS BIR BIT. Kritik nokta —
DURUM paketini PI olusturuyor (esp32_bridge -> durum_paketle), ESP yalniz
bayt tasiyor. Yani bu TAMAMEN ROS TARAFI bir degisiklik: firmware
degismiyor, UC ESP'yi yeniden flashlamak GEREKMIYOR, paket boyutu ayni
kaliyor (16 bayt) ve eski aliciler biti yok sayiyor.
"""

from swarm_control.esp32_bridge import packet_parser as pp


def test_bit_degeri_SOZLESME():
    """Bit degeri firmware ve Pi arasinda paylasilan sozlesme.

    Degisirse alici tarafta BASKA bir bayrak okunur ve kimse fark etmez —
    bu yuzden test degeri acikca kilitliyor.
    """
    assert pp.DURUM2_BAYRAK_KACINMA_KORU == 0x04
    # Mevcut bitlerle CAKISMAMALI
    assert pp.DURUM2_BAYRAK_KACINMA_KORU & pp.DURUM2_BAYRAK_READY_TO_ARM == 0
    assert pp.DURUM2_BAYRAK_KACINMA_KORU & pp.DURUM2_BAYRAK_ORIGIN_SYNCED == 0


def _paketle(**kw):
    varsayilan = dict(
        drone_id=1, durum=1, armed=0, gps_fix_type=6, battery_pct=100,
        battery_volt=12.6, ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=1,
        rssi=0, mesh_link_ok=1,
    )
    varsayilan.update(kw)
    return pp.durum_paketle(**varsayilan)


def test_bit_KURULUYOR_ve_COZULUYOR():
    ham = _paketle(kacinma_koru=1)
    assert pp.durum_coz(ham).kacinma_koru is True


def test_bit_VARSAYILAN_KAPALI():
    """Eski cagrilar bu parametreyi vermiyor; sessizce 1 olmamali."""
    assert pp.durum_coz(_paketle()).kacinma_koru is False


def test_PAKET_BOYUTU_DEGISMEDI():
    """16 bayt sozlesmesi: boyut degisirse cerceve dilimi kayar ve BUTUN
    alanlar sessizce yanlis okunur (mesh_config.h:300 sozlesme kilidi)."""
    assert len(_paketle(kacinma_koru=1)) == len(_paketle(kacinma_koru=0))


def test_DIGER_BAYRAKLARI_BOZMUYOR():
    """Ayni bayt icinde ready_to_arm ve origin_synced duruyor."""
    d = pp.durum_coz(_paketle(kacinma_koru=1, ready_to_arm=1, origin_synced=1))
    assert d.kacinma_koru is True
    assert d.ready_to_arm is True
    assert d.origin_synced is True
    d2 = pp.durum_coz(_paketle(kacinma_koru=1, ready_to_arm=0, origin_synced=0))
    assert d2.kacinma_koru is True
    assert d2.ready_to_arm is False
    assert d2.origin_synced is False


def test_GERIYE_UYUMLU_eski_alici_biti_yok_sayar():
    """Eski alici bayraklar2'yi maskeleyerek okuyor; yeni bit onu bozmamali."""
    d = pp.durum_coz(_paketle(kacinma_koru=1, ready_to_arm=1))
    assert d.ready_to_arm is True, 'yeni bit eski bayragi bozdu'
