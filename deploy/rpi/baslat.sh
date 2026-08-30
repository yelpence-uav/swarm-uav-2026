#!/bin/bash
# Drone tarafi tam zincir: Pixhawk -> MAVROS -> px4_bridge -> agent_fsm -> esp32_bridge -> mesh
# AGENT_ID env ile parametrik (verilmezse 1 = eski ylp00 davranisi). ns=/drone_${AGENT_ID}.
# Konteynere run_drone.sh ile -e AGENT_ID=<N> gecilir. Drone'da /ws/baslat.sh olarak durur.
AGENT_ID="${AGENT_ID:-1}"
echo "[baslat] AGENT_ID=$AGENT_ID"

# --- --yalniz <dugum>: TEK DUGUMU yeniden baslat (29 Agustos 2026) ----------
#
# NEDEN VAR: bir Python satiri degistiginde tam `docker restart` gerekiyordu.
# Olculen maliyet ~50 sn sabit sleep (2 + 15 mavros + 5 + 5 + 2 + ~20 dugum)
# + MAVROS el sikismasi + PX4 + RTK yeniden kilit + consensus yeniden secim.
# Oysa degisen sey `formation_node` ise mavros'un kalkmasina GEREK YOK.
#
#   docker exec -d drone1 /ws/baslat.sh --yalniz formasyon
#
# NE YAPAR : yalniz o anahtarin dugumlerini oldurur ve yeniden baslatir.
# NE YAPMAZ: mavros, px4_bridge, agent_fsm, esp32_bridge, ucus kaydi ve
#            gunluk bekcisine DOKUNMAZ; yeni gunluk dizini ACMAZ (mevcut
#            `son` dizinine yazar, boylece acilis loglari donmez).
#
# 🔴 UCUS SIRASINDA KULLANMA. Dugum saniyelerce yok olur; kacinma ya da
#    formasyon o pencerede sessizce devre disi kalir.
#
# ⚠️ Gating degiskenleri (SP_REMAP, VELOCITY_ONLY, bos yuva kapisi) normal
#    aciliskaki gibi /ws/suru_dugumleri'nden hesaplanir — yani `acik`
#    DEGISMEZ, yalniz BASLATMA kapisi (`baslat_mi`) daralir. Aksi halde
#    --yalniz formasyon derken CA kapali sanilir ve gozlem modu zorlanirdi.
YALNIZ=""
while [ $# -gt 0 ]; do
    case "$1" in
        --yalniz) YALNIZ="${2:-}"; shift 2 ;;
        --yalniz=*) YALNIZ="${1#*=}"; shift ;;
        *) shift ;;
    esac
done

altyapi() { [ -z "$YALNIZ" ]; }

# baslat_mi: `acik` (yapilandirma) VE (yalniz modu yoksa ya da hedef bu ise)
baslat_mi() {
    acik "$1" || return 1
    [ -z "$YALNIZ" ] || [ "$YALNIZ" = "$1" ]
}

# Anahtar -> yurutulebilir adlari. `--yalniz` oldurmek icin kullanir.
_dugum_exe() {
    case "$1" in
        origin)    echo "swarm_origin_publisher" ;;
        consensus) echo "consensus_node" ;;
        formasyon) echo "formation_node path_planner" ;;
        sekans)    echo "formasyon_sekans" ;;
        ca)        echo "collision_avoidance" ;;
        manevra)   echo "maneuver_executor" ;;
        fsm)       echo "swarm_fsm_node" ;;
        gorevfsm)  echo "mission_fsm_node" ;;
        mod)       echo "mode_manager_node" ;;
        joystick)  echo "joystick_interpreter_node rc_ibus_kopru" ;;
        gorev1)    echo "mission1_node" ;;
        goru)      echo "camera_driver vision_node" ;;
        inis)      echo "precision_landing_node" ;;
        rol)       echo "task_reallocator_node" ;;
        *)         echo "" ;;
    esac
}

# `ros2 run` bir SARMALAYICI: gercek dugum ayri bir surec ve sarmalayiciyi
# oldurmek cocugu OKSUZ birakiyor (TUZAKLAR §1.24 — 23 Agustos'ta ylp02'de
# uc artik dugum bulundu). Bu yuzden once gercek surec, sonra sarmalayici.
#
# 🔴 `pkill -f` KULLANILMIYOR: desen KOMUT SATIRINA bakiyor ve cagiran kabugun
# kendi komut satiri deseni icerirse pkill ONU DA olduruyor (29 Agustos'ta
# masada yasandi — test kabugu kendini kesti). Onun yerine pgrep + kendi
# PID'lerini eleyerek kill.
_dugum_oldur() {
    local exe pid kalan
    for exe in $1; do
        for pid in $(pgrep -f "install/[^ ]*/${exe}\b" 2>/dev/null) \
                   $(pgrep -f "ros2 run [^ ]* ${exe}\b" 2>/dev/null); do
            [ "$pid" = "$$" ] && continue
            [ "$pid" = "$PPID" ] && continue
            kill "$pid" 2>/dev/null
        done
    done
    sleep 1
    for exe in $1; do
        kalan=""
        for pid in $(pgrep -f "install/[^ ]*/${exe}\b" 2>/dev/null); do
            [ "$pid" = "$$" ] && continue
            [ "$pid" = "$PPID" ] && continue
            kill -9 "$pid" 2>/dev/null; kalan="$kalan $pid"
        done
        [ -n "$kalan" ] && echo "[baslat]   $exe TERM ile inmedi, KILL gonderildi:$kalan"
    done
    return 0
}

# TRAMPLEN — dugum, cagiran oturumdan KOPARILIR.
# `docker exec ... /ws/baslat.sh --yalniz ca` ile cagrildiginda exec oturumu
# kapaninca arka plandaki dugum SIGHUP alabilir. setsid ile yeni bir oturum
# acilir; boylece `-d` bayragi unutulsa da dugum yasamaya devam eder.
# Cikti bir dosyaya alinip geri basiliyor — cagiran yine de ne oldugunu gorur.
if [ -n "$YALNIZ" ] && [ -z "${YELPENCE_YALNIZ_KOPUK:-}" ] \
   && command -v setsid >/dev/null 2>&1; then
    export YELPENCE_YALNIZ_KOPUK=1
    _cik="/tmp/yalniz_${YALNIZ}.log"
    # `bash "$0"` SART: baslat.sh 644 (calistirilabilir DEGIL) ve konteyner
    # CMD'si de `bash /ws/baslat.sh`. setsid "$0" dogrudan calistirmaya
    # kalkar ve "permission denied" alir (29 Agustos'ta sahada yasandi).
    setsid bash "$0" --yalniz "$YALNIZ" > "$_cik" 2>&1 &
    sleep 5
    cat "$_cik"
    exit 0
fi

source /opt/ros/jazzy/setup.bash && source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1  # saha: DDS loopback-only, dis ag bagimsiz

# --- Dugum ciktilari nereye yazilir ------------------------------------------
# Onceden hepsi '> /tmp/X.log' idi ve '>' her aciliste dosyayi TRUNCATE
# ediyordu: bir dugum cokup yigin yeniden basladiginda cokme mesaji
# kayboluyordu. Sistem gunlugu journald'da, telemetri ros2 bag'de duruyordu
# ama "hangi dugum neden oldu" sorusunun cevabi hicbir yerde kalmiyordu.
#
# Artik /ws/gunluk/<damga>/ altina yaziliyor. Uc kazanc:
#   - /ws host'ta ~/yelpence_ws demek — konteyner silinip yeniden kurulsa kalir
#   - host'tan 'docker exec' olmadan okunur
#   - klasor adi Istanbul damgali, journald ile ayni saatte hizalanir
# TZ burada set ediliyor cunku damga hemen asagida kullaniliyor: konteyner
# UTC'de calisir, host Europe/Istanbul'da; verilmezse gunlukler sistem
# gunlukleriyle 3 saat kayar (tzdata konteynerde mevcut, dogrulandi).
# En yeni 5 acilis tutulur. ONCE 10 IDI ve "dosyalar kucuk, ayri disk tavani
# gerekmiyor" yaziyordu — YANLISTI, 14 Agustos'ta iki dronun da diski
# %100 doldu. Bkz. asagidaki gunluk bekcisi.
# Budama -type d ile yapiliyor, boylece asagidaki 'son' sembolik bagi
# hedefiyle birlikte silinmiyor.
export TZ=Europe/Istanbul
if [ -n "$YALNIZ" ] && [ -d /ws/gunluk/son ]; then
    # --yalniz: YENI acilis dizini ACMA. Aksi halde her tek-dugum yeniden
    # baslatmasi bir dizin uretir ve asagidaki budama (en yeni 5) gercek
    # acilis loglarini birkac denemede silip supururdu.
    GUNLUK="$(cd /ws/gunluk/son && pwd -P)"
else
    GUNLUK="/ws/gunluk/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$GUNLUK"
    find /ws/gunluk -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | tail -n +6 | cut -d' ' -f2- | xargs -r rm -rf
fi
# Bag GORELI olmak zorunda: mutlak verilirse '/ws/gunluk/<damga>'i gosterir ve
# host'ta /ws diye bir yol olmadigi icin ~/yelpence_ws/gunluk/son KIRIK cikar
# (olculdu). Sadece dizin adi verilince iki taraftan da cozuluyor.
altyapi && ln -sfn "$(basename "$GUNLUK")" /ws/gunluk/son   # ~/yelpence_ws/gunluk/son/mavros.log
echo "[baslat] gunlukler: $GUNLUK"

