"""crc.py — RTCM/YKİ köprüsü için CRC fonksiyonları.

İki ayrı CRC:
  1. CRC-24Q  — RTCM3 çerçevesinin kendi bütünlük kontrolü (0xD3 mesajının
     son 3 baytı). Base'den okunan mesajı doğrulamak için.
  2. CRC16 CCITT-FALSE — YKİ→Base ESP UART çerçevesinin bütünlük damgası.
     Büşra REV B: poly 0x1021, init 0xFFFF, refin/refout YOK, xorout YOK.
     Big-endian eklenir. Şeyda'nın esp32_bridge/crc16.py'siyle AYNI algoritma.

Test vektörü (Büşra): crc16_ccitt_false(b"123456789") == 0x29B1
"""


def crc16_ccitt_false(data: bytes) -> int:
    """CRC16/CCITT-FALSE — poly 0x1021, init 0xFFFF, yansıtma/xorout yok."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def crc24q(data: bytes) -> int:
    """CRC-24Q (Qualcomm) — RTCM3 CRC'si. poly 0x1864CFB, init 0."""
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


# Modül doğrudan çalıştırılırsa Büşra'nın test vektörünü doğrula.
if __name__ == "__main__":
    assert crc16_ccitt_false(b"123456789") == 0x29B1, "CRC16 CCITT-FALSE HATALI"
    print("✅ crc16_ccitt_false(b'123456789') == 0x%04X (0x29B1 beklenen)"
          % crc16_ccitt_false(b"123456789"))
