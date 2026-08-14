#!/bin/bash
# =============================================================================
# DRONE BUL — MAC'ten IP bulur ve SSH ile baglar
#
# NEDEN VAR: IP'ler her agda degisiyor. 29 Tem 10.207.118.x, 30 Tem
# 10.158.16.x, 14 Agu 10.188.209.x — her seferinde butun SSH komutlari
# kirildi. DEGISMEYEN TEK SEY MAC ADRESIDIR.
#
# Bu betik agi tarar, bulunan MAC'leri asagidaki tabloyla eslestirir ve
# hangi IP'nin hangi drone oldugunu SOYLER. Tahmin yok.
#
# KULLANIM
#   ./drone_bul.sh                 menu acar, sec, baglanir
#   ./drone_bul.sh ylp00           dogrudan baglanir
#   ./drone_bul.sh ylp00 'komut'   komutu calistirir, ciktisini basar
#   ./drone_bul.sh --liste         tabloyu basar, baglanmaz  (Claude icin)
#   ./drone_bul.sh --ip ylp00      yalniz IP'yi basar        (betikler icin)
#   ./drone_bul.sh --durum         hepsinin durumunu gosterir
#   ./drone_bul.sh --yenile        onbellegi atlayip yeniden tarar
#
# NASIL BULUYOR (sirayla, ilk tutan kazanir)
#   1. onbellek   — son basarili tarama (~/.cache/yelpence/droneler)
#   2. mDNS       — ylp00.local  (hotspot multicast'i engellemiyorsa)
#   3. MAC tarama — /24 boyunca 22. porta bak, ARP tablosundan MAC oku
#
# 3. yontem her zaman calisir ve internet gerektirmez; digerleri yalnizca
# hizlandirmak icin. Onbellek yanlissa (drone yer degistirmis) dogrulama
# adimi yakalar ve otomatik yeniden tarar.
# =============================================================================
set -uo pipefail

# --- DRONE TABLOSU -----------------------------------------------------------
# MAC'ler docs/cihazlar.md'den. wlan0 arayuzunun MAC'i.
#
# DIKKAT: kullanici adi drone basina AYRI (hepsi 'yelpence' degil). Yanlis
# kullanici -> "Permission denied (publickey,password)" ve insan bunu anahtar
# sorunu saniyor. Once kullanici adini dogrula.
#
# DIKKAT 2: isim ile numara AYNI DEGIL. ylp00 -> drone1, ylp02 -> drone3.
#
#          isim   MAC (wlan0)          kullanici     konteyner  agent_id
DRONELAR=(
    "ylp00  88:a2:9e:71:60:ed  yelpence00  drone1  1"
    "ylp01  88:a2:9e:da:04:2d  yelpence01  drone2  2"
    "ylp02  88:a2:9e:71:60:24  yelpence02  drone3  3"
)

ONBELLEK_DIZIN="${XDG_CACHE_HOME:-$HOME/.cache}/yelpence"
ONBELLEK="$ONBELLEK_DIZIN/droneler"
# Onbellek bu sureden eskiyse dogrudan yeniden taranir. 12 saat: bir calisma
# gunu boyunca ag genelde degismiyor, ertesi gun degismis olma ihtimali yuksek.
ONBELLEK_OMRU_SN=43200

K_KIRMIZI=$'\033[31m'; K_YESIL=$'\033[32m'; K_SARI=$'\033[33m'
K_MAVI=$'\033[36m';    K_KALIN=$'\033[1m';  K_SIFIR=$'\033[0m'
if [ ! -t 1 ]; then K_KIRMIZI=""; K_YESIL=""; K_SARI=""; K_MAVI=""; K_KALIN=""; K_SIFIR=""; fi

bilgi() { printf '%s\n' "$*" >&2; }

# --- Yardimcilar -------------------------------------------------------------

alan_al() { echo "$1" | awk -v n="$2" '{print $n}'; }

drone_satiri() {
    local isim="$1" satir
    for satir in "${DRONELAR[@]}"; do
        [ "$(alan_al "$satir" 1)" = "$isim" ] && { echo "$satir"; return 0; }
    done
    return 1
}

