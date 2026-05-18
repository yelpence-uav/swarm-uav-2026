#pragma once
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

#ifdef HAS_PIXHAWK

inline void px4_mod_gonder(HardwareSerial &seri, uint8_t sub_mode) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];
    mavlink_msg_command_long_pack(
        255, 190, &msg,
        1, 1,
        176,
        0,
        1,
        PX4_CUSTOM_MAIN_MODE_AUTO,
        (float)sub_mode,
        0, 0, 0, 0
    );
    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    seri.write(buf, len);
    Serial.printf("[FAILSAFE] PX4 mod: sub_mode=%u (%s)\n",
        sub_mode,
        sub_mode == PX4_CUSTOM_SUB_MODE_AUTO_RTL ? "RTL" : "LAND");
}

inline void failsafe_kontrol(HardwareSerial &pixhawk_seri) {
    unsigned long gecen = millis() - son_paket_ms;

    if (ardisik_kayip_sayisi >= ARDISIK_KAYIP_ESIGI && _failsafe_asama < 2) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.printf("[FAILSAFE] Ardisik kayip (%u), RTL\n", ardisik_kayip_sayisi);
        px4_mod_gonder(pixhawk_seri, PX4_CUSTOM_SUB_MODE_AUTO_RTL);
        return;
    }
    if (gecen >= FAILSAFE_WARN_MS && _failsafe_asama == 0) {
        _failsafe_asama = 1;
        Serial.println("[FAILSAFE] UYARI: Baglanti zayif");
    }
    if (gecen >= FAILSAFE_SOFT_MS && _failsafe_asama == 1) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.printf("[FAILSAFE] SOFT (%lums): RTL\n", gecen);
        px4_mod_gonder(pixhawk_seri, PX4_CUSTOM_SUB_MODE_AUTO_RTL);
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
    if (ardisik_kayip_sayisi >= ARDISIK_KAYIP_ESIGI && _failsafe_asama < 2) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.printf("[FAILSAFE][LOG] Ardisik kayip (%u), RTL olurdu\n", ardisik_kayip_sayisi);
        return;
    }
    if (gecen >= FAILSAFE_WARN_MS && _failsafe_asama == 0) {
        _failsafe_asama = 1;
        Serial.println("[FAILSAFE][LOG] UYARI");
    }
    if (gecen >= FAILSAFE_SOFT_MS && _failsafe_asama == 1) {
        _failsafe_asama     = 2;
        failsafe_tetiklendi = true;
        Serial.println("[FAILSAFE][LOG] SOFT: RTL olurdu");
    }
    if (gecen >= FAILSAFE_HARD_MS && _failsafe_asama == 2) {
        _failsafe_asama = 3;
        Serial.println("[FAILSAFE][LOG] HARD: LAND olurdu");
    }
}

#endif

inline void failsafe_reset() {
    if (_failsafe_asama > 0) {
        Serial.printf("[FAILSAFE] Sifirlandi (asama %u)\n", _failsafe_asama);
        _failsafe_asama      = 0;
        failsafe_tetiklendi  = false;
        ardisik_kayip_sayisi = 0;
    }
    son_paket_ms = millis();
}
