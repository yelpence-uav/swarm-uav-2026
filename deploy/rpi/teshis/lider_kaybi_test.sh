#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id
#
# P0.14 YER TESTI — lider KAYBI (birakma degil):
# Iki ucakta da ayni anda calistirilir. Ikisi de arm olur, lider secilir;
# LIDER OLAN kendi consensus_node surecini OLDURUR (ucak ve konteyner
# ayakta, agent_fsm DURUM yayinlamaya devam eder — yani mesh'te "saglikli
# ve uygun" gorunen ama kalp atisi uretmeyen bir lider olusur).
#
# BEKLENEN (P0.14(a) duzeltmesi): takipci hb_timeout (1000 ms) dolunca
# lideri etkin kumeden dusurur ve KENDINI secer — sebep LEADER_TIMEOUT.
# Duzeltmeden once bu yol HIC calismiyordu (iki kapi da oluydu).
#
# ROL SECIMI KENDILIGINDEN: hangi ucagin lider olacagini onceden bilmiyoruz.
# Betik, izleyicinin kaydettigi SON kalp atisindaki lider kimligine bakar;
# kendisiyse oldurur, degilse bekler. Boylece pencere ortasinda ucaklar
# arasi SSH gerekmez — ag yavasken (duvar arkasi telefon AP) bu sart.
#
# GUVENLIK: pervaneler CIKIK (operator teyidi olmadan calistirma). Sonda
# ACIK disarm + dogrulama var. Yerde disarm guvenli; havada asla (bu betik
# yerde kosar, px4_bridge'e hicbir setpoint gondermez).
AID="${1:?kullanim: lider_kaybi_test.sh <agent_id>}"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

LOG="/ws/gunluk/son/consensus.log"
OUT="/tmp/lider_kaybi_${AID}.txt"
ST="/tmp/lk_statustext_${AID}.txt"
: > "$OUT"; : > "$ST"

# PX4'un arm/red gerekcelerini yakala — reddederse TAHMIN degil OLCUM olsun
timeout -s INT 55 ros2 topic echo "/drone_${AID}/mavros/statustext/recv" \
    --field text > "$ST" 2>&1 &

kaydet() { echo "$1 $(date +%s.%N) $2" >> "$OUT"; }

# --- 1) consensus'u TEMIZ baslat -------------------------------------------
# _lider_id yapiskan (arm_secim.sh'ta olculdu): onceki kosulardan kalan lider
# kimligiyle yeni secim GOZLENEMEZ. Su anki sureci durdurup sifirdan ac.
benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*) case "$c" in *lider_kaybi*) continue ;; esac
            kill "$p" 2>/dev/null && kaydet CONS_DURDU "pid=$p" ;;
    esac
done
sleep 3
ISARET=$(wc -l < "$LOG" 2>/dev/null || echo 0)
# PARAMETRELER baslat.sh:748 ILE BIREBIR — 21 Agustos'ta olculdu: parametresiz
# baslatinca battery_min_v varsayilani 14.0 kaliyor, yeni piller 12.6 V
# okuyor ve IKI UCAK DA aday olamiyor -> sifir secim, sifir kalp atisi.
# baslat.sh bu yuzden battery_min_v:=0.0 geciyor; ayni sey burada da sart.
# (arm_secim.sh/consensus_baslat.sh de parametresiz — ayni tuzak orada da var.)
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    -p agent_count:=3 -p battery_min_v:=0.0 \
    >> "$LOG" 2>&1 < /dev/null &
sleep 6
kaydet CONS_ACILDI ""

# --- 2) izleyici (olcumun tek saati) ---------------------------------------
setsid python3 /ws/lider_kaybi_izle.py "$AID" "$OUT" 40 \
    >> "$OUT" 2>&1 < /dev/null &
sleep 2

# --- 2.5) HAZIRLIK KAPISI: FSM gercekten IDLE mi? ---------------------------
# Kosu 3'te olculdu (21 Agustos): konteyner acilisindan ~4 dk sonra bile
# ylp00 agent_fsm'i state=0 (UNKNOWN) yayinliyordu; gorev olayi UNKNOWN'da
# ise yaramiyor ve ucak HIC arm olmadan test bos gecti. Olay yayinlamadan
# once kendi ic status'u state=1 (IDLE) + healthy olana kadar bekle.
i=0; ST_LINE=""
while [ $i -lt 120 ]; do
    ST_LINE=$(timeout -s INT 6 ros2 topic echo "/swarm/internal/drone${AID}/status" \
        --once 2>/dev/null | grep -E '^(state|healthy):' | tr -d ' ' | tr '\n' ' ')
    case "$ST_LINE" in *state:1*healthy:true*|*healthy:true*state:1*) break ;; esac
    sleep 1; i=$((i + 1))
done
kaydet HAZIR "tur=$i durum=$ST_LINE"

