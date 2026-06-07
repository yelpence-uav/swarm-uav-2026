#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "rtk_sender.h"

// ===== CRC16-CCITT =====
static uint16_t crc16(const uint8_t* veri, uint8_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

// ===== COBS ENCODE =====
static uint8_t cobs_encode(const uint8_t* giris, uint8_t uzunluk, uint8_t* cikis) {
    uint8_t kod_idx = 0;
    uint8_t yaz_idx = 1;
    uint8_t kod     = 1;
    for (uint8_t i = 0; i < uzunluk; i++) {
        if (giris[i] != 0x00) {
            cikis[yaz_idx++] = giris[i];
            kod++;
            if (kod == 0xFF) {
                cikis[kod_idx] = kod;
                kod_idx = yaz_idx;
                cikis[yaz_idx++] = 0x01;
                kod = 1;
            }
        } else {
            cikis[kod_idx] = kod;
            kod_idx = yaz_idx;
            cikis[yaz_idx++] = 0x01;
            kod = 1;
        }
    }
    cikis[kod_idx] = kod;
    cikis[yaz_idx++] = 0x00;
    return yaz_idx;
}

// ===== COBS DECODE =====
static uint8_t cobs_decode(const uint8_t* giris, uint8_t uzunluk, uint8_t* cikis) {
    if (uzunluk == 0) return 0;
    uint8_t oku_idx = 0;
    uint8_t yaz_idx = 0;
    while (oku_idx < uzunluk) {
        uint8_t kod = giris[oku_idx++];
        if (kod == 0) return 0;
        for (uint8_t i = 1; i < kod; i++) {
            if (oku_idx >= uzunluk) return 0;
            cikis[yaz_idx++] = giris[oku_idx++];
        }
        if (kod < 0xFF && oku_idx < uzunluk)
            cikis[yaz_idx++] = 0x00;
    }
    return yaz_idx;
}

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

    ham[0] = tip;
    ham[1] = iha_id;
    memcpy(&ham[2], payload, payload_uzunluk);

    uint16_t crc = crc16(ham, 2 + payload_uzunluk);
    ham[2 + payload_uzunluk]     = (crc >> 8) & 0xFF;
    ham[2 + payload_uzunluk + 1] =  crc & 0xFF;

    uint8_t toplam       = 2 + payload_uzunluk + 2;
    uint8_t cobs_uzunluk = cobs_encode(ham, toplam, cobs_buf);
    Serial.write(cobs_buf, cobs_uzunluk);
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
static const struct { uint8_t mac_son; uint8_t id; } drone_tablo[] = {
    {0xB4, 1}, {0x88, 2}, {0x00, 3}, {0xFF, 4},
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);

uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < DRONE_SAYISI; i++)
        if (drone_tablo[i].mac_son == mac[5])
            return drone_tablo[i].id;
    return 0;
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
    
    // FIX #1: Uzunluk (22) parametresi eklendi
    if (!aes_coz_gcm(p->sifreli_veri, 24, acik, p->iv, p->tag)) {
        return; 
    }

    // FIX #4: Replay kontrolu
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
    msg.iha_id = mac_to_id(p->kaynak_mac);
    if (msg.iha_id == 0) {
        Serial.println("[MESH] Bilinmeyen MAC, paket reddedildi");
        return;
    }

    if      (p->tip == TIP_POSE)      msg.uzunluk = sizeof(pose_veri_t);
    else if (p->tip == TIP_GOREV)     msg.uzunluk = sizeof(gorev_veri_t);
    else if (p->tip == TIP_RENK)      msg.uzunluk = sizeof(renk_veri_t);
    else if (p->tip == TIP_DURUM)     msg.uzunluk = sizeof(durum_veri_t);
    else if (p->tip == TIP_TELEMETRI)  msg.uzunluk = 16;
    else if (p->tip == TIP_LEADER_HB)  msg.uzunluk = sizeof(leader_hb_veri_t);
    else if (p->tip == TIP_ELECTION)   msg.uzunluk = sizeof(election_veri_t);
    else if (p->tip == TIP_VERSION)    msg.uzunluk = sizeof(version_veri_t);
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


    uart_kuyruk = xQueueCreate(20, sizeof(uart_mesaj_t));
    sistem_mesaj("RX BASE HAZIR");

#ifdef HAS_PIXHAWK
    Serial2.begin(57600, SERIAL_8N1, 16, 17);
    sistem_mesaj("PIXHAWK BAGLI");
#endif

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    // Watchdog: 8 saniye — loop donerse ESP32 reset atar
    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);
    son_paket_ms = millis();
    sistem_mesaj("MESH HAZIR");
}

void loop() {
    rtk_loop();
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

#ifdef HAS_PIXHAWK
    failsafe_kontrol();
#else
    failsafe_kontrol_log();
#endif

    static bool son_failsafe = false;
    if (failsafe_tetiklendi != son_failsafe) {
        son_failsafe = failsafe_tetiklendi;
        uint8_t buf[16] = {0};
        buf[0] = failsafe_tetiklendi ? 1 : 0;
        uart_gonder(0xFE, 0x00, buf, 16);
    }

    uart_mesaj_t gelen;
    while (xQueueReceive(uart_kuyruk, &gelen, 0) == pdPASS) {
        uart_gonder(gelen.tip, gelen.iha_id, gelen.payload, gelen.uzunluk);
    }

    static uint8_t rx_buf[32];
    static uint8_t rx_idx = 0;
    uint8_t okunan = 0;
    while (Serial.available() && okunan < 32) {
        uint8_t b = Serial.read();
        okunan++;
        if (b == 0x00) {
            if (rx_idx >= 4) {
                uint8_t decoded[32] = {0};
                uint8_t decoded_uzunluk = cobs_decode(rx_buf, rx_idx, decoded);
                if (decoded_uzunluk >= 5) {
                    uint8_t veri_uzunluk = decoded_uzunluk - 2;
                    uint16_t crc_hesap   = crc16(decoded, veri_uzunluk);
                    uint16_t crc_gelen   = ((uint16_t)decoded[veri_uzunluk] << 8)
                                         |  (uint16_t)decoded[veri_uzunluk + 1];
                    if (crc_hesap == crc_gelen) {
                        uint8_t tip_byte = decoded[0];
                        uint32_t simdi   = millis();
                        uint8_t veri[16] = {0};
                        uint8_t payload_uzunluk = min((int)veri_uzunluk - 2, 16);
                        memcpy(veri, &decoded[2], payload_uzunluk);

                        if (tip_byte == TIP_RENK) {
                            if (simdi - son_mesh_gonderim_ms >= MESH_GONDERIM_MIN_MS) {
                                son_mesh_gonderim_ms = simdi;
                                mesh_gonder(veri, TIP_RENK);
                            }
                        } else if (tip_byte == TIP_DURUM) {
                            if (simdi - son_mesh_gonderim_ms >= MESH_GONDERIM_MIN_MS) {
                                son_mesh_gonderim_ms = simdi;
                                mesh_gonder(veri, TIP_DURUM);
                            }
                        } else {
                            if (simdi - son_joystick_ms >= JOYSTICK_MIN_ARALIK_MS) {
                                son_joystick_ms = simdi;
                                if (simdi - son_mesh_gonderim_ms >= MESH_GONDERIM_MIN_MS) {
                                    son_mesh_gonderim_ms = simdi;
                                    mesh_gonder(veri, TIP_KOMUT);
                                }
                            }
                        }
                    }
                }
            }
            rx_idx = 0;
        } else {
            if (rx_idx < sizeof(rx_buf))
                rx_buf[rx_idx++] = b;
        }
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
