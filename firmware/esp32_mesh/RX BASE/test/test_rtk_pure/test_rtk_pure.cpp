// RTK saf mantigi (rtk_pure.h + uart_cobs.h) native unit testleri.
// Arduino/ESP-IDF donanimi gerektirmez (pio test -e native).
//
// Bu dosya sadece rtk_pure.h ve uart_cobs.h'yi include eder (ikisi de Arduino.h'ye
// bagli degil). mesh_config.h/rtk_handler.h/rtk_sender.h (GCM, ESP-NOW, Serial)
// native'de derlenemedigi icin dahil edilmez.

#include <unity.h>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "rtk_pure.h"
#include "uart_cobs.h"
#include "uart_frame_parser.h"   // desync regresyon testleri

// CRC16 test vektoru (spec 2.1).
void test_crc16_test_vektoru(void) {
    const uint8_t veri[] = "123456789";
    TEST_ASSERT_EQUAL_HEX16(0x29B1, cobs_crc16(veri, 9));
}

// COBS round-trip (0x00 iceren veriler dahil, 1-1200B rastgele).
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
        // cobs_decode terminator haric uzunluk bekler (main.cpp'lerdeki
        // kullanimla ayni: byte'lar 0x00'a kadar biriktirilir, 0x00'in kendisi
        // decode'a verilmez).
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

// Cerceve kur/coz (TIP+ID+payload+crc16_be).
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

// COBS decode: tampon tasmasi regresyonu.
// rtk_serial_isle() 0x00'a rastlamayan gurultu/yanlis-baud girdisini tampon
// kapasitesine kadar biriktirebilir; cobs_decode bu durumda ciktiyi girdi-1'e
// kadar uretebilir. Cikis tamponu girdiden kucuk secilirse static overflow olur
// (bkz uart_cobs.h basindaki kural).
//
// RTK_COBS_BUF_SIZE Arduino.h'ye bagli rtk_handler.h'de tanimli (native'de
// derlenemez), ayni formul burada mirrorlanir ve gercek uretim tamponuyla
// (_yki_rx_buf) boyutca eslesir.
#define TEST_RTK_HAM_BUF_SIZE   (1 + 1 + RTK_REASSEMBLY_BUF_SIZE + 2)
#define TEST_RTK_COBS_BUF_SIZE  (TEST_RTK_HAM_BUF_SIZE + (TEST_RTK_HAM_BUF_SIZE / 254) + 2)

void test_cobs_decode_gurultu_cikis_tamponunu_asmaz(void) {
    // 0x00 icermeyen, tampon kapasitesi kadar (en kotu durum) rastgele gurultu
    // girdisi: cokmemeli ve cikis kural geregi (uart_cobs.h) girdiden kisa olmali,
    // boylece cikis>=girdi boyutlu bir tampon guvenli olur.
    srand(4242);
    uint8_t giris[TEST_RTK_COBS_BUF_SIZE];
    for (uint16_t i = 0; i < TEST_RTK_COBS_BUF_SIZE; i++) {
        uint8_t b;
        do { b = (uint8_t)(rand() % 256); } while (b == 0x00);
        giris[i] = b;
    }
    // Kural geregi cikis tamponu >= girdi tamponu; sinirda test (ASan bu sinirin
    // gercekten tutuldugunu dogrular).
    uint8_t cikis[TEST_RTK_COBS_BUF_SIZE];
    uint16_t dec_len = cobs_decode(giris, TEST_RTK_COBS_BUF_SIZE, cikis);
    // Gurultu icin cobs_decode 0 donebilir (grup sinirlari tam oturmuyorsa bozuk
    // cerceve olarak reddedilir); bu gecerli ve guvenli. Asil kural: cikis hicbir
    // zaman girdiyi asmaz.
    TEST_ASSERT_TRUE(dec_len < TEST_RTK_COBS_BUF_SIZE);
}

