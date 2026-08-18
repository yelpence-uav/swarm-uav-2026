#!/usr/bin/env python3
"""yki_rtcm_reader.py — Here4 Base'ten RTCM oku → çerçevele → Base ESP'ye yaz.

Zincir: Here4 Base (F9P) → BU KOD (PC) → Base ESP → mesh → drone → Pixhawk.
Bizim katman SADECE: tam RTCM3 mesajını ayıkla + CRC-24Q doğrula +
cobs_framing ile çerçevele + ESP'ye yaz. Parçalama/mesh/retry YOK (ESP'nin işi).

SAHA TEŞHİSİ (Büşra'nın sahte-port incelemesindeki 3 bulgu üzerine):
  1. Özet satırı ZAMANLAYICIYA bağlı — veri gelmese de her saniye tek satır
     çıkar. 3 sn geçerli mesaj yoksa ⚠ RTCM GELMİYOR basılır ve iki arıza
     ayrışır: ham bayt YOK (kablo/Base kapalı/Mission Planner portu tutuyor)
     vs ham bayt VAR ama çözülmüyor (baud/parazit — crc_err artar).
     Sessizlik artık başarıya benzemez; crc_err tam ihtiyaç anında görünür.
  2. Tamponlu ayrıştırıcı — payload içinde tesadüfen görülen sahte 0xD3,
     "uzunluk" alanı kadar gerçek baytı ÇÖPE ATTIRMAZ. CRC tutmazsa sahte
     senkronun BİR sonrasından yeniden taranır; akış ortasından başlangıçta
     mesaj kaybı olmaz. (Eski akış-tabanlı okuyucu: 1 sahte 0xD3 + 2 geçerli
     mesaj → 0 mesaj buluyordu.)
  3. Seri port koparsa süreç ölmez: uyarı basılır, 2 sn'de bir yeniden
     bağlanılır (GPS ve ESP ayrı ayrı). MSM7 uyarısı mesaj başına değil
     saniyelik özette (spam yok).

Kurulum notu: her sahada önce Mission Planner ile Base ayarlanıp KAPATILIR
(aynı COM portu iki program açamaz), sonra bu kod devralır.

Kullanım:
    # Sadece oku + logla (ESP yok, kabul testi adım 3):
    python3 yki_rtcm_reader.py --gps-port /dev/ttyACM0
    # ESP'ye de yaz (adım 4+):
    python3 yki_rtcm_reader.py --gps-port /dev/ttyACM0 --esp-port /dev/ttyUSB0
    # Donanımsız öz-test (Büşra'nın senaryoları dahil):
    python3 yki_rtcm_reader.py --self-test
"""

import argparse
import signal
import struct
import sys
import time

# SIGTERM/SIGINT ile temiz kapanış.
#
# Bu olmadan süreç sinyali yok sayıyordu: ana döngü `while True` idi ve
# pyserial okuması sinyalle kesilmiyordu. Sonucu yki_durdur.sh'ın (düz `kill`
# = SIGTERM) okuyucuyu durduramaması; portu bırakmadığı için bir sonraki
# başlatma "Device or resource busy" alıyordu. Sahada `kill -9` gerekti.
_dur_istendi = False


def _sinyal_yakala(signum, _frame) -> None:
    global _dur_istendi
    _dur_istendi = True
    print(f"\n[YKİ-RTCM] sinyal {signum} alındı, kapanılıyor...", flush=True)


try:
    from .crc import crc24q
    from .cobs_framing import frame_rtcm
except ImportError:  # doğrudan script olarak çalıştırılınca
    from crc import crc24q
    from cobs_framing import frame_rtcm

# Çıktı boruya/dosyaya gidince (örn. sahada `| tee rtcm.log`) Python stdout'u
# BLOK tamponlar: sağlık satırları ~dakika gecikir — "sessizlik = başarı"
# açığı arka kapıdan geri gelirdi (Büşra'nın tee ölçümü: -u'suz 5 sn'de 0
# satır). Satır tamponlamaya zorla: her '\n'ta flush, tee/log altında da
# saniyelik satırlar anında düşer.
try:
    sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass  # stdout değiştirilmişse (test harness vb.) sessizce geç

