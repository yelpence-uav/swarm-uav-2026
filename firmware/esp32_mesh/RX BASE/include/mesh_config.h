#pragma once

#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include "encryption.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define MESH_KANAL            1
#define MESH_MAX_NODES        8
#define ATLAMA_MAKS           3
#define HEARTBEAT_ARALIK_MS   500UL
#define NODE_TIMEOUT_MS       12000UL
#define CSMA_GECIKME_MAKS_MS  10
#define DUPLIKAT_TAMPON       32

#define TIP_TELEMETRI   0x01
#define TIP_KOMUT       0x02
#define TIP_HEARTBEAT   0x03
#define TIP_POSE        0x04
#define TIP_GOREV       0x05
#define TIP_RENK        0x06
#define TIP_DURUM       0x07

#define FORMASYON_OKBASI  0x01
#define FORMASYON_V       0x02
#define FORMASYON_CIZGI   0x03

#define GOREV_FORMASYON   0x01
#define GOREV_MANEVRA     0x02
#define GOREV_IRTIFA      0x03
#define GOREV_AYRIL       0x04

#define RENK_KIRMIZI      0x01
#define RENK_MAVI         0x02

#define DURUM_AKTIF       0x01
#define DURUM_AYRILDI     0x02
#define DURUM_INDI        0x03

struct __attribute__((packed)) pose_veri_t {
    int32_t  lat;
    int32_t  lon;
    int16_t  alt_cm;
    int16_t  heading;
    int16_t  vx;
    int16_t  vy;
};

struct __attribute__((packed)) gorev_veri_t {
    uint8_t  tip;             // GOREV_FORMASYON / MANEVRA / IRTIFA / AYRIL
    uint8_t  param1;          // formasyon tipi / pitch deg / irtifa / drone_id
    int8_t   param2;          // roll deg / hedef renk
    uint8_t  bekleme_suresi_s;// QR noktasinda bekleme suresi (saniye)
    uint8_t  rezerv[12];      // toplam 16 byte korunur
};

struct __attribute__((packed)) renk_veri_t {
    uint8_t  renk;
    int32_t  lat;
    int32_t  lon;
    uint8_t  rezerv[7];
};

struct __attribute__((packed)) durum_veri_t {
    uint8_t  drone_id;
    uint8_t  durum;
    uint8_t  rezerv[14];
};

