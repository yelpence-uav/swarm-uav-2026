#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"

// ===== FORWARD DECLARATIONS =====
void durum_gonder(uint8_t durum);
#define RPI_RX_PIN 18 // Pinleri kartiniza gore degistirin
#define RPI_TX_PIN 19

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


// ===== COBS DECODE (TX DRONE — Serial1 okuma icin) =====
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

// ===== UART PAKET GONDER (Serial1 → RPi) =====
static void uart_gonder(uint8_t tip, uint8_t iha_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 16) return;
    uint8_t ham[20];
    uint8_t cobs_buf[32]; // FIX: Buffer boyutu genisletildi
    ham[0] = tip;
    ham[1] = iha_id;
    memcpy(&ham[2], payload, payload_uzunluk);
    uint16_t crc = crc16(ham, 2 + payload_uzunluk);
    ham[2 + payload_uzunluk]     = (crc >> 8) & 0xFF;
    ham[2 + payload_uzunluk + 1] =  crc & 0xFF;
    uint8_t toplam       = 2 + payload_uzunluk + 2;
    uint8_t cobs_uzunluk = cobs_encode(ham, toplam, cobs_buf);
    
    // FIX #6: Serial2 yerine Serial1 (RPi) uzerinden gonder
    Serial1.write(cobs_buf, cobs_uzunluk);
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

uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < 4; i++)
        if (_drone_id_tablo[i].mac_son == mac[5])
            return _drone_id_tablo[i].id;
    return 0;
}

// ===== MESH NODE COUNT =====
static uint8_t mesh_node_count() {
    uint8_t n = 0;
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
        if (_bilinen_nodlar[i].aktif &&
            millis() - _bilinen_nodlar[i].son_heartbeat_ms < NODE_TIMEOUT_MS)
            n++;
    return n;
}

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

// FIX #7: gorev_mesaj_t icine iha_id eklendi
struct gorev_mesaj_t {
    uint8_t tip;
    uint8_t iha_id;
    uint8_t payload[16];
};
static QueueHandle_t gorev_kuyruk = nullptr;

static_assert(sizeof(gorev_veri_t) <= 16, "gorev_veri_t 16 byte'i asiyor");
static_assert(sizeof(pose_veri_t)  <= 16, "pose_veri_t 16 byte'i asiyor");
static_assert(sizeof(durum_veri_t) <= 16, "durum_veri_t 16 byte'i asiyor");
static_assert(sizeof(renk_veri_t)  <= 16, "renk_veri_t 16 byte'i asiyor");

// ===== GOREV ISLE =====
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
                    Serial.println("[GOREV] HATA: Inis alani bulunamadi! RTL baslatiliyor.");
#ifdef HAS_PIXHAWK
                    px4_mod_gonder(Serial2, PX4_CUSTOM_SUB_MODE_AUTO_RTL);
#else
                    Serial.println("[GOREV][LOG] RTL olurdu");
#endif
                    // BUG-B FIX: nullptr crash onlendi
                    durum_gonder(DURUM_AKTIF);
                }
            }
            break;
        default:
            Serial.printf("[GOREV] Bilinmeyen tip: %d\n", gorev->tip);
            break;
    }
}

// REPLAY KONTROL HELPER (FIX #4)
static inline bool mesh_replay_dogrula(const uint8_t* mac, const uint8_t* decrypted_baslik) {
    node_durum_t* node = _node_bul_veya_ekle(mac);
    if (!node) return false;
    return _replay_kontrol(node, (const anti_replay_t*)decrypted_baslik);
}

