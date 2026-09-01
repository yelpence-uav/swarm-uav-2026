#!/bin/bash
# =============================================================================
# YKİ (yer istasyonu) başlatma — base bridge + backend + frontend.
#
# Sahada WiFi YOK: drone verisi TAMAMEN ESP mesh'ten (base ESP seri portu) gelir.
# base_bridge, backend, frontend hepsi bu laptopta çalışır ve aralarında ROS 2
# (DDS) ile konuşur. DDS'i tek bir kesin yolla LOOPBACK'e sabitleriz:
#
#     CYCLONEDDS_URI -> cyclonedds_yki.xml  (lo arayüzü + 127.0.0.1 unicast peer)
#
# Bu config unicast peer kullanır; 'lo' multicast flag'ine İHTİYACI YOK, deprecated
# ROS_LOCALHOST_ONLY'ye de gerek yok. WiFi açık/kapalı fark etmez — laptop-içi DDS
# her zaman loopback üzerinden gider. Tek bağ mesh; DDS sadece laptop-içi taşıma.
#
# Kullanım:  ./yki_baslat.sh
# Durdurma:  ./yki_durdur.sh
# =============================================================================
# NOT: 'set -u' KULLANMA — ROS setup.bash bağlanmamış değişken referanslar,
# set -u ile source patlar (AMENT_TRACE_SETUP_FILES).

# Repo kokunu scriptin KENDI konumundan bul: farkli kullanici/makinede (yentur,
# eyup, ...) elle duzenleme gerekmesin. Ikisi de env ile ezilebilir.
REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV="${VENV:-$HOME/gcs-venv}"

# ROS ortami NEREDEN geliyor — Ubuntu'da apt (/opt/ros/jazzy), macOS'ta ise
# RoboStack/pixi conda ortami (18 Agustos 2026'da eklendi). Tek yerden
# parametreleniyor ki iki ayri baslatma betigi tutmayalim.
#   Ubuntu : (bir sey yapma, varsayilan dogru)
#   macOS  : ROS_SETUP=~/yelpence-yki-mac/.pixi/envs/default/setup.bash ./yki_baslat.sh
ROS_SETUP="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"

# setsid macOS'ta YOK (util-linux'a ait, Darwin'de gelmiyor). Isi surecleri
# kontrol terminalinden koparmak; nohup + disown ayni sonucu veriyor.
if command -v setsid > /dev/null 2>&1; then ARKAPLAN=setsid; else ARKAPLAN=nohup; fi

# venv KOSULLU: Ubuntu'da kur_yki.sh ~/gcs-venv uretiyor. macOS'ta backend
# bagimliliklari dogrudan pixi ortaminda duruyor, ayri venv yok — yoksa
# atlanir, "No such file" ile backend'i dusurmez.
if [ -f "$VENV/bin/activate" ]; then
  VENV_KAYNAK="source '$VENV/bin/activate' &&"
else
  VENV_KAYNAK=""