# --- GUNLUK BOYUT BEKCISI ---------------------------------------------------
# 14 AGUSTOS: IKI DRONUN DA DISKI %100 DOLDU. Olculdu:
#   ylp00  gunluk/ 19 GB   (mavros.log tek basina 18.64 GB)
#   ylp02  gunluk/ 22 GB   (mavros.log tek basina 21.57 GB)
# Ucus kayitlari (kayit/) sucsuzdu: 4.6 ve 3.0 GB. Disk dolunca 'ros2 bag'
# yazamaz — yani BIR SONRAKI UCUS KAYDEDILMEZ. 2 Agustos kazasini cozen sey
# o kayitti.
#
# KOK NEDEN — bir tek satir:
#     Warning: mavconn: udp1: sendto: Network is unreachable, retrying
# 200 bin satirlik ornekte 99.760 tanesi buydu, yani logun YARISI. 'udp1',
# GCS_URL ile QGC'ye MAVLink ileten ucnokta. WiFi dustugunde MAVROS her
# MAVLink mesaji icin bir uyari basiyor; yayin hizlari 20 Hz oldugu icin
# saniyede yuzlerce satir, saatte GB'lar. Yani patlama sahada WiFi
# kopmasiyla birebir ortusuyor. Bu satirlar ROS logger'indan degil mavconn
# kutuphanesinin kendi stderr'inden geliyor, --log-level ile susmuyor.
#
# COZUM: dosyayi kirp, SONUNU koru. Son taraf onemli olan taraf — hata
# aninda ne oldugunu o anlatir.
#
# NEDEN YUKARIDAKI BUTUN YONLENDIRMELER '>>' : bash '>' dosyayi O_APPEND
# OLMADAN aciyor. Oyle bir dosyayi kirparsak yazan surec kendi eski
# ofsetinden yazmaya devam eder ve SEYREK (sparse) dosya olusur — 'ls' buyuk
# gorunur, 'du' kucuk, ve kimse ne oldugunu anlamaz. '>>' ile O_APPEND set
# edilir; kirptiktan sonra bir sonraki yazma yeni EOF'a gider. Dogru davranis
# bu tek karaktere bagli, degistirme.
# TAVAN NEDEN 500 MB (once 100 idi):
#
# Normal isleyiste log KB mertebesinde — saglikli bir aciliste mavros.log
# 37 KB olculdu. Yani tavan YALNIZCA patlama aninda devreye giriyor.
# Patlamada ~25 MB/dk yaziliyor; 25 MB korumak elde ~1 DAKIKALIK gecmis
# birakiyordu ve kirpmadan 3 dk once olan bir arizanin kaniti gidiyordu.
#
# KORUNAN ORANI %25'TE TUTULUYOR, bu bilincli: kirpma her seferinde korunan
# kadar okuyup yaziyor, yani I/O yuku korunan/(tavan-korunan) oraniyla
# belirleniyor. 125/500 ile 25/100 AYNI I/O yukunu veriyor (8.3 MB/dk) ama
# bes kat gecmis birakiyor. 250/500 secseydik yuk uc katina cikardi.
#
# Disk tarafi rahat: 5 acilis x 500 MB = 2.5 GB, diskte 19-21 GB bos.
GUNLUK_TAVAN_MB="${GUNLUK_TAVAN_MB:-500}"
GUNLUK_KORUNAN_MB="${GUNLUK_KORUNAN_MB:-125}"
# DIZIN GENELI TAVAN — dosya basina tavan TEK BASINA YETMEZ.
#
# Su an buyuyen tek dosya mavros.log. Ama SURU DUGUMLERI acilinca 14 log
# daha olacak (formation, collision_avoidance, mission1, vision...) ve
# herhangi biri spam yapabilir. O zaman en kotu hal:
#     14 dosya x 500 MB x 5 acilis = 35 GB   ->  disk YINE dolar
# Bu yuzden ikinci bir kapi: dizin bu tavani asarsa EN ESKI acilis dizinleri
# silinir (en yeni ikisi her zaman korunur — biri calisan, biri onceki).
GUNLUK_DIZIN_TAVAN_MB="${GUNLUK_DIZIN_TAVAN_MB:-3000}"
gunluk_bekcisi() {
    local tavan=$((GUNLUK_TAVAN_MB * 1024 * 1024))
    local korunan=$((GUNLUK_KORUNAN_MB * 1024 * 1024))
    local f boyut dizin_mb eskiler
    while true; do
        sleep 60

        # 1) DIZIN GENELI: tavani asiyorsa en eski acilislari at.
        dizin_mb=$(du -sm /ws/gunluk 2>/dev/null | cut -f1)
        if [ -n "$dizin_mb" ] && [ "$dizin_mb" -gt "$GUNLUK_DIZIN_TAVAN_MB" ]; then
            # En yeni IKI dizin her zaman kalir; gerisi en eskiden silinir.
            eskiler=$(find /ws/gunluk -maxdepth 1 -mindepth 1 -type d \
                        -printf '%T@ %p\n' 2>/dev/null \
                      | sort -rn | tail -n +3 | cut -d' ' -f2-)
            if [ -n "$eskiler" ]; then
                echo "$eskiler" | xargs -r rm -rf
                echo "[$(date +%H:%M:%S)] dizin ${dizin_mb} MB > ${GUNLUK_DIZIN_TAVAN_MB} MB" \
                     "-> eski acilislar silindi, kalan $(du -sm /ws/gunluk | cut -f1) MB" \
                     >> "$GUNLUK/bekci.log"
            fi
        fi

        # 2) DOSYA BASINA: tavani asani kirp, SONUNU koru.
        for f in "$GUNLUK"/*.log; do
            [ -f "$f" ] || continue
            case "$f" in *bekci.log) continue ;; esac
            boyut=$(stat -c %s "$f" 2>/dev/null) || continue
            [ "$boyut" -gt "$tavan" ] || continue
            # tail -> gecici -> cp: cp AYNI inode'a yazar, dosya kuculur,
            # yazan surec O_APPEND sayesinde yeni sonundan devam eder.
            tail -c "$korunan" "$f" > "$f.kirp" 2>/dev/null || continue
            cp "$f.kirp" "$f" 2>/dev/null
            rm -f "$f.kirp"
            # BU SATIR BIR SINYALDIR, gurultu degil: kirpma olduysa o dugum
            # saniyede yuzlerce satir basiyor demektir. Sik kirpma = arayacagin
            # arizanin kendisi. Zaman damgasi hangi ucus anina denk geldigini
            # soyler.
            echo "[$(date +%H:%M:%S)] $(basename "$f") ${GUNLUK_TAVAN_MB}MB asti -> son ${GUNLUK_KORUNAN_MB}MB korundu" \
                >> "$GUNLUK/bekci.log"
        done
    done
}
if altyapi; then   # --yalniz modunda ATLANIR  (gunluk bekcisi)
gunluk_bekcisi &
fi   # /altyapi: gunluk bekcisi
echo "[baslat] gunluk bekcisi: dosya ${GUNLUK_TAVAN_MB} MB (son ${GUNLUK_KORUNAN_MB} MB korunur)," \
     "dizin ${GUNLUK_DIZIN_TAVAN_MB} MB"

# GCS_URL: MAVROS'un MAVLink'i AYNEN ilettigi ikinci ucnokta (QGroundControl).
# NEDEN VAR: kanit videosu yonergesi "ucus modunun ve yonelimlerin acikca
# gorundugu Mission Planner veya QGroundControl ekran goruntusu" istiyor.
# Telemetri normalde ESP mesh'ten YKI'ye gidiyor ama mesh 16 baytlik ozet
# tasiyor — QGC'nin HUD'u icin tam MAVLink akisi gerekir. Bos birakilirsa
# eski davranis aynen korunur (hicbir yere iletmez).
#   ornek: GCS_URL=udp://@10.158.16.115:14550
#
# Env DISINDA /ws/gcs_url dosyasindan da okunur. Sebep pratik: konteynerler
# 'docker run -e AGENT_ID=N' ile yaratildi ve env eklemek konteyneri YENIDEN
# YARATMAK demek — sahada gereksiz risk. Dosya birakip 'docker restart' yeter.
GCS_URL="${GCS_URL:-}"
if [ -z "$GCS_URL" ] && [ -f /ws/gcs_url ]; then
    GCS_URL="$(tr -d '[:space:]' < /ws/gcs_url)"
fi
# TGT_SYSTEM: MAVROS'un konusacagi PX4 sistem kimligi.
#
# Varsayilan 1'dir ve cogu PX4'umuz fabrika ayari MAV_SYS_ID=1 ile geliyor.
# AMA ylp02'nin FCU'su 31 Temmuz'da 3'e gecti: MAV_SYS_ID=3 yazilmisti,
# PX4 bu parametreyi ancak YENIDEN BASLATMADA uyguluyor, ve FCU o gun
# yeniden basladi. MAVROS 1'i hedeflemeye devam edince FCU ile hic
# konusamadi — dugumler ayakta, port acik, ama 'connected: false' ve
# YKI'de butun alanlar sifir. Teshisi zor bir hal; ipucu mavros.log'daki
# 'detected remote address 3.125' satiri (saglamda '1.1' olur).
#
# Bu yuzden AGENT_ID'den TUREMEZ — o, FCU'su hala 1 olan drone'lari bozar.
# /ws/tgt_system dosyasindan okunur; yoksa MAVROS varsayilani kullanilir.
TGT_SYSTEM=""
if [ -f /ws/tgt_system ]; then
    TGT_SYSTEM="$(tr -d '[:space:]' < /ws/tgt_system)"
    echo "[baslat] MAVROS tgt_system=$TGT_SYSTEM (PX4 MAV_SYS_ID ile ayni olmali)"
fi
# Suanki durum: ylp00 -> dosya YOK (FCU sysid 1, MAVROS varsayilani 1)
#               ylp02 -> /ws/tgt_system = 3 (FCU sysid 3)
if altyapi; then   # --yalniz modunda ATLANIR  (ag beklemesi + mavros + GCS denetimi + gps_saat)
# --- AG HAZIR MI? (20 Agustos 2026, P0.13) ----------------------------------
# OLCULDU (ylp00, 20 Agustos):
#     Pi acilis          15:51
#     konteyner + mavros 15:52:41
#     wlan0 DHCP kirasi  15:56:32   <- DORT DAKIKA SONRA
# Konteyner `--restart unless-stopped` ile Pi acilir acilmaz kalkiyor ve
# mavros'un gcs_url ucnoktasi ag yokken kuruluyor. Belirtisi mavros.log'daki
# 'removed stale remote address' ve QGC'nin hic baglanmamasi (P1.5).
#
# UCUS BUNA BAGLI DEGIL: mesh seri hat uzerinden, WiFi'siz calisiyor. Bu
# yuzden ag gelmezse BEKLEMEYE DEVAM ETMEYIZ — uyarip gecicez. Bekleme
# yalnizca "birazdan gelecek" durumunu kurtarmak icin.
#
# NOT: konteynerde `ip` komutu YOK (olculdu), `hostname -I` var. Docker
# koprusu (172.17.x) ve loopback disariliyor; saha aglari bugune kadar
# 10.x / 172.19.x / 192.168.x oldu.
AG_BEKLE_SN="${AG_BEKLE_SN:-30}"
_ag_var() {
    for a in $(hostname -I 2>/dev/null); do
        case "$a" in
            127.*|172.17.*) continue ;;
            *.*.*.*) return 0 ;;
        esac
    done
    return 1
}
_bekledi=0
while [ "$_bekledi" -lt "$AG_BEKLE_SN" ]; do
    _ag_var && break
    [ "$_bekledi" = 0 ] && echo "[baslat] ag henuz yok, en fazla ${AG_BEKLE_SN} sn bekleniyor..."
    sleep 2
    _bekledi=$((_bekledi + 2))
done
if _ag_var; then
    [ "$_bekledi" -gt 0 ] && echo "[baslat] ag geldi (${_bekledi} sn sonra): $(hostname -I)"
else
    echo "[baslat] UYARI: ${AG_BEKLE_SN} sn'de ag gelmedi — DEVAM EDILIYOR."
    echo "[baslat]        Mesh ve ucus WiFi'ye bagli DEGIL; yalniz QGC/SSH etkilenir."
fi

# Fonksiyon: ayni komut hem ilk aciliste hem onarim denemesinde kullanilsin.
# Iki yere kopyalanirsa biri guncellenip digeri unutulur (bu depoda yasandi).
_mavros_baslat() {
    ros2 run mavros mavros_node --ros-args -r __ns:=/drone_${AGENT_ID}/mavros \
        -p fcu_url:=/dev/ttyAMA0:921600 \
        ${TGT_SYSTEM:+-p tgt_system:=$TGT_SYSTEM} \
        ${GCS_URL:+-p gcs_url:="$GCS_URL"} \
        >> "$GUNLUK/mavros.log" 2>&1 &
}
_mavros_baslat
[ -n "$GCS_URL" ] && echo "[baslat] MAVLink QGC'ye iletiliyor: $GCS_URL"
sleep 15

# --- MAVROS GCS HATTI GERCEKTEN KURULDU MU? (26 Agustos 2026) ---------------
# Yukaridaki P0.13 ag bekleme dongusu YETMIYOR. 26 Agustos'ta olculdu: ag
# tamamen ayaktayken ELLE yapilan restart'lar da bozuk cikti (19:49 ve 19:51).
# Yani "ag yoktu" tek sebep degil — her baslatmada atilan bir zar. Uc ucagin
# da hem temiz hem kirli acilislari var; ucaga ozgu degil.
#
# ELENENLER (hepsi ayni gun olculdu): gcs_url farki YOK (ucunde ayni), ag modu
# ucunde de host, arayuz/rota ayni, 14555 ucunde de bagli. Yayin adresinin
# kendisi de saglam: ylp02'den 10.x.x.255 / 172.17.255.255 / 255.255.255.255
# ucune de test paketi SORUNSUZ gitti. Yani yonlendirme ya da docker0 degil.
# Kok neden bulunamadi; mavconn kaynagini okumak gerekiyor (ayri is).
#
# BOZUK HALIN BEDELI (ayni gun, tek oturum): ylp02 289 MB / 2.805.206 satir,
# ylp00 876 MB / 8.275.479 satir. Tarihsel tepe: mavros.log tek basina
# 18,64 GB (bu dosyanin basindaki nota bak).
#
# UCUS BUNA BAGLI DEGIL — mesh seri hattan gidiyor. ASIL ZARAR TESHIS:
# mavros.log ucus sonrasi bakilan kaynaktir ve gurultu onu yutuyor. Log
# dondurme devreye girdiginde acilis satirlari tamamen siliniyor; 26 Agustos'ta
# ylp01'in logunun basi zaten yok olmustu.
#
# BELIRTI: 'mavconn: udp1: sendto: Network is unreachable, retrying'
# Ilk saniyede basliyor ve kendiliginden DUZELMIYOR. Bilinen tek cozum
# konteyneri yeniden baslatmak — 26 Agustos'ta iki ucakta da temizledi.
#
# ONARIM: bozuksa mavros BIR KEZ yeniden baslatilir. 26 Agustos'ta olculdu —
# yeniden baslatmak iki ucakta da temizledi, yani hata kalici degil; yeni bir
# deneme cogu zaman tutuyor. Tam BURASI guvenli: mavros ayakta ama gps_saat ve
# suru dugumleri HENUZ acilmadi, yani hicbir sey mavros'a bagli degil.
# TEK deneme — dongu riski yok; ikincide de bozuksa bayrak birakilip gecilir.
_gcs_hata_say() {
    _bastan="${1:-0}"
    _n=$(tail -n +"$((_bastan + 1))" "$GUNLUK/mavros.log" 2>/dev/null \
         | grep -ac 'Network is unreachable')
    echo "${_n:-0}"
}
if [ -n "$GCS_URL" ]; then
    _gcs_hata=$(_gcs_hata_say 0)
    # OTOMATIK ONARIM YALNIZ ILK ACILISTA (27 Agustos 2026, operator karari)
    #
    # Operator: "rpi acildiginda bu hata olursa ... sadece drone ILK KEZ
    # acildiginda rpi kendisi yapabilsin. Ama ucurduk ve inis yaptik ya da
    # rpi acilisindan belli bir dakika gecti, o zaman ... bu insiyatifi
    # almasin. YKI'ye log olarak bassin, operator SSH ile kendisi yapsin."
    #
    # GEREKCE: konteyner Pi acildiktan saatler sonra da yeniden baslatilabilir
    # — ucus sonrasi, kayit incelenirken, saha ortasinda. O anda mavros'u
    # kendiliginden yeniden baslatmak SURPRIZ ve riskli; karar operatorun.
    # Acilisin ilk dakikalarinda ise hicbir sey mavros'a bagli degil, orada
    # otomatik onarim zararsiz ve faydali.
    #
    # OLCUT Pi UPTIME'i — konteyner uptime'i DEGIL: konteyner her restart'ta
    # sifirlanir ve "ilk acilis" yanilsamasi yaratirdi.
    _PI_UPTIME_SN=$(cut -d. -f1 /proc/uptime 2>/dev/null || echo 999999)
    _ONARIM_TAVANI_SN="${MAVROS_ONARIM_TAVANI_SN:-900}"     # 15 dakika
    if [ "$_gcs_hata" -gt 0 ] && [ "$_PI_UPTIME_SN" -lt "$_ONARIM_TAVANI_SN" ]; then
        echo "[baslat] MAVROS GCS hatti kurulamadi ($_gcs_hata hata) — ilk acilis, BIR KEZ yeniden deneniyor"
        _isaret=$(wc -l < "$GUNLUK/mavros.log" 2>/dev/null || echo 0)
        pkill -f 'mavros_node' 2>/dev/null
        sleep 3
        _mavros_baslat
        sleep 15
        _gcs_hata=$(_gcs_hata_say "$_isaret")
    elif [ "$_gcs_hata" -gt 0 ]; then
        echo "[baslat] MAVROS GCS hatti bozuk ($_gcs_hata hata) — Pi ${_PI_UPTIME_SN} sn'dir acik"
        echo "[baslat]   OTOMATIK ONARIM YAPILMADI (tavan ${_ONARIM_TAVANI_SN} sn)."
        echo "[baslat]   Karar operatorde: SSH ile 'docker restart <konteyner>'."
    fi
    if [ "$_gcs_hata" -gt 0 ]; then
        echo "[baslat] ==========================================================="
        echo "[baslat] MAVROS GCS HATTI KURULAMADI — ikinci denemede de $_gcs_hata hata"
        echo "[baslat]   QGC bu uctan MAVLink ALAMAZ."
        echo "[baslat]   mavros.log denetlenemez hale gelene kadar buyuyecek."
        echo "[baslat]   COZUM: docker restart <konteyner> — sonra bu satir CIKMAMALI"
        echo "[baslat] ==========================================================="
        echo "$_gcs_hata" > /ws/mavros_gcs_bozuk
    else
        rm -f /ws/mavros_gcs_bozuk
        echo "[baslat] MAVROS GCS hatti saglikli (yayin hatasi yok)"
    fi
fi

# --- GPS'ten saat duzeltme (15 Agustos) -------------------------------------
# Pi 5'te RTC yedek pili yok: acilista saat ~11 saat GERIDEN geliyor ve ancak
# ag gelince NTP one atlatiyor (olculdu, ayrinti gps_saat.py basinda). Iki
# ucagin saati o pencerede birbirinden farkli olur; capraz ucak kayit
# karsilastirmasi (kim once lider oldu, kacinma ne zaman tetiklendi) imkansiz
# hale gelir. Yarisma gunu sahada internet olmayabilir — NTP hic gelmez.
#
# PX4 UTC'yi GPS'ten aliyor, MAVROS 1 Hz'de yayinliyor. Internet gerekmiyor.
#
# NEDEN TAM BURASI: mavros ayakta ama diger dugumler HENUZ ACILMADI. Saati bir
# dugum kostuktan sonra atlatmak ROS zamanlayicilarini ve kayit damgalarini
# bozar. Bu yuzden bir kez, burada, dugumlerden once.
#
# GPS bu sure icinde kilitlenmezse saat DEGISMEZ ve olculen fark loga yazilir —
# o boot'un kayitlari sonradan o farkla duzeltilebilir. Acilis bloke olmaz.
# Kapatmak icin: touch ~/yelpence_ws/gps_saat_kapali
#
# BEKLEME NEDEN 150 SN (17 Agustos'ta olculdu, onceden 25'ti)
# 25 sn SOGUK BASLANGICTA yetmiyor. Olcum, iki ucakta da ayni:
#     Pi acilis 01:52:36 -> konteyner 01:52:49 -> mavros + sleep 15
#     -> gps_saat --bekle 25 pes ediyor ~01:53:30
# Yani GPS'e guc verildikten sonra topu topu ~54 sn taniniyor. Here4 o surede
# efemeris almadan kilitlenmiyor; sonuc "[gps_saat] GPS zamani 25 sn icinde
# gelmedi" ve iki ucagin saati BIRBIRINDEN 2 sa 17 dk farkli kaldi. Sicak
# baslangicta sorun cikmadigi icin aylarca fark edilmedi.
#
# Uzatmanin bedeli YOK: gps_saat.py ilk gecerli ornegi alinca hemen cikiyor
# (bkz. while dongusu, gps_saat.py). Yani sicak GPS'te gene saniyeler surer;
# 150 sn yalnizca gercekten soguksa — yani tam da beklemek istedigimiz anda —
# harcanir. Ust sinir bilincli: kilitlenmeyen bir GPS acilisi 2.5 dk'dan fazla
# geciktirmesin.
if [ -f /ws/gps_saat_kapali ]; then
    echo "[baslat] gps saat duzeltmesi KAPALI (/ws/gps_saat_kapali)"
elif [ -f /ws/gps_saat.py ]; then
    # SERT ZAMAN ASIMI — 20 Agustos 2026, P0.13.
    #
    # OLCULDU: bu cagri SENKRON (arka plana atilmiyor) ve 20 Agustos'ta
    # `--bekle 150` olmasina RAGMEN 25+ DAKIKA takildi. Sonucu:
    # baslat.sh'in GERI KALANI HIC CALISMADI — px4_bridge, esp32_bridge,
    # agent_fsm yok, yalnizca mavros vardi. Ucak sessizce sakat kaldi.
    #
    # Kendi `--bekle` dongusu time.monotonic() ile sinirli, yani takilma
    # ORADA DEGIL; muhtemelen rclpy/DDS kurulumunda (ag yokken). Nerede
    # oldugunu KANITLAMADIK, o yuzden noktasal duzeltme yerine DISARIDAN
    # sert bir tavan koyuyoruz: nerede takilirsa takilsin acilis surer.
    #
    # 200 = 150 (kendi beklemesi) + 50 pay.
    #
    # `-k 15` SART, `-s INT` TEK BASINA YETMEZ — bu duzeltme yazilirken
    # denendi ve tam da onlemeye calistigi sekilde takildi: `timeout -s INT`
    # sinyali gonderip cikar, ama surec SIGINT'i yutar ya da kesilemez bir
    # bekleyisteyse OLMEZ; boru `tee`'ye acik kaldigi icin baslat.sh YINE
    # bloke olur. `-k 15` 15 sn sonra SIGKILL yollayip bunu keser.
    timeout -s INT -k 15 200 python3 /ws/gps_saat.py \
            --ns "/drone_${AGENT_ID}" --bekle 150 2>&1 \
            | tee -a "$GUNLUK/gps_saat.log"
    _gs=${PIPESTATUS[0]}
    if [ "$_gs" = 124 ] || [ "$_gs" = 137 ]; then
        echo "[baslat] UYARI: gps_saat 200 sn'de bitmedi, ZORLA kesildi." \
             "Saat DUZELTILMEDI — capraz ucak kayit karsilastirmasi bozuk" \
             "olabilir, ama ucus etkilenmez. Bkz. YAPILACAKLAR P1.4." \
             | tee -a "$GUNLUK/gps_saat.log"
    fi
fi
fi   # /altyapi: ag beklemesi + mavros + GCS denetimi + gps_saat
# GUIDED YORUNGE HIZLARI — yorunge 2 Agustos'ta px4_bridge'e tasindi
# (bkz. _yurutucu_ilerlet). Onceden gorev betigi setpoint'i kendi yurutuyor ve
# her ara noktayi mesh'ten yolluyordu; mesh'te ~%30 paket kaybi oldugu icin
# her kayip ucakta bir sicrama uretiyordu ("gaz bas-cek"). Artik YKI yalniz
# hedefi gonderiyor, ara degerleri drone 50 Hz'de kendi uretiyor.
#
# Bu degerler gorev betigindeki GOREV_HIZ_MPS / GOREV_DIKEY_HIZ_MPS ile AYNI
# olmali — ayrisirsa ucus dogru hizda olur ama YKI ekranindaki sayi yalan
# soyler. Betikteki degerler artik yalniz bilgi amacli.
# UCUS AYARLARI DOSYASI — hiz/ivme TEK KAYNAKTAN.
#
# /ws/ucus_ayarlari.env varsa buradan okunur. O dosyayi YKI uretir:
#     python3 src/gcs/ucus_ayarlari.py --kabuk > ucus_ayarlari.env
# ve dagit.sh ucaklara kopyalar.
#
# NEDEN: ayni hiz uc yerde duruyordu — gorev kosucusu, burasi ve PX4.
# 14 Agustos'ta gorev kosucusu 3.0'a gecti ama burasi 2.0'da kaldi; ucak
# 2.0 ucar, YKI ekraninda 3.0 yazardi ve varis zamanlamasi kayardi.
# Dosya yoksa asagidaki varsayilanlar gecerli — eski davranis korunur.
#
# DOSYA ONCELIKLI — `. dosya` env'i EZER.
#
# 15 Agustos'ta olculdu: burada onceden "ENV ONCELIKLI, -e dosyayi ezer"
# yaziyordu ve YANLISTI. `GUIDED_HIZ_YATAY=9.9` env'iyle girip dosyayi
# source edince sonuc 3.0 cikiyor, yani -e SESSIZCE yok sayiliyor. Ucus hizi
# degiskeninde bu tehlikeli bir yalan: operator 1.0 verdigini sanip 3.0
# ucabilirdi.
#
# Davranis BILEREK boyle birakildi: 14 Agustos'ta hiz/ivme tek kaynaga
# (ucus_ayarlari.py) baglandi ve dosyanin kazanmasi tam olarak kaymayi
# onleyen sey. Duzeltilen yorumdur.
#
# Tek ucakta hizli deneme icin -e degil, CANLI parametre yolu var
# (konteyner yeniden baslamadan, CLAUDE.md §8):
#     python3 - --ns /px4_bridge --yaz guided_hiz_yatay_mps=4.0  < src/gcs/px4_param.py
if [ -f /ws/ucus_ayarlari.env ]; then
    # shellcheck disable=SC1091
    . /ws/ucus_ayarlari.env
    echo "[baslat] ucus ayarlari dosyadan: yatay=${GUIDED_HIZ_YATAY} dikey=${GUIDED_HIZ_DIKEY}"
fi
GUIDED_HIZ_YATAY="${GUIDED_HIZ_YATAY:-2.0}"
GUIDED_HIZ_DIKEY="${GUIDED_HIZ_DIKEY:-1.0}"
GUIDED_TASMA="${GUIDED_TASMA:-3.0}"
# Rota sekillendirme varsayilanlari — ucus_ayarlari.env yoksa devreye girer.
# Degerler config'in URETTIGI ile AYNI olmali; ayrisirsa env dosyasi olan ve
# olmayan ucak farkli ucar.
ROTA_MAKS_HIZ="${ROTA_MAKS_HIZ:-3.0}"
ROTA_ADIM_HZ="${ROTA_ADIM_HZ:-5.0}"
ROTA_DONUS_TAVANI_DEG_S="${ROTA_DONUS_TAVANI_DEG_S:-25.0}"
ROTA_TEGET_HIZ="${ROTA_TEGET_HIZ:-1.5}"
ROTA_TEGET_IVME="${ROTA_TEGET_IVME:-0.75}"
# IVME SINIRI: ilk surumde yoktu ve hiz ileri-beslemesi BASAMAK gidiyordu —
# hareket baslarken bir tik'te 0'dan tam hiza. Ucus kaydinda olculdu: yatayda
# %28 (2.57 m/s), dikeyde %18 (1.18 m/s) asim. Operator "once asiri hizli,
# sonra olmasi gereken hizda" diye bildirdi. MPC_ACC_HOR ucakta 2.0; altinda.
#
# 2. TUR (2 Agustos, ikinci ucus): rampa geldi, KOMUT tepe artik tam 2.00 /
# 1.00 — basamak yok. Ama OLCULEN hala asiyor: yatay 2.51 (%25),
# dikey 1.42 (%42). Sebep artik farkli: rampa sirasinda ucak yurutucunun
# GERISINDE kaliyor, konum hatasi birikiyor ve PX4 onu ileri-beslemenin
# USTUNE ekliyor (MPC_XY_P x hata). Olculen gecikme ~0.5 m -> ~0.5 m/s fazla.
# Operator "varinca biraz geri geldi, sonradan bir duzeltme yapti" dedi.
#
# Tek gercek kaldirac IVME: yurutucu ucagin yetisebileceginden hizli
# rampalarsa gecikme birikir. Yariya indiriyoruz. Bedeli 7 m'lik gecisin
# ~4.7 -> ~6 sn'ye cikmasi.
#
# 3. TUR: ivmeyi yariya indirmek ISE YARAMADI. Olculdu: 1.5 -> 0.8 yapinca
# yatay asim %25'ten sadece %21'e indi (2.51 -> 2.42), bedeli 3 sn. Sebep:
# 7 m'lik gecis neredeyse tamamen gecici rejim; gecikmenin sonumlenme zaman
# sabiti 1/MPC_XY_P ~ 1.05 sn ve seyir fazi zaten ~1 sn. Ivme geri alindi.
# Asimin gercek kaldiraci GECIKME TELAFISI (bkz. _yurutucu_ilerlet).
GUIDED_IVME_YATAY="${GUIDED_IVME_YATAY:-1.5}"
GUIDED_IVME_DIKEY="${GUIDED_IVME_DIKEY:-1.0}"
# GECIKME TELAFISI — DENENDI, KAPATILDI (2 Agustos, 4. ucus).
#
# Fikir: PX4 toplam talebi "ileri-besleme + MPC_XY_P x gecikme" seklinde
# kuruyor; o ikinci terimi ileri-beslemeden geri cikarirsak toplam istedigimiz
# hiz kalir. Kod calisti, KOMUT tepesi 2.00 -> 1.43 indi. Ama:
#
#     telafisiz:  KOMUT 2.00  OLCULEN 2.42   (PX4 ekledi 0.42 -> gecikme 0.44 m)
#     telafili :  KOMUT 1.43  OLCULEN 2.24   (PX4 ekledi 0.81 -> gecikme 0.85 m)
#
# GECIKME IKIYE KATLANDI. Sebep: yuruyen nokta hala 2.0 m/s ilerliyor ama
# ucaga 1.43 deniyor; ucak yavas kalinca nokta daha cok one geciyor, PX4'un
# ekledigi terim buyuyor ve kaybedilen hizin cogu geri geliyor. Telafi kendi
# kendini yiyor.
#
# Bilanco: kazanc %7 (2.42 -> 2.24). Bedel: MPC_XY_P'ye gizli bagimlilik,
# konum dongusunun %70'inin iptali (ruzgar direnci ucte bire iner) ve ucus
# 33 -> 35 sn. Takas savunulamaz -> oran 0.0.
#
# Kod DURUYOR: tekrar denenecekse yuruyen noktanin hizi da ucagin gercek
# hizina baglanmali, yoksa ayni geri besleme dongusune girilir.
GUIDED_KONUM_KP="${GUIDED_KONUM_KP:-0.95}"
GUIDED_TELAFI_ORANI="${GUIDED_TELAFI_ORANI:-0.0}"
# IVME ILERI-BESLEMESI (20 Agustos 2026): 1.0 acik, 0.0 kapali.
# A/B ucusuyla olculdu — tepe gecici hata -60 %, varis asimi -61 %.
# Geri almak icin GUIDED_IVME_FF=0.0 (docs/PLAN.md §9).
GUIDED_IVME_FF="${GUIDED_IVME_FF:-1.0}"
# --- SURU DUGUM ANAHTARI — YUKARI TASINDI (21 Agustos 2026) -----------------
# Eskiden bu blok dosyanin ~648. satirindaydi, yani px4_bridge (velocity_only)
# ve esp32_bridge yonlendirme karari ALINDIKTAN SONRA. Ikisi de "sürü zinciri
# acik mi" bilgisine ihtiyac duyuyor, o yuzden cozumleme yukari alindi.
# Davranis degismedi: ayni dosya, ayni oncelik (dosya env'i ezer).
if [ -f /ws/suru_dugumleri ]; then
    SURU_DUGUMLERI="$(sed 's/#.*//' /ws/suru_dugumleri | tr '\n' ' ' \
                      | tr -s '[:space:]' ' ' | sed 's/^ *//; s/ *$//')"
    echo "[baslat] suru dugumleri DOSYADAN: '${SURU_DUGUMLERI}' (/ws/suru_dugumleri)"
fi
SURU_DUGUMLERI="${SURU_DUGUMLERI:-}"

acik() {
    case " $SURU_DUGUMLERI " in
        *" hepsi "*) return 0 ;;
        *" $1 "*)    return 0 ;;
        *)           return 1 ;;
    esac
}

