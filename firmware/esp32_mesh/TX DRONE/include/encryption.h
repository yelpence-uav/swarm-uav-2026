#pragma once
#include "mbedtls/gcm.h"
#include <stdint.h>
#include <string.h>
#include <esp_random.h>

// ===== AES-128 GCM ANAHTARI =====
// ANAHTAR BURAYA YAZILMAZ — ortam degiskeninden veya NVS'den yuklenir
// Gecici placeholder: production oncesi degistirin
static const uint8_t AES_KEY[16] = {
    0xF5,0x5F,0x70,0x2C,
    0xBE,0xF9,0xFB,0x9D,
    0x9F,0x5A,0x91,0xC2,
    0xA4,0xFB,0x6C,0xE4
};

// GCM context — key expansion bir kez yapilir
// NOT: sadece loop() gorevinden cagriliyor, ISR-safe degil
static mbedtls_gcm_context _gcm_ctx;
static bool _gcm_hazir = false;

static inline void aes_init() {
    if (_gcm_hazir) return;
    mbedtls_gcm_init(&_gcm_ctx);
    mbedtls_gcm_setkey(&_gcm_ctx, MBEDTLS_CIPHER_ID_AES, AES_KEY, 128);
    _gcm_hazir = true;
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

// Sifrele — GCM, 16 byte plaintext → 16 byte ciphertext + 16 byte auth tag
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
