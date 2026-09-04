#!/bin/bash
# Konteynerde kosar.  $1 = agent_id   $2 = basla|dur|durum|qr
#
# AMAC: camera_driver + vision_node zincirini ELLE kosturmak — QR okumayi
# GERCEK kamerayla, gercek karede sinamak icin. Diger surunu dugumlerine
# hic dokunmaz; tek basina acilip tek basina kapanir.
#
# ⚠️ KAMERAYI TEK SUREC ACAR. Bu zincir host'taki `kamera_yayin.py`
# servisinden besleniyor (source=http). Servis kosmuyorsa camera_driver
# acilamaz — o yuzden `basla` once onu denetliyor.
#
# NEDEN source=http (27 Agustos 2026, gercek donanimda olculdu):
# Pi 5'te /dev/video0 = rp1-cfe-csi2_ch0, yani ham Bayer veren CSI yakalama
# dugumu — UVC kamera DEGIL. `cv2.VideoCapture(0)` oradan kullanilabilir BGR
# karesi alamaz. Kamerayi libcamera ile `kamera_yayin.py` aciyor, bu zincir
# onun MJPEG akisini tuketiyor. Konteyner --network host oldugu icin
# 127.0.0.1 dogrudan erisilir: --device /dev/video* GEREKMIYOR.
#
# ⚠️ ODAK: lens odagi bozuksa QR COZULMEZ. Once tarayicidan odagi ayarla —
# yayin servisi ayni anda hem tarayiciya hem bu zincire kare verdigi icin
# odagi ayarlarken QR sonucunu da izleyebilirsin.
#
# NOT: `set -u` YOK — ROS'un setup.bash'i baglanmamis degiskene dokunuyor
# (AMENT_TRACE_SETUP_FILES) ve betik daha ilk satirda oluyor. Dizindeki
# diger teshis betiklerinde de bu yuzden yok.

AID="${1:?agent_id gerekli}"
KOMUT="${2:-durum}"
SERVIS="${KAMERA_SERVIS:-http://127.0.0.1:8080}"

source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash 2>/dev/null

KAM_LOG=/ws/gunluk/son/kamera_zincir_camera.log
GOZ_LOG=/ws/gunluk/son/kamera_zincir_vision.log
KOP_LOG=/ws/gunluk/son/kamera_zincir_kopru.log
ALGI_JSON=/ws/algi_durum.json
mkdir -p /ws/gunluk/son

# Cozunurlugu SERVISTEN okuyoruz, elle yazmiyoruz. Elle yazilan bir deger
# servisin onizleme ayari degisince sessizce yanlis kalir ve dugum bos yere
# "Cozunurluk farkli" uyarisi verir.
servis_boyutu() {
    python3 - "$SERVIS" <<'PY' 2>/dev/null
import json, sys, urllib.request
try:
    o = json.load(urllib.request.urlopen(sys.argv[1] + '/olcum', timeout=4))
    g, _, y = o['onizleme'].partition('x')
    print(g, y, o['yakalama'], o['fps'])
except Exception:
    print('')
PY
}

