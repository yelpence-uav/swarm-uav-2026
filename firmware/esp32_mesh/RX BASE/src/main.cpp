#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include <string.h>   // ORTA-2 FIX: memcmp icin
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "rtk_sender.h"
#include "uart_cobs.h"   // REV B: ortak CRC16/COBS/cerceve kur-coz (RX BASE + TX DRONE)
#include "uart_frame_parser.h"  // desync-güvenli ortak COBS çerçeve ayrıştırıcı (native testli)

// ===== FREERTOS QUEUE =====
struct uart_mesaj_t {
    uint8_t tip;
    uint8_t iha_id;
    uint8_t payload[18];
    uint8_t uzunluk;
};
static QueueHandle_t uart_kuyruk = nullptr;

// ===== UART PAKET GONDER =====
static void uart_gonder(uint8_t tip, uint8_t iha_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;

    uint8_t ham[22];
    uint8_t cobs_buf[27];
    uint16_t cobs_uzunluk = cobs_cerceve_olustur(tip, iha_id, payload, payload_uzunluk, ham, cobs_buf);
    Serial2.write(cobs_buf, cobs_uzunluk);  // KRITIK-1 FIX: USB debug'tan ayrildi
}

// ===== SISTEM MESAJI =====
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

// ===== DRONE ID ESLESTIRME =====
// ORTA-2 FIX: eskiden yalnizca MAC'in son byte'i karsilastiriliyordu; iki
// ESP32'nin son byte'i ayni olursa (Espressif atamasinda mumkun) iki drone
// ayni ID'ye eslenip sessizce kimlik cakismasi olusuyordu. Simdi tam 6 byte
// karsilastiriliyor.
// !!! DIKKAT: asagidaki ilk 5 byte SIFIR PLACEHOLDER'dir. Gercek MAC
// adreslerini (esptool.py chip_id ile veya WiFi.macAddress() ile okunan
// tam adresi) buraya girmeden derleyip yuklemeyin — aksi halde tum
// dronelarin ilk 5 byte'i esit sayilir ve son byte'a geri donmus oluruz.
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

