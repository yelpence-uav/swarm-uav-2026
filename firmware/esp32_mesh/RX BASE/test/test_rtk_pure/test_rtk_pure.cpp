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
#include "replay_pure.h"         // reboot-replay karar kurali

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

// Reboot-replay karar kurali.
// Tehdit: saldirgan RF'i yakalar, gonderici reboot edene kadar bekler, sonra
// eski session'in (authenticated ama eski) paketlerini tekrar oynatir.
// "session_id farkli -> reboot varsay, pencereyi sifirla, kabul" deseydik saldiri
// islerdi. Kural: session_id monoton, kucuk olan reddedilir. Alici yarisi
// (kalici_session) olmadan kural kagit uzerinde kalir, o yuzden ayrica test edilir.

static replay_state_t _yeni_durum(void) {
    replay_state_t rs;
    memset(&rs, 0, sizeof(rs));
    rs.ilk_paket = true;
    return rs;
}

void test_replay_ilk_paket_kabul(void) {
    replay_state_t rs = _yeni_durum();
    // Kalici kayit yok (0) -> ilk paket kabul, cagirana "persist et" denir
    TEST_ASSERT_EQUAL(REPLAY_KABUL_YENI_SESSION, replay_karar(&rs, 5, 100, 0));
    TEST_ASSERT_EQUAL_UINT16(5, rs.session_id);
    TEST_ASSERT_FALSE(rs.ilk_paket);
}

// Cekirdek regresyon: alici reboot etti (RAM durumu yok, ilk_paket=true) ama
// NVS'te peer'in son session'i duruyor. Saldirgan eski session'i oynatiyor.
void test_replay_alici_reboot_sonrasi_eski_session_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    // NVS: bu peer'i en son session 9'da gormustuk
    TEST_ASSERT_EQUAL(REPLAY_RED_ESKI_SESSION, replay_karar(&rs, 7, 500, /*kalici=*/9));
    // Reddedilen paket durumu KIRLETMEMELI (hala ilk_paket)
    TEST_ASSERT_TRUE(rs.ilk_paket);
}

// Ayni senaryo ama kalici kayit yoksa (alici yarisi atlanmis olsaydi) saldiri
// gecerdi. Bu test alici-persist yarisinin neden sart oldugunu belgeliyor:
// kalici=0 iken ayni eski paket kabul ediliyor.
void test_replay_kalici_kayit_yoksa_eski_session_gecer(void) {
    replay_state_t rs = _yeni_durum();
    TEST_ASSERT_TRUE(replay_kabul_mu(replay_karar(&rs, 7, 500, /*kalici=*/0)));
}

void test_replay_ayni_session_devam_kabul(void) {
    replay_state_t rs = _yeni_durum();
    // NVS'teki session ile ayni -> normal kabul, persist gerekmez
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 9, 100, /*kalici=*/9));
}

void test_replay_calisirken_eski_session_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 10, 100, 0);            // session 10'da calisiyoruz
    // Saldirgan session 9'dan bir paket enjekte ediyor
    TEST_ASSERT_EQUAL(REPLAY_RED_ESKI_SESSION, replay_karar(&rs, 9, 50, 10));
    TEST_ASSERT_EQUAL_UINT16(10, rs.session_id);  // durum bozulmadi
}

void test_replay_yeni_session_kabul_ve_pencere_sifirlanir(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 10, 5000, 0);
    // Gonderici reboot etti: session 11, paket_id bastan (dusuk)
    TEST_ASSERT_EQUAL(REPLAY_KABUL_YENI_SESSION, replay_karar(&rs, 11, 1, 10));
    TEST_ASSERT_EQUAL_UINT16(11, rs.session_id);
    TEST_ASSERT_EQUAL_UINT32(1, rs.en_yuksek_id);   // pencere sifirlandi
}

void test_replay_duplikat_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 3, 100, 0);
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 101, 3));
    TEST_ASSERT_EQUAL(REPLAY_RED_DUPLIKAT, replay_karar(&rs, 3, 101, 3));  // ayni paket
    TEST_ASSERT_EQUAL(REPLAY_RED_DUPLIKAT, replay_karar(&rs, 3, 100, 3));
}

