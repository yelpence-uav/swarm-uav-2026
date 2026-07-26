#pragma once
// RX BASE - RTK sender.
// YKİ'den (PC) gelen COBS cerceveli tam RTCM3 mesajini RTK_FRAG_PAYLOAD_MAKS
// byte'lik mesh fragmentlarina boler ve rtk_mesh_gonder() ile buyuk AES-GCM
// zarfinda mesh'e yayar.
//
// Akis:
//   YKİ (PC) -> COBS(TIP_RTK+BAZ_ID+rtcm+crc16_be)+0x00 -> Serial1 (460800)
//   -> rtk_serial_isle() (loop'ta okunur, cerceve coz+dogrula)
//   -> tam RTCM mesaji -> rtk_rtcm_fragment_ve_gonder()
//   -> rtk_mesh_gonder() x N fragment (buyuk AES-GCM zarfi, CSMA+3-retry)
//   -> TX DRONE'da rtk_mesh_loop()/rtk_mesh_frag_handle -> reassembly
//   -> Serial1 (460800, COBS+CRC16) -> Pi

#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, BAZ_ID
#include "rtk_handler.h"   // RTK_MAX_FRAGS, RTK_FRAG_PAYLOAD_MAKS, rtk_mesh_gonder
#include "uart_cobs.h"     // cobs_decode, cobs_cerceve_coz

// rtk_mesh_frag_t'nin kanonik tanimi rtk_pure.h'de (rtk_handler.h uzerinden gelir).

// Global paket sayaci: her yeni RTCM mesajinda artar, TX DRONE ID degisimini
// buradan tespit eder.
static uint32_t _rtk_paket_sayaci = 0;

// YKİ giris sayaclari - baz tarafi teshisi.
// rtk_handler.h'deki alici sayaclarinin gonderici yakasi. "RTK niye fix vermiyor"
// sorusunda ilk ayrim baz hic yayin yapiyor mu olmali. Bu sayaclar olmadan baz
// sessizce yayinlamiyorken (or. YKİ baud'u yanlis -> her cerceve CRC'den duser)
// İHA tarafinda yalnizca "timeout" gorunur ve teshis RF'e yanlis yonlenir, oysa
// sorun kablodadir.
static uint32_t rtk_tx_mesaj        = 0;   // YKİ'den gecerli RTCM alinip mesh'e yayilan
static uint32_t rtk_yki_crc_hatasi  = 0;   // COBS cerceve CRC16 tutmadi (baud/kablo/gurultu)
static uint32_t rtk_yki_tip_hatasi  = 0;   // CRC gecti ama tip/id beklenmedik (protokol uyumsuz)
static uint32_t rtk_yki_rtcm_hatasi = 0;   // cerceve saglam ama payload gecerli RTCM3 degil
static uint32_t rtk_tx_cok_buyuk    = 0;   // RTK_MAX_FRAGS'i asan mesaj (reddedildi)

// RTCM3 fragmentasyon ve mesh'e gonderme.
// rtcm_veri: tam RTCM3 mesaji (200-1000 byte tipik)
// uzunluk:   mesajin toplam byte sayisi
//
// Her cagrida yeni bir paket_id atanir.
// Fragment sayisi = ceil(uzunluk / RTK_FRAG_PAYLOAD_MAKS)
// Son fragment RTK_FRAG_PAYLOAD_MAKS'tan kisa olabilir; frag.frag_uzunluk alanina
// gercek byte sayisi yazilir, TX DRONE bunu okuyup reassembly toplam uzunlugunu
// dogru hesaplar (aksi halde dolgu sifirlari toplam uzunluga dahil olurdu).
static inline void rtk_rtcm_fragment_ve_gonder(const uint8_t* rtcm_veri, uint16_t uzunluk) {
    if (!rtcm_veri || uzunluk == 0) return;

    // Fragment sayisi ve her parcanin uzunlugu rtk_pure.h'deki saf hesaplayicidan
    // geliyor, mantik burada tekrarlanmiyor.
    uint8_t frag_uzunluklari[RTK_MAX_FRAGS];
    uint8_t frag_toplam = rtk_fragman_hesapla(uzunluk, frag_uzunluklari);
    if (frag_toplam == 0) return;
    if (frag_toplam == RTK_FRAGMAN_REDDEDILDI) {
        rtk_tx_cok_buyuk++;
        Serial.printf("[RTK-TX] HATA: mesaj cok buyuk (%u byte, max %u)\n",
                      uzunluk, (unsigned)(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS));
        return;
    }

    uint32_t paket_id = ++_rtk_paket_sayaci;
    rtk_tx_mesaj++;

    Serial.printf("[RTK-TX] RTCM fragmentlaniyor: %u byte -> %u fragment (paket_id=%lu)\n",
                  uzunluk, frag_toplam, (unsigned long)paket_id);

    // Fragment'lar arasina ek sabit bekleme konulmadi. RTK_FRAG_PAYLOAD_MAKS
    // 191B oldugundan mesaj basina fragment sayisi az (tipik MSM4 icin 1-2, en
    // kotu ~4). Her rtk_mesh_gonder() zaten kendi CSMA rastgele beklemesini
    // (CSMA_GECIKME_MAKS_MS) uyguluyor; sabit gecikme eklemek RTCM'in 1sn'lik
    // tazelik butcesini gereksiz yere tuketirdi.
    uint16_t offset = 0;
    for (uint8_t i = 0; i < frag_toplam; i++) {
        rtk_mesh_frag_t frag;
        memset(&frag, 0, sizeof(frag));

        frag.paket_id     = paket_id;
        frag.frag_index   = i;
        frag.frag_total   = frag_toplam;
        frag.frag_uzunluk = frag_uzunluklari[i];
        memcpy(frag.payload, rtcm_veri + offset, frag_uzunluklari[i]);

        // Buyuk AES-GCM zarfini kendi CSMA+retry'iyle gonderen rtk_mesh_gonder()
        // kullaniliyor (bkz rtk_handler.h).
        rtk_mesh_gonder(&frag);

        Serial.printf("[RTK-TX] Frag %u/%u gonderildi (offset=%u, %u byte)\n",
                      i + 1, frag_toplam, offset, frag_uzunluklari[i]);
        offset += frag_uzunluklari[i];
    }
}

