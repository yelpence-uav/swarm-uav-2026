"""Sentetik RTCM3 ureticisi birim testleri.

Iki bagimsiz CRC24Q implementasyonu ile capraz dogrulama yapar.
"""

import os
import tempfile

import pytest

from sim_rtcm_source.rtcm_synth import (
    cerceve_uret,
    produce_1005_referans,
    produce_1005_sentetik,
    produce_1077_sentetik,
    produce_synthetic_burst,
    replay_byte_akisi,
)
from swarm_control.px4_interface.rtcm_packing import (
    crc24q,
    iter_rtcm_messages,
)


_RTCM3_PREAMBLE = 0xD3


def _crc_dogrula(cerceve: bytes) -> bool:
    """Capraz CRC24Q dogrulamasi yapar."""
    govde = cerceve[:-3]
    crc_alindi = (
        (cerceve[-3] << 16)
        | (cerceve[-2] << 8)
        | cerceve[-1]
    )
    return crc24q(govde) == crc_alindi


def test_referans_1005_crc_gecerli():
    """Referans 1005 cercevesi CRC gecerli olmali."""
    cerceve = produce_1005_referans()
    assert len(cerceve) == 25
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1005_crc_gecerli():
    """Sentetik 1005 CRC gecerli olmali."""
    cerceve = produce_1005_sentetik()
    assert len(cerceve) == 25
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1005_mesaj_no_dogru():
    """1005 payload ilk 12 bitte mesaj no 1005 tasiyor."""
    cerceve = produce_1005_sentetik()
    payload = cerceve[3:22]
    mesaj_no = (payload[0] << 4) | (payload[1] >> 4)
    assert mesaj_no == 1005


def test_sentetik_1077_crc_gecerli():
    """Sentetik 1077 CRC gecerli olmali."""
    cerceve = produce_1077_sentetik()
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1077_mesaj_no_dogru():
    """1077 payload mesaj no 1077 tasiyor."""
    cerceve = produce_1077_sentetik()
    payload = cerceve[3:-3]
    mesaj_no = (payload[0] << 4) | (payload[1] >> 4)
    assert mesaj_no == 1077


def test_synthetic_burst_iki_cerceve_doner():
    """Burst 2 gecerli cerceve dondurur."""
    cerceveler = produce_synthetic_burst()
    assert len(cerceveler) == 2
    for c in cerceveler:
        assert _crc_dogrula(c)


def test_sentetik_cerceveler_framer_ile_parse_edilir():
    """Sentetik cerceveler iter_rtcm_messages ile parse olur."""
    cerceveler = produce_synthetic_burst()
    akis = b''.join(cerceveler)
    mesajlar, remainder = iter_rtcm_messages(akis)
    assert len(mesajlar) == 2
    assert remainder == b''


def test_cerceve_uret_bos_payload_value_error():
    """Bos payload ValueError firlatir."""
    with pytest.raises(ValueError):
        cerceve_uret(b'')


def test_cerceve_uret_uzun_payload_value_error():
    """1023'ten uzun payload ValueError firlatir."""
    with pytest.raises(ValueError):
        cerceve_uret(b'\x00' * 1024)


def test_cerceve_uret_round_trip():
    """Uretilen cerceve framer ile parse edilebilmeli."""
    payload = b'\x12\x34\x56\x78'
    cerceve = cerceve_uret(payload)
    assert len(cerceve) == 3 + len(payload) + 3
    mesajlar, _ = iter_rtcm_messages(cerceve)
    assert len(mesajlar) == 1
    assert mesajlar[0] == cerceve


def test_replay_byte_akisi_dosya_okur():
    """Replay fonksiyonu dosyayi dogru okur."""
    icerik = b'\x01\x02\x03\x04'
    with tempfile.NamedTemporaryFile(
        suffix='.rtcm', delete=False
    ) as f:
        f.write(icerik)
        gecici = f.name
    try:
        sonuc = replay_byte_akisi(gecici)
        assert sonuc == icerik
    finally:
        os.unlink(gecici)


def test_replay_byte_akisi_bulunamayan_dosya():
    """Olmayan dosya FileNotFoundError firlatir."""
    yok_dosya = os.path.join(
        tempfile.gettempdir(),
        'yok_olmayan_dosya_123456.rtcm',
    )
    with pytest.raises(FileNotFoundError):
        replay_byte_akisi(yok_dosya)


def test_sample_data_dosyasi_var_ve_gecerli():
    """sample_1005.rtcm okunup parse edilebilmeli."""
    yol = os.path.join(
        os.path.dirname(__file__), '..',
        'sample_data', 'sample_1005.rtcm',
    )
    assert os.path.isfile(yol)
    icerik = replay_byte_akisi(yol)
    assert len(icerik) > 0
    mesajlar, remainder = iter_rtcm_messages(icerik)
    assert len(mesajlar) >= 1
    for m in mesajlar:
        assert _crc_dogrula(m)


# pyrtcm round-trip (sadece 1005, 1077 stub bos)

def test_pyrtcm_1005_referans_round_trip_decode():
    """Referans 1005 pyrtcm ile identity 1005 donmeli."""
    import io
    pyrtcm = pytest.importorskip('pyrtcm')
    RTCMReader = pyrtcm.RTCMReader

    raw = produce_1005_referans()
    mesajlar = []
    for (_rawmsg, parsed) in RTCMReader(
        io.BytesIO(raw)
    ):
        if parsed is not None:
            mesajlar.append(parsed)
    assert len(mesajlar) == 1
    assert mesajlar[0].identity == '1005'


def test_pyrtcm_1005_sentetik_round_trip_decode():
    """Sentetik 1005 pyrtcm ile identity 1005 donmeli."""
    import io
    pyrtcm = pytest.importorskip('pyrtcm')
    RTCMReader = pyrtcm.RTCMReader

    raw = produce_1005_sentetik()
    mesajlar = []
    for (_rawmsg, parsed) in RTCMReader(
        io.BytesIO(raw)
    ):
        if parsed is not None:
            mesajlar.append(parsed)
    assert len(mesajlar) == 1
    assert mesajlar[0].identity == '1005'


# Negatif testler: bozuk veri reddedilmeli

def test_bozuk_payload_byte_reddedilmeli():
    """Payload byte bozulunca CRC uyusmaz, framer reddetmeli."""
    temiz = produce_1005_referans()
    mesajlar_temiz, _ = iter_rtcm_messages(temiz)
    assert len(mesajlar_temiz) == 1

    bozuk = bytearray(temiz)
    bozuk[3] = bozuk[3] ^ 0xFF
    bozuk_bytes = bytes(bozuk)

    mesajlar, _ = iter_rtcm_messages(bozuk_bytes)
    assert mesajlar == []


def test_bozuk_crc_byte_reddedilmeli():
    """CRC byte bozulunca framer reddetmeli."""
    temiz = produce_1005_referans()
    bozuk = bytearray(temiz)
    bozuk[-2] = bozuk[-2] ^ 0xFF
    bozuk_bytes = bytes(bozuk)

    mesajlar, _ = iter_rtcm_messages(bozuk_bytes)
    assert mesajlar == []