void test_replay_pencere_disi_eski_paket_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 3, 1000, 0);
    // PENCERE_BOYU=64: 1000-64=936 ve altisi cok eski
    TEST_ASSERT_EQUAL(REPLAY_RED_ESKI_PAKET, replay_karar(&rs, 3, 936, 3));
    TEST_ASSERT_EQUAL(REPLAY_RED_ESKI_PAKET, replay_karar(&rs, 3, 1, 3));
    // Pencere icindeki (henuz gorulmemis) eski paket KABUL edilmeli
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 990, 3));
}

void test_replay_sira_disi_pencere_icinde_kabul(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 3, 100, 0);
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 105, 3));  // ileri sicrama
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 102, 3));  // geride kalan
    TEST_ASSERT_EQUAL(REPLAY_RED_DUPLIKAT, replay_karar(&rs, 3, 102, 3));  // tekrari
}

void test_replay_buyuk_ilerleme_pencereyi_temizler(void) {
    replay_state_t rs = _yeni_durum();
    replay_karar(&rs, 3, 100, 0);
    // 64'ten buyuk ilerleme -> pencere tamamen temizlenir
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 1000, 3));
    TEST_ASSERT_EQUAL_UINT32(1000, rs.en_yuksek_id);
    // Eski pencereden bir sey kalmamali: 999 (henuz gorulmedi) kabul
    TEST_ASSERT_EQUAL(REPLAY_KABUL, replay_karar(&rs, 3, 999, 3));
}

// Fragmantasyon.
// Bu testler mesh-seviyesi fragmantasyonu (RTK_MAX_FRAGS=8,
// RTK_FRAG_PAYLOAD_MAKS=191 -> ust sinir 1528B) dogruluyor. Spec'in "721B ustu
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
void test_fragmantasyon_200B(void) { _frag_test_yardimci(200, 2); }
void test_fragmantasyon_201B(void) { _frag_test_yardimci(201, 2); }
void test_fragmantasyon_400B(void) { _frag_test_yardimci(400, 3); }
void test_fragmantasyon_720B(void) { _frag_test_yardimci(720, 4); }
void test_fragmantasyon_721B(void) { _frag_test_yardimci(721, 4); }

