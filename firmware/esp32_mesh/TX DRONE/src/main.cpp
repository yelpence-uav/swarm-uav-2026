#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"

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

// ===== UART PAKET GONDER (Serial2 → RPi) =====
static void uart_gonder(uint8_t tip, uint8_t iha_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 16) return;
    uint8_t ham[20];
    uint8_t cobs_buf[25];
    ham[0] = tip;
    ham[1] = iha_id;
    memcpy(&ham[2], payload, payload_uzunluk);
    uint16_t crc = crc16(ham, 2 + payload_uzunluk);
    ham[2 + payload_uzunluk]     = (crc >> 8) & 0xFF;
    ham[2 + payload_uzunluk + 1] =  crc & 0xFF;
    uint8_t toplam       = 2 + payload_uzunluk + 2;
    uint8_t cobs_uzunluk = cobs_encode(ham, toplam, cobs_buf);
    Serial2.write(cobs_buf, cobs_uzunluk);
}

volatile unsigned long   son_paket_ms         = 0;
bool                     failsafe_tetiklendi  = false;
uint8_t                  _failsafe_asama      = 0;
volatile uint8_t         ardisik_kayip_sayisi = 0;
uint8_t                  failsafe_active_mode = APM_MODE_RTL;

// ===== DRONE ID =====
static const struct { uint8_t mac_son; uint8_t id; } _drone_id_tablo[] = {
    {0xB4, 1}, {0x88, 2}, {0x00, 3}, {0xFF, 4},
};
static uint8_t DRONE_ID = 0;

void drone_id_ata() {
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    for (uint8_t i = 0; i < 4; i++) {
        if (_drone_id_tablo[i].mac_son == mac[5]) {
            DRONE_ID = _drone_id_tablo[i].id;
            Serial.printf("[DRONE] ID atandi: %d\n", DRONE_ID);
            return;
        }
    }
    DRONE_ID = 0xFF;
    Serial.printf("[DRONE] UYARI: Bilinmeyen MAC 0x%02X, gorev almayacak\n", mac[5]);
}

// ===== RENK ALANI =====
#define MAX_RENK_ALANI 8
struct {
    uint8_t renk;
    int32_t lat;
    int32_t lon;
    bool    dolu;
} renk_alanlari[MAX_RENK_ALANI] = {};

void renk_alani_kaydet(uint8_t renk, int32_t lat, int32_t lon) {
    for (uint8_t i = 0; i < MAX_RENK_ALANI; i++) {
        if (!renk_alanlari[i].dolu) {
            renk_alanlari[i].renk = renk;
            renk_alanlari[i].lat  = lat;
            renk_alanlari[i].lon  = lon;
            renk_alanlari[i].dolu = true;
            Serial.printf("[RENK] Kaydedildi: %s lat:%ld lon:%ld\n",
                renk == RENK_KIRMIZI ? "KIRMIZI" : "MAVI", lat, lon);
            return;
        }
    }
    Serial.println("[RENK] UYARI: Alan tablosu dolu!");
}

// ===== FREERTOS QUEUE =====
struct gorev_mesaj_t {
    uint8_t tip;
    uint8_t payload[16];
};
static QueueHandle_t gorev_kuyruk = nullptr;

static_assert(sizeof(gorev_veri_t) <= 16, "gorev_veri_t 16 byte'i asiyor");
static_assert(sizeof(pose_veri_t)  <= 16, "pose_veri_t 16 byte'i asiyor");
static_assert(sizeof(durum_veri_t) <= 16, "durum_veri_t 16 byte'i asiyor");
static_assert(sizeof(renk_veri_t)  <= 16, "renk_veri_t 16 byte'i asiyor");

// ===== GOREV ISLE - loop() icinde calisir =====
void gorev_isle(const gorev_veri_t* gorev) {
    switch (gorev->tip) {
        case GOREV_FORMASYON:
            Serial.printf("[GOREV] Formasyon: tip=%d\n", gorev->param1);
            break;
        case GOREV_MANEVRA:
            Serial.printf("[GOREV] Manevra: pitch=%d roll=%d\n",
                gorev->param1, gorev->param2);
            break;
        case GOREV_IRTIFA:
            Serial.printf("[GOREV] Irtifa: %d cm\n", gorev->param1);
            break;
        case GOREV_AYRIL:
            if (DRONE_ID == 0xFF) {
                Serial.println("[GOREV] Bilinmeyen drone, komut reddedildi");
                break;
            }
            Serial.printf("[GOREV] Suruden ayril: drone_id=%d renk=%d\n",
                gorev->param1, gorev->param2);
            if (gorev->param1 == DRONE_ID) {
                bool inis_bulundu = false;
                for (uint8_t i = 0; i < MAX_RENK_ALANI; i++) {
                    if (renk_alanlari[i].dolu &&
                        renk_alanlari[i].renk == (uint8_t)gorev->param2) {
                        Serial.printf("[GOREV] Inis alani: lat:%ld lon:%ld\n",
                            renk_alanlari[i].lat, renk_alanlari[i].lon);
                        inis_bulundu = true;
                        break;
                    }
                }
                if (inis_bulundu) {
                    durum_veri_t d = {};
                    d.drone_id = DRONE_ID;
                    d.durum    = DURUM_AYRILDI;
                    uint8_t veri[16] = {0};
                    memcpy(veri, &d, sizeof(durum_veri_t));
                    mesh_gonder(veri, TIP_DURUM);
                } else {
                    Serial.println("[GOREV] HATA: Inis alani bulunamadi!");
                }
            }
            break;
        default:
            Serial.printf("[GOREV] Bilinmeyen tip: %d\n", gorev->tip);
            break;
    }
}

