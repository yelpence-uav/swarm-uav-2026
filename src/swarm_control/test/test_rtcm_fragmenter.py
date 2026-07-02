"""test_rtcm_fragmenter.py — fragment_for_inject birim testleri."""

import pytest

from swarm_control.px4_interface.rtcm_packing import fragment_for_inject


def test_kucuk_mesaj_tek_parca_fragmented_false():
    """max_payload altı mesaj tek parça döner, fragmented=False."""
    mesaj = b'\x10' * 50
    parcalar = fragment_for_inject(mesaj, max_payload=300)
    assert len(parcalar) == 1
    chunk, fragmented = parcalar[0]
    assert chunk == mesaj
    assert fragmented is False


def test_tam_sinir_uzunlugu_tek_parca():
    """Tam max_payload uzunluğu tek parça, fragmented=False."""
    mesaj = b'\xAA' * 300
    parcalar = fragment_for_inject(mesaj, max_payload=300)
    assert len(parcalar) == 1
    chunk, fragmented = parcalar[0]
    assert chunk == mesaj
    assert fragmented is False


def test_buyuk_mesaj_birden_fazla_parca():
    """> max_payload mesaj fragmanlara bölünür, hepsi fragmented=True."""
    mesaj = bytes(range(256)) * 3  # 768 bayt
    parcalar = fragment_for_inject(mesaj, max_payload=300)
    # 768 / 300 = 2.56 → 3 parça
    assert len(parcalar) == 3
    for _, fragmented in parcalar:
        assert fragmented is True


def test_buyuk_mesaj_birlestirilince_korunur():
    """Fragmanlar birleştirilince orijinal mesaj geri elde edilmeli."""
    mesaj = bytes((i * 7) & 0xFF for i in range(701))
    parcalar = fragment_for_inject(mesaj, max_payload=300)
    yeniden = b''.join(c for c, _ in parcalar)
    assert yeniden == mesaj


def test_bos_mesaj_bos_liste():
    """Boş mesaj boş liste döner (yayınlanacak fragman yok)."""
    assert fragment_for_inject(b'', max_payload=300) == []


def test_chunk_boyutlari_max_payload_asmaz():
    """Hiçbir fragman max_payload sınırını aşmamalı."""
    mesaj = b'\x00' * 1000
    parcalar = fragment_for_inject(mesaj, max_payload=128)
    for chunk, _ in parcalar:
        assert len(chunk) <= 128


def test_gecersiz_max_payload_value_error():
    """0 ve negatif max_payload ValueError fırlatmalı."""
    with pytest.raises(ValueError):
        fragment_for_inject(b'\x01', max_payload=0)
    with pytest.raises(ValueError):
        fragment_for_inject(b'\x01', max_payload=-5)


def test_son_parca_kismi_dolulukta_olabilir():
    """Son fragman max_payload'tan kısa olabilir (toplam bölünmez)."""
    mesaj = b'\xBB' * 350  # 300 + 50
    parcalar = fragment_for_inject(mesaj, max_payload=300)
    assert len(parcalar) == 2
    assert len(parcalar[0][0]) == 300
    assert len(parcalar[1][0]) == 50
    assert parcalar[0][1] is True
    assert parcalar[1][1] is True
