// ADIM 6 — RTK saf mantigi (rtk_pure.h + uart_cobs.h) native unit testleri.
// Arduino/ESP-IDF donanimi GEREKTIRMEZ (pio test -e native).
//
// NOT: bu dosya SADECE rtk_pure.h ve uart_cobs.h'yi include eder — ikisi de
// Arduino.h'ye bagli degil. mesh_config.h/rtk_handler.h/rtk_sender.h (GCM,
// ESP-NOW, Serial) buraya DAHIL EDILMEZ, cunku onlar native'de derlenemez.

#include <unity.h>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "rtk_pure.h"
#include "uart_cobs.h"

// ===== CRC16 TEST VEKTORU (spec 2.1) =====
void test_crc16_test_vektoru(void) {
    const uint8_t veri[] = "123456789";
    TEST_ASSERT_EQUAL_HEX16(0x29B1, cobs_crc16(veri, 9));
}

// ===== COBS ROUND-TRIP (0x00 iceren veriler dahil, 1-1200B rastgele) =====
void test_cobs_roundtrip_rastgele(void) {
    srand(1234);
    for (int deneme = 0; deneme < 300; deneme++) {
        uint16_t uzunluk = 1 + (uint16_t)(rand() % 1200);
        uint8_t giris[1200];
        for (uint16_t i = 0; i < uzunluk; i++) giris[i] = (uint8_t)(rand() % 256);

        uint8_t encoded[1200 + 1200 / 254 + 2];
        uint16_t enc_len = cobs_encode(giris, uzunluk, encoded);
        TEST_ASSERT_TRUE(enc_len > 0);
        TEST_ASSERT_EQUAL_UINT8(0x00, encoded[enc_len - 1]);  // terminator

        uint8_t decoded[1200];
        // cobs_decode terminator HARIC uzunluk bekler (main.cpp'lerdeki
        // kullanimla ayni: byte'lar 0x00'a KADAR biriktirilir, 0x00'in
        // kendisi decode'a verilmez).
        uint16_t dec_len = cobs_decode(encoded, (uint16_t)(enc_len - 1), decoded);
        TEST_ASSERT_EQUAL_UINT16(uzunluk, dec_len);
        TEST_ASSERT_EQUAL_UINT8_ARRAY(giris, decoded, uzunluk);
    }
}

// 0x00 iceren veri icin ozel durum (rastgele testte de olasi ama garanti icin ayrica)
void test_cobs_roundtrip_sifir_iceren(void) {
    uint8_t giris[] = {0x00, 0x01, 0x00, 0x00, 0xFF, 0x00};
    uint16_t uzunluk = sizeof(giris);
    uint8_t encoded[32];
    uint16_t enc_len = cobs_encode(giris, uzunluk, encoded);
    uint8_t decoded[32];
    uint16_t dec_len = cobs_decode(encoded, (uint16_t)(enc_len - 1), decoded);
    TEST_ASSERT_EQUAL_UINT16(uzunluk, dec_len);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(giris, decoded, uzunluk);
}

// ===== CERCEVE KUR/COZ (TIP+ID+payload+crc16_be) =====
void test_cerceve_kur_coz_roundtrip(void) {
    uint8_t payload[18];
    for (int i = 0; i < 18; i++) payload[i] = (uint8_t)(i * 7 + 3);

    uint8_t ham[24], cobs_buf[32];
    uint16_t cobs_len = cobs_cerceve_olustur(0x0C /*TIP_RTK*/, 99 /*BAZ_ID*/, payload, 18, ham, cobs_buf);

    uint8_t decoded[24];
    uint16_t dec_len = cobs_decode(cobs_buf, (uint16_t)(cobs_len - 1), decoded);

    uint8_t tip, id;
    const uint8_t* cozulen_payload;
    uint16_t cozulen_uzunluk;
    bool ok = cobs_cerceve_coz(decoded, dec_len, &tip, &id, &cozulen_payload, &cozulen_uzunluk);
    TEST_ASSERT_TRUE(ok);
    TEST_ASSERT_EQUAL_UINT8(0x0C, tip);
    TEST_ASSERT_EQUAL_UINT8(99, id);
    TEST_ASSERT_EQUAL_UINT16(18, cozulen_uzunluk);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(payload, cozulen_payload, 18);
}

void test_cerceve_coz_bozuk_crc_reddedilir(void) {
    uint8_t payload[4] = {1, 2, 3, 4};
    uint8_t ham[8], cobs_buf[16];
    uint16_t cobs_len = cobs_cerceve_olustur(0x02, 5, payload, 4, ham, cobs_buf);
    uint8_t decoded[8];
    uint16_t dec_len = cobs_decode(cobs_buf, (uint16_t)(cobs_len - 1), decoded);
    decoded[2] ^= 0xFF;  // payload'i boz -> CRC artik tutmamali

    uint8_t tip, id;
    const uint8_t* p; uint16_t plen;
    TEST_ASSERT_FALSE(cobs_cerceve_coz(decoded, dec_len, &tip, &id, &p, &plen));
}

