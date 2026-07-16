#pragma once
// ===== RTK — ARDUINO'DAN BAGIMSIZ SAF MANTIK (ADIM 6) =====
// Bu dosya HICBIR Arduino/ESP-IDF sembolune (Serial, millis, HardwareSerial,
// esp_now_*, mbedtls_*) bagli DEGILDIR — sadece <stdint.h>/<string.h>
// kullanir. Boylece PlatformIO'nun "native" ortaminda (host makinede,
// donanimsiz) derlenip test edilebilir (bkz test/native/).
//
// rtk_handler.h ve rtk_sender.h (Arduino tarafi) bu dosyadaki sabitleri VE
// fonksiyonlari kullanir — mantik burada TEK YERDE yasar, Arduino tarafi
// sadece ince bir kabuk (GCM sifreleme, ESP-NOW gonderim, Serial loglama).

#include <stdint.h>
#include <string.h>
#include <stddef.h>   // offsetof — asagidaki sozlesme static_assert'i icin

// ===== BUYUK RTK ZARFI — BYTE BUTCESI (bkz rtk_handler.h basindaki yorum) =====
//   RTK_ENV_ONSOZ_BOYUTU  = 30  (kaynak_mac6+hedef_mac6+paket_id4+atlama_sayisi1+tip1+iv12)
//   RTK_ENV_TAG_BOYUTU    = 16  (GCM auth tag)
//   RTK_ENV_SABIT_TOPLAM  = 46
//   RTK_ENV_MAKS_TOPLAM   = 250 (ESP-NOW donanim siniri — TEK KAYNAK BURASI;
//                                 mesh_config.h bu header'i include eder, orada
//                                 duplike TANIMLAMA. Eskiden iki kopyaydi ve bu
//                                 satir "eslesmeli" diyordu; ADIM 6 duplikasyonu
//                                 kaldirdi, uyari da onunla birlikte dusmeliydi.)
//   RTK_ENV_MAKS_SIFRELI  = 250 - 46 = 204
//   RTK_ANTI_REPLAY_BOYUTU = 6  (anti_replay_t: session_id2+paket_id4)
//   RTK_FRAG_HEADER_BOYUTU = 7  (msg_id4+idx1+total1+len1)
//   RTK_FRAG_PAYLOAD_MAKS  = 204 - 6 - 7 = 191
#define RTK_ENV_MAKS_TOPLAM     250
#define RTK_ENV_ONSOZ_BOYUTU    30
#define RTK_ENV_TAG_BOYUTU      16
#define RTK_ENV_SABIT_TOPLAM    (RTK_ENV_ONSOZ_BOYUTU + RTK_ENV_TAG_BOYUTU)
#define RTK_ENV_MAKS_SIFRELI    (RTK_ENV_MAKS_TOPLAM - RTK_ENV_SABIT_TOPLAM)
#define RTK_ANTI_REPLAY_BOYUTU  6
#define RTK_FRAG_HEADER_BOYUTU  7
#define RTK_FRAG_PAYLOAD_MAKS   (RTK_ENV_MAKS_SIFRELI - RTK_ANTI_REPLAY_BOYUTU - RTK_FRAG_HEADER_BOYUTU) // 191

// ===== IKI FARKLI ISTE CALISAN IKI ASSERT — IKISI DE KALMALI =====
// (1) GUVENLIK TABANI: mutlak alt sinir. Payload bunun altina duserse
//     tasarim MAVLink enjeksiyon uyumunu kaybeder.
static_assert(RTK_FRAG_PAYLOAD_MAKS >= 180,
              "RTK_FRAG_PAYLOAD_MAKS 180'in altina dustu - zarf hesabini kontrol et");

// (2) SOZLESME KILIDI: spec §2.3 byte butcesi (250-46-6-7=191).
//     Bu assert patlarsa YAPILACAK SEY SAYIYI DUZELTMEK DEGILDIR:
//     zarf yapisi degismis demektir -> docs/YELPENCE_RTCM_SPEC.md §2.3'u
//     (layout tablosu + byte butcesi dokumu) GUNCELLE ve YKİ/pi_bridge
//     ekibine haber ver; ancak ondan sonra bu sayiyi degistir.
static_assert(RTK_FRAG_PAYLOAD_MAKS == 191,
              "Zarf byte butcesi degisti: spec §2.3 senkronu gerekli! "
              "Sayiyi duzeltmeden once docs/YELPENCE_RTCM_SPEC.md §2.3'u "
              "guncelle ve YKİ/pi_bridge'e bildir.");

