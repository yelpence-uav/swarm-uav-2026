#!/usr/bin/env bash
# Copyright 2026 Yelpence
# Ucaktaki ESP32'yi Pi UZERINDEN yeniden yukler — RPi kablosu SOKULMEDEN.
#
# NIYE BOYLE: YUKLEME_PROSEDURU.md "firmware yuklerken RPi kablolarini cikar"
# diyor, ama o uyari USB-seri cevirici kullanildigi icin var (iki surucu ayni
# hatta konusur). Pi'nin KENDISINDEN yuklerken hatta tek surucu var: ESP'nin
# Serial0'i (GPIO3/GPIO1) zaten Pi'nin /dev/ttyAMA4'une bagli ve flash portu
# ile veri portu AYNI hat. Sokmeye gerek yok.
#
# 🔴 IKI SART:
#  1) Konteyner DURDURULMALI — esp32_bridge /dev/ttyAMA4'u tutuyor, iki surec
#     ayni portu acarsa baytlar bolunur ve yukleme "chip stopped responding"
#     verir. Betik durduruyor ve sonunda geri baslatiyor.
#  2) 🔴 SIRA KRITIK — 2 Eylul'de sekiz deneme bunun yuzunden kayboldu.
#     Once KONTEYNER DURUR, sonra operator BOOT+EN yapar, esptool o sirada
#     ZATEN sync gonderiyor olur. Ters sirada (cip once indirme moduna
#     alinip konteyner sonra durdurulursa) esp32_bridge 460800'de ROM'a
#     kilobaytlarca mesh verisi basar; ROM o coplu akistan sonra sync'e
#     CEVAP VERMEZ ve belirti "No serial data received" olur — kablo/pin
#     arizasina benzer, degildir. Bu sirayla ylp01 ilk denemede yuklendi.
#     DTR/RTS Pi UART'ina bagli olmadigi icin reset ELLE (--before no_reset).
#
# Kullanim:  ./esp_yukle.sh ylp00 [baud]
# Ornek:     ./esp_yukle.sh ylp00 115200

set -u
D="${1:-}"; BAUD="${2:-460800}"
case "$D" in
    ylp00) KUL=yelpence00; IP=10.38.209.134; KON=drone1 ;;
    ylp01) KUL=yelpence01; IP=10.38.209.156; KON=drone2 ;;
    ylp02) KUL=yelpence02; IP=10.38.209.189; KON=drone3 ;;
    *) echo "kullanim: $0 <ylp00|ylp01|ylp02> [baud]"; exit 1 ;;
esac
H="$KUL@$IP"

echo "=== $D ($KON) — ESP32 yukleme ==="
echo "[1] konteyner durduruluyor (UART serbest kalsin)"
ssh -o BatchMode=yes "$H" "docker stop $KON" || { echo "konteyner durdurulamadi"; exit 1; }

echo
echo "  ############################################################"
echo "  #  ŞİMDİ: $D üzerindeki ESP32'de                            "
echo "  #    1) BOOT tuşunu BASILI TUT                              "
echo "  #    2) EN (reset) tuşuna bas ve bırak                      "
echo "  #    3) BOOT'u bırak                                        "
echo "  #  esptool ~2 dakika deneyecek — ACELE ETME.               "
echo "  ############################################################"
echo

ssh -o BatchMode=yes "$H" "
    cd ~/esp_fw_2eylul || exit 1
    PYTHONPATH=\$HOME/pylib timeout 180 python3 ~/esptool/esptool.py \
        --chip esp32 --port /dev/ttyAMA4 --baud $BAUD \
        --before no_reset --after no_reset \
        --no-stub \
        --connect-attempts 60 \
        write_flash -z --flash_mode dio --flash_freq 40m --flash_size detect \
        0x1000  bootloader.bin \
        0x8000  partitions.bin \
        0xe000  boot_app0.bin \
        0x10000 firmware.bin
"
SONUC=$?

echo
echo "[3] konteyner geri baslatiliyor"
ssh -o BatchMode=yes "$H" "docker start $KON" >/dev/null

if [ "$SONUC" -eq 0 ]; then
    echo "TAMAM — $D yuklendi. ESP'nin EN tusuna bir kez daha basip birak"
    echo "       (--after no_reset: esptool kartı kendisi resetleyemiyor)."
else
    echo "BASARISIZ (kod $SONUC) — ESP indirme modunda miydi?"
    echo "  'chip stopped responding' -> BOOT/EN sirasi tekrarlanmali"
    echo "  'could not open port'     -> konteyner hala UART'i tutuyor olabilir"
fi
exit "$SONUC"
