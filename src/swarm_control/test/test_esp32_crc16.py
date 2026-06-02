"""test_esp32_crc16.py — CRC16-CCITT birim testleri."""

from swarm_control.esp32_bridge.crc16 import crc16, crc16_dogrula


def test_bos_giris():
    """Boş girişte CRC başlangıç değeri 0xFFFF olmalı."""
    assert crc16(b'') == 0xFFFF


def test_bilinen_vektor():
    """'123456789' için CRC16-CCITT (init=0xFFFF) referans değeri 0x29B1."""
    assert crc16(b'123456789') == 0x29B1


def test_dogrula_eslesme():
    """crc16_dogrula doğru değerde True döner."""
    veri = b'\x04\x02test'
    assert crc16_dogrula(veri, crc16(veri))


def test_dogrula_uyumsuz():
    """crc16_dogrula yanlış değerde False döner."""
    assert not crc16_dogrula(b'abc', 0x0000)


def test_16bit_sinirinda():
    """Sonuç her zaman 16 bit içinde kalmalı."""
    assert 0 <= crc16(b'\xff' * 32) <= 0xFFFF
