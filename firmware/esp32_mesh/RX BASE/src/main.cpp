#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include <string.h>   // memcmp icin
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "rtk_sender.h"
#include "uart_cobs.h"   // ortak CRC16/COBS/cerceve kur-coz (RX BASE + TX DRONE)
#include "uart_frame_parser.h"  // desync-guvenli ortak COBS cerceve ayristirici

// FreeRTOS queue.
struct uart_mesaj_t {
    uint8_t tip;
    uint8_t iha_id;
    uint8_t payload[18];
    uint8_t uzunluk;
};
static QueueHandle_t uart_kuyruk = nullptr;

// UART paket gonder.
static void uart_gonder(uint8_t tip, uint8_t iha_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;

    uint8_t ham[22];
    uint8_t cobs_buf[27];
    uint16_t cobs_uzunluk = cobs_cerceve_olustur(tip, iha_id, payload, payload_uzunluk, ham, cobs_buf);
    Serial2.write(cobs_buf, cobs_uzunluk);  // USB debug'tan ayri hat
}

// Sistem mesaji.
static void sistem_mesaj(const char* mesaj) {
    uint8_t buf[16] = {0};
    strncpy((char*)buf, mesaj, 15);
    uart_gonder(0xFF, 0x00, buf, 16);
}

volatile unsigned long   son_paket_ms         = 0;
bool                     failsafe_tetiklendi  = false;
uint8_t                  _failsafe_asama      = 0;
volatile uint8_t         ardisik_kayip_sayisi = 0;
uint8_t                  failsafe_active_mode = APM_MODE_RTL;

// Drone ID eslestirme.
// Tam 6 byte MAC karsilastiriliyor; sadece son byte'a bakilsaydi iki ESP32'nin
// son byte'i ayni oldugunda (Espressif atamasinda mumkun) iki drone ayni ID'ye
// eslenip sessizce kimlik cakismasi olurdu.
// Dikkat: asagidaki ilk 5 byte sifir placeholder'dir. Gercek MAC adreslerini
// (esptool.py chip_id veya WiFi.macAddress() ile okunan) buraya girmeden derleyip
// yuklemeyin, yoksa tum dronelarin ilk 5 byte'i esit sayilir.
static const struct { uint8_t mac[6]; uint8_t id; } drone_tablo[] = {
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0xB4}, 1},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0x88}, 2},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 3},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0xFF}, 4},
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);

uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < DRONE_SAYISI; i++)
        if (memcmp(drone_tablo[i].mac, mac, 6) == 0)
            return drone_tablo[i].id;
    return 0;
}

