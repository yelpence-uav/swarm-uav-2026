#pragma once
extern uint8_t mac_to_id(const uint8_t* mac);
#include <Arduino.h>
#include "freertos/FreeRTOS.h"
extern portMUX_TYPE _recv_mux;
#include <common/mavlink.h>

#define FAILSAFE_WARN_MS    3000UL
#define FAILSAFE_SOFT_MS    8000UL
#define FAILSAFE_HARD_MS   15000UL
#define ARDISIK_KAYIP_ESIGI  80

#define PX4_CUSTOM_MAIN_MODE_AUTO       4
#define PX4_CUSTOM_SUB_MODE_AUTO_RTL    5
#define PX4_CUSTOM_SUB_MODE_AUTO_LAND   6

// Geriye donuk uyumluluk icin alias
#define APM_MODE_RTL   PX4_CUSTOM_SUB_MODE_AUTO_RTL
#define APM_MODE_LAND  PX4_CUSTOM_SUB_MODE_AUTO_LAND

extern uint8_t            failsafe_active_mode;
extern volatile unsigned long son_paket_ms;
extern bool               failsafe_tetiklendi;
extern volatile uint8_t   ardisik_kayip_sayisi;
extern uint8_t            _failsafe_asama;

// Manevra sirasinda failsafe RTL geciktirilir
volatile bool             manevra_aktif     = false;
volatile uint32_t         manevra_bitis_ms  = 0;
#define MANEVRA_FAILSAFE_GECIKME_MS  3000UL  // Manevra bittikten 3sn sonra RTL

#ifdef HAS_PIXHAWK

