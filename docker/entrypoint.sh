#!/bin/bash
# Konteyner her sıfırdan başlatıldığında veya varolan konteynerin içine girildiğinde çalışan betik.

set -e

# Kullanıcı sahiplik ayarı
if ! grep -q "$HOSTNAME" /etc/hosts; then
  sudo bash -c "echo '127.0.0.1 $HOSTNAME' >> /etc/hosts" 2>/dev/null || true
fi
sudo chown -R yelpence:yelpence \
  /home/yelpence/ros2_ws/build \
  /home/yelpence/ros2_ws/install \
  /home/yelpence/ros2_ws/src/PX4-Autopilot/build \
  /home/yelpence/ros2_ws/src/px4_autopilot/build 2>/dev/null || true
# NOT: kucuk harfli px4_autopilot AKTIF klasordur (launch bunu kullanir).
# Eskiden yalniz buyuk harfli chown'laniyordu -> anonim volume root kaliyor,
# 'make px4_sitl' Permission denied veriyordu (2026-07-16'da yakalandi).

# Parmak izlerinin saklanacağı gizli klasör
HASH_DIR="/home/yelpence/.config/yelpence_hashes"
mkdir -p "$HASH_DIR"
REQ_FILE="/home/yelpence/ros2_ws/src/requirements.txt"

# Python bağımlılık kontrolü; her açılışta requirements.txt dosyasını kontrol eder.
check_and_update_deps() {
  if [ -f "$REQ_FILE" ]; then
    current_hash=$(md5sum "$REQ_FILE" | awk '{ print $1 }')
    old_hash_file="$HASH_DIR/req.hash"

    if [ ! -f "$old_hash_file" ] || [ "$current_hash" != "$(cat "$old_hash_file")" ]; then
      echo -e "\n\e[33m[UYARI] DEĞİŞİKLİK SAPTANDI. BAĞIMLILIKLAR GÜNCELLENİYOR...\e[0m"
      # Sanal ortam aktif mi kontrol et ve yükle
      source /home/yelpence/venv/bin/activate
      pip install --no-cache-dir -r "$REQ_FILE"

      # Yeni hash'i kaydet
      echo "$current_hash" >"$old_hash_file"
      echo -e "\e[32m[TAMAM] BAĞIMLILIKLAR GÜNCEL.\e[0m\n"
    fi
  fi
}