static const uint8_t BROADCAST_MAC[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

struct __attribute__((packed)) mesh_paket_t {
    uint8_t  kaynak_mac[6];
    uint8_t  hedef_mac[6];
    uint32_t paket_id;
    uint8_t  atlama_sayisi;
    uint8_t  tip;
    uint8_t  sifreli_veri[16];
};

struct node_durum_t {
    uint8_t  mac[6];
    uint32_t son_heartbeat_ms;
    bool     aktif;
    bool     peer_kayitli;
};

// ===== ISR-SAFE PAKET BUFFER =====
// Callback sadece buraya yazar, mesh_loop() okur
#define RECV_BUFFER_SIZE 8
static struct {
    mesh_paket_t paket;
    bool         dolu;
} _recv_buffer[RECV_BUFFER_SIZE];
static volatile uint8_t _recv_yaz  = 0;
static volatile uint8_t _recv_oku  = 0;
static volatile bool    _recv_flag = false;

// son_paket_ms volatile — callback ve loop arasında paylaşılıyor
extern volatile unsigned long son_paket_ms;

static uint8_t  _benim_mac[6];
static uint32_t _paket_sayaci     = 0;
static uint32_t _son_heartbeat_ms = 0;
static node_durum_t _bilinen_nodlar[MESH_MAX_NODES] = {};
static uint32_t _duplikat_tampon[DUPLIKAT_TAMPON]   = {};
static uint8_t  _duplikat_indeks                    = 0;

typedef void (*mesh_veri_callback_t)(const mesh_paket_t* paket);
static mesh_veri_callback_t _veri_callback = nullptr;

static inline IRAM_ATTR bool _mac_esit(const uint8_t* a, const uint8_t* b) {
    return memcmp(a, b, 6) == 0;
}
static inline IRAM_ATTR bool _benim_mac_mi(const uint8_t* mac) {
    return _mac_esit(mac, _benim_mac);
}
static inline bool _broadcast_mi(const uint8_t* mac) {
    return _mac_esit(mac, BROADCAST_MAC);
}

static inline uint32_t _paket_hash(const mesh_paket_t* p) {
    // FIX: paket_id tam 32 bit kullaniliyor, XOR ile MAC ile karistirildi
    uint32_t mac_part = ((uint32_t)p->kaynak_mac[5] << 24)
                      | ((uint32_t)p->kaynak_mac[4] << 16)
                      | ((uint32_t)p->kaynak_mac[3] << 8)
                      |  (uint32_t)p->kaynak_mac[2];
    return mac_part ^ p->paket_id;
}
static inline bool _duplikat_mi(const mesh_paket_t* p) {
    uint32_t h = _paket_hash(p);
    for (uint8_t i = 0; i < DUPLIKAT_TAMPON; i++)
        if (_duplikat_tampon[i] == h) return true;
    return false;
}
static inline void _duplikat_kaydet(const mesh_paket_t* p) {
    _duplikat_tampon[_duplikat_indeks] = _paket_hash(p);
    _duplikat_indeks = (_duplikat_indeks + 1) % DUPLIKAT_TAMPON;
}

static inline void _peer_ekle(const uint8_t* mac) {
    if (_mac_esit(mac, BROADCAST_MAC)) return;
    if (esp_now_is_peer_exist(mac))    return;
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, mac, 6);
    peer.channel = MESH_KANAL;
    peer.encrypt = false;
    if (esp_now_add_peer(&peer) == ESP_OK)
        Serial.printf("[MESH] Yeni peer: %02X:%02X:%02X:%02X:%02X:%02X\n",
            mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
}

static node_durum_t* _node_bul_veya_ekle(const uint8_t* mac) {
    node_durum_t* bos = nullptr;
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (_bilinen_nodlar[i].aktif && _mac_esit(_bilinen_nodlar[i].mac, mac))
            return &_bilinen_nodlar[i];
        if (!_bilinen_nodlar[i].aktif && bos == nullptr)
            bos = &_bilinen_nodlar[i];
    }
    if (bos) {
        memcpy(bos->mac, mac, 6);
        bos->aktif = true;
        bos->peer_kayitli = false;
        bos->son_heartbeat_ms = millis();
    }
    return bos;
}

static uint32_t _csma_son_ms = 0;

static inline esp_err_t _mesh_gonder(mesh_paket_t* p) {
    if (!esp_now_is_peer_exist(BROADCAST_MAC)) {
        esp_now_peer_info_t bp = {};
        memcpy(bp.peer_addr, BROADCAST_MAC, 6);
        bp.channel = MESH_KANAL;
        bp.encrypt = false;
        esp_now_add_peer(&bp);
    }
    if (p->tip == TIP_TELEMETRI || p->tip == TIP_HEARTBEAT) {
        uint32_t _csma_bekleme = (uint32_t)esp_random() % (CSMA_GECIKME_MAKS_MS + 1);
        if (_csma_bekleme > 0) vTaskDelay(pdMS_TO_TICKS(_csma_bekleme));
        _csma_son_ms = millis();
    }
    const uint8_t* hedef = _broadcast_mi(p->hedef_mac) ? BROADCAST_MAC : p->hedef_mac;
    esp_err_t ret = esp_now_send(hedef, (const uint8_t*)p, sizeof(mesh_paket_t));
    if (ret != ESP_OK)
        Serial.printf("[MESH] Gonderim hatasi: %d tip:%d\n", ret, p->tip);
    return ret;
}