# NOT (21 Agustos): bu blok VELOCITY_ONLY'den ONCE durmak ZORUNDA.
# Bos yuva kapisi VELOCITY_ONLY'yi geri false yapabiliyor ve px4_bridge
# hemen asagida o degerle kalkiyor — blok asagida kalirsa kapi cok gec
# calisir ve dugum yanlis modda baslar.
# --- CARPISMA KACINMASI ------------------------------------------------------
# Tek kacinma dugumu: collision_avoidance (`ca` anahtari, ADIM 4/KARAR-01).
#
# Devredeyken zincir soyle olur:
#   esp32_bridge -> /control/setpoint/RAW -> collision_avoidance -> /control/setpoint
# Yani esp32_bridge'in cikisi yeniden yonlendiriliyor ve kacinma araya
# giriyor. Kacinma yoksa esp32_bridge dogrudan /control/setpoint'e yazar.
#
# NOT: kacinma dugumu calissa bile remap YOKSA zararsizdir — /raw'a kimse
# yazmadigi icin hicbir setpoint yayinlamaz (Asama-1 gozlem modu boyleydi).
# YONLENDIRME, DUGUM SECIMINDEN AYRILDI — 21 Agustos 2026.
#
# 🔴 basit_kacinma 29 Agustos 2026'da SILINDI — ve bu bir sadelestirmeden
# fazlasiydi. O dugum yalniz position_valid=True setpoint'lerde calisiyordu;
# formasyon ucagi SAF HIZ kipinde (position_valid=False) suruyor, yani sürü
# zincirinde ZATEN OLUYDU. Belgelerde "geri donus" diye duran sey aslinda
# kacinmanin TAMAMEN kapanmasi anlamina geliyordu. /ws/kacinma bayragi da
# onunla birlikte kalkti; dosya hala duruyorsa asagisi HATA verip durur —
# sessizce korumasiz kalmaktansa acilmamak dogru.
if [ -f /ws/kacinma ]; then
    echo "[baslat] 🔴 HATA: /ws/kacinma var ama basit_kacinma SILINDI (29 Agu 2026)."
    echo "[baslat]        Bu dosyayla devam etmek kacinmayi SESSIZCE kapatirdi."
    echo "[baslat]        Yapilacak: rm /ws/kacinma  +  /ws/suru_dugumleri'ne 'ca' ekle."
    exit 1
