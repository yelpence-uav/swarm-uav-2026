#!/bin/bash
# =============================================================================
# Drone Pi'sine teşhis/kayıt altyapısı kurar.   sudo bash izleme_kur.sh
# Idempotent — tekrar çalıştırmak günceller, bozmaz.
#
# NEDEN VAR
# 29 Temmuz'da ylp00 iki AYRI şekilde düştü ve ikisini de sonradan
# açıklayamadık:
#   1) Öğleden sonra: kart tamamen kapandı. Dosya sisteminde "orphan cleanup"
#      izi vardı (temiz kapanmamış) ama SEBEBİ okunamadı — journald RAM'de
#      tutuluyordu, yeniden başlatmada silinmişti.
#   2) Akşam 20:31-20:54: Pi ayaktaydı (voltaj kaydı dakika dakika düşüyor,
#      5.19 V sabit, throttle yok) ama ne mesh'e veri gidiyordu ne de WiFi
#      bağlanıyordu. Yani sistem kısmen kilitlenmişti. Elimizde o ana ait
#      hiçbir kayıt yoktu.
#
# TASARIM
#   normal dakika  -> /var/log/yelpence_izle.log   tek satır, key=value
#   arıza dakikası -> /var/log/yelpence_olay.log   dmesg + ağ + docker fotoğrafı
# Arıza sayılan durumlar: WiFi down, IP yok, konteyner durmuş, ROS süreci yok.
# Böylece dosya normalde şişmez ama olay anında bağlam kaydedilir.
#
# YÜK: dakikada bir avuç /proc okuması + bir docker sorgusu. Ölçülemeyecek
# kadar küçük. Rutin kayıt günde ~150 KB; iki dosya da 5 MB'ı geçince kırpılır.
#
# NE KURAR
#   1) saat dilimi Europe/Istanbul (fabrika ayarı Europe/London'dı; Pi ve
#      laptop günlükleri 2 saat kayıyor, olay eşleştirmesi imkânsızlaşıyordu)
#   2) kalıcı journald (200 MB tavan) + kullanıcıya günlük okuma yetkisi
#   3) dakikada bir çalışan izleme timer'ı
# =============================================================================
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "HATA: root gerekiyor -> sudo bash $0" >&2
    exit 1
fi

KULLANICI="${SUDO_USER:-$(logname 2>/dev/null || echo '')}"

# ---------------------------------------------------------------- 1) saat ---
echo "--- 1/7  saat dilimi ---"
timedatectl set-timezone Europe/Istanbul
echo "    $(timedatectl show -p Timezone --value)"

# ------------------------------------------------------------ 1.5) wifi ---
# SSH'a bazen 20 sn bağlanamama sorununun sebebi: WiFi radyosu boştayken
# uykuya geçiyor, gelen bağlantıyı geç fark ediyor. Ping atmak radyoyu
# uyandırdığı için "ping atınca bağlanıyor" davranışı çıkıyordu. Ölçüldü:
# iki Pi'de de "Power save: on".
#
# nmcli ile kapatıyoruz çünkü NetworkManager yeniden bağlanınca `iw` ile
# yapılan geçici değişikliği geri alır; bağlantı profiline yazmak kalıcıdır.
# wifi.powersave: 2 = kapalı, 3 = açık.
#
# Maliyeti: radyo uyanık kalır, birkaç yüz mW fazla çeker. Motorların yanında
# ölçülemeyecek kadar küçük. WiFi zaten uçuş için kritik hat değil (mesh var),
# yer tarafındaki bakım/hata ayıklama yolu — orada gecikme gerçek zaman kaybı.
echo "--- 2/7  wifi power save ---"
if systemctl is-active --quiet NetworkManager; then
    nmcli -t -f NAME,TYPE connection show 2>/dev/null \
      | awk -F: '$2=="802-11-wireless"{print $1}' \
      | while read -r baglanti; do
            nmcli connection modify "$baglanti" wifi.powersave 2 2>/dev/null \
              && echo "    $baglanti -> powersave kapali"
        done
    nmcli device reapply wlan0 >/dev/null 2>&1 || true
