#!/bin/bash
# headon_proof.sh — ÇARPIŞMA ÖNLEME KESİN KANIT TESTİ (SITL)
#
# Senin sorduğun "CA çalışıyor mu" sorusuna tek belirleyici cevap. two_group
# modu: drone1 ve drone2 zıt taraflara park edip karşı tarafa uçar → ortada
# TEMİZ 2-cisim kafa-kafaya kesişme; drone3 koridordan kenara çekilir (atfı
# bulandırmaz). lateral_offset simetriyi kırar (ayna-deadlock önler). Yol
# kesişince APF yerel-minimum tuzağı (donma) tetiklenir: teğet kuralı
# çalışıyorsa ikisi de sağına kayıp geçer; çalışmıyorsa donar.
#
# Bu script GAZEBO/TAKEOFF YAPMAZ. Önkoşul: start_all + takeoff zaten yapıldı,
# dronlar hedef irtifada (~15m) formasyonda hover'da ([[gazebo-yasam-dongusu-kullanicida]]).
#
# 4 KANIT KRİTERİ (hepsi geçmeli):
#   1) min merkez-merkez mesafe >= 1.5m  → emniyet ihlali yok (itki çalıştı)
#   2) ihlal tick = 0                    → hiç eşik altına inilmedi
#   3) CA aktivasyon > 0                 → CA GERÇEKTEN devreye girdi
#                                          (yoksa "şanslı geometri", CA değil)
#   4) test sonu ayrışma >= 3.5m         → donmadılar, geçtiler (deadlock yok)
#
# A/B KANITI (önerilir): CA'sız bir kez koş → 1 ve 4 KALMALI (çarpışma/donma).
#   CA node'unu durdur:  pkill -f collision_avoidance   (sonra start_all ile geri)
#   Fark = CA'nın katkısı. CA'sız da temiz çıkarsa test senaryosu zayıf demektir.
#
# Kullanım: bash headon_proof.sh [hız_m/s]
#   bash headon_proof.sh 1.5    # güvenli ilk koşu (varsayılan)
#   bash headon_proof.sh 2.5    # yarışma hızı

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash 2>/dev/null

SPEED="${1:-1.5}"
IDS="[1,2,3]"
LAT=41.04418990
LON=29.00170000
CENTER_Z=-15.0          # 15m irtifa — gate(3m) çok üstünde
SPACING=6.0
GATE=3.0

# --- two_group head-on parametreleri (temiz 2-cisim, 3.dron kenara) ---
SEP=15.0                # başlangıç ayrımı (m); kapanma hızı = 2*SPEED
LAT_OFF=0.3             # yanal offset — simetri kır (ayna-deadlock önle)
PARK_SECS=10            # faz 1: dronlar ±sep/2 park noktasına gider, yerleşir
OBSERVE_SECS=22         # faz 2: kesişme + avoidance penceresi (park sonrası)
RECOVERY_SECS=12        # toparlanma (formasyona dönüş) izleme

DIR=~/ros2_ws/scripts/test/collision
OUT_DIR=~/ros2_ws/analysis/collision_sitl
RUN="headon_proof_$(date +%H%M%S)"
CSV="$OUT_DIR/$RUN.csv"
SM_LOG="/tmp/sm_proof.log"

CLOSING=$(python3 -c "print(f'{2*float($SPEED):.1f}')")
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  HEAD-ON KESİN KANIT TESTİ (two_group — temiz 2-cisim)      ║"
echo "║  drone1 ↔ drone2 taraf değiştirir (kafa-kafaya), drone3 yan ║"
echo "║  Hız: ${SPEED}m/s | kapanma: ${CLOSING}m/s | ayrım: ${SEP}m | offset: ${LAT_OFF}m  ║"
echo "╚════════════════════════════════════════════════════════════╝"

# ── [0/4] TEMİZLİK ───────────────────────────────────────────────────────────
echo ">>> [0/4] Önceki publisher/monitör temizliği..."
pkill -f formation_test_publisher 2>/dev/null
pkill -f disturbance_publisher 2>/dev/null
pkill -f safety_monitor 2>/dev/null
pkill -f trajectory_logger 2>/dev/null
sleep 1.5
pkill -9 -f formation_test_publisher 2>/dev/null
pkill -9 -f disturbance_publisher 2>/dev/null
sleep 0.5

