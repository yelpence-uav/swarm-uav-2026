"""rtcm_synth.py — Sentetik RTCM3 cerceve uretici (saf Python).

Sim ortaminda RTCM3 byte akisi taklit etmek icin kullanilir. ROS importu
yok; birim testlerde dogrudan koshturulabilir. CRC24Q hesaplamasi varsa
pyrtcm'in calc_crc24q yardimcisina delege edilir, yoksa yerel (ayni
algoritma) implementasyona duser; test tarafinda
px4_interface.rtcm_packing.crc24q (bagimsiz uygulama) ile capraz
dogrulanir.

UYARI: Bu modulun urettigi cerceveler RECEIVER-anlamli RTCM3 verisi
DEGILDIR. Sadece pipeline testi (preamble + uzunluk + CRC dogrulugu)
icin gecerli minimal RTCM3 cerceveleridir. Gercek bir GPS modulune
beslenirse 'kabul edilir' ama anlamli duzeltme uretmez.

Synthetic mod sinirlari:
  - 1005 (referans istasyon ARP): pyrtcm round-trip parse OK (identity
    1005 dogrulandi, test_pyrtcm_1005_*).
  - 1077 (GPS MSM7): pipeline-stub; cerceve gecerli, mesaj no 1077,
    ama MSM7 govdesi (DF394/DF395) doldurulmamis -> pyrtcm/gercek
    receiver MSM7 olarak cozemez.

Gercek 1077 verisi gerekirse: replay mode + sample_data/ (gercek baz
istasyonu kayitlari).
"""

# pyrtcm bir gelistirme/dogrulama bagimliligidir ve CI gibi ortamlarda
# kurulu olmayabilir. Yoksa kendi (dogrulanmis) CRC24Q implementasyonumuza
# duseriz; uretim her ortamda calisir, pyrtcm yalnizca capraz-dogrulama
# (round-trip parse) testleri icin gereklidir.
try:
    from pyrtcm.rtcmhelpers import calc_crc24q
except ImportError:
    _CRC24Q_POLY = 0x1864CFB

    def calc_crc24q(govde: bytes) -> int:
        """RTCM3 CRC24Q — pyrtcm yoksa yerel fallback (ayni algoritma)."""
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
_RTCM3_MAX_PAYLOAD = 1023   # 10-bit uzunluk alani


def cerceve_uret(payload: bytes) -> bytes:
    """Verilen payload icin tam RTCM3 cercevesi olusturur.

    Cerceve formati:
        preamble (1B) + reserved+length (2B) + payload (N) + CRC24Q (3B)

    Args:
        payload (bytes): RTCM3 mesaj govdesi (header ve CRC haric).

    Returns:
        bytes: Tam RTCM3 cercevesi (preamble..CRC dahil).

    Raises:
        ValueError: payload uzunlugu 0 veya > 1023 ise.
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
    """Faz 1 dogrulanmis RTCM3 1005 referans cercevesi.

    Bu cerceve u-blox/RTKLib dokumantasyonundan alinmistir ve
    test_rtcm_framer.py::test_crc24q_bilinen_rtcm_referans_vektoru
    tarafindan CRC24Q dogrulamasi ile teyit edilmistir.

    Returns:
        bytes: 25 byte 1005 RTCM3 cercevesi (sabit, CRC=0x360B98).
    """
    return bytes.fromhex(
        'D300133ED7D30202980EDEEF34B4BD62AC0941986F33360B98'
    )


def produce_1005_sentetik() -> bytes:
    """Sentetik 1005 (Stationary RTK Reference Station ARP) cercevesi.

    Payload icerigi minimal: sadece mesaj numarasi (1005) ilk 12 bitte
    isaretlenir, kalan 1005 alanlari (station_id, ITRF yili, ECEF x/y/z)
    sifirla baslar. Receiver perspektifinden anlamli koordinat yoktur;
    sadece CRC gecerli olur, framer kabul eder.

    Returns:
        bytes: 25 byte sentetik 1005 cercevesi (yeni CRC ile).
    """
    # 1005 mesaji 19 byte sabit payload
    payload = bytearray(19)
    # DF002 (12 bit) = 1005 mesaj numarasi, MSB-first
    payload[0] = (1005 >> 4) & 0xFF        # 0x3E
    payload[1] = (1005 << 4) & 0xF0        # 0xD0
    return cerceve_uret(bytes(payload))


def produce_1077_sentetik() -> bytes:
    """Sentetik 1077 (GPS MSM7) PIPELINE-STUB cerceve.

    Yalniz gecerli RTCM3 CERCEVESI uretir (preamble + uzunluk + CRC24Q).
    MSM7 govdesi (DF394 uydu maskesi, DF395 hucre maskesi, sinyal
    bilgileri vb.) DOLDURULMAZ; bu yuzden pyrtcm/gercek receiver bu
    cerceveyi MSM7 olarak COZEMEZ — sadece mesaj numarasini (1077)
    okur, MSM7 alanlarini parse etmeye calisirken hata verir.

    KASITLIDIR: px4_bridge (RTK) RTCM'i opak byte tasir; sim'de PX4 fix=6'yi
    sim_rtk_fix6.patch ile taklit eder. Bu uretici sadece pipeline
    testi icin (cerceve gecerliligi + framer kabulu) tasarlanmistir.

    Gercek 1077 verisi icin replay mode + sample_data/ icindeki gercek
    baz istasyonu kayitlari kullanilmalidir.

    Returns:
        bytes: 26 byte sentetik 1077 cercevesi (pipeline-stub).
    """
    payload = bytearray(20)
    # DF002 (12 bit) = 1077 mesaj numarasi
    payload[0] = (1077 >> 4) & 0xFF        # 0x43
    payload[1] = (1077 << 4) & 0xF0        # 0x50
    return cerceve_uret(bytes(payload))


def produce_synthetic_burst() -> list:
    """Bir sentetik periyot icin 1005 + 1077 cerceveleri donerek liste.

    sim_rtcm_source_node bu fonksiyonu publish_hz periyodunda cagirir
    ve sirayla rtcm/in topic'ine basar.

    Returns:
        list[bytes]: [1005 sentetik, 1077 sentetik] siralarinda.
    """
    return [produce_1005_sentetik(), produce_1077_sentetik()]


def replay_byte_akisi(rtcm_dosyasi: str) -> bytes:
    """Bir .rtcm dosyasinin tum baytlarini okur (replay modu icin).

    Args:
        rtcm_dosyasi (str): .rtcm dosya yolu (sample_data/ altinda).

    Returns:
        bytes: Dosyanin ham bayt icerigi.

    Raises:
        FileNotFoundError: dosya yoksa.
    """
    with open(rtcm_dosyasi, 'rb') as f:
        return f.read()