// ===== MESH CALLBACK - sadece kuyruga yaz =====
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[16] = {0};
    aes_coz_iv(p->sifreli_veri, acik, p->paket_id);

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);

    failsafe_reset();

    if (gorev_kuyruk) {
        gorev_mesaj_t msg = {};
        msg.tip = p->tip;
        memcpy(msg.payload, acik, 16);
        if (xQueueSend(gorev_kuyruk, &msg, 0) != pdPASS) {
            static volatile uint32_t _kuyruk_dolu_sayisi = 0;
            _kuyruk_dolu_sayisi++;
        }
    }
}

// ===== POSE GONDER =====
void pose_gonder() {
    pose_veri_t pose = {};
#ifdef HAS_PIXHAWK
    // TODO: Pixhawk MAVLink GPS oku
#else
    static int32_t test_lat = 411234567;
    static int32_t test_lon = 291234567;
    test_lat += 10;
    pose.lat     = test_lat;
    pose.lon     = test_lon;
    pose.alt_cm  = 1500;
    pose.heading = 900;
    pose.vx      = 0;
    pose.vy      = 0;
#endif
    uint8_t veri[16] = {0};
    memcpy(veri, &pose, sizeof(pose_veri_t));
    mesh_gonder(veri, TIP_POSE);
}

// ===== DURUM GONDER =====
void durum_gonder(uint8_t durum) {
    durum_veri_t d = {};
    d.drone_id = DRONE_ID;
    d.durum    = durum;
    uint8_t veri[16] = {0};
    memcpy(veri, &d, sizeof(durum_veri_t));
    mesh_gonder(veri, TIP_DURUM);
}

// ===== SETUP =====
void setup() {
    Serial.begin(115200);
    delay(1000);
    drone_id_ata();

    gorev_kuyruk = xQueueCreate(10, sizeof(gorev_mesaj_t));
    if (!gorev_kuyruk) {
        Serial.println("[HATA] Kuyruk olusturulamadi!");
    }

    Serial.printf("[DRONE] ID:%d HAZIR\n", DRONE_ID);

#ifdef HAS_PIXHAWK
    Serial2.begin(57600, SERIAL_8N1, 16, 17);
    Serial.println("[UART] Pixhawk bagli");
#else
    Serial2.begin(57600, SERIAL_8N1, 16, 17);
    Serial.println("[UART] RPi bagli");
#endif

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    son_paket_ms = millis();

    durum_gonder(DURUM_AKTIF);
    Serial.println("[MESH] Hazir");
}

// ===== LOOP =====
void loop() {
    mesh_loop();

    // Ardisik kayip sayaci
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
    failsafe_kontrol(Serial2);
#else
    failsafe_kontrol_log();
#endif

    // ===== KUYRUKTAN ISLE =====
    gorev_mesaj_t gelen;
    while (xQueueReceive(gorev_kuyruk, &gelen, 0) == pdPASS) {
        if (gelen.tip == TIP_GOREV) {
            gorev_isle((gorev_veri_t*)gelen.payload);
        }
        else if (gelen.tip == TIP_KOMUT) {
            Serial.printf("[KOMUT] %s\n", (char*)gelen.payload);
        }
        else if (gelen.tip == TIP_POSE) {
            uart_gonder(TIP_POSE, DRONE_ID, gelen.payload, sizeof(pose_veri_t));
        }
        else if (gelen.tip == TIP_RENK) {
            renk_veri_t* renk = (renk_veri_t*)gelen.payload;
            renk_alani_kaydet(renk->renk, renk->lat, renk->lon);
        }
        else if (gelen.tip == TIP_DURUM) {
            uart_gonder(TIP_DURUM, DRONE_ID, gelen.payload, sizeof(durum_veri_t));
        }
    }

    // 10Hz pose gonder
    static uint32_t son_pose = 0;
    if (millis() - son_pose >= 100) {
        son_pose = millis();
        pose_gonder();
    }
}
