#pragma once
#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, mesh_gonder

// ===== SABITLER =====
#define RTK_MAX_PAYLOAD          220    // TX DRONE alim tarafı (eski ESP-NOW fragment boyutu)
#define RTK_MAX_FRAGS             64    // KRITIK-1 FIX: alinan_maske artik uint64_t (asagida).
                                        // 64 bit maske guvenle 0..63 index temsil eder.
                                        // 64*11 = 704 byte -> tipik MSM7 (400-600B) rahat sigar.
                                        // (DUSUK-1 FIX ile fragment payload'i 12->11 oldu.)
                                        // 65+ fragmentli mesaj artik SENDER'da reddedilir
                                        // (rtk_sender.h ayni sinira guncellendi, senkron kalmali).
#define RTK_REASSEMBLY_BUF_SIZE  1200
#define RTK_HAM_BUF_SIZE   (1 + 1 + RTK_REASSEMBLY_BUF_SIZE + 2)
#define RTK_COBS_BUF_SIZE  (RTK_HAM_BUF_SIZE + (RTK_HAM_BUF_SIZE / 254) + 2)
// 2000 -> 500ms: fragment basina en kotu CSMA+retry gecikmesi ~40ms
// (CSMA_GECIKME_MAKS_MS=10 + 3 deneme*~2-7ms), 500ms bu payi rahat
// karsiliyor. Daha kisa timeout, kayip fragment durumunda reassembly
// buffer'ini daha hizli serbest birakiyor (sonraki 1Hz RTCM dongusunu
// beklemeden).
#define RTK_FRAG_TIMEOUT_MS      500UL

// DUSUK-1 FIX: fragment basina gercek payload boyutu 12 -> 11 byte'a indi;
// kazanilan 1 byte frag_uzunluk alanina ayrildi (struct toplami 18 byte'ta sabit).
// SENDER (rtk_sender.h) ve RECEIVER (burasi) bu sabiti PAYLASMALI.
#define RTK_FRAG_PAYLOAD_MAKS 11

#ifndef RTK_MESH_FRAG_DEFINED
#define RTK_MESH_FRAG_DEFINED
// ===== MESH FRAGMENT YAPISI (RX BASE gönderir, TX DRONE alır) =====
// Mesh payload limiti 18 byte — bu struct tam sığar.
// DUSUK-1 FIX: frag_uzunluk eklendi — bu parçanın GERÇEK veri byte sayısını
// taşır (son parça hariç hepsi RTK_FRAG_PAYLOAD_MAKS=11'dir). Eskiden her
// parça reassembly'de sabit 12 sayılıyordu; son parça 12'den kısaysa
// toplam_uzunluk gerçekte olduğundan uzun çıkıyordu (dolgu sıfırlar dahil
// ediliyordu). Şimdi eski ESP-NOW yolundaki (rtk_paket_isle, satır ~273)
// gercek_uzunluk mantığıyla tutarlı.
typedef struct __attribute__((packed)) {
    uint32_t paket_id;               // 4 byte  — hangi RTCM mesajına ait
    uint8_t  frag_index;             // 1 byte  — bu parçanın sırası (0'dan başlar)
    uint8_t  frag_total;             // 1 byte  — toplam parça sayısı
    uint8_t  frag_uzunluk;           // 1 byte  — bu parçadaki GERÇEK veri byte sayısı (1..11)
    uint8_t  payload[RTK_FRAG_PAYLOAD_MAKS]; // 11 byte — RTCM verisi
} rtk_mesh_frag_t;                   // Toplam: 18 byte
#endif // RTK_MESH_FRAG_DEFINED

// ===== PAKET YAPISI (eski ESP-NOW tabanlı, geriye uyumluluk) =====
typedef struct __attribute__((packed)) {
    uint32_t paket_id;
    uint8_t  frag_index;
    uint8_t  frag_total;
    uint8_t  payload[RTK_MAX_PAYLOAD];
    uint16_t payload_uzunluk;
    uint16_t crc;
} rtk_paket_t;

// ===== DURUM SAYAÇLARI =====
static uint32_t rtk_alinan          = 0;
static uint32_t rtk_kayip           = 0;
static uint32_t rtk_uart_gonderilen = 0;

