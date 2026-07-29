#!/usr/bin/env python3
"""f9p_base_yapilandir.py — u-blox F9P'yi RTK BASE olarak yapılandırır.

NEDEN BU SCRIPT VAR
-------------------
Spec §3.1 base kurulumunu Mission Planner'ın "RTK/GPS Inject" ekranından
yapılacak MANUEL adım olarak tarif ediyor ve otomatik yapılandırmayı
"backlog v2, şimdilik uygulanmaz" diye bırakmış. Sahada bu üç sebeple
işlemedi:

  1. YKİ laptopu Linux; Mission Planner ve u-center yok.
  2. QGC seri portlara autoconnect yapıyor ve RTK okuyucusunun portunu
     kapıyor ("Device or resource busy" — birebir yaşandı).
  3. Manuel adım tekrarlanabilir değil: her kurulumda elle yapılırsa
     yarışma günü unutulacak tek şey bu olur.

Bu script aynı işi UBX-CFG-VALSET ile yapar; PROTVER >= 27 gerektirir
(NEO-F9P'de 27.40 doğrulandı).

KULLANIM
--------
    # Mevcut durumu oku (hiçbir şey değiştirmez)
    python3 f9p_base_yapilandir.py --durum

    # Survey-In ile base yap (SAHADA, açık gökyüzü altında)
    python3 f9p_base_yapilandir.py --survey-in --sure 120 --dogruluk 2.0

    # Survey bittikten sonra konumu sabitle (sonraki kurulumlarda survey yok)
    python3 f9p_base_yapilandir.py --sabitle

    # Base modunu kapat
    python3 f9p_base_yapilandir.py --rover

ÖNEMLİ: Survey-In kapalı alanda YAKINSAMAZ. Çoklu-yansıma yüzünden konum
gezinir ve doğruluk hedefe inmez. Bu adım dışarıda yapılmalı.
"""
from __future__ import annotations

import argparse
import sys
import time

VARSAYILAN_PORT = ("/dev/serial/by-id/"
                   "usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00")

# Spec §2.6 "beklenen mesaj seti": 1005, 1074, 1084, 1094, 1230.
# 1124 (BeiDou MSM4) da ekleniyor: modül BDS görüyor (MON-VER: GPS;GLO;GAL;BDS)
# ve rover'lar da BDS destekliyorsa fix kalitesi artar. MSM7 KULLANILMAZ —
# 720B MAVLink tavanını aşabilir (spec Bölüm 5).
RTCM_MESAJLARI = [
    "CFG_MSGOUT_RTCM_3X_TYPE1005_USB",   # referans istasyon ARP
    "CFG_MSGOUT_RTCM_3X_TYPE1074_USB",   # GPS MSM4
    "CFG_MSGOUT_RTCM_3X_TYPE1084_USB",   # GLONASS MSM4
    "CFG_MSGOUT_RTCM_3X_TYPE1094_USB",   # Galileo MSM4
    "CFG_MSGOUT_RTCM_3X_TYPE1124_USB",   # BeiDou MSM4
    "CFG_MSGOUT_RTCM_3X_TYPE1230_USB",   # GLONASS kod-faz sapmaları
]

TMODE_ADI = {0: "KAPALI (rover)", 1: "SURVEY-IN", 2: "SABİT KONUM"}


def _baglan(port: str, baud: int):
    import serial
    return serial.Serial(port, baud, timeout=1.0)


def _yaz(ser, kalici: bool, cfg: list) -> None:
    """CFG-VALSET gönder. kalici=True ise RAM+BBR+Flash (güç kesilse de kalır)."""
    from pyubx2 import UBXMessage
    katman = 7 if kalici else 1          # 7 = RAM|BBR|Flash, 1 = yalnız RAM
    msg = UBXMessage.config_set(katman, 0, cfg)
    ser.write(msg.serialize())
    time.sleep(0.35)