fi
/usr/sbin/iw dev wlan0 set power_save off 2>/dev/null || true   # anlik etki
echo -n "    su anki durum : "; /usr/sbin/iw dev wlan0 get power_save 2>/dev/null || echo "?"

# ------------------------------------------------------------- 2) journal ---
echo "--- 3/7  kalıcı journal + okuma yetkisi ---"
# DOSYA ADI ÖNEMLİ — "10-" ile başlarsa İŞE YARAMAZ.
# Raspberry Pi OS, SD kartı yıpratmamak için journald'ı bilerek RAM'e sabitleyen
# kendi dosyasını koyuyor:
#     /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf -> Storage=volatile
# systemd bütün journald.conf.d dizinlerini dosya adına göre sıralayıp okur ve
# SONRAKİ öncekini ezer. İlk denememiz "10-kalici.conf" adındaydı, 40-'tan önce
# geldiği için sessizce eziliyordu: ayar dosyası yerinde duruyor, journald yine
# RAM'e yazıyordu. Belirti aldatıcıydı — dosyayı okuyunca "Storage=persistent"
# görüyorsun ama etkin değer volatile. "systemd-analyze cat-config
# systemd/journald.conf" birleştirilmiş sonucu gösterir, teşhis oradan çıktı.
# "99-" öneki hem 40-rpi-volatile-storage.conf'tan hem syslog.conf'tan sonra gelir.
#
# Not: RPi OS'in tercihini bilerek eziyoruz. Karşılığında SD kart yazması var,
# bu yüzden 200 MB tavan koyuyoruz. Sahada çökme sebebini okuyabilmek bu maliyete
# değer — 29 Temmuz'da tam olarak bu eksik yüzünden iki arızayı da açıklayamadık.
mkdir -p /etc/systemd/journald.conf.d
rm -f /etc/systemd/journald.conf.d/10-kalici.conf        # eski, etkisiz sürüm
cat > /etc/systemd/journald.conf.d/99-yelpence-kalici.conf <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=200M
SystemMaxFileSize=50M
SystemMaxFiles=8
EOF

# Kullanıcı systemd-journal grubunda değilse journalctl "insufficient
# permissions" der ve boot listesi BOŞ görünür — günlük tutulmuyor sanılır.
if [ -n "$KULLANICI" ]; then
    usermod -aG systemd-journal,adm "$KULLANICI"
    echo "    $KULLANICI -> systemd-journal, adm (yeni oturumda geçerli)"
fi

mkdir -p /var/log/journal
chgrp systemd-journal /var/log/journal
chmod 2755 /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald
sleep 2
journalctl --flush 2>/dev/null || true

# --------------------------------------------------------------- 3) izle ---
echo "--- 4/7  izleme scripti ---"
cat > /usr/local/bin/yelpence_izle.sh <<'BETIK'
#!/bin/bash
# Dakikada bir sistem durumunu tek satır yazar. Arıza görürse ayrıca
# detaylı fotoğraf çeker. systemd timer'dan root olarak çalışır.
IZLE=/var/log/yelpence_izle.log
OLAY=/var/log/yelpence_olay.log
IF=wlan0

kirp() {  # $1 dosya — 5 MB'ı geçerse son 20000 satırı tut
    [ -f "$1" ] || return 0
    [ "$(stat -c%s "$1")" -gt 5242880 ] || return 0
    tail -n 20000 "$1" > "$1.tmp" && mv "$1.tmp" "$1"
}

ts=$(date -Is)
up=$(cut -d. -f1 /proc/uptime)

# --- besleme / sıcaklık (Pi 5 PMIC) ---
thr=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
v=$(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null | grep -oE '=[0-9.]+V' | tr -d '=V')
t=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 | tr -d "'C")

