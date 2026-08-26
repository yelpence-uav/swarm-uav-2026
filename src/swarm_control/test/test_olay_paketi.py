# Copyright 2026 Yelpence
"""TIP_OLAY (0x16) — uçak olaylarının mesh paketi.

27 AGUSTOS 2026. Operator istegi: "her droneun loglarini gorebilecegim bir
kisim olsun ... tabii ki tum logu meshten akitamayiz, kisa olayin ne oldugunu
belli eden loglar akitalim."

TASARIM KARARLARI VE NEDEN TEST EDILDIKLERI
-------------------------------------------
1. PAKET BUYUMUYOR. olay_veri_t mevcut 16 baytlik yuke tam oturuyor;
   mesh_paket_t 25 bayt kaliyor, veri[18] ve UART_FRAME_BUF_SIZE=32
   degismiyor. Boyut testi bunu KILITLIYOR — birisi alan eklerse burada
   patlar, sahada "cerceve dilimi kaydi, alanlar sessizce yanlis cozuluyor"
   diye degil (bkz. mesh_config.h durum_veri_t static_assert'i, ayni ilke).

2. METIN TASINMIYOR. 16 bayt ~16 karakter eder. Onun yerine SystemEvent.msg'
   deki EVENT_* kodu tasiniyor, metni YKI uretiyor.

3. DEGER int16 x100 — float32 DEGIL. §1.2 birim kurali. Aralik disi deger
   KIRPILIR, sarmaz: sarma sessizce ters isaretli bir sayi uretir ve
   "batarya %-321" gibi YANLIS ama inandirici bir sonuc verir.

4. sira_no drone basina artan sayac. Broadcast'te ACK YOK, yani teslimat
   garanti edilemez — ama YKI BOSLUGU GOREBILIR ("7'den sonra 10 geldi,
   3 olay kacti"). Sessiz kayip yerine bilinen kayip.
"""

import struct

from swarm_control.esp32_bridge.packet_parser import (
    MODUL_ADLARI,
    MODUL_KODLARI,
    OLAY_DEGER_MAKS,
    OLAY_DEGER_MIN,
    TIP_OLAY,
    modul_kodu,
    olay_coz,
    olay_paketle,
)


def test_paket_16_bayt():
    """SOZLESME KILIDI: 16 bayti asarsa mesh yuku degisir."""
    p = olay_paketle(43, 2, 3, sira_no=1)
    assert len(p) == 16


def test_tip_kodu_serbest_araliktta():
    # Firmware tip tablosu MESH_TIP_TABLO_BOYU = 24; 0x16 = 22 < 24.
    assert TIP_OLAY == 0x16
    assert TIP_OLAY < 24


def test_gidis_donus():
    p = olay_paketle(
        olay_tipi=43, siddet=2, kaynak_id=3, sira_no=7, hedef_id=1,
        deger=3.88, modul='collision_avoidance', zaman_ms=123456,
        ek1=10, ek2=20,
    )
    o = olay_coz(p)
    assert o.olay_tipi == 43
    assert o.siddet == 2
    assert o.kaynak_id == 3
    assert o.hedef_id == 1
    assert abs(o.deger - 3.88) < 0.005
    assert o.sira_no == 7
    assert o.modul == 'collision_avoidance'
    assert o.zaman_ms == 123456
    assert (o.ek1, o.ek2) == (10, 20)


def test_negatif_deger():
    assert abs(olay_coz(olay_paketle(1, 0, 1, 0, deger=-12.5)).deger + 12.5) < 0.005


def test_deger_kirpiliyor_sarmiyor():
    """Aralik disi deger SARMAMALI — sarma inandirici bir yanlis uretir."""
    buyuk = olay_coz(olay_paketle(1, 0, 1, 0, deger=99999.0))
    assert 0 < buyuk.deger <= OLAY_DEGER_MAKS

    kucuk = olay_coz(olay_paketle(1, 0, 1, 0, deger=-99999.0))
    assert OLAY_DEGER_MIN <= kucuk.deger < 0


def test_modul_alt_ad_tabana_dusuyor():
    # Depoda 'collision_avoidance:korluk' gibi alt-adlar var; her biri icin
    # ayri kod tutmak tabloyu sisirir.
    assert modul_kodu('collision_avoidance:korluk') == MODUL_KODLARI['collision_avoidance']


def test_bilinmeyen_modul_sifir():
    assert modul_kodu('olmayan_modul') == 0
    assert modul_kodu('') == 0
    assert olay_coz(olay_paketle(1, 0, 1, 0, modul='olmayan')).modul == 'bilinmiyor'


def test_modul_tablosu_tutarli():
    """Kodlar BENZERSIZ ve tablo cift yonlu tutarli olmali.

    Cakisan bir kod, eski kayitlarin yanlis modul adiyla okunmasi demek —
    ve bu hicbir hata vermez.
    """
    assert len(set(MODUL_KODLARI.values())) == len(MODUL_KODLARI)
    assert all(MODUL_ADLARI[v] == k for k, v in MODUL_KODLARI.items())


def test_sira_no_sarmasi():
    """sira_no tek bayt: 255'ten sonra 0'a doner.

    YKI bosluk sayarken bunu hesaba katmak ZORUNDA — aksi halde her 256
    olayda bir sahte 'kayip' gorunur.
    """
    assert olay_coz(olay_paketle(1, 0, 1, sira_no=255)).sira_no == 255
    assert olay_coz(olay_paketle(1, 0, 1, sira_no=256)).sira_no == 0


def test_alanlar_bayt_sinirinda_kirpiliyor():
    """Tasma struct.error ATMAMALI.

    Olay yolu, bir alan tasti diye koprüyu dusurmemeli.
    """
    o = olay_coz(olay_paketle(999, 999, 999, sira_no=999, hedef_id=999,
                              zaman_ms=2**40, ek1=2**20, ek2=2**20))
    assert 0 <= o.olay_tipi <= 255
    assert 0 <= o.zaman_ms <= 0xFFFFFFFF


def test_struct_formati_degismedi():
    """Format degisirse iki taraf SESSIZCE ayrisir.

    Firmware C++ tarafi ayni bayt duzenini varsayiyor; bu test degisikligi
    gorunur kiliyor.
    """
    from swarm_control.esp32_bridge import packet_parser
    assert struct.calcsize(packet_parser._OLAY_FMT) == 16
    assert packet_parser._OLAY_FMT == '<BBBBhBBIHH'
