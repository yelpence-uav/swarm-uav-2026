#pragma once
// ===== RX BASE — RTK SENDER (REV B) =====
// YKİ'den (PC) gelen COBS cerceveli tam RTCM3 mesajini RTK_FRAG_PAYLOAD_MAKS
// byte'lik mesh fragmentlarina boler ve rtk_mesh_gonder() ile buyuk AES-GCM
// zarfinda mesh'e yayar.
//
// AKIŞ (REV B):
//   YKİ (PC) → COBS(TIP_RTK+BAZ_ID+rtcm+crc16_be)+0x00 → Serial2 (460800)
//   → rtk_serial_isle() (loop'ta okunur, cerceve coz+dogrula)
//   → tam RTCM mesaji → rtk_rtcm_fragment_ve_gonder()
//   → rtk_mesh_gonder() × N fragment (buyuk AES-GCM zarfi, CSMA+3-retry)
//   → TX DRONE'da rtk_mesh_loop()/rtk_mesh_frag_handle → reassembly
//   → Serial1 (460800, COBS+CRC16) → Pi

#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, mesh_gonder
#include "rtk_handler.h"   // RTK_MAX_FRAGS, RTK_FRAG_PAYLOAD_MAKS, rtk_mesh_gonder
                           // (pragma once sayesinde main.cpp'de cift include zararsiz)
#include "uart_cobs.h"     // cobs_decode, cobs_cerceve_coz

// rtk_mesh_frag_t TX DRONE'la ortak tanim. Kanonik tanim rtk_handler.h'de
// (bu dosya onu zaten include ediyor, RTK_MESH_FRAG_DEFINED guard sayesinde
// buradaki blok normalde derlenmez). DUSUK-1 FIX: frag_uzunluk alani eklendi,
// payload 12->11. Burasi sadece belgeleme/fallback amaçlı guncel tutulur.
#ifndef RTK_MESH_FRAG_DEFINED
#define RTK_MESH_FRAG_DEFINED
typedef struct __attribute__((packed)) {
    uint32_t paket_id;               // 4 byte
    uint8_t  frag_index;             // 1 byte
    uint8_t  frag_total;             // 1 byte
    uint8_t  frag_uzunluk;           // 1 byte — bu parçadaki gercek veri byte sayisi
    uint8_t  payload[RTK_FRAG_PAYLOAD_MAKS]; // 11 byte RTCM verisi
} rtk_mesh_frag_t;                   // 18 byte — mesh payload'a tam sığar
#endif

// ===== GLOBAL PAKET SAYACI =====
// Her yeni RTCM mesajında artar → TX DRONE'da ID değişimini tespit eder
static uint32_t _rtk_paket_sayaci = 0;

