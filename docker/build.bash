#!/bin/bash

# Hata oluşursa işlemi durdur
set -e

# ----------------------------------------------------------------
# YELPENÇE 2026 - AKILLI İNŞA SCRİPTİ
# Amaç: Takım üyelerinin farklı UID/GID değerlerine uyum sağlamak.
# ----------------------------------------------------------------

# 1. Mevcut bilgisayardaki kullanıcının ID'lerini tespit et
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

echo "=================================================="
echo " YELPENÇE SÜRÜ İHA TAKIMI - DOCKER KURULUMU"
echo "=================================================="
echo " Tespit Edilen Kullanıcı : $(whoami)"
echo " Kullanıcı ID (UID)      : $CURRENT_UID"
echo " Grup ID (GID)           : $CURRENT_GID"
echo "=================================================="
echo " İmaj inşası başlıyor..."

# 2. Docker Compose Build Komutunu Çalıştır
# --build-arg ile ID'leri Dockerfile'a gönderiyoruz.
docker compose build \
    --build-arg USER_UID=$CURRENT_UID \
    --build-arg USER_GID=$CURRENT_GID

echo " "
echo " KURULUM BAŞARIYLA TAMAMLANDI!"
echo " Sistemi başlatmak için şu komutu girin:"
echo " docker compose up -d"
echo "=================================================="
