#!/bin/bash
# === BÖLÜM 5.2 — Formasyon Kontrolü ve Yörünge Takip Hassasiyeti Testi ===
# İSTERLER (sadece bu 3 rejim, öteleme/seyir YOK):
#   1) Otonom kalkış
#   2) V formasyonuna geçiş (form-up geçici rejimi)
#   3) Keskin dönüş manevraları (apex etrafında YERİNDE rijit dönüş)
# Ölçülen: hedef slot (raw setpoint) vs İHA gerçek konumu → RMSE(t),
#          geçici rejim (settling) süreleri, kararlılık eğrileri.
# Tüm fazlar AYNI merkezde (LAT0/LON0) → merkez sıçraması yok, saf dönüş analizi.
# formation_test_publisher rate_hz=10 (default) → slot 0.1s'de güncellenir
#   (2Hz'de 0.5m sıçrama → ölçüm artefaktı; 10Hz'de ~0.1m, gerçek lag görünür).
# Toplam kayıt ~95s.

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

BAG=~/test_v_kalkis
rm -rf "$BAG"

# --- trap: script NASIL biterse bitsin (Ctrl+C, hata, normal çıkış) recorder
# ve publisher garantili öldürülür → öksüz process / bag accumulation OLMAZ.
BAG_PID=""
cleanup() {
  echo "[trap] temizlik: recorder + publisher kapatılıyor..."
  pkill -9 -f "[f]ormation_test_publisher" 2>/dev/null || true
  if [ -n "$BAG_PID" ]; then
    kill -INT "$BAG_PID" 2>/dev/null || true
  fi
  pkill -INT -f "[r]os2 bag record" 2>/dev/null || true
  for i in $(seq 1 15); do [ -f "$BAG/metadata.yaml" ] && break; sleep 1; done
}
trap cleanup EXIT INT TERM

# Merkez koordinatı (kalkış = form-up = dönüş noktası, hepsi aynı)
LAT0=41.04418990
LON0=29.00170000

echo "[0/6] Eski publisher temizleniyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1

# CA influence_radius'unu 0.1m'e çek → dronlar 0.1m'den yaklaşmadıkça CA
# tetiklenmez (saf formasyon analizi). kinematic_fusion AÇIK → v_align çalışır.
echo "[0/6] CA influence_radius sıfırlanıyor (v_align aktif, CA etkisiz)..."
for attempt in 1 2 3; do
  sleep 0.5
  ok=0
  ros2 param set /collision_avoidance influence_radius_m 0.1 --qos-durability transient_local 2>/dev/null && ok=$((ok+1)) || true
  for node in $(ros2 node list 2>/dev/null | grep collision_avoidance); do
    ros2 param set "$node" influence_radius_m 0.1 2>/dev/null && ok=$((ok+1)) || true
  done
  [ "$ok" -ge 3 ] && echo "  CA param set OK (attempt $attempt)" && break
  echo "  CA param set $ok/3+ (attempt $attempt), tekrar..."
done

echo "[1/6] Bag kaydı başlıyor: $BAG"
ros2 bag record \
  /drone_1/control/setpoint/raw \
  /drone_2/control/setpoint/raw \
  /drone_3/control/setpoint/raw \
  /drone_1/control/setpoint \
  /drone_2/control/setpoint \
  /drone_3/control/setpoint \
  /swarm/internal/drone1/status \
  /swarm/internal/drone2/status \
  /swarm/internal/drone3/status \
  /swarm/public/formation/target \
  -o "$BAG" &
BAG_PID=$!
sleep 3

echo "[2/6] OTONOM KALKIŞ başlatılıyor (hedef: 15m)..."
if ! python3 ~/ros2_ws/scripts/test/formation/sync_takeoff.py; then
  echo "[İPTAL] Kalkış başarısız — bag kapatılıyor."
  kill -INT "$BAG_PID" 2>/dev/null || true
  pkill -INT -f "ros2 bag record" 2>/dev/null || true
  for i in $(seq 1 15); do [ -f "$BAG/metadata.yaml" ] && break; sleep 1; done
  exit 1
fi
echo "  Kalkış doğrulandı."
sleep 5  # irtifa kararlılaşsın

# pub <tgt_hdg> <start_hdg> <rate_dps> <center_lat> <center_lon> <max_speed>
# move_speed=0 → merkez SABİT (öteleme yok). Dönüş: rate>0 → apex etrafında
# yerinde rijit döner; kanatlar r=8m'de v=ω·8 ile sweep eder.
# Keskin dönüş için max_speed artırılır (rijit kısıt: ω·8 ≤ max_speed).
pub() {
  pkill -9 -f formation_test_publisher 2>/dev/null || true
  sleep 0.5
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=2 \
    -p spacing_m:=8.0 \
    -p heading_deg:="$1" \
    -p start_heading_deg:="$2" \
    -p heading_rate_dps:="$3" \
    -p use_hungarian:=true \
    -p center_z:=-15.0 \
    -p use_proxy:=false \
    -p center_lat:="$4" \
    -p center_lon:="$5" \
    -p move_speed_mps:=0.0 \
    -p move_heading_deg:=0.0 \
    -p max_speed_mps:="$6" &
  echo "[$(date +%H:%M:%S)] hdg $2°→$1° (rate=$3°/s) max_v=$6 @ ($4,$5)"
}

# Dronlar spawn'da DOĞUYA (90°) bakarak kalkıyor → form-up'ı 90°'de başlat,
# yaw snap YOK, kalkıştan formasyona pürüzsüz geçiş.

echo "[3/6] >>> İSTER-2: V FORMASYONUNA GEÇİŞ (heading=90°, form-up transient)..."
pub 90.0 90.0 0.0 "$LAT0" "$LON0" 1.5
sleep 24   # form-up oturması + kararlı-hal taban çizgisi

echo "[4/6] >>> İSTER-3: KESKİN DÖNÜŞ-1 90°→180° (15°/s, yerinde, sharp)..."
pub 180.0 90.0 15.0 "$LAT0" "$LON0" 3.0
sleep 20   # 90°/15°/s = 6s dönüş + ~14s oturma

echo "[5/6] >>> İSTER-3: KESKİN DÖNÜŞ-2 180°→90° (15°/s, yerinde, geri dönüş)..."
pub 90.0 180.0 15.0 "$LAT0" "$LON0" 3.0
sleep 20

echo "[6/6] Test tamamlandı, kayıt kapatılıyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1
kill -INT "$BAG_PID" 2>/dev/null || true
pkill -INT -f "ros2 bag record" 2>/dev/null || true
for i in $(seq 1 15); do
  [ -f "$BAG/metadata.yaml" ] && break
  sleep 1
done
sleep 1

echo "=== TAMAMLANDI ==="
ls -lh "$BAG"/
[ -f "$BAG/metadata.yaml" ] && echo "[OK] bag temiz kapandı" \
  || echo "[UYARI] metadata yok — bag bozuk olabilir"
