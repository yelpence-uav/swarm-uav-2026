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
# tgt_system = AGENT_ID. NEDEN: PX4'lerin hepsi fabrika ayari MAV_SYS_ID=1
# ile geliyordu ve QGC araclari SYSID ile ayirt ediyor — ikisi de 1 olunca
# QGC ikisini TEK ARAC sanip telemetriyi karistiriyor (31 Temmuz'da UDP
# 14550 dinlenerek olculdu: iki farkli IP'den gelen paketlerin hepsi
# sysid=1). Her drone'un MAV_SYS_ID'si kendi AGENT_ID'si yapiliyor;
# MAVROS'un hedef sistemi de ayni olmak ZORUNDA, yoksa FCU ile konusamaz.
ros2 run mavros mavros_node --ros-args -r __ns:=/drone_${AGENT_ID}/mavros \
    -p fcu_url:=/dev/ttyAMA0:921600 \
    -p tgt_system:=${AGENT_ID} \
    ${GCS_URL:+-p gcs_url:="$GCS_URL"} \
    > "$GUNLUK/mavros.log" 2>&1 &
[ -n "$GCS_URL" ] && echo "[baslat] MAVLink QGC'ye iletiliyor: $GCS_URL"
echo "[baslat] MAVROS tgt_system=$AGENT_ID (PX4 MAV_SYS_ID ile ayni olmali)"
sleep 15
ros2 run swarm_control px4_bridge --ros-args -p agent_id:=${AGENT_ID} > "$GUNLUK/px4b.log" 2>&1 &
sleep 5
ros2 run swarm_state_machine agent_fsm_node --ros-args -p agent_id:=${AGENT_ID} > "$GUNLUK/fsm.log" 2>&1 &
sleep 5
# MAVLink yayin hizlari: FCU her resetlendiginde sifirlanir, her aciliste yeniden istenir
python3 /ws/mesaj_hizlari.py > "$GUNLUK/hizlar.log" 2>&1
sleep 2
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
ros2 run swarm_control esp32_bridge --ros-args -p serial_port:=/dev/ttyAMA4 -p baud:=460800 -p agent_id:=${AGENT_ID} -p team_id:="'${TAKIM_ID}'" -p wing_alpha_deg:=${KANAT_ALFA_DEG} > "$GUNLUK/esp.log" 2>&1 &

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

# --- Suru dugumleri: BILEREK OPT-IN ----------------------------------------
# Bunlar simulasyon icin yazildi ve sahada HIC kosmadilar. On dortunu birden
# acmak, bir tuhaflik ciktiginda hangisinden geldigini ayirt edilemez hale
# getirir. Bu yuzden varsayilan olarak HICBIRI acilmiyor; hangisi acilacaksa
# SURU_DUGUMLERI ile ADI verilir:
#
#   SURU_DUGUMLERI="consensus"                       # yalniz lider secimi
#   SURU_DUGUMLERI="consensus fusion"                # + komsu yumusatma
#   SURU_DUGUMLERI="consensus fusion formasyon"      # + formasyon zinciri
#   SURU_DUGUMLERI="hepsi"                           # tumu (dikkatli)
#
# run_drone.sh bunu -e ile gecirir. Sira onemli: formasyon zinciri
# formation_node -> collision_avoidance -> px4_bridge seklinde akiyor ve
# collision_avoidance ZORUNLU HALKA (setpoint/raw -> setpoint donusumu onda).
# Yalniz formation_node acilirsa setpoint PX4'e HIC ulasmaz.
SURU_DUGUMLERI="${SURU_DUGUMLERI:-}"

acik() {
    case " $SURU_DUGUMLERI " in
        *" hepsi "*) return 0 ;;
        *" $1 "*)    return 0 ;;
        *)           return 1 ;;
    esac
}