# Temizlik onayı
REMAINING=$(pgrep -af "formation_test_publisher\|disturbance_publisher" 2>/dev/null | wc -l)
[ "$REMAINING" -gt 0 ] && echo "    ⚠ Hâlâ çalışan publisher var: $(pgrep -af 'formation_test_publisher\|disturbance_publisher')"
echo "    Temizlik tamam."

# ── [1/4] ÖN-KONTROL KAPISI ──────────────────────────────────────────────────
echo ">>> [1/4] Ön-kontrol: dronlar uçuşta, EKF geçerli, irtifa>gate mı?"
python3 "$DIR/preflight_check.py" --ros-args \
  -p agent_ids:="$IDS" -p altitude_gate_m:=$GATE \
  -p required_ids:="[1,3]" -p timeout_s:=15.0
if [ $? -ne 0 ]; then
  echo ">>> ✗ Ön-kontrol KALDI — test başlatılmadı."
  exit 1
fi

# ── [2/4] ÖLÇÜM CİHAZI ───────────────────────────────────────────────────────
echo ">>> [2/4] safety_monitor + trajectory_logger başlatılıyor (GPS/haversine)..."
> "$SM_LOG"
python3 "$DIR/safety_monitor.py" --ros-args \
  -p agent_ids:="$IDS" -p safety_radius_m:=1.5 -p warn_radius_m:=2.0 \
  -p out_dir:="$OUT_DIR" -p run_label:="$RUN" >"$SM_LOG" 2>&1 &
SM_PID=$!
python3 "$DIR/trajectory_logger.py" --ros-args \
  -p agent_ids:="$IDS" -p out_dir:="$OUT_DIR" -p run_label:="$RUN" \
  >/tmp/traj_proof.log 2>&1 &
TRAJ_PID=$!
sleep 2
echo "    baseline (formasyon stabil mi) 4sn..."
sleep 4

# ── [3/4] HEAD-ON (two_group: drone1↔drone2 taraf değiştirir) ────────────────
echo ">>> [3/4] two_group başladı: park ${PARK_SECS}s → sonra kafa-kafaya geçiş"
python3 "$DIR/disturbance_publisher.py" --ros-args \
  -p agent_ids:="$IDS" -p formation_type:=3 -p spacing_m:=5.0 \
  -p heading_deg:=0.0 -p center_z:=$CENTER_Z \
  -p center_lat:=$LAT -p center_lon:=$LON -p max_speed_mps:=$SPEED \
  -p mode:=two_group -p group_b_ids:="[2]" -p neutral_ids:="[3]" \
  -p separation_m:=$SEP -p cross_speed_mps:=$SPEED \
  -p lateral_offset_m:=$LAT_OFF -p cross_axis:=horizontal \
  -p park_time_s:=${PARK_SECS}.0 >/tmp/dist_proof.log 2>&1 &
SWAP_PID=$!