# Yerel /24 agini varsayilan rotadan turetir. Birden fazla arayuz varsa
# varsayilan rotayi tasiyani seceriz — drone'lar oradan erisilir.
ag_oneki() {
    ip -4 route get 1.1.1.1 2>/dev/null \
        | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}' \
        | awk -F. '{print $1"."$2"."$3}'
}

ssh_acik_mi() {
    timeout "${2:-2}" bash -c "echo > /dev/tcp/$1/22" 2>/dev/null
}

# --- Bulma yontemleri --------------------------------------------------------

# 1) mDNS. Hotspot multicast'i engelliyorsa sessizce basarisiz olur.
mdns_ile() {
    local ip
    ip=$(getent hosts "$1.local" 2>/dev/null | awk '{print $1; exit}')
    [ -n "$ip" ] && ssh_acik_mi "$ip" 2 && { echo "$ip"; return 0; }
    return 1
}

# 2) MAC tarama. HER ZAMAN CALISAN yontem.
#
# 22. porta TCP baglantisi denenir. Iki isi birden yapar: ARP tablosunu
# doldurur (MAC'i ordan okuyacagiz) ve SSH'in gercekten acik oldugunu
# dogrular. Salt ping yetmezdi — ping'e cevap verip SSH'i kapali olan
# cihazlar listeye girerdi.
mac_tarama() {
    local onek; onek=$(ag_oneki)
    if [ -z "$onek" ]; then
        bilgi "${K_KIRMIZI}HATA:${K_SIFIR} yerel ag bulunamadi (agda misin?)"
        return 1
    fi
    bilgi "${K_MAVI}...${K_SIFIR} $onek.0/24 taraniyor (MAC eslestirme)"

    local i
    for i in $(seq 1 254); do
        ( ssh_acik_mi "$onek.$i" 1 && echo "$onek.$i" ) &
    done > /tmp/.yelpence_tarama_$$ 2>/dev/null
    wait

    # ARP tablosu: IP -> MAC. Taramadan hemen sonra okunmali, girdiler eskir.
    local arp; arp=$(ip -4 neigh show 2>/dev/null)

    local satir isim mac ip bulunan=""
    for satir in "${DRONELAR[@]}"; do
        isim=$(alan_al "$satir" 1)
        mac=$(alan_al "$satir" 2 | tr 'A-Z' 'a-z')
        ip=$(echo "$arp" | grep -i " $mac " | awk '{print $1; exit}')
        [ -n "$ip" ] && bulunan+="$isim $ip"$'\n'
    done
    rm -f /tmp/.yelpence_tarama_$$

    [ -n "$bulunan" ] || return 1
    printf '%s' "$bulunan"
}

# --- Onbellek ----------------------------------------------------------------

onbellek_yaz() {
    mkdir -p "$ONBELLEK_DIZIN"
    printf '%s' "$1" > "$ONBELLEK"
}

onbellek_oku() {
    [ -f "$ONBELLEK" ] || return 1
    local yas=$(( $(date +%s) - $(stat -c %Y "$ONBELLEK" 2>/dev/null || echo 0) ))
    [ "$yas" -lt "$ONBELLEK_OMRU_SN" ] || return 1
    cat "$ONBELLEK"
}