fi
CA_ACIK=0
if acik ca || acik hepsi; then CA_ACIK=1; fi

# SP_REMAP hesabi BURADAN TASINDI (25 Agustos 2026, tek-uretici gecisi).
# Karar "formasyon SURUYOR mu"ya bagli ve o ancak asagidaki bos-yuva
# kapisindan SONRA kesinlesiyor (kapi /ws/gozlem'i touch edebiliyor).
# Yeni yeri: kapinin hemen arkasi. esp32_bridge'in kullanimi cok daha
# asagida (ros2 run satiri), o yuzden tasima guvenli.

# BOS YUVA KAPISI — 21 Agustos 2026.
#
# Kacinma yuvasi ayni zamanda ZORUNLU AKTARIM KATI (CLAUDE.md bolum 3):
# /control/setpoint/raw ile /control/setpoint arasindaki TEK kopru orasi.
# Formasyon ucagi SURUYORKEN (gozlem kapali) hicbir kacinma dugumu
# kosmuyorsa formation_node /raw'a yazar, kimse /setpoint'e aktarmaz ve
# setpoint'ler px4_bridge'e HIC ULASMAZ. Ucak kalkar, komut bekler, hicbir
# sey gelmez — hata da vermez. Bu sinif hatayi sessiz birakmiyoruz.
if [ ! -f /ws/gozlem ] && { acik formasyon || acik hepsi; } \
   && [ "$CA_ACIK" = "0" ]; then
    echo "[baslat] 🔴 HATA: formasyon UCAGI SURECEK (gozlem kapali) ama"
    echo "[baslat]        hicbir kacinma dugumu yok — /raw ile /setpoint"
    echo "[baslat]        arasindaki AKTARIM KATI BOS. Setpoint'ler ucaga"
    echo "[baslat]        ULASMAZ. SURU_DUGUMLERI'ne 'ca' ekle."
    echo "[baslat]        Bkz. CLAUDE.md bolum 3, KARAR-01."
    echo "[baslat]        GUVENLI TARAFA GECILIYOR: gozlem modu zorlaniyor."
    # `touch` YETIYOR: asagidaki VELOCITY_ONLY blogu tam da bu dosyaya
    # bakiyor ([ ! -f /ws/gozlem ]), yani B moduna gecis kendiliginden
    # iptal olur. Burada ayrica VELOCITY_ONLY=false yazmak gereksiz ve
    # yaniltici olurdu — degisken bu satirdan SONRA kuruluyor.
    touch /ws/gozlem
fi

# FORMASYON_SURUYOR — bu noktadan sonra KESIN (kapi gozlemi zorladiysa 0).
FORMASYON_SURUYOR=0
if [ ! -f /ws/gozlem ] && { acik formasyon || acik hepsi; }; then
    FORMASYON_SURUYOR=1
fi

# TEK-URETICI GECISI — 25 Agustos 2026 (CLAUDE.md §4, ADIM 3).
#
# /control/setpoint/raw'in iki olasi ureticisi var: esp32_bridge (mesh
# goto'lari, remap ile) ve formation_node (50 Hz slot takibi). Formasyon
# UCAGI SURERKEN ikisi ayni yuvaya yazamaz — px4_bridge 50 Hz'de iki
# algoritmadan celiskili setpoint alir, kazanan zamanlamaya kalir.
#
# Cozum FIZIKSEL ayrim (durum-bazli susturmaya guvenmiyoruz — o yalniz
# formation_node tarafinda var, esp32_bridge kosulsuz basar):
#   formasyon SURUYOR  -> esp32_bridge cikisi /gozlem/.../mesh_goto
#                         (kayda girer, UCAGI SUREMEZ; raw'in tek
#                         ureticisi formation_node olur)
#   formasyon surmuyor -> bugune kadarki davranis BIREBIR:
#                         kacinma varsa /raw'a, yoksa dogrudan /setpoint'e
#
# NOT: mesh'in ARM / takeoff / land / mode komutlari AgentCommand
# kanalindan gider, bu remap onlara DOKUNMAZ. Acil mudahale her zaman
# land/RTL komutuyla — goto ile degil.
SP_REMAP=""
if [ "$FORMASYON_SURUYOR" = "1" ]; then
    SP_REMAP="-r /drone_${AGENT_ID}/control/setpoint:=/gozlem/drone_${AGENT_ID}/mesh_goto"
    echo "[baslat] 🔒 TEK-URETICI (ADIM 3): formasyon SURUYOR — esp32_bridge"
    echo "[baslat]    cikisi /gozlem/drone_${AGENT_ID}/mesh_goto (mesh goto UCAGI SUREMEZ;"
    echo "[baslat]    /raw'in tek ureticisi formation_node, aktarim kati CA)"
elif [ "$CA_ACIK" = "1" ]; then
    SP_REMAP="-r /drone_${AGENT_ID}/control/setpoint:=/drone_${AGENT_ID}/control/setpoint/raw"
    echo "[baslat] CARPISMA KACINMASI ACIK (collision_avoidance) — esp32_bridge cikisi /raw'a yonlendirildi"
else
    echo "[baslat] carpisma kacinmasi kapali ('ca' istenmedi)"
fi

# VELOCITY_ONLY — ADIM 3'un sarti (PLAN.md Engel 3).
#
# formation_node C modu icin yazildi (saf hiz, position_valid=False). Bu
# bayrak False kalirsa px4_bridge A modunda kosar, PX4 de konum kontrolu
# yapar ve KAZANCLAR TOPLANIR (SVT 0.8 + MPC_XY_P 0.95).
#
# GUIDED YOLU BOZMAZ — olculdu (px4_bridge.py:656,672):
#     use_velocity = setpoint_fresh AND velocity_valid
#     if use_velocity and velocity_only:  -> B (saf hiz)
#     elif use_velocity or yurutucu_aktif: -> A (konum + hiz FF)
# Guided goto yalniz position_valid koyuyor, yani use_velocity=False ve
# A moduna duser. Anahtar setpoint TIPINE gore calisiyor, global degil:
# suru zinciri acikken bile kanitlanmis guided yol yedek olarak durur.
#
# SART: zincirde HIZ ureten bir dugum var mi. Iki kaynak:
#   (a) formation_node ucagi SURUYORSA (gozlem kapali)  — ADIM 3
#   (b) collision_avoidance kosuyorsa                    — ADIM 4
#
# (b) 21 Agustos'ta EKLENDI, ilk yazimda ATLANMISTI ve ucmadan once
# yakalandi. CA kacisi da position_valid=False + velocity_valid=True
# uretiyor; velocity_only false iken px4_bridge onu A moduna sokuyor:
#     publish_position_velocity_setpoint(target_x, target_y, target_z, vx,vy,vz)
# yani PX4'e "ESKI hedefe git" + "su kacis hizi" birden gidiyor ve PX4'un
# konum kontrolu kacisi GERI CEKIYOR. Kacinma sessizce zayifliyor.
# Ayni hastalik PLAN.md "Engel 3"te formation_node icin yaziliydi; CA icin
# de gecerli oldugu gozden kacmis.
#
# GUIDED YOLU BOZMAZ (olculdu, px4_bridge.py:656,665,800-812):
#   guided goto -> velocity_valid=False -> use_velocity=False
#               -> yurutucu_aktif dali (C) — velocity_only'ye HIC bakmiyor
#   CA kacisi   -> velocity_valid=True   -> B dali (saf hiz, PX4 konum tutmaz)
VELOCITY_ONLY=false
if [ "$FORMASYON_SURUYOR" = "1" ] || [ "$CA_ACIK" = "1" ]; then
    VELOCITY_ONLY=true
fi
echo "[baslat] px4_bridge velocity_only=${VELOCITY_ONLY}" \
     "(formasyon suruyor mu: $([ -f /ws/gozlem ] && echo 'HAYIR-gozlem' || echo evet-veya-kapali))"

if altyapi; then   # --yalniz modunda ATLANIR  (px4_bridge)
ros2 run swarm_control px4_bridge --ros-args -p agent_id:=${AGENT_ID} \
    -p velocity_only:=${VELOCITY_ONLY} \
    -p guided_hiz_yatay_mps:=${GUIDED_HIZ_YATAY} \
    -p guided_hiz_dikey_mps:=${GUIDED_HIZ_DIKEY} \
    -p guided_ivme_yatay_mps2:=${GUIDED_IVME_YATAY} \
    -p guided_ivme_dikey_mps2:=${GUIDED_IVME_DIKEY} \
    -p guided_konum_kp:=${GUIDED_KONUM_KP} \
    -p guided_telafi_orani:=${GUIDED_TELAFI_ORANI} \
    -p guided_ivme_ff:=${GUIDED_IVME_FF} \
    -p guided_tasma_m:=${GUIDED_TASMA} >> "$GUNLUK/px4b.log" 2>&1 &
sleep 5
fi   # /altyapi: px4_bridge
# BATARYA KRITIK ESIGI — 0 ise FSM bataryaya HIC BAKMAZ.
#
# 2 AGUSTOS: ucaklar regulatorden besleniyor, PX4'te BAT1_SOURCE disabled.
# Telemetrideki gerilim gercek bir olcum degil; d3'un FCU'su yapilandirilmamis
# ADC'den 3.1 V okuyordu. Varsayilan esik 13.6 V oldugu icin FSM 3 saniyede bir
# IDLE <-> FAILSAFE zipladi, her seferinde EMERGENCY olayi yayinladi, kacinma
# d3'u disladi ve YKI ekraninda "Failsafe" yazdi.
#
# PIL GERI TAKILINCA: bu degeri 13.6 yap (ya da BATARYA_KRITIK_V ile gec).
# Ayrica YKI tarafinda iki yer daha var, ucu birden acilmali:
#   frontend/src/services/gorunum.ts -> PIL_GOSTER = true
#   backend/config.yaml -> alerts.susturulan'dan batarya kodlarini cikar
BATARYA_KRITIK_V="${BATARYA_KRITIK_V:-0.0}"