// ===== RTCM3 FRAGMENTASYON VE MESH'E GÖNDERME =====
// rtcm_veri: tam RTCM3 mesajı (200-1000 byte tipik)
// uzunluk:   mesajın toplam byte sayısı
//
// Her çağrıda yeni bir paket_id atanır.
// Fragment sayısı = ceil(uzunluk / RTK_FRAG_PAYLOAD_MAKS)
// DUSUK-1 FIX: son fragment RTK_FRAG_PAYLOAD_MAKS'tan kısa olabilir — artık
// frag.frag_uzunluk alanına gerçek byte sayısı yazılıyor, TX DRONE tarafı
// bunu okuyup reassembly toplam_uzunluğunu doğru hesaplıyor (eskiden her
// parça sabit 12 sayılıyor, dolgu sıfırları toplam uzunluğa dahil oluyordu).
static inline void rtk_rtcm_fragment_ve_gonder(const uint8_t* rtcm_veri, uint16_t uzunluk) {
    if (!rtcm_veri || uzunluk == 0) return;

    // ADIM 6: fragment sayisi ve her parcanin uzunlugu artik rtk_pure.h'deki
    // saf (Arduino'dan bagimsiz, native'de test edilen) hesaplayicidan
    // geliyor — mantik burada tekrarlanmiyor.
    uint8_t frag_uzunluklari[RTK_MAX_FRAGS];
    uint8_t frag_toplam = rtk_fragman_hesapla(uzunluk, frag_uzunluklari);
    if (frag_toplam == 0) return;
    if (frag_toplam == RTK_FRAGMAN_REDDEDILDI) {
        Serial.printf("[RTK-TX] HATA: mesaj cok buyuk (%u byte, max %u)\n",
                      uzunluk, (unsigned)(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS));
        return;
    }

    uint32_t paket_id = ++_rtk_paket_sayaci;

    Serial.printf("[RTK-TX] RTCM fragmentlaniyor: %u byte → %u fragment (paket_id=%lu)\n",
                  uzunluk, frag_toplam, (unsigned long)paket_id);

    // ADIM 5: fragment'lar arasina EK bir sabit bekleme (spec 3.2'nin eski
    // "2 ms bekle" onerisi) BILEREK KONULMADI. Yeni tasarimda RTK_FRAG_PAYLOAD_MAKS
    // buyudugu (191B) icin mesaj basina fragment sayisi cok azaldi (tipik
    // MSM4 ~100-300B icin 1-2 fragment, en kotu 720B/191≈4 fragment) — eski
    // 2ms onerisi ~23 fragment/mesaj varsayimina gore yazilmisti. Her
    // rtk_mesh_gonder() cagrisi zaten kendi CSMA rastgele beklemesini
    // (mesh_config.h, CSMA_GECIKME_MAKS_MS) uyguluyor; 1-4 fragment icin bu
    // yeterli — ayrica sabit gecikme eklemek RTCM'in 1sn'lik tazelik
    // butcesini gereksiz yere tuketirdi.
    uint16_t offset = 0;
    for (uint8_t i = 0; i < frag_toplam; i++) {
        rtk_mesh_frag_t frag;
        memset(&frag, 0, sizeof(frag));

        frag.paket_id     = paket_id;
        frag.frag_index   = i;
        frag.frag_total   = frag_toplam;
        frag.frag_uzunluk = frag_uzunluklari[i];
        memcpy(frag.payload, rtcm_veri + offset, frag_uzunluklari[i]);

        // REV B: eski mesh_gonder(TIP_RTK) (kucuk 18B zarf) yerine buyuk
        // AES-GCM zarfini kendi CSMA+retry'iyle gonderen rtk_mesh_gonder()
        // kullaniliyor (bkz rtk_handler.h).
        rtk_mesh_gonder(&frag);

        Serial.printf("[RTK-TX] Frag %u/%u gonderildi (offset=%u, %u byte)\n",
                      i + 1, frag_toplam, offset, frag_uzunluklari[i]);
        offset += frag_uzunluklari[i];
    }
}

// ===== YKİ COBS ÇERÇEVE OKUMA — RX BASE loop()'ta çağrılır (REV B ADIM 3) =====
// Eski hali (0xD3-senkronlu ham RTCM ayrıştırıcı, YKİ'den GELMEDEN önceki
// mimaride "GNSS modulu/Pi ham RTCM yolluyor" varsayımıyla yazılmıştı)
// KALDIRILDI. Artık YKİ, ADIM 2'deki ortak çerçeveyle gönderiyor:
//   COBS( TIP_RTK + BAZ_ID(99) + tam_rtcm_mesaji + crc16_be ) + 0x00
// (Pi/esp_rx hattıyla AYNI şema — REV B karar #3'ün "UART hattı çoklanmış
// sayılıyor" ilkesi YKİ hattına da uygulandı. NOT: bu, YKİ ekibine daha önce
// söylenen "prefiks yok, little-endian" cevabından FARKLI — pi_bridge/YKİ'ye
// bu değişiklik raporda ayrıca bildirilecek.)
//
// Akış: 0x00'a kadar biriktir → cobs_decode → cobs_cerceve_coz (CRC16 TIP+ID
// dahil doğrular) → TIP_RTK && BAZ_ID kontrolü → payload = tam RTCM mesajı.
// Ardından iki ucuz savunma kontrolü: payload[0]==0xD3, ve RTCM'in kendi
// uzunluk alanının (spec 2.6) payload boyutuyla tutarlılığı. Son olarak
// mesaj tipi (spec 2.6 formülü) loglanır; MSM7 görülürse UYARI basılır
// (Base yanlış yapılandırılmış demektir — spec Bölüm 5 MSM7'yi yasaklıyor).
//
// KULLANIM:
//   void loop() { rtk_serial_isle(Serial2); ... }
#define RTCM_MAX_MSG_SIZE RTK_REASSEMBLY_BUF_SIZE   // reassembly tarafiyla ayni ust sinir
#define BAZ_ID 99

