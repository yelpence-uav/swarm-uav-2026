#!/bin/bash
# =============================================================================
# RPi ANLIK DURUM — YKI'deki "RPi" panelinin veri kaynagi.
#
# 🔴 BU VERI MESH'TEN GECMEZ. Operator karari (29 Agustos 2026): Pi saglik
# bilgisi YALNIZ SSH ile gelir. Mesh 16 baytlik paketler tasiyor ve gorev
# telemetrisi icin; oraya tesihs verisi koymak dar bandi yer.
# SSH yoksa bilgi de yok — panel bunu acikca soyluyor, tahmin uretmiyor.
#
# NASIL CAGRILIR (dagitim GEREKMEZ, stdin'den gecer):
#   ./deploy/yki/drone_bul.sh ylp00 'bash -s' < deploy/rpi/teshis/rpi_durum.sh
#
# CIKTI: `anahtar=deger` satirlari. Deger bulunamazsa anahtar HIC yazilmaz —
# arayuz "bilinmiyor" gostersin, 0 gostermesin (0 gercek bir olcum sanilir).
# =============================================================================
WS="$HOME/yelpence_ws"

yaz() { [ -n "${2:-}" ] && printf '%s=%s\n' "$1" "$2"; }

# --- kimlik / calisma suresi ---
yaz host      "$(hostname 2>/dev/null)"
yaz uptime_sn "$(cut -d. -f1 /proc/uptime 2>/dev/null)"
yaz cekirdek  "$(nproc 2>/dev/null)"

# --- sicaklik ve besleme (Pi 5 PMIC; vcgencmd yalniz HOST'ta var) ---
yaz sicaklik_c "$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 | tr -d "'C")"
yaz gerilim_v  "$(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null | grep -oE '=[0-9.]+V' | tr -d '=V')"
# throttled biti: 0x0 = temiz. Sifirdan farkliysa besleme/isil kisitlama var.
yaz throttled  "$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"

# --- CPU ---
# /proc/stat'tan 300 ms'lik ORNEK: loadavg "kac surec kuyrukta" der,
# "CPU yuzde kac dolu" DEMEZ. Operatorun sordugu ikincisi.
read -r _ u1 n1 s1 i1 w1 q1 sq1 _ < /proc/stat
sleep 0.3
read -r _ u2 n2 s2 i2 w2 q2 sq2 _ < /proc/stat
t1=$((u1+n1+s1+i1+w1+q1+sq1)); t2=$((u2+n2+s2+i2+w2+q2+sq2))
bos=$((i2-i1)); top=$((t2-t1))
[ "$top" -gt 0 ] && yaz cpu_yuzde "$(( (100*(top-bos)) / top ))"
yaz yuk_1dk "$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)"

# --- bellek (MB) ---
yaz mem_toplam_mb "$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null)"
yaz mem_bos_mb    "$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo 2>/dev/null)"
yaz takas_mb      "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{if(t>0) print int((t-f)/1024)}' /proc/meminfo 2>/dev/null)"

# --- disk: kok ve ucus kayitlari AYRI. Kayit diski dolunca bir sonraki
#     ucus KAYDEDILMEZ; 14 Agustos'ta iki dronun da diski %100 doldu. ---
yaz disk_yuzde "$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"
yaz disk_bos   "$(df -h --output=avail / 2>/dev/null | tail -1 | tr -d ' ')"
[ -d "$WS/kayit" ] && yaz kayit_mb "$(du -sm "$WS/kayit" 2>/dev/null | cut -f1)"

# --- sicaklik/guc kisitlamasi disinda: ag ---
yaz wifi_ssid "$(iw dev wlan0 link 2>/dev/null | awk '/SSID/{print $2}')"
yaz wifi_dbm  "$(awk -v i='wlan0:' '$1==i {print int($4)}' /proc/net/wireless 2>/dev/null)"

# --- uygulama katmani ---
yaz konteyner "$(docker ps --format '{{.Names}}' 2>/dev/null | paste -sd, -)"
yaz konteyner_durum "$(docker ps -a --format '{{.Names}}:{{.Status}}' 2>/dev/null | paste -sd'|' -)"
yaz ros_surec "$(pgrep -cf 'mavros|swarm_|px4_bridge' 2>/dev/null)"

# --- izleme dosyasinin tazeligi: eskiyse yelpence-izle timer'i durmus ---
[ -f "$WS/sistem_durum" ] && yaz izleme_yas_sn "$(( $(date +%s) - $(stat -c %Y "$WS/sistem_durum") ))"
