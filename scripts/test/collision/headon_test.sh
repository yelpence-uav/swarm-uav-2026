#!/bin/bash
# HEAD-ON TESTİ — Senaryo 1 (GERÇEKÇİ)
#
# Gerçek yarışma senaryosu: iki drone sabit hızla tam karşılıklı uçar.
#
# Gerçek parametreler:
#   lateral_offset=0.3m  → GPS titremesi kadar asimetri; her drone kendi
#                           sağına natural yield eder (tam simetrik = kilitlenme riski)
#   cross_speed=2.5 m/s  → yarışma hızı (1.5 m/s çok yavaş, look-ahead avantajı abartılır)
#   separation=15m       → kapanma hızı 5 m/s, avoidance penceresi ~2s (gerçekçi)
#
# Beklenen davranış:
#   Yaklaşma fazı : mesafe 15m→~6m kapanır, CA henüz aktif değil
#   Avoidance fazı: CA devreye girer, yay çizer, min ≥ 1.5m, ihlal=0
#   Toparlanma    : publisher kill sonrası dronlar formasyona döner (slot hatası azalır)
#
# Kullanım: bash headon_test.sh [hız_m/s] [ayrım_m] [lateral_offset_m]
#   Örnek: bash headon_test.sh 2.5 15 0.3   (varsayılan yarışma parametreleri)
#          bash headon_test.sh 1.5 12 0.0   (eski düşük-hız test)
#          bash headon_test.sh 3.5 15 0.3   (agresif)

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash 2>/dev/null

SPEED="${1:-2.5}"
SEP="${2:-15.0}"
LAT_OFF="${3:-0.3}"
LAT=41.04418990
LON=29.00170000

APPROACH_SECS=45   # kapanma + avoidance için bekleme
RECOVERY_SECS=20   # formasyona dönüş izleme

CLOSING_SPEED=$(python3 -c "print(f'{2*float($SPEED):.1f}')")
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  HEAD-ON TESTİ — gerçek yarışma parametreleri               ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Hız         : ${SPEED} m/s (her drone)                          ║"
echo "║  Kapanma hızı: ${CLOSING_SPEED} m/s                                    ║"
echo "║  Başlangıç   : ${SEP} m ayrım                                 ║"
echo "║  Yanal offset: ${LAT_OFF} m  (simetri kırma / natural yield)       ║"
echo "║  Drone3      : KENDİ SLOTUNDA SABİT (neutral)                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Beklenen:                                                   ║"
echo "║    Yaklaşma : 15m→6m, CA sessiz                              ║"
echo "║    Avoidance: 6m→min, yay çizer → min ≥ 1.5m                ║"
echo "║    Toparlanma: formation'a geri dön, slot hatası azalır      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── TEMIZLE ──────────────────────────────────────────────────────────────────
echo ">>> [0/3] Önceki publisher'ları ve monitörü temizle..."
ps aux | grep -E "disturbance_publisher|formation_test_publisher|safety_monitor" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
sleep 1.2

# Safety monitörü temiz log ile yeniden başlat (kümülatif min sıfırlansın)
> /tmp/sm_manual.log
python3 ~/ros2_ws/scripts/test/collision/safety_monitor.py --ros-args \
  -p agent_ids:="[1,2,3]" -p safety_radius_m:=1.5 -p warn_radius_m:=2.0 \
  -p run_label:=headon_run >/tmp/sm_manual.log 2>&1 &
sleep 1.5

# ── FAZ 1: ÖN KONTROL ────────────────────────────────────────────────────────
echo ">>> [1/3] Ön kontrol — drone'lar formasyonda mı? (5sn bekle)"
echo "    Eğer dronlar yerde / stabil değilse testi durdur (Ctrl+C)"
sleep 5
echo ""

# ── FAZ 2: HEAD-ON YAKLAŞMA ──────────────────────────────────────────────────
PARK_SECS=10  # dronların başlangıç pozisyonuna gidip yerleşme süresi (15m ayrım → ~6s uçuş + marj)

echo ">>> [2/3] HEAD-ON başlıyor: drone1 ↑ drone2 ↓ | offset=${LAT_OFF}m"
echo "    Park fazı: ${PARK_SECS}sn (dronlar ${SEP}m ayrım pozisyonuna gider)"
echo "    Geçiş fazı: ${PARK_SECS}sn sonra başlar — CA devreye girecek"
echo ""

python3 ~/ros2_ws/scripts/test/collision/disturbance_publisher.py --ros-args \
  -p agent_ids:="[1,2,3]" \
  -p formation_type:=3 \
  -p spacing_m:=5.0 \
  -p heading_deg:=0.0 \
  -p center_z:=-15.0 \
  -p center_lat:=$LAT \
  -p center_lon:=$LON \
  -p max_speed_mps:=$SPEED \
  -p mode:=two_group \
  -p group_b_ids:="[2]" \
  -p neutral_ids:="[3]" \
  -p separation_m:=${SEP%.*}.0 \
  -p cross_speed_mps:=$SPEED \
  -p lateral_offset_m:=$LAT_OFF \
  -p cross_axis:=horizontal \
  -p park_time_s:=${PARK_SECS}.0 >/tmp/dist.log 2>&1 &
DIST_PID=$!

# Başlangıç anını kaydet
T0=$(date +%s)

# Faz takibi
MIN_EVER=99.9
IHLAL_EVER=0
AVOIDANCE_STARTED=false
CLOSEST_AT=""

echo "    t(s) | mesafe(m) | kapatma hızı | faz           | durum"
echo "    ─────┼───────────┼──────────────┼───────────────┼──────────"

