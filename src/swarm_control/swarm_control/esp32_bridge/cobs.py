"""COBS (Consistent Overhead Byte Stuffing) kodlama/cozme.

ESP32 UART paketleri COBS ile kodlanip 0x00 ayirici
ile cercevelenir. Bu modul o cerceveleri cozer/kodlar.
"""


def cobs_decode(giris: bytes) -> bytes:
    """COBS kodlu veriyi cozer (sondaki 0x00 haric).

    Args:
        giris (bytes): COBS kodlu veri.

    Returns:
        bytes: Cozulmus veri. Bozuk girdide bos doner.
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
            return b''

        for _ in range(1, kod):
            if oku_idx >= uzunluk:
                return b''
            cikis.append(giris[oku_idx])
            oku_idx += 1

        if kod < 0xFF and oku_idx < uzunluk:
            cikis.append(0x00)

    return bytes(cikis)


def cobs_encode(giris: bytes) -> bytes:
    """Ham veriyi COBS ile kodlar (sonda 0x00 dahil).

    Args:
        giris (bytes): Kodlanacak ham veri.

    Returns:
        bytes: COBS kodlu veri + 0x00 ayirici.
    """
    cikis = bytearray()
    kod_idx = 0
    cikis.append(0)
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
    cikis.append(0x00)
    return bytes(cikis)