void test_fragmantasyon_ust_sinir_kabul(void) {
    // RTK_MAX_FRAGS * RTK_FRAG_PAYLOAD_MAKS = 8*191 = 1528B, tam sinirda kabul edilmeli
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
    // (rtk_fragman_hesapla), yani 248B -> 191 + 57. 5+5B parcalarla yazilan
    // eski sekil telde asla olusmuyor ve testi anlamsizlastiriyordu; bu test
    // teslim edilen byte'lara da bakiyor.
    const uint16_t MESAJ_UZUNLUK = 248;
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

// RTK ile reboot-replay kesisimi.
// Bu kesisim daha once "analizle guvenli, testle degil" diye isaretlenmisti;
// burasi o cumleyi kanita ceviriyor.
//
// Modellenen mimari:
//   - RTK zarfi da genel mesh de ayni anti_replay'i tasiyor ve gonderici tarafta
//     ayni _paket_sayaci'ndan besleniyor (tek artan dizi).
//   - ISR offset 17'deki tip'e bakip TIP_RTK'yi ayri bir ring buffer'a
//     (_rtk_recv_buffer, 8) yaziyor, digerleri _recv_buffer'a (16). Ikisini
//     farkli donguler bosaltiyor, iki kaynak arasinda sira korunmuyor.
//   - Alici tarafta ikisi de ayni node->replay penceresini kullaniyor, yani
//     sirasizlik dogrudan replay penceresine vuruyor.
//
// Azami kayma buffer derinlikleriyle sinirli: 8 + 16 = 24 << PENCERE_BOYU(64).
// Testler bu siniri ve session degisimi anini zorluyor.

// replay_karar'i "kalici kayit yok" kisayoluyla cagiran yardimci (kesisim
// testlerinde ilgilenilen sey session/pencere etkilesimi, NVS degil).
static bool _kabul(replay_state_t* rs, uint16_t sid, uint32_t pid) {
    return replay_kabul_mu(replay_karar(rs, sid, pid, /*kalici=*/0));
}

// RTK burst'u + genel mesh trafigi TEK sayactan besleniyor; iki ring buffer
// sirasiz bosaldigi icin alici bunlari karisik sirada goruyor. Hicbir mesru
// paket kaybolmamali.
void test_rtk_f1_iki_kaynak_sirasiz_hepsi_kabul(void) {
    replay_state_t rs = _yeni_durum();
    // paket_id 1..12: {1,3,5,7} RTK fragmentlari, {2,4,6,8..12} genel mesh.
    // Gercek loop() sirasi: once TUM rtk buffer, sonra genel buffer.
    const uint32_t rtk[]   = {1, 3, 5, 7};
    const uint32_t genel[] = {2, 4, 6, 8, 9, 10, 11, 12};

    for (uint32_t p : rtk)
        TEST_ASSERT_TRUE_MESSAGE(_kabul(&rs, 1, p), "RTK fragmenti reddedildi");
    // Genel mesh paketleri SONRA isleniyor -> paket_id'leri geriye gidiyor.
    // Sliding window bunlari pencere icinde kabul etmeli.
    for (uint32_t p : genel)
        TEST_ASSERT_TRUE_MESSAGE(_kabul(&rs, 1, p), "Sirasiz genel mesh paketi reddedildi");
}

// Kayma tam sinirda (24 = 8+16 buffer derinligi): en kotu durumda bile
// pencere (64) hepsini soğurmali. Bu test PENCERE_BOYU kucultulurse patlar.
void test_rtk_f1_azami_kayma_penceresi_asmiyor(void) {
    replay_state_t rs = _yeni_durum();
    // Once ileri sicra (RTK buffer'i once bosaldi): 1, sonra 25.
    TEST_ASSERT_TRUE(_kabul(&rs, 1, 1));
    TEST_ASSERT_TRUE(_kabul(&rs, 1, 25));
    // Simdi geride kalan 24 paket (genel buffer) sirasiz geliyor: 2..24
    for (uint32_t p = 2; p <= 24; p++)
        TEST_ASSERT_TRUE_MESSAGE(_kabul(&rs, 1, p), "Kayma<=24 pencerede kabul edilmeliydi");
    // Sinirin otesi (65 geride) reddedilmeli, pencere hala calisiyor.
    TEST_ASSERT_TRUE(_kabul(&rs, 1, 200));
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 1, 200 - PENCERE_BOYU),
                              "Pencere disi paket kabul edildi");
}

// SESSION DEGISIMI ANI: gonderici reboot etti (session 1 -> 2) ve _paket_sayaci
// 0'dan yeniden basladi. Alicinin iki buffer'i hala ESKI session'in paketlerini
// tasiyor olabilir. Yeni session'in kucuk paket_id'leri kabul edilmeli; eski
// session'in paketleri ise (buffer'da kalmis olsalar bile) REDDEDILMELI.
void test_rtk_f1_session_degisimi_aninda_eski_session_paketleri_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    TEST_ASSERT_TRUE(_kabul(&rs, 1, 500));
    TEST_ASSERT_TRUE(_kabul(&rs, 1, 501));

    // Gonderici reboot: session 2, paket_id 1'den basliyor. Ilk gelen bir RTK
    // fragmenti olsun -> yeni session kabul, pencere sifirlanir.
    TEST_ASSERT_TRUE_MESSAGE(_kabul(&rs, 2, 1), "Reboot sonrasi yeni session reddedildi");
    // Ardindan gecikmis genel mesh paketleri (yeni session, kucuk id) gelir.
    TEST_ASSERT_TRUE(_kabul(&rs, 2, 2));
    TEST_ASSERT_TRUE(_kabul(&rs, 2, 3));

    // Kritik: buffer'da kalmis eski session (1) paketleri, paket_id'leri buyuk
    // olsa bile reddedilmeli. "farkli session -> kabul" deseydik bu paketler
    // gecerdi (tam da kapatilan acik).
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 1, 502),
                              "Eski session paketi kabul edildi - F1 kurali kesisimde calismiyor");
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 1, 9999),
                              "Eski session'in buyuk paket_id'si kabul edildi");
    // Yeni session normal akmaya devam etmeli (eski session reddi onu bozmadi).
    TEST_ASSERT_TRUE(_kabul(&rs, 2, 4));
}