# --- Ana bulma ---------------------------------------------------------------
# Cikti: "isim ip" satirlari.
bul() {
    local zorla="${1:-hayir}" onbellekli gecerli="" satir isim ip

    if [ "$zorla" = "hayir" ] && onbellekli=$(onbellek_oku); then
        # ONBELLEGE KORU KORUNE GUVENILMEZ. Drone yer degistirmis ya da ag
        # kaymis olabilir; o IP'de baska bir cihaz oturuyor olabilir.
        # Dogrulama: SSH portu hala acik mi?
        while read -r isim ip; do
            [ -n "$ip" ] && ssh_acik_mi "$ip" 2 && gecerli+="$isim $ip"$'\n'
        done <<< "$onbellekli"
        if [ -n "$gecerli" ]; then
            printf '%s' "$gecerli"; return 0
        fi
        bilgi "${K_SARI}...${K_SIFIR} onbellek eskimis, yeniden taraniyor"
    fi

    # mDNS: hizli ve tarama gerektirmiyor. Calisirsa 254 baglanti denemesinden
    # kurtuluruz.
    for satir in "${DRONELAR[@]}"; do
        isim=$(alan_al "$satir" 1)
        ip=$(mdns_ile "$isim") && gecerli+="$isim $ip"$'\n'
    done
    if [ -n "$gecerli" ]; then
        bilgi "${K_YESIL}mDNS${K_SIFIR} ile bulundu"
        onbellek_yaz "$gecerli"; printf '%s' "$gecerli"; return 0
    fi

    gecerli=$(mac_tarama) || return 1
    onbellek_yaz "$gecerli"; printf '%s' "$gecerli"
}

ip_bul() {
    local isim="$1" liste
    liste=$(bul "${2:-hayir}") || return 1
    echo "$liste" | awk -v n="$isim" '$1==n {print $2; exit}'
}

# --- Ciktilar ----------------------------------------------------------------

tablo_yaz() {
    local liste="$1" satir isim ip kul kon aid
    printf '\n%s%-7s %-16s %-12s %-9s %-4s %s%s\n' \
        "$K_KALIN" "DRONE" "IP" "KULLANICI" "KONTEYNER" "ID" "DURUM" "$K_SIFIR"
    for satir in "${DRONELAR[@]}"; do
        isim=$(alan_al "$satir" 1); kul=$(alan_al "$satir" 3)
        kon=$(alan_al "$satir" 4);  aid=$(alan_al "$satir" 5)
        ip=$(echo "$liste" | awk -v n="$isim" '$1==n {print $2; exit}')
        if [ -n "$ip" ]; then
            printf '%-7s %-16s %-12s %-9s %-4s %sAGDA%s\n' \
                "$isim" "$ip" "$kul" "$kon" "$aid" "$K_YESIL" "$K_SIFIR"
        else
            printf '%-7s %-16s %-12s %-9s %-4s %syok%s\n' \
                "$isim" "-" "$kul" "$kon" "$aid" "$K_KIRMIZI" "$K_SIFIR"
        fi
    done
    echo
}