// (3) numarali sozlesme kilidi rtk_mesh_frag_t tanimindan HEMEN SONRA
//     (struct'in kendisi asagida tanimlaniyor, offsetof once cagrilmaz).

// REV B: 8 fragment x 191B = 1528B, MSM4/720B MAVLink tavanina bol marj.
#define RTK_MAX_FRAGS            8
// 8 x 191B = 1528B en kotu durumu karsilayacak sekilde 1600'e yuvarlandi.
#define RTK_REASSEMBLY_BUF_SIZE  1600
#define RTK_FRAG_TIMEOUT_MS      500UL

// ===== MESH FRAGMENT YAPISI (Arduino'dan bagimsiz, saf POD struct) =====
#ifndef RTK_MESH_FRAG_DEFINED
#define RTK_MESH_FRAG_DEFINED
typedef struct
#if defined(__GNUC__)
__attribute__((packed))
#endif
{
    uint32_t paket_id;               // msg_id
    uint8_t  frag_index;
    uint8_t  frag_total;
    uint8_t  frag_uzunluk;           // gercek veri byte sayisi (1..RTK_FRAG_PAYLOAD_MAKS)
    uint8_t  payload[RTK_FRAG_PAYLOAD_MAKS];
} rtk_mesh_frag_t;

// (3) SOZLESME KILIDI — yukaridaki (2)'nin KOR NOKTASI:
//     RTK_FRAG_HEADER_BOYUTU ciplak bir literal (7); rtk_handler.h ise
//     memcpy(plaintext + RTK_ANTI_REPLAY_BOYUTU, frag, RTK_FRAG_HEADER_BOYUTU)
//     ile frag basligini bu literale gore kopyaliyor. rtk_mesh_frag_t'ye alan
//     eklenir/genisletilirse memcpy sessizce KIRPAR ve tel formati bozulur —
//     ustelik RTK_FRAG_PAYLOAD_MAKS degismedigi icin (2) numarali assert
//     PATLAMAZ. Yani ic alanlar kayarken toplam sabit kalabilir; bu assert
//     tam o senaryo icin var.
//     Patlarsa: sayiyi duzeltme — spec §2.3 layout tablosunu guncelle ve
//     YKİ/pi_bridge'e bildir.
static_assert(offsetof(rtk_mesh_frag_t, payload) == RTK_FRAG_HEADER_BOYUTU,
              "rtk_mesh_frag_t basligi RTK_FRAG_HEADER_BOYUTU ile uyumsuz: "
              "rtk_handler.h'deki memcpy sessizce kirpar. Spec §2.3 layout "
              "tablosunu guncelle ve ekibe bildir.");
#endif

// ===== SAF FRAGMANTASYON HESABI =====
// uzunluk byte'lik bir mesaji RTK_FRAG_PAYLOAD_MAKS'lik parcalara boler.
// frag_uzunluklari_out en az RTK_MAX_FRAGS eleman almali. Donus degeri
// fragment sayisi (0 = bos girdi, 0xFF = RTK_MAX_FRAGS'i asiyor, reddedildi).
#define RTK_FRAGMAN_REDDEDILDI 0xFF
static inline uint8_t rtk_fragman_hesapla(uint16_t uzunluk, uint8_t* frag_uzunluklari_out) {
    if (uzunluk == 0) return 0;
    // Parca sayisi uint16'da tutulup OYLE sinanir. (uint8_t) cast'i sinamadan
    // ONCE yapilirsa 256'nin katlarinda taban kaybolur: 257 parca -> (uint8_t)257
    // == 1, yani asagidaki "> RTK_MAX_FRAGS" kapisi SESSIZCE gecilir ve ~49KB'lik
    // bir mesaj tek parcaya kirpilir. Bugun cagiran taraf uzunlugu <=1029'a
    // sabitledigi icin erisilemiyor (bkz rtk_sender.h'deki ispat), ama kapi
    // "buyuk girdiyi reddet" diye YAZILMIS durumda ve o isi tum uint16 araliginda
    // yapmiyordu -- olu kod degil, hatali kod.
    uint16_t frag_toplam16 = (uint16_t)((uzunluk + (RTK_FRAG_PAYLOAD_MAKS - 1)) / RTK_FRAG_PAYLOAD_MAKS);
    if (frag_toplam16 == 0 || frag_toplam16 > RTK_MAX_FRAGS) return RTK_FRAGMAN_REDDEDILDI;
    uint8_t frag_toplam = (uint8_t)frag_toplam16;
    for (uint8_t i = 0; i < frag_toplam; i++) {
        uint16_t offset = (uint16_t)i * RTK_FRAG_PAYLOAD_MAKS;
        uint16_t kalan  = uzunluk - offset;
        frag_uzunluklari_out[i] = (kalan >= RTK_FRAG_PAYLOAD_MAKS)
                                 ? (uint8_t)RTK_FRAG_PAYLOAD_MAKS : (uint8_t)kalan;
    }
    return frag_toplam;
}

