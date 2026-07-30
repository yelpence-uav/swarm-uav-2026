"""test_formasyon_montaj.py - çok parçalı formasyon montajı birim testleri.

Bu modül ROS'a bağımlı değil (bilinçli), o yüzden testleri de düz pytest.
"""

import math

import pytest

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.formasyon_montaj import (
    FormasyonMontaj,
    parcala,
)
from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_CUSTOM,
    FORMATION_OKBASI,
    compute_slot_offsets,
)


def _baslik(tip=FORMATION_OKBASI, slotlar=(1, 2, 3), spacing_m=5.0,
            devam=False, kanat=45.0, merkez=(0.0, 0.0, -15.0),
            heading=0.0, hiz=3.0) -> pp.FormasyonVeri:
    """Gerçek codec'ten geçirerek başlık üretir - kuantizasyon dahil."""
    payload, uyarilar = pp.formasyon_paketle(
        formasyon_tipi=tip,
        merkez_kuzey_m=merkez[0], merkez_dogu_m=merkez[1],
        merkez_asagi_m=merkez[2], heading_deg=heading,
        spacing_m=spacing_m, slot_ajan=list(slotlar),
        maks_hiz_mps=hiz, kanat_alfa_deg=kanat, devam_var=devam,
    )
    assert uyarilar == [], uyarilar
    return pp.formasyon_coz(payload)


def test_tek_paket_hemen_tamamlanir():
    """3 ajan + adlandırılmış formasyon = tek paket, anında montaj."""
    m = FormasyonMontaj()
    sonuc = m.baslik_ekle(1, _baslik(), simdi=100.0)
    assert sonuc is not None
    assert sonuc.ajan_ids == [1, 2, 3]
    assert sonuc.formasyon_tipi == FORMATION_OKBASI
    assert abs(sonuc.spacing_m - 5.0) < 0.05
    assert abs(sonuc.merkez_asagi_m + 15.0) < 0.05
    assert len(sonuc.ofsetler) == 3


def test_offsetler_compute_slot_offsets_ile_AYNI():
    """Montajın ürettiği offsetler formation_node'un hesabıyla birebir olmalı.

    Ayrışırsa lider ile takipçi farklı slot geometrisi kullanır ve formasyon
    bozulur — bu testin varlık sebebi o.
    """
    m = FormasyonMontaj()
    sonuc = m.baslik_ekle(1, _baslik(slotlar=(3, 1, 2)), simdi=0.0)
    assert sonuc is not None
    beklenen = compute_slot_offsets(
        FORMATION_OKBASI, 3, sonuc.spacing_m,
        math.radians(sonuc.kanat_alfa_deg),
    )
    for got, bek in zip(sonuc.ofsetler, beklenen):
        assert all(abs(a - b) < 1e-9 for a, b in zip(got, bek))


def test_slot_sirasi_atama_olarak_korunur():
    """agent_ids sırası slot atamasıdır; bozulursa çarpışma riski doğar."""
    m = FormasyonMontaj()
    sonuc = m.baslik_ekle(1, _baslik(slotlar=(3, 1, 2)), simdi=0.0)
    assert sonuc.ajan_ids == [3, 1, 2]


def test_bes_ajan_devam_paketi_bekler():
    """devam bayrağı setse başlık tek başına montajı tamamlamamalı."""
    m = FormasyonMontaj()
    b = _baslik(slotlar=(1, 2, 3, 4, 5), devam=True)
    assert m.baslik_ekle(1, b, simdi=0.0) is None      # bekliyor

    sonuc = m.devam_ekle(1, pp.formasyon_devam_coz(
        pp.formasyon_devam_paketle([5, 0, 0, 0])), simdi=0.1)
    assert sonuc is not None
    assert sonuc.ajan_ids == [1, 2, 3, 4, 5]
    assert len(sonuc.ofsetler) == 5


def test_custom_offset_paketlerini_bekler():
    """CUSTOM formülden türetilemez; offsetler gelene kadar tamamlanmamalı."""
    m = FormasyonMontaj()
    b = _baslik(tip=FORMATION_CUSTOM, slotlar=(1, 2, 3))
    assert m.baslik_ekle(1, b, simdi=0.0) is None

    p0, _ = pp.form_ofset_paketle(0, [(2.3, -1.7, 0.0), (-4.1, 3.2, -0.5)])
    assert m.ofset_ekle(1, pp.form_ofset_coz(p0), simdi=0.05) is None  # 1 slot eksik

    p1, _ = pp.form_ofset_paketle(2, [(0.0, 6.0, 0.0)])
    sonuc = m.ofset_ekle(1, pp.form_ofset_coz(p1), simdi=0.1)
    assert sonuc is not None
    assert sonuc.formasyon_tipi == FORMATION_CUSTOM
    assert len(sonuc.ofsetler) == 3
    assert all(abs(a - b) < 0.05
               for a, b in zip(sonuc.ofsetler[0], (2.3, -1.7, 0.0)))
    assert all(abs(a - b) < 0.05
               for a, b in zip(sonuc.ofsetler[2], (0.0, 6.0, 0.0)))


def test_zaman_asimi_yarim_montaji_duşurur():
    """Eksik parça sonsuza kadar beklenmemeli; sayaç artmalı."""
    m = FormasyonMontaj(zaman_asimi_s=0.5)
    m.baslik_ekle(1, _baslik(slotlar=(1, 2, 3, 4, 5), devam=True), simdi=0.0)
    # 0.6 sn sonra devam gelirse montaj çoktan düşmüş olmalı
    sonuc = m.devam_ekle(1, [5, 0, 0, 0], simdi=0.6)
    assert sonuc is None
    assert m.zaman_asimi_sayisi >= 1
    assert m.sahipsiz_parca_sayisi >= 1


