#!/usr/bin/env bash
# Copyright 2026 Yelpence
# KARA KUTU CANLI TUTMA — kosmuyorsa baslatir, kosuyorsa hicbir sey yapmaz.
#
# 🔴 NIYE VAR (8 Eylul 2026): kara_kutu.py `setsid nohup` ile elle
# baslatilmisti. Pil degisimi Pi'yi yeniden baslatti ve kayitci onunla
# gitti; TAM DA yakalamak icin kuruldugu arizada (ylp02 mesh dususu)
# CALISMIYORDU. Yani teshis araci, teshis edecegi anda yoktu.
#
# Kamera gozcusu (kamera_qr_gozcu.sh) ayni sorunu cron ile cozmustu;
# burada da supervizor CRON'un kendisi. Bu betik sadece "yoksa baslat".
#
# KURULUM (root gerekmez):
#     ~/yelpence_ws/kara_kutu_gozcu.sh --kur
# Kaldirmak:
#     ~/yelpence_ws/kara_kutu_gozcu.sh --kaldir

set -u
BETIK_YOLU="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
KAYITCI="$HOME/yelpence_ws/kara_kutu.py"
HEDEF="${YELPENCE_KARA_KUTU_HEDEF:-10.38.209.115}"
LOG="$HOME/kara_kutu.log"
ETIKET="# yelpence-kara-kutu-gozcu"

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

# Koseli parantez ZORUNLU: yoksa pgrep bu betigin kendi komut satirini
# eslestirir ve kayitci bir daha hic baslamaz (ayni tuzak kamera
# gozcusunde de not edildi).
if pgrep -f "kara_[k]utu\.py" > /dev/null 2>&1; then
    exit 0
fi
[ -f "$KAYITCI" ] || exit 1
echo "$(date -Is) kara_kutu.py kosmuyor — baslatiliyor" >> "$LOG"
setsid nohup python3 "$KAYITCI" --hedef "$HEDEF" >> "$LOG" 2>&1 < /dev/null &