// ===== COBS DECODE — TAMPON TASMASI REGRESYONU (REV B code review) =====
// Gercek bug: rtk_sender.h::rtk_serial_isle() 0x00'a rastlamayan gurultu/
// yanlis-baud girdisini tampon KAPASITESINE kadar biriktiriyor, cobs_decode
// da bu durumda ciktiyi girdi-1'e kadar uretebiliyordu — cikis tamponu
// girdiden kucuk secilmisti, ~3B static overflow olustu (bkz uart_cobs.h
// basindaki KURAL yorumu, rtk_sender.h duzeltmesi).
//
// RTK_COBS_BUF_SIZE Arduino.h'ye bagli rtk_handler.h'de tanimli (native'de
// derlenemez) — ayni formul burada mirrorlanir, gercek uretim tamponuyla
// (_yki_rx_buf) boyutça eslesir.
#define TEST_RTK_HAM_BUF_SIZE   (1 + 1 + RTK_REASSEMBLY_BUF_SIZE + 2)
#define TEST_RTK_COBS_BUF_SIZE  (TEST_RTK_HAM_BUF_SIZE + (TEST_RTK_HAM_BUF_SIZE / 254) + 2)

void test_cobs_decode_gurultu_cikis_tamponunu_asmaz(void) {
    // 0x00 icermeyen, tampon KAPASITESI kadar (production'daki en kotu durum)
    // rastgele "gurultu" girdisi — cokmemeli, ve cikis KURAL geregi (uart_cobs.h)
    // girdiden kisa olmali, boylece cikis>=girdi boyutlu bir tampon guvenli olur.
    srand(4242);
    uint8_t giris[TEST_RTK_COBS_BUF_SIZE];
    for (uint16_t i = 0; i < TEST_RTK_COBS_BUF_SIZE; i++) {
        uint8_t b;
        do { b = (uint8_t)(rand() % 256); } while (b == 0x00);
        giris[i] = b;
    }
    // Kural geregi cikis tamponu >= girdi tamponu — sinirda test (ASan bu
    // sinirin gercekten tutuldugunu dogrular, bkz platformio.ini native env).
    uint8_t cikis[TEST_RTK_COBS_BUF_SIZE];
    uint16_t dec_len = cobs_decode(giris, TEST_RTK_COBS_BUF_SIZE, cikis);
    // NOT: gurultu icin cobs_decode 0 donebilir (grup sinirlari L'e tam
    // oturmuyorsa "bozuk cerceve" olarak reddedilir) — bu GECERLI ve GUVENLI
    // bir sonuctur. Asil kural: cikis HICBIR ZAMAN girdiyi asmaz.
    TEST_ASSERT_TRUE(dec_len < TEST_RTK_COBS_BUF_SIZE);
}

// Ikinci savunma testi: tek bir maksimum boyutta degil, 0xFF kod-grubu
// sinirlarini (254/255/508/509) da kapsayan COK sayida farkli uzunlukta
// gurultu girdisiyle ayni kurali dogrular. std::vector KASITLI: heap
// tamponu tam girdi boyutunda ayrilir, boylece ASan'in heap-redzone'u
// TEK BYTE'lik bir tasmayi bile yakalar (bkz platformio.ini native env
// -fsanitize=address,undefined).
void test_cobs_decode_gurultu_coklu_boyut_tamponu_asmaz(void) {
    srand(777);
    const uint16_t boyutlar[] = {1, 2, 10, 63, 253, 254, 255, 256, 507, 508,
                                  509, 510, 1000, 1527, 1528,
                                  (uint16_t)TEST_RTK_COBS_BUF_SIZE};
    for (uint16_t uzunluk : boyutlar) {
        std::vector<uint8_t> giris(uzunluk);
        for (uint16_t i = 0; i < uzunluk; i++) {
            uint8_t b;
            do { b = (uint8_t)(rand() % 256); } while (b == 0x00);
            giris[i] = b;
        }
        std::vector<uint8_t> cikis(uzunluk);  // tam sinirda — kural: cikis>=girdi
        uint16_t dec_len = cobs_decode(giris.data(), uzunluk, cikis.data());
        TEST_ASSERT_TRUE(dec_len < uzunluk);
    }
}