def _oku(ser, anahtarlar: list) -> dict:
    """CFG-VALGET ile ayarları geri okur. Yazdığımızın gerçekten oturduğunu
    doğrulamak için — 'gönderdim' ile 'kabul edildi' aynı şey değil."""
    from pyubx2 import UBXMessage, UBXReader
    ser.reset_input_buffer()
    ser.write(UBXMessage.config_poll(0, 0, anahtarlar).serialize())
    time.sleep(0.6)
    sonuc: dict = {}
    ubr = UBXReader(ser, protfilter=2)
    t0 = time.time()
    while time.time() - t0 < 2.0:
        try:
            _, parsed = ubr.read()
        except Exception:
            break
        if parsed is None:
            continue
        if parsed.identity == "CFG-VALGET":
            for a in anahtarlar:
                if hasattr(parsed, a):
                    sonuc[a] = getattr(parsed, a)
            if len(sonuc) >= len(anahtarlar):
                break
    return sonuc


def _svin_durumu(ser) -> dict | None:
    """UBX-NAV-SVIN: survey-in ilerlemesi."""
    from pyubx2 import UBXMessage, UBXReader
    ser.reset_input_buffer()
    ser.write(UBXMessage("NAV", "NAV-SVIN", 0).serialize())
    ubr = UBXReader(ser, protfilter=2)
    t0 = time.time()
    while time.time() - t0 < 2.5:
        try:
            _, p = ubr.read()
        except Exception:
            break
        if p is not None and p.identity == "NAV-SVIN":
            return {"aktif": p.active, "gecerli": p.valid,
                    "sure_s": p.dur, "dogruluk_m": p.meanAcc / 10000.0,
                    "gozlem": p.obs}
    return None


def durum_yazdir(ser) -> None:
    anahtarlar = (["CFG_TMODE_MODE", "CFG_TMODE_SVIN_MIN_DUR",
                   "CFG_TMODE_SVIN_ACC_LIMIT", "CFG_USBOUTPROT_NMEA",
                   "CFG_USBOUTPROT_RTCM3X"] + RTCM_MESAJLARI)
    d = _oku(ser, anahtarlar)
    if not d:
        print("  ⚠ CFG-VALGET cevabı yok — modül UBX kabul etmiyor olabilir.")
        return
    mod = d.get("CFG_TMODE_MODE")
    print(f"  TMODE           : {mod} = {TMODE_ADI.get(mod, '?')}")
    if mod == 1:
        print(f"  Survey-In min süre    : {d.get('CFG_TMODE_SVIN_MIN_DUR')} sn")
        print(f"  Survey-In doğruluk hd.: "
              f"{(d.get('CFG_TMODE_SVIN_ACC_LIMIT') or 0)/10000.0:.2f} m")
    print(f"  USB çıkışı NMEA : {'açık' if d.get('CFG_USBOUTPROT_NMEA') else 'kapalı'}")
    print(f"  USB çıkışı RTCM3: {'açık' if d.get('CFG_USBOUTPROT_RTCM3X') else 'kapalı'}")
    acik = [k.split('TYPE')[1].split('_')[0] for k in RTCM_MESAJLARI if d.get(k)]
    print(f"  RTCM mesajları  : {', '.join(acik) if acik else '— HİÇBİRİ AÇIK DEĞİL'}")

    sv = _svin_durumu(ser)
    if sv:
        if sv["gecerli"]:
            print(f"  Survey-In       : ✅ TAMAMLANDI "
                  f"({sv['sure_s']} sn, {sv['dogruluk_m']:.2f} m)")
        elif sv["aktif"]:
            print(f"  Survey-In       : ⏳ sürüyor — {sv['sure_s']} sn, "
                  f"doğruluk {sv['dogruluk_m']:.2f} m, {sv['gozlem']} gözlem")
        else:
            print("  Survey-In       : pasif")


