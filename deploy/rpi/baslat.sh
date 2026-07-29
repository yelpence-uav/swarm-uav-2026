#!/bin/bash
# Drone tarafi tam zincir: Pixhawk -> MAVROS -> px4_bridge -> agent_fsm -> esp32_bridge -> mesh
# AGENT_ID env ile parametrik (verilmezse 1 = eski ylp00 davranisi). ns=/drone_${AGENT_ID}.
# Konteynere run_drone.sh ile -e AGENT_ID=<N> gecilir. Drone'da /ws/baslat.sh olarak durur.
AGENT_ID="${AGENT_ID:-1}"
echo "[baslat] AGENT_ID=$AGENT_ID"
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
# En yeni 10 acilis tutulur; dosyalar kucuk, ayri disk tavani gerekmiyor.
# Budama -type d ile yapiliyor, boylece asagidaki 'son' sembolik bagi
# hedefiyle birlikte silinmiyor.
export TZ=Europe/Istanbul
GUNLUK="/ws/gunluk/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$GUNLUK"
find /ws/gunluk -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | tail -n +11 | cut -d' ' -f2- | xargs -r rm -rf
# Bag GORELI olmak zorunda: mutlak verilirse '/ws/gunluk/<damga>'i gosterir ve
# host'ta /ws diye bir yol olmadigi icin ~/yelpence_ws/gunluk/son KIRIK cikar
# (olculdu). Sadece dizin adi verilince iki taraftan da cozuluyor.
ln -sfn "$(basename "$GUNLUK")" /ws/gunluk/son   # ~/yelpence_ws/gunluk/son/mavros.log
echo "[baslat] gunlukler: $GUNLUK"

ros2 run mavros mavros_node --ros-args -r __ns:=/drone_${AGENT_ID}/mavros -p fcu_url:=/dev/ttyAMA0:921600 > "$GUNLUK/mavros.log" 2>&1 &
sleep 15
ros2 run swarm_control px4_bridge --ros-args -p agent_id:=${AGENT_ID} > "$GUNLUK/px4b.log" 2>&1 &
sleep 5
ros2 run swarm_state_machine agent_fsm_node --ros-args -p agent_id:=${AGENT_ID} > "$GUNLUK/fsm.log" 2>&1 &
sleep 5
# MAVLink yayin hizlari: FCU her resetlendiginde sifirlanir, her aciliste yeniden istenir
python3 /ws/mesaj_hizlari.py > "$GUNLUK/hizlar.log" 2>&1
sleep 2
ros2 run swarm_control esp32_bridge --ros-args -p serial_port:=/dev/ttyAMA4 -p baud:=460800 -p agent_id:=${AGENT_ID} > "$GUNLUK/esp.log" 2>&1 &

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
# 30 sn'lik parcalar: ucus 13-14 dk suruyor. Kaza aninda ACIK olan parca
# risk altindadir; 30 sn'de en fazla 30 sn kaybedilir. ros2 bag klasorun
# tamamini metadata.yaml uzerinden TEK kayit olarak gorur, parcalanma
# analizi zorlastirmaz.
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
YAML
KAYIT_DIZIN="/ws/kayit/$(hostname)_$(date +%Y%m%d_%H%M%S)"
ros2 bag record \
    -e "^(/drone_${AGENT_ID}/|/swarm/)" \
    -o "$KAYIT_DIZIN" \
    --max-bag-duration 30 \
    --storage-config-file /tmp/mcap_zstd.yaml \
    > "$GUNLUK/kayit.log" 2>&1 &
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

echo "tum dugumler basladi (kayit: $KAYIT_DIZIN)"
wait
