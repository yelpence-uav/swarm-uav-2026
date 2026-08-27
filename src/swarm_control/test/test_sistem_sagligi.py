# Copyright 2026 Yelpence
"""Pi sağlık ölçümlerinin olaya çevrilmesi — eşik ve histerezis.

27 AGUSTOS 2026. Operator: "rpi sicakligi 50 dereceyi gecti, ya da 45
derecenin altina indi gibi ... riskli bir dereceye gelirse kritik olan
loglardan olur."

HISTEREZIS NEDEN TEST EDILIYOR: tek esik olsaydi sinirda gezinen bir deger
her olcumde olay uretir, olay butcesini doldurur ve GERCEK olaylarin
dusmesine yol acardi. Ayni tuzaga `_diag_yayinla` ile bir kez dusuldu
(bkz. d8ae3df); bu testler tekrarini engelliyor.
"""

from swarm_control.esp32_bridge.sistem_sagligi import (
    SIDDET_INFO,
    SIDDET_KRITIK,
    SIDDET_UYARI,
    SistemSagligi,
    satir_coz,
)

ORNEK = ("2026-08-27T03:45:00+03:00 up=8123 v=5.14 t=58.2 thr=0x0 wifi=up "
         "ip=10.205.4.134 ssid=rpissid sig=56 load=0.42 mem=6100 disk=47% "
         "dok=drone1 ros=11")


def test_satir_cozuluyor():
    """Izleme satiri sayisal alanlara cozulur."""
    o = satir_coz(ORNEK)
    assert o['t'] == 58.2
    assert o['disk'] == 47.0        # % isareti atiliyor
    assert o['thr'] == 0.0          # onaltilik cozuluyor
    assert o['ros'] == 11.0
    assert 'ip' not in o            # sayisal olmayan alanlar atlaniyor
    assert 'dok' not in o


def test_thr_onaltilik():
    """Kisitlama bitleri onaltilik cozulur."""
    assert satir_coz('thr=0x50005')['thr'] == float(0x50005)


def test_normal_degerlerde_OLAY_YOK():
    """Normal olcumde olay uretilmez."""
    assert SistemSagligi().degerlendir(satir_coz(ORNEK)) == []


def test_sicaklik_esigi_ve_HISTEREZIS():
    s = SistemSagligi()
    assert s.degerlendir({'t': 65.0}) == []                  # normal

    olaylar = s.degerlendir({'t': 72.0})                     # UYARI acildi
    assert (60, SIDDET_UYARI, 72.0) in olaylar

    assert s.degerlendir({'t': 72.0}) == []                  # SURUYOR, tekrar YOK
    assert s.degerlendir({'t': 68.0}) == []                  # kapanma esiginin ustunde
    olaylar = s.degerlendir({'t': 60.0})                     # kapandi
    assert (60, SIDDET_INFO, 60.0) in olaylar


def test_sinirda_GEZINME_olay_yagmuru_uretmiyor():
    """En onemli test: 70 civarinda gezinen deger tek olay uretmeli."""
    s = SistemSagligi()
    s.degerlendir({'t': 71.0})                               # acildi
    toplam = sum(len(s.degerlendir({'t': v}))
                 for v in [69.5, 70.2, 69.0, 70.5, 68.0, 69.9] * 5)
    assert toplam == 0, f"{toplam} gereksiz olay uretildi"


def test_kritik_ve_uyari_AYRI_izleniyor():
    """Kritik ve uyari esikleri ayri durum tutar."""
    s = SistemSagligi()
    olaylar = s.degerlendir({'t': 85.0})
    tipler = {(t, sd) for t, sd, _ in olaylar}
    assert (60, SIDDET_KRITIK) in tipler
    assert (60, SIDDET_UYARI) in tipler        # ikisi de acildi


def test_dusuk_gerilim_biti():
    """Kisitlama biti sifirdan farkliysa kritik."""
    s = SistemSagligi()
    assert s.degerlendir({'thr': 0.0}) == []
    olaylar = s.degerlendir({'thr': float(0x50005)})
    assert (61, SIDDET_KRITIK, float(0x50005)) in olaylar
    assert s.degerlendir({'thr': float(0x50005)}) == []      # suruyor
    assert (61, SIDDET_INFO, 0.0) in s.degerlendir({'thr': 0.0})


def test_bellek_ALT_yonlu():
    """Bellek AZALINCA kotu — ust yonlu esiklerin tersi."""
    s = SistemSagligi()
    assert s.degerlendir({'mem': 1000.0}) == []
    assert (63, SIDDET_UYARI, 250.0) in s.degerlendir({'mem': 250.0})
    assert s.degerlendir({'mem': 350.0}) == []               # histerezis araligi
    assert (63, SIDDET_INFO, 500.0) in s.degerlendir({'mem': 500.0})


def test_disk_esigi():
    """Disk doluluk esigi olay uretir."""
    s = SistemSagligi()
    assert s.degerlendir({'disk': 70.0}) == []
    assert (62, SIDDET_UYARI, 90.0) in s.degerlendir({'disk': 90.0})


def test_ros_dugum_eksigi():
    """Dugum sayisi dusunce kritik olay uretilir."""
    s = SistemSagligi()
    assert s.degerlendir({'ros': 11.0}) == []
    assert (66, SIDDET_KRITIK, 2.0) in s.degerlendir({'ros': 2.0})
    assert s.degerlendir({'ros': 6.0}) == []                 # histerezis
    assert (66, SIDDET_INFO, 11.0) in s.degerlendir({'ros': 11.0})


def test_eksik_alan_cokmeye_yol_acmiyor():
    """sistem_durum satiri yarim yazilmis olabilir (kesinti aninda)."""
    assert SistemSagligi().degerlendir({}) == []
    assert SistemSagligi().degerlendir({'bilinmeyen': 1.0}) == []
