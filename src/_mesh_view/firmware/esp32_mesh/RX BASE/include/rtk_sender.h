#pragma once
// ===== RX BASE — RTK SENDER =====
// RTCM3 mesajlarini RTK_FRAG_PAYLOAD_MAKS (11) byte payload'li mesh
// fragmentlarina boler ve mesh_gonder(payload, TIP_RTK) ile AES-GCM
// sifreli mesh'e yayar. (DUSUK-1 FIX: eskiden 12 byte'ti, frag_uzunluk
// alani icin 1 byte ayrildi.)
//
// AKIŞ:
//   Pi (Serial1) → RTCM bytes → rtk_rtcm_isle (loop'ta okunur)
//   → tam mesaj tespiti → rtk_rtcm_fragment_ve_gonder
//   → mesh_gonder(TIP_RTK) × N fragment
//   → TX DRONE'da rtk_mesh_frag_handle → reassembly → Serial1 → Pi
//
// BANT HESABİ:
//   Tipik RTCM 1 Hz, ~250 byte → 250/11 ≈ 23 fragment/saniye
//   Mesh kapasitesi rahatca destekler.

#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, mesh_gonder
#include "rtk_handler.h"   // RTK_MAX_FRAGS — KRITIK-1 fix: sender/receiver ayni sinira uymali
                           // (pragma once sayesinde main.cpp'de cift include zararsiz)

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

    // Fragment sayisi hesapla
    uint8_t frag_toplam = (uint8_t)((uzunluk + (RTK_FRAG_PAYLOAD_MAKS - 1)) / RTK_FRAG_PAYLOAD_MAKS);
    if (frag_toplam == 0) return;
    // KRITIK-1 FIX: TX DRONE tarafi alinan_maske artik uint64_t (max 64 frag
    // guvenle temsil edilebilir). Daha once burada 100'e izin veriliyordu,
    // ama alici 32 bitle sessizce hicbir zaman birlestiremiyordu (>=32 frag UB).
    // 64'u asan mesaji artik burada, gonderim oncesi, gurultuyle reddediyoruz.
    if (frag_toplam > RTK_MAX_FRAGS) {
        // 64 * 11 = 704 byte maksimum — TX DRONE'daki alinan_maske (uint64_t) ile eslesir
        Serial.printf("[RTK-TX] HATA: mesaj cok buyuk (%u byte, max %u)\n",
                      uzunluk, (unsigned)(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS));
        return;
    }

    uint32_t paket_id = ++_rtk_paket_sayaci;

    Serial.printf("[RTK-TX] RTCM fragmentlaniyor: %u byte → %u fragment (paket_id=%lu)\n",
                  uzunluk, frag_toplam, (unsigned long)paket_id);

    for (uint8_t i = 0; i < frag_toplam; i++) {
        rtk_mesh_frag_t frag;
        memset(&frag, 0, sizeof(frag));

        frag.paket_id   = paket_id;
        frag.frag_index = i;
        frag.frag_total = frag_toplam;

        uint16_t offset    = (uint16_t)i * RTK_FRAG_PAYLOAD_MAKS;
        uint16_t kalan     = uzunluk - offset;
        uint8_t  kopyala   = (kalan >= RTK_FRAG_PAYLOAD_MAKS) ? RTK_FRAG_PAYLOAD_MAKS : (uint8_t)kalan;
        frag.frag_uzunluk  = kopyala;   // DUSUK-1 FIX: gercek uzunluk artik iletiliyor
        memcpy(frag.payload, rtcm_veri + offset, kopyala);
        // Son fragmentte kalan < MAKS ise payload sonu sifir kalir (memset ile),
        // ama artik frag_uzunluk sayesinde alici bu dolguyu veriye katmiyor.

        // mesh_gonder: sifreler ve yayar
        mesh_gonder((uint8_t*)&frag, TIP_RTK);

        Serial.printf("[RTK-TX] Frag %u/%u gonderildi (offset=%u, %u byte)\n",
                      i + 1, frag_toplam, offset, kopyala);
    }
}

// ===== RTCM3 SERIAL OKUMA — RX BASE loop()'ta çağrılır =====
// Pi'den Serial1 üzerinden gelen RTCM3 byte akışını okur.
// RTCM3 frame yapisi: 0xD3 + 6-bit 0 + 10-bit uzunluk + payload + CRC24
// Tam mesaj tamamlaninca rtk_rtcm_fragment_ve_gonder cagrilir.
//
// KULLANIMM:
//   void loop() { rtk_serial_isle(); ... }

#define RTCM_MAX_MSG_SIZE 1200
static struct {
    uint8_t  buf[RTCM_MAX_MSG_SIZE];
    uint16_t idx;
    uint16_t beklenen_uzunluk;  // 0 = henuz header parse edilmedi
    bool     senkronize;
} _rtcm_rx = {};

static inline void rtk_serial_isle(HardwareSerial& seri) {
    while (seri.available()) {
        uint8_t b = seri.read();

        // Senkronizasyon: 0xD3 preamble'i bekle
        if (!_rtcm_rx.senkronize) {
            if (b == 0xD3) {
                _rtcm_rx.buf[0]          = 0xD3;
                _rtcm_rx.idx             = 1;
                _rtcm_rx.beklenen_uzunluk = 0;
                _rtcm_rx.senkronize      = true;
            }
            continue;
        }

        // Buffer taşma koruması
        if (_rtcm_rx.idx >= RTCM_MAX_MSG_SIZE) {
            Serial.println("[RTK-RX] HATA: buffer tasti, yeniden senkronize ediliyor");
            memset(&_rtcm_rx, 0, sizeof(_rtcm_rx));
            continue;
        }

        _rtcm_rx.buf[_rtcm_rx.idx++] = b;

        // Header 3 byte tamamlandıktan sonra uzunlugu hesapla:
        // Byte[1]: 00xxxxxx (ust 6 bit sifir, alt 2 bit uzunlugun MSB'si)
        // Byte[2]: uzunlugun kalan 8 biti
        // Toplam mesaj = 3 (header) + uzunluk + 3 (CRC24)
        if (_rtcm_rx.idx == 3 && _rtcm_rx.beklenen_uzunluk == 0) {
            uint16_t payload_len = (uint16_t)(_rtcm_rx.buf[1] & 0x03) << 8
                                 | (uint16_t)_rtcm_rx.buf[2];
            _rtcm_rx.beklenen_uzunluk = 3 + payload_len + 3;  // header + payload + CRC24

            if (_rtcm_rx.beklenen_uzunluk > RTCM_MAX_MSG_SIZE) {
                Serial.printf("[RTK-RX] HATA: gecersiz uzunluk %u, sifirlanıyor\n",
                              _rtcm_rx.beklenen_uzunluk);
                memset(&_rtcm_rx, 0, sizeof(_rtcm_rx));
                continue;
            }
        }

        // Tam mesaj geldi mi?
        if (_rtcm_rx.beklenen_uzunluk > 0 &&
            _rtcm_rx.idx >= _rtcm_rx.beklenen_uzunluk) {
            // CRC24 dogrulamasi isteğe bağlı — simdilik atlanıyor,
            // mesh AES-GCM bütünlük sağlıyor.
            rtk_rtcm_fragment_ve_gonder(_rtcm_rx.buf, _rtcm_rx.beklenen_uzunluk);
            memset(&_rtcm_rx, 0, sizeof(_rtcm_rx));
        }
    }
}
