#!/bin/bash
# Algi imajini bir ucaga tasir ve yukler.  $1 = ucak adi (ylp00/ylp01/ylp02)
#
# NEDEN VAR (KARAR-09, 28 Agustos 2026): 28 Agustos'ta ucaklar arasi imaj
# ayrismasi BASLADI. 20 Agustos'ta ylp00 ve ylp02'de imaj kimligi ayniydi
# (661296d…); kameraya opencv/pyzbar/zxing eklenince ylp02 ea2c1b1e… oldu.
# Operator karari: konteynerler ESITLENSIN — kamerasi olmayan ucakta bu
# paketlerin bulunmasi yalnizca 760 MB disk demek, dugumler zaten acilmiyor.
#
# ⚠️ `docker load` CALISAN KONTEYNERI DEGISTIRMEZ. Konteyner eski imajin
# kimligine bagli; yeni imaj ancak konteyner YENIDEN OLUSTURULUNCA
# (`docker rm` + `run_drone.sh`) kullanilir. Bu betik bilerek yeniden
# olusturmuyor — o ayri bir is (bekleyen A19) ve dikkat istiyor.
#
# KULLANIM
#   ./deploy/yki/imaj_esitle.sh ylp00
set -o pipefail

UCAK="${1:?ucak adi gerekli (ylp00 / ylp01 / ylp02)}"
KOK="$(cd "$(dirname "$0")/../.." && pwd)"
BUL="$KOK/deploy/yki/drone_bul.sh"
YEDEK="$HOME/yelpence-yedek/yelpence-ros-algi-20260828.tar.gz"
ETIKET="yelpence-ros:latest"
ESKI_ETIKET="yelpence-ros:temiz-20260828"

[ -f "$YEDEK" ] || { echo "HATA: yedek yok: $YEDEK"; exit 1; }
BOY=$(du -m "$YEDEK" | cut -f1)
echo "=== $UCAK — algi imaji esitleniyor (${BOY} MB) ==="

IP=$("$BUL" --tablo 2>/dev/null | awk -v u="$UCAK" '$1==u{print $2}')
KUL=$("$BUL" --tablo 2>/dev/null | awk -v u="$UCAK" '$1==u{print $3}')
[ -n "$IP" ] || { echo "HATA: $UCAK agda bulunamadi — acik mi?"; exit 1; }
echo "  $IP ($KUL)"

echo "--- 1) disk ---"
ssh -n -o ConnectTimeout=15 "$KUL@$IP" 'df -h / | tail -1'
BOS=$(ssh -n -o ConnectTimeout=15 "$KUL@$IP" "df -m / | tail -1 | awk '{print \$4}'")
GEREKLI=$((BOY + 2600))     # tarball + acilmis imaj + pay
if [ "$BOS" -lt "$GEREKLI" ]; then
    echo "HATA: ${BOS} MB bos, ${GEREKLI} MB gerekiyor"; exit 1
fi

echo "--- 2) mevcut imaj ---"
ssh -n -o ConnectTimeout=15 "$KUL@$IP" "docker images yelpence-ros --format '  {{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}'"

echo "--- 3) bilinen-iyi imaji koru ---"
# Yeni imaj :latest'i devralacak; eskisi etiketsiz kalmasin diye
# adlandiriliyor. Zaten varsa dokunmuyoruz.
ssh -n -o ConnectTimeout=15 "$KUL@$IP" \
  "docker image inspect $ESKI_ETIKET >/dev/null 2>&1 || docker tag $ETIKET $ESKI_ETIKET" \
  && echo "  $ESKI_ETIKET hazir"

echo "--- 4) tasima ---"
ADI=$(basename "$YEDEK")
UZAK_BOY=$(ssh -n -o ConnectTimeout=15 "$KUL@$IP" "stat -c%s ~/imaj-yedek/$ADI 2>/dev/null || echo 0")
YEREL_BOY=$(stat -c%s "$YEDEK")
if [ "$UZAK_BOY" = "$YEREL_BOY" ]; then
    echo "  zaten orada, atlaniyor"
else
    ssh -n -o ConnectTimeout=15 "$KUL@$IP" 'mkdir -p ~/imaj-yedek'
    scp -o ConnectTimeout=30 "$YEDEK" "$KUL@$IP:~/imaj-yedek/" || exit 1
fi
ssh -n -o ConnectTimeout=60 "$KUL@$IP" "gzip -t ~/imaj-yedek/$ADI" \
  && echo "  gzip SAGLAM" || { echo "HATA: tasima bozuk"; exit 1; }

echo "--- 5) yukleme (birkac dakika) ---"
ssh -n -o ConnectTimeout=900 "$KUL@$IP" "gunzip -c ~/imaj-yedek/$ADI | docker load" 2>&1 | tail -3

echo "--- 6) dogrulama: YENI imajdan taze konteyner ---"
ssh -n -o ConnectTimeout=300 "$KUL@$IP" "docker run --rm $ETIKET python3 -c \"
import importlib
eksik=[]
for m in ('cv2','pyzbar.pyzbar','zxingcpp','numpy'):
    try: importlib.import_module(m); print('  [+] '+m)
    except ImportError: print('  [!] '+m+'  EKSIK'); eksik.append(m)
raise SystemExit(1 if eksik else 0)\""
SONUC=$?

echo "--- 7) son durum ---"
ssh -n -o ConnectTimeout=15 "$KUL@$IP" "docker images yelpence-ros --format '  {{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}'"
if [ "$SONUC" -eq 0 ]; then
    echo
    echo "✅ $UCAK imaji esitlendi."
    echo "⚠️  CALISAN KONTEYNER HALA ESKI IMAJDA. Yeni imaj ancak konteyner"
    echo "    YENIDEN OLUSTURULUNCA kullanilir (docker rm + run_drone.sh)."
    echo "    Bu betik bunu BILEREK yapmiyor — bekleyen A19 ile birlikte."
else
    echo "❌ $UCAK: dogrulama BASARISIZ"
fi
exit $SONUC