// Boot'ta provision tablosunun benzersizligini dogrula. Iki satir ayni MAC'e
// sahipse (kopyala-yapistir hatasi, doldurulmamis placeholder vb.) sistemi
// acikca uyar; sessiz kimlik cakismasindansa gurultulu boot hatasi yeglenir.
static void _drone_tablo_dogrula() {
    bool hata = false;
    for (uint8_t i = 0; i < DRONE_SAYISI; i++) {
        // 0 = "bilinmeyen MAC" sentinel'i, BAZ_ID (99) = RTK UART sentinel'i.
        // Ikisi de mesh kimligi olamaz (bkz mesh_config.h).
        if (drone_tablo[i].id == 0 || drone_tablo[i].id == BAZ_ID) {
            Serial.printf("[BOOT] HATA: drone_tablo[%u] gecersiz ID %u "
                          "(0 ve BAZ_ID/%u yasak).\n",
                          i, drone_tablo[i].id, BAZ_ID);
            hata = true;
        }
        for (uint8_t j = i + 1; j < DRONE_SAYISI; j++) {
            if (memcmp(drone_tablo[i].mac, drone_tablo[j].mac, 6) == 0) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI MAC! "
                              "ID %u ve %u cakisiyor.\n",
                              i, j, drone_tablo[i].id, drone_tablo[j].id);
                hata = true;
            }
            // ID benzersizligi: iki satira ayni ID verilirse telemetri yanlis
            // drone'a atfedilir.
            if (drone_tablo[i].id == drone_tablo[j].id) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI ID (%u)!\n",
                              i, j, drone_tablo[i].id);
                hata = true;
            }
        }
    }
    if (hata) {
        // ID cakismasi iki drone'un telemetrisinin YKİ'ye ayni iha_id ile
        // karismasi demek (yer istasyonu yanlis drone'u gosterir). aes_init()
        // 'teki provision-yok durumuyla ayni fail-closed desen: duzeltilmeden
        // calismaya devam etmez.
        Serial.println("[BOOT] drone_tablo duzeltilmeden ucusa cikilmamali!");
        Serial.println("[BOOT] KRITIK: ID cakismasi - baslatma durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
}

// Hiz limiti zaman damgalari mesh_config.h'de, tip basina (_son_tip_gonderim_ms[]).
#define JOYSTICK_MIN_ARALIK_MS 200
#define MESH_GONDERIM_MIN_MS 50

// Replay kontrol helper: node disaridan alinir.
static inline bool mesh_replay_dogrula(node_durum_t* node, const uint8_t* decrypted_baslik) {
    if (!node) return false;
    return _replay_kontrol(node, (const anti_replay_t*)decrypted_baslik);
}


// Mesh callback.
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[24] = {0};

    // AAD (tip+kaynak_mac+hedef_mac) da dogrulanir
    uint8_t aad[13];
    _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, aad);
    if (!aes_coz_gcm(p->sifreli_veri, 24, acik, p->iv, p->tag, aad, sizeof(aad))) {
        return; 
    }

    // mac_to_id whitelist once: bilinmeyen MAC state'e hic girmiyor
    uint8_t iha_id = mac_to_id(p->kaynak_mac);
    if (iha_id == 0) {
        Serial.println("[MESH] Bilinmeyen MAC, paket reddedildi");
        return;
    }
    node_durum_t* node = _node_bul_veya_ekle(p->kaynak_mac);
    if (!node) return;
    if (!mesh_replay_dogrula(node, acik)) {
        Serial.println("[MESH] Replay/Eski Paket reddedildi!");
        return;
    }

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);

    failsafe_reset();

    uart_mesaj_t msg = {};
    msg.tip    = p->tip;
    msg.iha_id = iha_id;

    if      (p->tip == TIP_POSE)      msg.uzunluk = sizeof(pose_veri_t);
    else if (p->tip == TIP_GOREV)     msg.uzunluk = sizeof(gorev_veri_t);
    else if (p->tip == TIP_RENK)      msg.uzunluk = sizeof(renk_veri_t);
    else if (p->tip == TIP_DURUM)     msg.uzunluk = sizeof(durum_veri_t);
    else if (p->tip == TIP_LEADER_HB)  msg.uzunluk = sizeof(leader_hb_veri_t);
    else if (p->tip == TIP_ELECTION)   msg.uzunluk = sizeof(election_veri_t);
    else if (p->tip == TIP_VERSION)    msg.uzunluk = sizeof(version_veri_t);
    else if (p->tip == TIP_SWARM_STATE) msg.uzunluk = sizeof(swarm_state_veri_t);
    else if (p->tip == TIP_QR_DATA)    msg.uzunluk = sizeof(qr_veri_t);
    else return; 

    // Ilk 6 byte'i atla (anti-replay basligi)
    memcpy(msg.payload, acik + sizeof(anti_replay_t), msg.uzunluk);

    if (uart_kuyruk) {
        if (xQueueSend(uart_kuyruk, &msg, pdMS_TO_TICKS(5)) != pdPASS) { // 5ms timeout
            static volatile uint32_t _kuyruk_dolu_sayisi = 0;
            _kuyruk_dolu_sayisi++;
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    _drone_tablo_dogrula();  // MAC benzersizligini boot'ta dogrula

    // RTCM girisi icin Serial1. Baslatilmazsa Serial1.available() hep 0 kalir
    // ve RTK base RTCM okuyamaz.
    // Dikkat: asagidaki pin numaralari placeholder'dir. Ucus/saha oncesi gercek
    // RTCM kaynaginizin (YKİ/PC) hangi GPIO'lara bagli oldugunu dogrulayin.
    #define RTK_RX_PIN 16   // TODO: gercek YKİ->ESP RX pinini dogrula
    #define RTK_TX_PIN 17   // TODO: gercek YKİ->ESP TX pinini dogrula (genelde kullanilmaz)
    // baud 460800 (spec + ekip karari). setRxBufferSize() begin()'den once
    // cagrilmali; sonra cagrilirsa sessizce etkisiz kalir (varsayilan 256B ring
    // buffer kullanilmaya devam eder).
    Serial1.setRxBufferSize(2048);  // spec 3.2: UART RX buffer >= 2048B
    Serial1.begin(460800, SERIAL_8N1, RTK_RX_PIN, RTK_TX_PIN);
    Serial.println("[UART] YKİ/RTCM (Serial1, 460800) baslatildi - PIN DOGRULAMASI GEREKLI");

    // RTCM durum LED'i (saha teshisi icin yanip soner).
    // TODO: pin placeholder, gercek donanimda dogrulanmali (cogu ESP32 kartinda
    // GPIO2 yerlesik LED'e bagli).
    pinMode(RTK_LED_PIN, OUTPUT);

    // YKİ komut/telemetri COBS binary protokolu USB Serial yerine Serial2'de,
    // boylece debug printf'leriyle carpismaz. (Yerde RPi YOK: Serial2'nin karsisi
    // YKİ laptobudur, "Pi" degil. Isim drone tarafindan miras kalmisti.)
    // Dikkat: asagidaki pin numaralari placeholder'dir, YKİ UART kablolamasina
    // gore dogrulayin.
    #define YKI_RX_PIN 25    // TODO: gercek YKİ TX -> ESP32 RX pinini dogrula
    #define YKI_TX_PIN 26    // TODO: gercek YKİ RX -> ESP32 TX pinini dogrula
    Serial2.begin(115200, SERIAL_8N1, YKI_RX_PIN, YKI_TX_PIN);
    Serial.println("[UART] YKİ komut/telemetri (Serial2, 115200) baslatildi - PIN DOGRULAMASI GEREKLI");


    uart_kuyruk = xQueueCreate(20, sizeof(uart_mesaj_t));
    sistem_mesaj("RX BASE HAZIR");


    WiFi.mode(WIFI_STA);

    // Ucus oncesi opsiyonel manuel kanal taramasi.
    // Otomatik degisim yok, sadece operator isterse rapor alir.
    Serial.println("[BOOT] Kanal taramasi icin 3 sn icinde 'T' gonderin (opsiyonel)...");
    uint32_t _tara_bekleme_baslangic = millis();
    while (millis() - _tara_bekleme_baslangic < 3000) {
        if (Serial.available() && Serial.read() == 'T') {
            mesh_kanal_tara();
            break;
        }
    }

    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    // Watchdog: 8 saniye, loop donerse ESP32 reset atar
    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);
    son_paket_ms = millis();
    sistem_mesaj("MESH HAZIR");
}




