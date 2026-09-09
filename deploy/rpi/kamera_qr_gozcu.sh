#!/usr/bin/env bash
# Copyright 2026 Yelpence
# KAMERA YAYINI CANLI TUTMA — kosmuyorsa baslatir, kosuyorsa hicbir sey yapmaz.
#
# 🔴 NIYE VAR (8 Eylul 2026): `kamera_yayin.py` ucus hazirligi sirasinda
# KENDILIGINDEN OLDU. camera_driver "Kamera acilamadi: .../akis" verdi ve
# QR okuma SESSIZCE bitti — uctaki hicbir dugum hata vermedi, YKI yalnizca
# "kamera arizasi" gosterdi. Havada olsaydi QR gorevi kaybedilirdi.
#
# NIYE KALICI BIR BEKCI SUREC DEGIL: bekcinin kendisi de olur. Burada
# supervizor CRON'un kendisi — zaten bir sistem servisi ve ayakta.
# Bu betik SADECE "yoksa baslat" yapar, dakikada bir cagrilir.
#
# KURULUM (root GEREKMEZ, kullanici crontab'i):
#     ~/yelpence_ws/kamera_qr_gozcu.sh --kur
# Kaldirmak icin:
#     ~/yelpence_ws/kamera_qr_gozcu.sh --kaldir

set -u
BETIK_YOLU="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
YAYIN="$HOME/yelpence_ws/kamera_qr.py"
LOG="$HOME/kamera_qr.log"
GOZCU_LOG="$HOME/kamera_qr_gozcu.log"
# crontab satirini bu etiketle buluyoruz — iki kez eklenmesin.
ETIKET="# yelpence-kamera-qr-gozcu"

kur() {
    ( crontab -l 2>/dev/null | grep -v "$ETIKET"
      echo "@reboot $BETIK_YOLU $ETIKET"
      echo "* * * * * $BETIK_YOLU $ETIKET"
    ) | crontab -
    echo "kuruldu (dakikada bir + her acilista):"
    crontab -l | grep "$ETIKET"
}

kaldir() {
    crontab -l 2>/dev/null | grep -v "$ETIKET" | crontab -
    echo "kaldirildi"
}

case "${1:-}" in
    --kur)    kur;    exit 0 ;;
    --kaldir) kaldir; exit 0 ;;
esac

# --- asil is: yoksa baslat ------------------------------------------------
# pgrep deseninde koseli parantez ZORUNLU: yoksa pgrep bu betigin KENDI
# komut satirini eslestirip "kosuyor" sanar ve yayin bir daha hic baslamaz.
# (Ayni tuzak bu depoda pkill ile iki kez yasandi.)
if pgrep -f "kamera_[q]r\.py" > /dev/null 2>&1; then
    exit 0
fi

[ -f "$YAYIN" ] || { echo "$(date -Is) YAYIN YOK: $YAYIN" >> "$GOZCU_LOG"; exit 1; }

echo "$(date -Is) kamera_qr.py kosmuyor — baslatiliyor" >> "$GOZCU_LOG"
setsid nohup python3 "$YAYIN" >> "$LOG" 2>&1 < /dev/null &
