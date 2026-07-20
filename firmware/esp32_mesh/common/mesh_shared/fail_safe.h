#pragma once
#include <Arduino.h>
#include "freertos/FreeRTOS.h"
extern portMUX_TYPE _recv_mux;

// Failsafe zaman esikleri.
#define FAILSAFE_WARN_MS      3000UL
#define FAILSAFE_SOFT_MS      8000UL
#define FAILSAFE_HARD_MS     15000UL
#define ARDISIK_KAYIP_ESIGI    80

// Failsafe tip kodlari: RPi bu kodu alip Pixhawk'a iletir
#define FAILSAFE_TIP_UYARI   0x01
#define FAILSAFE_TIP_RTL     0x02
#define FAILSAFE_TIP_LAND    0x03

#define APM_MODE_RTL   0x05
#define APM_MODE_LAND  0x06

extern uint8_t            failsafe_active_mode;
extern volatile unsigned long son_paket_ms;
extern bool               failsafe_tetiklendi;
extern volatile uint8_t   ardisik_kayip_sayisi;
extern uint8_t            _failsafe_asama;

// Failsafe bildirimini RPi'ye gonder (COBS+CRC16 sarmali).
// Diger tum mesajlarla ayni format: [TIP][IHA_ID][FAILSAFE_TIP] + CRC16, COBS
// sarmali. (Eskiden 3 raw byte gonderiliyordu, bridge onu drop ediyordu.)
//
// Frame yapisi (decode sonrasi):
//   [0] = 0xFA          failsafe tip markeri
//   [1] = 0x00          iha_id (broadcast)
//   [2] = failsafe_tip  FAILSAFE_TIP_UYARI / RTL / LAND
//   [3..4] = CRC16-CCITT (big-endian)
// COBS encode + 0x00 terminator ile verilen uart'a yazilir. uart parametreli:
// TX DRONE'da Serial1 tek Pi hatti, RX BASE'de Serial1 sadece RTCM girisine
// ayrilmis (Pi protokolu Serial2'de), o yuzden port sabitlenmez, cagiran belirler.
static inline void _failsafe_rpi_bildir(uint8_t failsafe_tip, HardwareSerial& uart) {
    // --- Ham frame ---
    uint8_t ham[5];
    ham[0] = 0xFA;           // marker (tip)
    ham[1] = 0x00;           // iha_id broadcast
    ham[2] = failsafe_tip;

    // CRC16-CCITT ilk 3 byte uzerinden
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < 3; i++) {
        crc ^= (uint16_t)ham[i] << 8;
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    ham[3] = (uint8_t)(crc >> 8);
    ham[4] = (uint8_t)(crc & 0xFF);

    // --- COBS encode (5 byte ham -> max 7 byte COBS + 1 terminator) ---
    uint8_t cobs_buf[8];
    uint8_t kod_idx = 0;
    uint8_t yaz_idx = 1;
    uint8_t kod     = 1;
    for (uint8_t i = 0; i < 5; i++) {
        if (ham[i] != 0x00) {
            cobs_buf[yaz_idx++] = ham[i];
            kod++;
        } else {
            cobs_buf[kod_idx] = kod;
            kod_idx = yaz_idx;
            cobs_buf[yaz_idx++] = 0x01;
            kod = 1;
        }
    }
    cobs_buf[kod_idx]   = kod;
    cobs_buf[yaz_idx++] = 0x00;  // COBS frame terminator

    uart.write(cobs_buf, yaz_idx);
    Serial.printf("[FAILSAFE] RPiye bildirildi (COBS+CRC): tip=0x%02X\n", failsafe_tip);
}

// Failsafe kontrol.
// uart: bildirimin yazilacagi Pi hatti. TX DRONE'da varsayilan Serial1 (tek Pi
// hatti) yeterli; RX BASE bunu acikca Serial2 ile cagirmali (Serial1 orada
// RTCM'e ayrilmis, Pi orada dinlemiyor).
inline void failsafe_kontrol(HardwareSerial& uart = Serial1) {
    unsigned long gecen = millis() - son_paket_ms;

    if (ardisik_kayip_sayisi >= ARDISIK_KAYIP_ESIGI && _failsafe_asama < 2) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.printf("[FAILSAFE] Ardisik kayip (%u): RPiye RTL bildiriliyor\n",
                      ardisik_kayip_sayisi);
        _failsafe_rpi_bildir(FAILSAFE_TIP_RTL, uart);
        return;
    }
    if (gecen >= FAILSAFE_WARN_MS && _failsafe_asama == 0) {
        _failsafe_asama = 1;
        Serial.println("[FAILSAFE] UYARI: Baglanti zayif");
        _failsafe_rpi_bildir(FAILSAFE_TIP_UYARI, uart);
    }
    if (gecen >= FAILSAFE_SOFT_MS && _failsafe_asama == 1) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.printf("[FAILSAFE] SOFT (%lums): RPiye RTL bildiriliyor\n", gecen);
        _failsafe_rpi_bildir(FAILSAFE_TIP_RTL, uart);
    }
    if (gecen >= FAILSAFE_HARD_MS && _failsafe_asama == 2) {
        _failsafe_asama = 3;
        Serial.println("[FAILSAFE] HARD 15s: RPiye LAND bildiriliyor");
        _failsafe_rpi_bildir(FAILSAFE_TIP_LAND, uart);
    }
}

// Failsafe reset.
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