// ORTA-2 FIX: boot'ta provision tablosunun benzersizligini dogrula.
// Iki satir ayni MAC'e sahipse (kopyala-yapistir hatasi, doldurulmamis
// placeholder vb.) sistemi acikca uyar — sessiz kimlik cakismasindansa
// gurultulu bir boot hatasi tercih edilir.
static void _drone_tablo_dogrula() {
    bool hata = false;
    for (uint8_t i = 0; i < DRONE_SAYISI; i++) {
        // ID SANITY: 0 = "bilinmeyen MAC" sentinel'i, BAZ_ID (99) = RTK UART
        // sentinel'i. Ikisi de mesh kimligi olamaz (bkz mesh_config.h).
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
            // ID BENZERSIZLIGI: eskiden SADECE MAC kontrol ediliyordu; iki
            // satira ayni ID verilirse telemetri yanlis drone'a atfedilir.
            if (drone_tablo[i].id == drone_tablo[j].id) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI ID (%u)!\n",
                              i, j, drone_tablo[i].id);
                hata = true;
            }
        }
    }
    if (hata) {
        // BUG FIX (satır satır inceleme): eskiden sadece loglayip devam
        // ediyordu — yorum "gurultulu bir boot hatasi tercih edilir" diyordu
        // ama kod sessizce calismaya devam ediyordu. ID cakismasi iki
        // drone'un telemetrisinin Pi'ye AYNI iha_id ile karismasi demek
        // (yer istasyonu yanlis drone'u gosterir) — encryption.h::aes_init()
        // 'teki provision-yok durumuyla ayni fail-closed desenine getirildi:
        // duzeltilmeden calismaya devam etmez.
        Serial.println("[BOOT] drone_tablo duzeltilmeden ucusa cikilmamali!");
        Serial.println("[BOOT] KRITIK: ID cakismasi - baslatma durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
}

#define JOYSTICK_MIN_ARALIK_MS 200
static uint32_t son_joystick_ms = 0;
#define MESH_GONDERIM_MIN_MS 50
static uint32_t son_mesh_gonderim_ms = 0;

// REPLAY KONTROL HELPER — C2 fix: node disaridan alinir
static inline bool mesh_replay_dogrula(node_durum_t* node, const uint8_t* decrypted_baslik) {
    if (!node) return false;
    return _replay_kontrol(node, (const anti_replay_t*)decrypted_baslik);
}


// ===== MESH CALLBACK =====
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[24] = {0}; // FIX: Buffer 24'e cikarildi

    // FIX #1: Uzunluk (24) parametresi eklendi
    // ORTA-1 fix: AAD (tip+kaynak_mac+hedef_mac) de dogrulanir
    uint8_t aad[13];
    _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, aad);
    if (!aes_coz_gcm(p->sifreli_veri, 24, acik, p->iv, p->tag, aad, sizeof(aad))) {
        return; 
    }

    // FIX #4: mac_to_id whitelist ONCE — bilinmeyen MAC state'e hic girmiyor
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

    // FIX #3: Ilk 6 byte'i atla (anti-replay basligi)
    memcpy(msg.payload, acik + sizeof(anti_replay_t), msg.uzunluk);

    if (uart_kuyruk) {
        if (xQueueSend(uart_kuyruk, &msg, pdMS_TO_TICKS(5)) != pdPASS) { // FIX: Timeout 5ms
            static volatile uint32_t _kuyruk_dolu_sayisi = 0;
            _kuyruk_dolu_sayisi++;
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    _drone_tablo_dogrula();  // ORTA-2 FIX: MAC benzersizligini boot'ta dogrula

    // KRITIK-1 FIX: RTCM girisi icin Serial1 hic baslatilmiyordu -> RTK base
    // hicbir zaman RTCM okuyamiyordu (Serial1.available() hep 0).
    // !!! DIKKAT: asagidaki pin numaralari PLACEHOLDER'dir. Ucus/saha
    // oncesi gercek RTCM kaynaginizin (YKİ/PC) hangi GPIO'lara
    // bagli oldugunu DOGRULAYIN ve gerekirse degistirilmeli.
    #define RTK_RX_PIN 16   // TODO: gercek YKİ->ESP RX pinini dogrula
    #define RTK_TX_PIN 17   // TODO: gercek YKİ->ESP TX pinini dogrula (genelde kullanilmaz)
    // REV B: baud 460800 kesinlesti (spec + ekip karari). Onceki oturumda
    // gercek donanimda dogrulanmadigi icin 115200'de birakilmisti — artik
    // ekip karariyla degistirildi. setRxBufferSize() begin()'DEN ONCE
    // cagrilmali; ESP32 Arduino corede sonra cagrilirsa SESSIZCE etkisiz
    // kalir (varsayilan 256B ring buffer kullanilmaya devam eder).
    Serial1.setRxBufferSize(2048);  // spec 3.2: UART RX buffer >= 2048B
    Serial1.begin(460800, SERIAL_8N1, RTK_RX_PIN, RTK_TX_PIN);
    Serial.println("[UART] YKİ/RTCM (Serial1, 460800) baslatildi - PIN DOGRULAMASI GEREKLI");

    // ADIM 5: RTCM durum LED'i (spec 3.2 "saha teshisi icin yanip sonsun").
    // TODO: pin PLACEHOLDER — gercek donanimda dogrulanmali (cogu ESP32
    // gelistirme kartinda GPIO2 yerlesik LED'e bagli).
    pinMode(RTK_LED_PIN, OUTPUT);

    // KRITIK-2 FIX: Pi ile COBS binary protokolu artik USB Serial yerine
    // Serial2'de - debug printf'leri ile artik CARPISMAZ.
    // !!! DIKKAT: asagidaki pin numaralari PLACEHOLDER'dir, Pi UART
    // kablolamasina gore DOGRULAYIN.
    #define PI_RX_PIN 25    // TODO: gercek Pi TX -> ESP32 RX pinini dogrula
    #define PI_TX_PIN 26    // TODO: gercek Pi RX -> ESP32 TX pinini dogrula
    Serial2.begin(115200, SERIAL_8N1, PI_RX_PIN, PI_TX_PIN);
    Serial.println("[UART] Pi protokolu (Serial2) baslatildi - PIN DOGRULAMASI GEREKLI");


    uart_kuyruk = xQueueCreate(20, sizeof(uart_mesaj_t));
    sistem_mesaj("RX BASE HAZIR");


    WiFi.mode(WIFI_STA);

    // DUSUK-2 FIX: ucus oncesi opsiyonel manuel kanal taramasi.
    // Otomatik degisim YOK — sadece operator isterse rapor alir.
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
    // Watchdog: 8 saniye — loop donerse ESP32 reset atar
    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);
    son_paket_ms = millis();
    sistem_mesaj("MESH HAZIR");
}




