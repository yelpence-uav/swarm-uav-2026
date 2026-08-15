#!/usr/bin/env bash
# =============================================================================
# Repodaki ROS paketlerini drone Pi'lerine dagitir, konteynerde derler ve
# HANGI COMMIT'IN yuklu oldugunu Pi'ye yazar.
#
#   ./dagit.sh                 # cihazlar.md'deki tum drone'lar
#   ./dagit.sh ylp02           # yalniz biri
#   KURU=1 ./dagit.sh          # ne yapilacagini goster, dokunma
#
# NEDEN VAR
# 30 Temmuz'da olculdu: Pi'lerdeki kod 22 TEMMUZ'DAN kalmaydi, yani 8 gun
# geride. Bunu ancak dosya dosya md5 karsilastirarak bulabildik cunku Pi'de
# "hangi surum yuklu" bilgisi HICBIR YERDE yoktu. Ayrica elle rsync/scp ile
# dagitmak sessiz kaymaya davetiye: bir dosya atlanirsa semptom cok sonra ve
# baska bir yerde cikiyor.
#
# Bu script uc seyi birlikte yapar ve ucu de gerekli:
#   1) kaynak senkronu (rsync --delete ile, artik dosya kalmasin)
#   2) konteynerde colcon build (install/ guncellenmezse kod DEGISMEZ)
#   3) ~/yelpence_ws/.surum dosyasina commit + tarih + kirli-mi bilgisi
#
# ADIM 3 OLMADAN ILK IKISI YETMEZ: "Pi'de ne var" sorusu tekrar olcum
# gerektirir. .surum dosyasi bunu tek komuta indiriyor.
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KURU="${KURU:-0}"

# Drone tablosu — docs/cihazlar.md ile ayni. IP'ler DHCP ile degisir, o yuzden
# once son bilinen IP denenir, cevap yoksa 22. port taramasiyla MAC'ten bulunur.
# Kullanici adlari drone basina AYRI (yelpence00 / yelpence02, duz "yelpence"
# degil) — karistirilirsa "Permission denied (publickey)" alinir ve anahtar
# sorunu sanilir.
declare -A KULLANICI=( [ylp00]="yelpence00" [ylp01]="yelpence01" [ylp02]="yelpence02" )
declare -A SON_IP=(    [ylp00]="10.158.16.134" [ylp01]="10.158.16.211" [ylp02]="10.158.16.189" )
declare -A KAP=(       [ylp00]="drone1" [ylp01]="drone2" [ylp02]="drone3" )
SUBNET="10.158.16"

# Pi'lere gidecek ROS paketleri. network_proxy ve sim_rtcm_source BILEREK YOK:
# ikisi de SIMULASYON bileseni. network_proxy sahada esp32_bridge'in yerini
# almaya calisir ve /swarm/public/* topic'lerine IKINCI bir yayinci sokar —
# teshisi cok zor bir cift-kaynak durumu olusur.
PAKETLER=(swarm_interfaces swarm_core swarm_control swarm_state_machine
          swarm_perception swarm_missions)

log()  { printf '   %s\n' "$*"; }
bas()  { printf '\n==== %s ====\n' "$*"; }

# IP cozumlemesinin TEK KAYNAGI: deploy/yki/drone_bul.sh
#
# 15 Agustos'ta bulundu: buradaki SON_IP tablosu ve SUBNET hala 10.158.16.x
# yaziyordu, sahadaki ag ise 10.188.209.x idi. Yani dagit.sh once olmayan bir
# adrese baglanmayi denyor, sonra YANLIS subnet'i 254 kez tariyor ve
# "ULASILAMADI" diyordu — kod dagitilmadigi halde uc dakika bekletiyordu.
#
# Adres tablosu iki yerde durdugu surece bu tekrar edecek (CLAUDE.md §9:
# "Ayni sabiti iki yere yazma"). drone_bul.sh onbellek -> mDNS -> MAC taramasi
# sirasiyla deniyor ve MAC degismedigi icin sonuncusu her agda calisiyor.
ip_bul() {
    local ad="$1"
    local bulucu="$REPO/deploy/yki/drone_bul.sh"
    local ip=""

    if [ -x "$bulucu" ]; then
        ip="$("$bulucu" --ip "$ad" 2>/dev/null | tr -d '[:space:]')"
        if [ -n "$ip" ]; then echo "$ip"; return 0; fi
    fi

    # Yedek: betik yoksa son bilinen adresi bir kere dene. Subnet taramasi
    # BILEREK kaldirildi — yanlis subnet'i taramak dakikalarca surup yine
    # bulamiyordu, drone_bul.sh bu isi zaten dogru yapiyor.
    ip="${SON_IP[$ad]:-}"
    if [ -n "$ip" ] && timeout 2 bash -c "echo > /dev/tcp/$ip/22" 2>/dev/null; then
        echo "$ip"; return 0
    fi
    return 1
}