# --- WiFi ---
wifi=$(cat "/sys/class/net/$IF/operstate" 2>/dev/null || echo yok)
ip4=$(ip -4 -o addr show "$IF" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
[ -z "$ip4" ] && ip4=yok
ssid=$(iw dev "$IF" link 2>/dev/null | awk '/SSID/{print $2}')
[ -z "$ssid" ] && ssid=yok
sig=$(awk -v i="$IF:" '$1==i {print int($4)}' /proc/net/wireless 2>/dev/null)
[ -z "$sig" ] && sig=yok

# --- sistem ---
load=$(cut -d' ' -f1 /proc/loadavg)
mem=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
disk=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')

# --- uygulama ---
dok=$(docker ps --format '{{.Names}}' 2>/dev/null | paste -sd, -)
[ -z "$dok" ] && dok=yok
ros=$(pgrep -cf "mavros|swarm_|px4_bridge" 2>/dev/null || echo 0)

printf '%s up=%s v=%s t=%s thr=%s wifi=%s ip=%s ssid=%s sig=%s load=%s mem=%s disk=%s%% dok=%s ros=%s\n' \
    "$ts" "$up" "$v" "$t" "$thr" "$wifi" "$ip4" "$ssid" "$sig" \
    "$load" "$mem" "$disk" "$dok" "$ros" >> "$IZLE"
kirp "$IZLE"

# --- arıza mı? öyleyse bağlam fotoğrafı ---
sorun=""
[ "$wifi" != "up" ]        && sorun="$sorun wifi=$wifi"
[ "$ip4"  = "yok" ]        && sorun="$sorun ip-yok"
[ "$dok"  = "yok" ]        && sorun="$sorun konteyner-yok"
[ "${ros:-0}" -eq 0 ]      && sorun="$sorun ros-yok"
[ "$thr" != "0x0" ]        && sorun="$sorun throttle=$thr"

if [ -n "$sorun" ]; then
    {
        echo "================ $ts  SORUN:$sorun ================"
        echo "--- ag ---"
        ip -brief addr 2>/dev/null
        iw dev "$IF" link 2>/dev/null | head -8
        echo "--- docker ---"
        docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null
        echo "--- basarisiz servisler ---"
        systemctl --failed --no-legend --no-pager 2>/dev/null | head -10
        echo "--- dmesg son 40 ---"
        dmesg -T 2>/dev/null | tail -40
        echo
    } >> "$OLAY"
    kirp "$OLAY"
fi
BETIK
chmod +x /usr/local/bin/yelpence_izle.sh

# Eski surumden kalan dosyayi temizle (v1'de adi guc_izle.sh idi)
rm -f /usr/local/bin/guc_izle.sh
rm -f /etc/systemd/system/guc-izle.service /etc/systemd/system/guc-izle.timer
systemctl disable --now guc-izle.timer 2>/dev/null || true

# --------------------------------------------------------------- 4) timer ---
echo "--- 5/7  timer ---"
cat > /etc/systemd/system/yelpence-izle.service <<'EOF'
[Unit]
Description=Yelpence drone Pi durum kaydi

[Service]
Type=oneshot
ExecStart=/usr/local/bin/yelpence_izle.sh
Nice=19
IOSchedulingClass=idle
EOF

cat > /etc/systemd/system/yelpence-izle.timer <<'EOF'
[Unit]
Description=Durum kaydini dakikada bir calistir

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now yelpence-izle.timer
/usr/local/bin/yelpence_izle.sh

# ---------------------------------------------------------- 6) ucus kaydi ---
# PX4'un kendi ULog'unun yerine gecen kayit. Pixhawk'ta RAM sinirda oldugu icin
# FCU tarafinda logger ACILMIYOR; onun yerine MAVROS'un ZATEN aldigi veriyi
# Pi'de diske yaziyoruz. Pixhawk'a EK YUK BINMEZ — veri hatta nasilsa akiyor,
# biz sadece kaydediyoruz.
#
# ULog'dan eksigi: PX4'un ic uORB konulari (kestirimci innovation'lari,
# aktuator ciktilari, ham sensor 250 Hz+) MAVLink'ten gecmez. Mevcut yayin
# hizlariyla (ATTITUDE_QUAT 20 Hz, ODOMETRY 20 Hz, GLOBAL_POS 10 Hz) 10 Hz'e
# kadar olan olaylar yakalanir — kaza/olay analizi icin yeter, EKF veya
# kontrol ayari icin yetmez. Gerekirse mesaj_hizlari.py'den SECICI olarak
# yukseltilir (hepsi birden degil; her mesaj FCU'da CPU ve biraz RAM demek).
#
# baslat.sh'e DOKUNULMUYOR: Pi'deki surum repodakinden ayrismis durumda ve
# ucus zinciri orada. Kayit ayri bir servis olarak disaridan docker exec ile
# baglaniyor; konteyner yeniden baslatmaya gerek yok, ucus yigini etkilenmez.
echo "--- 6/7  kayit disk bekcisi ---"
# NOT: ucus kaydini (ros2 bag) BU script kurmaz — o /ws/baslat.sh icinde,
# konteynerin icinde calisir. Sebebi: docker exec ile disaridan baglanirsak
# systemd'nin gonderdigi sinyal konteynerin ICINE ulasmaz (Docker iletmez),
# kayit sureci oksuz kalir ve bag indekssiz/acilmaz halde biter. Kayit
# konteynerin icinde baslarsa bu sorun hic olusmuyor.
# Host'a dusen tek is disk yonetimi — asagidaki bekci.

# Disk bekcisi: kayit dizini tavani asarsa EN ESKI parcalari siler.
cat > /usr/local/bin/yelpence_kayit_temizlik.sh <<'BETIK'
#!/bin/bash
# Kayit dizinini tavan altinda tutar. Saatte bir calisir.
set -uo pipefail
TAVAN_MB=5000                       # toplam kayit tavani
for D in /home/*/yelpence_ws/kayit; do
    [ -d "$D" ] || continue
    while :; do
        boyut=$(du -sm "$D" 2>/dev/null | cut -f1)
        [ -z "$boyut" ] && break
        [ "$boyut" -le "$TAVAN_MB" ] && break
        eski=$(ls -1dt "$D"/*/ 2>/dev/null | tail -1)
        [ -z "$eski" ] && break
        echo "$(date -Is) tavan asildi (${boyut}MB) -> siliniyor: $eski" \
            >> /var/log/yelpence_izle.log
        rm -rf "$eski"
    done
