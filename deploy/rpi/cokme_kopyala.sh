#!/bin/bash
# Cokme izlerini kullanicinin OKUYABILECEGI yere kopyalar.
#
# NEDEN VAR (22 Agustos 2026): systemd-pstore cokme kayitlarini
# /var/lib/systemd/pstore/ altina tasiyor ama dosyalar root:root 0600.
# Sahada teshis yapan kisi (ve Claude) sudo parolasi olmadan OKUYAMIYOR.
# Cokme izinin okunamamasi, hic tutulmamasiyla neredeyse ayni sey.
#
# Bu betik her acilista izleri ~/yelpence_ws/gunluk/cokme/ altina kopyalar.
# Boylece cokme kaydi diger ucus gunlukleriyle AYNI dizinde durur:
# "Pi neden oldu" sorusu tek yerden cevaplanir.
#
# izleme_kur.sh 8/8 tarafindan /usr/local/bin/ altina kurulur ve
# yelpence-cokme.service ile systemd-pstore'dan SONRA calistirilir.
set -u

KAYNAK=/var/lib/systemd/pstore
KULLANICI="${1:-}"
[ -n "$KULLANICI" ] || exit 0

EV=$(getent passwd "$KULLANICI" | cut -d: -f6)
[ -n "$EV" ] || exit 0
HEDEF="$EV/yelpence_ws/gunluk/cokme"

[ -d "$KAYNAK" ] || exit 0
mkdir -p "$HEDEF" || exit 0

kopyalanan=0
for f in "$KAYNAK"/*; do
    [ -e "$f" ] || continue
    ad=$(basename "$f")
    hedef="$HEDEF/$ad"
    # Ayni ad tekrar gelirse USTUNE YAZMA — her cokme ayri kalmali,
    # yoksa ikinci olay birincinin kanitini siler.
    [ -e "$hedef" ] && hedef="$HEDEF/$ad.$(date +%Y%m%d_%H%M%S)"
    cp -a "$f" "$hedef" 2>/dev/null || continue
    chmod 644 "$hedef"
    kopyalanan=$((kopyalanan + 1))
done

chown -R "$KULLANICI:$KULLANICI" "$HEDEF" 2>/dev/null
[ "$kopyalanan" -gt 0 ] && echo "cokme izi kopyalandi: $kopyalanan dosya -> $HEDEF"
exit 0
