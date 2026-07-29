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
echo "--- 1/4  saat dilimi ---"
timedatectl set-timezone Europe/Istanbul
echo "    $(timedatectl show -p Timezone --value)"

# ------------------------------------------------------------- 2) journal ---
echo "--- 2/4  kalıcı journal + okuma yetkisi ---"
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
echo "--- 3/4  izleme scripti ---"
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
echo "--- 4/4  timer ---"
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
echo "ilk satir   : $(tail -1 /var/log/yelpence_izle.log 2>/dev/null)"
echo
echo "Sonradan bakmak icin:"
echo "    tail -40 /var/log/yelpence_izle.log      # dakika dakika durum"
echo "    cat /var/log/yelpence_olay.log           # sadece ariza anlari"
echo "    journalctl -b -1 -e                      # onceki oturumun sonu"