done
BETIK
chmod +x /usr/local/bin/yelpence_kayit_temizlik.sh

cat > /etc/systemd/system/yelpence-kayit-temizlik.service <<'EOF'
[Unit]
Description=Kayit dizini tavan bekcisi

[Service]
Type=oneshot
ExecStart=/usr/local/bin/yelpence_kayit_temizlik.sh
Nice=19
IOSchedulingClass=idle
EOF

cat > /etc/systemd/system/yelpence-kayit-temizlik.timer <<'EOF'
[Unit]
Description=Kayit temizligini saatte bir calistir

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
EOF

systemctl disable --now yelpence-kayit.service 2>/dev/null || true
rm -f /etc/systemd/system/yelpence-kayit.service /usr/local/bin/yelpence_kayit.sh
systemctl daemon-reload
systemctl enable --now yelpence-kayit-temizlik.timer

# ------------------------------------------------- 7) yazma geri yazimi ---
# GUC KESINTISINDE VERI KAYBININ UCUNCU KATMANI.
#
# Uygulama write() cagirdiginda veri karta INMEZ, cekirdegin sayfa
# onbellegine yazilir ve orada KIRLI (dirty) bekler. Ne kadar? Olculdu
# (ylp02, 2 Agustos): vm.dirty_expire_centisecs = 3000, yani 30 SANIYE.
# Guc o arada giderse o veri yoktur.
#
# 2 Agustos kazasinda ylp01'in son parcasi tam bu yuzden 0 bayt kaldi
# (rosbag2/mcap tamponlariyla birlikte; onlar baslat.sh'te kapatildi).
# Burasi kapatilmazsa oradaki duzeltmelerin anlami kalmaz: veri sadece
# kullanici alanindan cekirdek alanina taser, yine RAM'de olur.
#
# 1 sn secildi: kayit hizi ~40 KB/s, yani saniyede ~40 KB'lik geri yazim.
# SD kart icin onemsiz bir yuk; yazma birlestirmesini (write coalescing)
# bir miktar azaltir ama kart asinmasi acisindan bu boyutta fark etmez.
# Daha agresif gitmedik (0 = surekli senkron) cunku o gercekten kart omru
# ve gecikme demek.
#
# Bu SISTEM GENELI bir ayar; /proc/sys/vm ad alanina alinmaz, konteynerden
# yazilmaz. Bu yuzden burada, host tarafinda.
echo "--- 7/7  sayfa onbellegi geri yazimi ---"
cat > /etc/sysctl.d/60-yelpence-writeback.conf <<'EOF'
# Ucus kaydinin karta inmesini 30 sn'den 1 sn'ye cek (bkz. izleme_kur.sh 7).
vm.dirty_expire_centisecs = 100
vm.dirty_writeback_centisecs = 100
EOF
sysctl -q --load=/etc/sysctl.d/60-yelpence-writeback.conf
echo "    dirty_expire=$(cat /proc/sys/vm/dirty_expire_centisecs) cs" \
     "writeback=$(cat /proc/sys/vm/dirty_writeback_centisecs) cs"

