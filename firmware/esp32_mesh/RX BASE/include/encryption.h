#pragma once
#include "mbedtls/aes.h"
#include <stdint.h>
#include <string.h>

// ===== AES-128 CBC ANAHTARI =====
static const uint8_t AES_KEY[16] = {
    0xF5,0x5F,0x70,0x2C,
    0xBE,0xF9,0xFB,0x9D,
    0x9F,0x5A,0x91,0xC2,
    0xA4,0xFB,0x6C,0xE4
};

// IV: paket_id'den türetilir — ECB'nin örüntü zayıflığını giderir
// paket_id her pakette farklı olduğu için her şifreli blok farklı çıkar
static inline void _iv_uret(uint8_t iv[16], uint32_t paket_id) {
    memset(iv, 0, 16);
    iv[0] = (paket_id >> 24) & 0xFF;
    iv[1] = (paket_id >> 16) & 0xFF;
    iv[2] = (paket_id >>  8) & 0xFF;
    iv[3] = (paket_id      ) & 0xFF;
    // Kalan 12 byte sabit tuz — çarpışma riskini azaltır
    iv[4]  = 0xA5; iv[5]  = 0x3C; iv[6]  = 0x7F; iv[7]  = 0x11;
    iv[8]  = 0xDE; iv[9]  = 0xAD; iv[10] = 0xBE; iv[11] = 0xEF;
    iv[12] = 0x01; iv[13] = 0x23; iv[14] = 0x45; iv[15] = 0x67;
}

// Şifrele — CBC modu, IV paket_id'den türetilir
inline void aes_sifrele_iv(const uint8_t* girdi, uint8_t* cikti, uint32_t paket_id) {
    uint8_t iv[16];
    _iv_uret(iv, paket_id);
    mbedtls_aes_context ctx;
    mbedtls_aes_init(&ctx);
    mbedtls_aes_setkey_enc(&ctx, AES_KEY, 128);
    mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_ENCRYPT, 16, iv, girdi, cikti);
    mbedtls_aes_free(&ctx);
}

// Çöz — CBC modu, aynı IV ile
inline void aes_coz_iv(const uint8_t* girdi, uint8_t* cikti, uint32_t paket_id) {
    uint8_t iv[16];
    _iv_uret(iv, paket_id);
    mbedtls_aes_context ctx;
    mbedtls_aes_init(&ctx);
    mbedtls_aes_setkey_dec(&ctx, AES_KEY, 128);
    mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_DECRYPT, 16, iv, girdi, cikti);
    mbedtls_aes_free(&ctx);
}

// Geriye dönük uyumluluk — paket_id=0 ile ECB benzeri davranış (geçiş için)
inline void aes_sifrele(const uint8_t* girdi, uint8_t* cikti) {
    aes_sifrele_iv(girdi, cikti, 0);
}
inline void aes_coz(const uint8_t* girdi, uint8_t* cikti) {
    aes_coz_iv(girdi, cikti, 0);
}