if [ -n "$SURU_DUGUMLERI" ]; then
    echo "[baslat] suru dugumleri: $SURU_DUGUMLERI"

    # Lider secimi. Formasyon yayini buna BAGLI: esp32_bridge'in lider kapisi
    # (KARAR 11) secim/heartbeat gormeden formasyon yayinlamaz.
    if acik consensus; then
        ros2 run swarm_core consensus_node --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/consensus.log" 2>&1 &
        sleep 2
    fi

    # Komsu telemetrisini yumusatir (EMA). Formasyon oncesi acilmasi mantikli:
    # slot atamasi komsu konumlarina bakiyor.
    if acik fusion; then
        ros2 run swarm_perception kinematic_fusion --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/fusion.log" 2>&1 &
        sleep 2
    fi

    # Formasyon zinciri — UCU BIRLIKTE acilir, tek basina anlamsizlar.
    if acik formasyon; then
        # wing_alpha_deg: kopru ve mission1 ile AYNI deger sart, yoksa slot
        # geometrisi sessizce ayrisir.
        ros2 run swarm_core formation_node --ros-args \
            -p agent_id:=${AGENT_ID} -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
            > "$GUNLUK/formation.log" 2>&1 &
        sleep 1
        ros2 run swarm_core collision_avoidance --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/ca.log" 2>&1 &
        sleep 1
        # path_planner agent_id KABUL ETMIYOR (olculdu) - lider kapisi
        # kopruden isliyor (KARAR 11), dugum her dronda kosuyor.
        ros2 run swarm_core path_planner \
            > "$GUNLUK/planner.log" 2>&1 &
        sleep 1
    fi

    # Manevra (pitch/roll/yaw) — formasyon zinciri acikken anlamli.
    if acik manevra; then
        ros2 run swarm_core maneuver_executor --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/manevra.log" 2>&1 &
        sleep 1
    fi

    # Suru/gorev FSM'leri. KARAR 1/2: her dronda kosar, SwarmState yerel uretilir.
    if acik fsm; then
        # DIKKAT: bu ucu agent_id KABUL ETMIYOR (olculdu). Gecirmek zararsiz
        # ama yaniltici olurdu - "id gecti sanip" yanlis yerde aranir.
        ros2 run swarm_state_machine swarm_fsm_node \
            > "$GUNLUK/swarm_fsm.log" 2>&1 &
        sleep 1
        # team_id: kopru ve mission1 ile AYNI olmali (QR filtresi).
        ros2 run swarm_state_machine mission_fsm_node --ros-args \
            -p team_id:="'${TAKIM_ID}'" > "$GUNLUK/mission_fsm.log" 2>&1 &
        sleep 1
        ros2 run swarm_state_machine mode_manager_node \
            > "$GUNLUK/mode_manager.log" 2>&1 &
        sleep 1
    fi

    # Gorev 1 orkestratoru. KARAR 10: her dronda kosar (sicak yedek).
    if acik gorev1; then
        ros2 run swarm_missions mission1_dynamic_swarm --ros-args \
            -p agent_id:=${AGENT_ID} -p team_id:="'${TAKIM_ID}'" \
            -p wing_alpha_deg:=${KANAT_ALFA_DEG} \
            > "$GUNLUK/mission1.log" 2>&1 &
        sleep 1
    fi

    # Kamera + goru. Kamera donanimi olmayan dronda camera_driver hata dongusune
    # girer, o yuzden ayri anahtar.
    if acik goru; then
        ros2 run swarm_perception camera_driver --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/kamera.log" 2>&1 &
        sleep 2
        ros2 run swarm_perception vision_node --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/goru.log" 2>&1 &
        sleep 1
    fi

    # Hassas inis — goru acikken anlamli (inis bolgesi kameradan geliyor).
    if acik inis; then
        ros2 run swarm_core precision_landing_node --ros-args \
            -p agent_id:=${AGENT_ID} > "$GUNLUK/inis.log" 2>&1 &
        sleep 1
    fi

    # Rol yeniden dagitim.
    if acik rol; then
        # task_reallocator agent_id KABUL ETMIYOR (olculdu).
        ros2 run swarm_core task_reallocator_node \
            > "$GUNLUK/rol.log" 2>&1 &
        sleep 1
    fi
else
    echo "[baslat] suru dugumleri KAPALI (SURU_DUGUMLERI bos)"
fi

echo "tum dugumler basladi (kayit: $KAYIT_DIZIN)"
wait
