#!/bin/bash
# Kamera zinciri teshisi — kontrol hatti (I2C) ile veri hattini (MIPI) AYIRIR.
# 1 Eylul 2026: iki modul, ayni -121 / timeout tablosu. Ayrimi bu betik yapiyor.
set -u

echo "=========== 0) YENIDEN BASLATMA DENETIMI ==========="
_acilis=$(uptime -s); _dk=$(( ($(date +%s) - $(date -d "$_acilis" +%s)) / 60 ))
_hata=$(journalctl -k -b 0 2>/dev/null | grep -c "Error writing reg")
echo "  acilis: $_acilis  ($_dk dk once)"
if [ "$_hata" -gt 100 ]; then
    echo "  🔴 DIKKAT: bu acilista $_hata reg-yazma hatasi BIRIKMIS."
    echo "     Kamera modulu DEGISTIYSE once UCAGI KAPATIP AC — imx477 surucusu"
    echo "     sensoru yalnizca ACILISTA bagliyor. Calisirken degisen modul hic"
    echo "     ilklendirilmez ve asagidaki olcumlerin HEPSI yaniltici olur."
    echo
fi
echo "=========== 1) ACILIS YOKLAMASI (journal — dmesg tasabiliyor) ==========="
journalctl -k -b 0 2>/dev/null | grep -E "Device found is imx477|Using sensor" | cut -c1-110
printf "  chip-id HATA      : %s   (1 = bos ikinci port, normal)\n" \
    "$(journalctl -k -b 0 2>/dev/null | grep -c 'failed to read chip id')"
printf "  reg YAZMA hatasi  : %s   (0 olmali — I2C kontrol hatti)\n" \
    "$(journalctl -k -b 0 2>/dev/null | grep -c 'Error writing reg')"
printf "  start_streaming   : %s   (0 olmali)\n" \
    "$(journalctl -k -b 0 2>/dev/null | grep -c 'start_streaming failed')"

echo
echo "=========== 2) KAMERAYI TUTAN SUREC VAR MI ==========="
ps -eo pid,comm --no-headers | grep -E 'rpicam' | grep -v grep || echo "  temiz"
pkill -x rpicam-vid  2>/dev/null && echo "  rpicam-vid durduruldu"
pkill -x rpicam-jpeg 2>/dev/null && echo "  rpicam-jpeg durduruldu"
for p in $(ps -eo pid,args --no-headers | grep 'yelpence_ws/kamera_yayin' | grep -v grep | awk '{print $1}'); do
    kill "$p" 2>/dev/null && echo "  servis $p durduruldu"
done
sleep 3

echo
echo "=========== 3) VERI HATTI — uc kip ==========="
echo "  (dusuk gecip yuksek gecmiyorsa hat SINIRDA = kablo)"
for wh in "1332 990" "2028 1520" "4056 3040"; do
    set -- $wh
    rm -f "/tmp/th_$1.jpg"
    out=$(timeout 22 rpicam-jpeg -o "/tmp/th_$1.jpg" -t 2500 -n --width "$1" --height "$2" 2>&1)
    if [ -s "/tmp/th_$1.jpg" ]; then
        printf "  %4sx%-4s  ✅ %s bayt\n" "$1" "$2" "$(stat -c%s "/tmp/th_$1.jpg")"
    else
        printf "  %4sx%-4s  ❌ %s\n" "$1" "$2" \
            "$(echo "$out" | grep -oE 'timed out|Device timeout|failed to acquire|busy' | head -1)"
    fi
    pkill -x rpicam-jpeg 2>/dev/null; sleep 2
done

echo
echo "=========== 4) AKIS KARARLILIGI (25 sn) ==========="
setsid nohup python3 "$HOME/yelpence_ws/kamera_yayin.py" > /tmp/kamera_yayin.log 2>&1 < /dev/null &
sleep 8
onceki=0; durgun=0
for i in 0 1 2 3 4; do
    k=$(curl -s -m 5 http://127.0.0.1:8080/olcum | grep -oP '"kare_sayisi":\s*\K[0-9]+')
    k=${k:-0}
    d=$((k - onceki))
    [ "$i" -gt 0 ] && [ "$d" -eq 0 ] && durgun=$((durgun + 1))
    printf "  t=%2ds  kare=%-6s delta=%-6s\n" "$((i*5))" "$k" "$d"
    onceki=$k; sleep 5
done

echo
echo "=========== SONUC ==========="
if [ "$onceki" -gt 400 ] && [ "$durgun" -eq 0 ]; then
    echo "  ✅ AKIS KARARLI — kamera saglikli"
elif [ "$onceki" -gt 0 ]; then
    echo "  ⚠️ AKIS KESILIYOR ($durgun durgun ornek) — veri hatti SINIRDA"
    echo "     I2C saglamsa suclu FLEX ya da modulun CSI cikisi."
else
    echo "  ❌ HIC KARE YOK — veri hatti KOPUK"
fi