// ===== SAF REASSEMBLY DURUM MAKINESI =====
typedef struct {
    uint32_t paket_id;
    uint8_t  toplam;
    uint32_t alinan_maske;
    uint8_t  buf[RTK_REASSEMBLY_BUF_SIZE];
    uint16_t parca_uzunluk[RTK_MAX_FRAGS];
    uint32_t son_parca_ms;
} rtk_asm_durum_t;

typedef enum {
    RTK_ASM_REDDEDILDI = 0,  // gecersiz fragment (index/total/uzunluk)
    RTK_ASM_DUPLIKAT,        // zaten alinmis fragment, atlandi
    RTK_ASM_DEVAM,           // fragment kabul edildi, mesaj henuz tam degil
    RTK_ASM_TASTI,           // toplam_uzunluk RTK_REASSEMBLY_BUF_SIZE'i asti
    RTK_ASM_TAMAMLANDI       // fragment kabul edildi, mesaj TAMAMLANDI
} rtk_asm_sonuc_t;

static inline void rtk_asm_sifirla(rtk_asm_durum_t* a) {
    memset(a, 0, sizeof(*a));
}

// simdi_ms: cagiran taraf saglar (Arduino'da millis(), testte elle verilir).
// toplam_uzunluk_out: sadece RTK_ASM_TAMAMLANDI doneminde gecerli deger alir.
static inline rtk_asm_sonuc_t rtk_asm_fragment_isle(
        rtk_asm_durum_t* a, uint32_t paket_id, uint8_t frag_index, uint8_t frag_total,
        uint8_t frag_uzunluk, const uint8_t* payload, uint32_t simdi_ms,
        uint16_t* toplam_uzunluk_out) {
    if (frag_total == 0 || frag_total > RTK_MAX_FRAGS || frag_index >= frag_total)
        return RTK_ASM_REDDEDILDI;
    if (frag_uzunluk == 0 || frag_uzunluk > RTK_FRAG_PAYLOAD_MAKS)
        return RTK_ASM_REDDEDILDI;

    // Farkli paket_id ya da timeout → sifirla, yeni mesaja basla
    if (a->toplam > 0 &&
        (paket_id != a->paket_id || (simdi_ms - a->son_parca_ms) > RTK_FRAG_TIMEOUT_MS)) {
        rtk_asm_sifirla(a);
    }
    if (a->toplam == 0) {
        a->paket_id = paket_id;
        a->toplam   = frag_total;
    }

    if (a->alinan_maske & (1u << frag_index))
        return RTK_ASM_DUPLIKAT;

    uint16_t offset = (uint16_t)frag_index * RTK_FRAG_PAYLOAD_MAKS;
    if (offset + RTK_FRAG_PAYLOAD_MAKS > RTK_REASSEMBLY_BUF_SIZE) {
        rtk_asm_sifirla(a);
        return RTK_ASM_TASTI;
    }

    memcpy(a->buf + offset, payload, frag_uzunluk);
    a->parca_uzunluk[frag_index] = frag_uzunluk;
    a->alinan_maske             |= (1u << frag_index);
    a->son_parca_ms              = simdi_ms;

    uint32_t tam_maske = (1u << a->toplam) - 1u;
    if (a->alinan_maske != tam_maske)
        return RTK_ASM_DEVAM;

    uint16_t toplam = 0;
    for (uint8_t i = 0; i < a->toplam; i++) toplam += a->parca_uzunluk[i];
    if (toplam > RTK_REASSEMBLY_BUF_SIZE) {
        rtk_asm_sifirla(a);
        return RTK_ASM_TASTI;
    }
    if (toplam_uzunluk_out) *toplam_uzunluk_out = toplam;
    return RTK_ASM_TAMAMLANDI;
}

// true donerse timeout nedeniyle sifirlandi demektir.
static inline bool rtk_asm_timeout_kontrol(rtk_asm_durum_t* a, uint32_t simdi_ms) {
    if (a->toplam == 0) return false;
    if ((simdi_ms - a->son_parca_ms) > RTK_FRAG_TIMEOUT_MS) {
        rtk_asm_sifirla(a);
        return true;
    }
    return false;
}