// ===== MESH CALLBACK =====
void mesh_veri_al(const mesh_paket_t* p) {
    uint8_t acik[22] = {0}; // FIX #2: Buffer 22 yapildi
    
    // FIX #1: Uzunluk (22) eklendi
    if (!aes_coz_gcm(p->sifreli_veri, 22, acik, p->iv, p->tag)) {
        return; 
    }

    // FIX #4: Replay Kontrolu
    if (!mesh_replay_dogrula(p->kaynak_mac, acik)) {
        Serial.println("[MESH] Replay/Eski Paket reddedildi!");
        return; 
    }

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);

    failsafe_reset();

    if (gorev_kuyruk) {
        gorev_mesaj_t msg = {};
        msg.tip = p->tip;
        msg.iha_id = mac_to_id(p->kaynak_mac); // FIX #7: Gonderenin MAC'i alindi
        
        // FIX #3: Ilk 6 byte atlandi
        memcpy(msg.payload, acik + sizeof(anti_replay_t), 16);
        
        if (xQueueSend(gorev_kuyruk, &msg, pdMS_TO_TICKS(5)) != pdPASS) {
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


// ===== MAVLINK DURUM DEGISKENLERI (Task 3) =====
#ifdef HAS_PIXHAWK
static uint8_t  mav_armed        = 0;
static uint8_t  mav_gps_fix_type = 0;
static uint8_t  mav_battery_pct  = 0;
static float    mav_battery_volt = 0.0f;
static uint8_t  mav_ekf_ok       = 0;
static uint8_t  mav_imu_ok       = 0;
static uint8_t  mav_mag_ok       = 0;
static uint8_t  mav_baro_ok      = 0;

static void pixhawk_mavlink_isle() {
    mavlink_message_t msg;
    mavlink_status_t  status;
    while (Serial2.available()) {
        uint8_t c = (uint8_t)Serial2.read();
        if (!mavlink_parse_char(MAVLINK_COMM_0, c, &msg, &status)) continue;
        switch (msg.msgid) {
            case MAVLINK_MSG_ID_HEARTBEAT: {
                mavlink_heartbeat_t hb;
                mavlink_msg_heartbeat_decode(&msg, &hb);
                mav_armed = (hb.base_mode & MAV_MODE_FLAG_SAFETY_ARMED) ? 1 : 0;
                break;
            }
            case MAVLINK_MSG_ID_SYS_STATUS: {
                mavlink_sys_status_t ss;
                mavlink_msg_sys_status_decode(&msg, &ss);
                mav_battery_volt = ss.voltage_battery / 1000.0f;
                mav_battery_pct  = (uint8_t)ss.battery_remaining;
                break;
            }
            case MAVLINK_MSG_ID_GPS_RAW_INT: {
                mavlink_gps_raw_int_t gps;
                mavlink_msg_gps_raw_int_decode(&msg, &gps);
                mav_gps_fix_type = gps.fix_type;
                break;
            }
            case MAVLINK_MSG_ID_EKF_STATUS_REPORT: {
                mavlink_ekf_status_report_t ekf;
                mavlink_msg_ekf_status_report_decode(&msg, &ekf);
                mav_ekf_ok  = ((ekf.flags & 0x1F) == 0x1F) ? 1 : 0;
                mav_imu_ok  = (ekf.flags & 0x01) ? 1 : 0;
                mav_mag_ok  = (ekf.flags & 0x02) ? 1 : 0;
                mav_baro_ok = (ekf.flags & 0x08) ? 1 : 0;
                break;
            }
            default: break;
        }
    }
}
#endif // HAS_PIXHAWK

// ===== DURUM GONDER — MAVLink degiskenleri ile (Task 3) =====
void durum_gonder(uint8_t durum) {
    durum_veri_t d = {};
    d.drone_id = DRONE_ID;
    d.durum    = durum;
#ifdef HAS_PIXHAWK
    d.armed        = mav_armed;
    d.gps_fix_type = mav_gps_fix_type;
    d.battery_pct  = mav_battery_pct;
    d.battery_volt = mav_battery_volt;
    d.ekf_ok       = mav_ekf_ok;
    d.imu_ok       = mav_imu_ok;
    d.mag_ok       = mav_mag_ok;
    d.baro_ok      = mav_baro_ok;
    d.rssi         = _son_rssi;
    d.mesh_link_ok = ((millis() - son_paket_ms) < NODE_TIMEOUT_MS) ? 1 : 0;
#else
    d.armed        = 0;
    d.gps_fix_type = 0;
    d.battery_pct  = 0;
    d.battery_volt = 0.0f;
    d.ekf_ok       = 0;
#endif
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

    // FIX #6: UART portlari ayrildi
#ifdef HAS_PIXHAWK
    Serial2.begin(57600, SERIAL_8N1, 16, 17); // Pixhawk
    Serial1.begin(115200, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN); // RPi
    Serial.println("[UART] Pixhawk (Serial2) ve RPi (Serial1) bagli");
#else
    Serial1.begin(115200, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN); // RPi
    Serial.println("[UART] Sadece RPi (Serial1) bagli");
#endif

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    son_paket_ms = millis();

    durum_gonder(DURUM_AKTIF);
    Serial.println("[MESH] Hazir");
}

#define MESH_GONDERIM_MIN_MS 50

// ===== LOOP =====
void loop() {
    mesh_loop();

    // MAVLink parse (Task 3)
#ifdef HAS_PIXHAWK
    pixhawk_mavlink_isle();
#endif

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

    // ===== Serial1 (RPi → Mesh) COBS OKUMA — Task 2 =====
    {
        static uint8_t  rpi_rx_buf[32];
        static uint8_t  rpi_rx_idx      = 0;
        static uint32_t son_rpi_mesh_ms = 0;
        uint8_t okunan = 0;
        while (Serial1.available() && okunan < 32) {
            uint8_t b = (uint8_t)Serial1.read();
            okunan++;
            if (b == 0x00) {
                if (rpi_rx_idx >= 4) {
                    uint8_t decoded[32] = {0};
                    uint8_t dec_len     = cobs_decode(rpi_rx_buf, rpi_rx_idx, decoded);
                    if (dec_len >= 5) {
                        uint8_t  veri_uzunluk = dec_len - 2;
                        uint16_t crc_hesap    = crc16(decoded, veri_uzunluk);
                        uint16_t crc_gelen    = ((uint16_t)decoded[veri_uzunluk] << 8)
                                              |  (uint16_t)decoded[veri_uzunluk + 1];
                        if (crc_hesap == crc_gelen) {
                            uint8_t tip_byte        = decoded[0];
                            uint8_t payload[16]     = {0};
                            uint8_t payload_uzunluk = (uint8_t)min((int)veri_uzunluk - 2, 16);
                            memcpy(payload, &decoded[2], payload_uzunluk);
                            uint32_t simdi = millis();
                            if (simdi - son_rpi_mesh_ms >= MESH_GONDERIM_MIN_MS) {
                                if (tip_byte == TIP_RENK) {
                                    son_rpi_mesh_ms = simdi;
                                    renk_veri_t* rv = (renk_veri_t*)payload;
                                    renk_alani_kaydet(rv->renk, rv->lat, rv->lon);
                                    mesh_gonder(payload, TIP_RENK);
                                } else if (tip_byte == TIP_KOMUT) {
                                    son_rpi_mesh_ms = simdi;
                                    mesh_gonder(payload, TIP_KOMUT);
                                } else if (tip_byte == TIP_ORIGIN) {
                                    son_rpi_mesh_ms = simdi;
                                    mesh_gonder(payload, TIP_ORIGIN);
                                }
                            }
                        }
                    }
                }
                rpi_rx_idx = 0;
            } else {
                if (rpi_rx_idx < sizeof(rpi_rx_buf))
                    rpi_rx_buf[rpi_rx_idx++] = b;
            }
        }
    }

    // ===== KUYRUKTAN ISLE =====
    gorev_mesaj_t gelen;
    while (xQueueReceive(gorev_kuyruk, &gelen, 0) == pdPASS) {
        if (gelen.tip == TIP_GOREV) {
            gorev_isle((gorev_veri_t*)gelen.payload);
            uart_gonder(TIP_GOREV, gelen.iha_id, gelen.payload, sizeof(gorev_veri_t));
        } else if (gelen.tip == TIP_KOMUT) {
            Serial.printf("[KOMUT] %s\n", (char*)gelen.payload);
            uart_gonder(TIP_KOMUT, gelen.iha_id, gelen.payload, sizeof(gorev_veri_t));
        } else if (gelen.tip == TIP_POSE) {
            uart_gonder(TIP_POSE, gelen.iha_id, gelen.payload, sizeof(pose_veri_t));
        } else if (gelen.tip == TIP_RENK) {
            renk_veri_t* renk = (renk_veri_t*)gelen.payload;
            renk_alani_kaydet(renk->renk, renk->lat, renk->lon);
            uart_gonder(TIP_RENK, gelen.iha_id, gelen.payload, sizeof(renk_veri_t));
        } else if (gelen.tip == TIP_DURUM) {
            uart_gonder(TIP_DURUM, gelen.iha_id, gelen.payload, sizeof(durum_veri_t));
        } else if (gelen.tip == TIP_ORIGIN) {
            uart_gonder(TIP_ORIGIN, gelen.iha_id, gelen.payload, 16);
        }
    }

    static uint32_t son_pose = 0;
    if (millis() - son_pose >= 100) {
        son_pose = millis();
        pose_gonder();
    }
}