// Ikinci savunma testi: tek boyut degil, 0xFF kod-grubu sinirlarini
// (254/255/508/509) da kapsayan cok sayida farkli uzunlukta gurultu girdisiyle
// ayni kurali dogrular. std::vector kasitli: heap tamponu tam girdi boyutunda
// ayrilir, boylece ASan'in heap-redzone'u tek byte'lik bir tasmayi bile yakalar.
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
        std::vector<uint8_t> cikis(uzunluk);  // tam sinirda, kural: cikis>=girdi
        uint16_t dec_len = cobs_decode(giris.data(), uzunluk, cikis.data());
        TEST_ASSERT_TRUE(dec_len < uzunluk);
    }
}

// UART cerceve ayristirici: desync regresyonu.
// whitelist-disi bir tip gelince "break" ile okuma dongusunu kirip idx=0'i
// atlamak, reddedilen bir cerceveyi bir sonrakini index kaydirarak bozardi.
// Framing artik uart_frame_parser.h'de saf/testli ve "break"siz; bu testler o
// garantiyi dogrular.

// Bir cerceveyi (COBS + 0x00 terminatoru dahil) bayt bayt besler; tamamlanan son
// cerceveyi cikislara yazar, kac cerceve tamamlandigini doner.
static int _besle(uart_frame_parser_t* st, const uint8_t* cerceve, uint16_t n,
                  uint8_t* tip_out, uint8_t* id_out,
                  uint8_t* payload_kopya, uint16_t* plen_out) {
    int tamamlanan = 0;
    for (uint16_t i = 0; i < n; i++) {
        uint8_t tip, id; const uint8_t* p; uint16_t plen;
        if (uart_frame_parser_push(st, cerceve[i], &tip, &id, &p, &plen)) {
            tamamlanan++;
            if (tip_out) *tip_out = tip;
            if (id_out)  *id_out  = id;
            if (plen_out) *plen_out = plen;
            if (payload_kopya && plen) memcpy(payload_kopya, p, plen);
        }
    }
    return tamamlanan;
}

// Bir cerceve insa et: COBS(tip+id+payload+crc16_be) + 0x00. cobs_len cikisi
// terminator dahil toplam uzunluk.
static void _cerceve_yap(uint8_t tip, uint8_t id, const uint8_t* payload,
                         uint16_t plen, uint8_t* cikis, uint16_t* cikis_len) {
    uint8_t ham[64], cobs[80];
    uint16_t clen = cobs_cerceve_olustur(tip, id, payload, plen, ham, cobs);
    memcpy(cikis, cobs, clen);
    *cikis_len = clen;   // cobs_cerceve_olustur zaten 0x00 terminatorunu ekliyor
}

void test_frame_parser_tek_cerceve_roundtrip(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    uint8_t payload[16]; for (int i = 0; i < 16; i++) payload[i] = (uint8_t)(i + 1);
    uint8_t cerceve[80]; uint16_t clen;
    _cerceve_yap(0x02 /*TIP_KOMUT*/, 7, payload, 16, cerceve, &clen);

    uint8_t tip, id, pk[32]; uint16_t plen;
    int n = _besle(&st, cerceve, clen, &tip, &id, pk, &plen);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_EQUAL_UINT8(0x02, tip);
    TEST_ASSERT_EQUAL_UINT8(7, id);
    TEST_ASSERT_EQUAL_UINT16(16, plen);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(payload, pk, 16);
}

void test_frame_parser_arka_arkaya_iki_cerceve(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    uint8_t pa[4] = {1,2,3,4}, pb[4] = {9,8,7,6};
    uint8_t ca[80], cb[80]; uint16_t la, lb;
    _cerceve_yap(0x02, 1, pa, 4, ca, &la);
    _cerceve_yap(0x05, 2, pb, 4, cb, &lb);

    uint8_t tip, id, pk[32]; uint16_t plen;
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, ca, la, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x02, tip);
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, cb, lb, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x05, tip);
    TEST_ASSERT_EQUAL_UINT8(2, id);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pb, pk, 4);
}

