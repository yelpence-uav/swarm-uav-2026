#pragma once
#include "mbedtls/gcm.h"
#include <stdint.h>
#include <string.h>
#include <esp_random.h>
#include <Preferences.h>

// ===== AES-128 GCM — ANAHTAR NVS'DEN YÜKLENİR =====
// Anahtar kaynak kodda YOKTUR.
// Üretim:    python tools/nvs_key_gen.py
// Provision: KEY WRITER firmware'i (KEY WRITER/src/main.cpp) — uretilen hex
//            SAHA_ANAHTARI'na yapistirilir, karta flash'lanir, "PROVISION
//            TAMAMLANDI" gorununce ana firmware (TX DRONE / RX BASE) yuklenir.
//            KEY WRITER/src/main.cpp gitignore'da; anahtar repoya girmez.
//
// NVS namespace : "mesh_sec"
// NVS key       : "aes_key"
// Boyut         : 16 byte (AES-128)
//
// Boot davranışı:
//   NVS'de anahtar var  → yükle, kullan
//   NVS boş (provision yapılmamış) → HATA, Serial'e yaz, sonsuz döngü
//   Provision yapılmamış cihaz mesh'e katılamamalı.

static mbedtls_gcm_context _gcm_ctx;
static bool _gcm_hazir = false;
static uint8_t _aes_key[16] = {0};

static inline void aes_init() {
    if (_gcm_hazir) return;

    Preferences prefs;
    prefs.begin("mesh_sec", true);  // read-only
    size_t okunan = prefs.getBytes("aes_key", _aes_key, 16);
    prefs.end();

    if (okunan != 16) {
        // Provision yapılmamış — mesh'e katılma, dur
        Serial.println("[CRYPTO] KRITIK HATA: NVS'de AES anahtari bulunamadi!");
        Serial.println("[CRYPTO] Provision yapilmadan mesh'e katilinamaz.");
        Serial.println("[CRYPTO] Cozum: KEY WRITER firmware'ini bu karta flash'la");
        Serial.println("[CRYPTO] (anahtar: python tools/nvs_key_gen.py), 'PROVISION TAMAMLANDI'");
        Serial.println("[CRYPTO] gorununce bu firmwareyi tekrar yukle.");
        Serial.flush();
        while (true) {
            delay(1000);
            Serial.println("[CRYPTO] PROVISION BEKLENIYOR...");
        }
    }

    mbedtls_gcm_init(&_gcm_ctx);
    mbedtls_gcm_setkey(&_gcm_ctx, MBEDTLS_CIPHER_ID_AES, _aes_key, 128);
    _gcm_hazir = true;
    Serial.println("[CRYPTO] AES-128-GCM anahtari NVS'den yuklendi.");
}

// Nonce: 12 byte (GCM icin standart boyut — NIST SP 800-38D)
static inline void iv_uret_rastgele(uint8_t iv[12]) {
    uint32_t r0 = esp_random();
    uint32_t r1 = esp_random();
    uint32_t r2 = esp_random();
    memcpy(iv,     &r0, 4);
    memcpy(iv + 4, &r1, 4);
    memcpy(iv + 8, &r2, 4);
}

// Sifrele — GCM, plaintext → ciphertext + 16 byte auth tag
// ORTA-1 FIX: aad/aad_uzunluk eklendi. Paket basligi (tip+kaynak_mac+hedef_mac)
// AAD olarak verilirse, sifreli payload degismeden basligi degistirmek artik
// tag'i gecersiz kilar (mesh_config.h::mesh_gonder AAD'i hesaplayip geciyor).
inline void aes_sifrele_gcm(const uint8_t* girdi, size_t uzunluk, uint8_t* cikti,
                              const uint8_t iv[12], uint8_t tag[16],
                              const uint8_t* aad = nullptr, size_t aad_uzunluk = 0) {
    aes_init();
    mbedtls_gcm_crypt_and_tag(&_gcm_ctx, MBEDTLS_GCM_ENCRYPT,
        uzunluk, iv, 12, aad, aad_uzunluk, girdi, cikti, 16, tag);
}

// Coz + dogrula — false donerse tag uyusmadi: sahte veya bozuk paket, at
// ORTA-1 FIX: coz tarafi da ayni AAD'i vermeli (sifrelemede kullanilanla birebir
// ayni tip+kaynak_mac+hedef_mac), aksi halde dogrulama hep basarisiz olur.
inline bool aes_coz_gcm(const uint8_t* girdi, size_t uzunluk, uint8_t* cikti,
                          const uint8_t iv[12], const uint8_t tag[16],
                          const uint8_t* aad = nullptr, size_t aad_uzunluk = 0) {
    aes_init();
    int ret = mbedtls_gcm_auth_decrypt(&_gcm_ctx, uzunluk,
        iv, 12, aad, aad_uzunluk, tag, 16, girdi, cikti);
    return (ret == 0);
}