// ===== FRAGMENTASYON YENİDEN BİRLEŞTİRME =====
// alinan_maske: uint32_t → uint64_t (KRITIK-1 FIX)
//   uint32_t ile (1u << toplam), toplam>=32 oldugunda TANIMSIZ DAVRANIS idi.
//   Cok-uydulu RTCM (MSM7: GPS+GLONASS+Galileo+BeiDou) 400-600B -> 34-50 fragment,
//   32 bit maskeyi rahatlikla asiyordu -> sessiz birlesme hatasi + rtk_kayip artisi.
//   uint64_t ile guvenli sinir 64 fragment (768 byte). toplam==64 ozel durumla
//   ele alinir; (1ull<<64) de tanimsizdir (bkz _rtk_tamamsa_gonder / rtk_loop).
static struct {
    uint32_t paket_id;
    uint8_t  toplam;
    uint64_t alinan_maske;          // uint32_t → uint64_t (KRITIK-1 fix, max 64 frag)
    uint8_t  buf[RTK_REASSEMBLY_BUF_SIZE];
    uint16_t parca_uzunluk[RTK_MAX_FRAGS];
    uint32_t son_parca_ms;
} _rtk_asm = {};

static uint16_t _rtk_crc16(const uint8_t* veri, uint16_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

static inline void _rtk_asm_sifirla(void) {
    memset(&_rtk_asm, 0, sizeof(_rtk_asm));
}

static inline void _rtk_uart_gonder(const uint8_t* veri, uint16_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    uint16_t ham_uzunluk = 1 + 1 + uzunluk + 2;
    static uint8_t ham[RTK_HAM_BUF_SIZE];
    ham[0] = TIP_RTK;
    ham[1] = 99; // BAZ_ID
    memcpy(ham + 2, veri, uzunluk);
    ham[ham_uzunluk - 2] = (uint8_t)(crc >> 8);
    ham[ham_uzunluk - 1] = (uint8_t)(crc & 0xFF);
    static uint8_t cobs_buf[RTK_COBS_BUF_SIZE];
    uint16_t cobs_len = 1;
    uint16_t code_idx = 0;
    uint8_t code = 1;
    for (uint16_t i = 0; i < ham_uzunluk; i++) {
        if (ham[i] == 0x00) {
            cobs_buf[code_idx] = code;
            code_idx = cobs_len++;
            cobs_buf[cobs_len - 1] = 0;
            code = 1;
        } else {
            cobs_buf[cobs_len++] = ham[i];
            code++;
            if (code == 0xFF) {
                cobs_buf[code_idx] = code;
                code_idx = cobs_len++;
                cobs_buf[cobs_len - 1] = 0;
                code = 1;
            }
        }
    }
    cobs_buf[code_idx] = code;
    cobs_buf[cobs_len++] = 0x00;
    Serial1.write(cobs_buf, cobs_len);
    rtk_uart_gonderilen++;
    Serial.printf("[RTK] RPiye gonderildi: %u byte (toplam: %lu)\n",
                  uzunluk, rtk_uart_gonderilen);
}

static inline void _rtk_tamamsa_gonder(void) {
    // KRITIK-1 FIX: uint64_t maske. toplam==64 icin (1ull<<64) tanimsizdir
    // (shift genisligi >= tip genisligi), bu yuzden ozel durumla ele alinir.
    uint64_t tam_maske = (_rtk_asm.toplam >= 64) ? ~0ULL
                        : ((1ull << _rtk_asm.toplam) - 1ull);
    if (_rtk_asm.alinan_maske != tam_maske) return;

    uint16_t toplam_uzunluk = 0;
    for (uint8_t i = 0; i < _rtk_asm.toplam; i++)
        toplam_uzunluk += _rtk_asm.parca_uzunluk[i];

    if (toplam_uzunluk > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: birlesik paket cok buyuk: %u byte\n", toplam_uzunluk);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    Serial.printf("[RTK] Birlestirildi: %u byte\n", toplam_uzunluk);
    _rtk_uart_gonder(_rtk_asm.buf, toplam_uzunluk);
    _rtk_asm_sifirla();
}

// ===== MESH'TEN GELEN RTK FRAGMENT İŞLE (TX DRONE) =====
// mesh_veri_al callback'inde TIP_RTK görülünce bu fonksiyona yönlendirilir.
// rtk_mesh_frag_t (18 byte) parse eder, reassembly buffer'a koyar,
// tamamlanınca _rtk_uart_gonder ile RPi'ye iletir.
//
// TASARIM KARARI: burada ayrica ham CRC16 dogrulamasi YAPILMIYOR. Bu
// fonksiyona ulasan her fragment zaten mesh_veri_al()'da aes_coz_gcm()
// (AES-128-GCM auth tag) ile dogrulanmis durumda — bozuk/sahte paket GCM
// asamasinda elenip buraya hic gelmiyor. GCM authentication CRC16'dan daha
// guclu oldugu icin ayrica chunk-level CRC16 eklemek redundant olurdu; ustelik
// rtk_mesh_frag_t zaten 18 byte'lik mesh payload limitini tam dolduruyor
// (2 byte'lik CRC16 icin RTK_FRAG_PAYLOAD_MAKS'i 11'den 9'a dusurmek gerekirdi,
// bu da surudeki paylasimli kanalda fragment/paket sayisini artirirdi).
static inline void rtk_mesh_frag_handle(const uint8_t* ham_veri, uint16_t uzunluk) {
    if (uzunluk < sizeof(rtk_mesh_frag_t)) {
        Serial.printf("[RTK] HATA: fragment cok kisa (%u byte, beklenen %u)\n",
                      uzunluk, (unsigned)sizeof(rtk_mesh_frag_t));
        rtk_kayip++;
        return;
    }

    const rtk_mesh_frag_t* f = (const rtk_mesh_frag_t*)ham_veri;

    // Gecersiz fragment parametreleri
    if (f->frag_total == 0 || f->frag_total > RTK_MAX_FRAGS ||
        f->frag_index >= f->frag_total) {
        Serial.printf("[RTK] HATA: gecersiz frag index=%u total=%u\n",
                      f->frag_index, f->frag_total);
        rtk_kayip++;
        return;
    }

    // DUSUK-1 FIX: frag_uzunluk sinir disi olamaz (0 ya da MAKS'i asamaz)
    if (f->frag_uzunluk == 0 || f->frag_uzunluk > RTK_FRAG_PAYLOAD_MAKS) {
        Serial.printf("[RTK] HATA: gecersiz frag_uzunluk=%u (idx=%u)\n",
                      f->frag_uzunluk, f->frag_index);
        rtk_kayip++;
        return;
    }

    uint32_t simdi = millis();

    // Farkli paket_id ya da timeout → sifirla
    if (_rtk_asm.toplam > 0 &&
        (f->paket_id != _rtk_asm.paket_id ||
         (simdi - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS)) {
        Serial.printf("[RTK] TIMEOUT/ID DEGISIM — yeniden baslaniyor\n");
        rtk_kayip++;
        _rtk_asm_sifirla();
    }

    // Yeni paket baslar
    if (_rtk_asm.toplam == 0) {
        _rtk_asm.paket_id = f->paket_id;
        _rtk_asm.toplam   = f->frag_total;
    }

    uint8_t idx = f->frag_index;

    // Duplikat kontrol
    if (_rtk_asm.alinan_maske & (1ull << idx)) {
        Serial.printf("[RTK] Duplikat frag %u, atlaniyor\n", idx);
        return;
    }

    // Buffer taşma kontrol
    // Her fragment en fazla RTK_FRAG_PAYLOAD_MAKS byte payload, offset = idx * MAKS
    uint16_t offset = (uint16_t)idx * RTK_FRAG_PAYLOAD_MAKS;
    if (offset + RTK_FRAG_PAYLOAD_MAKS > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: buffer tasacak offset=%u\n", offset);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    // DUSUK-1 FIX: gercek uzunluk kadar kopyala ve kaydet (12 sabit degil)
    memcpy(_rtk_asm.buf + offset, f->payload, f->frag_uzunluk);
    _rtk_asm.parca_uzunluk[idx] = f->frag_uzunluk;
    _rtk_asm.alinan_maske      |= (1ull << idx);
    _rtk_asm.son_parca_ms       = simdi;

    rtk_alinan++;
    Serial.printf("[RTK] Mesh frag %u/%u alindi (paket_id=%lu)\n",
                  idx + 1, _rtk_asm.toplam, (unsigned long)f->paket_id);

    _rtk_tamamsa_gonder();
}

// ===== ESKİ ESP-NOW BAZLI PAKET İŞLEME (geriye uyumluluk) =====
static inline void rtk_paket_isle(const uint8_t* ham_veri, uint16_t uzunluk) {
    if (uzunluk < sizeof(rtk_paket_t)) {
        Serial.printf("[RTK] HATA: kisa paket (%u byte)\n", uzunluk);
        rtk_kayip++;
        return;
    }

    const rtk_paket_t* p = (const rtk_paket_t*)ham_veri;

    uint16_t hesap_crc = _rtk_crc16(ham_veri, uzunluk - sizeof(uint16_t));
    if (hesap_crc != p->crc) {
        Serial.printf("[RTK] CRC HATASI paket_id=%lu beklenen=%04X gelen=%04X\n",
                      (unsigned long)p->paket_id, hesap_crc, p->crc);
        rtk_kayip++;
        return;
    }

    rtk_alinan++;

    uint32_t simdi = millis();
    if (_rtk_asm.toplam > 0 &&
        (p->paket_id != _rtk_asm.paket_id ||
         (simdi - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS)) {
        Serial.printf("[RTK] TIMEOUT/ID DEGISIM — yeniden baslaniyor\n");
        rtk_kayip++;
        _rtk_asm_sifirla();
    }

    if (p->frag_total == 0 || p->frag_total > RTK_MAX_FRAGS ||
        p->frag_index >= p->frag_total) {
        Serial.printf("[RTK] HATA: gecersiz frag index=%u total=%u\n",
                      p->frag_index, p->frag_total);
        rtk_kayip++;
        return;
    }

    if (_rtk_asm.toplam == 0) {
        _rtk_asm.paket_id = p->paket_id;
        _rtk_asm.toplam   = p->frag_total;
    }

    uint8_t idx = p->frag_index;

    if (_rtk_asm.alinan_maske & (1ull << idx)) {
        Serial.printf("[RTK] Duplikat frag %u, atlaniyor\n", idx);
        return;
    }

    uint16_t offset = (uint16_t)idx * RTK_MAX_PAYLOAD;
    if (offset + RTK_MAX_PAYLOAD > RTK_REASSEMBLY_BUF_SIZE) {
        Serial.printf("[RTK] HATA: buffer tasacak offset=%u\n", offset);
        rtk_kayip++;
        _rtk_asm_sifirla();
        return;
    }

    uint16_t gercek_uzunluk = (p->payload_uzunluk > 0 && p->payload_uzunluk <= RTK_MAX_PAYLOAD)
                             ? p->payload_uzunluk : RTK_MAX_PAYLOAD;
    memcpy(_rtk_asm.buf + offset, p->payload, gercek_uzunluk);
    _rtk_asm.parca_uzunluk[idx] = gercek_uzunluk;
    _rtk_asm.alinan_maske |= (1ull << idx);
    _rtk_asm.son_parca_ms  = simdi;

    Serial.printf("[RTK] Frag %u/%u alindi (paket_id=%lu)\n",
                  idx + 1, _rtk_asm.toplam, (unsigned long)p->paket_id);

    _rtk_tamamsa_gonder();
}

// ===== TIMEOUT KONTROL — loop()'tan çağrılır =====
static inline void rtk_loop(void) {
    if (_rtk_asm.toplam == 0) return;
    if ((millis() - _rtk_asm.son_parca_ms) > RTK_FRAG_TIMEOUT_MS) {
        uint64_t _tam_maske_dbg = (_rtk_asm.toplam >= 64) ? ~0ULL
                                : ((1ull << _rtk_asm.toplam) - 1ull);
        Serial.printf("[RTK] Assembly timeout — paket_id=%lu maske=%016llX/%016llX\n",
                      (unsigned long)_rtk_asm.paket_id,
                      (unsigned long long)_rtk_asm.alinan_maske,
                      (unsigned long long)_tam_maske_dbg);
        rtk_kayip++;
        _rtk_asm_sifirla();
    }
}

static inline void rtk_istatistik_yazdir(void) {
    Serial.printf("[RTK] alinan=%lu kayip=%lu uart_gonderilen=%lu\n",
                  (unsigned long)rtk_alinan,
                  (unsigned long)rtk_kayip,
                  (unsigned long)rtk_uart_gonderilen);
}