void loop() {
    // rtk_mesh_loop() cagrilmali: _esp_now_recv_cb ISR'i RX BASE'te de TIP_RTK
    // zarflarini _rtk_recv_buffer'a yaziyor ve bu buffer'i bosaltan tek yer bu.
    // Tek-baz topolojisinde RX BASE kendi yayinini geri almaz (_benim_mac_mi
    // eler) ama RF ortaminda/testte gelecek herhangi bir TIP_RTK paketi bosalma
    // olmadan bu 8 girislik ring buffer'i tikayabilir. rtk_mesh_loop() zaten
    // rtk_loop()'u kendi icinde cagirir.
    //
    // Serial2 acikca verilir: RX BASE'te Serial1 YKİ/RTCM giris hattidir, YKİ
    // komut/telemetri protokolu Serial2'de yurur. Varsayilan (Serial1) birakilirsa
    // reassemble edilen RTCM mesaji YKİ'nin yayin yaptigi hatta geri yazilirdi.
    rtk_mesh_loop(Serial2);
    rtk_serial_isle(Serial1);
    esp_task_wdt_reset();
    mesh_loop();


    static uint32_t son_kayip_kontrol = 0;
    if (millis() - son_kayip_kontrol >= 100) {
        son_kayip_kontrol = millis();
        if (millis() - son_paket_ms > 150) {
            portENTER_CRITICAL(&_recv_mux);
            if (ardisik_kayip_sayisi < 255) ardisik_kayip_sayisi++;
            portEXIT_CRITICAL(&_recv_mux);
        }
    }


    // RX BASE'in YKİ hatti Serial2'dir (Serial1 RTCM'e ayrildi), o yuzden acikca
    // Serial2 verilir; aksi halde bildirim varsayilan Serial1'e (RTCM giris
    // hattina) gider ve YKİ'ye hic ulasmaz. Kademeli (UYARI/RTL/LAND) bildirim
    // TX DRONE ile ayni formatta calisir.
    failsafe_kontrol(Serial2);

#ifndef RTK_ISTATISTIK_LOGLAMA_KAPALI
    // Gonderici tarafi RTK istatistigi (TX DRONE'daki alici karsiligiyla ayni
    // periyot/flag). Baz'in kendi yayin sagligini gorunur kilar: bu satir
    // olmadan "RTK yok" sikayetinde baz'in hic yayin yapmadigi ile havada
    // kaybolmasi ayirt edilemiyordu (bkz rtk_sender.h okuma kilavuzu).
    static uint32_t son_rtk_tx_istatistik_ms = 0;
    if (millis() - son_rtk_tx_istatistik_ms >= 10000) {
        son_rtk_tx_istatistik_ms = millis();
        rtk_tx_istatistik_yazdir();
        mesh_tip_dusen_yazdir();   // hiz limitinde dusen cerceveler (tip bazinda)
    }
#endif

    uart_mesaj_t gelen;
    while (xQueueReceive(uart_kuyruk, &gelen, 0) == pdPASS) {
        uart_gonder(gelen.tip, gelen.iha_id, gelen.payload, gelen.uzunluk);
    }

    // Ortak, desync-guvenli COBS cerceve ayristirici (bkz uart_frame_parser.h).
    // Whitelist/dispatch mantigi sadece tamamlanmis cerceveye uygulanir; hicbir
    // dali ayristirici durumunu (idx) etkilemez.
    static uart_frame_parser_t pi_parser;
    uint8_t okunan = 0;
    while (Serial2.available() && okunan < 32) {  // YKİ hatti Serial2'de
        uint8_t b = Serial2.read();
        okunan++;
        uint8_t tip_byte, id_byte_unused;
        const uint8_t* cerceve_payload;
        uint16_t cerceve_payload_uzunluk;
        if (!uart_frame_parser_push(&pi_parser, b, &tip_byte, &id_byte_unused,
                                    &cerceve_payload, &cerceve_payload_uzunluk))
            continue;

        uint32_t simdi = millis();
        // mesh_gonder() her zaman 18 byte okur (memcpy(tam_veri+6, veri, 18)),
        // o yuzden buffer 18B. 16B olsaydi 2 byte stack over-read (UB) olurdu.
        // Gercek payload struct'lari 16B, payload_uzunluk siniri 16'da kaliyor,
        // fazladan 2 byte zaten sifirlanmis dolgu.
        uint8_t veri[18] = {0};
        uint8_t payload_uzunluk = (uint8_t)min((int)cerceve_payload_uzunluk, 16);
        memcpy(veri, cerceve_payload, payload_uzunluk);

        // Acik whitelist + reddet: TIP_KOMUT kendi (daha siki) joystick hiz
        // sinirini korur, bilinen diger tipler ait olduklari tiple gonderilir,
        // taninmayan tip atilir. Bilinmeyen bir tip TIP_KOMUT'a donusturulup
        // joystick sanilmaz. Hiz limiti tip basina (mesh_tip_gecebilir);
        // TIP_KOMUT kendi 200ms araligini korur.
        if (tip_byte == TIP_KOMUT) {
            if (mesh_tip_gecebilir(TIP_KOMUT, simdi, JOYSTICK_MIN_ARALIK_MS))
                mesh_gonder(veri, TIP_KOMUT);
        } else if (tip_byte == TIP_RENK  || tip_byte == TIP_DURUM ||
                   tip_byte == TIP_SWARM_STATE || tip_byte == TIP_QR_DATA ||
                   tip_byte == TIP_ORIGIN || tip_byte == TIP_GOREV) {
            if (mesh_tip_gecebilir(tip_byte, simdi, MESH_GONDERIM_MIN_MS))
                mesh_gonder(veri, tip_byte);
        }
        // else: taninmayan tip sessizce atilir. TIP_LEADER_HB/TIP_ELECTION
        // bilerek dahil edilmedi: baz, drone consensus'una taraf degil.
    }

    static uint32_t son_durum = 0;
    if (millis() - son_durum >= 5000) {
        son_durum = millis();
        uint8_t aktif = 0;
        portENTER_CRITICAL(&_recv_mux);
        for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
            if (_bilinen_nodlar[i].aktif) aktif++;
        portEXIT_CRITICAL(&_recv_mux);
        uint8_t buf[16] = {0};
        buf[0] = aktif;
        buf[1] = MESH_MAX_NODES;
        uart_gonder(0xFD, 0x00, buf, 16);
    }
}