// YKİ COBS cerceve okuma, RX BASE loop()'ta cagrilir.
// YKİ ortak cerceveyle gonderiyor:
//   COBS( TIP_RTK + BAZ_ID(99) + tam_rtcm_mesaji + crc16_be ) + 0x00
// (Pi/esp_rx hattiyla ayni sema; "UART hatti coklanmis sayilir" ilkesi YKİ
// hattina da uygulandi. Not: bu, YKİ ekibine daha once soylenen "prefiks yok,
// little-endian" cevabindan farkli, raporda ayrica bildirilecek.)
//
// Akis: 0x00'a kadar biriktir -> cobs_decode -> cobs_cerceve_coz (CRC16 TIP+ID
// dahil dogrular) -> TIP_RTK && BAZ_ID kontrolu -> payload = tam RTCM mesaji.
// Ardindan iki ucuz savunma: payload[0]==0xD3 ve RTCM'in kendi uzunluk alaninin
// (spec 2.6) payload boyutuyla tutarliligi. Son olarak mesaj tipi loglanir; MSM7
// gorulurse uyari basilir (Base yanlis yapilandirilmis, spec Bolum 5 yasagi).
//
// Kullanim:
//   void loop() { rtk_serial_isle(Serial2); ... }

// Durum LED'i: RTCM basariyla ayristirilip fragmentlere gonderilen her mesajda
// toggle edilir (saha teshisi). Pin placeholder, main.cpp::setup() icinde
// pinMode(RTK_LED_PIN, OUTPUT) cagrilir.
#define RTK_LED_PIN 2   // TODO: gercek donanimda dogrula
static bool _rtk_led_durum = false;

static uint8_t  _yki_rx_buf[RTK_COBS_BUF_SIZE];  // ham COBS byte'lari (0x00'a kadar)
static uint16_t _yki_rx_idx = 0;

// Gonderici (baz) istatistigi.
// rtk_istatistik_yazdir() (alici/İHA) ile ayni desen, ama baz'in sorusu farkli:
// "ben yayin yapiyor muyum, yapmiyorsam nerede tikandim?" Okuma kilavuzu:
//   yki_crc yuksek + mesaj=0  -> YKİ hatti: baud/kablo/gurultu (hava temiz)
//   yki_tip yuksek            -> YKİ protokolu uyumsuz (prefiks/spec surumu)
//   yki_rtcm yuksek           -> Base yanlis yapilandirilmis (RTCM3 uretmiyor)
//   mesaj artiyor + zarf_hata -> ESP-NOW TX kuyrugu doluyor (yerel, RF degil)
//   mesaj artiyor + hata yok  -> baz saglam; sorun havada ya da İHA'da ara
static inline void rtk_tx_istatistik_yazdir(void) {
    Serial.printf("[RTK-TX] mesaj=%lu frag=%lu | yki_crc=%lu yki_tip=%lu "
                  "yki_rtcm=%lu cok_buyuk=%lu zarf_hata=%lu\n",
                  (unsigned long)rtk_tx_mesaj,
                  (unsigned long)rtk_tx_frag,
                  (unsigned long)rtk_yki_crc_hatasi,
                  (unsigned long)rtk_yki_tip_hatasi,
                  (unsigned long)rtk_yki_rtcm_hatasi,
                  (unsigned long)rtk_tx_cok_buyuk,
                  (unsigned long)rtk_tx_zarf_hatasi);
}

