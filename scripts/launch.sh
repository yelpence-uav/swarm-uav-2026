#!/bin/bash
# EYÜP'ÜN İZOLE SÜRÜ BAŞLATICISI (Tam Korumalı)

NUM_DRONES=${1:-1}

echo "==================================================="
echo "$NUM_DRONES İHA İçin Temiz Kurulum Başlıyor..."
echo "==================================================="

# 1. GÜVENLİK KANCASI: CTRL+C basılırsa zombileri otomatik öldür ve çık!
trap "echo -e '\nSimülasyon kapatılıyor...'; pkill -9 -x px4; exit" SIGINT SIGTERM

echo "Eski süreçler ve hafızalar temizleniyor..."
pkill -9 -x px4
rm -rf ~/ros2_ws/src/PX4-Autopilot/build/px4_sitl_default/instance_*
sleep 2

cd ~/ros2_ws/src/PX4-Autopilot

# 2. DRONLARI SESSİZ MODDA (-d) BAŞLAT
for ((i=1; i<=NUM_DRONES; i++))
do
    echo "[$i/$NUM_DRONES] Drone $i hazırlanıyor (Loglar: drone_$i.log)..."
    
    if [ $i -eq 1 ]; then POSE="0,0";
    elif [ $i -eq 2 ]; then POSE="0,2";
    elif [ $i -eq 3 ]; then POSE="0,-2";
    elif [ $i -eq 4 ]; then POSE="0,4";
    elif [ $i -eq 5 ]; then POSE="0,-4";
    fi

    # KRİTİK DEĞİŞİKLİK: -d parametresi eklendi! Artık log dosyasında pxh> çıldırması olmayacak.
    if [ $i -eq 1 ]; then
        PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i $i -d > ../../drone_$i.log 2>&1 &
    else
        PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL_POSE=$POSE PX4_SIM_MODEL=gz_x500 ./build/px4_sitl_default/bin/px4 -i $i -d > ../../drone_$i.log 2>&1 &
    fi
    
    sleep 4 
done

echo "==================================================="
echo "Görev Tamam! Dronlar sahada. Kapatmak için CTRL+C yapın."
echo "==================================================="
wait