// Desync regresyonu 1: bozuk-CRC bir cerceve reddedilir, ardindan gelen gecerli
// cerceve dogru parse edilmeli (idx dogru sifirlandi).
void test_frame_parser_bozuk_cerceve_sonrasi_gecerli_parse_edilir(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    uint8_t pg[4] = {1,2,3,4};
    uint8_t cg[80]; uint16_t lg;
    _cerceve_yap(0x02, 1, pg, 4, cg, &lg);

    // Bozuk cerceve: gecerliyi al, CRC'yi boz (COBS icinde bir bayti degistir),
    // yine 0x00 ile bitir.
    uint8_t bozuk[80]; uint16_t lb;
    _cerceve_yap(0x02, 1, pg, 4, bozuk, &lb);
    bozuk[1] ^= 0xFF;   // ilk veri baytini boz -> CRC tutmaz

    uint8_t tip, id, pk[32]; uint16_t plen;
    // Bozuk cerceve: 0 tamamlanmis cerceve (CRC reddi)
    TEST_ASSERT_EQUAL_INT(0, _besle(&st, bozuk, lb, &tip, &id, pk, &plen));
    // Ardindan gecerli cerceve: idx sifirlandigi icin dogru parse edilmeli
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, cg, lg, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x02, tip);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pg, pk, 4);
}

// Desync regresyonu 2: consumer (whitelist) bir cerceveyi "istenmeyen tip" diye
// reddedip hicbir sey yapmasa bile, bir sonraki gecerli cerceve etkilenmemeli.
// Framing whitelist'ten bagimsiz oldugu icin bu yapisal garanti; test belgeler.
void test_frame_parser_istenmeyen_tip_sonraki_komutu_bozmaz(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    // Whitelist-disi bir tip tasiyan gecerli cerceve (or. TIP_VERSION=0x0B)
    uint8_t pv[4] = {0xAA,0xBB,0xCC,0xDD};
    uint8_t cv[80]; uint16_t lv;
    _cerceve_yap(0x0B /*TIP_VERSION*/, 1, pv, 4, cv, &lv);
    // Ardindan gercek joystick komutu (TIP_KOMUT)
    uint8_t pk_in[16]; for (int i = 0; i < 16; i++) pk_in[i] = (uint8_t)(0x10 + i);
    uint8_t ck[80]; uint16_t lk;
    _cerceve_yap(0x02 /*TIP_KOMUT*/, 1, pk_in, 16, ck, &lk);

    uint8_t tip, id, pk[32]; uint16_t plen;
    // Istenmeyen tip: parser acisindan gecerli cerceve (1 tamamlanir); consumer
    // whitelist'te reddederdi ama bu parser durumunu etkilemez.
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, cv, lv, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x0B, tip);
    // Sonraki KOMUT bozulmadan gelmeli
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, ck, lk, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x02, tip);
    TEST_ASSERT_EQUAL_UINT16(16, plen);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pk_in, pk, 16);
}

// Desync regresyonu 3: 0x00 icermeyen tasma-boyu gurultu + terminator, ardindan
// gecerli cerceve resync olmali.
void test_frame_parser_tasma_gurultu_sonrasi_resync(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    // UART_FRAME_BUF_SIZE'dan fazla, 0x00 icermeyen gurultu
    uint8_t gurultu[UART_FRAME_BUF_SIZE * 2];
    srand(31337);
    for (uint16_t i = 0; i < sizeof(gurultu); i++) {
        uint8_t b; do { b = (uint8_t)(rand() % 256); } while (b == 0x00);
        gurultu[i] = b;
    }
    uint8_t tip, id, pk[32]; uint16_t plen;
    _besle(&st, gurultu, sizeof(gurultu), &tip, &id, pk, &plen);  // cokmemeli
    uint8_t term = 0x00;
    _besle(&st, &term, 1, &tip, &id, pk, &plen);  // gurultu cercevesini kapat/at

    uint8_t pg[4] = {5,6,7,8};
    uint8_t cg[80]; uint16_t lg;
    _cerceve_yap(0x05, 3, pg, 4, cg, &lg);
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, cg, lg, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x05, tip);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pg, pk, 4);
}

