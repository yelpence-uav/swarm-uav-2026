#!/bin/bash
# =============================================================================
# ylp02 KLONUNU ylp01'E DONUSTURUR — 24 Agustos 2026 (tek seferlik)
#
# Neden var: ylp01'in Pi'si 2 Agustos dususunde oldu; ylp02'nin SD imaji
# klonlanip YENI bir Pi'ye takildi. Klon kendini ylp02 saniyor — gercek
# ylp02 acilirsa hostname/mDNS/SSH anahtari CAKISIR. Bu betik kimligi
# ylp01 yapar: kullanici, hostname, SSH host anahtarlari, tgt_system.
#
# root + OTURUM DISI kosmali (usermod, aktif oturumu olan kullaniciyi
# yeniden adlandiramaz). Kurulum (YKI'den, tek satir):
#
#   ssh -t yelpence02@<IP> 'sudo cp ylp01_donusum.sh /usr/local/bin/ && \
#       sudo systemd-run --on-active=15 bash /usr/local/bin/ylp01_donusum.sh'
#
# sonra SSH'tan cik. 15 sn sonra kosar, bitince YENIDEN BASLATIR.
# Kayit: /var/log/ylp01_donusum.log — sorun olursa oradan okunur.
# =============================================================================
set -e
exec >/var/log/ylp01_donusum.log 2>&1
echo "=== donusum basladi: $(date) ==="

# Eski kimligin konteyneri kalksin. drone2, donusum sonrasi YKI'den
# run_drone.sh 2 ile olusturulacak (log dondurmesi de boylece gelir).
docker rm -f drone3 2>/dev/null || true

# yelpence02 oturumlari kapansin ki usermod calisabilsin
pkill -u yelpence02 || true; sleep 3
pkill -9 -u yelpence02 || true; sleep 2

usermod  -l yelpence01 yelpence02
groupmod -n yelpence01 yelpence02
usermod  -d /home/yelpence01 -m yelpence01
echo "kullanici: $(id yelpence01)"

hostnamectl set-hostname ylp01
sed -i 's/\bylp02\b/ylp01/g' /etc/hosts
echo "hostname: $(hostname)"

# SSH host anahtarlari ylp02'nin KOPYASI — iki cihaz ayni anahtarla
# dolasamaz (kimlik ayirt edilemez olur); yeniden uret.
rm -f /etc/ssh/ssh_host_*
dpkg-reconfigure -f noninteractive openssh-server
echo "ssh anahtarlari yeniden uretildi"

# FCU kimligi: ylp01'in Pixhawk'i MAV_SYS_ID=2 (docs/cihazlar.md).
# baslat.sh tgt_system'i bu dosyadan okur, AGENT_ID'den TURETMEZ.
echo 2 > /home/yelpence01/yelpence_ws/tgt_system
chown yelpence01:yelpence01 /home/yelpence01/yelpence_ws/tgt_system
echo "tgt_system: $(cat /home/yelpence01/yelpence_ws/tgt_system)"

echo "=== donusum bitti, yeniden baslatiliyor: $(date) ==="
reboot