# YER TESTI BAYRAGI — /ws/yer_testi dosyasi varsa acilir.
#
# Acikken "gorev basladi" olayi FSM'i IDLE -> ARMING -> ARMED yolundan normal
# yurutur (gercek preflight, gercek arm, gercek AgentStatus) ama ARMED'da
# DURDURUR: kalkis komutu hic gonderilmez.
#
# NEDEN (15 Agustos): consensus'un lider secebilmesi icin ajanin
# ELIGIBLE_STATES'te olmasi gerekiyor ve IDLE o kumede YOK; en dusuk uygun
# durum ARMED. ARMED'a cikmanin tek yolu EVENT_MISSION_STARTED, ama o olay
# ayni zamanda kalkisi tetikliyor. Pervanesiz yer testinde bu, motorlari
# ~30 sn bosta TAM GAZDA tutup FAILSAFE'e dusuruyordu — ESC'leri pisirir.
#
#     touch ~/yelpence_ws/yer_testi   # ac
#     rm    ~/yelpence_ws/yer_testi   # kapat (UCUSTAN ONCE ZORUNLU)
#
# drone_bul.sh --durum bayraklari listeliyor, orada gorunur.
YER_TESTI=false
if [ -f /ws/yer_testi ]; then
    YER_TESTI=true
    echo "[baslat] *** YER TESTI ACIK *** kalkis komutu GONDERILMEYECEK (/ws/yer_testi)"
fi

# kalkis_olayla=false: GECIS DONEMI (19 Agustos 2026, P0.11 kopru karari).
# esp32_bridge guided ARM'da EVENT_MISSION_STARTED uretir; ajan ARMED'a
# cikar (consensus secim yapabilir) ama kalkisi TETIKLEMEZ — 'takeoff'
# komutunun tek kaynagi guided yol. mission1+agent_fsm kalkisi
# devraldiginda SURU_KALKIS_OLAYLA=true yapilacak.
if altyapi; then   # --yalniz modunda ATLANIR  (agent_fsm + mesaj hizlari)
ros2 run swarm_state_machine agent_fsm_node --ros-args \
    -p agent_id:=${AGENT_ID} \
    -p battery_critical_voltage_v:=${BATARYA_KRITIK_V} \
    -p kalkis_olayla:=${SURU_KALKIS_OLAYLA:-false} \
    -p yer_testi:=${YER_TESTI} >> "$GUNLUK/fsm.log" 2>&1 &
sleep 5
# MAVLink yayin hizlari: FCU her resetlendiginde sifirlanir, her aciliste yeniden istenir
python3 /ws/mesaj_hizlari.py >> "$GUNLUK/hizlar.log" 2>&1
sleep 2
fi   # /altyapi: agent_fsm + mesaj hizlari
# TAKIM_ID -> team_id: QR'in takim filtresi mesh'te TASINMIYOR (metin, 16 bayta sigmaz).
# QR'i okuyan drone yerelde filtreliyor; alici kopru bu alani DOLDURMAK ZORUNDA.
# Bos kalirsa mission_fsm_node:336 ve mission1_node:205 gelen HER QR'i reddeder
# ve semptom "QR gorevleri hic islenmiyor" olur. Kopru bos gorurse uyariyor.
# Varsayilan mission1_node:122 / mission_fsm_node:89 ile AYNI olmali;
# ucu ayrisirsa mission_fsm gelen her QR'i reddeder.
# TEK TIRNAK SART. ROS 2 "-p ad:=deger" degerini YAML olarak ayristiriyor:
# 752825 -> INTEGER sanilir, parametre STRING bildirildigi icin
# InvalidParameterTypeException atar ve DUGUM COKER (yasandi 30 Tem).
# team_id:='752825' seklinde gecmek gerekiyor.
TAKIM_ID="${TAKIM_ID:-752825}"
# KANAT_ALFA_DEG -> wing_alpha_deg: OKBASI/V kanat acisi. FormationCommand bu alani TASIMIYOR, o
# yuzden lider parametreden okuyup pakete koyuyor, alici paketten okuyor —
# boylece butun suru LIDERIN degerini kullanir. formation_node ve mission1_node
# da ayni isimli parametreyi kullaniyor; UCU AYNI OLMALI yoksa slot geometrisi
# sessizce ayrisir.
KANAT_ALFA_DEG="${KANAT_ALFA_DEG:-45.0}"
if altyapi; then   # --yalniz modunda ATLANIR  (esp32_bridge)
ros2 run swarm_control esp32_bridge --ros-args -p serial_port:=/dev/ttyAMA4 -p baud:=460800 -p agent_id:=${AGENT_ID} -p team_id:="'${TAKIM_ID}'" -p wing_alpha_deg:=${KANAT_ALFA_DEG} $SP_REMAP >> "$GUNLUK/esp.log" 2>&1 &
fi   # /altyapi: esp32_bridge

# basit_kacinma baslatma blogu 29 Agustos 2026'da SILINDI (yukaridaki
# gerekce). Tek kacinma dugumu collision_avoidance ve o asagida, sürü
# dugumleri bolumunde `ca` anahtariyla aciliyor.

# --- Ucus kaydi (PX4 ULog'unun yerine gecen kayit) --------------------------
# Pixhawk'ta RAM sinirda oldugu icin FCU tarafinda logger ACILMIYOR. Onun
# yerine MAVROS'un ZATEN aldigi veriyi burada diske yaziyoruz: Pixhawk'a ek
# yuk binmez, veri hatta nasilsa akiyor.
#
# ULog'dan eksigi: PX4'un ic uORB konulari (kestirimci innovation'lari,
# aktuator ciktilari, ham sensor 250 Hz+) MAVLink'ten gecmez. Mevcut yayin
# hizlariyla (ATTITUDE_QUAT 20 Hz, ODOMETRY 20 Hz) 10 Hz'e kadar olan olaylar
# yakalanir — kaza/olay analizi icin yeter, EKF/kontrol ayari icin yetmez.
#
# 30 sn'lik parcalar: ucus 13-14 dk suruyor. ros2 bag klasorun tamamini
# metadata.yaml uzerinden TEK kayit olarak gorur, parcalanma analizi
# zorlastirmaz.
#
# "30 sn'de en fazla 30 sn kaybedilir" DIYORDU; yanlisti, 2 Agustos kazasi
# gosterdi. Parca sinirinda kayip olmuyor — parca sinirinda TEK YAZMA oluyor.
# Dosya icinde veri diske HIC inmiyordu. Olculdu (ylp02, 2 Agustos):
# 3 konuluk kayitta dosya 30 sn boyunca 0 BAYT kaldi, split anida 114 KB'a
# firladi. ylp01'in enkazinda da son parca 0 bayttir ve kayip 14.65 sn =
# son split (13:47:18.85) ile yere carpma (13:47:33.5) arasi. Birebir.
#
# UC AYRI TAMPON vardi, ucu de kapatildi:
#   1) rosbag2 mesaj onbellegi — --max-cache-size varsayilani 104857600
#      (100 MiB) ve CIFT tamponlu. 40 KB/s'te bu tampon uctan uca ~40 dakikada
#      dolar, yani ucus boyunca hic bosalmaz. 100 KB'a cekildi -> ~1 sn.
#      NOT: RSS'i dusurmuyor (tembel ayriliyor, iki testte de ~200 MB olculdu);
#      kazanc RAM degil, DAYANIKLILIK.
#   2) mcap chunk — varsayilan 768 KiB, 40 KB/s'te ~17 sn. chunkSize 32768
#      yapildi -> tam yukte ~0.4 sn. Anahtar kabul ediliyor, dogrulandi.
#   3) cekirdek sayfa onbellegi — vm.dirty_expire_centisecs 3000 (30 SANIYE).
#      Yukaridaki ikisi duzelse bile veri bu kadar RAM'de bekler. Host
#      tarafinda izleme_kur.sh 7) bolumunde 1 sn'ye cekiliyor.
# Toplam en kotu kayip: ~14.7 sn -> ~2-3 sn.
#
# PARCAYI 1 SN YAPMAK COZUM DEGIL, olculdu: her dosyanin basina 113 sema +
# 160 kanal tanimi yeniden yaziliyor = 307 KB SABIT yuk (30 sn'lik 1.31 MB'lik
# dosyanin %23'u). 1 sn parcada yazma hizi 44 -> ~340 KB/s (7.8 kat), 14 dk
# ucusta 840 dosya / ~286 MB. Asagidaki konu filtresinden sonra bile 185 KB/s.
# Tamponlari kapatmak ayni kazanci bedelsiz veriyor.
#
# KONU FILTRESI (--exclude-regex): bu ucakta FIZIKSEL OLARAK OLMAYAN donanimin
# konulari
# (gimbal, px4flow, optical_flow, wheel_odometry, adsb, rangefinder, ikinci
# GPS...) ve simulasyon/HIL konulari. Olculdu: 117 konudan 74'u hic mesaj
# yayinlamiyor ama semalari her dosyaya yaziliyordu. Bu liste 52 konu atiyor,
# dosya basina 102 KB kazandiriyor; atilanlarin HICBIRINDE veri olmadigi
# dogrulandi.
#   BILEREK TUTULANLAR: esc_status/*, esc_telemetry/* (su an bos, ama ESC
#   telemetrisi acilirsa "ESC'ler elektrigi mi kaybetti" sorusunu TAM bunlar
#   cevaplar — 2 Agustos kazasinda en cok bunlar arandi), butun /swarm/*
#   (surunun kendi trafigi), statustext/recv, status_event, param/event.
#
# SIKISTIRMA mcap'in ICINDE yapilir, rosbag2'nin dosya duzeyinde DEGIL.
# Sebebi olculdu (30 Temmuz): --compression-mode file ile parcalar .mcap.zstd
# olur ve `ros2 bag reindex` bu dosyalari HIC gormez -> "No storage files
# found for reindexing. Abort". metadata.yaml ise yalniz bag DUZGUN kapaninca
# yaziliyor. Ucus her zaman guc kesilerek bittigi icin sonuc su: kayit
# acilamaz. 29 Temmuz kaydinda tam bu oldu — 113 saglam parca, okunamiyor.
# mcap ic sikistirmasiyla parcalar gecerli .mcap dosyasi kalir. Dogrulandi:
# 20 sn kayit + SIGKILL (guc kesintisi taklidi) -> reindex "Reindexing
# complete", yarim kalan son parca dahil 3680 mesaj okundu. Ayni test eski
# ayarla Abort veriyordu.
# Bedeli olculdu: 22 KB/s -> 42 KB/s (1.9 kat). 14 dk ucus ~35 MB, 5 GB
# tavana ~140 ucus sigar. Seviye "Default" secildi; "Fastest" ile yapilan tek
# olcum daha kotu oran verdi (50 KB/s, ama filtre farkliydi — kontrollu
# karsilastirma YAPILMADI). Diskte sikinti cikarsa once burasi denenir.
#
# Kayit klasorunun adi da Istanbul damgali olsun diye TZ gerekiyor; yukarida
# gunluk dizini icin zaten set edildi, burada tekrar edilmiyor.
mkdir -p /ws/kayit
cat > /tmp/mcap_zstd.yaml <<'YAML'
compression: "Zstd"
compressionLevel: "Default"
chunkSize: 32768
YAML

# Bu ucakta olmayan donanim + simulasyon konulari. Tek satirda tutuluyor ki
# rosbag2'ye giden regex'te kaza eseri bosluk olmasin.
KAYIT_HARIC="/mavros/(sim_state/|hil/|px4flow/|optical_flow/|gimbal_control/|mount_control/|landing_target/|camera/|cam_imu_sync/|wheel_odometry/|adsb/|terrain/|rangefinder/|wind_estimation|log_transfer/|mag_calibration/|geofence/|rallypoint/|mission/|debug_value/|gpsstatus/gps2/|imu/diff_pressure|imu/temperature_baro|trajectory/desired|setpoint_trajectory/|nav_controller_output/|target_actuator_control|tunnel/|manual_control/|radio_status|timesync_status)"

KAYIT_DIZIN="/ws/kayit/$(hostname)_$(date +%Y%m%d_%H%M%S)"
if altyapi; then   # --yalniz modunda ATLANIR  (ucus kaydi + trap)
ros2 bag record \
    -e "^(/drone_${AGENT_ID}/|/swarm/|/gozlem/)" \
    --exclude-regex "$KAYIT_HARIC" \
    -o "$KAYIT_DIZIN" \
    --max-bag-duration 30 \
    --max-cache-size 100000 \
    --storage-config-file /tmp/mcap_zstd.yaml \
    >> "$GUNLUK/kayit.log" 2>&1 &
KAYIT_PID=$!

# Konteyner durdurulurken bag'i DUZGUN kapat.
# Docker yalniz PID 1'e (bu script) SIGTERM yollar, cocuklara yollamaz; ayrica
# ros2 bag'in bag'i kapatip indekslemesi icin SIGINT gerekir. Ikisi de
# yapilmazsa kayit yarim/indekssiz kalir ve acilmaz.
kapat() {
    kill -INT "$KAYIT_PID" 2>/dev/null
    wait "$KAYIT_PID" 2>/dev/null
    kill -TERM 0 2>/dev/null
}
trap kapat TERM INT
fi   # /altyapi: ucus kaydi + trap

