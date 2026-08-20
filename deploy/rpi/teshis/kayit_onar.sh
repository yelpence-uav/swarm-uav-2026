#!/bin/bash
# Konteyner icinde kosar (root gerekiyor: kayit dosyalari root'a ait).
#
#   docker exec droneN bash /ws/kayit_onar.sh [--kuru]
#
# (dagit.sh teshis betiklerini /ws/ KOKUNE koyuyor, /ws/teshis/ altina degil)
#
# NE ICIN
# =======
# 20 Agustos 2026'da olculdu: ylp00'daki 60 kayittan 60'inda metadata.yaml
# YOK ve `ros2 bag info` hicbirini acamiyor ("Could not find metadata in bag
# directory"). Yani UCUS VERILERI rosbag2 ile okunamaz durumda.
#
# NEDEN
# =====
# rosbag2 metadata.yaml'i kayit dugumu TEMIZ KAPANDIGINDA yaziyor. Pil
# degistirmek icin gucu kesince kayit dugumu SIGKILL bile almiyor, oylece
# olyor — metadata hic yazilmiyor. Bu projede pil degisimi gunde defalarca
# oluyor, yani kural disi degil, NORMAL yol.
#
# VERI KAYIP DEGIL
# ================
# .mcap parcalari kendi kendini tanimlar; `ros2 bag reindex` metadata'yi
# yeniden uretebiliyor. TEK ENGEL: guc kesilirken rosbag2'nin yeni actigi
# SON parca 0 bayt (ya da yarim) kaliyor ve tek bozuk parca butun reindex'i
# iptal ediyor ("file too small"). O parcayi kenara alinca reindex geciyor.
#
# 20 Agustos'ta ylp00_20260820_211501 uzerinde dogrulandi: _18.mcap 0 bayt,
# kenara alindi, reindex tamam, `ros2 bag info` -> 18 parca / 21.5 MiB.
#
# YARIM PARCALAR SILINMEZ
# =======================
# /ws/kayit_yarim/ altina TASINIR. Silmek geri alinamaz ve 0 bayt olmayan
# (gercekten yarim ama icinde veri olan) bir parca cikarsa elle kurtarilir.

set -uo pipefail
KURU=0
[ "${1:-}" = "--kuru" ] && KURU=1

KAYIT=/ws/kayit
YARIM=/ws/kayit_yarim
mkdir -p "$YARIM"

# ROS setup dosyalari `set -u` altinda coker (AMENT_TRACE_SETUP_FILES:
# unbound variable) — kaynak alirken gecici kapatiliyor.
set +u
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash 2>/dev/null || true
set -u

# Su an KAYIT YAPILAN dizine dokunma — acik dosyayi tasimak kaydi bozar.
AKTIF=""
if pgrep -f "ros2 bag record" >/dev/null 2>&1; then
    AKTIF=$(ls -1dt "$KAYIT"/*/ 2>/dev/null | head -1)
    echo "[onar] kayit SURUYOR, atlanacak: $(basename "${AKTIF%/}")"
fi

toplam=0; atlandi=0; onarildi=0; basarisiz=0
for d in "$KAYIT"/*/; do
    [ -d "$d" ] || continue
    ad=$(basename "${d%/}")
    toplam=$((toplam + 1))

    if [ -n "$AKTIF" ] && [ "${d%/}" = "${AKTIF%/}" ]; then
        atlandi=$((atlandi + 1)); continue
    fi
    if [ -f "$d/metadata.yaml" ]; then
        atlandi=$((atlandi + 1)); continue
    fi

    # Bos/kucuk parcalari kenara al. mcap basligi 8 bayttan uzun; 1 KB alti
    # parca zaten hicbir mesaj tasimiyor.
    tasinan=0
    for m in "$d"*.mcap; do
        [ -e "$m" ] || continue
        b=$(stat -c %s "$m")
        if [ "$b" -lt 1024 ]; then
            if [ "$KURU" = 1 ]; then
                echo "[kuru] $ad: $(basename "$m") ($b bayt) tasinacakti"
            else
                mv "$m" "$YARIM/" && tasinan=$((tasinan + 1))
            fi
        fi
    done

    if [ "$KURU" = 1 ]; then
        echo "[kuru] $ad: reindex edilecekti"
        continue
    fi

    # HATA GUDUMLU YENIDEN DENEME
    #
    # 0 bayt kurali YETMIYOR: 17 Agustos'ta ylp02'de olculdu — son parca
    # 831488 bayt, yani "dolu", ama son zstd blogu yarim kalmis ve mcap
    # "Data corruption detected" diyor. Guc kesilirken yazilan parcanin
    # normal hali bu; sifir bayt olan yalnizca YENI ACILMIS parca.
    #
    # Bu yuzden parcayi boyutuna gore degil, REINDEX'IN KENDISINE sorarak
    # eliyoruz: hata metnindeki dosyayi kenara al, tekrar dene. Her tur en
    # az bir parca eksiltiyor, o yuzden dongu sonlu.
    deneme=0
    while :; do
        if ! ls "$d"*.mcap >/dev/null 2>&1; then
            echo "[onar] $ad: hic saglam parca yok, atlandi"
            basarisiz=$((basarisiz + 1)); break
        fi

        cikti=$(timeout 240 ros2 bag reindex "$d" -s mcap 2>&1)
        if [ -f "$d/metadata.yaml" ]; then
            n=$(ls -1 "$d"*.mcap | wc -l)
            ek=""
            [ "$tasinan" -gt 0 ] && ek=", $tasinan bozuk parca kenara alindi"
            echo "[onar] $ad: TAMAM ($n parca$ek)"
            onarildi=$((onarildi + 1)); break
        fi

        # "Could not open '/ws/kayit/.../xxx_4.mcap' with 'mcap'."
        kotu=$(printf '%s\n' "$cikti" | sed -n "s/.*Could not open '\([^']*\.mcap\)'.*/\1/p" | head -1)
        deneme=$((deneme + 1))
        if [ -z "$kotu" ] || [ ! -f "$kotu" ] || [ "$deneme" -gt 20 ]; then
            echo "[onar] $ad: BASARISIZ — elle bak"
            printf '%s\n' "$cikti" | grep -i error | head -2 | sed 's/^/         /'
            basarisiz=$((basarisiz + 1)); break
        fi
        b=$(stat -c %s "$kotu")
        echo "[onar] $ad: bozuk parca $(basename "$kotu") ($b bayt) kenara aliniyor"
        mv "$kotu" "$YARIM/" && tasinan=$((tasinan + 1))
    done
done

echo "[onar] OZET: toplam=$toplam onarildi=$onarildi atlandi=$atlandi basarisiz=$basarisiz"
[ "$basarisiz" = 0 ]