# RTCM mesaj tipleri
EXPECTED = {1005, 1074, 1084, 1094, 1230}          # MSM4 seti (beklenen)
MSM7 = {1077, 1087, 1097, 1127}                    # ağır tip — MSM4'e alınmalı

NO_DATA_WARN_SEC = 3.0     # bu kadar sn geçerli mesaj yoksa ⚠ bas
SUMMARY_PERIOD_SEC = 1.0   # sağlık satırı periyodu (veri olsun olmasın)
REOPEN_PERIOD_SEC = 2.0    # kopan seri portu yeniden deneme aralığı
_MAX_RTCM_FRAME = 3 + 1023 + 3   # başlık + 10-bit maks payload + CRC24


class RTCMStreamParser:
    """Tamponlu RTCM3 ayrıştırıcı — sahte 0xD3 senkronunda bayt KAYBETMEZ.

    Baytlar iç tamponda birikir. 0xD3 adayının CRC-24Q'su tutmazsa yalnızca
    o adayın BİR sonrasından yeniden taranır; adayın "uzunluk" alanının işaret
    ettiği baytlar atılmaz (içlerinde gerçek mesaj başlangıcı olabilir).
    Sahte-uzun senkron en fazla _MAX_RTCM_FRAME kadar bayt bekletebilir
    (gecikme), asla kayıp yaratamaz.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0     # CRC-24Q tutmayan aday sayısı
        self.bytes_in = 0       # porttan okunan toplam ham bayt

    def feed(self, data: bytes) -> list[bytes]:
        """Yeni baytları ver; tamamlanan DOĞRULANMIŞ çerçeveleri döndür."""
        if data:
            self._buf.extend(data)
            self.bytes_in += len(data)
        frames: list[bytes] = []
        buf = self._buf
        pos = 0
        while True:
            j = buf.find(b"\xD3", pos)
            if j < 0:                      # senkron adayı yok → hepsi çöp
                pos = len(buf)
                break
            if len(buf) - j < 6:           # başlık+boş payload+CRC için bile az
                pos = j                    # veri bekle
                break
            length = ((buf[j + 1] & 0x03) << 8) | buf[j + 2]
            end = j + 6 + length
            if end > len(buf):             # tam çerçeve henüz gelmedi → bekle
                pos = j
                break
            if crc24q(bytes(buf[j:end - 3])) == int.from_bytes(buf[end - 3:end], "big"):
                frames.append(bytes(buf[j:end]))
                pos = end
            else:
                self.crc_errors += 1
                pos = j + 1                # SADECE sahte 0xD3 atlanır — gerisi korunur
        del buf[:pos]                      # kesinleşen kısmı at
        return frames


def msg_type(frame: bytes) -> int:
    """RTCM mesaj numarası — payload'ın ilk 12 biti."""
    return (frame[3] << 4) | (frame[4] >> 4)


# ---------------------------------------------------------------------------
# U-BLOX RESET — YKİ arayüzündeki butonun ucu burada
# ---------------------------------------------------------------------------
#
# NEDEN BURADA: seri port TEK SAHİPLİ. Bu süreç GPS portunu açık tutuyor;
# başka bir süreç aynı porta yazamaz ("Resource busy"). O yüzden reset komutu
# ROS üzerinden BURAYA gelir ve yazmayı port sahibi yapar. Alternatifi
# (okuyucuyu durdur → resetle → yeniden başlat) sahada üç adım ve YKİ'yi
# saniyelerce kör bırakıyor.
#
# UBX-CFG-RST (sinif 0x06, id 0x04, 4 bayt):
#     navBbrMask (u2) · resetMode (u1) · reserved (u1)
#
# ⚠️ RESET RTCM AKIŞINI KESER. Alıcı yeniden açılana kadar (tipik 5-15 sn)
# baz düzeltme yayınlamaz ve UÇAKLAR RTK-FIX'İ DÜŞÜRÜR. Havadayken çağırma.
_UBX_BBR = {
    'sicak': 0x0000,   # hot  — hafızadaki her şey korunur, en hızlı toparlar
    'ilik': 0x0001,    # warm — efemeris silinir, uydu takibi baştan
    'soguk': 0xFFFF,   # cold — tüm yardımcı veri silinir, en uzun toparlama
}
_UBX_RESET_MODU = 0x01   # kontrollü yazılım reseti (donanım watchdog'u DEĞİL)