static inline void mesh_gonder(const uint8_t* veri, uint8_t tip,
                                const uint8_t* hedef = nullptr) {
    mesh_paket_t p = {};
    memcpy(p.kaynak_mac, _benim_mac, 6);
    memcpy(p.hedef_mac, (hedef ? hedef : BROADCAST_MAC), 6);
    p.paket_id      = ++_paket_sayaci;
    p.atlama_sayisi = 0;
    p.tip           = tip;
    aes_sifrele_iv(veri, p.sifreli_veri, p.paket_id);
    _duplikat_kaydet(&p);
    _mesh_gonder(&p);
}

static inline void _paketi_ilet(const mesh_paket_t* gelen) {
    if (!_broadcast_mi(gelen->hedef_mac))    return;
    if (gelen->atlama_sayisi >= ATLAMA_MAKS) return;
    mesh_paket_t ilet = *gelen;
    ilet.atlama_sayisi++;
    _mesh_gonder(&ilet);
}

static inline void _heartbeat_gonder() {
    mesh_paket_t p = {};
    memcpy(p.kaynak_mac, _benim_mac, 6);
    memcpy(p.hedef_mac,  BROADCAST_MAC, 6);
    p.paket_id      = ++_paket_sayaci;
    p.atlama_sayisi = 0;
    p.tip           = TIP_HEARTBEAT;
    _duplikat_kaydet(&p);
    _mesh_gonder(&p);
}

static inline void mesh_node_timeout_kontrol() {
    uint32_t simdi = millis();
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (!_bilinen_nodlar[i].aktif) continue;
        if (simdi - _bilinen_nodlar[i].son_heartbeat_ms > NODE_TIMEOUT_MS) {
            Serial.printf("[MESH] Timeout: %02X:%02X:%02X:%02X:%02X:%02X\n",
                _bilinen_nodlar[i].mac[0],_bilinen_nodlar[i].mac[1],
                _bilinen_nodlar[i].mac[2],_bilinen_nodlar[i].mac[3],
                _bilinen_nodlar[i].mac[4],_bilinen_nodlar[i].mac[5]);
            esp_now_del_peer(_bilinen_nodlar[i].mac);
            _bilinen_nodlar[i].aktif        = false;
            _bilinen_nodlar[i].peer_kayitli = false;
        }
    }
}

// ===== ISR CALLBACK — sadece buffer'a yazar =====
#define ISR_DUPLIKAT_TAMPON 4
static DRAM_ATTR uint32_t _isr_hashler[ISR_DUPLIKAT_TAMPON] = {};
static DRAM_ATTR uint8_t  _isr_hash_idx = 0;

static inline IRAM_ATTR bool _isr_duplikat_mi(const mesh_paket_t* p) {
    uint32_t h = ((uint32_t)p->kaynak_mac[4] << 8 | p->kaynak_mac[5])
                 | ((uint32_t)(p->paket_id & 0xFFFF) << 16);
    for (uint8_t i = 0; i < ISR_DUPLIKAT_TAMPON; i++)
        if (_isr_hashler[i] == h) return true;
    _isr_hashler[_isr_hash_idx] = h;
    _isr_hash_idx = (_isr_hash_idx + 1) % ISR_DUPLIKAT_TAMPON;
    return false;
}

static portMUX_TYPE _recv_mux = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR _esp_now_recv_cb(const uint8_t* mac,
                                        const uint8_t* data, int len) {
    if (len != sizeof(mesh_paket_t)) return;
    const mesh_paket_t* p = reinterpret_cast<const mesh_paket_t*>(data);
    if (_benim_mac_mi(p->kaynak_mac)) return;
    if (_isr_duplikat_mi(p))          return;

    // Bağlantıyı canlı tut — sadece volatile write, ISR-safe
    son_paket_ms = millis();

    // Kritik bolge — dual-core race condition onleme
    portENTER_CRITICAL_ISR(&_recv_mux);
    uint8_t sonraki = (_recv_yaz + 1) % RECV_BUFFER_SIZE;
    if (sonraki == _recv_oku) {
        portEXIT_CRITICAL_ISR(&_recv_mux);
        return; // buffer dolu, paketi at
    }
    memcpy(&_recv_buffer[_recv_yaz].paket, data, sizeof(mesh_paket_t));
    _recv_buffer[_recv_yaz].dolu = true;
    _recv_yaz = sonraki;
    _recv_flag = true;
    portEXIT_CRITICAL_ISR(&_recv_mux);
}

