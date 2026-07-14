#pragma once
// ADIM 6: Arduino.h'ye ihtiyaci yok (Serial/millis/HardwareSerial hic
// kullanilmiyor) — <stdint.h> yeterli, boylece PlatformIO native ortaminda
// da (donanimsiz unit test) derlenebiliyor.
#include <stdint.h>
#include <string.h>

// ===== ORTAK UART COBS KATMANI (REV B karar #3) =====
// RX BASE (YKİ hattı) ve TX DRONE (Pi hattı) AYNI çerçeve formatını kullanır:
//
//   frame_on_wire = COBS_encode( TIP + ID + payload + crc16_be(TIP+ID+payload) ) + 0x00
//
// CRC16 = CCITT-FALSE (poly 0x1021, init 0xFFFF, refin/refout false),
// test vektörü crc16("123456789")==0x29B1 (ESP tarafinda dogrulandi).
// CRC, TIP+ID dahil COBS icindeki HER SEYI kapsar (CRC'nin kendisi haric)
// ve BUYUK-ENDIAN (MSB once) yazilir — REV B karari, eski genel
// uart_gonder() zaten bu sekilde davraniyordu, RTK tarafi buna uydurulacak.

// ===== CRC16-CCITT-FALSE =====
static inline uint16_t cobs_crc16(const uint8_t* veri, uint16_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

// ===== COBS ENCODE/DECODE =====
// (RX BASE/TX DRONE main.cpp'lerindeki eski birebir ayni fonksiyonlar,
// tek yere tasindi; uzunluk tipi uint16_t'ye genisletildi cunku RTK
// tarafinda cerceve 1600B'a kadar cikabiliyor.)
static inline uint16_t cobs_encode(const uint8_t* giris, uint16_t uzunluk, uint8_t* cikis) {
    uint16_t kod_idx = 0, yaz_idx = 1;
    uint8_t kod = 1;
    for (uint16_t i = 0; i < uzunluk; i++) {
        if (giris[i] != 0x00) {
            cikis[yaz_idx++] = giris[i];
            if (++kod == 0xFF) {
                cikis[kod_idx] = kod; kod_idx = yaz_idx;
                cikis[yaz_idx++] = 0x01; kod = 1;
            }
        } else {
            cikis[kod_idx] = kod; kod_idx = yaz_idx;
            cikis[yaz_idx++] = 0x01; kod = 1;
        }
    }
    cikis[kod_idx] = kod;
    cikis[yaz_idx++] = 0x00;
    return yaz_idx;
}

// KURAL: cikis tamponu >= girdi tamponu boyutunda olmalı. cobs_decode'un
// ciktisi matematiksel olarak girdiden en az 1 byte kisadir (her cagrida en
// azindan son grup icin 0x00 dolgusu eklenmez) — AMA bu sadece "girdi==gercek
// veri uzunlugu" ise gecerlidir. Cagiran taraf girdiyi kapasiteye kadar
// (0x00 gorene kadar) biriktiriyorsa (bkz rtk_sender.h::rtk_serial_isle),
// gurultu/yanlis-baud durumunda girdi UZUNLUGU tampon KAPASITESINE ulasabilir
// ve cikis da o kapasiteye yakin (kapasite-1) olabilir. Cikis tamponu
// girdi tamponundan KUCUK secilirse bu durumda tampon tasar (REV B code
// review'da bulunan gercek bug, bkz rtk_sender.h duzeltmesi).
static inline uint16_t cobs_decode(const uint8_t* giris, uint16_t uzunluk, uint8_t* cikis) {
    if (uzunluk == 0) return 0;
    uint16_t oku_idx = 0, yaz_idx = 0;
    while (oku_idx < uzunluk) {
        uint8_t kod = giris[oku_idx++];
        if (kod == 0) return 0;
        for (uint8_t i = 1; i < kod; i++) {
            if (oku_idx >= uzunluk) return 0;
            cikis[yaz_idx++] = giris[oku_idx++];
        }
        if (kod < 0xFF && oku_idx < uzunluk)
            cikis[yaz_idx++] = 0x00;
    }
    return yaz_idx;
}

// ===== REV B ÇERÇEVE — KUR =====
// tip+id+payload+crc16(BE)'yi ham_scratch'e yazip COBS ile cobs_cikis'e
// kodlar, toplam COBS+0x00 uzunlugunu doner. ham_scratch en az
// (2+payload_uzunluk+2), cobs_cikis en az onun COBS worst-case genisleme
// formuluyle (n + n/254 + 2) kadar buyuk olmali — cagiran taraf saglar.
static inline uint16_t cobs_cerceve_olustur(uint8_t tip, uint8_t id,
                                             const uint8_t* payload, uint16_t payload_uzunluk,
                                             uint8_t* ham_scratch, uint8_t* cobs_cikis) {
    ham_scratch[0] = tip;
    ham_scratch[1] = id;
    memcpy(ham_scratch + 2, payload, payload_uzunluk);
    uint16_t ham_uzunluk = (uint16_t)(2 + payload_uzunluk);
    uint16_t crc = cobs_crc16(ham_scratch, ham_uzunluk);
    ham_scratch[ham_uzunluk]     = (uint8_t)(crc >> 8);   // buyuk-endian
    ham_scratch[ham_uzunluk + 1] = (uint8_t)(crc & 0xFF);
    return cobs_encode(ham_scratch, (uint16_t)(ham_uzunluk + 2), cobs_cikis);
}

// ===== REV B ÇERÇEVE — ÇÖZ =====
// COBS-decode EDİLMİŞ (0x00 sinirlayicisi zaten ayiklanmis) bir tampon
// alir; TIP+ID dahil CRC16'yi dogrular, basariliysa true doner ve
// tip/id/payload/payload_uzunluk cikislarini doldurur. payload_out,
// decoded tamponu ICINE isaret eder (kopyalamaz).
static inline bool cobs_cerceve_coz(const uint8_t* decoded, uint16_t decoded_uzunluk,
                                     uint8_t* tip_out, uint8_t* id_out,
                                     const uint8_t** payload_out, uint16_t* payload_uzunluk_out) {
    if (decoded_uzunluk < 4) return false;  // en az tip(1)+id(1)+crc16(2)
    uint16_t crc_hesap = cobs_crc16(decoded, (uint16_t)(decoded_uzunluk - 2));
    uint16_t crc_gelen = ((uint16_t)decoded[decoded_uzunluk - 2] << 8)
                        |  (uint16_t)decoded[decoded_uzunluk - 1];
    if (crc_hesap != crc_gelen) return false;
    *tip_out              = decoded[0];
    *id_out                = decoded[1];
    *payload_out           = decoded + 2;
    *payload_uzunluk_out   = (uint16_t)(decoded_uzunluk - 4);
    return true;
}