def _ubx(sinif: int, mid: int, govde: bytes = b"") -> bytes:
    """UBX çerçevesi kurar (8-bit Fletcher sağlaması).

    rtk_baz_survey.py'deki ubx() ile AYNI hesap — orası ayrı bir süreç ve
    seri portu o açıyor, ortak modüle çıkarmak import zinciri getirirdi.
    Değiştirirsen İKİSİNİ birden değiştir.
    """
    g = bytes([sinif, mid]) + struct.pack("<H", len(govde)) + govde
    a = b = 0
    for x in g:
        a = (a + x) & 0xFF
        b = (b + a) & 0xFF
    return b"\xb5\x62" + g + bytes([a, b])


def ubx_reset(kip: str = 'sicak') -> bytes:
    """UBX-CFG-RST paketi döner. kip: sicak | ilik | soguk."""
    if kip not in _UBX_BBR:
        raise ValueError(f"bilinmeyen reset kipi: {kip} (sicak|ilik|soguk)")
    govde = struct.pack("<HBB", _UBX_BBR[kip], _UBX_RESET_MODU, 0x00)
    return _ubx(0x06, 0x04, govde)


def _try_open(port: str, baud: int):
    """Seri portu açmayı dene; (Serial|None, hata_metni) döndür."""
    import serial
    try:
        return serial.Serial(port, baud, timeout=0.2), ""
    except Exception as e:  # SerialException, PermissionError, FileNotFoundError...
        return None, str(e)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="YKİ RTCM okuyucu (Here4 Base → Base ESP)"
    )
    ap.add_argument("--gps-port", help="Here4 Base COM/seri portu")
    ap.add_argument("--gps-baud", type=int, default=115200)
    ap.add_argument("--esp-port", default=None,
                    help="Base ESP portu. DOĞRUDAN seri yazım — yalnız saha "
                         "teşhisi/tek başına test için. Üretimde --ros-topic "
                         "kullanın: seri portun sahibi esp32_bridge'dir ve "
                         "aynı portu iki süreç açamaz.")
    ap.add_argument("--esp-baud", type=int, default=460800)
    ap.add_argument("--ros-topic", default=None, metavar="TOPIC",
                    help="ÜRETİM YOLU. RTCM3 mesajlarını bu ROS topic'ine "
                         "yayınlar; esp32_bridge abone olup çerçeveleyerek "
                         "baz ESP'ye yazar. Örn: /swarm/internal/rtcm")
    ap.add_argument("--ros-komut-topic", default="/swarm/internal/rtk/komut",
                    metavar="TOPIC",
                    help="u-blox reset komutlarinin dinlendigi ROS konusu "
                         "(std_msgs/String: sicak|ilik|soguk). Yalniz "
                         "--ros-topic verildiyse acilir.")
    ap.add_argument("--self-test", action="store_true",
                    help="Donanımsız öz-testleri çalıştır ve çık")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        return
    if not args.gps_port:
        ap.error("--gps-port gerekli (ya da --self-test)")

    # Not: pyserial'i _try_open() kendi içinde import ediyor; burada ayrıca
    # import etmeye gerek yok (eskiden vardı, kullanılmıyordu — flake8 F401).

    # ROS yayıncısı — tembel kurulum. rclpy yalnızca --ros-topic verilirse
    # import edilir, böylece bu script ROS kurulu olmayan bir makinede de
    # (saha teşhisi, --self-test) çalışmaya devam eder.
    ros_pub = ros_node = None
    if args.ros_topic:
        import rclpy
        from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy,
                               QoSProfile, QoSReliabilityPolicy)
        from std_msgs.msg import UInt8MultiArray
        # QoS, esp32_bridge'deki _RTCM_QOS ile BİREBİR aynı olmalı.
        # Uyumsuz QoS'ta DDS bağlantıyı hiç kurmaz ve HATA DA VERMEZ —
        # bu projede daha önce yaşandı (20 Temmuz §7.7). Varsayılana
        # güvenmek yerine açıkça yazıyoruz.
        qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.VOLATILE,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        rclpy.init()
        ros_node = rclpy.create_node("yki_rtcm_reader")
        ros_pub = ros_node.create_publisher(UInt8MultiArray, args.ros_topic, qos)
        _ROS_MSG = UInt8MultiArray

        # --- u-blox reset komut kanali (18 Agustos 2026) ------------------
        # Callback DOGRUDAN porta YAZMIYOR: bu anda port kapali olabilir
        # (USB cekilmis, yeniden acilmayi bekliyor). Komut kuyruga girer,
        # ana dongu portun acik oldugu anda isler. Boylece "butona bastim,
        # hicbir sey olmadi ve hicbir yerde yazmiyor" durumu olusmuyor.
        from std_msgs.msg import String as _RosString
        komut_qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                               durability=QoSDurabilityPolicy.VOLATILE,
                               history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        ros_node.create_subscription(
            _RosString, args.ros_komut_topic,
            lambda m: _reset_kuyrugu.append(m.data.strip().lower()),
            komut_qos)
        print(f"[YKİ-RTCM] reset komut kanali: {args.ros_komut_topic} "
              f"(sicak|ilik|soguk)")

    gps = esp = None
    gps_err = esp_err = ""
    next_gps_try = next_esp_try = 0.0

    if args.ros_topic:
        mode = f"→ ROS {args.ros_topic}"
    elif args.esp_port:
        mode = f"→ ESP {args.esp_port}@{args.esp_baud} (doğrudan seri)"
    else:
        mode = "SADECE oku+logla (çıkış yok)"
    print(f"[YKİ-RTCM] başladı · GPS {args.gps_port}@{args.gps_baud} · {mode}")

    parser = RTCMStreamParser()
    _reset_kuyrugu: list[str] = []
    start = time.monotonic()
    last_valid: float | None = None        # son GEÇERLİ RTCM zamanı
    next_summary = start + SUMMARY_PERIOD_SEC
    prev_bytes = prev_crc = 0              # pencere deltaları için
    win_msgs = 0
    win_bytes = 0
    types_seen: dict[int, int] = {}
    msm7_seen: set[int] = set()

    signal.signal(signal.SIGTERM, _sinyal_yakala)
    signal.signal(signal.SIGINT, _sinyal_yakala)

    while not _dur_istendi:
        now = time.monotonic()

        # ROS geri cagrilarini isle (abonelik olmadan da zararsiz, 0 sn bekler)
        if ros_node is not None:
            rclpy.spin_once(ros_node, timeout_sec=0.0)

        # --- bekleyen u-blox reset komutlari ------------------------------
        while _reset_kuyrugu:
            kip = _reset_kuyrugu.pop(0)
            if gps is None:
                print(f"[YKİ-RTCM] reset ({kip}) ISTENDI ama GPS portu KAPALI "
                      f"— komut DUSURULDU, port acilinca tekrar dene")
                continue
            try:
                paket = ubx_reset(kip)
            except ValueError as e:
                print(f"[YKİ-RTCM] reset komutu REDDEDILDI: {e}")
                continue
            try:
                gps.write(paket)
                gps.flush()
                print(f"[YKİ-RTCM] *** U-BLOX RESET GONDERILDI ({kip}) *** "
                      f"RTCM birkac saniye kesilecek, ucaklar RTK-FIX dusurur")
            except Exception as e:                       # noqa: BLE001
                print(f"[YKİ-RTCM] reset YAZILAMADI: {e}")

        # --- port sağlığı: kopanı 2 sn'de bir yeniden dene -----------------
        if gps is None and now >= next_gps_try:
            gps, gps_err = _try_open(args.gps_port, args.gps_baud)
            next_gps_try = now + REOPEN_PERIOD_SEC
            if gps:
                print(f"[YKİ-RTCM] GPS portu açıldı: {args.gps_port}")
        if args.esp_port and esp is None and now >= next_esp_try:
            esp, esp_err = _try_open(args.esp_port, args.esp_baud)
            next_esp_try = now + REOPEN_PERIOD_SEC
            if esp:
                print(f"[YKİ-RTCM] ESP portu açıldı: {args.esp_port}")

        # --- oku (timeout=0.2 sn → veri yokken de döngü döner) -------------
        data = b""
        if gps is not None:
            try:
                data = gps.read(4096)
            except Exception as e:          # port koptu (USB çekildi vb.)
                gps_err = str(e)
                try:
                    gps.close()
                except Exception:
                    pass
                gps = None
                next_gps_try = now + REOPEN_PERIOD_SEC
        else:
            time.sleep(0.2)                 # port yokken CPU'yu yakma

        # --- ayrıştır + ilet ------------------------------------------------
        for frame in parser.feed(data):
            last_valid = time.monotonic()
            t = msg_type(frame)
            types_seen[t] = types_seen.get(t, 0) + 1
            if t in MSM7:
                msm7_seen.add(t)            # uyarısı özette (spam yok)
            win_msgs += 1
            win_bytes += len(frame)
            # ÜRETİM YOLU: ham RTCM3 mesajını ROS'a yayınla. Çerçeveleme
            # (TIP_RTK+BAZ_ID+CRC16+COBS) esp32_bridge'in işi — seri portun
            # sahibi o. Burada çerçevelersek iş iki yerde yapılır ve biri
            # değişince diğeri sessizce uyumsuz kalır.
            if ros_pub is not None:
                m = _ROS_MSG()
                m.data = list(frame)
                ros_pub.publish(m)
            if esp is not None:
                try:
                    esp.write(frame_rtcm(frame))
                except Exception as e:      # ESP hattı koptu
                    esp_err = str(e)
                    try:
                        esp.close()
                    except Exception:
                        pass
                    esp = None
                    next_esp_try = time.monotonic() + REOPEN_PERIOD_SEC

        # --- saniyelik sağlık satırı (VERİ OLMASA DA basılır) ---------------
        now = time.monotonic()
        if now >= next_summary:
            delta_bytes = parser.bytes_in - prev_bytes
            delta_crc = parser.crc_errors - prev_crc
            prev_bytes, prev_crc = parser.bytes_in, parser.crc_errors
            gap = now - (last_valid if last_valid is not None else start)

            if gps is None:
                line = (f"⚠ GPS PORTU AÇILAMADI ({args.gps_port}) — "
                        f"{REOPEN_PERIOD_SEC:.0f} sn'de bir deneniyor · {gps_err}")
            elif gap >= NO_DATA_WARN_SEC:
                if delta_bytes == 0:
                    hint = ("hatta HİÇ veri yok → kablo/Base gücü/"
                            "Mission Planner portu kapattı mı?")
                else:
                    # En sık sebep: modül base olarak YAPILANDIRILMAMIŞ ve
                    # NMEA basıyor. Sahada birebir bu yaşandı (NEO-F9P,
                    # fabrika ayarı, 1888 B/sn saf NMEA). USB'ye takılı bir
                    # F9P CDC-ACM'dir ve baud'un hiçbir etkisi yoktur, o
                    # yüzden "baud yanlış" ilk şüpheli DEĞİL.
                    hint = (f"ham veri akıyor ({delta_bytes}B/sn) ama RTCM yok "
                            f"→ modül base modunda mı? (TMODE3 + RTCM3 "
                            f"mesajları açık olmalı: yapılandırmak için "
                            f"f9p_base_yapilandir.py (bu dizinde))")
                line = (f"⚠ RTCM GELMİYOR ({gap:.0f} sn) · "
                        f"crc_err={parser.crc_errors} (+{delta_crc}) → {hint}")
            else:
                tipler = ", ".join(f"{k}:{v}" for k, v in sorted(types_seen.items()))
                line = (f"[{win_msgs} msg/s · {win_bytes}B · "
                        f"crc_err={parser.crc_errors}] tipler: {tipler or '—'}")
                if msm7_seen:
                    line += (f" | ⚠ MSM7 {sorted(msm7_seen)} — Base'i MSM4'e al "
                             f"(Mission Planner)")

            if args.esp_port and esp is None:
                line += f" | ⚠ ESP PORTU KAPALI (deneniyor · {esp_err})"

            print(line)
            win_msgs = 0
            win_bytes = 0
            types_seen = {}
            msm7_seen = set()
            next_summary = now + SUMMARY_PERIOD_SEC

    # --- temiz kapanış (SIGTERM/SIGINT) ------------------------------------
    for p in (gps, esp):
        try:
            if p is not None:
                p.close()
        except Exception:
            pass
    if ros_node is not None:
        import rclpy
        ros_node.destroy_node()
        rclpy.shutdown()
    print("[YKİ-RTCM] kapandı.")


