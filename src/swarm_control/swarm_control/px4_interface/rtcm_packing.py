"""rtcm_packing.py — RTCM3 framer + GpsInjectData fragmenter (saf Python).

ROS / px4_msgs / serial gibi dış bağımlılık YOK. Bu sayede modül birim
testlerde ROS ortamı kurulmadan çalıştırılabilir; rtk_bridge_node bu
modülü kullanarak gelen bayt akışını PX4'e enjekte edilebilir
fragmanlara dönüştürür.

RTCM3 çerçeve formatı (https://www.use-snip.com/kb/knowledge-base/...):
    +----------+---------------+-------------+--------------+
    | Preamble | Reserved+Len  | Payload (N) | CRC24Q (3 B) |
    | 0xD3 (1B)| 6 bit + 10 bit| N bayt      |              |
    +----------+---------------+-------------+--------------+
    Toplam çerçeve uzunluğu = 6 + N bayt.

CRC24Q parametreleri (RTCM/Qualcomm):
    Polinom    : 0x1864CFB
    Başlangıç  : 0x000000
    Yansıtma   : yok
    Son XOR    : yok
    Kapsam     : preamble + reserved+len + payload (CRC hariç)
"""


_RTCM3_PREAMBLE = 0xD3
_RTCM3_HEADER_LEN = 3      # preamble(1) + reserved+length(2)
_RTCM3_CRC_LEN = 3         # CRC24Q
_RTCM3_MIN_FRAME = _RTCM3_HEADER_LEN + _RTCM3_CRC_LEN  # 6 byte (boş payload)

_CRC24Q_POLY = 0x1864CFB
_CRC24Q_INIT = 0x000000
_CRC24Q_MASK = 0xFFFFFF

# RTCM3 uzunluk alanı 10 bit -> teorik en büyük payload 1023 bayt.
_RTCM3_MAX_PAYLOAD = 1023


def crc24q(veri: bytes) -> int:
    """RTCM3 CRC24Q değerini hesaplar.

    Args:
        veri (bytes): CRC hesaplanacak bayt dizisi.

    Returns:
        int: 24-bit CRC değeri (0..0xFFFFFF).
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
    """Byte akışından tam ve CRC-doğrulanmış RTCM3 mesajlarını ayıklar.

    Streaming kullanım için tasarlandı: tüketilmemiş yarım kuyruğu
    `remainder` olarak döndürür; çağıran sonraki gelen veriyi bunun
    önüne ekleyerek tekrar çağırır. Hatalı CRC veya rastgele gürültü
    durumunda preamble false-positive olabileceği için 1 bayt ileri
    kayarak aramaya devam edilir.

    Args:
        akis (bytes): Çözümlenecek bayt akışı (eski kuyruk + yeni veri).
        max_makul_payload (int): Bu değerden büyük uzunluk iddia eden
            preamble, CRC hesaplanmadan sahte kabul edilir (fail-fast).
            Varsayılan RTCM3 teorik tavanı (1023) = filtre kapalı; çağıran
            kendi alanına uygun daha küçük bir sınır geçebilir.

    Returns:
        tuple[list[bytes], bytes]: (mesajlar, remainder).
            mesajlar: Tam ve CRC-geçerli RTCM3 çerçeveleri (preamble
                ..CRC dahil ham bayt).
            remainder: Sonraki çağrıya birleştirilecek yarım kuyruk.
    """
    mesajlar = []
    i = 0
    n = len(akis)
    while i < n:
        if akis[i] != _RTCM3_PREAMBLE:
            i += 1
            continue
        # Preamble bulundu; header için en az 3 bayt gerek
        if i + _RTCM3_HEADER_LEN > n:
            break
        # Uzunluk: header[1] alt 2 biti + header[2] (10 bit toplam)
        uzunluk = ((akis[i + 1] & 0x03) << 8) | akis[i + 2]
        # FAIL-FAST: makul üst sınırı aşan uzunluk sahte preamble'dır.
        # CRC (pahalı) hesaplamadan reddet, 1 bayt ilerle. Bu olmadan
        # 0xD3/0xFF-dolu gürültü her pozisyonda boşa CRC tetikler ve
        # callback'i ~ms'lere uzatır (algorithmic-complexity / DoS).
        if uzunluk > max_makul_payload:
            i += 1
            continue
        cerceve_boy = _RTCM3_HEADER_LEN + uzunluk + _RTCM3_CRC_LEN
        if i + cerceve_boy > n:
            # Tam çerçeve gelmedi; remainder'a kalsın
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
            # False-positive preamble; bir bayt ileri kay
            i += 1
    remainder = bytes(akis[i:])
    return mesajlar, remainder


def fragment_for_inject(rtcm_msg: bytes, max_payload: int = 300):
    """RTCM3 mesajını GpsInjectData fragmanlarına böler.

    PX4 `GpsInjectData.data` 300 bayt sabit dizidir; bu sınırı aşan
    mesajlar fragmentlere bölünür ve her fragmanın `flags` baytında
    LSB=1 işaretlenir (fragmented). Çağıran üretilen `chunk`'ı
    `data[0:len(chunk)]` alanına kopyalar, `len` alanını chunk
    uzunluğuna atar, `flags`'ı `fragmented_bool`'a göre kurar.

    Args:
        rtcm_msg (bytes): Tam RTCM3 mesajı (preamble..CRC dahil).
        max_payload (int): Tek fragmanın maks yükü. Default 300.

    Returns:
        list[tuple[bytes, bool]]: (chunk, fragmented_bool) listesi.
            chunk: Gönderilecek yük (≤ max_payload bayt).
            fragmented_bool: Bu mesaj parçalandıysa True.

    Raises:
        ValueError: max_payload pozitif değilse.
    """
    if max_payload <= 0:
        raise ValueError('max_payload pozitif olmalı')
    if not rtcm_msg:
        return []
    toplam = len(rtcm_msg)
    fragmented = toplam > max_payload
    parcalar = []
    pos = 0
    while pos < toplam:
        son = min(pos + max_payload, toplam)
        parcalar.append((bytes(rtcm_msg[pos:son]), fragmented))
        pos = son
    return parcalar
