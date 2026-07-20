#pragma once
// Ortak COBS cerceve ayristirici (saf, Arduino'dan bagimsiz).
// RX BASE (Serial2/Pi) ve TX DRONE (Serial1/Pi) main.cpp loop()'larindaki
// "0x00'a kadar biriktir -> cobs_decode -> cobs_cerceve_coz -> idx'i sifirla"
// dongusu buraya cikarildi. Iki amaci var:
//
//  1) Yapisal desync garantisi: bir cerceve reddedilse bile bu fonksiyon cagri
//     basina en fazla bir bayt isler ve 0x00 gorunce idx'i her zaman sifirlar.
//     Burada break / erken cikis yok, dolayisiyla reddedilen bir cerceve bir
//     sonrakini index'i kaydirarak bozamaz. (whitelist-disi tip gelince "break"
//     ile okuma dongusunu kirip idx=0'i atlayan gercek desync bug'inin sinifini
//     tasarimla ortadan kaldirir. Whitelist/dispatch artik cerceveyi alan
//     tarafta, ayristirici durumundan kopuk yapilir.)
//
//  2) Native'de test edilebilirlik: Arduino.h/Serial/HardwareSerial'e bagli
//     degil (sadece <stdint.h>/<string.h> ve uart_cobs.h), boylece
//     `pio test -e native` altinda dogrulanir.

#include <stdint.h>
#include <string.h>
#include "uart_cobs.h"

// Pi<->ESP komut protokolu cerceveleri kucuktur (ham <= tip+id+18B payload+
// crc16 = 22B; COBS + terminator <= ~27B). 32, eski main.cpp'lerdeki
// rx_buf[32]/rpi_rx_buf[32] boyutuyla ayni ve yeterli marj birakiyor.
#ifndef UART_FRAME_BUF_SIZE
#define UART_FRAME_BUF_SIZE 32
#endif

typedef struct {
    uint8_t raw[UART_FRAME_BUF_SIZE];      // 0x00'a kadar biriken ham COBS baytlari
    // Kural (bkz uart_cobs.h): cobs_decode cikis tamponu >= giris tamponu olmali.
    // decoded ve raw ayni boyutta; cobs_decode ciktisi giristen her zaman kisa
    // oldugundan tasma imkansiz.
    uint8_t decoded[UART_FRAME_BUF_SIZE];  // cozulmus cerceve (payload buraya isaret eder)
    uint8_t idx;
} uart_frame_parser_t;

static inline void uart_frame_parser_sifirla(uart_frame_parser_t* st) {
    st->idx = 0;
}

// Bir bayt besle.
//   b != 0x00 : bayti tampona ekle (tasarsa cerceveyi at, yeniden senkronize
//               ol) ve false don.
//   b == 0x00 : cerceve sonu. idx'i her zaman sifirla, sonra en az 4 bayt
//               (tip+id+crc16) varsa cobs_decode + cobs_cerceve_coz uygula.
//               CRC gecerse true don ve tip/id/payload cikislarini doldur
//               (payload st->decoded icine isaret eder, bir sonraki push
//               cerceveyi tamamlayana kadar gecerlidir).
//
// Cagiran taraf whitelist/rate-limit/dispatch mantigini donen cerceveye uygular;
// bu mantigin hicbir dali ayristirici durumunu etkileyemez.
static inline bool uart_frame_parser_push(
        uart_frame_parser_t* st, uint8_t b,
        uint8_t* tip_out, uint8_t* id_out,
        const uint8_t** payload_out, uint16_t* payload_uzunluk_out) {
    if (b != 0x00) {
        if (st->idx < UART_FRAME_BUF_SIZE) st->raw[st->idx++] = b;
        else st->idx = 0;   // tasma: cerceveyi at, yeniden senkronize ol
        return false;
    }
    uint8_t n = st->idx;
    st->idx = 0;            // 0x00'da her zaman sifirla (yapisal desync korumasi)
    if (n < 4) return false;
    uint16_t dlen = cobs_decode(st->raw, (uint16_t)n, st->decoded);
    return cobs_cerceve_coz(st->decoded, dlen, tip_out, id_out,
                            payload_out, payload_uzunluk_out);
}