// ===== FRAGMANTASYON =====
// NOT: bu testler MESH-seviyesi fragmantasyonu (esp_tx->esp_rx, RTK_MAX_FRAGS=8,
// RTK_FRAG_PAYLOAD_MAKS=191 -> ust sinir 1528B) dogruluyor. Spec'in "721B
// ustu dusur" kurali (Bolum 2.5) PI_BRIDGE'in MAVLink 180B/4-fragment
// enjeksiyon katmanina ait, AYRI bir sinirdir — mesh fragmantasyonuyla
// karistirilmamali (HABERLESME gorev talimatindaki "mevcut ust sinir
// mantigiyla tutarli uygula" notu bu yuzden burada RTK_MAX_FRAGS'e gore
// yorumlandi, sabit 720B'e gore degil).
void _frag_test_yardimci(uint16_t uzunluk, uint8_t beklenen_frag_sayisi) {
    uint8_t frag_uzunluklari[RTK_MAX_FRAGS];
    uint8_t toplam = rtk_fragman_hesapla(uzunluk, frag_uzunluklari);
    TEST_ASSERT_EQUAL_UINT8(beklenen_frag_sayisi, toplam);
    uint16_t toplam_uzunluk = 0;
    for (uint8_t i = 0; i < toplam; i++) {
        TEST_ASSERT_TRUE(frag_uzunluklari[i] > 0);
        TEST_ASSERT_TRUE(frag_uzunluklari[i] <= RTK_FRAG_PAYLOAD_MAKS);
        toplam_uzunluk += frag_uzunluklari[i];
    }
    TEST_ASSERT_EQUAL_UINT16(uzunluk, toplam_uzunluk);
}

void test_fragmantasyon_25B(void)  { _frag_test_yardimci(25, 1); }
void test_fragmantasyon_180B(void) { _frag_test_yardimci(180, 1); }
void test_fragmantasyon_200B(void) { _frag_test_yardimci(200, 2); }
void test_fragmantasyon_201B(void) { _frag_test_yardimci(201, 2); }
void test_fragmantasyon_400B(void) { _frag_test_yardimci(400, 3); }
void test_fragmantasyon_720B(void) { _frag_test_yardimci(720, 4); }
void test_fragmantasyon_721B(void) { _frag_test_yardimci(721, 4); }

void test_fragmantasyon_ust_sinir_kabul(void) {
    // RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS = 8*191 = 1528B — tam sinirda kabul edilmeli
    _frag_test_yardimci(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS, RTK_MAX_FRAGS);
}

void test_fragmantasyon_ust_sinir_reddedilir(void) {
    uint8_t frag_uzunluklari[RTK_MAX_FRAGS];
    uint16_t asiri = (uint16_t)(RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS) + 1;
    uint8_t toplam = rtk_fragman_hesapla(asiri, frag_uzunluklari);
    TEST_ASSERT_EQUAL_UINT8(RTK_FRAGMAN_REDDEDILDI, toplam);
}

void test_fragmantasyon_bos_girdi(void) {
    uint8_t frag_uzunluklari[RTK_MAX_FRAGS];
    TEST_ASSERT_EQUAL_UINT8(0, rtk_fragman_hesapla(0, frag_uzunluklari));
}

// ===== REASSEMBLY DURUM MAKINESI =====
void test_reassembly_eksik_fragment_timeout(void) {
    rtk_asm_durum_t a; rtk_asm_sifirla(&a);
    uint8_t payload[10] = {1,2,3,4,5,6,7,8,9,10};
    uint16_t toplam;

    rtk_asm_sonuc_t s = rtk_asm_fragment_isle(&a, 1, 0, 2, 10, payload, 1000, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_DEVAM, s);

    // 500ms timeout dolmadan hala bekliyor olmali
    TEST_ASSERT_FALSE(rtk_asm_timeout_kontrol(&a, 1000 + RTK_FRAG_TIMEOUT_MS));
    TEST_ASSERT_EQUAL_UINT8(2, a.toplam);

    // Timeout dolunca sifirlanmali
    TEST_ASSERT_TRUE(rtk_asm_timeout_kontrol(&a, 1000 + RTK_FRAG_TIMEOUT_MS + 1));
    TEST_ASSERT_EQUAL_UINT8(0, a.toplam);
}

void test_reassembly_msg_id_sicramasi_bufferi_sifirlar(void) {
    rtk_asm_durum_t a; rtk_asm_sifirla(&a);
    uint8_t payload[10] = {0};
    uint16_t toplam;

    // paket_id=1, 2 fragmentlik mesajin sadece 1. parcasi gelir (yarim kalir)
    rtk_asm_fragment_isle(&a, 1, 0, 2, 10, payload, 1000, &toplam);
    TEST_ASSERT_EQUAL_UINT32(1, a.paket_id);
    TEST_ASSERT_EQUAL_UINT32(1u, a.alinan_maske);

    // Farkli paket_id (msg_id sicramasi) gelirse yarim mesaj DUSMELI, yenisi baslamali
    uint8_t payload2[3] = {9, 9, 9};
    rtk_asm_sonuc_t s = rtk_asm_fragment_isle(&a, 2, 0, 1, 3, payload2, 1100, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_TAMAMLANDI, s);  // tek fragmentlik yeni mesaj hemen tamamlanir
    TEST_ASSERT_EQUAL_UINT32(2, a.paket_id);
    TEST_ASSERT_EQUAL_UINT16(3, toplam);
}

