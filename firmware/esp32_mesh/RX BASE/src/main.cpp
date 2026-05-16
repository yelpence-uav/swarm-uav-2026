#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"

volatile unsigned long son_paket_ms = 0;
bool   failsafe_tetiklendi  = false;
uint8_t _failsafe_asama     = 0;
volatile uint8_t ardisik_kayip_sayisi = 0;
uint8_t failsafe_active_mode = APM_MODE_RTL;

// ===== DRONE ID ESLESTIRME =====
// MAC'in son byte'ina gore IHA numarasi
struct { uint8_t mac_son; uint8_t id; } drone_tablo[] = {
    {0xB4, 1},
    {0x88, 2},
    {0x00, 3},
    {0xFF, 4},
};

uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < 4; i++)
        if (drone_tablo[i].mac_son == mac[5])
            return drone_tablo[i].id;
    return 0; // bilinmiyor
}

// ===== JOYSTICK LIMIT =====
#define JOYSTICK_MIN_ARALIK_MS 200  // 5Hz
static uint32_t son_joystick_ms = 0;

// ===== MESH CALLBACK =====
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[16] = {0};
    aes_coz_iv(p->sifreli_veri, acik, p->paket_id);
    ardisik_kayip_sayisi = 0;
    failsafe_reset();

    char mac_str[18];
    snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
        p->kaynak_mac[0], p->kaynak_mac[1], p->kaynak_mac[2],
        p->kaynak_mac[3], p->kaynak_mac[4], p->kaynak_mac[5]);

    uint8_t iha_id = mac_to_id(p->kaynak_mac);
    uint32_t ts    = millis();

    if (p->tip == TIP_POSE) {
        pose_veri_t* pose = (pose_veri_t*)acik;
        Serial.printf("{\"tip\":\"POSE\",\"id\":%d,\"mac\":\"%s\",\"lat\":%ld,\"lon\":%ld,\"alt\":%d,\"hdg\":%d,\"vx\":%d,\"vy\":%d,\"ts\":%lu}\n",
            iha_id, mac_str, pose->lat, pose->lon, pose->alt_cm,
            pose->heading, pose->vx, pose->vy, ts);
    }
    else if (p->tip == TIP_GOREV) {
        gorev_veri_t* gorev = (gorev_veri_t*)acik;
        Serial.printf("{\"tip\":\"GOREV\",\"id\":%d,\"mac\":\"%s\",\"gorev_tip\":%d,\"param1\":%d,\"param2\":%d,\"ts\":%lu}\n",
            iha_id, mac_str, gorev->tip, gorev->param1, gorev->param2, ts);
    }
    else if (p->tip == TIP_RENK) {
        renk_veri_t* renk = (renk_veri_t*)acik;
        Serial.printf("{\"tip\":\"RENK\",\"id\":%d,\"mac\":\"%s\",\"renk\":%d,\"lat\":%ld,\"lon\":%ld,\"ts\":%lu}\n",
            iha_id, mac_str, renk->renk, renk->lat, renk->lon, ts);
    }
    else if (p->tip == TIP_DURUM) {
        durum_veri_t* durum = (durum_veri_t*)acik;
        Serial.printf("{\"tip\":\"DURUM\",\"id\":%d,\"mac\":\"%s\",\"drone_id\":%d,\"durum\":%d,\"ts\":%lu}\n",
            iha_id, mac_str, durum->drone_id, durum->durum, ts);
    }
    else if (p->tip == TIP_TELEMETRI) {
        Serial.printf("{\"tip\":\"TELEMETRI\",\"id\":%d,\"mac\":\"%s\",\"veri\":\"%s\",\"ts\":%lu}\n",
            iha_id, mac_str, (char*)acik, ts);
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("{\"tip\":\"SISTEM\",\"durum\":\"RX BASE HAZIR\"}");

#ifdef HAS_PIXHAWK
    Serial2.begin(57600, SERIAL_8N1, 16, 17);
    Serial.println("{\"tip\":\"SISTEM\",\"durum\":\"PIXHAWK BAGLI\"}");
#endif

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    son_paket_ms = millis();
    Serial.println("{\"tip\":\"SISTEM\",\"durum\":\"MESH HAZIR\"}");
}

void loop() {
    mesh_loop();

    // Ardisik kayip sayaci
    static uint32_t son_kayip_kontrol = 0;
    if (millis() - son_kayip_kontrol >= 100) {
        son_kayip_kontrol = millis();
        if (millis() - son_paket_ms > 150) {
            portENTER_CRITICAL(&_recv_mux);
            ardisik_kayip_sayisi++;
            portEXIT_CRITICAL(&_recv_mux);
        }
    }

#ifdef HAS_PIXHAWK
    failsafe_kontrol(Serial2);
#else
    failsafe_kontrol_log();
#endif

    // Failsafe durumunu YKI'ye bildir
    static bool son_failsafe = false;
    if (failsafe_tetiklendi != son_failsafe) {
        son_failsafe = failsafe_tetiklendi;
        Serial.printf("{\"tip\":\"FAILSAFE\",\"failsafe_aktif\":%d,\"ts\":%lu}\n",
            failsafe_tetiklendi ? 1 : 0, millis());
    }

    // YKI'den gelen komutlari oku — 5Hz limit
    if (Serial.available()) {
        String komut = Serial.readStringUntil('\n');
        komut.trim();
        if (komut.length() > 0) {
            uint32_t simdi = millis();
            if (simdi - son_joystick_ms >= JOYSTICK_MIN_ARALIK_MS) {
                son_joystick_ms = simdi;
                uint8_t veri[16] = {0};
                komut.getBytes(veri, 15);
                mesh_gonder(veri, TIP_KOMUT);
            }
        }
    }

    // Mesh durum raporu — 5 saniyede bir
    static uint32_t son_durum = 0;
    if (millis() - son_durum >= 5000) {
        son_durum = millis();
        uint8_t aktif = 0;
        for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
            if (_bilinen_nodlar[i].aktif) aktif++;
        Serial.printf("{\"tip\":\"MESH_DURUM\",\"aktif\":%d,\"maks\":%d,\"ts\":%lu}\n",
            aktif, MESH_MAX_NODES, millis());
    }
}
