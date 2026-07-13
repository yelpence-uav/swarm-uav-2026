#!/usr/bin/env python3
"""
ADIM 6 — Firmware smoke-test: RX BASE'e (esp_tx) REV B formatinda ornek
RTCM3 mesaji basar: COBS(TIP_RTK + BAZ_ID + rtcm + crc16_be) + 0x00.

KANONIK implementasyon common/ paketindedir (YKI sorumlusu: crc.py +
cobs_framing.py) — bu script SADECE firmware smoke testi icindir, uretim
kodu DEGILDIR ve YKI'nin gercek RTCM parser'inin yerini tutmaz.

Kullanim:
    python3 test_sender.py --port /dev/ttyUSB0 --baud 460800
"""
import argparse
import time
import serial

TIP_RTK = 0x0C
BAZ_ID = 99


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out, idx = bytearray(), 0
    while True:
        z = data.find(b"\x00", idx)
        chunk = data[idx:] if z == -1 else data[idx:z]
        out.append(len(chunk) + 1)
        out += chunk
        if z == -1:
            return bytes(out)
        idx = z + 1


def cerceve_olustur(tip: int, id_: int, payload: bytes) -> bytes:
    ham = bytes([tip, id_]) + payload
    crc = crc16_ccitt_false(ham)
    ham += bytes([(crc >> 8) & 0xFF, crc & 0xFF])  # buyuk-endian (REV B)
    return cobs_encode(ham) + b"\x00"


def ornek_rtcm3() -> bytes:
    # Synthetic RTCM3 tip 1005 iskeleti (0xD3 + uzunluk + 19B payload +
    # CRC24Q). CRC24Q gercek hesaplanmadi — esp_tx bu smoke testte zaten
    # savunma kontrolu (0xD3 + uzunluk tutarliligi) uyguluyor, gercek
    # CRC24Q dogrulamasi YKI'nin isi.
    payload = bytes(19)
    uzunluk = len(payload)
    return bytes([0xD3, (uzunluk >> 8) & 0x03, uzunluk & 0xFF]) + payload + bytes(3)


def main():
    ap = argparse.ArgumentParser(description="esp_tx (RX BASE) icin REV B COBS/CRC16 smoke-test gonderici")
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--tekrar", type=int, default=1, help="kac kez gonderilsin")
    args = ap.parse_args()

    cerceve = cerceve_olustur(TIP_RTK, BAZ_ID, ornek_rtcm3())
    with serial.Serial(args.port, args.baud, timeout=1) as ser:
        for i in range(args.tekrar):
            ser.write(cerceve)
            print(f"[{i + 1}/{args.tekrar}] {len(cerceve)} byte gonderildi")
            if args.tekrar > 1:
                time.sleep(1)


if __name__ == "__main__":
    main()
