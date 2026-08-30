#!/bin/bash
# Yelpence — Raspberry Pi 5 drone bilgisayarini sifirdan hazirlar.
#
# PI UZERINDE, SUDO ILE kosar:
#     sudo bash pi_hazirla.sh <AGENT_ID>
#
# NEDEN VAR: ylp00 ve ylp02 elle kurulmustu ve adimlar hicbir yerde yaziliydi.
# ylp01 eklenirken (30 Temmuz) hangi ayarin neden gerektigi tek tek ylp00'dan
# geri muhendislikle cikarildi. Bir daha olmasin diye buraya yaziliyor.
#
# IDEMPOTENT: iki kez kosturmak zararsiz. Var olan satiri tekrar eklemez,
# /boot/firmware/config.txt'yi degistirmeden once yedekler.
#
# BU BETIK DOCKER IMAJINI VE ROS CALISMA ALANINI KURMAZ — onlari dizustunden
# dagitim yapiyoruz (bkz. deploy/rpi/dagit.sh ve README notu asagida).
set -euo pipefail

AGENT_ID="${1:-}"
if [ -z "$AGENT_ID" ]; then
    echo "kullanim: sudo bash pi_hazirla.sh <AGENT_ID>   (ylp00=1 ylp01=2 ylp02=3)"
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "HATA: sudo ile calistirin."
    exit 1
fi

# Betigi sudo ile kosturunca $USER root olur; asil kullaniciyi SUDO_USER verir.
KUL="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
BOOT=/boot/firmware
YENIDEN_BASLAT=0

log() { printf '  %s\n' "$*"; }
bas() { printf '\n== %s ==\n' "$*"; }

bas "kullanici: $KUL   agent_id: $AGENT_ID"

# ---------------------------------------------------------------------------
bas "0) Docker"
# Gruplardan ONCE: 'docker' grubu ancak docker kurulunca olusur.
if command -v docker >/dev/null 2>&1; then
    log "kurulu: $(docker --version)"
else
    log "docker YOK — resmi kurulum betigi calistiriliyor (get.docker.com)"
    if curl -fsSL https://get.docker.com -o /tmp/get-docker.sh; then
        sh /tmp/get-docker.sh
        rm -f /tmp/get-docker.sh
        log "kuruldu: $(docker --version 2>/dev/null || echo BASARISIZ)"
        YENIDEN_BASLAT=1
    else
        log "HATA: kurulum betigi indirilemedi (internet var mi?)"
    fi
fi
systemctl enable --now docker >/dev/null 2>&1 && log "servis: enabled+running" \
    || log "UYARI: docker servisi etkinlestirilemedi"

# ---------------------------------------------------------------------------
bas "1) Kullanici gruplari"
# dialout: /dev/ttyAMA* root:dialout — bu grup olmadan Pixhawk ve ESP32
#          seri portlari acilmaz.
# docker : konteyneri sudo'suz yonetmek icin (dagit.sh sudo kullanmiyor).
for g in dialout docker; do
    if getent group "$g" >/dev/null 2>&1; then
        if id -nG "$KUL" | tr ' ' '\n' | grep -qx "$g"; then
            log "$g: zaten uye"
        else
            usermod -aG "$g" "$KUL"
            log "$g: EKLENDI (oturum yenilenince gecerli)"
            YENIDEN_BASLAT=1
        fi
    else
        log "$g: grup YOK (docker kurulu degil olabilir)"
    fi
done

# ---------------------------------------------------------------------------
bas "2) UART (Pixhawk /dev/ttyAMA0, ESP32 /dev/ttyAMA4, suru RC /dev/ttyAMA2)"
# ylp00'dan birebir alindi. uart4-pi5 overlay'i olmadan /dev/ttyAMA4 olusmaz
# ve esp32_bridge portu acamaz.
if [ ! -f "$BOOT/config.txt" ]; then
    log "UYARI: $BOOT/config.txt yok — bu Raspberry Pi OS degil mi?"
else
    cp -n "$BOOT/config.txt" "$BOOT/config.txt.yelpence-yedek" 2>/dev/null || true
    # uart2-pi5 (GPIO4 TX / GPIO5 RX = fiziksel pin 7 / 29) — GOREV 2
    # suru kumandasinin i-BUS alicisi. Alici YALNIZ pilot ucaginda takili
    # ama overlay UCUNDE DE aciliyor: filo tekduze kalsin ve alici baska
    # ucaga tasindiginda tek is kablo olsun. Takili degilken /dev/ttyAMA2
    # olusur ama BOS kalir — zararsiz.
    for satir in "enable_uart=1" "dtparam=uart0=on" "dtoverlay=uart4-pi5" \
                 "dtoverlay=uart2-pi5"; do
        if grep -qxF "$satir" "$BOOT/config.txt"; then
            log "$satir: var"
        else
            echo "$satir" >> "$BOOT/config.txt"
            log "$satir: EKLENDI"
            YENIDEN_BASLAT=1
        fi
    done
fi