# --------------------------------------------------------------------------
# Öz-testler — Büşra'nın sahte-port senaryoları (donanımsız çalışır)
# --------------------------------------------------------------------------

def _build_rtcm(msg_num: int, body: bytes) -> bytes:
    payload = bytes([(msg_num >> 4) & 0xFF, ((msg_num & 0xF) << 4)]) + body
    hdr = bytes([(len(payload) >> 8) & 0x03, len(payload) & 0xFF])
    f = b"\xD3" + hdr + payload
    return f + crc24q(f).to_bytes(3, "big")


def _self_test() -> None:
    import os

    m1005 = _build_rtcm(1005, b"\x11" * 17)   # 25B
    m1074 = _build_rtcm(1074, b"\x22" * 40)   # 48B

    # 1) Büşra senaryosu: sahte 0xD3 (uzunluk=43 → eski kod 2 mesajı yutuyordu)
    fake = b"\xD3" + bytes([0x00, 43])
    p = RTCMStreamParser()
    got = p.feed(fake + m1005 + m1074)
    assert [msg_type(f) for f in got] == [1005, 1074], got
    assert p.crc_errors >= 1
    print("✅ 1) sahte 0xD3 + 2 geçerli mesaj → 2'si de bulundu (eski kod: 0)")

    # 2) Akışın ortasından başlama (F9P zaten yayında senaryosu)
    p = RTCMStreamParser()
    got = p.feed(m1074[7:] + m1005 + m1074)   # yarım kuyruk + 2 tam mesaj
    assert [msg_type(f) for f in got] == [1005, 1074]
    print("✅ 2) akış ortasından başlangıç → mesaj kaybı yok")

    # 3) Bayt-bayt besleme — tamponun sınır davranışı
    p = RTCMStreamParser()
    got = []
    stream = fake + m1005 + m1074
    for i in range(len(stream)):
        got += p.feed(stream[i:i + 1])
    assert [msg_type(f) for f in got] == [1005, 1074]
    print("✅ 3) bayt-bayt besleme → aynı sonuç (tamponlama doğru)")

    # 4) Uzunluğu ileriyi gösteren sahte senkron: mesaj GECİKİR ama KAYBOLMAZ
    p = RTCMStreamParser()
    lone = b"\xD3\x03\xFF"                    # length=1023 → 1029B bekletir
    got = p.feed(lone + m1005)
    assert got == []                          # henüz karar veremez (bekliyor)
    got = p.feed(bytes(1100))                 # dolgu gelince sahte aday çözülür
    assert [msg_type(f) for f in got] == [1005]
    assert p.crc_errors >= 1
    print("✅ 4) uzun sahte senkron → m1005 gecikti ama kaybolmadı")

    # 5) Yanlış-baud simülasyonu: rastgele çöp → çökme yok, tampon sınırlı
    p = RTCMStreamParser()
    for _ in range(20):
        p.feed(os.urandom(500))
    assert len(p._buf) <= _MAX_RTCM_FRAME + 8
    print(f"✅ 5) 10KB rastgele çöp → çökme yok, tampon {len(p._buf)}B'ta sınırlı "
          f"(crc_err={p.crc_errors} — 'hat var format yok' sinyali)")

    print("\n🎯 Tüm öz-testler geçti. (Zamanlayıcı uyarısı için saha kontrolü: "
          "Base kapalıyken 3 sn içinde ⚠ RTCM GELMİYOR satırı akmalı.)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[YKİ-RTCM] durduruldu.")
