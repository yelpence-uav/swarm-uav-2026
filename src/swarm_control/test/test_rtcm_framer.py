"""test_rtcm_framer.py — RTCM3 ayıklayıcı (iter_rtcm_messages) testleri.

Birim test deseni `test_esp32_cobs.py` ile aynıdır: pytest function-style,
docstring'li, edge case'leri kapsar. Saf Python (ROS importu yok).
"""

from swarm_control.rtk_bridge.rtcm_packing import (
    crc24q,
    iter_rtcm_messages,
)


def _cerceve_uret(payload: bytes) -> bytes:
    """Test için geçerli CRC24Q ile RTCM3 çerçevesi üretir."""
    uzunluk = len(payload)
    header = bytes([
        0xD3,
        (uzunluk >> 8) & 0x03,
        uzunluk & 0xFF,
    ])
    govde = header + payload
    crc = crc24q(govde)
    crc_baytlar = bytes([
        (crc >> 16) & 0xFF,
        (crc >> 8) & 0xFF,
        crc & 0xFF,
    ])
    return govde + crc_baytlar


def test_crc24q_bos_giris_sifir():
    """CRC24Q boş giriş için init değerini (0) dönmeli."""
    assert crc24q(b'') == 0


def test_crc24q_24_bit_sinirinda():
    """Sonuç her zaman 24 bit içinde kalmalı."""
    assert 0 <= crc24q(b'\xff' * 32) <= 0xFFFFFF


def test_tek_mesaj_dogru_crc():
    """Tek geçerli RTCM3 çerçevesi tam ayıklanmalı."""
    payload = b'\x01\x02\x03\x04'
    cerceve = _cerceve_uret(payload)
    mesajlar, remainder = iter_rtcm_messages(cerceve)
    assert len(mesajlar) == 1
    assert mesajlar[0] == cerceve
    assert remainder == b''


def test_yarim_mesaj_remainder_kalir():
    """Yarım gelen çerçeve tamamı remainder'a düşmeli."""
    payload = b'\xAA\xBB\xCC\xDD'
    cerceve = _cerceve_uret(payload)
    # Çerçevenin sadece ilk 5 baytı
    mesajlar, remainder = iter_rtcm_messages(cerceve[:5])
    assert mesajlar == []
    assert remainder == cerceve[:5]


def test_iki_mesaj_arka_arkaya():
    """Arka arkaya gelen 2 mesaj ayrı ayrı ayıklanmalı."""
    f1 = _cerceve_uret(b'\x10\x20')
    f2 = _cerceve_uret(b'\xAA\xBB\xCC')
    mesajlar, remainder = iter_rtcm_messages(f1 + f2)
    assert mesajlar == [f1, f2]
    assert remainder == b''


def test_bozuk_crc_reddedilir():
    """CRC bozulursa mesaj listeye girmemeli."""
    payload = b'\x05\x06\x07'
    cerceve = bytearray(_cerceve_uret(payload))
    cerceve[-1] ^= 0xFF  # CRC son baytı boz
    mesajlar, _ = iter_rtcm_messages(bytes(cerceve))
    assert mesajlar == []


def test_arada_cope_bayt_atlanir():
    """Preamble olmayan başlangıç baytları sessizce atlanmalı."""
    payload = b'\xDE\xAD'
    cerceve = _cerceve_uret(payload)
    akis = b'\x99\x88\x77' + cerceve
    mesajlar, _ = iter_rtcm_messages(akis)
    assert mesajlar == [cerceve]


def test_bos_akis_sonuc_bos():
    """Boş akış sıfır mesaj döner, remainder de boş."""
    mesajlar, remainder = iter_rtcm_messages(b'')
    assert mesajlar == []
    assert remainder == b''


def test_iki_mesaj_arada_kuyruk():
    """1 tam mesaj + yarım mesaj → 1 mesaj alınır, yarım remainder."""
    f1 = _cerceve_uret(b'\x01')
    f2 = _cerceve_uret(b'\x02\x03')
    akis = f1 + f2[:5]  # f2'nin sadece ilk 5 baytı
    mesajlar, remainder = iter_rtcm_messages(akis)
    assert mesajlar == [f1]
    assert remainder == f2[:5]


def test_round_trip_uzun_payload():
    """Uzun payload (255 bayt) round-trip korunmalı."""
    payload = bytes(range(256))[:255]  # 255 farklı bayt
    cerceve = _cerceve_uret(payload)
    mesajlar, remainder = iter_rtcm_messages(cerceve)
    assert len(mesajlar) == 1
    assert mesajlar[0] == cerceve
    assert remainder == b''


def test_sahte_preamble_atlatilir():
    """0xD3 false-positive durumda 1 bayt ileri kayıp gerçek mesaj alınmalı."""
    sahte = bytes([0xD3, 0x00, 0x02, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    f = _cerceve_uret(b'\x42')
    mesajlar, _ = iter_rtcm_messages(sahte + f)
    assert f in mesajlar


def test_crc24q_bilinen_rtcm_referans_vektoru():
    """RTCM3 1005 (Stationary RTK Reference) referansı ile CRC24Q teyidi.

    Bu vektör u-blox / RTKLib dokümantasyonunda yaygın referans olarak
    geçer. CRC24Q parametrelerinin (init=0x000000, polinom=0x1864CFB,
    refleksiyon yok) doğruluğunu kendi-içinde-tutarlı testlerden
    bağımsız olarak doğrular.
    """
    # 25 bayt = 3 byte header + 19 byte payload + 3 byte CRC
    referans = bytes.fromhex(
        'D3001'
        '33ED7D'
        '3020298'
        '0EDEEF34'
        'B4BD62AC'
        '09419'
        '86F33'
        '360B98'
    )
    assert len(referans) == 25
    govde = referans[:-3]
    crc_beklenen = (
        (referans[-3] << 16)
        | (referans[-2] << 8)
        | referans[-1]
    )
    assert crc24q(govde) == crc_beklenen
    # Parser de bu mesajı kabul etmeli
    mesajlar, remainder = iter_rtcm_messages(referans)
    assert len(mesajlar) == 1
    assert mesajlar[0] == referans
    assert remainder == b''
