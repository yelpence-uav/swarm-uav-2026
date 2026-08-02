#!/bin/bash
# =============================================================================
# Drone Pi'sine teşhis altyapısı kurar. root gerekir:  sudo bash izleme_kur.sh
#
# Neden: 29 Temmuz'da ylp00 kendiliğinden kapandı. Dosya sisteminde "orphan
# cleanup" izi vardı (temiz kapanmamış), ama SEBEBİ okunamadı çünkü journal
# RAM'de tutuluyordu ve yeniden başlatmada silinmişti. Bu script o kör noktayı
# kapatır: bir dahaki sefere "güç mü kesildi, sistem mi dondu" sorusu
# journalctl -b -1 ile cevaplanabilir.
#
# Üç iş yapar:
#   1) Saat dilimini Europe/Istanbul'a alır (fabrika ayarı Europe/London'dı —
#      Pi günlükleriyle laptop günlükleri 2 saat kayıyordu).
#   2) journald'ı kalıcı yapar, 200 MB tavanla (SD kart dolmasın).
#   3) Dakikada bir besleme voltajı/throttle/sıcaklık kaydeden timer kurar.
#      Çökme journal'ı silse bile voltajın düştüğü an dosyada kalır.
#
# Yük: timer dakikada bir vcgencmd çağırır (ölçülemeyecek kadar küçük),
# günde ~100 KB yazar, 5 MB'ı geçince kendini kırpar.
# =============================================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "HATA: root gerekiyor -> sudo bash $0" >&2
    exit 1
fi

echo "--- 1/3  saat dilimi ---"
timedatectl set-timezone Europe/Istanbul

echo "--- 2/3  kalıcı journal ---"
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/10-kalici.conf <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=200M
SystemMaxFileSize=50M
SystemMaxFiles=8
EOF
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald

echo "--- 3/3  besleme kaydedici ---"
cat > /usr/local/bin/guc_izle.sh <<'EOF'
#!/bin/bash
# Pi 5 besleme durumunu tek satır olarak kaydeder.
LOG=/var/log/guc_izle.log
ts=$(date -Is)
th=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
v=$(vcgencmd pmic_read_adc EXT5V_V 2>/dev/null | grep -oE '=[0-9.]+V' | tr -d '=V')
t=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2)
printf '%s throttled=%s ext5v=%s temp=%s\n' "$ts" "$th" "$v" "$t" >> "$LOG"
# logrotate kurulu değil — 5 MB'ı geçerse son 20000 satırı tut.
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5242880 ]; then
    tail -n 20000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
EOF
chmod +x /usr/local/bin/guc_izle.sh

cat > /etc/systemd/system/guc-izle.service <<'EOF'
[Unit]
Description=Pi 5 besleme (voltaj/throttle/sicaklik) kaydi

[Service]
Type=oneshot
ExecStart=/usr/local/bin/guc_izle.sh
Nice=19
IOSchedulingClass=idle
EOF

cat > /etc/systemd/system/guc-izle.timer <<'EOF'
[Unit]
Description=Besleme kaydini dakikada bir calistir

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now guc-izle.timer
/usr/local/bin/guc_izle.sh          # ilk satırı hemen yaz

echo
echo "=== KURULDU ==="
echo -n "saat dilimi : "; timedatectl show -p Timezone --value
echo -n "journal     : "; grep -h '^Storage' /etc/systemd/journald.conf.d/10-kalici.conf
echo -n "timer       : "; systemctl is-active guc-izle.timer || true
echo    "ilk kayıt   : $(tail -1 /var/log/guc_izle.log 2>/dev/null)"
echo
echo "Bundan sonra beklenmedik kapanmadan SONRA:"
echo "    journalctl -b -1 -e          # önceki oturumun son satırları"
echo "    tail -20 /var/log/guc_izle.log"