static void _esp_now_send_cb(const uint8_t* mac, esp_now_send_status_t status) {
    (void)mac; (void)status;
}

// ===== BUFFER'DAN PAKET İŞLE — mesh_loop() içinde çağrılır =====
static inline void _recv_isle() {
    while (_recv_oku != _recv_yaz) {
        mesh_paket_t* p = &_recv_buffer[_recv_oku].paket;

        if (!_duplikat_mi(p)) {
            _duplikat_kaydet(p);

            node_durum_t* node = _node_bul_veya_ekle(p->kaynak_mac);
            if (node) {
                node->son_heartbeat_ms = millis();
                node->aktif = true;
                if (!node->peer_kayitli) {
                    _peer_ekle(p->kaynak_mac);
                    node->peer_kayitli = true;
                }
            }

            if (p->tip != TIP_HEARTBEAT) {
                bool benim_icin = _broadcast_mi(p->hedef_mac) ||
                                  _benim_mac_mi(p->hedef_mac);
                if (benim_icin && _veri_callback) _veri_callback(p);
                if (_broadcast_mi(p->hedef_mac)) _paketi_ilet(p);
            }
        }

        _recv_buffer[_recv_oku].dolu = false;
        _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
    }
    _recv_flag = false;
}

static inline void mesh_init(mesh_veri_callback_t callback) {
    _veri_callback = callback;
    esp_read_mac(_benim_mac, ESP_MAC_WIFI_STA);
    Serial.printf("[MESH] MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
        _benim_mac[0],_benim_mac[1],_benim_mac[2],
        _benim_mac[3],_benim_mac[4],_benim_mac[5]);
    if (esp_now_init() != ESP_OK) {
        Serial.println("[MESH] HATA: esp_now_init!");
        return;
    }
    esp_now_register_recv_cb(_esp_now_recv_cb);
    esp_now_register_send_cb(_esp_now_send_cb);
    esp_now_peer_info_t bp = {};
    memcpy(bp.peer_addr, BROADCAST_MAC, 6);
    bp.channel = MESH_KANAL;
    bp.encrypt = false;
    esp_now_add_peer(&bp);
    Serial.println("[MESH] Hazir.");
}

static inline void mesh_loop() {
    // Gelen paketleri ISR buffer'dan isle
    if (_recv_flag) _recv_isle();

    uint32_t simdi = millis();
    if (simdi - _son_heartbeat_ms >= HEARTBEAT_ARALIK_MS) {
        _son_heartbeat_ms = simdi;
        _heartbeat_gonder();
    }
    mesh_node_timeout_kontrol();
}

static inline void mesh_durum_yazdir() {
    Serial.println("=== MESH DURUM ===");
    uint8_t aktif = 0;
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (!_bilinen_nodlar[i].aktif) continue;
        aktif++;
        Serial.printf("  [%d] %02X:%02X:%02X:%02X:%02X:%02X  %ums\n", i,
            _bilinen_nodlar[i].mac[0],_bilinen_nodlar[i].mac[1],
            _bilinen_nodlar[i].mac[2],_bilinen_nodlar[i].mac[3],
            _bilinen_nodlar[i].mac[4],_bilinen_nodlar[i].mac[5],
            (unsigned)(millis()-_bilinen_nodlar[i].son_heartbeat_ms));
    }
    Serial.printf("  Aktif: %d/%d\n", aktif, MESH_MAX_NODES);
    Serial.println("==================");
}