case "$KOMUT" in
basla)
    OKUMA=$(servis_boyutu)
    if [ -z "$OKUMA" ]; then
        echo "HATA: kamera yayin servisi cevap vermiyor ($SERVIS)"
        echo "  host'ta baslat:  setsid python3 \$HOME/kamera_yayin.py &"
        exit 1
    fi
    read -r G Y YAKALAMA SFPS <<<"$OKUMA"
    echo "servis: yakalama $YAKALAMA -> onizleme ${G}x${Y} @ ${SFPS} fps"

    pkill -f 'camera_driver|vision_node|algi_kopru' 2>/dev/null; sleep 2

    # fps servisin verdiginden YUKSEK olmasin: fazlasi bos donen grab()
    # demek, faydasi yok. Tam sayiya yuvarliyoruz.
    FPS=$(python3 -c "print(max(1, int(float('$SFPS') or 5)))")

    nohup ros2 run swarm_perception camera_driver --ros-args \
        -p agent_id:="$AID" -p source:=http -p source_url:="$SERVIS/akis" \
        -p fps:="$FPS.0" -p width:="$G" -p height:="$Y" \
        > "$KAM_LOG" 2>&1 &
    sleep 6
    # LZ_HZ -- RENK yolunun hizi. Varsayilan 15 Hz ve PAHALI: renk yolu
    # kareyi 1/2'ye kucultup isliyor (9 ms) ama once TAM kareyi cozduruyor
    # ve 4056x3040 bir JPEG'i cozmek 106 ms (KAMERA.md §6.2). Yani 15 Hz
    # renk, tek basina ~1,6 cekirdek. QR menzili olculurken renge
    # bakilmiyor: LZ_HZ=0.2 ile cozme 15/sn'den 5/sn'ye duser.
    # SIFIR VERME -- vision_node 1.0/hz hesapliyor, 0 bolme hatasi verir.
    #
    # QR_HZ -- QR yolunun hizi. Her tur TAM kareyi cozduruyor: 4K'da 106 ms,
    # yani 5 Hz tek basina yarim cekirdek (4 Eylul olcumu: vision_node
    # %92,4, sistem %11,7 bosta). Asili durup olcerken 2,5 Hz fazlasiyla
    # yeter -- 20 sn'lik bir bantta 50 deneme eder. okuma/sn olcusu
    # bantlar arasinda karsilastirmali oldugu icin hiz sabit kaldigi
    # surece dusurmek olcumu bozmaz.
    #
    # WECHAT -- VARSAYILAN KAPALI. 4 Eylul 2026'da UCAKTA olculdu, kadrajda
    # QR YOKKEN (en kotu hal, 4056x3040, 10 kare ortalamasi):
    #     wechat ACIK    951,1 ms/kare
    #     wechat KAPALI  249,1 ms/kare      <- 3,8 kat
    # Yani wechat TEK BASINA kare basina ~702 ms yiyor. KAMERA.md §6.4'teki
    # koruma "wechat TAM KAREDE asla calistirilmaz" diyor (bos karede
    # 11,6 sn olculmustu) ve dogru yazilmis -- ama KIRPMA da guvenli
    # degilmis: QR yokken varyans bulucunun aday kutusu neredeyse tum kare
    # oluyor ve wechat ayni felakete kirpma uzerinden giriyor. Koruma
    # yanlis yerde duruyor.
    # Menzil bedeli YOK: wechat ~40 m, zxing ~25 m, ama gercek tavanimiz
    # 11 m ve onu belirleyen JOLE (KAMERA.md §5.3), cozucu menzili degil.
    #
    # TAM_TARAMA -- iki asamali bulucu kacirirsa devreye giren guvenlik agi.
    # 5 -> 20: olculen fark yalnizca 249,1 -> 219,8 ms ama ag duruyor.
    # 0 (tamamen kapali) 197,8 ms verir; kalan 22 ms icin agi atmaya degmez.
    nohup ros2 run swarm_perception vision_node --ros-args \
        -p agent_id:="$AID" -p qr_processing_rate_hz:="${QR_HZ:-5.0}" \
        -p landing_zone_rate_hz:="${LZ_HZ:-15.0}" \
        -p qr_wechat_yedek:="${WECHAT:-false}" \
        -p qr_tam_tarama_periyodu:="${TAM_TARAMA:-20}" \
        > "$GOZ_LOG" 2>&1 &
    echo "vision_node: qr ${QR_HZ:-5.0} Hz, renk ${LZ_HZ:-15.0} Hz, wechat ${WECHAT:-false}, tam_tarama ${TAM_TARAMA:-20}"
    sleep 4
    # Kopru: sonuclari JSON'a yazar, kamera sayfasi onu gosterir. Boylece
    # QR/renk sonucunu gormek icin terminale `ros2 topic echo` yazmak
    # gerekmiyor — operatorun zaten baktigi sayfada cikiyor.
    # YOL: dagit.sh teshis betiklerini /ws KOKUNE koyuyor, /ws/teshis/
    # altina DEGIL (bkz. kayit_onar.sh:6). Eski yol yalniz ylp02'de elle
    # kurulmus bir dizin sayesinde calisiyordu; ylp00'da zincir sessizce
    # kirilirdi (4 Eylul 2026'da olculdu: ylp00'da teshis/ dizini HIC YOK).
    nohup python3 /ws/algi_kopru.py --ros-args \
        -p agent_id:="$AID" -p cikti:="$ALGI_JSON" \
        > "$KOP_LOG" 2>&1 &
    sleep 4
    echo "--- camera_driver ---"; tail -4 "$KAM_LOG"
    echo "--- vision_node ---";   tail -4 "$GOZ_LOG"
    echo "--- algi_kopru ---";    tail -3 "$KOP_LOG"
    echo
    echo "Sonuclar TARAYICIDA cikiyor. Terminalden istersen:"
    echo "  bash /ws/kamera_zincir.sh $AID qr"
    ;;

dur)
    pkill -f 'camera_driver|vision_node|algi_kopru' 2>/dev/null
    sleep 1
    rm -f "$ALGI_JSON"
    echo "zincir durduruldu (kamera servisi calismaya devam eder)"
    ;;

durum)
    echo "=== surecler ==="
    pgrep -af 'camera_driver|vision_node|algi_kopru' | sed 's/ --ros-args.*//' \
        || echo "(zincir kapali)"
    echo "=== algi ciktisi ==="
    if [ -f "$ALGI_JSON" ]; then
        python3 -c "import json,time,sys; d=json.load(open(sys.argv[1])); \
print(f\"  yas {time.time()-d['an']:.1f} sn  qr_sayaci={d['qr_sayaci']}  \
lz={'VAR' if d.get('lz') else 'yok'}  qr={'VAR' if d.get('qr') else 'yok'}\")" \
            "$ALGI_JSON" 2>/dev/null || echo "  (cozulemedi)"
    else
        echo "  (dosya yok — kopru kosmuyor)"
    fi
    echo "=== servis ==="
    OKUMA=$(servis_boyutu)
    [ -n "$OKUMA" ] && echo "  $OKUMA" || echo "  CEVAP YOK"
    echo "=== goruntu hizi ==="
    timeout 7 ros2 topic hz "/drone_${AID}/camera/image_raw" 2>&1 | tail -2
    echo "=== son kayitlar ==="
    # `|| true`: kayit dosyasi henuz yoksa tail 1 doner ve `durum` basarisiz
    # gorunurdu — oysa durum bildirmek basarisizlik degil.
    tail -3 "$KAM_LOG" 2>/dev/null || true
    tail -3 "$GOZ_LOG" 2>/dev/null || true
    ;;

qr)
    SURE="${3:-40}"
    echo "QR bekleniyor — kamerayi bir QR koda tut. ${SURE} sn dinleniyor."
    echo "(bos cikti = hic cozulmedi; en olasi sebep ODAK)"
    timeout "$SURE" ros2 topic echo /swarm/internal/perception/qr_data
    ;;

*)
    echo "kullanim: $0 <agent_id> {basla|dur|durum|qr [saniye]}"
    exit 2
    ;;
esac
