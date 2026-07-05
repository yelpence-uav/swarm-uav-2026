#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"

#define RPI_RX_PIN 18
#define RPI_TX_PIN 19

static uint16_t crc16(const uint8_t* veri, uint8_t uzunluk) {
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < uzunluk; i++) {
        crc ^= (uint16_t)veri[i] << 8;
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

static uint8_t cobs_encode(const uint8_t* giris, uint8_t uzunluk, uint8_t* cikis) {
    uint8_t kod_idx = 0, yaz_idx = 1, kod = 1;
    for (uint8_t i = 0; i < uzunluk; i++) {
        if (giris[i] != 0x00) {
            cikis[yaz_idx++] = giris[i];
            if (++kod == 0xFF) {
                cikis[kod_idx] = kod; kod_idx = yaz_idx;
                cikis[yaz_idx++] = 0x01; kod = 1;
            }
        } else {
            cikis[kod_idx] = kod; kod_idx = yaz_idx;
            cikis[yaz_idx++] = 0x01; kod = 1;
        }
    }
    cikis[kod_idx] = kod;
    cikis[yaz_idx++] = 0x00;
    return yaz_idx;
}

static uint8_t cobs_decode(const uint8_t* giris, uint8_t uzunluk, uint8_t* cikis) {
    if (uzunluk == 0) return 0;
    uint8_t oku_idx = 0, yaz_idx = 0;
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

static void uart_gonder(uint8_t tip, uint8_t kaynak_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;
    uint8_t ham[24];
    uint8_t cobs_buf[32];
    ham[0] = tip;
    ham[1] = kaynak_id;
    memcpy(&ham[2], payload, payload_uzunluk);
    uint16_t crc = crc16(ham, 2 + payload_uzunluk);
    ham[2 + payload_uzunluk]     = (crc >> 8) & 0xFF;
    ham[2 + payload_uzunluk + 1] =  crc & 0xFF;
    uint8_t toplam       = 2 + payload_uzunluk + 2;
    uint8_t cobs_uzunluk = cobs_encode(ham, toplam, cobs_buf);
    Serial1.write(cobs_buf, cobs_uzunluk);
}

volatile unsigned long son_paket_ms         = 0;
bool                   failsafe_tetiklendi  = false;
uint8_t                _failsafe_asama      = 0;
volatile uint8_t       ardisik_kayip_sayisi = 0;
uint8_t                failsafe_active_mode = APM_MODE_RTL;
volatile bool          manevra_aktif        = false;
volatile uint32_t      manevra_bitis_ms     = 0;

// ===== DRONE ID ESLESTIRME =====
static const struct { uint8_t mac_son; uint8_t id; } drone_tablo[] = {
    {0xB4, 1}, {0x88, 2}, {0x00, 3}, {0xFF, 4},
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);
static uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < DRONE_SAYISI; i++)
        if (drone_tablo[i].mac_son == mac[5])
            return drone_tablo[i].id;
    return 0;
}
void mesh_veri_al(const mesh_paket_t* p) {
    // C1 fix: GCM + replay gecerse peer kaydet ve heartbeat guncelle
    // ORTA-1 fix: AAD (tip+kaynak_mac+hedef_mac) de dogrulanir
    uint8_t acik[24] = {0};
    uint8_t aad[13];
    _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, aad);
    if (!aes_coz_gcm(p->sifreli_veri, 24, acik, p->iv, p->tag, aad, sizeof(aad))) return;

    uint8_t kaynak_id = mac_to_id(p->kaynak_mac);
    if (kaynak_id == 0) {
        Serial.println("[MESH] Bilinmeyen MAC, paket reddedildi");
        return;
    }

    node_durum_t* node = _node_bul_veya_ekle(p->kaynak_mac);
    if (!node) return;
    if (!_replay_kontrol(node, (const anti_replay_t*)acik)) {
        Serial.println("[MESH] Replay reddedildi");
        return;
    }

    // GCM + replay gecti: peer kaydet, heartbeat guncelle
    if (!node->peer_kayitli) {
        _peer_ekle(p->kaynak_mac);
        node->peer_kayitli = true;
    }
    node->son_heartbeat_ms = millis();
    node->aktif = true;

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);
    failsafe_reset();
    // HEARTBEAT sadece node aktivasyonu icin — RPi'ya gonderilmez
    if (p->tip == TIP_HEARTBEAT) return;
    // #1 RTK: mesh fragment dogrudan rtk_handler'a yonlendir, RPi Serial1'den alir
    if (p->tip == TIP_RTK) {
        rtk_mesh_frag_handle(acik + sizeof(anti_replay_t), sizeof(rtk_mesh_frag_t));
        return;
    }

    uint8_t* payload = acik + sizeof(anti_replay_t);
    uint8_t uzunluk = 0;
    if      (p->tip == TIP_POSE)        uzunluk = sizeof(pose_veri_t);
    else if (p->tip == TIP_GOREV)       uzunluk = sizeof(gorev_veri_t);
    else if (p->tip == TIP_RENK)        uzunluk = sizeof(renk_veri_t);
    else if (p->tip == TIP_DURUM)       uzunluk = sizeof(durum_veri_t);
    else if (p->tip == TIP_LEADER_HB)   uzunluk = sizeof(leader_hb_veri_t);
    else if (p->tip == TIP_ELECTION)    uzunluk = sizeof(election_veri_t);
    else if (p->tip == TIP_VERSION)     uzunluk = sizeof(version_veri_t);
    else if (p->tip == TIP_SWARM_STATE) uzunluk = sizeof(swarm_state_veri_t);
    else if (p->tip == TIP_QR_DATA)     uzunluk = sizeof(qr_veri_t);
    else return; // bilinmeyen tip — gonderme
    uart_gonder(p->tip, kaynak_id, payload, uzunluk);
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("[ESP32] Basliyor...");

    Serial1.begin(115200, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);
    Serial.println("[UART] RPi (Serial1) bagli");

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
    son_paket_ms = millis();

    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);

    Serial.println("[ESP32] Hazir");
}

