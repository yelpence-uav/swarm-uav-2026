#!/bin/bash
# Copyright 2026 Yelpence
# ============================================================================
# SAHA KURULUMU — origin'i uçaklara eşitle + irtifa düzlemini zemine otur.
#
#     ./deploy/yki/saha_kur.sh
#
# Başka argüman yok. Uçaklar AÇIK ve YERDE olmalı. İstediğin kadar tekrar
# çalıştırabilirsin; değişecek bir şey yoksa hiçbir şeye dokunmaz.
#
# ---------------------------------------------------------------------------
# 🔴 NİYE VAR — 8/9 Eylül 2026 gecesi iki ayrı arıza, ikisi de SESSİZ
#
# ① ORIGIN İKİ YERDEN YAYINLANIYOR. YKİ `deploy/saha_origin.env`'den okuyup
#    mesh'ten gönderiyor; her uçak da kendi `/ws/origin` dosyasından yerel
#    olarak yayınlıyor. İkisi ayrışırsa px4_bridge origin'i dönüşümlü görür,
#    `_origin_dogrula` sapmayı yakalar, `origin_synced` 0'a düşer, uçak aktif
#    kadrodan çıkar ve ÖN KONTROL ARM'A İZİN VERMEZ.
#    Belirti hiçbir yerde "origin" demiyor: operatör BAŞLAT'a basıyor ve
#    HİÇBİR ŞEY olmuyor. 9 Eylül'de sebebi bulmak saatler aldı.
#
# ② ORIGIN_ALT ZEMİNDE OLMAK ZORUNDA. O sayı PX4'ün yerel z=0 düzlemini
#    nereye koyacağını belirler; zeminden farklıysa HER irtifa komutu o
#    kadar kayar. Ölçüldü: 3.33 m fazlaydı, "10 m" komutu uçağı 13.3 m'ye
#    çıkarıyordu, "15 m" ise 18.3 m'ye — kameranın QR okuma tavanı 16.64 m
#    (KAMERA.md §13), yani QR'lar okunamayacak yükseklikte aranıyordu.
#    Aynı hata 1 Ağustos'ta 1.54 m ile yaşandı ve haftalarca "irtifa
#    sıçraması" diye semptom verdi.
#
# GPS'ten okunan irtifa ZEMİN AMSL'İ DEĞİLDİR — bu yüzden ölçüm şöyle
# yapılır: origin yazılı hâlde, uçaklar yerdeyken `local_position/pose.z`
# okunur. Sıfırdan sapma ne kadarsa ORIGIN_ALT o kadar düzeltilir.
#
# ⚠️ RTK BAZI YENİDEN SURVEY EDİLDİYSE bunu TEKRAR koştur — irtifa kestirimi
#    GPS çözümüne bağlı, survey değişince kayar.
# ⚠️ Bu betik konteynerleri yeniden başlatabilir → QR TABLOSU VE TAKIM SLOTU
#    SİLİNİR. Bu yüzden QR'ları sermeden ÖNCE çalıştır.
# ============================================================================
set -u

BETIK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$BETIK/../.." && pwd)"
ORIGIN_ENV="$REPO/deploy/saha_origin.env"
BUL="$BETIK/drone_bul.sh"

# ad : kullanıcı : konteyner : ROS ad alanı
UCAKLAR=("ylp00:yelpence00:drone1:drone_1"
         "ylp01:yelpence01:drone2:drone_2"
         "ylp02:yelpence02:drone3:drone_3")

TOLERANS_M=0.30      # bu kadar sapma kabul; altındaysa dokunma
BEKLE_DUGUM_S=90     # restart sonrası düğümlerin açılması için

hata_var=0
kirmizi() { echo "🔴 $*"; hata_var=1; }
yesil()   { echo "✅ $*"; }
sari()    { echo "⚠️  $*"; }

if [ ! -f "$ORIGIN_ENV" ]; then
  kirmizi "$ORIGIN_ENV yok — saha origin'i tanımlı değil."; exit 1
fi
# shellcheck disable=SC1090
. "$ORIGIN_ENV"
BEKLENEN="$ORIGIN_LAT $ORIGIN_LON $ORIGIN_ALT"

echo "════════════════════════════════════════════════════════"
echo " SAHA KURULUMU"
echo " beklenen origin: $BEKLENEN"
echo "════════════════════════════════════════════════════════"

# --- yardımcılar -----------------------------------------------------------
ucak_oku() {            # $1=kullanıcı  $2=komut  -> stdout
  timeout 90 "$BUL" "$1" "$2" 2>/dev/null | grep -vE '^\.\.\.|^\[' || true
}

