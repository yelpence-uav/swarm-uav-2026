#pragma once
#include <stdint.h>
#include <string.h>
#include <Arduino.h>

// ===== RTK PAKET YAPISI =====
#define RTK_MAX_PAYLOAD  220

typedef struct {
    uint32_t paket_id;
    uint8_t  frag_index;
    uint8_t  frag_total;
    uint8_t  payload[RTK_MAX_PAYLOAD];
    uint16_t crc;
} rtk_paket_t;

// ===== DURUM SAYAÇLARI =====
static uint32_t rtk_alinan          = 0;
static uint32_t rtk_kayip           = 0;
static uint32_t rtk_uart_gonderilen = 0;

// ===== FRAGMENTASYON YENİDEN BİRLEŞTİRME =====
#define RTK_MAX_FRAGS            6
#define RTK_REASSEMBLY_BUF_SIZE  1200
#define RTK_FRAG_TIMEOUT_MS      2000UL

static struct {
    uint32_t paket_id;
    uint8_t  toplam;
    uint8_t  alinan_maske;
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
#ifdef HAS_PIXHAWK
    // COBS + CRC16-CCITT sarmalama
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    // tip(1) + iha_id(1) + payload(N) + crc16(2)
    uint16_t ham_uzunluk = 1 + 1 + uzunluk + 2;
    uint8_t ham[ham_uzunluk];
    ham[0] = TIP_RTK;
    ham[1] = 99; // BAZ_ID
    memcpy(ham + 2, veri, uzunluk);
    ham[ham_uzunluk - 2] = (uint8_t)(crc >> 8);
    ham[ham_uzunluk - 1] = (uint8_t)(crc & 0xFF);
    // COBS encode
    uint8_t cobs_buf[ham_uzunluk + 2];
    uint16_t cobs_len = 0;
    uint16_t code_idx = 0;
    uint8_t code = 1;
    cobs_buf[cobs_len++] = 0; // placeholder
    code_idx = 0;
    cobs_len = 1;
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
    cobs_buf[cobs_len++] = 0x00; // frame delimiter
    Serial1.write(cobs_buf, cobs_len);
    rtk_uart_gonderilen++;
    Serial.printf("[RTK] UART gonderildi: %u byte (toplam: %lu)\n",
                  uzunluk, rtk_uart_gonderilen);
#else
    Serial.printf("[RTK][LOG] UART olmadan %u byte iletilirdi\n", uzunluk);
#endif
}

static inline void _rtk_tamamsa_gonder(void) {
    uint8_t tam_maske = (uint8_t)((1u << _rtk_asm.toplam) - 1u);
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

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wstringop-overflow"
    memcpy(_rtk_asm.buf + offset, (const void*)p->payload, RTK_MAX_PAYLOAD);
#pragma GCC diagnostic pop
    _rtk_asm.parca_uzunluk[idx] = RTK_MAX_PAYLOAD;
    _rtk_asm.alinan_maske |= (1u << idx);
    _rtk_asm.son_parca_ms  = simdi;

    Serial.printf("[RTK] Frag %u/%u alindi (paket_id=%lu)\n",
                  idx + 1, _rtk_asm.toplam, (unsigned long)p->paket_id);

    _rtk_tamamsa_gonder();
}

static inline void rtk_loop(void) {
    if (_rtk_asm.toplam == 0) return;
    if ((millis() - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS) {
        Serial.printf("[RTK] Assembly timeout — paket_id=%lu maske=%02X/%02X\n",
                      (unsigned long)_rtk_asm.paket_id,
                      _rtk_asm.alinan_maske,
                      (uint8_t)((1u << _rtk_asm.toplam) - 1u));
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
