#pragma once
#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, mesh_gonder

// ===== SABITLER =====
#define RTK_MAX_PAYLOAD          220    // TX DRONE alim tarafı (eski ESP-NOW fragment boyutu)
#define RTK_MAX_FRAGS            100    // 6'dan 100'e: 1000 byte / 12 byte = ~84 frag max
                                        // DIKKAT: alinan_maske uint32_t olmali (asagida)
#define RTK_REASSEMBLY_BUF_SIZE  1200
#define RTK_HAM_BUF_SIZE   (1 + 1 + RTK_REASSEMBLY_BUF_SIZE + 2)
#define RTK_COBS_BUF_SIZE  (RTK_HAM_BUF_SIZE + (RTK_HAM_BUF_SIZE / 254) + 2)
#define RTK_FRAG_TIMEOUT_MS      2000UL

#ifndef RTK_MESH_FRAG_DEFINED
#define RTK_MESH_FRAG_DEFINED
// ===== MESH FRAGMENT YAPISI (RX BASE gönderir, TX DRONE alır) =====
// Mesh payload limiti 18 byte — bu struct tam sığar.
typedef struct __attribute__((packed)) {
    uint32_t paket_id;      // 4 byte — hangi RTCM mesajına ait
    uint8_t  frag_index;    // 1 byte — bu parçanın sırası (0'dan başlar)
    uint8_t  frag_total;    // 1 byte — toplam parça sayısı
    uint8_t  payload[12];   // 12 byte — RTCM verisi
} rtk_mesh_frag_t;          // Toplam: 18 byte
#endif // RTK_MESH_FRAG_DEFINED

// ===== PAKET YAPISI (eski ESP-NOW tabanlı, geriye uyumluluk) =====
typedef struct __attribute__((packed)) {
    uint32_t paket_id;
    uint8_t  frag_index;
    uint8_t  frag_total;
    uint8_t  payload[RTK_MAX_PAYLOAD];
    uint16_t payload_uzunluk;
    uint16_t crc;
} rtk_paket_t;

// ===== DURUM SAYAÇLARI =====
static uint32_t rtk_alinan          = 0;
static uint32_t rtk_kayip           = 0;
static uint32_t rtk_uart_gonderilen = 0;

// ===== FRAGMENTASYON YENİDEN BİRLEŞTİRME =====
// alinan_maske: uint8_t → uint32_t
//   Eski uint8_t ile max 8 bit → max 8 fragment takip edilebilirdi.
//   RTK_MAX_FRAGS=100 ile uint32_t gerekli (32 bit → max 32 frag).
//   NOT: 32 bit maske ile 33+ fragment göndermek istenirse
//        maske yerine alinan_sayac karşılaştırması kullanılmalı.
//        Tipik RTCM: 250 byte / 12 byte ≈ 21 fragment — 32 bit yeter.
static struct {
    uint32_t paket_id;
    uint8_t  toplam;
    uint32_t alinan_maske;          // uint8_t → uint32_t (max 32 frag)
    uint8_t  buf[RTK_REASSEMBLY_BUF_SIZE];
    uint16_t parca_uzunluk[RTK_MAX_FRAGS];
    uint32_t son_parca_ms;
} _rtk_asm = {};