fi
# base ESP VERI portu — kalici by-id yolu (ttyUSB numarasi degisir, by-id degismez).
# RX BASE 'esp32dev' (default/loglu) env: VERI Serial2 -> USB-TTL (CH340) @460800.
#   LOG hatti ayri: ESP'nin CP2102'si @115200 ([MESH] ciktilari) — izlemek icin:
#   screen /dev/serial/by-id/usb-Silicon_Labs_CP2102...  115200  (veya pio device monitor)
# Farkli port icin: BASE_ESP_PORT=/dev/ttyUSB1 ./yki_baslat.sh
# =============================================================================
# 🔴 SERI PORT OTOMATIK BULMA — 31 Agustos 2026, sahada IKI KEZ isirdi
# =============================================================================
# Asagidaki varsayilanlar Linux `/dev/serial/by-id/...` yollari: cihazin
# takildigi USB portundan BAGIMSIZ, kararli adlar. macOS'ta oyle bir dizin
# YOK ve ham ad (`cu.usbserial-XXXX`) her yeniden takista DEGISEBILIYOR —
# rakamlar USB yolunu kodluyor.
#
# 31 Agustos gecesi OLCULDU — iki surec de olu porta bagliydi ve ikisi de
# HIC HATA VERMEDI, sadece sustu:
#     base ESP : bekledigi -11340    gercek -1340
#     RTK      : bekledigi 113301    gercek 13301   (RTK cikarilip takildi)
# Mesh telemetrisi 66 dakika akmadi. Once ucaklar suclandi, sonra QGC;
# gercek sebep buydu. Belirti: `/api/health` -> "connected: 0" ve
# px4_bridge logunda `rtk: msg=0`.
#
# 🔴 BELIRSIZLIKTE TAHMIN ETMEZ. Birden cok aday varsa hicbirini secmez ve
# GURULTULU uyarir: yanlis port SESSIZ ariza, eksik port en azindan gorunur.
seri_port_bul() {
    local ad="$1" yapilandirilmis="$2"; shift 2
    if [ -e "$yapilandirilmis" ]; then
        echo "$yapilandirilmis"
        return 0
    fi
    local adaylar=() d
    for d in "$@"; do
        [ -e "$d" ] && adaylar+=("$d")
    done
    if [ ${#adaylar[@]} -eq 1 ]; then
        echo "[YKİ] ⚠ $ad: yapılandırılan port YOK ($yapilandirilmis)" >&2
        echo "[YKİ] ✓ $ad: otomatik bulundu -> ${adaylar[0]}" >&2
        echo "${adaylar[0]}"
        return 0
    fi
    if [ ${#adaylar[@]} -eq 0 ]; then
        echo "[YKİ] 🔴 $ad: PORT BULUNAMADI. Yapılandırılan: $yapilandirilmis" >&2
        echo "[YKİ]    Cihaz takılı mı? Süreç yine de başlar ve port" >&2
        echo "[YKİ]    gelince bağlanmayı dener." >&2
    else
        echo "[YKİ] 🔴 $ad: BİRDEN ÇOK ADAY, seçim YAPILMADI:" >&2
        printf '[YKİ]      %s\n' "${adaylar[@]}" >&2
        echo "[YKİ]    Doğrusunu elle ver — yanlış port SESSİZCE hiçbir şey" >&2
        echo "[YKİ]    okumaz. Örn: ${ad//[^A-Za-z]/}_PORT=... ./yki_baslat.sh" >&2
    fi
    echo "$yapilandirilmis"
    return 1
}

BASE_ESP_PORT="${BASE_ESP_PORT:-/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0}"
BASE_ESP_PORT="$(seri_port_bul 'base ESP' "$BASE_ESP_PORT" \
    /dev/serial/by-id/*1a86* /dev/cu.usbserial-* /dev/ttyUSB*)"
BASE_ESP_BAUD=460800

# --- Ortak NED origin (sabit çapa) — SAHAYA göre güncelle ---
# Origin İKİ topic'te gerekir:
#   /swarm/public/origin   -> backend (harita tıklaması lat/lon -> NED çevirisi)
#   /swarm/internal/origin -> base esp32_bridge -> mesh -> drone px4_bridge
#                             (SET_GPS_GLOBAL_ORIGIN; formation_node origin gelmeden setpoint üretmez)
# base esp32_bridge public'i mesh'e İLETMEZ (yalnız /internal dinler) -> İKİ yayıncı gerekir.
# Değeri sahanın referans noktasıyla değiştir (env ile: ORIGIN_LAT=... ./yki_baslat.sh).
# RTK baz istasyonu gelince: swarm_origin_publisher'ı origin_source:=rtk_base'e çevir.
# TEK KAYNAK: deploy/saha_origin.env. Ucaklardaki /ws/origin de AYNI
# dosyadan uretiliyor (dagit.sh) — 15 Agustos'ta ikisi ayrisip 18.2 m fark
# olusmustu, o yuzden artik tek yerden besleniyor.
# shellcheck disable=SC1091
[ -f "$REPO/deploy/saha_origin.env" ] && . "$REPO/deploy/saha_origin.env"
ORIGIN_LAT="${ORIGIN_LAT:-38.6904758}"
ORIGIN_LON="${ORIGIN_LON:-39.1610188}"
# ORIGIN_ALT ZEMİNİN AMSL YÜKSEKLİĞİ OLMALI — 1218.5 idi, 1.54 m fazlaydı.
#
# Bu sayı PX4'ün yerel z=0 düzlemini nereye koyacağını belirler. Zeminden
# farklıysa "irtifa 5 m" komutu uçağı 5 m'ye ÇIKARMAZ: origin düzlemi 1.54 m
# yukarıdaysa uçak zeminden 3.46 m'de kalır. Operatörün birden çok görevde
# bildirdiği "irtifa sıçraması" buydu; kalkış sonrası ölçülen irtifa_ofset
# semptomu soğuruyordu ama sebep duruyordu.
#
# 1 Ağustos'ta ölçüldü, aritmetik birebir oturdu:
#   GPS AMSL (yerde)     1216.96 m
#   PX4 yerel z (ENU up)   -1.542 m
#   1218.5 - 1.542 = 1216.96  -> PX4 1218.5'i DOĞRU uygulamış, sayı yanlışmış.
# Doğrusu zeminin kendi AMSL'i: 1216.96.
#
# BAŞKA SAHADA: drone'u yere koy, GPS'in AMSL'ini oku, buraya yaz —
#   ros2 topic echo --once /drone_N/mavros/global_position/global | grep altitude
# Yanlış bırakılırsa px4_bridge._origin_dogrula dikey sapmayı yakalar,
# origin_synced false olur ve ön kontrol görevi BAŞLATMAZ.
ORIGIN_ALT="${ORIGIN_ALT:-1216.96}"

# --- DDS: loopback (WiFi'den bağımsız) — tek kesin mekanizma ---
# macOS'ta loopback arayuzunun adi lo DEGIL lo0 — o yuzden env ile ezilebilir.
DDS_URI="${DDS_URI:-file://$REPO/src/gcs/cyclonedds_yki.xml}"

# --- Önce çalışan örnekleri durdur (IDEMPOTENT) ---
# Bu script eskiden mevcut süreçleri kontrol etmiyordu: her çalıştırmada
# yenilerini başlatıp eskilerini bırakıyordu. Sonuç, aynı seri portu isteyen
# N tane esp32_base ve N tane origin yayıncısı — biri portu tutar, diğerleri
# saniyede bir "Device or resource busy" döngüsüne girer. Ölçüldü: art arda
# birkaç başlatmadan sonra 12 esp32_base, 22 origin yayıncısı.
# Sahada bu, teşhisi çok zor bir "bazen çalışıyor" arızası olurdu.
if pgrep -f "esp32_base|swarm_origin_pub|yki_rtcm_reader|qgc_proxy|uvicorn backend" > /dev/null 2>&1; then
  echo "[YKİ] çalışan örnekler bulundu, önce durduruluyor..."
  bash "$(dirname "${BASH_SOURCE[0]}")/yki_durdur.sh"
  sleep 2
fi

# --- ROS 2 ortamı ---
#
# ERKEN PATLA (18 Agustos 2026). Onceden bu satir sessizce basarisiz oluyor,
# betik devam ediyor ve dugumler ROS olmadan baslatilmaya calisiliyordu:
# ekranda 'No such file or directory' + arkasindan normal gorunen dort satir.
# Sonraki kisi YKI'yi ayakta saniyordu. macOS'ta bu HER SEFERINDE oluyor,
# cunku orada ROS apt'ta degil pixi ortaminda.
if [ ! -f "$ROS_SETUP" ]; then
  echo "[YKI] HATA: ROS ortami bulunamadi: $ROS_SETUP" >&2
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "" >&2
    echo "  macOS'tasin. Bu betik dogrudan calistirilmaz; sarmalayiciyi kullan:" >&2
    echo "      bash ~/yelpence-yki-mac/yki_mac.sh" >&2
    echo "" >&2
    echo "  O betik ROS_SETUP / DDS_URI / seri portlari macOS'a gore doldurup" >&2
    echo "  bu dosyayi cagiriyor. Ayrinti: ~/yelpence-yki-mac/README.md" >&2
  else
    echo "  ROS 2 kurulu mu? Kurulum: deploy/yki/kur_yki.sh" >&2
    echo "  Farkli bir yerdeyse: ROS_SETUP=/yol/setup.bash $0" >&2
  fi
  exit 1
fi
source "$ROS_SETUP"
source "$REPO/install/setup.bash"
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="$DDS_URI"

# --- 1) Base bridge (mesh <-> ROS): telemetri alır, guided komut gönderir ---
echo "[YKİ] base bridge başlatılıyor ($BASE_ESP_PORT @ $BASE_ESP_BAUD)..."
$ARKAPLAN bash -c "source '$ROS_SETUP' && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control esp32_bridge --ros-args -r __node:=esp32_base \
  -p serial_port:=$BASE_ESP_PORT -p baud:=$BASE_ESP_BAUD -p agent_id:=10" \
  > /tmp/yki_base_bridge.log 2>&1 < /dev/null &
disown

# --- 1.5) Ortak origin yayıncıları — İKİ tane (bkz. yukarıdaki açıklama) ---
echo "[YKİ] origin yayıncıları başlatılıyor (lat=$ORIGIN_LAT lon=$ORIGIN_LON alt=$ORIGIN_ALT)..."
# (a) public -> backend harita->NED
#
# REMAP ZORUNLU (18 Agustos 2026'da olculdu). swarm_origin_publisher'in
# varsayilan konusu 15 Agustos'ta /swarm/public/origin -> /swarm/internal/origin
# olarak degistirildi (sozlesmeye uyum). Ucaktaki baslat.sh o gun guncellendi,
# BU DOSYA GUNCELLENMEDI: (a) remapsiz kalinca o da internal'a yaziyordu ve
# /swarm/public/origin'e YKI'de HIC KIMSE yazmiyordu.
#
# Belirti sessizdi: telemetri normal akiyor, ama haritaya tiklayinca backend
#   "Origin henuz yok - harita hedefi NED'e cevrilemiyor"  (guided.py:175)
# donuyordu. Ucakta bu bosluğu ic_dis_kopru kapatiyor; YKI'de o dugum kosmuyor.
$ARKAPLAN bash -c "source '$ROS_SETUP' && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control swarm_origin_publisher --ros-args -r __node:=swarm_origin_pub_public \
  -r /swarm/internal/origin:=/swarm/public/origin \
  -p origin_source:=fixed -p fixed_lat:=$ORIGIN_LAT -p fixed_lon:=$ORIGIN_LON -p fixed_alt:=$ORIGIN_ALT -p rate_hz:=1.0" \
  > /tmp/yki_origin_public.log 2>&1 < /dev/null &
disown
# (b) internal -> base bridge -> mesh -> drone (SET_GPS_GLOBAL_ORIGIN)
# Remap YOK: dugumun varsayilani zaten /swarm/internal/origin. Eskiden buradaki
# '-r /swarm/public/origin:=/swarm/internal/origin' satiri BOSA calisiyordu.
$ARKAPLAN bash -c "source '$ROS_SETUP' && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control swarm_origin_publisher --ros-args -r __node:=swarm_origin_pub_internal \
  -p origin_source:=fixed -p fixed_lat:=$ORIGIN_LAT -p fixed_lon:=$ORIGIN_LON -p fixed_alt:=$ORIGIN_ALT -p rate_hz:=1.0" \
  > /tmp/yki_origin_internal.log 2>&1 < /dev/null &
disown

# --- 1.7) RTK okuyucu: u-blox -> ROS -> base bridge -> mesh ---
# Seri portun sahibi esp32_bridge'dir (aynı portu iki süreç açamaz), o yüzden
# RTCM doğrudan porta değil ROS topic'ine gider. Okuyucu AYRI süreç: çökerse
# telemetri ve komut yolu etkilenmez.
# GPS portu takılı değilse okuyucu 2 sn'de bir yeniden dener, YKİ'yi bloke etmez.
#
# BU YÜZDEN KOŞULSUZ BAŞLATILIYOR. Eskiden "port var mı" diye bakılıp yoksa
# HİÇ başlatılmıyordu — okuyucunun kendi tekrar-deneme yeteneğine sıra bile
# gelmiyordu. 31 Temmuz'da tam bu ısırdı: u-blox YKİ açıldıktan SONRA takıldı,
# RTCM hiç akmadı, ve bu ancak drone'a SSH atıp px4_bridge logundaki
# 'rtk: msg=0' sayacına bakınca fark edildi. Artık okuyucu her hâlükârda
# başlar, port gelince kendiliğinden bağlanır.
RTK_GPS_PORT="${RTK_GPS_PORT:-/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00}"
# u-blox CDC-ACM olarak gorunuyor: Linux'ta ttyACM*, macOS'ta cu.usbmodem*.
# ESP ise CH340 (cu.usbserial-*) — ikisi ayri desen, karismiyorlar.
RTK_GPS_PORT="$(seri_port_bul 'RTK GPS' "$RTK_GPS_PORT" \
    /dev/serial/by-id/*u-blox* /dev/cu.usbmodem* /dev/ttyACM*)"
RTK_TOPIC="${RTK_TOPIC:-/swarm/internal/rtcm}"
if [ -e "$RTK_GPS_PORT" ]; then
  echo "[YKİ] RTK okuyucu başlatılıyor ($RTK_GPS_PORT -> $RTK_TOPIC)..."
else
  echo "[YKİ] RTK okuyucu başlatılıyor — GPS portu HENÜZ YOK, takılınca bağlanacak"
fi
$ARKAPLAN bash -c "source '$ROS_SETUP' && source '$REPO/install/setup.bash' && \
  $VENV_KAYNAK \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec python3 '$REPO/src/gcs/backend/rtcm/yki_rtcm_reader.py' \
    --gps-port '$RTK_GPS_PORT' --ros-topic '$RTK_TOPIC'" \
  > /tmp/yki_rtcm.log 2>&1 < /dev/null &
disown

# --- QGC BAGLANTISI (proxy YOK, bilerek) ---------------------------------
# QGC dogrudan UDP 14550'ye baglanir. Her PX4'un MAV_SYS_ID'si AYRI oldugu
# surece QGC onlari ayri arac gorur ve cift yonlu konusur (parametre indirme,
# kalibrasyon, komut hepsi calisir).
#   ylp00 -> 1   ylp01 -> 2   ylp02 -> 3
#
# BURAYA PROXY KOYMAYIN. 31 Temmuz'da sysid cakismasi icin qgc_proxy
# denendi ve ISI BOZDU: MAVROS'un udp-b ucnoktasi bir karsi taraf KESFEDINCE
# yayini birakip o adrese tekil gonderime geciyor. Proxy drone'a paket
# yollayinca MAVROS ona kilitlendi, proxy olunce de telemetri tamamen kesildi
# (olculdu: 14550'de ylp00'dan sifir paket, konteyner restarti gerekti).
# Dogru cozum sysid'leri FCU'da ayirmaktir — PX4 MAV_SYS_ID'yi ancak YENIDEN
# BASLATMADA uyguluyor, o yuzden ilk denemede "yazilmadi" sanilmisti.
# Ayrinti: src/gcs/qgc_proxy.py basligi.

# --- 2) Backend (REST + WebSocket, ros2 modu) ---
echo "[YKİ] backend başlatılıyor (:8000)..."
$ARKAPLAN bash -c "source '$ROS_SETUP' && source '$REPO/install/setup.bash' && \
  $VENV_KAYNAK cd '$REPO/src/gcs' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec uvicorn backend.main:app --host 0.0.0.0 --port 8000" \
  > /tmp/yki_backend.log 2>&1 < /dev/null &
disown

# --- 3) Frontend (Vite dev server) ---
echo "[YKİ] frontend başlatılıyor (:5173)..."
$ARKAPLAN bash -c "cd '$REPO/src/gcs/frontend' && exec npm run dev" \
  > /tmp/yki_frontend.log 2>&1 < /dev/null &
disown

sleep 8
echo ""
echo "[YKİ] Hazır:"
echo "   Arayüz : http://localhost:5173/"
echo "   Backend: http://localhost:8000/"
echo "   Loglar : /tmp/yki_base_bridge.log  /tmp/yki_backend.log  /tmp/yki_frontend.log"
echo ""
echo "   Backend sağlık:"; curl -s -o /dev/null -w "     HTTP %{http_code}\n" http://localhost:8000/api/health 2>/dev/null || echo "     (henüz açılıyor)"