# SERI KONSOL UART0'I ISGAL EDER — Pixhawk tam oraya bagli, kalirsa MAVROS
# baglanamaz. ylp00'da cmdline.txt yalnizca "console=tty1" iceriyor.
# ylp01'de (30 Temmuz) "console=serial0,115200" vardi ve bulunan en kritik
# eksikti. Yedek alarak kaldiriyoruz; kaldirmak yalnizca seri LOGIN konsolunu
# kapatir, donanim UART'i etkilenmez.
if [ -f "$BOOT/cmdline.txt" ]; then
    if grep -q "console=serial" "$BOOT/cmdline.txt"; then
        cp -n "$BOOT/cmdline.txt" "$BOOT/cmdline.txt.yelpence-yedek" 2>/dev/null || true
        # cmdline.txt TEK SATIR olmali; sed ile yalnizca console=serial0,... at.
        sed -i 's/console=serial[0-9]*,[0-9]*[[:space:]]*//g' "$BOOT/cmdline.txt"
        log "cmdline.txt: console=serial KALDIRILDI (yedek: cmdline.txt.yelpence-yedek)"
        log "  yeni: $(cat "$BOOT/cmdline.txt")"
        YENIDEN_BASLAT=1
    else
        log "cmdline.txt: seri konsol yok (dogru)"
    fi
    # serial-getty acik kalirsa portu yine tutar.
    if systemctl is-enabled serial-getty@ttyAMA0.service >/dev/null 2>&1; then
        systemctl disable --now serial-getty@ttyAMA0.service >/dev/null 2>&1 \
            && log "serial-getty@ttyAMA0: KAPATILDI"
    fi
fi

# ---------------------------------------------------------------------------
bas "3) Wi-Fi guc tasarrufu"
# SEMPTOM: Pi bir sure bos kalinca SSH'a cevap vermiyor, ~30 sn ping atinca
# uyaniyor. Sebep NetworkManager'in wifi powersave'i. ylp00'da
# 802-11-wireless.powersave=disable yapilmis; ayni ayari uyguluyoruz.
if command -v nmcli >/dev/null 2>&1; then
    BULUNDU=0
    while IFS= read -r c; do
        [ -z "$c" ] && continue
        tip=$(nmcli -t -f connection.type connection show "$c" 2>/dev/null | cut -d: -f2)
        [ "$tip" = "802-11-wireless" ] || continue
        BULUNDU=1
        mevcut=$(nmcli -t -f 802-11-wireless.powersave connection show "$c" 2>/dev/null | cut -d: -f2)
        if [ "$mevcut" = "disable" ] || [ "$mevcut" = "2" ]; then
            log "$c: powersave zaten kapali"
        else
            nmcli connection modify "$c" 802-11-wireless.powersave disable
            log "$c: powersave KAPATILDI (onceki: ${mevcut:-bilinmiyor})"
            nmcli connection up "$c" >/dev/null 2>&1 || true
        fi
    done < <(nmcli -t -f NAME connection show 2>/dev/null)
    [ "$BULUNDU" = 0 ] && log "UYARI: wifi baglantisi bulunamadi"
else
    log "UYARI: nmcli yok — powersave elle kapatilmali"
fi

# ---------------------------------------------------------------------------
bas "4) Docker"
if command -v docker >/dev/null 2>&1; then
    log "kurulu: $(docker --version)"
    systemctl is-enabled docker >/dev/null 2>&1 \
        && log "servis: enabled" \
        || { systemctl enable docker >/dev/null 2>&1 && log "servis: ETKINLESTIRILDI"; }
else
    log "docker YOK. Kurulum:"
    log "    curl -fsSL https://get.docker.com | sudo sh"
    log "    sudo usermod -aG docker $KUL"
fi

# ---------------------------------------------------------------------------
bas "5) Saat dilimi"
# Gunluk klasor adlari Istanbul damgali (baslat.sh). Host UTC'de kalirsa
# gunlukler journald ile 3 saat kayar ve olay eslestirmek zorlasir.
TZ_MEVCUT=$(timedatectl show -p Timezone --value 2>/dev/null || echo '?')
if [ "$TZ_MEVCUT" = "Europe/Istanbul" ]; then
    log "zaten Europe/Istanbul"
else
    timedatectl set-timezone Europe/Istanbul 2>/dev/null \
        && log "Europe/Istanbul yapildi (onceki: $TZ_MEVCUT)" \
        || log "UYARI: saat dilimi ayarlanamadi (mevcut: $TZ_MEVCUT)"
fi

# ---------------------------------------------------------------------------
bas "SONUC"
if [ "$YENIDEN_BASLAT" = 1 ]; then
    log "YENIDEN BASLATMA GEREKLI (UART overlay ve/veya grup uyeligi icin):"
    log "    sudo reboot"
else
    log "yeniden baslatma gerekmiyor."
fi
log ""
log "Sirada (dizustunden):"
log "  1. docker imajini aktar:  ylp00'da 'docker save yelpence-ros | gzip' ->"
log "     bu Pi'de 'gunzip | docker load'"
log "  2. ~/yelpence_ws olustur, Dockerfile/baslat.sh/mesaj_hizlari.py kopyala"
log "  3. konteyneri yarat (agent_id=$AGENT_ID, --network host, --restart"
log "     unless-stopped, -v ~/yelpence_ws:/ws, --device ttyAMA0 ve ttyAMA4)"
log "  4. deploy/rpi/dagit.sh ile kaynak senkronu + colcon build"
