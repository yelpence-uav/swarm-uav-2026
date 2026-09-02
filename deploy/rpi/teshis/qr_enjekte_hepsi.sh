#!/usr/bin/env bash
# Copyright 2026 Yelpence
# qr_enjekte.py'yi UC UCAKTA birden, yakin zamanli calistirir.
#
# NIYE SARMALAYICI VAR: baslat.sh ROS_LOCALHOST_ONLY=1 ile kosuyor, yani
# laptoptan yayinlanan konu ucaga ULASMAZ — her ucagin kendi ROS grafiginde
# yayin yapmak zorundayiz. Ustelik uc ucak AYNI QR'i gormus gibi davranmali;
# ardisik SSH ile teker teker calistirmak aralarina saniyeler koyar ve sürü
# farkli anlarda manevraya girer. Burada uc SSH PARALEL baslatiliyor.
#
# Kullanim (argumanlar oldugu gibi qr_enjekte.py'ye gecer):
#   ./qr_enjekte_hepsi.sh --qr 1 --sonraki 0 --roll 10
#   ./qr_enjekte_hepsi.sh --qr 1 --sonraki 2 --formasyon 2 --aralik 7
#
# 🔴 qr_seq UC UCAKTA AYNI OLMALI: mission_fsm sirasiz/eski QR'i dusuruyor,
# ama uc ucak ayni QR'i farkli seq ile gorurse durum makineleri ayrisir.
# Burada tek bir seq uretilip ucune de ayni deger veriliyor.

set -u
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BUL="$KOK/deploy/yki/drone_bul.sh"
BETIK="$KOK/deploy/rpi/teshis/qr_enjekte.py"

SEQ="$(date +%s)"

# ylp -> konteyner adi (CLAUDE.md §2: isim ile numara AYNI DEGIL)
declare -A KON=( [ylp00]=drone1 [ylp01]=drone2 [ylp02]=drone3 )

echo "qr_seq=$SEQ  ·  argumanlar: $*"

pids=()
for d in ylp00 ylp01 ylp02; do
    k="${KON[$d]}"
    (
        # 🔴 `| tail` cikis kodunu MASKELER: ilk surumde ucakta
        # AttributeError patlarken sarmalayici "TAMAM" dedi. Once tam ciktiyi
        # al, durumu SAKLA, kirpmayi sonra yap.
        tam=$(timeout 90 "$BUL" "$d" \
            "docker exec -e ROS_LOCALHOST_ONLY=1 $k bash -lc '
                 source /opt/ros/jazzy/setup.bash
                 source /ws/install/setup.bash 2>/dev/null
                 python3 /ws/qr_enjekte.py --seq $SEQ $*'" 2>&1)
        durum=$?
        printf '=== %s (%s) ===\n%s\n' "$d" "$k" "$(printf '%s' "$tam" | tail -4)"
        # Python izi ciktida gorunuyorsa cikis kodu 0 olsa bile BASARISIZ say.
        case "$tam" in *Traceback*|*Error*) durum=1 ;; esac
        exit "$durum"
    ) &
    pids+=($!)
done

hata=0
for p in "${pids[@]}"; do wait "$p" || hata=1; done
[ "$hata" -eq 0 ] && echo "TAMAM — uc ucakta da enjekte edildi" \
                  || echo "UYARI: en az bir ucakta hata var, ciktilara bak"
exit "$hata"
