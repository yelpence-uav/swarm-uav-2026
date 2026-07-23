"""Sentetik RTCM3 cerceve uretici (saf Python).

Sim ortaminda pipeline testi icin minimal RTCM3 byte akisi
uretir. Gercek receiver verisi icin replay modu kullanilir.
"""

# pyrtcm varsa onu kullan, yoksa yerel CRC24Q'ya dus
try:
    from pyrtcm.rtcmhelpers import calc_crc24q
except ImportError:
    _CRC24Q_POLY = 0x1864CFB

    def calc_crc24q(govde: bytes) -> int:
        """CRC24Q hesapla (pyrtcm yoksa fallback)."""
        crc = 0
        for byte in govde:
            crc ^= byte << 16
            for _ in range(8):
                crc <<= 1
                if crc & 0x1000000:
                    crc ^= _CRC24Q_POLY
            crc &= 0xFFFFFF
        return crc


_RTCM3_PREAMBLE = 0xD3
_RTCM3_MAX_PAYLOAD = 1023


def cerceve_uret(payload: bytes) -> bytes:
    """Payload'dan tam RTCM3 cercevesi olusturur.

    Args:
        payload (bytes): Mesaj govdesi (header/CRC haric).

    Returns:
        bytes: Tam RTCM3 cercevesi.

    Raises:
        ValueError: Payload bos veya >1023 byte ise.
    """
    uzunluk = len(payload)
    if uzunluk == 0:
        raise ValueError('RTCM3 payload bos olamaz')
    if uzunluk > _RTCM3_MAX_PAYLOAD:
        raise ValueError(
            f'RTCM3 payload max {_RTCM3_MAX_PAYLOAD} byte '
            f'(verilen: {uzunluk})'
        )
    header = bytes([
        _RTCM3_PREAMBLE,
        (uzunluk >> 8) & 0x03,
        uzunluk & 0xFF,
    ])
    govde = header + payload
    crc = calc_crc24q(govde)
    crc_bytes = bytes([
        (crc >> 16) & 0xFF,
        (crc >> 8) & 0xFF,
        crc & 0xFF,
    ])
    return govde + crc_bytes


def produce_1005_referans() -> bytes:
    """u-blox/RTKLib kaynakli dogrulanmis 1005 cercevesi."""
    return bytes.fromhex(
        'D300133ED7D30202980EDEEF34B4BD62AC094198'
        '6F33360B98'
    )


def produce_1005_sentetik() -> bytes:
    """Sentetik 1005 cercevesi (sadece mesaj no set, CRC gecerli)."""
    payload = bytearray(19)
    # DF002: mesaj numarasi 1005 (ilk 12 bit)
    payload[0] = (1005 >> 4) & 0xFF
    payload[1] = (1005 << 4) & 0xF0
    return cerceve_uret(bytes(payload))


def produce_1077_sentetik() -> bytes:
    """Sentetik 1077 stub cercevesi (MSM7 govdesi bos)."""
    payload = bytearray(20)
    # DF002: mesaj numarasi 1077 (ilk 12 bit)
    payload[0] = (1077 >> 4) & 0xFF
    payload[1] = (1077 << 4) & 0xF0
    return cerceve_uret(bytes(payload))


def produce_synthetic_burst() -> list:
    """Tek periyot icin 1005 + 1077 cerceve listesi doner."""
    return [produce_1005_sentetik(), produce_1077_sentetik()]


def replay_byte_akisi(rtcm_dosyasi: str) -> bytes:
    """RTCM dosyasini okuyup ham baytlarini doner.

    Args:
        rtcm_dosyasi (str): Dosya yolu.

    Returns:
        bytes: Dosya icerigi.

    Raises:
        FileNotFoundError: Dosya bulunamazsa.
    """
    with open(rtcm_dosyasi, 'rb') as f:
        return f.read()
