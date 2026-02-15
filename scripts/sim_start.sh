#!/bin/bash

# Hata olsa bile scriptin devam etmesi ve job control için
set -m

# --- KRİTİK EKLEME BAŞLANGICI ---
# Docker exec ile çalıştırıldığında ortam değişkenleri yüklü gelmez.
# Bu yüzden script çalışmadan önce ROS ve Gazebo'yu kendisi yüklemelidir.
source /opt/ros/jazzy/setup.bash

# Eğer projemiz derlenmişse onu da ekle
if [ -f /home/yelpence/ros2_ws/install/setup.bash ]; then
    source /home/yelpence/ros2_ws/install/setup.bash
fi
# --- KRİTİK EKLEME BİTİŞİ ---

# Varsayılan dünya dosyası
WORLD_FILE="${1:-shapes.sdf}"

echo "=================================================="
echo "🦅 YELPENÇE SÜRÜ SİMÜLASYONU BAŞLATILIYOR"
echo "🌍 Hedef Dünya: $WORLD_FILE"
echo "=================================================="

# 1. Gazebo Sunucusunu (Server) Arka Planda Başlat
echo "⚙️  Sunucu (Physics Engine) başlatılıyor..."
gz sim -s -v4 "$WORLD_FILE" &
SERVER_PID=$!

# Sunucunun kendine gelmesi için 3 saniye bekle
sleep 3

# 2. Grafik Arayüzü (GUI) Başlat
echo "🖥️  Grafik Arayüz (GUI) başlatılıyor..."
# X11 hatası almamak için önlem (OpenGL kullan)
export GZ_SIM_RENDER_ENGINE_BACKEND=ogre2
gz sim -g -v4

# 3. Temizlik (GUI kapanınca burası çalışır)
echo " "
echo "🛑 Simülasyon kapatılıyor..."
kill $SERVER_PID
echo "✅ Sunucu kapatıldı. İyi çalışmalar."