# Log satır numarasını başta kaydet — sadece bu testin satırlarını okuyacağız
LOG_START=$(wc -l < /tmp/sm_manual.log 2>/dev/null || echo 0)

for i in $(seq 1 $APPROACH_SECS); do
  sleep 1
  NOW=$(date +%s)
  ELAPSED=$((NOW - T0))

  # Bu test boyunca yazılan satırlardan gerçek minimum bul (tail yerine tüm yeni satırlar)
  MIN_WINDOW=$(tail -n +$((LOG_START+1)) /tmp/sm_manual.log 2>/dev/null \
               | grep -oP 'min=\K[0-9.]+' | sort -n | head -1)
  VIOL_WINDOW=$(tail -n +$((LOG_START+1)) /tmp/sm_manual.log 2>/dev/null \
                | grep -oP 'ihlal=\K[0-9]+' | sort -rn | head -1)
  # Son satırdan anlık mesafe (ekran için)
  MIN_NOW=$(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+' | head -1)

  DISP=${MIN_NOW:-"--"}

  if [ -n "$MIN_WINDOW" ]; then
    IS_LESS=$(python3 -c "print(1 if float('$MIN_WINDOW') < float('$MIN_EVER') else 0)" 2>/dev/null)
    if [ "$IS_LESS" = "1" ]; then
      MIN_EVER=$MIN_WINDOW
      CLOSEST_AT="${ELAPSED}s"
    fi
    [ -n "$VIOL_WINDOW" ] && [ "$VIOL_WINDOW" -gt 0 ] 2>/dev/null && IHLAL_EVER=$VIOL_WINDOW

    FAZ=$(python3 -c "
e=int('$ELAPSED'); p=$PARK_SECS
d=float('$MIN_WINDOW')
if e < p:     print('park (konum al)')
elif d > 6.0: print('yaklaşma      ')
elif d > 3.5: print('CA devreye    ')
elif d > 2.0: print('AVOIDANCE !!!  ')
else:         print('HARD ZONE !!!  ')
" 2>/dev/null)

    if echo "$FAZ" | grep -q "AVOIDANCE\|HARD"; then
      $AVOIDANCE_STARTED || echo "    *** AVOIDANCE BAŞLADI t=${ELAPSED}s ***"
      AVOIDANCE_STARTED=true
    fi

    STATUS=$(python3 -c "
d=float('$MIN_WINDOW'); v=int('${VIOL_WINDOW:-0}')
if v>0:    print('✗ İHLAL')
elif d<1.5: print('✗ EŞİK ALTI')
elif d<3.5: print('⚡ CA aktif')
else:       print('✓ güvenli')
" 2>/dev/null)

    printf "    %4ds | şu:%5sm en-az:%5sm | %-14s | %s\n" \
      "$ELAPSED" "$DISP" "$MIN_EVER" "$FAZ" "$STATUS"
  else
    printf "    %4ds | log bekleniyor...\n" "$ELAPSED"
  fi
done

echo ""

# ── FAZ 3: TOPARLANMA ────────────────────────────────────────────────────────
echo ">>> [3/3] Avoidance tamamlandı — disturbance durduruldu, formasyona dön"
kill $DIST_PID 2>/dev/null
sleep 0.5

ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 >/dev/null 2>&1 &

echo "    Formation komutu gönderildi (spacing=6m). Toparlanma izleniyor..."
echo ""
echo "    t(s) | mesafe(m) | faz"
echo "    ─────┼───────────┼──────────────────"

for i in $(seq 1 $RECOVERY_SECS); do
  sleep 1
  NOW=$(date +%s)
  ELAPSED=$((NOW - T0))

  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  MIN=$(echo "$LOG" | grep -oP 'min=\K[0-9.]+' | head -1)

  if [ -n "$MIN" ]; then
    FAZ=$(python3 -c "
d=float('$MIN')
if d > 5.5:  print('toparlandı ✓')
elif d > 3.5: print('yaklaşıyor...')
else:         print('yakın, CA aktif')
" 2>/dev/null)
    printf "    %4ds | %9sm | %s\n" "$ELAPSED" "$MIN" "$FAZ"
  else
    printf "    %4ds | log yok   |\n" "$ELAPSED"
  fi
done

# ── SONUÇ RAPORU ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  TEST SONUCU                                                 ║"
echo "╠══════════════════════════════════════════════════════════════╣"

RESULT=$(python3 -c "
m=float('$MIN_EVER')
v=int('${IHLAL_EVER:-0}')
if v > 0:
    print('✗ BAŞARISIZ — emniyet ihlali var')
elif m < 1.5:
    print('✗ BAŞARISIZ — eşik altına indi')
elif m < 2.0:
    print('⚠ SINIRDA  — kabul edilebilir ama riskli')
elif m < 3.5:
    print('✓ BAŞARILI — CA çalıştı')
else:
    print('✓ BAŞARILI — CA gerekmedi (mesafe yeterliydi)')
" 2>/dev/null)

echo "║  Min mesafe : ${MIN_EVER}m (t=${CLOSEST_AT})                        ║"
echo "║  İhlal sayısı: ${IHLAL_EVER:-0}                                           ║"
echo "║  Sonuç      : $RESULT"
echo "║                                                              ║"
echo "║  Parametre özeti:                                            ║"
echo "║    Hız: ${SPEED} m/s | Ayrım: ${SEP}m | Offset: ${LAT_OFF}m              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Farklı hızlarda tekrar etmek için:"
echo "    bash headon_test.sh 1.5 15 0.3   # yavaş"
echo "    bash headon_test.sh 2.5 15 0.3   # yarışma (varsayılan)"
echo "    bash headon_test.sh 3.5 15 0.3   # agresif"