// ADIM 5: durum LED'i — RTCM basariyla ayristirilip fragmentlere gonderilen
// her mesajda toggle edilir (spec 3.2, saha teshisi). Pin PLACEHOLDER,
// main.cpp::setup() icinde pinMode(RTK_LED_PIN, OUTPUT) cagrilir.
#define RTK_LED_PIN 2   // TODO: gercek donanimda dogrula
static bool _rtk_led_durum = false;

static uint8_t  _yki_rx_buf[RTK_COBS_BUF_SIZE];  // ham COBS byte'lari (0x00'a kadar)
static uint16_t _yki_rx_idx = 0;

static inline void rtk_serial_isle(HardwareSerial& seri) {
    while (seri.available()) {
        uint8_t b = seri.read();

        if (b != 0x00) {
            if (_yki_rx_idx < sizeof(_yki_rx_buf))
                _yki_rx_buf[_yki_rx_idx++] = b;
            else
                _yki_rx_idx = 0;   // tasma — cerceveyi at, yeniden senkronize ol
            continue;
        }

        if (_yki_rx_idx < 4) { _yki_rx_idx = 0; continue; }  // en az tip+id+crc16

        static uint8_t decoded[RTCM_MAX_MSG_SIZE + 8];
        uint16_t decoded_uzunluk = cobs_decode(_yki_rx_buf, _yki_rx_idx, decoded);
        _yki_rx_idx = 0;

        uint8_t tip_byte, id_byte;
        const uint8_t* rtcm_mesaj;
        uint16_t rtcm_uzunluk;
        if (!cobs_cerceve_coz(decoded, decoded_uzunluk, &tip_byte, &id_byte,
                               &rtcm_mesaj, &rtcm_uzunluk)) {
            Serial.println("[RTK-RX] HATA: CRC16 dogrulanamadi, cerceve atildi");
            continue;
        }
        if (tip_byte != TIP_RTK || id_byte != BAZ_ID) {
            Serial.printf("[RTK-RX] HATA: beklenmeyen tip/id (tip=0x%02X id=%u), atildi\n",
                          tip_byte, id_byte);
            continue;
        }

        // Savunma 1: RTCM3 preamble
        if (rtcm_uzunluk < 6 || rtcm_mesaj[0] != 0xD3) {
            Serial.println("[RTK-RX] HATA: payload RTCM3 ile baslamiyor, dusuruldu");
            continue;
        }
        // Savunma 2: uzunluk alani tutarliligi (spec 2.6 header matematigi)
        uint16_t rtcm_payload_len = (uint16_t)(rtcm_mesaj[1] & 0x03) << 8 | (uint16_t)rtcm_mesaj[2];
        uint16_t beklenen_uzunluk = 3 + rtcm_payload_len + 3;  // header + payload + CRC24
        if (beklenen_uzunluk != rtcm_uzunluk) {
            Serial.printf("[RTK-RX] HATA: RTCM uzunluk tutarsiz (beklenen %u, gelen %u), dusuruldu\n",
                          beklenen_uzunluk, rtcm_uzunluk);
            continue;
        }
        if (rtcm_uzunluk > RTCM_MAX_MSG_SIZE) {
            Serial.printf("[RTK-RX] HATA: RTCM mesaji cok buyuk (%u byte), dusuruldu\n", rtcm_uzunluk);
            continue;
        }

        // Mesaj tipi (spec 2.6) — MSM7 sizarsa erken uyari (Bolum 5 yasagi)
        uint16_t rtcm_tip = ((uint16_t)rtcm_mesaj[3] << 4) | (rtcm_mesaj[4] >> 4);
        if (rtcm_tip == 1077 || rtcm_tip == 1087 || rtcm_tip == 1097 || rtcm_tip == 1127) {
            Serial.printf("[RTK-RX] UYARI: MSM7 mesaji goruldu (tip %u) — Base MSM4'e "
                          "yapilandirilmali (spec Bolum 5)!\n", rtcm_tip);
        } else {
            Serial.printf("[RTK-RX] RTCM tip %u, %u byte\n", rtcm_tip, rtcm_uzunluk);
        }

        rtk_rtcm_fragment_ve_gonder(rtcm_mesaj, rtcm_uzunluk);

        // ADIM 5: durum LED'i toggle — RTCM akarken yanip soner
        _rtk_led_durum = !_rtk_led_durum;
        digitalWrite(RTK_LED_PIN, _rtk_led_durum ? HIGH : LOW);
    }
}