// Kismi cerceve loop()/paket sinirini gecebilmeli: ayni cerceve iki ayri besleme
// cagrisina bolunse de dogru birlesmeli (static durum korunur).
void test_frame_parser_bolunmus_cerceve_birlesir(void) {
    uart_frame_parser_t st; uart_frame_parser_sifirla(&st);
    uint8_t pg[16]; for (int i = 0; i < 16; i++) pg[i] = (uint8_t)(i * 3 + 1);
    uint8_t cg[80]; uint16_t lg;
    _cerceve_yap(0x02, 9, pg, 16, cg, &lg);

    uint8_t tip, id, pk[32]; uint16_t plen;
    uint16_t yari = lg / 2;
    // Ilk yari: henuz cerceve tamamlanmamali
    TEST_ASSERT_EQUAL_INT(0, _besle(&st, cg, yari, &tip, &id, pk, &plen));
    // Ikinci yari (terminator dahil): simdi tamamlanmali
    TEST_ASSERT_EQUAL_INT(1, _besle(&st, cg + yari, lg - yari, &tip, &id, pk, &plen));
    TEST_ASSERT_EQUAL_UINT8(0x02, tip);
    TEST_ASSERT_EQUAL_UINT8(9, id);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(pg, pk, 16);
}

// Tehdit: saldirgan RF'i yakalar, gonderici reboot edene kadar bekler, sonra
// eski session'in (authenticated ama eski) paketlerini tekrar oynatir.
// "session_id farkli -> reboot varsay, pencereyi sifirla, kabul" deseydik saldiri
// islerdi. Kural: session_id monoton, kucuk olan reddedilir. Alici yarisi
// (kalici_session) olmadan kural kagit uzerinde kalir, o yuzden ayrica test edilir.

// Cekirdek regresyon: alici reboot etti (RAM durumu yok, ilk_paket=true) ama
// NVS'te peer'in son session'i duruyor. Saldirgan eski session'i oynatiyor.
// Ayni senaryo ama kalici kayit yoksa (alici yarisi atlanmis olsaydi) saldiri
// gecerdi. Bu test alici-persist yarisinin neden sart oldugunu belgeliyor:
// kalici=0 iken ayni eski paket kabul ediliyor.
// Fragmantasyon.
// Bu testler mesh-seviyesi fragmantasyonu (RTK_MAX_FRAGS=8,
// RTK_FRAG_PAYLOAD_MAKS=238 -> ust sinir 1904B) dogruluyor. Parca boyutu
// sifreleme kaldirilinca 191'den 238'e cikti (zarf 47 bayt kuculdu), bu
// yuzden sinir testleri 238/239'a tasindi. Spec'in "721B ustu
// dusur" kurali (Bolum 2.5) pi_bridge'in MAVLink enjeksiyon katmanina ait ayri
// bir sinirdir, mesh fragmantasyonuyla karistirilmamali.
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
void test_fragmantasyon_238B(void) { _frag_test_yardimci(238, 1); }   // tam bir parca
void test_fragmantasyon_239B(void) { _frag_test_yardimci(239, 2); }   // bir bayt tasar
void test_fragmantasyon_400B(void) { _frag_test_yardimci(400, 2); }
void test_fragmantasyon_720B(void) { _frag_test_yardimci(720, 4); }   // tipik MSM4
void test_fragmantasyon_721B(void) { _frag_test_yardimci(721, 4); }
void test_fragmantasyon_1029B(void){ _frag_test_yardimci(1029, 5); }  // en buyuk RTCM3

