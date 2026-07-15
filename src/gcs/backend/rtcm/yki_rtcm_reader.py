#!/usr/bin/env python3
"""yki_rtcm_reader.py — Here4 Base'ten RTCM oku → çerçevele → Base ESP'ye yaz.

Zincir: Here4 Base (F9P) → BU KOD (PC) → Base ESP → mesh → drone → Pixhawk.
Bizim katman SADECE: tam RTCM3 mesajını ayıkla + CRC-24Q doğrula +
cobs_framing ile çerçevele + ESP'ye yaz. Parçalama/mesh/retry YOK (ESP'nin işi).

Kurulum notu: her sahada önce Mission Planner ile Base ayarlanıp KAPATILIR
(aynı COM portu iki program açamaz), sonra bu kod devralır.

Kullanım:
    # Sadece oku + logla (ESP yok, test adımı 3):
    python3 yki_rtcm_reader.py --gps-port /dev/ttyACM0
    # ESP'ye de yaz (test adımı 4+):
    python3 yki_rtcm_reader.py --gps-port /dev/ttyACM0 --esp-port /dev/ttyUSB0
"""

import argparse
import time

import serial

try:
    from .crc import crc24q
    from .cobs_framing import frame_rtcm
except ImportError:  # doğrudan script olarak çalıştırılınca
    from crc import crc24q
    from cobs_framing import frame_rtcm

# RTCM mesaj tipleri
EXPECTED = {1005, 1074, 1084, 1094, 1230}          # MSM4 seti (beklenen)
MSM7 = {1077, 1087, 1097, 1127}                    # ağır tip — MSM4'e alınmalı


def rtcm_frames(ser, stats):
    """GPS akışından CRC-24Q doğrulanmış tam RTCM3 mesajları üretir.

    RTCM3 çerçevesi: 0xD3 + 2 byte(6 rezerv + 10 uzunluk) + payload + 3 byte CRC24.
    Bozuk CRC'de mesaj atılır, senkrona dönülür (stats['crc_errors']++).
    """
    while True:
        b = ser.read(1)
        if not b:
            continue                               # timeout — RTCM 1Hz, boşluk normal
        if b != b"\xD3":
            continue                               # 0xD3 senkronu ara
        hdr = ser.read(2)
        if len(hdr) < 2:
            continue
        length = ((hdr[0] & 0x03) << 8) | hdr[1]   # 10-bit payload uzunluğu
        rest = ser.read(length + 3)                # payload + 3 byte CRC24
        if len(rest) < length + 3:
            continue
        frame = b"\xD3" + hdr + rest
        # CRC-24Q: son 3 byte hariç tüm çerçeve üzerinden, big-endian karşılaştır
        if crc24q(frame[:-3]) == int.from_bytes(frame[-3:], "big"):
            yield frame
        else:
            stats["crc_errors"] += 1               # bozuk → at, senkrona dön


def msg_type(frame):
    """RTCM mesaj numarası — payload'ın ilk 12 biti."""
    return (frame[3] << 4) | (frame[4] >> 4)


def main():
    ap = argparse.ArgumentParser(
        description="YKİ RTCM okuyucu (Here4 Base → Base ESP)"
    )
    ap.add_argument("--gps-port", required=True, help="Here4 Base COM/seri portu")
    ap.add_argument("--gps-baud", type=int, default=115200)
    ap.add_argument("--esp-port", default=None,
                    help="Base ESP portu. VERİLMEZSE sadece oku+logla (test modu).")
    ap.add_argument("--esp-baud", type=int, default=460800)
    args = ap.parse_args()

    gps = serial.Serial(args.gps_port, args.gps_baud, timeout=1.0)
    esp = serial.Serial(args.esp_port, args.esp_baud) if args.esp_port else None
    mode = f"→ ESP {args.esp_port}@{args.esp_baud}" if esp else "SADECE oku+logla (ESP yok)"
    print(f"[YKİ-RTCM] başladı · GPS {args.gps_port}@{args.gps_baud} · {mode}")

    stats = {"crc_errors": 0}
    win_start = time.monotonic()
    win_msgs = 0
    win_bytes = 0
    types_seen = {}

    for frame in rtcm_frames(gps, stats):
        t = msg_type(frame)
        types_seen[t] = types_seen.get(t, 0) + 1
        win_msgs += 1
        win_bytes += len(frame)

        if t in MSM7:
            print(f"⚠ UYARI: MSM7 tipi {t} — Base MSM4'e alınmalı (Mission Planner). "
                  f"ESP bunu reddedebilir.")

        if esp:
            esp.write(frame_rtcm(frame))           # tam mesaj → çerçevele → yaz

        now = time.monotonic()
        if now - win_start >= 1.0:                 # saniyede bir özet
            tipler = ", ".join(f"{k}:{v}" for k, v in sorted(types_seen.items()))
            uyari = "" if EXPECTED.issuperset(types_seen) or not types_seen else " ⚠beklenmeyen tip"
            print(f"[{win_msgs} msg/s · {win_bytes}B · crc_err={stats['crc_errors']}] "
                  f"tipler: {tipler}{uyari}")
            win_start, win_msgs, win_bytes, types_seen = now, 0, 0, {}


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[YKİ-RTCM] durduruldu.")
