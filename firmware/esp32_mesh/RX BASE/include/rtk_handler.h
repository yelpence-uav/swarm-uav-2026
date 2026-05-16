#pragma once
#include <stdint.h>

// ===== RTK PAKET YAPISI =====
#define RTK_MAX_PAYLOAD  220  // ESP-NOW max 250 byte, header için pay bırak

typedef struct {
    uint32_t paket_id;
    uint8_t  frag_index;   // parça sırası
    uint8_t  frag_total;   // toplam parça sayısı
    uint8_t  payload[RTK_MAX_PAYLOAD];
    uint16_t crc;
} rtk_paket_t;

// ===== DURUM =====
static uint32_t rtk_alinan   = 0;
static uint32_t rtk_kayip    = 0;

// RTK verisini işle — şimdilik iskelet
inline void handleRTKData(const uint8_t* veri, uint16_t len) {
    // TODO: RTCM3 parse et
    // TODO: Uçuş kontrolcüsüne ilet (UART)
    rtk_alinan++;
    Serial.printf("[RTK] Veri alindi: %d byte\n", len);
}