"""crc16.py — CRC16-CCITT (XModem) hesaplama.

ESP32 firmware'indeki crc16() fonksiyonunun birebir Python karşılığı.
UART paketlerinin bütünlük doğrulaması için kullanılır.

Parametreler (firmware ile AYNI olmalı):
    Polinom    : 0x1021
    Başlangıç  : 0xFFFF
    Yansıtma   : yok (reflect in/out = false)
    Son XOR    : yok
"""

_POLY = 0x1021
_INIT = 0xFFFF
_MASK = 0xFFFF


def crc16(veri: bytes) -> int:
    """Verilen byte dizisinin CRC16-CCITT değerini hesaplar.

    Args:
        veri (bytes): CRC'si hesaplanacak ham byte dizisi.

    Returns:
        int: 16 bitlik CRC değeri (0-65535).
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
    """Hesaplanan CRC'nin beklenen değerle eşleşip eşleşmediğini döner.

    Args:
        veri (bytes): CRC'si hesaplanacak ham byte dizisi.
        beklenen (int): Karşılaştırılacak 16 bitlik CRC değeri.

    Returns:
        bool: Eşleşiyorsa True, aksi halde False.
    """
    return crc16(veri) == (beklenen & _MASK)
