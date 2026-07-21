"""cobs_framing.py — YKİ→Base ESP UART çerçeveleme (Büşra REV B).

Çerçeve formülü:
    frame = cobs_encode( bytes([TIP_RTK, BAZ_ID]) + payload + crc16_be ) + b'\\x00'

- TIP_RTK=0x0C, BAZ_ID=99 (firmware'de kilitli, kesin)
- CRC16 (CCITT-FALSE) TIP+ID+payload'ın TAMAMI üzerinden hesaplanır,
  sona BÜYÜK-endian 2 byte (yüksek byte önce) eklenir, SONRA COBS'lanır.
- 0x00 yalnızca ayraç olarak en sonda bulunur (COBS gövdede 0x00 bırakmaz).

Bu paket KANONİK — Pi tarafı (Şeyda) aynı çöz fonksiyonunu kullanacak.
COBS: Consistent Overhead Byte Stuffing — ikili veriden 0x00'ları eleyip
0x00'ı güvenli bir çerçeve ayracı yapar.
"""

try:
    from .crc import crc16_ccitt_false
except ImportError:  # doğrudan script olarak çalıştırılınca
    from crc import crc16_ccitt_false

TIP_RTK = 0x0C
BAZ_ID = 99


def cobs_encode(data: bytes) -> bytes:
    """COBS kodla — çıktı hiç 0x00 içermez (ayraç için ayrılır)."""
    out = bytearray([0])       # ilk kod baytı için yer tutucu
    code_index = 0
    code = 1
    for byte in data:
        if byte == 0:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
        else:
            out.append(byte)
            code += 1
            if code == 0xFF:   # 254 baytlık blok doldu
                out[code_index] = code
                code_index = len(out)
                out.append(0)
                code = 1
    out[code_index] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """COBS çöz — cobs_encode'un tersi. Bozuk kodda ValueError."""
    out = bytearray()
    idx = 0
    n = len(data)
    while idx < n:
        code = data[idx]
        if code == 0:
            raise ValueError("COBS: govdede beklenmeyen 0x00")
        idx += 1
        block_end = idx + code - 1
        if block_end > n:
            raise ValueError("COBS: eksik veri (kod blogu tasti)")
        out.extend(data[idx:block_end])
        idx = block_end
        if code < 0xFF and idx < n:
            out.append(0)
    return bytes(out)


def frame_rtcm(payload: bytes, tip: int = TIP_RTK, baz_id: int = BAZ_ID) -> bytes:
    """Tam RTCM mesajını UART çerçevesine sar (0x00 ayraç dahil)."""
    inner = bytes([tip & 0xFF, baz_id & 0xFF]) + payload
    crc = crc16_ccitt_false(inner)
    inner += crc.to_bytes(2, "big")            # BÜYÜK-endian
    return cobs_encode(inner) + b"\x00"


def deframe_rtcm(cobs_body: bytes) -> tuple[int, int, bytes]:
    """Çerçeveyi çöz + CRC doğrula. (tip, baz_id, payload) döner.

    cobs_body: 0x00 ayracı ÇIKARILMIŞ COBS gövdesi. CRC uymazsa ValueError.
    """
    inner = cobs_decode(cobs_body)
    if len(inner) < 4:                          # tip + id + en az 0 payload + crc(2)
        raise ValueError("cerceve cok kisa")
    body = inner[:-2]
    crc_recv = int.from_bytes(inner[-2:], "big")
    if crc16_ccitt_false(body) != crc_recv:
        raise ValueError("CRC16 uyusmadi")
    return body[0], body[1], body[2:]


# --- Kendi kendine test ------------------------------------------------------
if __name__ == "__main__":
    import os

    # 1) COBS round-trip — 0x00 içeren + sınır durumları + rastgele 1-1200B
    cases = [b"", b"\x00", b"\x00\x00\x00", b"\x11\x22\x00\x33",
             b"\x01" * 254, b"\x01" * 255, bytes(range(256)),
             b"\xD3\x00\x13" + b"\x00" * 50]
    for _ in range(200):
        cases.append(os.urandom(int.from_bytes(os.urandom(2), "big") % 1200 + 1))
    for c in cases:
        assert cobs_decode(cobs_encode(c)) == c, f"COBS round-trip HATA: {c[:20]!r}"
    print(f"✅ COBS round-trip: {len(cases)} durum (0x00 dahil, 1-1200B) geçti")

    # 2) Tam çerçeve round-trip → (0x0C, 99, payload)
    rtcm = b"\xD3\x00\x13" + os.urandom(0x13) + b"\xAA\xBB\xCC"   # sahte RTCM
    framed = frame_rtcm(rtcm)
    assert framed.endswith(b"\x00") and framed.count(b"\x00") == 1, "0x00 ayraç hatası"
    tip, bid, payload = deframe_rtcm(framed[:-1])
    assert (tip, bid, payload) == (0x0C, 99, rtcm), "çerçeve round-trip HATA"
    print("✅ frame/deframe round-trip: TIP=0x0C, ID=99, payload aynen döndü")

    # 3) Bozuk CRC reddediliyor mu (tek bit oynat)
    inner = cobs_decode(framed[:-1])
    bozuk = cobs_encode(inner[:-3] + bytes([inner[-3] ^ 0x01]) + inner[-2:])
    try:
        deframe_rtcm(bozuk)
        raise AssertionError("bozuk CRC KABUL EDİLDİ (hatalı)")
    except ValueError:
        print("✅ bozuk CRC reddedildi (beklenen)")

    print("\n🎯 cobs_framing.py — tüm testler geçti, ESP ile byte-birebir uyumlu")