// RTK burst'u tam session degisimine denk gelirse: ayni RTCM mesajinin
// fragmentlari reboot'a bolunemez (gonderici reboot ederse burst zaten olur),
// ama alicinin buffer'inda eski session fragmentleri KALABILIR. Reassembly'nin
// bunlari gormemesi replay katmaninda saglanmali.
void test_rtk_f1_burst_ortasinda_reboot_eski_fragmentler_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    // Eski session'da 4 fragmentlik bir RTCM burst'unun ilk 2'si islendi.
    TEST_ASSERT_TRUE(_kabul(&rs, 7, 100));
    TEST_ASSERT_TRUE(_kabul(&rs, 7, 101));
    // Gonderici reboot etti (session 8), yeni burst basladi.
    TEST_ASSERT_TRUE(_kabul(&rs, 8, 1));
    // Buffer'da kalan ESKI burst'un 3. ve 4. fragmentleri simdi isleniyor:
    // reddedilmeli, yoksa reassembly iki session'in fragmentlerini karistirir.
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 7, 102),
                              "Reboot oncesi fragment kabul edildi - reassembly karisirdi");
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 7, 103),
                              "Reboot oncesi fragment kabul edildi - reassembly karisirdi");
    // Yeni session'in burst'u temiz devam eder.
    TEST_ASSERT_TRUE(_kabul(&rs, 8, 2));
    TEST_ASSERT_TRUE(_kabul(&rs, 8, 3));
}

// Duplikat, kesisimde de tutmali: RTK fragmenti iki kez islenirse (ISR ring
// buffer'i + retry) ikincisi reddedilmeli.
void test_rtk_f1_duplikat_fragment_kesisimde_reddedilir(void) {
    replay_state_t rs = _yeni_durum();
    TEST_ASSERT_TRUE(_kabul(&rs, 3, 10));
    TEST_ASSERT_TRUE(_kabul(&rs, 3, 11));
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 3, 10), "Duplikat RTK fragmenti kabul edildi");
    TEST_ASSERT_FALSE_MESSAGE(_kabul(&rs, 3, 11), "Duplikat RTK fragmenti kabul edildi");
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
    RUN_TEST(test_frame_parser_tek_cerceve_roundtrip);
    RUN_TEST(test_frame_parser_arka_arkaya_iki_cerceve);
    RUN_TEST(test_frame_parser_bozuk_cerceve_sonrasi_gecerli_parse_edilir);
    RUN_TEST(test_frame_parser_istenmeyen_tip_sonraki_komutu_bozmaz);
    RUN_TEST(test_frame_parser_tasma_gurultu_sonrasi_resync);
    RUN_TEST(test_frame_parser_bolunmus_cerceve_birlesir);
    RUN_TEST(test_replay_ilk_paket_kabul);
    RUN_TEST(test_replay_alici_reboot_sonrasi_eski_session_reddedilir);
    RUN_TEST(test_replay_kalici_kayit_yoksa_eski_session_gecer);
    RUN_TEST(test_replay_ayni_session_devam_kabul);
    RUN_TEST(test_replay_calisirken_eski_session_reddedilir);
    RUN_TEST(test_replay_yeni_session_kabul_ve_pencere_sifirlanir);
    RUN_TEST(test_replay_duplikat_reddedilir);
    RUN_TEST(test_replay_pencere_disi_eski_paket_reddedilir);
    RUN_TEST(test_replay_sira_disi_pencere_icinde_kabul);
    RUN_TEST(test_replay_buyuk_ilerleme_pencereyi_temizler);
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
    // RTK ile reboot-replay kesisimi
    RUN_TEST(test_rtk_f1_iki_kaynak_sirasiz_hepsi_kabul);
    RUN_TEST(test_rtk_f1_azami_kayma_penceresi_asmiyor);
    RUN_TEST(test_rtk_f1_session_degisimi_aninda_eski_session_paketleri_reddedilir);
    RUN_TEST(test_rtk_f1_burst_ortasinda_reboot_eski_fragmentler_reddedilir);
    RUN_TEST(test_rtk_f1_duplikat_fragment_kesisimde_reddedilir);
    return UNITY_END();
}