echo "    t(s) | anlık min | dek min | faz          | durum"
echo "    ─────┼───────────┼─────────┼──────────────┼──────────────"
TOTAL=$((PARK_SECS + OBSERVE_SECS))
for i in $(seq 1 $TOTAL); do
  sleep 1
  LINE=$(tail -1 "$SM_LOG" 2>/dev/null)
  NOW=$(echo "$LINE" | grep -oP 'min=\K[0-9.]+' | head -1)
  DEK=$(echo "$LINE" | grep -oP 'dek min=\K[0-9.]+' | head -1)
  FAZ=$([ "$i" -lt "$PARK_SECS" ] && echo "park         " || echo "GEÇİŞ        ")
  ST=$(python3 -c "
d=float('${DEK:-99}')
print('✗ EŞİK ALTI' if d<1.5 else ('⚡ CA bölgesi' if d<3.5 else '✓ güvenli'))" 2>/dev/null)
  printf "    %4ds | %8sm | %6sm | %s | %s\n" "$i" "${NOW:-–}" "${DEK:-–}" "$FAZ" "$ST"
done

# DEADLOCK ÖLÇÜMÜ: kesişme sonunda, two_group HÂLÂ AKTİFKEN ayrışmayı yakala.
# Geçtilerse karşı taraflarda (~sep) dururlar; donduysa merkezde ~2m'de takılı.
# (Recovery'den ÖNCE ölç: formasyona dönüş donmayı maskeler.)
FINAL_SEP=$(tail -20 "$CSV" 2>/dev/null | awk -F, 'NR>0{s+=$2;n++} END{if(n>0)printf "%.2f", s/n; else print "0"}')

# ── [4/4] TOPARLANMA + VERDİCT ───────────────────────────────────────────────
echo ">>> [4/4] two_group durduruldu — monitör durduruldu, formasyona dönüş (toparlanma)"
kill $SWAP_PID 2>/dev/null
sleep 0.5

# Monitör + logger'ı RECOVERY BAŞLAMADAN durdur → verdict sadece kesişme
# penceresini kapsar; recovery fazı formasyon geometrisi nedeniyle yakınlaşma
# yaratabilir (drone2-3 koridoru), bu testin kapsam dışıdır.
kill -INT $SM_PID 2>/dev/null
kill -INT $TRAJ_PID 2>/dev/null
sleep 2.0

ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="$IDS" -p formation_type:=3 -p spacing_m:=$SPACING \
  -p heading_deg:=0.0 -p center_z:=$CENTER_Z -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 >/dev/null 2>&1 &
FORM_PID=$!
sleep $RECOVERY_SECS
# Recovery publisher'ı temizle — yoksa sonraki çalıştırmada disturbance'ı ezer
kill $FORM_PID 2>/dev/null

# Sağ-el yaylanması görsel kanıtı: Doğu–Kuzey yörünge grafiği
TRAJ_CSV="$OUT_DIR/${RUN}_traj.csv"
TRAJ_PNG="$OUT_DIR/${RUN}_traj.png"
python3 "$DIR/plot_trajectory.py" "$TRAJ_CSV" "$TRAJ_PNG" 2>/dev/null

MIN_EVER=$(grep -oP 'min mesafe = \K[0-9.]+' "$SM_LOG" | tail -1)
IHLAL=$(grep -oP 'ihlal tick = \K[0-9]+' "$SM_LOG" | tail -1)
CA_SUM=$(grep -oP 'aktivasyon=\K[0-9]+' "$SM_LOG" | awk '{s+=$1} END{print s+0}')

MIN_EVER=${MIN_EVER:-0}
IHLAL=${IHLAL:-1}
FINAL_SEP=${FINAL_SEP:-0}

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  KANIT RAPORU [$RUN]"
echo "╠════════════════════════════════════════════════════════════╣"
python3 - "$MIN_EVER" "$IHLAL" "$CA_SUM" "$FINAL_SEP" <<'PY'
import sys
mn, ihlal, ca, sep = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
def row(ok, txt): return f"║  {'✓' if ok else '✗'} {txt}"
c1 = mn >= 1.5
c2 = ihlal == 0
c3 = ca > 0
c4 = sep >= 3.5
print(row(c1, f"1) min mesafe = {mn:.2f}m  (>= 1.5m gerekli)"))
print(row(c2, f"2) ihlal tick = {ihlal}  (= 0 gerekli)"))
print(row(c3, f"3) CA aktivasyon = {ca}x  (> 0 gerekli → CA gerçekten girdi)"))
print(row(c4, f"4) kesişme-sonu ayrışma = {sep:.2f}m  (>= 3.5m → donmadılar, geçtiler)"))
print("╠════════════════════════════════════════════════════════════╣")
if c1 and c2 and c3 and c4:
    print("║  SONUÇ: ✓✓ GEÇTİ — çarpışma önleme kanıtlandı")
elif c3 and not c4:
    print("║  SONUÇ: ✗ DEADLOCK ŞÜPHESİ — CA girdi ama ayrışamadılar")
    print("║         (teğet/k_tan zayıf? donma tuzağı)")
elif not c3:
    print("║  SONUÇ: ⚠ BELİRSİZ — CA hiç tetiklenmedi")
    print("║         (komşu beslemesi yok? mesafe hiç d0 altına inmedi?)")
else:
    print("║  SONUÇ: ✗ BAŞARISIZ — emniyet ihlali")
PY
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  min-mesafe CSV:     $CSV"
echo "║  yörünge CSV:        $TRAJ_CSV"
echo "║  sağ-el yayı GRAFİK: $TRAJ_PNG"
echo "║  Monitör özeti:      $SM_LOG"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "  → A/B için: CA'sız tekrar koş (pkill -f collision_avoidance),"
echo "    kriter 1 ve 4 KALMALI; fark CA'nın katkısını kanıtlar."
