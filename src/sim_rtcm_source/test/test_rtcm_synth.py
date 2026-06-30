"""test_rtcm_synth.py — Sentetik RTCM3 ureticisi birim testleri.

Capraz dogrulama: uretilen cerceveler bagimsiz crc24q
(swarm_control.px4_interface.rtcm_packing) ile kontrol edilir. Iki
ayri CRC24Q uygulamasi (pyrtcm + bizimki) ayni sonucu uretirse
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
from swarm_control.px4_interface.rtcm_packing import (
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
    # Hardcoded '/tmp' yerine tasinabilir tempfile (Bandit B108).
    yok_dosya = os.path.join(
        tempfile.gettempdir(), 'yok_olmayan_dosya_123456.rtcm'
    )
    with pytest.raises(FileNotFoundError):
        replay_byte_akisi(yok_dosya)


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


# =====================================================================
# pyrtcm round-trip decode testleri (SADECE 1005)
# ---------------------------------------------------------------------
# 1077 sentetik mesajimiz BILINEN sinirla pipeline-stub'dir: MSM7 govdesi
# (DF394, DF395 vb.) doldurulmadigi icin pyrtcm/gercek receiver onu MSM7
# olarak cozemez. Bu sebeple round-trip test yalniz 1005 cerceveleri icin
# yapilir. Gercek 1077 testi icin replay mode + sample_data/ kullan.
# =====================================================================

def test_pyrtcm_1005_referans_round_trip_decode():
    """1005 referans cercevesi pyrtcm ile hatasiz parse edilmelidir.

    Identity 1005 donmelidir (gercek RTCM3 parser ile capraz dogrulama).
    """
    import io
    pyrtcm = pytest.importorskip('pyrtcm')
    RTCMReader = pyrtcm.RTCMReader

    raw = produce_1005_referans()
    mesajlar = []
    for (_rawmsg, parsed) in RTCMReader(io.BytesIO(raw)):
        if parsed is not None:
            mesajlar.append(parsed)
    assert len(mesajlar) == 1, (
        f'pyrtcm tam 1 mesaj parse etmeli, edildi: {len(mesajlar)}'
    )
    assert mesajlar[0].identity == '1005'


def test_pyrtcm_1005_sentetik_round_trip_decode():
    """Sentetik 1005 cercevesi pyrtcm ile hatasiz parse edilmelidir.

    Identity 1005 donmelidir.
    """
    import io
    pyrtcm = pytest.importorskip('pyrtcm')
    RTCMReader = pyrtcm.RTCMReader

    raw = produce_1005_sentetik()
    mesajlar = []
    for (_rawmsg, parsed) in RTCMReader(io.BytesIO(raw)):
        if parsed is not None:
            mesajlar.append(parsed)
    assert len(mesajlar) == 1, (
        f'pyrtcm tam 1 mesaj parse etmeli, edildi: {len(mesajlar)}'
    )
    assert mesajlar[0].identity == '1005'


# =====================================================================
# NEGATIF TEST — bozuk CRC reddediliyor
# ---------------------------------------------------------------------
# Pozitif testler "kodumuz gecerli veriyi kabul ediyor" der, ama bu yeterli
# degil. Sahada bozulmus veri gelir (radyo paraziti, yarim cerceve vb.).
# Negatif test bozuk veriyi kodun REDDETTIGINI kanitlar.
# =====================================================================

def test_bozuk_payload_byte_iter_rtcm_messages_reddetmeli():
    """Bozuk PAYLOAD byte'i CRC eslesmesini bozar, framer reddetmelidir.

    iter_rtcm_messages bu cerceveyi YAYINLAMAMALI.
    Senaryo: gecerli RTKLib referans 1005 cercevesi alinir, payload
    icindeki bir byte degistirilir (CRC gecersizlesir). Framer'in bunu
    sessizce dusurdugu (mesajlar listesinde olmadigi) dogrulanir.
    """
    # Once temiz cerceve kabul edildigini dogrula (sanity check)
    temiz = produce_1005_referans()
    mesajlar_temiz, _ = iter_rtcm_messages(temiz)
    assert len(mesajlar_temiz) == 1
    assert mesajlar_temiz[0] == temiz

    # Payload icindeki bir byte'i boz (4. byte = ilk payload byte'i,
    # XOR 0xFF ile flip). CRC gecersizlesir.
    bozuk = bytearray(temiz)
    bozuk[3] = bozuk[3] ^ 0xFF
    bozuk_bytes = bytes(bozuk)

    # Bozuk cerceve framer tarafindan REDDEDILMELI
    mesajlar, _ = iter_rtcm_messages(bozuk_bytes)
    assert mesajlar == [], (
        f'Bozuk CRC reddedilmeliydi, yayilmis: {len(mesajlar)} mesaj'
    )


def test_bozuk_crc_byte_iter_rtcm_messages_reddetmeli():
    """Bozuk CRC24Q byte'i framer tarafindan reddedilmelidir.

    Framer bu cerceveyi YAYINLAMAMALI.
    Senaryo: cerceve sonundaki 3 byte'lik CRC24Q'nun ortasinda 1 byte
    flip edilir (payload bozulmaz, sadece CRC). Framer artik dogru
    payload'in CRC'sini hesaplar, gelen CRC ile eslesmez -> drop.
    """
    temiz = produce_1005_referans()
    bozuk = bytearray(temiz)
    # Cerceve sonundaki 3 byte CRC24Q; ortadaki byte'i flip et
    bozuk[-2] = bozuk[-2] ^ 0xFF
    bozuk_bytes = bytes(bozuk)

    mesajlar, _ = iter_rtcm_messages(bozuk_bytes)
    assert mesajlar == [], (
        f'Bozuk CRC24Q reddedilmeliydi, yayilmis: {len(mesajlar)} mesaj'
    )