yerel_z() {             # $1=kullanıcı $2=konteyner $3=ns -> "-3.268" ya da boş
  ucak_oku "$1" "docker exec -e ROS_LOCALHOST_ONLY=1 $2 bash -lc \
    'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1; \
     source /ws/install/setup.bash >/dev/null 2>&1; \
     timeout 10 ros2 topic echo --once /$3/mavros/local_position/pose 2>/dev/null \
     | sed -n \"/position:/,/orientation/p\" | grep -w z'" \
    | grep -oE '\-?[0-9]+\.[0-9]+' | head -1
}

konteyner_baslat() {
  echo "   konteynerler yeniden başlatılıyor..."
  for u in "${UCAKLAR[@]}"; do
    IFS=: read -r ad kul kap _ns <<< "$u"
    if timeout 90 "$BUL" "$kul" "docker restart $kap" >/dev/null 2>&1; then
      echo "     $ad ✓"
    else
      sari "  $ad yeniden başlatılamadı"
    fi
  done
  echo "   düğümlerin açılması bekleniyor (${BEKLE_DUGUM_S} sn)..."
  sleep "$BEKLE_DUGUM_S"
}

# ════════════════════════════════════════════════════════════════════════
# 🔴 RTK ÖNCE OTURMALI — irtifa kestirimi GPS çözümüne bağlı. Baz yeniden
# survey edilince ya da çözüm float'ta kalınca ölçüm metre mertebesinde
# kayar; tolerans ise 30 cm. RTK oturmadan kalibre edersen, oturduğunda
# tekrar kalibre etmen gerekir.
#   fix_type: 6 = RTK FIXED (istenen) · 5 = RTK float · 4 = DGPS · 3 = 3D
echo
echo "── 0/4 · RTK ÇÖZÜMÜ ────────────────────────────────────"
rtk_zayif=0
for u in "${UCAKLAR[@]}"; do
  IFS=: read -r ad kul kap ns <<< "$u"
  fix="$(ucak_oku "$kul" "docker exec -e ROS_LOCALHOST_ONLY=1 $kap bash -lc \
    'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1; \
     source /ws/install/setup.bash >/dev/null 2>&1; \
     timeout 8 ros2 topic echo --once /$ns/mavros/gpsstatus/gps1/raw 2>/dev/null \
     | grep -w fix_type'" | grep -oE '[0-9]+' | head -1)"
  case "${fix:-yok}" in
    6)   yesil "$ad : fix_type 6 (RTK FIXED)" ;;
    yok) sari "$ad : fix_type okunamadı"; rtk_zayif=1 ;;
    *)   sari "$ad : fix_type $fix — RTK OTURMAMIŞ"; rtk_zayif=1 ;;
  esac
done
if [ "$rtk_zayif" = "1" ]; then
  echo
  sari "RTK oturmadan yapılan irtifa ölçümü METRE mertebesinde kayabilir."
  echo "    Origin dosyası yine de eşitlenecek (o RTK'dan bağımsız)."
  echo "    🔴 RTK FIXED olunca BU BETİĞİ TEKRAR ÇALIŞTIR."
fi

echo
echo "── 1/4 · ORIGIN DOSYASI ────────────────────────────────"
sapan=0
for u in "${UCAKLAR[@]}"; do
  IFS=: read -r ad kul _kap _ns <<< "$u"
  satir="$(ucak_oku "$kul" 'cat ~/yelpence_ws/origin 2>/dev/null' | head -1 | tr -s ' ' | sed 's/^ *//; s/ *$//')"
  if [ -z "$satir" ]; then
    kirmizi "$ad : origin dosyası OKUNAMADI (uçak kapalı ya da ağda değil)"
    sapan=1
  elif [ "$satir" = "$BEKLENEN" ]; then
    yesil "$ad : $satir"
  else
    sari "$ad : $satir   ← BEKLENEN DEĞİL"
    sapan=1
  fi
done

if [ "$sapan" = "1" ] && [ "$hata_var" = "0" ]; then
  echo
  echo "   Origin uçaklara dağıtılıyor..."
  if "$REPO/deploy/rpi/dagit.sh" --paket swarm_missions >/dev/null 2>&1; then
    echo "   dağıtım tamam"
  else
    sari "  dağıtım sorunlu — çıktıyı elle kontrol et"
  fi
  konteyner_baslat
fi

