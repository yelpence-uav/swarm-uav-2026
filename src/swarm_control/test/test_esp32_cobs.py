"""test_esp32_cobs.py - COBS encode/decode birim testleri."""

from swarm_control.esp32_bridge.cobs import cobs_decode, cobs_encode


def test_round_trip_basit():
    """encode -> (0x00 at) -> decode orijinali vermeli."""
    veri = b'\x04\x02\x10\x20\x30'
    kodlu = cobs_encode(veri)
    assert kodlu[-1] == 0x00
    assert cobs_decode(kodlu[:-1]) == veri


def test_round_trip_icinde_sifir():
    """Veri içindeki 0x00 baytları korunmalı."""
    veri = b'\x01\x00\x02\x00\x00\x03'
    kodlu = cobs_encode(veri)
    assert 0x00 not in kodlu[:-1]  # ayraç hariç 0x00 olmamalı
    assert cobs_decode(kodlu[:-1]) == veri


def test_kodlu_veride_sifir_yok():
    """COBS kodlu çıktıda (ayraç hariç) 0x00 bulunmamalı."""
    veri = bytes(range(20))  # 0x00 ile başlar
    kodlu = cobs_encode(veri)
    assert 0x00 not in kodlu[:-1]


def test_bos_giris_decode():
    """Boş giriş boş çıktı vermeli."""
    assert cobs_decode(b'') == b''


def test_bozuk_kod_sifir():
    """Geçersiz (içinde 0x00 olan) kod boş döner."""
    assert cobs_decode(b'\x00\x01') == b''