# ------------------------------------------------------------ dogrulama ---
echo
echo "=== KURULDU ==="
echo -n "saat dilimi : "; timedatectl show -p Timezone --value
echo -n "timer       : "; systemctl is-active yelpence-izle.timer
ETKIN=$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null \
        | grep -E '^\s*Storage=' | tail -1 | cut -d= -f2)
echo "etkin ayar  : Storage=${ETKIN:-?}   (son okunan kazanir)"
echo -n "kalici log  : "
if ls -1 /var/log/journal/ 2>/dev/null | grep -q .; then
    echo "CALISIYOR ($(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMG]' | head -1))"
else
    echo "CALISMIYOR"
    echo "    etkin Storage '$ETKIN' — 'persistent' degilse baska bir drop-in eziyor:"
    systemd-analyze cat-config systemd/journald.conf 2>/dev/null \
        | grep -E '^#.*journald\.conf|^\s*Storage=' | sed 's/^/      /'
fi
echo -n "wifi psave  : "; /usr/sbin/iw dev wlan0 get power_save 2>/dev/null | awk '{print $NF}'
echo -n "ucus kaydi  : "; docker exec $(docker ps --format "{{.Names}}" | grep -E "^drone[0-9]+$" | head -1) pgrep -f "ros2 bag record" >/dev/null 2>&1 && echo "calisiyor (konteyner icinde)" || echo "YOK — baslat.sh guncellendi mi? konteyner yeniden baslatildi mi?"
sleep 4
KDIZIN=$(ls -1dt /home/*/yelpence_ws/kayit/*/ 2>/dev/null | head -1)
if [ -n "$KDIZIN" ]; then
    echo "    aktif bag : $KDIZIN"
    echo -n "    kayitli konu sayisi : "
    ls -1 "$KDIZIN" 2>/dev/null | wc -l
else
    echo "    UYARI: henuz bag dizini yok — 'journalctl -u yelpence-kayit -n 20' ile bak"
fi
echo "ilk satir   : $(tail -1 /var/log/yelpence_izle.log 2>/dev/null)"
echo
echo "Sonradan bakmak icin:"
echo "    tail -40 /var/log/yelpence_izle.log      # dakika dakika durum"
echo "    cat /var/log/yelpence_olay.log           # sadece ariza anlari"
echo "    journalctl -b -1 -e                      # onceki oturumun sonu"
echo "    ls -lt ~/yelpence_ws/kayit/              # ucus kayitlari"
echo "    ls ~/yelpence_ws/gunluk/son/             # bu acilisin dugum ciktilari"
echo "    tail -40 ~/yelpence_ws/gunluk/son/mavros.log   # host'tan, docker'a girmeden"
echo "    ls -1t ~/yelpence_ws/gunluk/             # onceki acilislar (en yeni 10 tutulur)"
echo "    ros2 bag reindex ~/yelpence_ws/kayit/<dizin>  # guc kesildiyse metadata.yaml yok"