# ════════════════════════════════════════════════════════════════════════
echo
echo "── 2/4 · İRTİFA DÜZLEMİ (yerel z, uçaklar YERDE) ───────"
topla=0; adet=0
for u in "${UCAKLAR[@]}"; do
  IFS=: read -r ad kul kap ns <<< "$u"
  z="$(yerel_z "$kul" "$kap" "$ns")"
  if [ -z "$z" ]; then
    sari "$ad : yerel z OKUNAMADI"
    continue
  fi
  # 🔴 HAVADAKİ UÇAKLA KALİBRASYON FELAKET OLUR: z havadaki irtifayı
  # ölçer, betik onu "origin sapması" sanıp ORIGIN_ALT'ı o kadar kaydırır
  # ve bundan sonraki BÜTÜN irtifa komutları o kadar yanlış olur.
  # İki kapı: ① ARM durumu (kesin ölçü) ② z büyüklüğü (yedek).
  armed="$(ucak_oku "$kul" "docker exec -e ROS_LOCALHOST_ONLY=1 $kap bash -lc \
    'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1; \
     source /ws/install/setup.bash >/dev/null 2>&1; \
     timeout 8 ros2 topic echo --once /$ns/mavros/state 2>/dev/null | grep -w armed'" \
    | grep -oE 'true|false' | head -1)"
  if [ "$armed" = "true" ]; then
    kirmizi "$ad : ARMED — uçak havada/motorlar dönüyor. KALİBRASYON İPTAL."
    exit 1
  fi
  if python3 -c "import sys; sys.exit(0 if abs(float('$z')) > 10.0 else 1)"; then
    kirmizi "$ad : yerel z = $z m — 10 m'yi aşıyor, uçak havada olabilir. İPTAL."
    echo "        (gerçekten yerdeyse origin bu kadar bozuk demektir; elle bak)"
    exit 1
  fi
  echo "   $ad : z = $z m"
  topla="$(python3 -c "print($topla + ($z))")"
  adet=$((adet + 1))
done

if [ "$adet" -eq 0 ]; then
  kirmizi "Hiçbir uçaktan ölçüm alınamadı — kalibrasyon YAPILAMADI."
  echo; echo "SONUÇ: HAZIR DEĞİL"; exit 1
fi

ort="$(python3 -c "print(f'{$topla/$adet:.3f}')")"
echo "   ortalama: $ort m   ($adet uçak)"

if python3 -c "import sys; sys.exit(0 if abs(float('$ort')) <= $TOLERANS_M else 1)"; then
  yesil "irtifa düzlemi zeminde (sapma ≤ ${TOLERANS_M} m) — düzeltme gerekmiyor"
else
  yeni="$(python3 -c "print(f'{float(\"$ORIGIN_ALT\") + float(\"$ort\"):.2f}')")"
  echo
  echo "   ORIGIN_ALT düzeltiliyor: $ORIGIN_ALT → $yeni   (sapma $ort m)"
  python3 - "$ORIGIN_ENV" "$yeni" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
yeni, n = re.subn(r'^ORIGIN_ALT=.*$', f'ORIGIN_ALT={sys.argv[2]}', s, flags=re.M)
assert n == 1, 'ORIGIN_ALT satiri bulunamadi'
p.write_text(yeni)
PY
  echo "   dağıtılıyor..."
  "$REPO/deploy/rpi/dagit.sh" --paket swarm_missions >/dev/null 2>&1 \
    && echo "   dağıtım tamam" || sari "  dağıtım sorunlu"
  konteyner_baslat

  echo "   doğrulama ölçümü..."
  t2=0; a2=0
  for u in "${UCAKLAR[@]}"; do
    IFS=: read -r ad kul kap ns <<< "$u"
    z="$(yerel_z "$kul" "$kap" "$ns")"
    [ -z "$z" ] && continue
    echo "     $ad : z = $z m"
    t2="$(python3 -c "print($t2 + ($z))")"; a2=$((a2 + 1))
  done
  if [ "$a2" -gt 0 ]; then
    o2="$(python3 -c "print(f'{$t2/$a2:.3f}')")"
    if python3 -c "import sys; sys.exit(0 if abs(float('$o2')) <= $TOLERANS_M else 1)"; then
      yesil "düzeltme tuttu — ortalama $o2 m"
    else
      kirmizi "düzeltmeden SONRA hâlâ $o2 m sapma var — elle bak"
    fi
  else
    sari "doğrulama ölçümü alınamadı"
  fi
fi

# ════════════════════════════════════════════════════════════════════════
echo
echo "── 3/4 · ORIGIN OTURDU MU (arm'ın ön şartı) ────────────"
for u in "${UCAKLAR[@]}"; do
  IFS=: read -r ad kul kap _ns <<< "$u"
  sat="$(ucak_oku "$kul" "docker exec $kap bash -lc \
        'grep -h origin_synced /ws/gunluk/son/swarm_fsm.log 2>/dev/null | tail -1'" | tail -1)"
  if [ -z "$sat" ]; then
    yesil "$ad : origin uyarısı yok"
  else
    kirmizi "$ad : $(echo "$sat" | cut -c1-110)"
  fi
done

echo
echo "════════════════════════════════════════════════════════"
if [ "$hata_var" = "0" ]; then
  echo " SONUÇ: HAZIR"
  echo " Sıradaki: QR'ları ser → takım slotunu gir → kuru test → BAŞLAT"
else
  echo " SONUÇ: HAZIR DEĞİL — yukarıdaki 🔴 satırlara bak"
fi
echo "════════════════════════════════════════════════════════"
[ "$hata_var" = "0" ]