def test_yeni_baslik_eski_yarim_montaji_dusurur():
    """5 Hz akışta yarım eski tur yeni turla KARIŞMAMALI."""
    m = FormasyonMontaj()
    m.baslik_ekle(1, _baslik(slotlar=(1, 2, 3, 4, 5), devam=True), simdi=0.0)
    # yeni tur: 3 ajan, tek paket -> hemen tamamlanır ve eski montaj düşer
    sonuc = m.baslik_ekle(1, _baslik(slotlar=(1, 2, 3)), simdi=0.2)
    assert sonuc is not None
    assert sonuc.ajan_ids == [1, 2, 3]
    assert m.zaman_asimi_sayisi >= 1


def test_kaynaklar_birbirini_bozmaz():
    """İki farklı drone aynı anda formasyon yayınlarsa montajlar ayrı olmalı."""
    m = FormasyonMontaj()
    m.baslik_ekle(1, _baslik(slotlar=(1, 2, 3, 4, 5), devam=True), simdi=0.0)
    sonuc2 = m.baslik_ekle(2, _baslik(slotlar=(7, 8)), simdi=0.01)
    assert sonuc2 is not None and sonuc2.ajan_ids == [7, 8]
    sonuc1 = m.devam_ekle(1, [5, 0, 0, 0], simdi=0.02)
    assert sonuc1 is not None and sonuc1.ajan_ids == [1, 2, 3, 4, 5]


def test_sahipsiz_parca_sayilir():
    """Başlığı görülmemiş devam/offset parçası sessizce yutulmamalı."""
    m = FormasyonMontaj()
    assert m.devam_ekle(9, [1, 2, 0, 0], simdi=0.0) is None
    assert m.sahipsiz_parca_sayisi == 1


def test_bilinmeyen_formasyon_tipi_dusurulur():
    """formation_type=0 (UNKNOWN) montajı tamamlamamalı.

    Adım 1c'de görüldü: 0 ile devam etmek compute_slot_offsets()'te
    ValueError demek. Burada montaj düşürülüyor, çağıran uyarıyor.
    """
    m = FormasyonMontaj()
    payload, _ = pp.formasyon_paketle(0, 0, 0, 0, 0, 5.0, [1, 2, 3])
    assert m.baslik_ekle(1, pp.formasyon_coz(payload), simdi=0.0) is None


def test_gecersiz_spacing_dusurulur():
    """spacing 0 compute_slot_offsets'te ValueError; montaj düşmeli."""
    m = FormasyonMontaj()
    payload, _ = pp.formasyon_paketle(FORMATION_CIZGI, 0, 0, 0, 0, 0.0, [1, 2])
    assert m.baslik_ekle(1, pp.formasyon_coz(payload), simdi=0.0) is None


def test_bos_slot_listesi_dusurulur():
    """Hiç ajan yoksa montaj tamamlanmamalı."""
    m = FormasyonMontaj()
    payload, _ = pp.formasyon_paketle(FORMATION_OKBASI, 0, 0, 0, 0, 5.0, [])
    assert m.baslik_ekle(1, pp.formasyon_coz(payload), simdi=0.0) is None


@pytest.mark.parametrize('n,beklenen_devam,beklenen_dilim', [
    (2, False, 0), (4, False, 0), (5, True, 0), (8, True, 0),
])
def test_parcala_adlandirilmis(n, beklenen_devam, beklenen_dilim):
    """Adlandırılmış formasyonda offset paketi HİÇ gerekmez."""
    devam, dilimler = parcala(list(range(1, n + 1)), FORMATION_OKBASI)
    assert devam is beklenen_devam
    assert len(dilimler) == beklenen_dilim


@pytest.mark.parametrize('n,beklenen_dilim', [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3)])
def test_parcala_custom_offset_dilimleri(n, beklenen_dilim):
    """CUSTOM'da paket başına 2 slot -> ceil(n/2) dilim."""
    ofsetler = [(float(i), 0.0, 0.0) for i in range(n)]
    _, dilimler = parcala(list(range(1, n + 1)), FORMATION_CUSTOM, ofsetler)
    assert len(dilimler) == beklenen_dilim
    assert dilimler[0][0] == 0
    if beklenen_dilim > 1:
        assert dilimler[1][0] == 2


def test_gonder_al_uctan_uca_custom():
    """parcala() + codec + montaj: CUSTOM için tam tur."""
    ajanlar = [4, 2, 7]
    ofsetler = [(1.0, 2.0, 0.0), (-3.0, 4.0, -0.5), (5.0, -6.0, 1.5)]
    devam, dilimler = parcala(ajanlar, FORMATION_CUSTOM, ofsetler)
    assert devam is False and len(dilimler) == 2

    m = FormasyonMontaj()
    b = _baslik(tip=FORMATION_CUSTOM, slotlar=tuple(ajanlar))
    sonuc = m.baslik_ekle(5, b, simdi=0.0)
    assert sonuc is None
    for i, (slot_bas, dilim) in enumerate(dilimler):
        payload, uyarilar = pp.form_ofset_paketle(slot_bas, dilim)
        assert uyarilar == []
        sonuc = m.ofset_ekle(5, pp.form_ofset_coz(payload), simdi=0.01 * (i + 1))
    assert sonuc is not None
    assert sonuc.ajan_ids == ajanlar
    for got, bek in zip(sonuc.ofsetler, ofsetler):
        assert all(abs(a - b) < 0.05 for a, b in zip(got, bek))
