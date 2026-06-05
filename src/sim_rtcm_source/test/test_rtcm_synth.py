"""test_rtcm_synth.py — Sentetik RTCM3 ureticisi birim testleri.

Capraz dogrulama: uretilen cerceveler Faz 1'deki bagimsiz crc24q
(swarm_control.rtk_bridge.rtcm_packing) ile kontrol edilir. Iki
ayri CRC24Q uygulamasi (pyrtcm + bizim Faz 1) ayni sonucu uretirse
algoritma dogruluyor demektir.
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
from swarm_control.rtk_bridge.rtcm_packing import (
    crc24q,
    iter_rtcm_messages,
)


_RTCM3_PREAMBLE = 0xD3


def _crc_dogrula(cerceve: bytes) -> bool:
    """Faz 1 crc24q ile cerceveyi capraz dogrula."""
    govde = cerceve[:-3]
    crc_alindi = (
        (cerceve[-3] << 16)
        | (cerceve[-2] << 8)
        | cerceve[-1]
    )
    return crc24q(govde) == crc_alindi


def test_referans_1005_crc_gecerli():
    """Faz 1 referans 1005 cercevesi Faz 1 crc24q ile gecerli olmali."""
    cerceve = produce_1005_referans()
    assert len(cerceve) == 25
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1005_crc_gecerli():
    """Sentetik 1005 cercevesi Faz 1 crc24q ile gecerli olmali."""
    cerceve = produce_1005_sentetik()
    assert len(cerceve) == 25       # 3B header + 19B payload + 3B CRC
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1005_mesaj_no_dogru():
    """Sentetik 1005 payload'unda mesaj no 1005 olmali (ilk 12 bit)."""
    cerceve = produce_1005_sentetik()
    # Payload byte 3-22 (header sonrasi 19 byte)
    payload = cerceve[3:22]
    # Ilk 12 bit: byte 0 hepsi + byte 1 ust 4 bit
    mesaj_no = (payload[0] << 4) | (payload[1] >> 4)
    assert mesaj_no == 1005


def test_sentetik_1077_crc_gecerli():
    """Sentetik 1077 cercevesi Faz 1 crc24q ile gecerli olmali."""
    cerceve = produce_1077_sentetik()
    assert cerceve[0] == _RTCM3_PREAMBLE
    assert _crc_dogrula(cerceve)


def test_sentetik_1077_mesaj_no_dogru():
    """Sentetik 1077 payload mesaj no 1077 olmali."""
    cerceve = produce_1077_sentetik()
    payload = cerceve[3:-3]
    mesaj_no = (payload[0] << 4) | (payload[1] >> 4)
    assert mesaj_no == 1077


def test_synthetic_burst_iki_cerceve_doner():
    """produce_synthetic_burst 1005 + 1077 (2 cerceve) doner."""
    cerceveler = produce_synthetic_burst()
    assert len(cerceveler) == 2
    for c in cerceveler:
        assert _crc_dogrula(c)


def test_sentetik_cerceveler_framer_ile_parse_edilir():
    """Sentetik cerceveler Faz 1 iter_rtcm_messages tarafindan kabul."""
    cerceveler = produce_synthetic_burst()
    akis = b''.join(cerceveler)
    mesajlar, remainder = iter_rtcm_messages(akis)
    assert len(mesajlar) == 2
    assert remainder == b''


def test_cerceve_uret_bos_payload_value_error():
    """Bos payload ValueError firlatmali."""
    with pytest.raises(ValueError):
        cerceve_uret(b'')


def test_cerceve_uret_uzun_payload_value_error():
    """1023'ten uzun payload ValueError firlatmali."""
    with pytest.raises(ValueError):
        cerceve_uret(b'\x00' * 1024)


def test_cerceve_uret_round_trip():
    """Verilen payload + CRC tam cerceve olusturmali, parse edilmeli."""
    payload = b'\x12\x34\x56\x78'
    cerceve = cerceve_uret(payload)
    assert len(cerceve) == 3 + len(payload) + 3
    mesajlar, _ = iter_rtcm_messages(cerceve)
    assert len(mesajlar) == 1
    assert mesajlar[0] == cerceve


def test_replay_byte_akisi_dosya_okur():
    """replay_byte_akisi dosyayi okuyup baytlari donmeli."""
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
    """Yok dosya FileNotFoundError firlatmali."""
    with pytest.raises(FileNotFoundError):
        replay_byte_akisi('/tmp/yok_olmayan_dosya_123456.rtcm')


def test_sample_data_dosyasi_var_ve_gecerli():
    """Paket icindeki sample_1005.rtcm okunup parse edilebilmeli."""
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