# --- --yalniz: hedefi dogrula ve ESKI surecini oldur ------------------------
if [ -n "$YALNIZ" ]; then
    _exe="$(_dugum_exe "$YALNIZ")"
    if [ -z "$_exe" ]; then
        echo "[baslat] HATA: --yalniz '$YALNIZ' bilinmiyor."
        echo "[baslat]   Gecerli anahtarlar: origin consensus formasyon sekans ca"
        echo "[baslat]                       manevra fsm gorevfsm mod joystick"
        echo "[baslat]                       gorev1 goru inis rol"
        exit 1
    fi
    if ! acik "$YALNIZ"; then
        echo "[baslat] HATA: '$YALNIZ' /ws/suru_dugumleri icinde YOK — acilmaz."
        echo "[baslat]   Su an acik olanlar: '${SURU_DUGUMLERI}'"
        echo "[baslat]   Once anahtari ekle, sonra --yalniz ile yeniden baslat."
        exit 1
    fi
    echo "[baslat] --yalniz $YALNIZ  (yurutulebilir: $_exe)"
    echo "[baslat]   altyapiya DOKUNULMUYOR: mavros, px4_bridge, agent_fsm,"
    echo "[baslat]   esp32_bridge, ucus kaydi ve gunluk bekcisi calismaya devam eder."
    _dugum_oldur "$_exe"
    echo "[baslat]   eski surecler oldurudu, yeniden baslatiliyor..."
fi

# --- Suru dugumleri: BILEREK OPT-IN ----------------------------------------
# Bunlar simulasyon icin yazildi ve sahada HIC kosmadilar. On dortunu birden
# acmak, bir tuhaflik ciktiginda hangisinden geldigini ayirt edilemez hale
# getirir. Bu yuzden varsayilan olarak HICBIRI acilmiyor; hangisi acilacaksa
# SURU_DUGUMLERI ile ADI verilir:
#
#   SURU_DUGUMLERI="consensus"                       # yalniz lider secimi
#   SURU_DUGUMLERI="consensus formasyon ca"          # + formasyon zinciri
#   SURU_DUGUMLERI="hepsi"                           # tumu (dikkatli)
#
# run_drone.sh bunu -e ile gecirir. Sira onemli: formasyon zinciri
# formation_node -> collision_avoidance -> px4_bridge seklinde akiyor ve
# collision_avoidance ZORUNLU HALKA (setpoint/raw -> setpoint donusumu onda).
# Yalniz formation_node acilirsa setpoint PX4'e HIC ulasmaz.
# CANLI ANAHTAR: /ws/suru_dugumleri dosyasi VARSA env'i EZER.
#
# NEDEN dosya (15 Agustos): env degistirmek konteyneri yeniden YARATMAK
# demek (docker run -e ...). O da mavros'u sifirdan baslatir -> FCU yeniden
# baglanir, RTK yeniden kilitlenir; sahada 1-2 dakika ve bir belirsizlik
# penceresi. Entegrasyon boyunca dugumleri surekli acip kapatacagiz, yani bu
# bedel onlarca kez odenecekti. Dosyaya baglayinca islem sadece:
#
#     echo "consensus" > ~/yelpence_ws/suru_dugumleri && docker restart drone1
#
# yani yeniden YARATMA degil, RESTART. /ws/kacinma ve /ws/ucus_ayarlari.env
# ile ayni deyim — uc bayrak da ayni sekilde davraniyor.
#
# Dosya bicimi: adlar bosluk ya da satirla ayrilir, '#' ile yorum yazilabilir.
#     echo "consensus"            > ~/yelpence_ws/suru_dugumleri
#     echo "consensus formasyon"  > ~/yelpence_ws/suru_dugumleri
#     rm ~/yelpence_ws/suru_dugumleri     # hepsini kapat (env'e geri doner)
#
# Bos dosya = "hicbiri" demek ve env'i yine ezer. Boylece env'de bir sey
# yazsa bile dosyayla hepsini kapatmak mumkun (acil durumda gerekli).
if [ -n "$SURU_DUGUMLERI" ]; then
    echo "[baslat] suru dugumleri: $SURU_DUGUMLERI"

    # Lider secimi. Formasyon yayini buna BAGLI: esp32_bridge'in lider kapisi
    # (KARAR 11) secim/heartbeat gormeden formasyon yayinlamaz.
    # PIL ESIGI agent_fsm ile AYNI degiskenden gelir (BATARYA_KRITIK_V).
    #
    # Neden zorunlu (15 Agustos): consensus'un kendi varsayilani 14.0 V.
    # Ucaklar regulatorden beslendigi icin 3.1 V okuyor ve election.py:29
    #   if rec.battery_v > 0.0 and rec.battery_v < battery_min_v: -> UYGUN DEGIL
    # diyor. Yani HICBIR ajan lider adayi olamaz, secim hic yapilmaz ve
    # esp32_bridge'in lider kapisi acilmadigi icin FORMASYON MESH'E HIC CIKMAZ.
    #
    # Iki yerde ayri sabit tutmamak onemli: pil olcer modul gelince
    # (KARARLAR.md KARAR-03) tek degiskeni 13.6 yapmak ikisini birden acar.
    #
    # AGENT_COUNT "kac ucak ucuyor" DEGIL, "ajan kimlikleri 1..N" demek:
    # consensus_node.py:133  for aid in range(1, agent_count + 1)
    # ile drone1..droneN'in status konularina abone oluyor. Bizim ucaklar
    # 1 ve 3 (ylp01 yerde ama kimligi 2) — 2 yazarsak drone3 HIC DINLENMEZ.
    # Bu yuzden yerde ucak olsa bile 3 kalmali.
    #
    # Eksik kadro secimi engellemez: election.py:101 tam kadro yoksa
    # bootstrap_grace_s (1.5 sn) sonrasi yine secim yapiyor.
    SURU_AJAN_SAYISI="${SURU_AJAN_SAYISI:-3}"
    # ORIGIN — surunun ortak sifir noktasi. consensus'tan ONCE acilmali.
    #
    # NEDEN ONCE (15 Agustos'ta ogrenildi): preflight_checker
    #     if not ctx.sitl_mode and not ctx.origin_synced:
    #         failures.append('Swarm origin senkronize degil')
    # diyor. Yani origin gelmeden IDLE -> ARMING OLMUYOR; ARMING olmadan
    # ARMED olmuyor; ARMED olmadan ajan ELIGIBLE_STATES'e girmiyor ve
    # consensus HIC lider secemiyor. Bu dugum docs/PLAN.md §8'de
    # ADIM 8'de yaziliydi — yanlisti, ADIM 1'in on kosulu.
    #
    # ⚠️ REMAP GECICI: dugum normalde /swarm/internal/origin'a yazar ve
    # esp32_bridge onu mesh'e verir. AMA esp32_bridge yerel olarak
    # /swarm/public/origin'e GERI KOYMUYOR — yani ucak kendi origin'ini
    # goremiyor (YAPILACAKLAR P0.6 "internal/public koprusu eksik").
    # Cozulene kadar dogrudan /public'e yaziyoruz: yerel, mesh'ten
    # bagimsiz, deterministik. Koprü duzelince bu remap KALDIRILACAK.
    #
    # Koordinat /ws/origin dosyasindan: tek satir "lat lon alt".
    #     echo "38.6905999 39.1611543 1216.03" > ~/yelpence_ws/origin
    # Iki ucakta da AYNI olmali, yoksa formasyonlar birbirine gore kayar.
    # IC->DIS KOPRUSU — EN ONCE acilmali.
    #
    # Suru dugumleri kendi ciktilarini /swarm/internal/... a yazar, ama
    # BASKALARININ ciktilarini /swarm/public/... tan okur. Sahada
    # esp32_bridge yalnizca mesh yonunu tasiyordu; ayni ucagin kendi
    # ciktisini kendi public'ine tasiyan YEREL DONGU yoktu. Yani her dugum
    # kendi yanindaki dugumun ciktisini goremiyordu.
    # Ayrinti ve olculen ornekler: ic_dis_kopru.py basligi.
    #
    # Kapatilamaz degil ama kapatilirsa suru dugumleri birbirini gormez;
    # bu yuzden 'origin'/'consensus' gibi ayri bir anahtara BAGLANMADI —
    # herhangi bir suru dugumu aciksa o da acilir.
if altyapi; then   # --yalniz modunda ATLANIR  (ic_dis_kopru)
    ros2 run swarm_control ic_dis_kopru \
        >> "$GUNLUK/ic_dis_kopru.log" 2>&1 &
    sleep 1
    echo "[baslat] ic_dis_kopru basladi (internal -> public yerel dongu)"