# --- 3) GOREV BASLAT olayi -> FSM: IDLE -> ARMING -> ARMED (kalkis YOK) ----
# Dogrudan mavros arming ILE OLMUYOR — 21 Agustos'ta olculdu: PX4 arm oluyor
# ("Armed by external command") ama agent_fsm IDLE'da kaliyor (state=1,
# armed=True), IDLE ELIGIBLE_STATES'te yok, HIC secim olmuyor ve PX4 ~10
# sn'de "auto preflight disarming" ile geri birakiyor. ARMED'a cikmanin tek
# yolu EVENT_MISSION_STARTED (=24, bkz. agent_fsm_node.py:345);
# kalkis_olayla=False oldugu icin olay ajani YALNIZ ARMED'a tasir, kalkis
# tetiklenmez (pervanesiz yer testinin tasarlanmis yolu, gorev_baslat.sh
# ile ayni yayin).
kaydet GOREV_OLAYI ""
timeout -s INT 5 ros2 topic pub -r 2 --qos-reliability reliable \
    /swarm/public/events/system swarm_interfaces/msg/SystemEvent \
    "{event_type: 24, source_agent_id: 0, target_agent_id: 0, value: 0.0, has_position: false, source_module: lider_kaybi_test, message: p014_yer_testi}" \
    >/dev/null 2>&1

# --- 4) ilk kalp atisina KADAR bekle (sabit uyku degil) --------------------
# Ilk HB = lider secildi. Olay gudumlu beklemek arm penceresini kisaltir;
# preflight suresi ucaklar arasi degisebilir, sabit uyku ya erken bakar ya
# pili bosa yakar.
i=0
while [ $i -lt 30 ]; do
    grep -q '^HB ' "$OUT" 2>/dev/null && break
    sleep 0.5; i=$((i + 1))
done
kaydet HB_GORULDU "tur=$i"
sleep 2
SON_HB=$(grep '^HB ' "$OUT" | tail -1)
LIDER=$(echo "$SON_HB" | grep -oE 'lider=[0-9]+' | cut -d= -f2)
kaydet LIDER_TESPIT "gorulen=${LIDER:-yok}"

if [ "${LIDER:-}" = "$AID" ]; then
    sleep 1
    # KILL ANI: bundan sonra HB akisi kesilmeli, DURUM akisi surmeli
    kaydet KILL_ANI ""
    for p in $(ls /proc | grep -E '^[0-9]+$'); do
        [ "$p" = "$benim" ] && continue
        c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
        case "$c" in
            *consensus_node*) case "$c" in *lider_kaybi*) continue ;; esac
                kill -9 "$p" 2>/dev/null && kaydet KILL_PID "pid=$p" ;;
        esac
    done
    sleep 6
else
    sleep 8   # takipci: liderin kill+tespit penceresini kapsa
fi

# --- 5) ONCE LAND, SONRA disarm ---------------------------------------------
# OFFBOARD'dayken dogrudan disarm REDDEDILIYOR — 21 Agustos'ta bu betigin
# onceki kosusunda olculdu: "Disarming denied: not landed". FSM'in ARMING
# dizisi ucagi OFFBOARD + konum kilidine sokuyor ve PX4 kendini inmemis
# sayiyor (TUZAKLAR 3.4). Iptal her zaman LAND (CLAUDE.md §9): yerdeki
# ucakta AUTO.LAND aninda "indi" tespitine, o da otomatik disarma goturur.
kaydet LAND_ISTEK ""
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/land" \
    mavros_msgs/srv/CommandTOL '{min_pitch: 0.0, yaw: 0.0, latitude: 0.0, longitude: 0.0, altitude: 0.0}' 2>&1 \
    | grep -oE 'success=\w+' | head -1 | xargs -I{} echo "LAND_CEVAP {}" >> "$OUT"
i=0
while [ $i -lt 40 ]; do
    A=$(timeout -s INT 6 ros2 topic echo "/drone_${AID}/mavros/state" --once 2>/dev/null \
        | grep -E '^armed' | tr -d ' ')
    [ "$A" = "armed:false" ] && break
    sleep 0.5; i=$((i + 1))
done
kaydet LAND_SONU "tur=$i son=$A"
if [ "$A" != "armed:false" ]; then
    # land yetmediyse acik disarm dene; o da tutmazsa OPERATORE birak
    kaydet DISARM_ISTEK ""
    timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
        mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
        | grep -oE 'success=\w+' | head -1 | xargs -I{} echo "DISARM_CEVAP {}" >> "$OUT"
fi
timeout -s INT 12 ros2 topic echo "/drone_${AID}/mavros/state" --once 2>/dev/null \
    | grep -E '^armed' | xargs -I{} echo "SON_DURUM {}" >> "$OUT"

# --- 6) consensus olduyse GERI GETIR (normal hale birak) ---------------------
if ! pgrep -f 'consensus_node' >/dev/null 2>&1; then
    setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
        -p agent_count:=3 -p battery_min_v:=0.0 \
        >> "$LOG" 2>&1 < /dev/null &
    sleep 3
    kaydet CONS_GERI "pgrep=$(pgrep -fc consensus_node)"
fi

# --- 7) KISA rapor (ag yavas: HB selini degil ozetini bas) -------------------
echo "===== OZET drone${AID} ====="
echo "-- olaylar (HB haric) --"
grep -v '^HB ' "$OUT"
echo "-- HB ozet --"
echo "toplam: $(grep -c '^HB ' "$OUT")"
grep '^HB ' "$OUT" | head -1 | sed 's/^/ilk : /'
grep '^HB ' "$OUT" | tail -2 | sed 's/^/son : /'
echo "-- consensus.log yeni satirlar --"
tail -n +$((ISARET + 1)) "$LOG" | grep -E 'CONSENSUS|Lider|lider' | tail -8
echo "-- statustext (arm/red) --"
grep -iE 'arm|reject|denied|fail' "$ST" | head -5