# swarm_interfaces .msg/.srv değişince otomatik yeniden derler (yukarıdaki pip
# kontrolüyle AYNI desen). Yeni bir mesaj (ör. MissionTarget) çekildiğinde kimse
# elle 'colcon build' yapmayı unutmaz -> "MissionTarget bulunamadı" hatası olmaz.
check_and_build_interfaces() {
  IF_DIR="/home/yelpence/ros2_ws/src/swarm_interfaces"
  if [ -d "$IF_DIR" ]; then
    current_hash=$(cat "$IF_DIR"/msg/*.msg "$IF_DIR"/srv/*.srv "$IF_DIR/CMakeLists.txt" 2>/dev/null | md5sum | awk '{ print $1 }')
    old_hash_file="$HASH_DIR/interfaces.hash"

    if [ ! -f "$old_hash_file" ] || [ "$current_hash" != "$(cat "$old_hash_file")" ]; then
      echo -e "\n\e[33m[UYARI] swarm_interfaces DEĞİŞTİ. YENİDEN DERLENİYOR...\e[0m"
      # KURŞUN-GEÇİRMEZ: 'if ... then' içinde çalıştığı için derleme başarısız
      # olsa bile set -e tetiklenmez; container DURMAZ, sadece uyarı basar.
      if colcon build --packages-select swarm_interfaces; then
        echo "$current_hash" >"$old_hash_file"
        echo -e "\e[32m[TAMAM] swarm_interfaces GÜNCEL.\e[0m\n"
      else
        echo -e "\e[31m[UYARI] swarm_interfaces derlenemedi — elle: colcon build --packages-select swarm_interfaces\e[0m"
      fi
    fi
  fi
}

# --- Başlangıç İşlemleri ---
sudo service ssh start >/dev/null 2>&1

# 1. ROS 2 Jazzy Global Ortamını Yükle
source /opt/ros/jazzy/setup.bash

# 2. Python Sanal Ortamını Aktif Et
source /home/yelpence/venv/bin/activate

# 3. Bağımlılık kontrollerini çalıştır
check_and_update_deps

# 4. Çalışma Alanına Geçiş Yap
cd /home/yelpence/ros2_ws

# 5. PX4 Otonom Uçuş İzinlerinin (Parametrelerin) Ayarlanması
AIRFRAME_FILE="src/px4_autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/4001_gz_x500"
if [ -f "$AIRFRAME_FILE" ]; then
  # Dosyaya daha önce eklenip eklenmediğini kontrol et (Dosyanın şişmesini engellemek için)
  if ! grep -q "NAV_DLL_ACT 0" "$AIRFRAME_FILE"; then
    echo -e "\n# YELPENCE SURU IHA - Otonom Ucus Izinleri (SIMULASYON)" >>"$AIRFRAME_FILE"
    echo "param set-default NAV_DLL_ACT 0" >>"$AIRFRAME_FILE"
    echo "param set-default NAV_RCL_ACT 0" >>"$AIRFRAME_FILE"
    echo "param set-default COM_RCL_EXCEPT 4" >>"$AIRFRAME_FILE"
    echo -e "\e[32m--- Otonom uçuş parametreleri x500 modeline başarıyla eklendi! ---\e[0m"
  fi
fi

# 6. İlk Kurulum ve Derleme Kontrolü (Klasör adı düzeltildi)
if [ ! -f "install/setup.bash" ]; then
  if [ -d "src/px4_autopilot" ]; then

    # EKLENEN KISIM: Root tarafından kilitlenmiş build klasörünü zorla sahiplen
    sudo mkdir -p src/px4_autopilot/build
    sudo chown -R yelpence:yelpence src/px4_autopilot/build

    # PX4 yamalarını uygula (build'den ÖNCE, derlemeye girsin diye).
    # ornek: sim_rtk_fix6 (SITL GPS'ini RTK kalitesine ceker).
    # KURŞUN-GEÇİRMEZ: --check önce "uygulanabilir mi?" diye sorar; zaten uygulanmışsa
    # 'else'e düşüp SESSİZCE atlar. Tüm git komutları 'if' içinde -> hata fırlatsa bile
    # set -e tetiklenmez, container DURMAZ. En kötü ihtimalle "atlandı" yazar.
    for YAMA in "$(pwd)"/docker/patches/*.patch; do
      [ -f "$YAMA" ] || continue
      if git -C src/px4_autopilot apply --check "$YAMA" 2>/dev/null; then
        if git -C src/px4_autopilot apply "$YAMA" 2>/dev/null; then
          echo -e "\e[32m[PATCH] uygulandı: $(basename "$YAMA")\e[0m"
        else
          echo -e "\e[33m[PATCH] uygulanamadı, atlandı: $(basename "$YAMA")\e[0m"
        fi
      else
        echo -e "\e[90m[PATCH] zaten uygulanmış / gerekmiyor: $(basename "$YAMA")\e[0m"
      fi
    done

    # Sonrasında normal derlemeye devam et
    make -C src/px4_autopilot px4_sitl_default
  else
    echo -e "\e[31m[HATA] src/px4_autopilot klasörü bulunamadı! Submodülleri çektiğinizden emin olun.\e[0m"
  fi

  touch /home/yelpence/ros2_ws/src/px4_autopilot/COLCON_IGNORE
  colcon build --symlink-install
  echo -e "\e[32m--- İlk kurulum ve derleme başarıyla tamamlandı! ---\e[0m"
else
  echo "--- Mevcut derleme bulundu. Hazır sistem üzerinden başlatılıyor... ---"
  # Mevcut kurulumda: swarm_interfaces .msg/.srv değiştiyse otomatik yeniden derle.
  check_and_build_interfaces
fi

# 7. Yelpençe Çalışma Alanını Yükle
if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
  source "/home/yelpence/ros2_ws/install/setup.bash"
fi

echo -e "\n\e[32m--- Sistem Hazır. İyi uçuşlar! ---\e[0m\n"

# Komutu çalıştır
exec "$@"
