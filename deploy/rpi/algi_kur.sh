#!/bin/bash
# Algi zincirinin konteyner bagimliliklarini kurar.  $1 = konteyner adi
#
# NEDEN VAR: bu paketler konteynerin YAZILABILIR KATMANINDA duruyor.
# `docker rm` + `docker run` (bekleyen A19 gibi) yapilinca HEPSI GIDER ve
# camera_driver/vision_node sessizce calismaz hale gelir — import hatasi
# verir ama uctan uca bakan biri "kamera bozuldu" sanir.
#
# Yeniden olusturmadan sonra tek komut:
#     ./deploy/yki/drone_bul.sh ylp02 'bash ~/yelpence_ws/algi_kur.sh drone3'
#
# NE KURAR ve NICIN (28 Agustos 2026'da olculdu):
#   python3-opencv      JPEG cozme, renk tespiti, wechat_qrcode
#                       --no-install-recommends ZORUNLU: recommends ile
#                       1203 MB, onsuz 709 MB. Aradaki 494 MB video
#                       hizlandirma surucusu, bassiz konteynerde kullanilmaz.
#   python3-pyzbar      QR — YEDEK cozucu (zxing yoksa buna duser)
#   zxing-cpp (pip)     QR — BIRINCIL cozucu. pyzbar ile ayni menzil, yari
#                       sure, ve QR yokken de ayni surede biter
#                       (tam kare: pyzbar 628 ms, zxing 275 ms).
set -o pipefail
K="${1:?konteyner adi gerekli (ornek: drone3)}"

echo "=== $K: algi bagimliliklari ==="
docker exec "$K" python3 -c 'import cv2, pyzbar' 2>/dev/null \
    && echo "  opencv + pyzbar zaten var" \
    || {
        echo "  apt guncelleniyor (uzun surebilir)..."
        docker exec -u root "$K" apt-get -qq update >/dev/null 2>&1 || {
            echo "  ⚠ apt-get update BASARISIZ — konteynerin interneti var mi?"
            exit 1
        }
        echo "  opencv + pyzbar kuruluyor (~709 MB)..."
        docker exec -u root "$K" apt-get install -y -qq \
            --no-install-recommends python3-opencv python3-pyzbar 2>&1 | tail -3
    }

docker exec "$K" python3 -c 'import zxingcpp' 2>/dev/null \
    && echo "  zxing-cpp zaten var" \
    || {
        echo "  zxing-cpp kuruluyor (~5 MB)..."
        docker exec -u root "$K" apt-get install -y -qq \
            --no-install-recommends python3-pip >/dev/null 2>&1
        docker exec -u root "$K" python3 -m pip install --quiet \
            --break-system-packages zxing-cpp 2>&1 | grep -v WARNING | tail -2
    }

echo "=== dogrulama ==="
# Dogrulama Python'u AYRI DOSYAYA yazilip borudan veriliyor. Ic ice heredoc
# + tirnak bugun uc kez isirdi: tek tirnaklar disaridaki `bash -lc '...'`
# dizgisini kapatip Python'u bozuyor.
DOG=$(mktemp)
cat > "$DOG" <<'PYKOD'
import importlib

TAMAM = True
for modul, nicin in (('cv2', 'JPEG cozme + renk'),
                     ('pyzbar.pyzbar', 'QR yedek'),
                     ('zxingcpp', 'QR birincil'),
                     ('numpy', 'dizi islemleri')):
    try:
        importlib.import_module(modul)
        print(f'  [+] {modul:16s} {nicin}')
    except ImportError:
        print(f'  [!] {modul:16s} {nicin}  -- EKSIK')
        TAMAM = False

try:
    import cv2
    var = hasattr(cv2, 'wechat_qrcode_WeChatQRCode')
    print(f'  [{"+" if var else "!"}] {"wechat_qrcode":16s} '
          f'QR menzil yedegi (~40 m)')
except ImportError:
    pass

raise SystemExit(0 if TAMAM else 1)
PYKOD
docker exec -i "$K" bash -lc 'source /opt/ros/jazzy/setup.bash 2>/dev/null; python3 -' < "$DOG"
SONUC=$?
rm -f "$DOG"
exit $SONUC
