"""RTCM3 framer + GpsInjectData fragmenter (saf Python).

ROS bagimliligi yok; birim testlerde dogrudan calisir.
"""

_RTCM3_PREAMBLE = 0xD3
_RTCM3_HEADER_LEN = 3
_RTCM3_CRC_LEN = 3
_RTCM3_MIN_FRAME = _RTCM3_HEADER_LEN + _RTCM3_CRC_LEN

_CRC24Q_POLY = 0x1864CFB
_CRC24Q_INIT = 0x000000
_CRC24Q_MASK = 0xFFFFFF

_RTCM3_MAX_PAYLOAD = 1023


def crc24q(veri: bytes) -> int:
    """RTCM3 CRC24Q hesaplar.

    Args:
        veri (bytes): CRC hesaplanacak baytlar.

    Returns:
        int: 24-bit CRC degeri.
    """
    crc = _CRC24Q_INIT
    for byte in veri:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= _CRC24Q_POLY
        crc &= _CRC24Q_MASK
    return crc


def iter_rtcm_messages(
    akis: bytes,
    max_makul_payload: int = _RTCM3_MAX_PAYLOAD,
):
    """Byte akisindan gecerli RTCM3 mesajlarini ayiklar.

    Args:
        akis (bytes): Ham bayt akisi.
        max_makul_payload (int): Sahte preamble filtresi.

    Returns:
        tuple[list[bytes], bytes]:
            (gecerli mesajlar, kalan kuyruk).
    """
    mesajlar = []
    i = 0
    n = len(akis)
    while i < n:
        if akis[i] != _RTCM3_PREAMBLE:
            i += 1
            continue
        if i + _RTCM3_HEADER_LEN > n:
            break
        uzunluk = (
            ((akis[i + 1] & 0x03) << 8) | akis[i + 2]
        )
        # Makul siniri asan uzunluk sahte preamble
        if uzunluk > max_makul_payload:
            i += 1
            continue
        cerceve_boy = (
            _RTCM3_HEADER_LEN + uzunluk + _RTCM3_CRC_LEN
        )
        if i + cerceve_boy > n:
            break
        cerceve = bytes(akis[i:i + cerceve_boy])
        govde = cerceve[:-_RTCM3_CRC_LEN]
        crc_alindi = (
            (cerceve[-3] << 16)
            | (cerceve[-2] << 8)
            | cerceve[-1]
        )
        if crc24q(govde) == crc_alindi:
            mesajlar.append(cerceve)
            i += cerceve_boy
        else:
            i += 1
    remainder = bytes(akis[i:])
    return mesajlar, remainder


def fragment_for_inject(
    rtcm_msg: bytes, max_payload: int = 300
):
    """RTCM3 mesajini GpsInjectData parcalarina boler.

    Args:
        rtcm_msg (bytes): Tam RTCM3 mesaji.
        max_payload (int): Parca basina maks bayt.

    Returns:
        list[tuple[bytes, bool]]: (parca, parcali_mi).

    Raises:
        ValueError: max_payload pozitif degilse.
    """
    if max_payload <= 0:
        raise ValueError('max_payload pozitif olmali')
    if not rtcm_msg:
        return []
    toplam = len(rtcm_msg)
    fragmented = toplam > max_payload
    parcalar = []
    pos = 0
    while pos < toplam:
        son = min(pos + max_payload, toplam)
        parcalar.append(
            (bytes(rtcm_msg[pos:son]), fragmented)
        )
        pos = son
    return parcalar