dagit_bir() {
    local ad="$1"
    local kul="${KULLANICI[$ad]}" kap="${KAP[$ad]}"
    bas "$ad"

    local ip
    if ! ip="$(ip_bul "$ad")"; then
        log "ULASILAMADI (son bilinen ${SON_IP[$ad]}, subnet taramasi da bulamadi)"
        return 1
    fi
    log "IP: $ip"

    local hedef="/home/$kul/yelpence_ws"
    local surum
    surum="$(git -C "$REPO" rev-parse --short HEAD)"
    local dal
    dal="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
    local kirli=""
    if [ -n "$(git -C "$REPO" status --porcelain -- src deploy)" ]; then
        kirli=" +KIRLI"
        log "UYARI: calisma agaci kirli (src/ veya deploy/ commit edilmemis"
        log "       degisiklik iceriyor). .surum dosyasina +KIRLI yazilacak;"
        log "       yani Pi'deki kod hicbir commit'e birebir esit DEGIL."
    fi

    if [ "$KURU" = "1" ]; then
        log "[KURU] rsync edilecek paketler: ${PAKETLER[*]}"
        log "[KURU] $hedef/src/ altina, --delete ile"
        log "[KURU] sonra konteyner '$kap' icinde colcon build"
        log "[KURU] .surum -> $surum ($dal)$kirli"
        return 0
    fi

    # --- 1) kaynak senkronu ------------------------------------------------
    # --delete SART: silinen/tasinan dosya Pi'de kalirsa eski modul import
    # edilmeye devam eder ve "neden eski davraniyor" sorusu cikar.
    local p
    for p in "${PAKETLER[@]}"; do
        if [ ! -d "$REPO/src/$p" ]; then
            log "ATLANDI (repoda yok): $p"
            continue
        fi
        rsync -a --delete \
              --exclude='__pycache__' --exclude='*.pyc' \
              --exclude='.pytest_cache' \
              "$REPO/src/$p" "$kul@$ip:$hedef/src/" || {
            log "rsync BASARISIZ: $p"; return 1; }
    done
    log "kaynak senkronu tamam (${#PAKETLER[@]} paket)"

    # baslat.sh ve mesaj_hizlari.py ws kokunde duruyor (konteyner /ws goruyor)
    # run_drone.sh de gidiyor: 15 Agustos'ta goruldu ki Pi'de HIC YOKTU.
    # Yani konteyneri yaratma tarifi yalnizca dizustundeki repoda duruyordu —
    # sahada dizustu olmadan (ya da baska birinin bilgisayariyla) konteyner
    # yeniden yaratilamazdi. Konteyner bir kez yaratilip unutuldugu icin bu
    # aylarca fark edilmedi; --cap-add gibi bir ayar degisince ortaya cikti.
    rsync -a "$REPO/deploy/rpi/baslat.sh" "$REPO/deploy/rpi/mesaj_hizlari.py" \
          "$REPO/deploy/rpi/gps_saat.py" "$REPO/deploy/rpi/run_drone.sh" \
          "$kul@$ip:$hedef/" || { log "baslat.sh rsync BASARISIZ"; return 1; }
    log "baslat.sh + mesaj_hizlari.py + gps_saat.py + run_drone.sh tamam"

    # --- 2) konteynerde derleme -------------------------------------------
    # colcon build OLMADAN rsync HICBIR SEY yapmaz: dugumler install/ altindan
    # kosuyor, src/ yalnizca kaynak.
    log "colcon build (konteyner: $kap) — bir kac dakika surebilir..."
    if ! ssh -o ConnectTimeout=15 "$kul@$ip" \
        "docker exec $kap bash -lc '
            source /opt/ros/jazzy/setup.bash &&
            cd /ws &&
            colcon build --symlink-install --packages-select $(printf '%s ' "${PAKETLER[@]}") \
                2>&1 | tail -15
         '" ; then
        log "colcon build BASARISIZ"
        return 1
    fi

    # --- 3) surum kaydi ----------------------------------------------------
    ssh -o ConnectTimeout=10 "$kul@$ip" "cat > $hedef/.surum <<EOF
commit=$surum$kirli
dal=$dal
tarih=\$(date -Is)
dagitan=$(hostname)
paketler=${PAKETLER[*]}
EOF
"
    log "surum kaydi: $surum ($dal)$kirli -> $hedef/.surum"
    log "TAMAM. Konteyneri yeniden baslatmak icin:"
    log "    ssh $kul@$ip 'docker restart $kap'"
}

# ---------------------------------------------------------------------------
hedefler=("$@")
if [ ${#hedefler[@]} -eq 0 ]; then
    hedefler=(ylp00 ylp01 ylp02)
fi

basarili=0
basarisiz=0
for ad in "${hedefler[@]}"; do
    if [ -z "${KULLANICI[$ad]:-}" ]; then
        log "bilinmeyen drone: $ad (tablo: ${!KULLANICI[*]})"
        basarisiz=$((basarisiz + 1))
        continue
    fi
    if dagit_bir "$ad"; then
        basarili=$((basarili + 1))
    else
        basarisiz=$((basarisiz + 1))
    fi
done

bas "OZET"
log "basarili: $basarili   basarisiz: $basarisiz"
[ "$basarisiz" -gt 0 ] && exit 1
exit 0
