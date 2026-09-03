#!/usr/bin/env bash
# Copyright 2026 Yelpence
# pil_testi.py'yi BIR YA DA COK ucakta baslatir / durdurur / kaydi getirir.
#
# NIYE SARMALAYICI VAR
#  1) 🔴 ISIM ILE NUMARA AYNI DEGIL (CLAUDE.md §2): ylp00 -> drone1/ajan 1,
#     ylp01 -> drone2/ajan 2, ylp02 -> drone3/ajan 3. Elle `--ajan` yazmak
#     bu projede tekrarlayan bir hata kaynagi; burada tablo tek yerde.
#  2) Iki ucakta test yaparken kayitlarin YAKIN ZAMANLI baslamasi lazim,
#     yoksa gerilim izleri kiyaslanamaz. SSH'ler PARALEL aciliyor.
#  3) Durdurma SIGINT ile yapilmali: betik o sinyalde CSV'yi kapatiyor.
#     `docker restart` de calisir ama tum ucus dugumlerini de dusurur.
#
# Kullanim:
#   ./pil_testi_calistir.sh basla  ylp00 ylp01
#   ./pil_testi_calistir.sh durum  ylp00 ylp01
#   ./pil_testi_calistir.sh durdur ylp00 ylp01
#   ./pil_testi_calistir.sh getir  ylp00 ylp01      # CSV'leri laptopa ceker
#
# Getirilen dosyalar: ./pil_kayitlari/<ylpXX>_<damga>.csv
# Cozumleme (ROS gerekmez):
#   python3 deploy/rpi/teshis/pil_testi.py coz --csv pil_kayitlari/<ad>.csv --cizelge

set -u
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BUL="$KOK/deploy/yki/drone_bul.sh"
HEDEF_DIZIN="$KOK/pil_kayitlari"

# ylp -> konteyner:ajan.  🔴 CLAUDE.md §2: ylp00 = drone1, ylp02 = drone3.
esle() {
    case "$1" in
        ylp00) echo "drone1 1" ;;
        ylp01) echo "drone2 2" ;;
        ylp02) echo "drone3 3" ;;
        *) return 1 ;;
    esac
}

KIP="${1:-}"; shift || true
[ -n "$KIP" ] || { sed -n '2,30p' "$0"; exit 1; }
UCAKLAR=("$@")
[ ${#UCAKLAR[@]} -gt 0 ] || UCAKLAR=(ylp00 ylp01 ylp02)

ROS_ON="source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash 2>/dev/null"

pids=(); hata=0
for d in "${UCAKLAR[@]}"; do
    if ! read -r kon ajan <<<"$(esle "$d")"; then
        echo "bilinmeyen ucak: $d"; hata=1; continue
    fi
    (
        case "$KIP" in
        basla)
            # -d: konteynerde ARKA PLANDA kalir, SSH kapansa da surer.
            cikti=$(timeout 90 "$BUL" "$d" \
                "docker exec -d -e ROS_LOCALHOST_ONLY=1 $kon bash -lc '
                     $ROS_ON
                     exec python3 /ws/pil_testi.py kaydet --ajan $ajan --hz 5'" 2>&1)
            sleep 3
            ad=$(timeout 60 "$BUL" "$d" \
                "docker exec $kon ls -t /ws/pil_testi 2>/dev/null | head -1" 2>/dev/null \
                | tr -d '\r' | tail -1)
            if [ -n "$ad" ]; then
                echo "$d ($kon, ajan $ajan) BASLADI -> $ad"
            else
                echo "$d BASLAMADI: $(echo "$cikti" | tail -2)"; exit 1
            fi
            ;;
        durum)
            o=$(timeout 60 "$BUL" "$d" \
                "docker exec $kon bash -lc '
                    pgrep -f pil_testi.py >/dev/null && echo KOSUYOR || echo DURDU
                    ls -t /ws/pil_testi 2>/dev/null | head -1
                    wc -l < \"/ws/pil_testi/\$(ls -t /ws/pil_testi 2>/dev/null | head -1)\" 2>/dev/null'" 2>/dev/null \
                | tr -d '\r' | tail -3 | tr '\n' ' ')
            echo "$d: $o"
            ;;
        durdur)
            # 🔴 SIGINT: betik bu sinyalde CSV'yi flush edip kapatiyor.
            o=$(timeout 60 "$BUL" "$d" \
                "docker exec $kon pkill -INT -f pil_testi.py && echo DURDURULDU || echo 'zaten kapali'" 2>&1 \
                | tr -d '\r' | tail -1)
            echo "$d: $o"
            ;;
        getir)
            mkdir -p "$HEDEF_DIZIN"
            ad=$(timeout 60 "$BUL" "$d" \
                "docker exec $kon ls -t /ws/pil_testi 2>/dev/null | head -1" 2>/dev/null \
                | tr -d '\r' | tail -1)
            if [ -z "$ad" ]; then echo "$d: kayit YOK"; exit 1; fi
            # Yalniz CSV satirlarini al: drone_bul.sh basina bilgi satiri
            # basabiliyor, onlar dosyaya karisirsa cozumleme satiri atlar.
            timeout 180 "$BUL" "$d" "docker exec $kon cat /ws/pil_testi/$ad" 2>/dev/null \
                | grep -E '^(t_epoch|[0-9])' > "$HEDEF_DIZIN/$ad"
            n=$(wc -l < "$HEDEF_DIZIN/$ad")
            if [ "$n" -lt 2 ]; then echo "$d: BOS geldi ($ad)"; exit 1; fi
            echo "$d: $HEDEF_DIZIN/$ad  ($n satir)"
            ;;
        *)
            echo "bilinmeyen kip: $KIP"; exit 1 ;;
        esac
    ) &
    pids+=($!)
done

for p in "${pids[@]}"; do wait "$p" || hata=1; done
exit "$hata"
