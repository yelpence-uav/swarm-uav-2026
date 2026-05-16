#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"

volatile unsigned long son_paket_ms        = 0;
bool          failsafe_tetiklendi  = false;
uint8_t       _failsafe_asama      = 0;
volatile uint8_t ardisik_kayip_sayisi = 0;
uint8_t       failsafe_active_mode = APM_MODE_RTL;

// Drone ID MAC adresinin son byte'indan otomatik atanir
static const struct { uint8_t mac_son; uint8_t id; } _drone_id_tablo[] = {
    {0xB4, 1},
    {0x88, 2},
    {0x00, 3},
    {0xFF, 4},
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
    DRONE_ID = mac[5];
    Serial.printf("[DRONE] ID bilinmiyor, MAC son byte: %d\n", DRONE_ID);
}

// ===== RENK ALANI KAYIT =====
// Şartname: rota üzerindeki kırmızı/mavi alanlar kameradan tespit edilip kaydedilmeli
#define MAX_RENK_ALANI 8
struct {
    uint8_t  renk;
    int32_t  lat;
    int32_t  lon;
    bool     dolu;
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

// ===== GOREV İŞLEME =====
void gorev_isle(const gorev_veri_t* gorev) {
    switch (gorev->tip) {

        case GOREV_FORMASYON:
            Serial.printf("[GOREV] Formasyon degisimi: tip=%d\n", gorev->param1);
            // param1: FORMASYON_OKBASI / FORMASYON_V / FORMASYON_CIZGI
#ifdef HAS_PIXHAWK
            // TODO: Suru algoritmasi formasyon guncelle
#endif
            break;

        case GOREV_MANEVRA:
            Serial.printf("[GOREV] Manevra: pitch=%d roll=%d\n",
                gorev->param1, gorev->param2);
            // param1: pitch derece, param2: roll derece
            // Suru merkezi sabit tutularak formasyon egim yapar
#ifdef HAS_PIXHAWK
            // TODO: MAVLink SET_POSITION_TARGET ile uygula
#endif
            break;

        case GOREV_IRTIFA:
            Serial.printf("[GOREV] Irtifa degisimi: %d cm\n", gorev->param1);
            // param1: hedef irtifa (metre)
#ifdef HAS_PIXHAWK
            // TODO: MAVLink ile irtifa komutu gonder
#endif
            break;

        case GOREV_AYRIL:
            Serial.printf("[GOREV] Suruden ayril: drone_id=%d renk=%d\n",
                gorev->param1, gorev->param2);
            // param1: ayrilacak drone ID
            // param2: inis yapilacak renk (RENK_KIRMIZI / RENK_MAVI)
            if (gorev->param1 == DRONE_ID) {
                // Bu drone ayrılacak — renk alanını bul ve in
                bool inis_bulundu = false;
                for (uint8_t i = 0; i < MAX_RENK_ALANI; i++) {
                    if (renk_alanlari[i].dolu &&
                        renk_alanlari[i].renk == (uint8_t)gorev->param2) {
                        Serial.printf("[GOREV] Inis alani: lat:%ld lon:%ld\n",
                            renk_alanlari[i].lat, renk_alanlari[i].lon);
#ifdef HAS_PIXHAWK
                        // TODO: MAVLink ile inis noktasina git ve in
#endif
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

// ===== MESH CALLBACK =====
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[16] = {0};
    aes_coz_iv(p->sifreli_veri, acik, p->paket_id);
    failsafe_reset();

    if (p->tip == TIP_GOREV) {
        gorev_veri_t* gorev = (gorev_veri_t*)acik;
        gorev_isle(gorev);
    }
    else if (p->tip == TIP_KOMUT) {
        Serial.printf("[KOMUT] %s\n", (char*)acik);
#ifdef HAS_PIXHAWK
        // TODO: MAVLink ile Pixhawk'a ilet
#endif
    }
    else if (p->tip == TIP_POSE) {
        pose_veri_t* pose = (pose_veri_t*)acik;
        Serial.printf("[POSE] Kaynak:%02X:%02X:%02X:%02X:%02X:%02X lat:%ld lon:%ld alt:%d\n",
            p->kaynak_mac[0], p->kaynak_mac[1], p->kaynak_mac[2],
            p->kaynak_mac[3], p->kaynak_mac[4], p->kaynak_mac[5],
            pose->lat, pose->lon, pose->alt_cm);
    }
    else if (p->tip == TIP_RENK) {
        // Şartname: rota üzerinde renk alanı tespit edildi, kaydet
        renk_veri_t* renk = (renk_veri_t*)acik;
        renk_alani_kaydet(renk->renk, renk->lat, renk->lon);
    }
    else if (p->tip == TIP_DURUM) {
        durum_veri_t* durum = (durum_veri_t*)acik;
        Serial.printf("[DURUM] Drone:%d durum:%d\n",
            durum->drone_id, durum->durum);
    }
}

// ===== POSE GONDER =====
void pose_gonder() {
    pose_veri_t pose = {};

#ifdef HAS_PIXHAWK
    // TODO: Pixhawk'tan MAVLink ile GPS oku
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
    Serial.printf("[DRONE] ID:%d HAZIR\n", DRONE_ID);

#ifdef HAS_PIXHAWK
    Serial2.begin(57600, SERIAL_8N1, 16, 17);
    Serial.println("[UART] Pixhawk bagli");
#else
    Serial.println("[UART] Test modu");
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
            ardisik_kayip_sayisi++;
            portEXIT_CRITICAL(&_recv_mux);
        }
    }

#ifdef HAS_PIXHAWK
    failsafe_kontrol(Serial2);
#else
    failsafe_kontrol_log();
#endif

    // 10Hz pose gonder
    static uint32_t son_pose = 0;
    if (millis() - son_pose >= 100) {
        son_pose = millis();
        pose_gonder();
    }
}