static inline void _failsafe_cobs_gonder(uint8_t sub_mode) {
    uint8_t ham[18] = {0};
    ham[0] = 0xFE;
    ham[1] = 0x00;
    ham[2] = sub_mode;
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < 16; i++) {
        crc ^= (uint16_t)ham[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    ham[16] = (crc >> 8) & 0xFF;
    ham[17] =  crc & 0xFF;
    uint8_t cobs[22] = {0};
    uint8_t kod_idx = 0, yaz_idx = 1, kod = 1;
    for (uint8_t i = 0; i < 18; i++) {
        if (ham[i] != 0x00) { cobs[yaz_idx++] = ham[i]; kod++;
            if (kod == 0xFF) { cobs[kod_idx] = kod; kod_idx = yaz_idx; cobs[yaz_idx++] = 0x01; kod = 1; }
        } else { cobs[kod_idx] = kod; kod_idx = yaz_idx; cobs[yaz_idx++] = 0x01; kod = 1; }
    }
    cobs[kod_idx] = kod;
    cobs[yaz_idx++] = 0x00;
    Serial1.write(cobs, yaz_idx);
    Serial.printf("[FAILSAFE] RPi Serial1: sub_mode=%u (%s)\n",
        sub_mode,
        sub_mode == PX4_CUSTOM_SUB_MODE_AUTO_RTL ? "RTL" : "LAND");
}

inline void px4_mod_gonder(HardwareSerial &seri, uint8_t sub_mode) {
    (void)seri;
    _failsafe_cobs_gonder(sub_mode);
}

inline void failsafe_kontrol(HardwareSerial &pixhawk_seri) {
    unsigned long gecen = millis() - son_paket_ms;

    // Manevra aktifse RTL'yi geciktir
    bool manevra_bekleniyor = manevra_aktif ||
        (manevra_bitis_ms > 0 && (millis() - manevra_bitis_ms) < MANEVRA_FAILSAFE_GECIKME_MS);

    if (ardisik_kayip_sayisi >= ARDISIK_KAYIP_ESIGI && _failsafe_asama < 2) {
        _failsafe_asama = 1;
        Serial.printf("[FAILSAFE] Ardisik kayip (%u), UYARI\n", ardisik_kayip_sayisi);
        if (!manevra_bekleniyor) {
            _failsafe_asama     = 2;
            failsafe_tetiklendi = true;
            Serial.println("[FAILSAFE] Ardisik kayip: RTL");
            px4_mod_gonder(pixhawk_seri, PX4_CUSTOM_SUB_MODE_AUTO_RTL);
        } else {
            Serial.println("[FAILSAFE] Ardisik kayip: Manevra aktif, RTL bekleniyor");
        }
        return;
    }
    if (gecen >= FAILSAFE_WARN_MS && _failsafe_asama == 0) {
        _failsafe_asama = 1;
        Serial.println("[FAILSAFE] UYARI: Baglanti zayif");
    }
    if (gecen >= FAILSAFE_SOFT_MS && _failsafe_asama == 1) {
        if (!manevra_bekleniyor) {
            _failsafe_asama     = 2;
            failsafe_tetiklendi = true;
            Serial.printf("[FAILSAFE] SOFT (%lums): RTL\n", gecen);
            px4_mod_gonder(pixhawk_seri, PX4_CUSTOM_SUB_MODE_AUTO_RTL);
        } else {
            Serial.printf("[FAILSAFE] SOFT (%lums): Manevra aktif, RTL bekleniyor\n", gecen);
        }
    }
    if (gecen >= FAILSAFE_HARD_MS && _failsafe_asama == 2) {
        _failsafe_asama = 3;
        Serial.println("[FAILSAFE] HARD 15s: LAND");
        px4_mod_gonder(pixhawk_seri, PX4_CUSTOM_SUB_MODE_AUTO_LAND);
    }
}

#endif

#ifndef HAS_PIXHAWK

inline void failsafe_kontrol_log() {
    unsigned long gecen = millis() - son_paket_ms;
    bool manevra_bekleniyor = manevra_aktif ||
        (manevra_bitis_ms > 0 && (millis() - manevra_bitis_ms) < MANEVRA_FAILSAFE_GECIKME_MS);
    if (ardisik_kayip_sayisi >= ARDISIK_KAYIP_ESIGI && _failsafe_asama < 2) {
        _failsafe_asama = 1;
        Serial.printf("[FAILSAFE][LOG] Ardisik kayip (%u), UYARI\n", ardisik_kayip_sayisi);
        if (!manevra_bekleniyor) {
            _failsafe_asama     = 2;
            failsafe_tetiklendi = true;
            Serial.println("[FAILSAFE][LOG] Ardisik kayip: RTL olurdu");
        } else {
            Serial.println("[FAILSAFE][LOG] Ardisik kayip: Manevra aktif, RTL bekleniyor");
        }
        return;
    }
    if (gecen >= FAILSAFE_WARN_MS && _failsafe_asama == 0) {
        _failsafe_asama = 1;
        Serial.println("[FAILSAFE][LOG] UYARI");
    }
    if (gecen >= FAILSAFE_SOFT_MS && _failsafe_asama == 1) {
        if (!manevra_bekleniyor) {
            _failsafe_asama     = 2;
            failsafe_tetiklendi = true;
            Serial.printf("[FAILSAFE][LOG] SOFT (%lums): RTL olurdu\n", gecen);
        } else {
            Serial.printf("[FAILSAFE][LOG] SOFT (%lums): Manevra aktif, RTL bekleniyor\n", gecen);
        }
    }
    if (gecen >= FAILSAFE_HARD_MS && _failsafe_asama == 2) {
        _failsafe_asama = 3;
        Serial.println("[FAILSAFE][LOG] HARD: LAND olurdu");
    }
}

#endif

// FIX #5: ardisik_kayip_sayisi critical section icinde sifirlanıyor
inline void failsafe_reset() {
    if (_failsafe_asama > 0) {
        Serial.printf("[FAILSAFE] Sifirlandi (asama %u)\n", _failsafe_asama);
        _failsafe_asama     = 0;
        failsafe_tetiklendi = false;
        portENTER_CRITICAL(&_recv_mux);
        ardisik_kayip_sayisi = 0;
        son_paket_ms = millis();
        portEXIT_CRITICAL(&_recv_mux);
    }
}
