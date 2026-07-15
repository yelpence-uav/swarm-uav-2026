#pragma once
// ===== RX BASE — RTK SENDER (REV B) =====
// YKİ'den (PC) gelen COBS cerceveli tam RTCM3 mesajini RTK_FRAG_PAYLOAD_MAKS
// byte'lik mesh fragmentlarina boler ve rtk_mesh_gonder() ile buyuk AES-GCM
// zarfinda mesh'e yayar.
//
// AKIŞ (REV B):
//   YKİ (PC) → COBS(TIP_RTK+BAZ_ID+rtcm+crc16_be)+0x00 → Serial1 (460800)
//   → rtk_serial_isle() (loop'ta okunur, cerceve coz+dogrula)
//   → tam RTCM mesaji → rtk_rtcm_fragment_ve_gonder()
//   → rtk_mesh_gonder() × N fragment (buyuk AES-GCM zarfi, CSMA+3-retry)
//   → TX DRONE'da rtk_mesh_loop()/rtk_mesh_frag_handle → reassembly
//   → Serial1 (460800, COBS+CRC16) → Pi

#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, BAZ_ID
#include "rtk_handler.h"   // RTK_MAX_FRAGS, RTK_FRAG_PAYLOAD_MAKS, rtk_mesh_gonder
                           // (pragma once sayesinde main.cpp'de cift include zararsiz)
#include "uart_cobs.h"     // cobs_decode, cobs_cerceve_coz

// rtk_mesh_frag_t'nin KANONIK tanimi rtk_pure.h'de (yukarida include edilen
// rtk_handler.h uzerinden gelir). Burada eskiden bir #ifndef fallback kopyasi
// vardi; guard rtk_pure.h'de zaten tanimlandigi icin o blok HIC derlenmiyordu
// ve icindeki REV A degerleri (payload 11B, toplam 18B) REV B'den sonra
// yaniltici hale gelmisti — kaldirildi.

// ===== GLOBAL PAKET SAYACI =====
// Her yeni RTCM mesajında artar → TX DRONE'da ID değişimini tespit eder
static uint32_t _rtk_paket_sayaci = 0;

// ===== YKİ GIRIS SAYAÇLARI — BAZ TARAFI TESHISI =====
// rtk_handler.h'deki alici sayaclarinin gonderici yakasi. Neden gerekli:
// "RTK niye fix vermiyor" sorusunda ilk ayrim BAZ HIC YAYIN YAPIYOR MU
// olmali. Bu sayaclar olmadan baz sessizce hicbir sey yayinlamiyorken
// (or. YKİ'nin baud'u yanlis -> her cerceve CRC'den duser) İHA tarafinda
// yalnizca "timeout" gorunur ve teshis RF'e yanlis yonlenir — oysa hava
// tertemizdir, sorun kablodadir.
static uint32_t rtk_tx_mesaj        = 0;   // YKİ'den gecerli RTCM alinip mesh'e yayilan
static uint32_t rtk_yki_crc_hatasi  = 0;   // COBS cerceve CRC16 tutmadi (baud/kablo/gurultu)
static uint32_t rtk_yki_tip_hatasi  = 0;   // CRC gecti ama tip/id beklenmedik (protokol uyumsuz)
static uint32_t rtk_yki_rtcm_hatasi = 0;   // cerceve saglam ama payload gecerli RTCM3 degil
static uint32_t rtk_tx_cok_buyuk    = 0;   // RTK_MAX_FRAGS'i asan mesaj (reddedildi)

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
        rtk_tx_cok_buyuk++;
        Serial.printf("[RTK-TX] HATA: mesaj cok buyuk (%u byte, max %u)\n",
                      uzunluk, (unsigned)(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS));
        return;
    }

    uint32_t paket_id = ++_rtk_paket_sayaci;
    rtk_tx_mesaj++;

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
// BAZ_ID artik mesh_config.h'de (TIP tanimlarinin yaninda) — rtk_handler.h de
// ayni degeri gormek zorunda oldugu icin paylasilan header'a tasindi.

// ADIM 5: durum LED'i — RTCM basariyla ayristirilip fragmentlere gonderilen
// her mesajda toggle edilir (spec 3.2, saha teshisi). Pin PLACEHOLDER,
// main.cpp::setup() icinde pinMode(RTK_LED_PIN, OUTPUT) cagrilir.
#define RTK_LED_PIN 2   // TODO: gercek donanimda dogrula
static bool _rtk_led_durum = false;

static uint8_t  _yki_rx_buf[RTK_COBS_BUF_SIZE];  // ham COBS byte'lari (0x00'a kadar)
static uint16_t _yki_rx_idx = 0;

// ===== GONDERICI (BAZ) ISTATISTIGI =====
// rtk_istatistik_yazdir() (alici/İHA) ile ayni desen, ama BAZ'in sorusu farkli:
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
                _yki_rx_idx = 0;   // tasma — cerceveyi at, yeniden senkronize ol
            continue;
        }

        if (_yki_rx_idx < 4) { _yki_rx_idx = 0; continue; }  // en az tip+id+crc16

        // BUG FIX (REV B code review): decoded[] eskiden daha kucuk (1608B)
        // sabitlenmisti, ama _yki_rx_buf RTK_COBS_BUF_SIZE'a (1612B) kadar
        // dolabiliyor ve cobs_decode cikisi girdi-1'e kadar (1611B) cikabilir
        // — 0x00'a hic denk gelmeyen gurultu/yanlis-baud senaryosunda ~3B
        // static buffer overflow olusuyordu. Kural (bkz uart_cobs.h):
        // cikis tamponu >= girdi tamponu olmali.
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
        // BOYUT SINIRI KONTROLU BILEREK YOK — gereksiz oldugu KANITLANABILIR:
        // RTCM3'un uzunluk alani 10 bit (spec 2.6), yani rtcm_payload_len <= 1023
        // ve yukaridaki tutarlilik kontrolunden sonra rtcm_uzunluk == 3+payload+3
        // <= 1029B'a SABITLENIR. Bu ust sinir hem reassembly buffer'in (1600B)
        // hem de fragmantasyonun (RTK_MAX_FRAGS*RTK_FRAG_PAYLOAD_MAKS = 8*191 =
        // 1528B) altinda kalir — yani 8 fragment her gecerli RTCM3 mesaji icin
        // yeterlidir (en kotu 1029B -> ceil(1029/191) = 6 fragment, 2 fragment
        // marj). Eskiden burada bir "rtcm_uzunluk > 1600" kontrolu vardi; bu
        // kanit geregi hicbir zaman tetiklenemiyordu (olu kod), kaldirildi.
        // Yine de savunma kaybolmadi: rtk_fragman_hesapla() sinirin asilmasi
        // halinde RTK_FRAGMAN_REDDEDILDI donuyor ve mesaj loglanip dusuruluyor.

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