durum_yaz() {
    local liste; liste=$(bul "hayir") || { bilgi "hicbir drone bulunamadi"; return 1; }
    tablo_yaz "$liste"
    local satir isim ip kul kon
    for satir in "${DRONELAR[@]}"; do
        isim=$(alan_al "$satir" 1); kul=$(alan_al "$satir" 3); kon=$(alan_al "$satir" 4)
        ip=$(echo "$liste" | awk -v n="$isim" '$1==n {print $2; exit}')
        [ -n "$ip" ] || continue
        printf '%s%s%s (%s)\n' "$K_KALIN" "$isim" "$K_SIFIR" "$ip"
        timeout 20 ssh -o ConnectTimeout=6 -o BatchMode=yes "$kul@$ip" \
            "printf '  calisma suresi : '; uptime -p 2>/dev/null || uptime
             printf '  konteyner      : '; docker ps --filter name=$kon --format '{{.Names}} {{.Status}}' 2>/dev/null | head -1
             printf '  bayraklar      : '
             for f in kacinma gcs_url tgt_system suru_dugumleri ucus_ayarlari.env; do
                 [ -e \"\$HOME/yelpence_ws/\$f\" ] && printf '%s ' \"\$f\"
             done; echo
             printf '  disk /         : '; df -h / | awk 'NR==2{print \$4\" bos (\"\$5\" dolu)\"}'" \
            2>&1 | sed 's/^/  /' || echo "  ${K_SARI}(SSH cevap vermedi — anahtar yok olabilir)${K_SIFIR}"
        echo
    done
}

menu() {
    local liste; liste=$(bul "hayir") || { bilgi "${K_KIRMIZI}Hicbir drone bulunamadi.${K_SIFIR} Ayni agda misin?"; return 1; }
    tablo_yaz "$liste"

    local secenekler=() satir isim ip
    for satir in "${DRONELAR[@]}"; do
        isim=$(alan_al "$satir" 1)
        ip=$(echo "$liste" | awk -v n="$isim" '$1==n {print $2; exit}')
        [ -n "$ip" ] && secenekler+=("$isim")
    done
    if [ ${#secenekler[@]} -eq 0 ]; then
        bilgi "${K_KIRMIZI}Agda hicbir drone yok.${K_SIFIR}"; return 1
    fi

    local i=1 s
    for s in "${secenekler[@]}"; do echo "  $i) $s"; i=$((i+1)); done
    echo "  q) cikis"
    echo
    read -rp "Hangisine baglanmak istiyorsun? " sec
    [ "$sec" = "q" ] && return 0
    if ! [[ "$sec" =~ ^[0-9]+$ ]] || [ "$sec" -lt 1 ] || [ "$sec" -gt ${#secenekler[@]} ]; then
        bilgi "${K_KIRMIZI}Gecersiz secim.${K_SIFIR}"; return 1
    fi
    baglan "${secenekler[$((sec-1))]}"
}

baglan() {
    local isim="$1"; shift
    local satir; satir=$(drone_satiri "$isim") || {
        bilgi "${K_KIRMIZI}Bilinmeyen drone:${K_SIFIR} $isim  (ylp00 / ylp01 / ylp02)"; return 1; }
    local kul; kul=$(alan_al "$satir" 3)
    local ip;  ip=$(ip_bul "$isim") || { bilgi "${K_KIRMIZI}$isim agda bulunamadi.${K_SIFIR}"; return 1; }

    if [ $# -gt 0 ]; then
        # Komut kipi — Claude ve betikler icin. Ciktisi temiz kalsin diye
        # bilgi satirlari stderr'e gidiyor (yukaridaki bilgi()).
        exec ssh -o ConnectTimeout=10 "$kul@$ip" "$@"
    fi
    bilgi "${K_YESIL}->${K_SIFIR} $isim  $kul@$ip"
    exec ssh -o ConnectTimeout=10 "$kul@$ip"
}

kullanim() {
    sed -n '/^# KULLANIM/,/^# NASIL/p' "$0" | sed 's/^# \{0,1\}//; $d'
}

# --- Giris -------------------------------------------------------------------
case "${1:-}" in
    ""|-i|--menu)   menu ;;
    -h|--help|yardim) kullanim ;;
    --liste)        liste=$(bul "hayir") && tablo_yaz "$liste" || exit 1 ;;
    # MAKINE OKUNUR TABLO — baska betikler drone bilgisini BURADAN alsin.
    # Kendi tablosunu tutan ikinci bir betik yazma: 2 Agustos'ta filo
    # varsayilani hem backend hem frontend'de duruyordu, biri guncellenip
    # digeri unutuldu ve dusmus drone'a komut gitti. Tek kaynak burasi.
    # Cikti: isim<TAB>ip<TAB>kullanici<TAB>konteyner<TAB>agent_id
    --tablo)        liste=$(bul "hayir") || exit 1
                    for s in "${DRONELAR[@]}"; do
                        i=$(alan_al "$s" 1)
                        p=$(echo "$liste" | awk -v n="$i" '$1==n {print $2; exit}')
                        [ -n "$p" ] || continue
                        printf '%s\t%s\t%s\t%s\t%s\n' "$i" "$p" \
                            "$(alan_al "$s" 3)" "$(alan_al "$s" 4)" "$(alan_al "$s" 5)"
                    done ;;
    --durum)        durum_yaz ;;
    --yenile)       liste=$(bul "evet") && tablo_yaz "$liste" || exit 1 ;;
    --ip)           [ -n "${2:-}" ] || { bilgi "kullanim: $0 --ip ylp00"; exit 1; }
                    ip_bul "$2" || exit 1 ;;
    ylp*)           baglan "$@" ;;
    *)              bilgi "${K_KIRMIZI}Bilinmeyen secenek:${K_SIFIR} $1"; kullanim; exit 1 ;;
esac
