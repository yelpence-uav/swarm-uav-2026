#!/bin/bash

# Konteyneri ilk defa başlatmak için kullanılan betik.

CONTAINER_NAME="yelpence_swarm_container"
CONTAINER_NAME_AMD="yelpence_swarm_container_amd"

# Konteyner hali hazırda çalışıyorsa uyarı verir.
if [ "$(docker ps -q -f name=^/${CONTAINER_NAME}$ -f status=running)" ]; then
    echo -e "\e[31m[HATA] KONTEYNER ZATEN ÇALIŞIYOR!\e[0m"
    echo -e "İçeri girmek için: \e[32myelpence_gir\e[0m"
    exit 1
elif [ "$(docker ps -q -f name=^/${CONTAINER_NAME_AMD}$ -f status=running)" ]; then
    echo -e "\e[31m[HATA] AMD KONTEYNERİ ZATEN ÇALIŞIYOR!\e[0m"
    echo -e "İçeri girmek için: \e[32myelpence_gir_amd\e[0m"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

# GUI izinlerini ver
xhost +local:root >/dev/null 2>&1

echo -e "\033[0;36m[BİLGİ] YELPENÇE SÜRÜ İHA SİSTEMİ BAŞLATILIYOR...\033[0m"
sleep 1

# Ekran kartı tipine göre compose eder.
while true; do
    echo -e "Ekran kartı tipinizi seçin:"
    echo -e "---------------------------"
    echo -e "1) NVIDIA"
    echo -e "2) AMD / INTEL"
    echo -e "---------------------------"
    read -p "Seçiminiz [1-2]: " SECIM

    case $SECIM in
    1)
        echo -e "\033[0;36m[BİLGİ] NVIDIA YAPILANDIRMASIYLA BAŞLATILIYOR...\033[0m"
        sleep 1
        docker compose -f "$PROJE_KOK/docker/docker-compose.yml" up -d
        TARGET_NAME=$CONTAINER_NAME
        break
        ;;
    2)
        echo -e "\033[0;36m[BİLGİ] AMD/INTEL YAPILANDIRMASIYLA BAŞLATILIYOR...\033[0m"
        sleep 1
        docker compose -f "$PROJE_KOK/docker/docker-compose-amd.yml" up -d
        TARGET_NAME=$CONTAINER_NAME_AMD
        break
        ;;
    *)
        echo -e "\e[31m[HATA] GEÇERSİZ SEÇİM!\e[0m"
        ;;
    esac
done

echo -e "\e[32m[TAMAM] KONTEYNER ARKA PLANDA BAŞLATILDI.\e[0m"
