"""cobs.py — Consistent Overhead Byte Stuffing (COBS) çöz/kodla.

ESP32 firmware UART paketlerini COBS ile kodlayıp 0x00 ayracı ile
çerçeveler. Bu modül o çerçeveleri çözer (decode) ve gerektiğinde
RPi -> ESP32 yönü için kodlar (encode).

Çerçeve formatı (firmware ile AYNI):
    [COBS kodlu veri ...][0x00]
0x00 baytı yalnızca çerçeve sonunda bulunur; COBS kodlu veri içinde
hiç 0x00 yoktur.
"""


def cobs_decode(giris: bytes) -> bytes:
    """COBS kodlu bir baytı (0x00 ayracı HARİÇ) çözer.

    Firmware'deki cobs_decode() ile aynı mantık. Girdi, çerçeve sonundaki
    0x00 ayracı atıldıktan sonraki ham COBS verisidir.

    Args:
        giris (bytes): COBS kodlu veri (sondaki 0x00 dahil DEĞİL).

    Returns:
        bytes: Çözülmüş orijinal veri. Bozuk girdide boş bytes döner.
    """
    if not giris:
        return b''

    cikis = bytearray()
    oku_idx = 0
    uzunluk = len(giris)

    while oku_idx < uzunluk:
        kod = giris[oku_idx]
        oku_idx += 1
        if kod == 0:
            return b''  # geçersiz: kodlu veride 0x00 olamaz

        for _ in range(1, kod):
            if oku_idx >= uzunluk:
                return b''  # eksik veri
            cikis.append(giris[oku_idx])
            oku_idx += 1

        if kod < 0xFF and oku_idx < uzunluk:
            cikis.append(0x00)

    return bytes(cikis)


def cobs_encode(giris: bytes) -> bytes:
    """Ham baytları COBS ile kodlar (sondaki 0x00 ayracı dahil).

    RPi -> ESP32 yönünde paket gönderirken kullanılır.

    Args:
        giris (bytes): Kodlanacak ham veri.

    Returns:
        bytes: COBS kodlu veri + sonda 0x00 ayracı.
    """
    cikis = bytearray()
    kod_idx = 0
    cikis.append(0)  # ilk kod baytı için yer tut
    kod = 1

    for byte in giris:
        if byte != 0x00:
            cikis.append(byte)
            kod += 1
            if kod == 0xFF:
                cikis[kod_idx] = kod
                kod_idx = len(cikis)
                cikis.append(0)
                kod = 1
        else:
            cikis[kod_idx] = kod
            kod_idx = len(cikis)
            cikis.append(0)
            kod = 1

    cikis[kod_idx] = kod
    cikis.append(0x00)  # çerçeve sonu ayracı
    return bytes(cikis)