fi   # /altyapi: ic_dis_kopru

    if baslat_mi origin; then
        if [ -f /ws/origin ]; then
            read -r O_LAT O_LON O_ALT _ < /ws/origin
            # REMAP KALDIRILDI (15 Agustos): dugum artik sozlesmeye uygun
            # sekilde /swarm/internal/origin'a yaziyor, ic_dis_kopru onu
            # /swarm/public/origin'e tasiyor. Boylece origin AYNI ANDA hem
            # yerel dugumlere hem de esp32_bridge uzerinden mesh'e gidiyor —
            # remap varken mesh yolu tamamen kapaliydi.
            ros2 run swarm_control swarm_origin_publisher --ros-args \
                -p origin_source:=fixed \
                -p fixed_lat:=${O_LAT} \
                -p fixed_lon:=${O_LON} \
                -p fixed_alt:=${O_ALT:-0.0} \
                >> "$GUNLUK/origin.log" 2>&1 &
            sleep 2
            echo "[baslat] swarm_origin_publisher: sabit origin" \
                 "lat=$O_LAT lon=$O_LON alt=${O_ALT:-0.0}"
        else
            echo "[baslat] UYARI: origin istendi ama /ws/origin YOK —" \
                 "dugum acilmadi, preflight ARMING'i REDDEDECEK"
        fi
    fi

    if baslat_mi consensus; then
        ros2 run swarm_core consensus_node --ros-args \
            -p agent_id:=${AGENT_ID} \
            -p agent_count:=${SURU_AJAN_SAYISI} \
            -p battery_min_v:=${BATARYA_KRITIK_V} \
            >> "$GUNLUK/consensus.log" 2>&1 &
        sleep 2
        echo "[baslat] consensus_node basladi" \
             "(agent_count=$SURU_AJAN_SAYISI, battery_min_v=$BATARYA_KRITIK_V)"
    fi

    # `fusion` (kinematic_fusion) anahtari 29 Agustos 2026'da SILINDI.
    # KARAR-01 ile zaten elenmisti: EMA yumusatmasi ~0,4 sn gecikme ekliyor,
    # kacinma komsu verisini ham AgentStatus'tan aliyor.

    # Formasyon zinciri — UCU BIRLIKTE acilir, tek basina anlamsizlar.
    # GOZLEM MODU — /ws/gozlem dosyasi varsa formation_node'un setpoint
    # ciktisi /gozlem/... a yonlendirilir ve UCAGA ULASMAZ.
    #
    # Neden var (docs/PLAN.md §5): simulasyon kullanmiyoruz. Onun
    # yerine dugum GERCEK telemetriyle GERCEK kararlar uretir ama cikisi
    # hicbir yere bagli degildir. Sonra kayittan "uretilen" ile "ucrulan"
    # karsilastirilir. G1 (yerde gozlem) ve G2 (havada gozlem) kademeleri
    # bunun uzerine kurulu; G2 ATLANMAZ.
    #
    # /gozlem/ konulari kayit include regex'ine eklendi — yoksa uretilen
    # veri hicbir yere yazilmaz ve gozlemin anlami kalmazdi.
    GOZLEM_REMAP=""
    if [ -f /ws/gozlem ]; then
        GOZLEM_REMAP="-r /drone_${AGENT_ID}/control/setpoint/raw:=/gozlem/drone_${AGENT_ID}/formation/raw"
        echo "[baslat] *** GOZLEM MODU *** formation_node ciktisi" \
             "/gozlem/drone_${AGENT_ID}/formation/raw a yonlendirildi — UCAGA ULASMIYOR"
    fi

    # ADIM 3 — formasyon zinciri. collision_avoidance BU ANAHTARDAN CIKARILDI:
    # o ADIM 4 ve aktarim kati yuvasini (/control/setpoint/raw ->
    # /control/setpoint) kullaniyor, ayri anahtari var: 'ca'. Ayni yuvaya
    # iki uretici baglanirsa px4_bridge 50 Hz'de celiskili setpoint alir —
    # CLAUDE.md §4'un yasakladigi sey.
    if baslat_mi formasyon; then
        # wing_alpha_deg: kopru, swarm_fsm ve mission1 ile AYNI deger sart,
        # yoksa slot geometrisi sessizce ayrisir.
        # sitl_mode:=false ACIKCA geciliyor (17 Agustos). Dugumun kendi
        # varsayilani da False'a cekildi ama IKI YERDEN baglaniyor: biri
        # unutulursa digeri tutar. Bu bayrak formation_node'da iki guvenlik
        # kapisini atlatiyor — origin_synced ve (xy_valid ve z_valid). True
        # iken dugum origin senkronsuz ve EKF gecersizken de setpoint uretir.
        # 17 Agustos'a kadar depodaki varsayilan True'ydu ve buradan da
        # gecilmiyordu, yani sahada kapilar KAPALI kosuyordu.
        ros2 run swarm_core formation_node --ros-args \
            -p agent_id:=${AGENT_ID} -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
            -p sitl_mode:=false \
            ${GOZLEM_REMAP} \
            >> "$GUNLUK/formation.log" 2>&1 &
        sleep 1
        # path_planner agent_id KABUL ETMIYOR (olculdu) - lider kapisi
        # kopruden isliyor (KARAR 11), dugum her dronda kosuyor.
        # NOT: path_planner URETICI DEGIL, SEKILLENDIRICI — gelen
        # FormationCommand'i ucagin izleyebilecegi hiza YAYIYOR (merkez
        # rampasi + donus rampasi). Komutu mission1 ya da mode_manager
        # uretir; ikisi de kapaliyken bu zincir sessiz kalir.
        #
        # PARAMETRELER 15 AGUSTOS'TA BAGLANDI. Onceden HIC parametre
        # gecilmiyordu ve dugum kendi gomulu varsayilanlariyla kosuyordu —
        # ucus_ayarlari.py'deki seyir hizindan habersiz. Ayni sinifin hatasi
        # 2 Agustos'ta yasanmisti: merkez 3.0 ile kosarken formation_node'un
        # slot rampasi 1.0'da tavan yapiyordu ve suru merkezin gerisinde
        # kaliyordu (bacak basina 5 -> 12.5 -> 20.4 m).
        #
        # ⚠️ Donus tavani 90 -> 25 deg/s dustu (PX4 yaw tavaniyla ayni).
        # Buyuk formasyonda zaten tegetsel hiz baskin: 12 m yaricapta fiili
        # donus 7.16 deg/s, yani 180 derece 25 saniye suruyor.
        ros2 run swarm_core path_planner --ros-args \
            -p max_speed_mps:=${ROTA_MAKS_HIZ} \
            -p control_rate_hz:=${ROTA_ADIM_HZ} \
            -p max_heading_slew_deg_s:=${ROTA_DONUS_TAVANI_DEG_S} \
            -p rot_tangential_speed_mps:=${ROTA_TEGET_HIZ} \
            -p rot_tangential_accel_mps2:=${ROTA_TEGET_IVME} \
            >> "$GUNLUK/planner.log" 2>&1 &
        sleep 1
        echo "[baslat] formation_node + path_planner basladi"
    fi

    # ⚠️ GECICI TEST APARATI — FORMASYON GECIS SEKANSI (28 Agustos).
    # mission1 zinciri sahaya alininca bu anahtar ve dugum SILINECEK.
    #
    # Ne yapar: guided ARM'in urettigi EVENT_MISSION_STARTED'i duyar, kadro
    # hedef irtifaya cikinca CIZGI -> OKBASI -> V tarifini
    # /swarm/internal/formation/target'a basar. Mesh'e yalniz LIDERINKI
    # cikar (kopru kapisi, KARAR 11) — dugum uc ucakta da kosar (sicak
    # yedek, path_planner ile ayni gerekce).
    #
    # 🔴 SOZLESME: bu anahtar ACIKKEN her guided ARM bir test baslangicidir.
    # Normal ucusa donmeden once suru_dugumleri'nden `sekans` SILINMELI.
    #
    # 🔴 formasyon anahtari SART: tarifi ucuran formation_node'dur. Sekans
    # tek basina acilirsa tarif mesh'e cikar ama hicbir ucak uymaz — sessiz
    # bosluk olmasin diye burada acikca reddediliyor.
    if baslat_mi sekans; then
        if ! acik formasyon; then
            echo "[baslat] HATA: 'sekans' istendi ama 'formasyon' kapali —" \
                 "tarifi ucuracak formation_node yok. formasyon_sekans" \
                 "ACILMADI." | tee -a "$GUNLUK/sekans.log"
        else
            if ! acik consensus; then
                echo "[baslat] UYARI: 'sekans' acik ama 'consensus' kapali —" \
                     "lider secilemez, tarif mesh'e HIC cikmaz" \
                     "(form_lider_degil sayaci artar)."
            fi
            # Kadro paramı SURU_KADRO'dan (bosluklu liste -> ROS dizisi).
            # fazlar/faz_sure_s VIRGULLU STRING gider — dizi olarak
            # gecirilen [25,25,25] YAML'da INTEGER_ARRAY sayilip dugumu
            # acilista olduruyordu (28 Agu G0 bulgusu, sekans.log).
            _SEKANS_KADRO="${SURU_KADRO:-1 2 3}"
            _SEKANS_KADRO_ROS="[$(echo ${_SEKANS_KADRO} | tr ' ' ',')]"
            ros2 run swarm_core formasyon_sekans --ros-args \
                -p agent_id:=${AGENT_ID} \
                -p kadro:="${_SEKANS_KADRO_ROS}" \
                -p aralik_m:=${SEKANS_ARALIK:-7.0} \
                -p irtifa_m:=${SEKANS_IRTIFA:-8.0} \
                -p fazlar:="'${SEKANS_FAZLAR:-cizgi,okbasi,v,cizgi}'" \
                -p faz_sure_s:="'${SEKANS_FAZ_SURELERI:-25,25,25,20}'" \
                -p kurulum_hiz_mps:=${SEKANS_KURULUM_HIZ:-2.5} \
                -p gecis_hiz_mps:=${SEKANS_GECIS_HIZ:-1.5} \
                -p kalkis_esik_orani:=${SEKANS_KALKIS_ESIK:-0.8} \
                -p kalkis_zaman_asimi_s:=${SEKANS_KALKIS_ZAMAN_ASIMI:-90.0} \
                -p eve_sure_s:=${SEKANS_EVE_SURE:-25.0} \
                -p kanat_alfa_deg:=${KANAT_ALFA_DEG} \
                >> "$GUNLUK/sekans.log" 2>&1 &
            sleep 1
            echo "[baslat] formasyon_sekans basladi (GECICI TEST:" \
                 "aralik=${SEKANS_ARALIK:-7.0} m," \
                 "fazlar=${SEKANS_FAZLAR:-cizgi,okbasi,v,cizgi}," \
                 "kadro=${_SEKANS_KADRO}) — her guided ARM sekansi tetikler"
        fi
    fi

    # ADIM 4 — KARAR-01. Tek kacinma dugumu; /raw -> /setpoint aktarim kati.
    if baslat_mi ca; then
        # Komsu listesi: kendisi haric butun filo. Olmayan drone'a abone
        # olmak zararsiz — veri gelmezse komsu yok sayilir.
        CA_KOMSULAR=$(echo "1 2 3" | tr ' ' '\n' \
                      | grep -v "^${AGENT_ID}$" | paste -sd, -)
        # ESIKLER ucus_ayarlari.py TEK KAYNAGINDAN (--kabuk uretir).
        #
        # neighbor_rx_stale_s: dugum varsayilani 0.5 idi — mesh ~5-7 Hz
        # ve ~%30 kayipli, iki-uc ardisik kayipta komsu dusuyor ve CA
        # SESSIZCE korumasiz kaliyor. Sahada kullanilan deger 1.5.
        #
        # KARAR-01 Secenek C: komsu verisi mesh'ten gelen ham
        # AgentStatus'tan aliniyor (komsu_adaptoru.py) — araya yumusatma
        # girmiyor, cunku EMA ~0,4 sn gecikme ekliyordu.
        # DIKEY YOL VERME — 23 Agustos 2026, operator karari.
        #
        # Birincil kacis DIKEY: catisan ucaklardan kimligi buyuk olan,
        # kucugun OLCULEN irtifasindan KATMAN kadar uzaga gider. Yatay
        # itme SON CARE — yalnizca `hard` kabugunun icinde acilir.
        #
        # RUTBE (donusumlu merdiven) kadrodan turetiliyor: kimligimin
        # `1,AGENT_ID..N` siralamasindaki indeksi. rutbe 1 -> +katman,
        # rutbe 2 -> -katman, rutbe 3 -> +2*katman ...
        # Sabit olmasi SART: anlik catisma kumesinden turetilseydi iki
        # ucak ayni katmani secebilirdi (benzetimde olculdu).
        # RUTBE, ABONELIK LISTESINDEN DEGIL UCAN KADRODAN turetilir.
        #
        # CA_KOMSULAR "kime abone olayim" listesi ve olmayan drone'u
        # icermesi zararsiz. Ama RUTBE oyle degil: ylp01 (id 2) yerde
        # dururken onu saymak ylp02'yi rutbe 1 yerine rutbe 2 yapiyor
        # ve donusumlu merdivende YON DEGISTIRIYOR (yukari yerine
        # asagi). Yani yerde duran bir ucak, ucanlarin kacis yonunu
        # belirliyordu.
        #
        # SURU_KADRO = GERCEKTEN ucan kimlikler.
        # 25 Agustos 2026: ylp01 DONDU (kaldirma testi gecti) -> "1 2 3"
        # yapildi (KARAR-04). DIKKAT: bu degisiklikle ylp02'nin rutbesi
        # 1 -> 2 oldu, dikey kacis yonu YUKARIDAN ASAGIYA dondu
        # (donusumlu merdiven). Alcakta 4 m irtifa tabani kelepcesi
        # asagi kacisi yukariya cevirir (birim testli).
        SURU_KADRO="${SURU_KADRO:-1 2 3}"
        CA_RUTBE=0
        for _k in $SURU_KADRO; do
            [ "$_k" -lt "$AGENT_ID" ] 2>/dev/null && \
                CA_RUTBE=$((CA_RUTBE + 1))
        done
        ros2 run swarm_core collision_avoidance --ros-args \
            -p agent_id:=${AGENT_ID} \
            -p neighbor_ids:="[$CA_KOMSULAR]" \
            -p rutbe:=${CA_RUTBE} \
            -p d0_m:=${KACINMA_D0:-4.0} \
            -p hard_m:=${KACINMA_HARD:-2.5} \
            -p katman_m:=${KACINMA_KATMAN:-3.0} \
            -p v_dikey_max_mps:=${KACINMA_DIKEY_HIZ:-1.2} \
            -p a_dikey_max_mps2:=${KACINMA_DIKEY_IVME:-2.0} \
            -p kp_dikey:=${KACINMA_DIKEY_KP:-2.0} \
            -p hist_m:=${KACINMA_HIST:-2.5} \
            -p korluk_yer_esigi_m:=${KACINMA_KORLUK_YER:-1.5} \
            -p k_dikey:=${KACINMA_K_DIKEY:-1.0} \
            -p k_yatay:=${KACINMA_K_YATAY:-1.0} \
            -p neighbor_rx_stale_s:=${KACINMA_BAYAT_S:-1.5} \
            -p slew_normal_mps2:=${KACINMA_IVME_NORMAL:-3.58} \
            -p slew_emergency_mps2:=${KACINMA_IVME_ACIL:-5.66} \
            -p donus_ivme_mps2:=${KACINMA_DONUS_IVME:-0.5} \
            >> "$GUNLUK/ca.log" 2>&1 &
        sleep 1
        echo "[baslat] collision_avoidance basladi (komsular: $CA_KOMSULAR," \
             "rutbe=$CA_RUTBE, d0=${KACINMA_D0:-4.0} hard=${KACINMA_HARD:-2.5}," \
             "DIKEY katman=${KACINMA_KATMAN:-3.0} hist=${KACINMA_HIST:-2.5}" \
             "v=${KACINMA_DIKEY_HIZ:-1.2}"\
             "a=${KACINMA_DIKEY_IVME:-2.0} kp=${KACINMA_DIKEY_KP:-2.0}," \
             "yatay SON CARE (hard icinde)," \
             "ivme normal=${KACINMA_IVME_NORMAL:-3.58} acil=${KACINMA_IVME_ACIL:-5.66}" \
             "donus=${KACINMA_DONUS_IVME:-0.5})"
    fi

    # Manevra (pitch/roll/yaw) — formasyon zinciri acikken anlamli.
    if baslat_mi manevra; then
        ros2 run swarm_core maneuver_executor --ros-args \
            -p agent_id:=${AGENT_ID} >> "$GUNLUK/manevra.log" 2>&1 &
        sleep 1
    fi

    # Suru/gorev FSM'leri. KARAR 1/2: her dronda kosar, SwarmState yerel uretilir.
    # UC DUGUM AYRILDI (15 Agustos). Onceden 'fsm' anahtari swarm_fsm,
    # mission_fsm ve mode_manager'i BIRLIKTE aciyordu — ama entegrasyon
    # sirasinda bunlar ADIM 2, ADIM 6 ve ADIM 12. Ucunu birden acmak, bir
    # tuhaflik ciktiginda hangisinden geldigini ayirt edilemez yapiyordu ki
    # bu dosyanin en basindaki opt-in kuralinin tam olarak onlemek istedigi
    # sey. Artik ayri anahtarlar: fsm / gorevfsm / mod.
    #
    # DIKKAT: mission_fsm ve mode_manager agent_id KABUL ETMIYOR (olculdu).
    # swarm_fsm ise 15 Agustos'ta agent_id ALIR HALE GELDI — kendi ucaginin
    # durumunu /swarm/internal/drone{id}/status'tan okuyabilsin diye. Bkz.
    # swarm_fsm_node.py'deki agent_id yorumu: bu olmadan iki ucakli suruda
    # tek komsu bayatlayinca TUM SURUYE acil inis yayinlaniyordu.
    if baslat_mi fsm; then
        # SURU_AJAN_SAYISI  = kimlik araligi (1..N), abonelikler bundan
        # SURU_BEKLENEN_UCAK = kac ucak GERCEKTEN uculuyor
        #
        # Ikisi ayri olmak ZORUNDA (15 Agustos'ta olculdu): tek deger
        # kullanilinca celisiyorlardi —
        #   formation_reached: active >= expected -> 2 >= 3 FALSE, FORMING'de takilir
        #   saglik orani     : healthy/expected < 0.5 -> 1/3 = 0.33 ile
        #                      iki ucaktan biri bozulunca TUM SURUYE acil inis
        # 25 Agustos 2026: ylp01 dondu, filo uc ucak -> 3 yapildi (KARAR-04).
        SURU_BEKLENEN_UCAK="${SURU_BEKLENEN_UCAK:-3}"
        ros2 run swarm_state_machine swarm_fsm_node --ros-args \
            -p agent_id:=${AGENT_ID} \
            -p agent_count:=${SURU_AJAN_SAYISI} \
            -p expected_agent_count:=${SURU_BEKLENEN_UCAK} \
            -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
            >> "$GUNLUK/swarm_fsm.log" 2>&1 &
        sleep 1
        echo "[baslat] swarm_fsm_node basladi" \
             "(kimlik araligi=$SURU_AJAN_SAYISI, beklenen ucak=$SURU_BEKLENEN_UCAK)"
    fi

    # ADIM 6 — gorev durum makinesi. Her IKI gorevi de bu suruyor.
    if baslat_mi gorevfsm; then
        # team_id: kopru ve mission1 ile AYNI olmali (QR filtresi).
        ros2 run swarm_state_machine mission_fsm_node --ros-args \
            -p team_id:="'${TAKIM_ID}'" >> "$GUNLUK/mission_fsm.log" 2>&1 &
        sleep 1
        echo "[baslat] mission_fsm_node basladi (team_id=$TAKIM_ID)"
    fi

    # ADIM 12 — Gorev 2 (yari otonom) mod yoneticisi.
    #
    # 🔴 'formasyon' SART: HAREKET modu tarifi formation_node ucurur;
    # formation_node yoksa hareket modu sessizce bos kalir (sekans
    # anahtarindaki kuralin aynisi). MANEVRA modunda mode_manager /raw'a
    # kendisi yazar ve formation_node'u /swarm/internal/mode/
    # formasyon_sustur bayragiyla susturur (28 Agu, KARAR-11).
    # test_hazir_atla BAYRAK DOSYASIYLA acilir: /ws/mod_test
    #
    # NEDEN ENV DEGIL (30 Agustos 2026, denetimde bulundu): env
    # /ws/ucus_ayarlari.env'den geliyor ve o dosyayi `ucus_ayarlari.py
    # --kabuk` URETIYOR — elle eklenen satir bir sonraki dagitimda
    # SILINIRDI. Ustelik bu bir UCUS AYARI degil TEST kipi; ucus
    # ayarlarinin tek kaynagina test bayragi koymak kategori hatasi olur
    # ve birinin onu `true` commit'lemesi an meselesi.
    # Bayrak dosyasi projenin kendi deyimi (gozlem, yer_testi) ve
    # `drone_bul.sh --durum` listesinde gorunur.
    #
    # NE YAPAR: mission_fsm kapaliyken mode_manager FSM'ini READY'ye
    # ulastirir (B3). KALKIS KAPISINI (B15) BAYPAS ETMEZ — READY olcutu
    # yine "gercekten havada mi".
    _MOD_TEST_HAZIR=false
    if [ -f /ws/mod_test ]; then
        _MOD_TEST_HAZIR=true
    fi

    if baslat_mi mod; then
        if ! acik formasyon; then
            echo "[baslat] HATA: 'mod' istendi ama 'formasyon' kapali —" \
                 "hareket modunun tarifini ucuracak formation_node yok." \
                 "mode_manager ACILMADI." | tee -a "$GUNLUK/mode_manager.log"
        else
            # B16 (30 Agustos 2026) — 'fsm' KAPI DEGIL, UYARI. NEDEN:
            #
            # Plan bunu 'formasyon'un esi bir KAPI olarak yazmisti; gerekce
            # "fsm kapaliysa SwarmState gelmez, mode_manager'in centroid'i
            # (0,0,0)'da kalir ve suru NED origin'e gider" idi. Uygulamadan
            # once kod okundu ve gerekce ARTIK GECERLI DEGIL:
            #
            #   * B15 KALKIS KAPISI centroid'i ucaklarin KENDI konumundan
            #     tohumluyor; SwarmState'e ihtiyac kalmadi.
            #   * SwarmState.formation_heading_deg ZATEN hep 0.0 —
            #     swarm_fsm o alani hicbir yerde HESAPLAMIYOR (B17).
            #   * formation_reached / formation_stable ctx'e yaziliyor ama
            #     HICBIR YERDE OKUNMUYOR (olculdu).
            #
            # Yani 'fsm' kapaliyken mode_manager bugun islevsel bir sey
            # KAYBETMIYOR. Calisan bir yapilandirmayi HATA ile durdurmak
            # yanlis olurdu. Ama sessiz de birakmiyoruz: kanitlanmis yigin
            # 'origin consensus fsm formasyon ca' ve ondan sapma gorunur olmali.
            if ! acik fsm; then
                echo "[baslat] UYARI: 'mod' acik ama 'fsm' KAPALI." \
                     "mode_manager aciliyor (B15 centroid'i ucaklardan" \
                     "tohumluyor, SwarmState sart degil) — ama bu" \
                     "kanitlanmis yigindan SAPMA. Bilerek yaptiysan sorun yok." \
                     | tee -a "$GUNLUK/mode_manager.log"
            fi
            _MOD_KADRO="${SURU_KADRO:-1 2 3}"
            _MOD_KADRO_ROS="[$(echo ${_MOD_KADRO} | tr ' ' ',')]"
            ros2 run swarm_state_machine mode_manager_node --ros-args \
                -p agent_ids:="${_MOD_KADRO_ROS}" \
                -p default_spacing_m:=${MOD_ARALIK:-7.0} \
                -p max_speed_mps:=${MOD_HIZ:-2.0} \
                -p max_yaw_rate_deg_s:=${MOD_YAW_HIZI:-25.0} \
                -p max_tilt_deg:=${MOD_EGIM_TAVANI:-15.0} \
                -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
                -p kalkis_esik_m:=${MOD_KALKIS_ESIK:-2.0} \
                -p test_hazir_atla:=${_MOD_TEST_HAZIR} \
                >> "$GUNLUK/mode_manager.log" 2>&1 &
            sleep 1
            echo "[baslat] mode_manager_node basladi (Gorev 2:" \
                 "egim=${MOD_EGIM_TAVANI:-15.0} deg," \
                 "yaw=${MOD_YAW_HIZI:-25.0} deg/s, hiz=${MOD_HIZ:-2.0} m/s," \
                 "aralik=${MOD_ARALIK:-7.0} m, kadro=${_MOD_KADRO}," \
                 "kalkis kapisi=${MOD_KALKIS_ESIK:-2.0} m," \
                 "test_hazir_atla=${_MOD_TEST_HAZIR} $([ "$_MOD_TEST_HAZIR" = true ] \
                    && echo '<- /ws/mod_test VAR: FSM yerde READY olur, ucus icin SIL'))"
        fi
    fi

    # Gorev 2 kumanda GIRIS ucu — joystick_interpreter.
    #
    # 🔴 YALNIZ PILOT UCAGINDA ACILIR (suru_dugumleri dosyasina 'joystick'
    # yalniz o ucakta yazilir). Her ucagin kendi RC alicisi var; uc ucakta
    # birden acilirsa UC kumanda birden mesh'e komut basar (kill-switch
    # pilotlarinin cubuklari dahil) — coklu uretici kaosu. Sartname:
    # "TEK bir joystick veya RC kumanda".
    #
    # Dugumun MAVROS abonelikleri KOKSUZ yazilmis (/mavros/rc/in) —
    # sahadaki ad alani /drone_N/mavros: remap SART, yoksa hic veri
    # gelmez ve HATA DA VERMEZ (TUZAKLAR'daki koksuz-ad sinifi).
    if baslat_mi joystick; then
        # ADIM 12a — SURU kumandasinin i-BUS koprusu (30 Agustos 2026, B1).
        #
        # 🔴 SURU KUMANDASI PIXHAWK'TAN GELMEZ. Sartname 5.2 her IHA icin
        # kill switch'e AYRI kumanda + AYRI pilot zorunlu kiliyor ve
        # Pixhawk'in tek RC girisi ONA ait (CH5 kill, CH8 arm, CH3
        # failsafe 2100). Suru kumandasinin alicisi Pi'ye i-BUS ile
        # bagli; cerceveyi rc_ibus_kopru RCIn'e cevirir.
        ros2 run swarm_control rc_ibus_kopru --ros-args \
            -p agent_id:=${AGENT_ID} \
            -p port:="'${SURU_RC_PORT:-/dev/ttyUSB0}'" \
            >> "$GUNLUK/rc_ibus.log" 2>&1 &
        sleep 1
        echo "[baslat] rc_ibus_kopru basladi (port=${SURU_RC_PORT:-/dev/ttyUSB0}" \
             "-> /drone_${AGENT_ID}/rc/suru)"

        # ADIM 12b — yorumlayici. REMAP'LER SURU ALICISINA BAKAR.
        #
        # 🔴 IKISI DE CEVRILMEK ZORUNDA. Biri kill pilotunun alicisinda
        # kalirsa o kumanda suruyu surer ve isaretler TERS calisir:
        # suru zinciri CH5'i EMNIYET, CH8'i KALKIS/INIS saniyor —
        # yani KILL SWITCH'I KALDIRMAK KOMUTLARI ACAR, ARM SWITCH'I
        # KALKIS TETIKLER. manual_control OLU bir konuya cevriliyor:
        # PX4 kill pilotunun cubuklarindan MANUAL_CONTROL uretiyor ve
        # o da ayni callback'i besliyordu (gorev2.md B11).
        ros2 run swarm_state_machine joystick_interpreter_node --ros-args \
            -p max_speed_mps:=${MOD_HIZ:-2.0} \
            -p max_yaw_rate_deg_s:=${MOD_YAW_HIZI:-25.0} \
            -p max_tilt_deg:=${MOD_EGIM_TAVANI:-15.0} \
            -p deadman_timeout_s:=${MOD_DEADMAN_ZAMAN_ASIMI:-0.5} \
            -p default_spacing_m:=${MOD_ARALIK:-7.0} \
            -r /mavros/rc/in:=/drone_${AGENT_ID}/rc/suru \
            -r /mavros/manual_control/control:=/drone_${AGENT_ID}/rc/manual_control_KAPALI \
            >> "$GUNLUK/joystick.log" 2>&1 &
        sleep 1
        echo "[baslat] joystick_interpreter basladi — BU UCAK PILOT UCAGI:" \
             "SURU alicisindan surer (SwA emniyet, SwB mod," \
             "SwC formasyon, SwD kalkis/inis). Kill pilotunun alicisi" \
             "px4_bridge'de kalir, suruye DOKUNMAZ."
    fi

    # Gorev 1 orkestratoru. KARAR 10: her dronda kosar (sicak yedek).
    if baslat_mi gorev1; then
        ros2 run swarm_missions mission1_dynamic_swarm --ros-args \
            -p agent_id:=${AGENT_ID} -p team_id:="'${TAKIM_ID}'" \
            -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
            >> "$GUNLUK/mission1.log" 2>&1 &
        sleep 1
    fi

    # Kamera + goru. Kamera donanimi olmayan dronda camera_driver hata dongusune
    # girer, o yuzden ayri anahtar.
    if baslat_mi goru; then
        ros2 run swarm_perception camera_driver --ros-args \
            -p agent_id:=${AGENT_ID} >> "$GUNLUK/kamera.log" 2>&1 &
        sleep 2
        ros2 run swarm_perception vision_node --ros-args \
            -p agent_id:=${AGENT_ID} >> "$GUNLUK/goru.log" 2>&1 &
        sleep 1
    fi

    # Hassas inis — goru acikken anlamli (inis bolgesi kameradan geliyor).
    if baslat_mi inis; then
        ros2 run swarm_core precision_landing_node --ros-args \
            -p agent_id:=${AGENT_ID} >> "$GUNLUK/inis.log" 2>&1 &
        sleep 1
    fi

    # Rol yeniden dagitim.
    if baslat_mi rol; then
        # task_reallocator agent_id KABUL ETMIYOR (olculdu).
        ros2 run swarm_core task_reallocator_node \
            >> "$GUNLUK/rol.log" 2>&1 &
        sleep 1
    fi
