#pragma once
#include "mbedtls/gcm.h"
#include <stdint.h>
#include <string.h>
#include <esp_random.h>
#include <Preferences.h>

// ===== AES-128 GCM — ANAHTAR NVS'DEN YÜKLENİR =====
// Anahtar kaynak kodda YOKTUR.
// Provision: python tools/nvs_provision.py --port /dev/ttyUSBx --key <hex>
// Üretim:    python tools/nvs_key_gen.py
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
        Serial.println("[CRYPTO] Calistir: python tools/nvs_provision.py --port <PORT> --key <HEX>");
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
inline void aes_sifrele_gcm(const uint8_t* girdi, size_t uzunluk, uint8_t* cikti,
                              const uint8_t iv[12], uint8_t tag[16]) {
    aes_init();
    mbedtls_gcm_crypt_and_tag(&_gcm_ctx, MBEDTLS_GCM_ENCRYPT,
        uzunluk, iv, 12, NULL, 0, girdi, cikti, 16, tag);
}

// Coz + dogrula — false donerse tag uyusmadi: sahte veya bozuk paket, at
inline bool aes_coz_gcm(const uint8_t* girdi, size_t uzunluk, uint8_t* cikti,
                          const uint8_t iv[12], const uint8_t tag[16]) {
    aes_init();
    int ret = mbedtls_gcm_auth_decrypt(&_gcm_ctx, uzunluk,
        iv, 12, NULL, 0, tag, 16, girdi, cikti);
    return (ret == 0);
}