void test_reassembly_duplicate_fragment_atlanir(void) {
    rtk_asm_durum_t a; rtk_asm_sifirla(&a);
    uint8_t payload[10] = {0};
    uint16_t toplam;

    rtk_asm_fragment_isle(&a, 1, 0, 2, 10, payload, 1000, &toplam);
    rtk_asm_sonuc_t s = rtk_asm_fragment_isle(&a, 1, 0, 2, 10, payload, 1010, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_DUPLIKAT, s);
    TEST_ASSERT_EQUAL_UINT32(1u, a.alinan_maske);  // maske degismedi
}

void test_reassembly_sira_disi_gelis_dogru_birlesir(void) {
    rtk_asm_durum_t a; rtk_asm_sifirla(&a);
    uint8_t p0[5] = {1,2,3,4,5};
    uint8_t p1[5] = {6,7,8,9,10};
    uint16_t toplam;

    // Once frag 1, SONRA frag 0 gelir
    rtk_asm_sonuc_t s1 = rtk_asm_fragment_isle(&a, 1, 1, 2, 5, p1, 1000, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_DEVAM, s1);
    rtk_asm_sonuc_t s2 = rtk_asm_fragment_isle(&a, 1, 0, 2, 5, p0, 1001, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_TAMAMLANDI, s2);
    TEST_ASSERT_EQUAL_UINT16(10, toplam);

    // Buf'ta offset'e gore DOGRU sirada olmali (varis sirasina gore degil)
    TEST_ASSERT_EQUAL_UINT8_ARRAY(p0, a.buf + 0 * RTK_FRAG_PAYLOAD_MAKS, 5);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(p1, a.buf + 1 * RTK_FRAG_PAYLOAD_MAKS, 5);
}

void test_reassembly_gecersiz_fragment_reddedilir(void) {
    rtk_asm_durum_t a; rtk_asm_sifirla(&a);
    uint8_t payload[5] = {0};
    uint16_t toplam;

    // frag_index >= frag_total -> gecersiz
    TEST_ASSERT_EQUAL(RTK_ASM_REDDEDILDI,
        rtk_asm_fragment_isle(&a, 1, 2, 2, 5, payload, 1000, &toplam));
    // frag_total 0 -> gecersiz
    TEST_ASSERT_EQUAL(RTK_ASM_REDDEDILDI,
        rtk_asm_fragment_isle(&a, 1, 0, 0, 5, payload, 1000, &toplam));
    // frag_uzunluk RTK_FRAG_PAYLOAD_MAKS'i asiyor -> gecersiz
    TEST_ASSERT_EQUAL(RTK_ASM_REDDEDILDI,
        rtk_asm_fragment_isle(&a, 1, 0, 1, RTK_FRAG_PAYLOAD_MAKS + 1, payload, 1000, &toplam));
}

int main(int argc, char** argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();
    RUN_TEST(test_crc16_test_vektoru);
    RUN_TEST(test_cobs_roundtrip_rastgele);
    RUN_TEST(test_cobs_roundtrip_sifir_iceren);
    RUN_TEST(test_cerceve_kur_coz_roundtrip);
    RUN_TEST(test_cerceve_coz_bozuk_crc_reddedilir);
    RUN_TEST(test_cobs_decode_gurultu_cikis_tamponunu_asmaz);
    RUN_TEST(test_cobs_decode_gurultu_coklu_boyut_tamponu_asmaz);
    RUN_TEST(test_fragmantasyon_25B);
    RUN_TEST(test_fragmantasyon_180B);
    RUN_TEST(test_fragmantasyon_200B);
    RUN_TEST(test_fragmantasyon_201B);
    RUN_TEST(test_fragmantasyon_400B);
    RUN_TEST(test_fragmantasyon_720B);
    RUN_TEST(test_fragmantasyon_721B);
    RUN_TEST(test_fragmantasyon_ust_sinir_kabul);
    RUN_TEST(test_fragmantasyon_ust_sinir_reddedilir);
    RUN_TEST(test_fragmantasyon_bos_girdi);
    RUN_TEST(test_reassembly_eksik_fragment_timeout);
    RUN_TEST(test_reassembly_msg_id_sicramasi_bufferi_sifirlar);
    RUN_TEST(test_reassembly_duplicate_fragment_atlanir);
    RUN_TEST(test_reassembly_sira_disi_gelis_dogru_birlesir);
    RUN_TEST(test_reassembly_gecersiz_fragment_reddedilir);
    return UNITY_END();
}