static uint16_t _rtk_crc16(const uint8_t* veri, uint16_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

static inline void _rtk_asm_sifirla(void) {
    memset(&_rtk_asm, 0, sizeof(_rtk_asm));
}

static inline void _rtk_uart_gonder(const uint8_t* veri, uint16_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    uint16_t ham_uzunluk = 1 + 1 + uzunluk + 2;
    static uint8_t ham[RTK_HAM_BUF_SIZE];
    ham[0] = TIP_RTK;
    ham[1] = 99; // BAZ_ID
    memcpy(ham + 2, veri, uzunluk);
    ham[ham_uzunluk - 2] = (uint8_t)(crc >> 8);
    ham[ham_uzunluk - 1] = (uint8_t)(crc & 0xFF);
    static uint8_t cobs_buf[RTK_COBS_BUF_SIZE];
    uint16_t cobs_len = 1;
    uint16_t code_idx = 0;
    uint8_t code = 1;
    for (uint16_t i = 0; i < ham_uzunluk; i++) {
        if (ham[i] == 0x00) {
            cobs_buf[code_idx] = code;
            code_idx = cobs_len++;
            cobs_buf[cobs_len - 1] = 0;
            code = 1;
        } else {
            cobs_buf[cobs_len++] = ham[i];
            code++;
            if (code == 0xFF) {
                cobs_buf[code_idx] = code;
                code_idx = cobs_len++;
                cobs_buf[cobs_len - 1] = 0;
                code = 1;
            }
        }
    }
    cobs_buf[code_idx] = code;
    cobs_buf[cobs_len++] = 0x00;
    Serial1.write(cobs_buf, cobs_len);
    rtk_uart_gonderilen++;
    Serial.printf("[RTK] RPiye gonderildi: %u byte (toplam: %lu)\n",
                  uzunluk, rtk_uart_gonderilen);
}

static inline void _rtk_tamamsa_gonder(void) {
    // uint32_t maske — toplam 32'den buyuk olamaz (yukarida not var)
    uint32_t tam_maske = (uint32_t)((1u << _rtk_asm.toplam) - 1u);
    if (_rtk_asm.alinan_maske != tam_maske) return;

    uint16_t toplam_uzunluk = 0;
    for (uint8_t i = 0; i < _rtk_asm.toplam; i++)
        toplam_uzunluk += _rtk_asm.parca_uzunluk[i];

    if (toplam_uzunluk > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: birlesik paket cok buyuk: %u byte\n", toplam_uzunluk);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    Serial.printf("[RTK] Birlestirildi: %u byte\n", toplam_uzunluk);
    _rtk_uart_gonder(_rtk_asm.buf, toplam_uzunluk);
    _rtk_asm_sifirla();
}

// ===== MESH'TEN GELEN RTK FRAGMENT İŞLE (TX DRONE) =====
// mesh_veri_al callback'inde TIP_RTK görülünce bu fonksiyona yönlendirilir.
// rtk_mesh_frag_t (18 byte) parse eder, reassembly buffer'a koyar,
// tamamlanınca _rtk_uart_gonder ile RPi'ye iletir.
static inline void rtk_mesh_frag_handle(const uint8_t* ham_veri, uint16_t uzunluk) {
    if (uzunluk < sizeof(rtk_mesh_frag_t)) {
        Serial.printf("[RTK] HATA: fragment cok kisa (%u byte, beklenen %u)\n",
                      uzunluk, (unsigned)sizeof(rtk_mesh_frag_t));
        rtk_kayip++;
        return;
    }

    const rtk_mesh_frag_t* f = (const rtk_mesh_frag_t*)ham_veri;

    // Gecersiz fragment parametreleri
    if (f->frag_total == 0 || f->frag_total > RTK_MAX_FRAGS ||
        f->frag_index >= f->frag_total) {
        Serial.printf("[RTK] HATA: gecersiz frag index=%u total=%u\n",
                      f->frag_index, f->frag_total);
        rtk_kayip++;
        return;
    }

    uint32_t simdi = millis();

    // Farkli paket_id ya da timeout → sifirla
    if (_rtk_asm.toplam > 0 &&
        (f->paket_id != _rtk_asm.paket_id ||
         (simdi - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS)) {
        Serial.printf("[RTK] TIMEOUT/ID DEGISIM — yeniden baslaniyor\n");
        rtk_kayip++;
        _rtk_asm_sifirla();
    }

    // Yeni paket baslar
    if (_rtk_asm.toplam == 0) {
        _rtk_asm.paket_id = f->paket_id;
        _rtk_asm.toplam   = f->frag_total;
    }

    uint8_t idx = f->frag_index;

    // Duplikat kontrol
    if (_rtk_asm.alinan_maske & (1u << idx)) {
        Serial.printf("[RTK] Duplikat frag %u, atlaniyor\n", idx);
        return;
    }

    // Buffer taşma kontrol
    // Her fragment 12 byte payload, offset = idx * 12
    uint16_t offset = (uint16_t)idx * 12;
    if (offset + 12 > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: buffer tasacak offset=%u\n", offset);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    memcpy(_rtk_asm.buf + offset, f->payload, 12);
    // Son fragment kısa olabilir — parca_uzunluk'u sonradan düzelt
    // (son fragment 12 byte dolmayabilir; tam uzunluk bilinmiyorsa 12 yaz)
    _rtk_asm.parca_uzunluk[idx] = 12;
    _rtk_asm.alinan_maske      |= (1u << idx);
    _rtk_asm.son_parca_ms       = simdi;

    rtk_alinan++;
    Serial.printf("[RTK] Mesh frag %u/%u alindi (paket_id=%lu)\n",
                  idx + 1, _rtk_asm.toplam, (unsigned long)f->paket_id);

    _rtk_tamamsa_gonder();
}

// ===== ESKİ ESP-NOW BAZLI PAKET İŞLEME (geriye uyumluluk) =====
static inline void rtk_paket_isle(const uint8_t* ham_veri, uint16_t uzunluk) {
    if (uzunluk < sizeof(rtk_paket_t)) {
        Serial.printf("[RTK] HATA: kisa paket (%u byte)\n", uzunluk);
        rtk_kayip++;
        return;
    }

    const rtk_paket_t* p = (const rtk_paket_t*)ham_veri;

    uint16_t hesap_crc = _rtk_crc16(ham_veri, uzunluk - sizeof(uint16_t));
    if (hesap_crc != p->crc) {
        Serial.printf("[RTK] CRC HATASI paket_id=%lu beklenen=%04X gelen=%04X\n",
                      (unsigned long)p->paket_id, hesap_crc, p->crc);
        rtk_kayip++;
        return;
    }

    rtk_alinan++;

    uint32_t simdi = millis();
    if (_rtk_asm.toplam > 0 &&
        (p->paket_id != _rtk_asm.paket_id ||
         (simdi - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS)) {
        Serial.printf("[RTK] TIMEOUT/ID DEGISIM — yeniden baslaniyor\n");
        rtk_kayip++;
        _rtk_asm_sifirla();
    }

    if (p->frag_total == 0 || p->frag_total > RTK_MAX_FRAGS ||
        p->frag_index >= p->frag_total) {
        Serial.printf("[RTK] HATA: gecersiz frag index=%u total=%u\n",
                      p->frag_index, p->frag_total);
        rtk_kayip++;
        return;
    }

    if (_rtk_asm.toplam == 0) {
        _rtk_asm.paket_id = p->paket_id;
        _rtk_asm.toplam   = p->frag_total;
    }

    uint8_t idx = p->frag_index;

    if (_rtk_asm.alinan_maske & (1u << idx)) {
        Serial.printf("[RTK] Duplikat frag %u, atlaniyor\n", idx);
        return;
    }

    uint16_t offset = (uint16_t)idx * RTK_MAX_PAYLOAD;
    if (offset + RTK_MAX_PAYLOAD > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: buffer tasacak offset=%u\n", offset);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    uint16_t gercek_uzunluk = (p->payload_uzunluk > 0 && p->payload_uzunluk <= RTK_MAX_PAYLOAD)
                             ? p->payload_uzunluk : RTK_MAX_PAYLOAD;
    memcpy(_rtk_asm.buf + offset, p->payload, gercek_uzunluk);
    _rtk_asm.parca_uzunluk[idx] = gercek_uzunluk;
    _rtk_asm.alinan_maske |= (1u << idx);
    _rtk_asm.son_parca_ms  = simdi;

    Serial.printf("[RTK] Frag %u/%u alindi (paket_id=%lu)\n",
                  idx + 1, _rtk_asm.toplam, (unsigned long)p->paket_id);

    _rtk_tamamsa_gonder();
}

// ===== TIMEOUT KONTROL — loop()'tan çağrılır =====
static inline void rtk_loop(void) {
    if (_rtk_asm.toplam == 0) return;
    if ((millis() - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS) {
        Serial.printf("[RTK] Assembly timeout — paket_id=%lu maske=%08lX/%08lX\n",
                      (unsigned long)_rtk_asm.paket_id,
                      (unsigned long)_rtk_asm.alinan_maske,
                      (unsigned long)((1u << _rtk_asm.toplam) - 1u));
        rtk_kayip++;
        _rtk_asm_sifirla();
    }
}

static inline void rtk_istatistik_yazdir(void) {
    Serial.printf("[RTK] alinan=%lu kayip=%lu uart_gonderilen=%lu\n",
                  (unsigned long)rtk_alinan,
                  (unsigned long)rtk_kayip,
                  (unsigned long)rtk_uart_gonderilen);
}
