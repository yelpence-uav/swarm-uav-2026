"""CRC16-CCITT (XModem) hesaplama.

ESP32 firmware'indeki crc16() ile ayni parametreler:
Polinom=0x1021, Baslangic=0xFFFF, yansitma yok.
"""

_POLY = 0x1021
_INIT = 0xFFFF
_MASK = 0xFFFF


def crc16(veri: bytes) -> int:
    """CRC16-CCITT degerini hesaplar.

    Args:
        veri (bytes): Ham byte dizisi.

    Returns:
        int: 16 bitlik CRC degeri.
    """
    crc = _INIT
    for byte in veri:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & _MASK
            else:
                crc = (crc << 1) & _MASK
    return crc & _MASK


def crc16_dogrula(veri: bytes, beklenen: int) -> bool:
    """Hesaplanan CRC beklenen degerle eslesir mi?

    Args:
        veri (bytes): Ham byte dizisi.
        beklenen (int): Beklenen 16-bit CRC.

    Returns:
        bool: Eslesme durumu.
    """
    return crc16(veri) == (beklenen & _MASK)