def main() -> int:
    ap = argparse.ArgumentParser(description="u-blox F9P RTK base yapılandırıcı")
    ap.add_argument("--port", default=VARSAYILAN_PORT)
    ap.add_argument("--baud", type=int, default=115200,
                    help="USB'de (CDC-ACM) anlamsız, seri bağlantı için")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--durum", action="store_true", help="Sadece oku, değiştirme")
    g.add_argument("--survey-in", action="store_true", help="Survey-In base modu")
    g.add_argument("--sabitle", action="store_true",
                   help="Tamamlanmış survey konumunu sabit moda al")
    g.add_argument("--rover", action="store_true", help="Base modunu kapat")
    ap.add_argument("--sure", type=int, default=120, help="Survey-In min süre (sn)")
    ap.add_argument("--dogruluk", type=float, default=2.0,
                    help="Survey-In hedef doğruluk (m)")
    ap.add_argument("--nmea-kapat", action="store_true",
                    help="USB'de NMEA'yı kapat (hattı RTCM'e bırakır)")
    ap.add_argument("--gecici", action="store_true",
                    help="Yalnız RAM'e yaz (güç kesilince kaybolur)")
    a = ap.parse_args()

    try:
        ser = _baglan(a.port, a.baud)
    except Exception as e:
        print(f"HATA: port açılamadı ({a.port}): {e}")
        print("  yki_rtcm_reader çalışıyorsa portu tutuyordur; önce onu durdur.")
        return 1

    kalici = not a.gecici
    try:
        if a.durum or not (a.survey_in or a.sabitle or a.rover):
            print(f"── {a.port} ──")
            durum_yazdir(ser)
            return 0

        if a.rover:
            print("Base modu kapatılıyor (rover'a dönülüyor)...")
            _yaz(ser, kalici, [("CFG_TMODE_MODE", 0)]
                 + [(k, 0) for k in RTCM_MESAJLARI])
        elif a.survey_in:
            print(f"Survey-In başlatılıyor: min {a.sure} sn, hedef "
                  f"{a.dogruluk:.2f} m ({'kalıcı' if kalici else 'geçici'})")
            print("  ⚠ Kapalı alanda yakınsamaz — açık gökyüzü gerekli.")
            _yaz(ser, kalici, [
                ("CFG_TMODE_MODE", 1),
                ("CFG_TMODE_SVIN_MIN_DUR", a.sure),
                # SVIN_ACC_LIMIT birimi 0.1 mm
                ("CFG_TMODE_SVIN_ACC_LIMIT", int(a.dogruluk * 10000)),
            ])
            # Navigasyon hızını 1 Hz'e sabitle — BU ATLANIRSA RTCM 10 Hz AKAR.
            #
            # Mesaj hızı "her epoch'ta bir" olarak ayarlanıyor; epoch hızı da
            # CFG_RATE_MEAS'ten geliyor. Modül 100 ms'e (10 Hz) ayarlıysa RTCM
            # de 10 Hz çıkar. Sahada ölçüldü: 7055 bayt/sn (beklenen ~700).
            # Mesh'e etkisi ~30 fragment/sn ve iki drone'a unicast ile 60
            # iletim/sn — yük testinde temiz taşınan 37/sn'nin üstünde, üstelik
            # tamamen gereksiz: RTK düzeltmesi 1 Hz'de standarttır ve tazelik
            # bütçesi 2 saniyedir (spec §1).
            #
            # QGC'nin "RTK GPS" autoconnect'i modülü kendi ayarlarıyla
            # bırakabiliyor, o yüzden burada açıkça sabitliyoruz.
            _yaz(ser, kalici, [("CFG_RATE_MEAS", 1000),   # ms -> 1 Hz
                               ("CFG_RATE_NAV", 1)])      # her ölçümde 1 çözüm
            # RTCM mesajlarını aç: rate=1 -> her epoch'ta bir (artık 1 Hz)
            _yaz(ser, kalici, [(k, 1) for k in RTCM_MESAJLARI])
            _yaz(ser, kalici, [("CFG_USBOUTPROT_RTCM3X", 1)])
        elif a.sabitle:
            sv = _svin_durumu(ser)
            if not sv or not sv["gecerli"]:
                print("HATA: geçerli bir survey-in sonucu yok. Önce --survey-in "
                      "çalıştırıp tamamlanmasını bekle (--durum ile izle).")
                return 1
            print(f"Survey tamamlanmış ({sv['dogruluk_m']:.2f} m). "
                  f"Konum sabit moda alınıyor — sonraki açılışlarda survey "
                  f"beklenmeyecek.")
            # NOT: F9P survey-in bitince konumu kendi TMODE3 sabit alanlarına
            # yazar; MODE=2'ye geçmek onu kalıcılaştırır.
            _yaz(ser, kalici, [("CFG_TMODE_MODE", 2)])

        if a.nmea_kapat:
            print("USB'de NMEA kapatılıyor.")
            _yaz(ser, kalici, [("CFG_USBOUTPROT_NMEA", 0)])

        print("\n── yazım sonrası GERİ OKUMA ──")
        time.sleep(0.8)
        durum_yazdir(ser)
        return 0
    finally:
        ser.close()


if __name__ == "__main__":
    sys.exit(main())
