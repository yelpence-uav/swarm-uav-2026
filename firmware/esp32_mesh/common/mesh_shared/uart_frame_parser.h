#pragma once
// ===== ORTAK COBS ÇERÇEVE AYRIŞTIRICI — SAF (Arduino'dan bağımsız) =====
// RX BASE (Serial2/Pi) ve TX DRONE (Serial1/Pi) main.cpp loop()'larındaki
// "0x00'a kadar biriktir → cobs_decode → cobs_cerceve_coz → idx'i sıfırla"
// döngüsü BURAYA çıkarıldı. Amaç iki yönlü:
//
//  1) YAPISAL DESYNC GARANTİSİ: bir çerçeve reddedilse bile bu fonksiyon
//     çağrı başına EN FAZLA bir bayt işler ve 0x00 görünce idx'i HER ZAMAN
//     sıfırlar. Burada "break" / erken çıkış YOKTUR — dolayısıyla reddedilen
//     bir çerçeve bir sonraki çerçeveyi index'i kaydırarak bozamaz. (Bu, TX
//     DRONE main.cpp'de bulunan gerçek desync bug'ının — whitelist-dışı tip
//     gelince "break" tüm okuma döngüsünü kırıp idx=0'ı atlıyordu — sınıfını
//     tasarımla ortadan kaldırır. Whitelist/dispatch artık ÇERÇEVEYİ ALAN
//     tarafta, ayrıştırıcı durumundan tamamen kopuk yapılır.)
//
//  2) NATIVE'DE TEST EDİLEBİLİRLİK: Arduino.h/Serial/HardwareSerial'e
//     bağlı değildir (sadece <stdint.h>/<string.h> ve pure uart_cobs.h),
//     böylece `pio test -e native` altında (ASan/UBSan ile) doğrulanır.

#include <stdint.h>
#include <string.h>
#include "uart_cobs.h"

// Pi<->ESP komut protokolü çerçeveleri küçüktür (ham ≤ tip+id+18B payload+
// crc16 = 22B; COBS + terminatör ≤ ~27B). 32 hem eski main.cpp'lerdeki
// rx_buf[32]/rpi_rx_buf[32] boyutuyla birebir aynı, hem de yeterli marj.
#ifndef UART_FRAME_BUF_SIZE
#define UART_FRAME_BUF_SIZE 32
#endif

typedef struct {
    uint8_t raw[UART_FRAME_BUF_SIZE];      // 0x00'a kadar biriken ham COBS baytları
    // KURAL (bkz uart_cobs.h): cobs_decode çıkış tamponu >= giriş tamponu
    // olmalı. decoded ve raw aynı boyutta — cobs_decode çıktısı girişten
    // her zaman kısa olduğundan taşma imkânsız.
    uint8_t decoded[UART_FRAME_BUF_SIZE];  // çözülmüş çerçeve (payload buraya işaret eder)
    uint8_t idx;
} uart_frame_parser_t;

static inline void uart_frame_parser_sifirla(uart_frame_parser_t* st) {
    st->idx = 0;
}

// Bir bayt besle.
//   b != 0x00 : baytı tampona ekle (taşarsa çerçeveyi at, yeniden senkronize
//               ol) ve false dön.
//   b == 0x00 : çerçeve sonu. idx'i HER ZAMAN sıfırla, sonra en az 4 bayt
//               (tip+id+crc16) varsa cobs_decode + cobs_cerceve_coz uygula.
//               CRC geçerse true dön ve tip/id/payload çıkışlarını doldur
//               (payload st->decoded İÇİNE işaret eder — bir sonraki push
//               çerçeveyi tamamlayana kadar geçerlidir).
//
// Çağıran taraf whitelist/rate-limit/dispatch mantığını DÖNEN çerçeveye
// uygular; bu mantığın hiçbir dalı ayrıştırıcı durumunu etkileyemez.
static inline bool uart_frame_parser_push(
        uart_frame_parser_t* st, uint8_t b,
        uint8_t* tip_out, uint8_t* id_out,
        const uint8_t** payload_out, uint16_t* payload_uzunluk_out) {
    if (b != 0x00) {
        if (st->idx < UART_FRAME_BUF_SIZE) st->raw[st->idx++] = b;
        else st->idx = 0;   // taşma — çerçeveyi at, yeniden senkronize ol
        return false;
    }
    uint8_t n = st->idx;
    st->idx = 0;            // 0x00'da HER ZAMAN sıfırla (yapısal desync koruması)
    if (n < 4) return false;
    uint16_t dlen = cobs_decode(st->raw, (uint16_t)n, st->decoded);
    return cobs_cerceve_coz(st->decoded, dlen, tip_out, id_out,
                            payload_out, payload_uzunluk_out);
}