#define MESH_GONDERIM_MIN_MS 50



void loop() {
    rtk_loop();
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

    failsafe_kontrol();

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
                    uint8_t dec_len = cobs_decode(rpi_rx_buf, rpi_rx_idx, decoded);
                    if (dec_len >= 5) {
                        uint8_t  veri_uzunluk = dec_len - 2;
                        uint16_t crc_hesap    = crc16(decoded, veri_uzunluk);
                        uint16_t crc_gelen    = ((uint16_t)decoded[veri_uzunluk] << 8)
                                              |  (uint16_t)decoded[veri_uzunluk + 1];
                        if (crc_hesap == crc_gelen) {
                            uint8_t tip_byte        = decoded[0];
                            // ORTA-2 FIX: 16 -> 18. mesh_gonder() her zaman 18 byte
                            // okuyor (memcpy(tam_veri+6, veri, 18)); 16 byte'lik
                            // buffer'dan okumak 2 byte stack over-read'e (UB) yol
                            // aciyordu. Gercek payload struct'lari 16B oldugundan
                            // payload_uzunluk siniri (asagida) 16'da kaliyor;
                            // fazladan 2 byte sadece zaten-sifirlanmis dolgu.
                            uint8_t payload[18]     = {0};
                            uint8_t payload_uzunluk = (uint8_t)min((int)veri_uzunluk - 2, 16);
                            memcpy(payload, &decoded[2], payload_uzunluk);
                            // Whitelist: sadece Pi'den gelmesi beklenen tipler
                            // FIX: TIP_LEADER_HB ve TIP_ELECTION eksikti. Bu ikisi
                            // mesh->RPi yonunde (yukarida satir 140-141) taniniyordu
                            // ama RPi->mesh yonunde reddediliyordu; yani her drone
                            // KENDI leader-heartbeat/election mesajini hic gonderemiyor,
                            // sadece BASKALARININKINI alabiliyordu. Sonuc: gercek
                            // donanimda (ESP-NOW uzerinden) consensus hic yayilamiyor,
                            // her ajan kendini yalniz saniyor -> split-brain. Sim'de
                            // muhtemelen ROS2/DDS uzerinden dogrudan gorusuldugu icin
                            // bu whitelist hic devreye girmiyor, bu yuzden fark edilmedi.
                            const bool izinli = (tip_byte == TIP_KOMUT  ||
                                                  tip_byte == TIP_GOREV  ||
                                                  tip_byte == TIP_RENK   ||
                                                  tip_byte == TIP_ORIGIN ||
                                                  tip_byte == TIP_DURUM  ||
                                                  tip_byte == TIP_SWARM_STATE ||
                                                  tip_byte == TIP_QR_DATA ||
                                                  tip_byte == TIP_LEADER_HB ||
                                                  tip_byte == TIP_ELECTION);
                            if (!izinli) break;
                            uint32_t simdi = millis();
                            if (simdi - son_rpi_mesh_ms >= MESH_GONDERIM_MIN_MS) {
                                son_rpi_mesh_ms = simdi;
                                mesh_gonder(payload, tip_byte);
                            }
                        }
                    }
                }
                rpi_rx_idx = 0;
            } else {
                if (rpi_rx_idx < sizeof(rpi_rx_buf)) {
                    rpi_rx_buf[rpi_rx_idx++] = b;
                } else {
                    rpi_rx_idx = 0;
                }
            }
        }
    }
}
