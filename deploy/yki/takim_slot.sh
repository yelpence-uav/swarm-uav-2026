#!/bin/bash
# Copyright 2026 Yelpence
# ============================================================================
# TAKIM SLOTUNU CANLI DEGISTIR — konteyner yeniden baslatmadan.
#
# 🔴 NIYE VAR (9 Eylul 2026, finale bir gun kala)
# QR'in `team` tablosu takim NUMARASIYLA degil SLOT ile anahtarli. Ucak
# `str(team_slot)` ariyor; slot yanlissa QR HIC okunmaz ve tek gorunen satir
# "Takim slotu N tabloda yok" olur. Hakem slotu GOREV ANINDA veriyor, yani
# deger sahada ogreniliyor.
#
# Eskiden slot yalniz acilista okunuyordu: degistirmek konteyner yeniden
# baslatmak demekti, o da QR KONUM TABLOSUNU siliyordu (tekrar sermek
# gerekiyordu). Artik `ros2 param set` ile aninda geciyor.
#
# KULLANIM
#     ./deploy/yki/takim_slot.sh 3          # ucuna da yaz
#     ./deploy/yki/takim_slot.sh 3 ylp00    # yalniz o ucaga
#     ./deploy/yki/takim_slot.sh --oku      # su an ne ayarli
#
# NOT: vision_node YALNIZ kameralı uçakta koşar; digerlerinde "dugum yok"
# demesi normaldir, hata degil.
# ============================================================================
set -u
BETIK_DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUL="$BETIK_DIZIN/drone_bul.sh"

declare -A KAP=( [ylp00]=drone1 [ylp01]=drone2 [ylp02]=drone3 )

if [ $# -lt 1 ]; then
    sed -n '3,25p' "$0" | sed 's/^# \?//'
    exit 1
fi

OKU=0
if [ "$1" = "--oku" ]; then OKU=1; shift; else SLOT="$1"; shift; fi

if [ "$OKU" = "0" ]; then
    case "$SLOT" in
        ''|*[!0-9]*) echo "HATA: slot bir SAYI olmali (or. 1, 2, 3)"; exit 1 ;;
    esac
fi

HEDEFLER=("$@")
[ ${#HEDEFLER[@]} -eq 0 ] && HEDEFLER=(ylp00 ylp01 ylp02)

for ad in "${HEDEFLER[@]}"; do
    kap="${KAP[$ad]:-}"
    if [ -z "$kap" ]; then echo "HATA: bilinmeyen ucak '$ad'"; continue; fi
    if [ "$OKU" = "1" ]; then
        komut="ros2 param get /vision_node team_slot"
    else
        komut="ros2 param set /vision_node team_slot $SLOT"
    fi
    printf '%-7s ' "$ad"
    timeout 90 "$BUL" "$ad" "docker exec -e ROS_LOCALHOST_ONLY=1 $kap bash -lc \
        'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1; \
         source /ws/install/setup.bash >/dev/null 2>&1; \
         timeout 15 $komut 2>&1 | tail -1'" 2>/dev/null \
        | grep -vE '^\[|^\.\.\.' | tail -1 \
        || echo 'ULASILAMADI'
done