static inline void rtk_serial_isle(HardwareSerial& seri) {
    while (seri.available()) {
        uint8_t b = seri.read();

        if (b != 0x00) {
            if (_yki_rx_idx < sizeof(_yki_rx_buf))
                _yki_rx_buf[_yki_rx_idx++] = b;
            else
                _yki_rx_idx = 0;   // tasma: cerceveyi at, yeniden senkronize ol
            continue;
        }

        if (_yki_rx_idx < 4) { _yki_rx_idx = 0; continue; }  // en az tip+id+crc16

        // decoded[] RTK_COBS_BUF_SIZE olmali: _yki_rx_buf o boyuta kadar dolabilir
        // ve cobs_decode cikisi girdi-1'e kadar cikabilir. Daha kucuk sabitlenirse
        // 0x00'a hic denk gelmeyen gurultu/yanlis-baud senaryosunda static buffer
        // overflow olur. Kural (bkz uart_cobs.h): cikis tamponu >= girdi tamponu.
        static uint8_t decoded[RTK_COBS_BUF_SIZE];
        uint16_t decoded_uzunluk = cobs_decode(_yki_rx_buf, _yki_rx_idx, decoded);
        _yki_rx_idx = 0;

        uint8_t tip_byte, id_byte;
        const uint8_t* rtcm_mesaj;
        uint16_t rtcm_uzunluk;
        if (!cobs_cerceve_coz(decoded, decoded_uzunluk, &tip_byte, &id_byte,
                               &rtcm_mesaj, &rtcm_uzunluk)) {
            rtk_yki_crc_hatasi++;
            Serial.println("[RTK-RX] HATA: CRC16 dogrulanamadi, cerceve atildi "
                           "(surekli tekrarliyorsa YKİ baud/kablo kontrol et)");
            continue;
        }
        if (tip_byte != TIP_RTK || id_byte != BAZ_ID) {
            rtk_yki_tip_hatasi++;
            Serial.printf("[RTK-RX] HATA: beklenmeyen tip/id (tip=0x%02X id=%u), atildi\n",
                          tip_byte, id_byte);
            continue;
        }

        // Savunma 1: RTCM3 preamble
        if (rtcm_uzunluk < 6 || rtcm_mesaj[0] != 0xD3) {
            rtk_yki_rtcm_hatasi++;
            Serial.println("[RTK-RX] HATA: payload RTCM3 ile baslamiyor, dusuruldu");
            continue;
        }
        // Savunma 2: uzunluk alani tutarliligi (spec 2.6 header matematigi)
        uint16_t rtcm_payload_len = (uint16_t)(rtcm_mesaj[1] & 0x03) << 8 | (uint16_t)rtcm_mesaj[2];
        uint16_t beklenen_uzunluk = 3 + rtcm_payload_len + 3;  // header + payload + CRC24
        if (beklenen_uzunluk != rtcm_uzunluk) {
            rtk_yki_rtcm_hatasi++;
            Serial.printf("[RTK-RX] HATA: RTCM uzunluk tutarsiz (beklenen %u, gelen %u), dusuruldu\n",
                          beklenen_uzunluk, rtcm_uzunluk);
            continue;
        }
        // Ayri bir boyut siniri kontrolu yok: RTCM3'un uzunluk alani 10 bit (spec
        // 2.6), yani rtcm_payload_len <= 1023 ve tutarlilik kontrolunden sonra
        // rtcm_uzunluk <= 1029B. Bu hem reassembly buffer'in (1600B) hem de
        // fragmantasyonun (8*191 = 1528B) altinda; en kotu 1029B -> 6 fragment.
        // Yine de rtk_fragman_hesapla() sinir asilirsa RTK_FRAGMAN_REDDEDILDI
        // donuyor ve mesaj loglanip dusuruluyor.

        // Mesaj tipi (spec 2.6): MSM7 sizarsa erken uyari (Bolum 5 yasagi)
        uint16_t rtcm_tip = ((uint16_t)rtcm_mesaj[3] << 4) | (rtcm_mesaj[4] >> 4);
        if (rtcm_tip == 1077 || rtcm_tip == 1087 || rtcm_tip == 1097 || rtcm_tip == 1127) {
            Serial.printf("[RTK-RX] UYARI: MSM7 mesaji goruldu (tip %u) — Base MSM4'e "
                          "yapilandirilmali (spec Bolum 5)!\n", rtcm_tip);
        } else {
            Serial.printf("[RTK-RX] RTCM tip %u, %u byte\n", rtcm_tip, rtcm_uzunluk);
        }

        rtk_rtcm_fragment_ve_gonder(rtcm_mesaj, rtcm_uzunluk);

        // durum LED'i toggle: RTCM akarken yanip soner
        _rtk_led_durum = !_rtk_led_durum;
        digitalWrite(RTK_LED_PIN, _rtk_led_durum ? HIGH : LOW);
    }
}