else
    echo "[baslat] suru dugumleri KAPALI (SURU_DUGUMLERI bos)"
fi

# --- ACILISTA KAYIT ONARIMI — 20 Agustos 2026 --------------------------------
#
# OLCULDU: ylp00'da 60 kayittan 60'inda, ylp02'de 50'den 50'sinde
# metadata.yaml YOKTU ve `ros2 bag info` hicbirini acamiyordu. Sebep pil
# degisimi: guc kesilince yukaridaki `kapat` tuzagi HIC calismiyor (sinyal
# gelmiyor), rosbag2 metadata'yi yazamiyor. Bkz. TUZAKLAR 1.19.
#
# Onarim burada, EN SONA konuldu ve UC KORUMASI var — acilis yolunu bozmak
# P0.13'te tam olarak duzeltilen seydi:
#   1) arka planda (&)      -> `wait`'e ve dugumlere hic dokunmaz
#   2) `timeout 600`        -> takilirsa kendi kendini keser
#   3) betik icinde: aktif kayit ve son 120 sn'de dokunulmus dizin ATLANIR
#
# Yani en kotu durumda onarim yapilmaz; ucusu geciktirmesi mumkun degil.
if altyapi; then   # --yalniz modunda ATLANIR  (kayit onarimi)
if [ -f /ws/kayit_onar.sh ]; then
    (
        timeout 600 bash /ws/kayit_onar.sh >> "$GUNLUK/kayit_onar.log" 2>&1
        echo "[onar] cikis=$? ($(date +%H:%M:%S))" >> "$GUNLUK/kayit_onar.log"
    ) &
    echo "[baslat] kayit onarimi arka planda basladi -> $GUNLUK/kayit_onar.log"
fi
fi   # /altyapi: kayit onarimi

if altyapi; then
    echo "tum dugumler basladi (kayit: $KAYIT_DIZIN)"
else
    # --yalniz: KAYIT_DIZIN yalnizca hesaplandi, YENI kayit ACILMADI.
    # Eski mesaj burada yeni bir dizin adi basip "ucusum hangi kayitta"
    # sorusunu yaniltiyordu (29 Agustos, sahada goruldu).
    echo "[baslat] --yalniz $YALNIZ TAMAM — altyapi ve ucus kaydi dokunulmadi"
fi
if altyapi; then   # --yalniz modunda ATLANIR  (wait — yalniz modunda beklemez, cikar)
wait
fi   # /altyapi: wait — yalniz modunda beklemez, cikar