void loop() {
    // BUG FIX (satır satır inceleme): eskiden burada sadece rtk_loop()
    // (timeout kontrolü) çağrılıyordu. Ama _esp_now_recv_cb ISR'ı (ortak
    // kod, mesh_config.h) RX BASE'te de TIP_RTK zarflarını _rtk_recv_buffer'a
    // yazmaya devam ediyor — bu buffer'ı boşaltan tek fonksiyon
    // rtk_mesh_loop() idi ve hiç çağrılmıyordu. Normal tek-baz topolojisinde
    // RX BASE kendi yayınını geri almaz (ESP-NOW self-loop yapmaz, ve
    // _benim_mac_mi kontrolü de zaten eler) ama RF ortamında/testte gelecek
    // herhangi bir TIP_RTK-etiketli paket bu 8 girişlik ring buffer'ı
    // kalıcı ve sessizce doldurup tıkardı (hiç boşalmadığı için). rtk_mesh_loop()
    // zaten rtk_loop()'u kendi içinde çağırıyor, bu yüzden davranış üst
    // kümesi — güvenli.
    //
    // Serial2 AÇIKÇA verilir: RX BASE'te Serial1 YKİ/RTCM GİRİŞ hattıdır,
    // Pi protokolü Serial2'de yürür. Varsayılan (Serial1) bırakılırsa
    // reassemble edilen bir RTCM mesajı YKİ'nin yayın yaptığı hatta geri
    // yazılırdı — failsafe_kontrol(Serial2) ile aynı gerekçe (bkz 50c84ef).
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


    // RX BASE'in Pi hatti Serial2'dir (Serial1 RTCM'e ayrildi) — bu yuzden
    // acikca Serial2 verilir; aksi halde bildirim varsayilan Serial1'e (RTCM
    // giris hattina) gider ve Pi'ye hic ulasmaz. Eskiden burada ayri, basit
    // bir 0xFE bayrak gonderimi vardi (failsafe_kontrol() hic cagrilmadigi
    // icin telafi amacli), ama o da tetiklenmiyordu; artik gercek kademeli
    // (UYARI/RTL/LAND) bildirim TX DRONE ile ayni formatta calisir.
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
    }
#endif

    uart_mesaj_t gelen;
    while (xQueueReceive(uart_kuyruk, &gelen, 0) == pdPASS) {
        uart_gonder(gelen.tip, gelen.iha_id, gelen.payload, gelen.uzunluk);
    }

    // Ortak, desync-güvenli COBS çerçeve ayrıştırıcı (bkz uart_frame_parser.h).
    // Whitelist/dispatch mantığı SADECE tamamlanmış çerçeveye uygulanır;
    // hiçbir dalı ayrıştırıcı durumunu (idx) etkilemez.
    static uart_frame_parser_t pi_parser;
    uint8_t okunan = 0;
    while (Serial2.available() && okunan < 32) {  // KRITIK-1 FIX: USB debug'tan ayrildi
        uint8_t b = Serial2.read();
        okunan++;
        uint8_t tip_byte, id_byte_unused;
        const uint8_t* cerceve_payload;
        uint16_t cerceve_payload_uzunluk;
        if (!uart_frame_parser_push(&pi_parser, b, &tip_byte, &id_byte_unused,
                                    &cerceve_payload, &cerceve_payload_uzunluk))
            continue;

        uint32_t simdi = millis();
        // ORTA-2 FIX: mesh_gonder() her zaman 18 byte okur (memcpy(tam_veri+6,
        // veri, 18)); 16 byte'lik buffer 2 byte stack over-read'e (UB) yol
        // aciyordu. Gercek payload struct'lari 16B oldugundan payload_uzunluk
        // siniri 16'da kaliyor, fazladan 2 byte zaten-sifirlanmis dolgu.
        uint8_t veri[18] = {0};
        uint8_t payload_uzunluk = (uint8_t)min((int)cerceve_payload_uzunluk, 16);
        memcpy(veri, cerceve_payload, payload_uzunluk);

        // FIX: eskiden bilinmeyen HER tip (orn. TIP_ORIGIN, TIP_GOREV)
        // sessizce TIP_KOMUT'a donusturulup joystick sanilarak gonderiliyordu.
        // TX DRONE'daki acik whitelist+reddet yaklasimiyla tutarli: TIP_KOMUT
        // kendi (daha siki) joystick hiz sinirini korur, bilinen diger tipler
        // ait olduklari tiple gonderilir, taninmayan tip atilir.
        if (tip_byte == TIP_KOMUT) {
            if (simdi - son_joystick_ms >= JOYSTICK_MIN_ARALIK_MS) {
                son_joystick_ms = simdi;
                if (simdi - son_mesh_gonderim_ms >= MESH_GONDERIM_MIN_MS) {
                    son_mesh_gonderim_ms = simdi;
                    mesh_gonder(veri, TIP_KOMUT);
                }
            }
        } else if (tip_byte == TIP_RENK  || tip_byte == TIP_DURUM ||
                   tip_byte == TIP_SWARM_STATE || tip_byte == TIP_QR_DATA ||
                   tip_byte == TIP_ORIGIN || tip_byte == TIP_GOREV) {
            if (simdi - son_mesh_gonderim_ms >= MESH_GONDERIM_MIN_MS) {
                son_mesh_gonderim_ms = simdi;
                mesh_gonder(veri, tip_byte);
            }
        }
        // else: taninmayan tip - sessizce atilir. TIP_LEADER_HB/TIP_ELECTION
        // bilerek dahil edilmedi: BASE, drone consensus'una taraf degil.
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