void test_fragmantasyon_ust_sinir_kabul(void) {
    // RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS = 8*238 = 1904B, tam sinirda kabul edilmeli
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

// Reassembly durum makinesi.
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
    uint16_t toplam;

    // Uretim sekilli veri: gonderici son parca haric hep tam parca uretir
    // (rtk_fragman_hesapla), yani "bir tam parca + 57B artik".
    // Uzunluk RTK_FRAG_PAYLOAD_MAKS'tan TURETILIYOR; sabit yazilsaydi parca
    // boyutu her degistiginde (191 -> 238 gibi) bu test kirilirdi.
    const uint16_t MESAJ_UZUNLUK = RTK_FRAG_PAYLOAD_MAKS + 57;
    uint8_t mesaj[MESAJ_UZUNLUK];
    for (uint16_t i = 0; i < MESAJ_UZUNLUK; i++) mesaj[i] = (uint8_t)(i * 7 + 1);

    uint8_t lens[RTK_MAX_FRAGS];
    TEST_ASSERT_EQUAL_UINT8(2, rtk_fragman_hesapla(MESAJ_UZUNLUK, lens));
    TEST_ASSERT_EQUAL_UINT8(RTK_FRAG_PAYLOAD_MAKS, lens[0]);  // ara parca tam
    TEST_ASSERT_EQUAL_UINT8(57, lens[1]);                     // son parca kisa

    // Once frag 1, sonra frag 0 gelir
    rtk_asm_sonuc_t s1 = rtk_asm_fragment_isle(&a, 1, 1, 2, lens[1],
                             mesaj + RTK_FRAG_PAYLOAD_MAKS, 1000, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_DEVAM, s1);
    rtk_asm_sonuc_t s2 = rtk_asm_fragment_isle(&a, 1, 0, 2, lens[0],
                             mesaj, 1001, &toplam);
    TEST_ASSERT_EQUAL(RTK_ASM_TAMAMLANDI, s2);
    TEST_ASSERT_EQUAL_UINT16(MESAJ_UZUNLUK, toplam);

    // Asil iddia: Pi'ye teslim edilen dilim, varis sirasindan bagimsiz olarak
    // orijinal mesajin aynisi olmali. Yerlesimi kontrol etmek yetmez.
    TEST_ASSERT_EQUAL_UINT8_ARRAY(mesaj, a.buf, toplam);
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

// Bu kesisim daha once "analizle guvenli, testle degil" diye isaretlenmisti;
// burasi o cumleyi kanita ceviriyor.
//
// Modellenen mimari:
// testlerinde ilgilenilen sey session/pencere etkilesimi, NVS degil).
// RTK burst'u + genel mesh trafigi TEK sayactan besleniyor; iki ring buffer
// sirasiz bosaldigi icin alici bunlari karisik sirada goruyor. Hicbir mesru
// paket kaybolmamali.
// Kayma tam sinirda (24 = 8+16 buffer derinligi): en kotu durumda bile
// pencere (64) hepsini soğurmali. Bu test PENCERE_BOYU kucultulurse patlar.
// SESSION DEGISIMI ANI: gonderici reboot etti (session 1 -> 2) ve _paket_sayaci
// 0'dan yeniden basladi. Alicinin iki buffer'i hala ESKI session'in paketlerini
// tasiyor olabilir. Yeni session'in kucuk paket_id'leri kabul edilmeli; eski
// session'in paketleri ise (buffer'da kalmis olsalar bile) REDDEDILMELI.
// RTK burst'u tam session degisimine denk gelirse: ayni RTCM mesajinin
// fragmentlari reboot'a bolunemez (gonderici reboot ederse burst zaten olur),
// ama alicinin buffer'inda eski session fragmentleri KALABILIR. Reassembly'nin
// Duplikat, kesisimde de tutmali: RTK fragmenti iki kez islenirse (ISR ring
// buffer'i + retry) ikincisi reddedilmeli.
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
    RUN_TEST(test_frame_parser_tek_cerceve_roundtrip);
    RUN_TEST(test_frame_parser_arka_arkaya_iki_cerceve);
    RUN_TEST(test_frame_parser_bozuk_cerceve_sonrasi_gecerli_parse_edilir);
    RUN_TEST(test_frame_parser_istenmeyen_tip_sonraki_komutu_bozmaz);
    RUN_TEST(test_frame_parser_tasma_gurultu_sonrasi_resync);
    RUN_TEST(test_frame_parser_bolunmus_cerceve_birlesir);
    RUN_TEST(test_fragmantasyon_25B);
    RUN_TEST(test_fragmantasyon_180B);
    RUN_TEST(test_fragmantasyon_238B);
    RUN_TEST(test_fragmantasyon_239B);
    RUN_TEST(test_fragmantasyon_400B);
    RUN_TEST(test_fragmantasyon_720B);
    RUN_TEST(test_fragmantasyon_721B);
    RUN_TEST(test_fragmantasyon_1029B);
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
