#pragma once

#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include "esp_wifi.h"      // DUSUK-2: promiscuous mod kanal taramasi icin
#include "encryption.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rtk_pure.h"      // ADIM 6: RTK_ENV_MAKS_TOPLAM vb. TEK yerden (portable)

#define MESH_KANAL           11   // Birincil — non-overlapping, TR ISM, sahada en az meşgul
#define MESH_KANAL_YEDEK      6   // Yedek — uçuş öncesi spektrum analizi olumsuzsa buraya geç
#define MESH_MAX_NODES        8
#define ATLAMA_MAKS           3
#define HEARTBEAT_ARALIK_MS   500UL
#define NODE_TIMEOUT_MS       12000UL
#define CSMA_GECIKME_MAKS_MS  10
#define DUPLIKAT_TAMPON       32

#define TIP_KOMUT       0x02
#define TIP_HEARTBEAT   0x03
#define TIP_POSE        0x04
#define TIP_GOREV       0x05
#define TIP_RENK        0x06
#define TIP_RTK         0x0C
#define TIP_DURUM       0x07
#define TIP_ORIGIN      0x08   // RPi → Mesh origin broadcast
#define TIP_LEADER_HB   0x09   // LeaderHeartbeat — lider secimi
#define TIP_ELECTION    0x0A   // ElectionResult  — lider degisimi
#define TIP_VERSION     0x0B   // VersionInfo     — boot'ta 1 kez, debug
#define TIP_SWARM_STATE 0x0D   // Sürü seviyesi FSM durumu
#define TIP_QR_DATA     0x0E   // QR tespit ve çözümleme verisi

// RTK çerçevelerinin kaynak/baz kimliği (spec §2.2). TIP tanımlarının yanında
// çünkü TIP_RTK ile birlikte, ÇERÇEVE PREFİKSİNİN ikinci baytını oluşturur:
//   COBS( TIP_RTK + BAZ_ID + rtcm + crc16_be ) + 0x00
// Burada (paylaşılan header'da) tanımlı olması ŞART: hem RX BASE (çerçeveyi
// çözüp ID'yi doğrular, rtk_sender.h) hem de rtk_handler.h (çerçeveyi kurar)
// aynı değeri görmeli. Eskiden rtk_sender.h'de tanımlıydı ve rtk_handler.h
// onu göremediği için 99'u hardcode ediyordu — iki taraf sessizce kayabilirdi.
#define BAZ_ID          99

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
    int16_t  alt_dm;
    int16_t  heading;
    int16_t  vx;
    int16_t  vy;
    int16_t  vz;        // cm/s (NED asagi pozitif)
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

struct __attribute__((packed)) qr_veri_t {
    uint8_t  drone_id;        // QR algılayan drone
    uint32_t action_id;       // Çözümlenen QR eylemi
    int32_t  lat;
    int32_t  lon;
    uint8_t  rezerv[3];       // toplam 16 byte
};

struct __attribute__((packed)) swarm_state_veri_t {
    uint8_t  mission_id;      // Mevcut aktif görev (mission1, mission2)
    uint8_t  swarm_fsm_state; // Sürü FSM genel state'i
    uint8_t  active_leader;   // Lider ID
    uint8_t  formation;       // Mevcut formasyon
    uint32_t timestamp;       // State time
    uint8_t  rezerv[8];       // toplam 16 byte
};

struct __attribute__((packed)) origin_veri_t {
    int32_t  lat_1e7;    // 1e-7 derece (RTK 1.1 cm hassasiyet)
    int32_t  lon_1e7;
    int32_t  alt_mm;     // milimetre
    uint32_t sequence;   // origin tekrar yakalanirsa +1
};   // toplam 16 byte

struct __attribute__((packed)) leader_hb_veri_t {
    uint8_t  leader_id;
    uint32_t sequence_num;        // her HB'de +1
    uint8_t  election_round;      // mevcut tur
    uint8_t  active_agent_count;  // liderin gordugu ajan sayisi
    uint8_t  mission_active;      // 0/1
    uint8_t  rezerv[8];
};   // 16 byte

struct __attribute__((packed)) election_veri_t {
    uint8_t  new_leader_id;
    uint8_t  election_round;
    uint8_t  reason;              // 0=UNKNOWN 1=TIMEOUT 2=FAULT 3=MANUAL
    uint8_t  triggered_by;        // election'i baslatan ajan ID (0=sistem)
    uint32_t sequence_num;
    uint8_t  confirmed_ids[4];    // onay veren ilk 4 ID (0=bos)
    uint8_t  rezerv[4];
};   // 16 byte

struct __attribute__((packed)) version_veri_t {
    uint8_t  major;
    uint8_t  minor;
    uint8_t  patch;
    uint8_t  drone_id;
    uint32_t build_unix;
    uint8_t  rezerv[8];
};   // 16 byte

// TODO: HAS_PIXHAWK=1 oldugunda durum_veri_t doldur ve loop() icinde TIP_DURUM gonder (500ms).
// Bagimliliklar: mesh_komsu_sayisi(), MAVLink SYS_STATUS/GPS_RAW_INT/EKF_STATUS_REPORT okuma fonksiyonlari.
// Stub implementasyonu hazir — Pixhawk fiziksel baglantiginda aktif edilecek.
struct __attribute__((packed)) durum_veri_t {
    uint8_t  drone_id;
    uint8_t  durum;
    uint8_t  armed;         // 0/1
    uint8_t  gps_fix_type;  // 0-6
    uint8_t  battery_pct;   // 0-100
    float    battery_volt;  // 4 byte
    uint8_t  ekf_ok;        // 0/1
    uint8_t  imu_ok;        // 0/1
    uint8_t  mag_ok;        // 0/1
    uint8_t  baro_ok;       // 0/1
    int8_t   rssi;          // dBm (-120..0)
    uint8_t  mesh_link_ok;  // 0/1
    uint8_t  mesh_komsu_sayisi; // aktif mesh node sayisi — failsafe + lider secimi + ground izleme
};

static const uint8_t BROADCAST_MAC[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

struct __attribute__((packed)) mesh_paket_t {
    uint8_t  kaynak_mac[6];
    uint8_t  hedef_mac[6];
    uint32_t paket_id;
    uint8_t  atlama_sayisi;
    uint8_t  tip;
    uint8_t  iv[12];           // GCM nonce (12 byte, NIST onerisi)
    uint8_t  sifreli_veri[24]; // anti_replay(6) + payload(18)
    uint8_t  tag[16];          // GCM auth tag — sifre cozumunde dogrulanir
};

// ===== SLIDING WINDOW ANTI-REPLAY (Yontem 1) =====
// TODO: GPS_TIMESTAMP — HAS_PIXHAWK + MAVLink GPS okumasi hazir oldugunda
//   stateless GPS zaman damgasina gec: |alici_gps_ms - paket_gps_ms| > 2000 ise at.
//   session_id, pencere ve ilk_paket mekanizmasina gerek kalmaz.
#define PENCERE_BOYU 64

struct __attribute__((packed)) anti_replay_t {
    uint16_t session_id; // boot basina rastgele — reboot sonrasi pencereyi sifirlar
    uint32_t paket_id;   // sifrelenmis payload icinde — baslik manipulasyonu engellenir
};

struct replay_state_t {
    uint16_t session_id;
    uint32_t en_yuksek_id;
    uint64_t pencere_bitmask; // son 64 paketin gelis durumu
    bool     ilk_paket;       // true: ilk pakette pencereyi baslatir
};

struct node_durum_t {
    uint8_t        mac[6];
    uint32_t       son_heartbeat_ms;
    bool           aktif;
    bool           peer_kayitli;
    replay_state_t replay;
};

// ===== ISR-SAFE PAKET BUFFER =====
// Callback sadece buraya yazar, mesh_loop() okur
#define RECV_BUFFER_SIZE 16
static struct {
    mesh_paket_t paket;
} _recv_buffer[RECV_BUFFER_SIZE];
static volatile uint8_t _recv_yaz  = 0;
static volatile uint8_t _recv_oku  = 0;
static volatile bool    _recv_flag = false;

// ===== TIP_RTK — AYRI, DEGISKEN BOYUTLU ISR-SAFE BUFFER =====
// REV B: RTK artik sabit boyutlu mesh_paket_t zarfini degil, degisken
// uzunlukta buyuk bir zarfi kullaniyor (bkz rtk_handler.h). Diger TIP'lerin
// _recv_buffer/mesh_paket_t yolunu HIC degistirmemek icin RTK'ye tamamen
// ayri, kendi ring buffer'i ayrildi. Zarf onsozu (kaynak_mac..tip) her iki
// zarf tipinde de ayni bayt duzeninde oldugundan (offset 17'de tip byte'i),
// ISR tam parse etmeden bu offset'e bakip hangi buffer'a yazacagina karar
// verebiliyor.
// RTK_ENV_MAKS_TOPLAM artik rtk_pure.h'den geliyor (ADIM 6, tek kaynak)
#define RTK_RECV_BUFFER_SIZE  8
static struct {
    uint8_t  veri[RTK_ENV_MAKS_TOPLAM];
    uint16_t uzunluk;
} _rtk_recv_buffer[RTK_RECV_BUFFER_SIZE];
static volatile uint8_t _rtk_recv_yaz  = 0;
static volatile uint8_t _rtk_recv_oku  = 0;
static volatile bool    _rtk_recv_flag = false;

// son_paket_ms volatile — callback ve loop arasında paylaşılıyor
extern volatile unsigned long son_paket_ms;

static uint8_t  _benim_mac[6];
static uint32_t _paket_sayaci     = 0;
static uint16_t _session_id       = 0; // mesh_init() atar
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

static inline bool _replay_kontrol(node_durum_t* node, const anti_replay_t* ar) {
    replay_state_t* rs = &node->replay;
    if (rs->ilk_paket) {
        rs->session_id      = ar->session_id;
        rs->en_yuksek_id    = ar->paket_id;
        rs->pencere_bitmask = 1ULL;
        rs->ilk_paket       = false;
        return true;
    }
    if (ar->session_id != rs->session_id) {
        // Reboot algilandi — yeni session kabul et, pencereyi sifirla
        rs->session_id      = ar->session_id;
        rs->en_yuksek_id    = ar->paket_id;
        rs->pencere_bitmask = 1ULL;
        return true;
    }
    if (ar->paket_id > rs->en_yuksek_id) {
        uint32_t ilerleme   = ar->paket_id - rs->en_yuksek_id;
        rs->pencere_bitmask = (ilerleme >= PENCERE_BOYU)
                              ? 0ULL : (rs->pencere_bitmask << ilerleme);
        rs->pencere_bitmask |= 1ULL;
        rs->en_yuksek_id    = ar->paket_id;
        return true;
    }
    uint32_t fark = rs->en_yuksek_id - ar->paket_id;
    if (fark >= PENCERE_BOYU)                 return false; // cok eski
    if (rs->pencere_bitmask & (1ULL << fark)) return false; // replay!
    rs->pencere_bitmask |= (1ULL << fark);
    return true;
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
        bos->replay = {};
        bos->replay.ilk_paket = true;
    }
    return bos;
}

static uint32_t _csma_son_ms = 0;
static volatile uint32_t _gonderim_basari = 0;
static volatile uint32_t _gonderim_hata  = 0;
static volatile uint32_t _paket_dustu    = 0;

static inline esp_err_t _mesh_gonder(mesh_paket_t* p) {
    if (!esp_now_is_peer_exist(BROADCAST_MAC)) {
        esp_now_peer_info_t bp = {};
        memcpy(bp.peer_addr, BROADCAST_MAC, 6);
        bp.channel = MESH_KANAL;
        bp.encrypt = false;
        esp_now_add_peer(&bp);
    }
    // CSMA: tum tipler icin kanal mesguliyse rastgele bekle
    uint32_t _csma_bekleme = (uint32_t)esp_random() % (CSMA_GECIKME_MAKS_MS + 1);
    if (_csma_bekleme > 0) vTaskDelay(pdMS_TO_TICKS(_csma_bekleme));
    _csma_son_ms = millis();

    const uint8_t* hedef = _broadcast_mi(p->hedef_mac) ? BROADCAST_MAC : p->hedef_mac;

    // Kritik paketler icin retry (3 deneme, aralikli)
    // NOT: hedef broadcast oldugu icin ESP-NOW donanim ACK'i YOKTUR — bu retry
    // sadece YEREL gonderim hatasini (TX kuyrugu dolu, esp_now_send() basarisiz)
    // kurtarir; havada/menzil disinda kaybolan paketi retry ile kurtaramaz.
    // REV B: TIP_RTK bu listeden cikarildi — artik mesh_paket_t/_mesh_gonder()
    // yolundan hic gecmiyor (bkz rtk_handler.h: rtk_mesh_gonder(), kendi ayni
    // CSMA+3-deneme retry mantigini ayri uyguluyor, REV B karari #4).
    const bool kritik = (p->tip == TIP_KOMUT || p->tip == TIP_ORIGIN ||
                         p->tip == TIP_GOREV || p->tip == TIP_ELECTION);
    const int deneme_maks = kritik ? 3 : 1;
    esp_err_t ret = ESP_FAIL;
    for (int d = 0; d < deneme_maks; d++) {
        ret = esp_now_send(hedef, (const uint8_t*)p, sizeof(mesh_paket_t));
        if (ret == ESP_OK) break;
        if (d < deneme_maks - 1)
            vTaskDelay(pdMS_TO_TICKS(2 + (uint32_t)esp_random() % 6));
    }
    if (ret != ESP_OK) {
        _paket_dustu++;
        Serial.printf("[MESH] Gonderim hatasi: %d tip:%d dustu:%lu\n",
                      ret, p->tip, _paket_dustu);
    }
    return ret;
}

// ===== ORTA-1 FIX: GCM AAD (Ek Dogrulanmis Veri) =====
// tip + kaynak_mac + hedef_mac AAD olarak verilir; boylece bu 3 alan artik
// sifreli payload'i hic bozmadan degistirilemez (ornegin TIP_POSE -> TIP_GOREV).
// atlama_sayisi kasitli olarak DISARIDA tutulur: _paketi_ilet() her hop'ta onu
// artirir, ayni iv/tag ile iletir — AAD'e girseydi relay ilk hop'ta tag'i
// gecersiz kilardi.
static inline void _mesh_aad_olustur(uint8_t tip, const uint8_t* kaynak_mac,
                                      const uint8_t* hedef_mac, uint8_t aad[13]) {
    aad[0] = tip;
    memcpy(aad + 1, kaynak_mac, 6);
    memcpy(aad + 7, hedef_mac, 6);
}

static inline void mesh_gonder(const uint8_t* veri, uint8_t tip,
                                const uint8_t* hedef = nullptr) {
    mesh_paket_t p = {};
    memcpy(p.kaynak_mac, _benim_mac, 6);
    memcpy(p.hedef_mac, (hedef ? hedef : BROADCAST_MAC), 6);
    p.paket_id      = ++_paket_sayaci;
    p.atlama_sayisi = 0;
    p.tip           = tip;
    iv_uret_rastgele(p.iv);
    // Anti-replay basligini (session_id + paket_id) sifrelenmis payload icine gom
    uint8_t tam_veri[24];
    anti_replay_t ar_out = { _session_id, p.paket_id };
    memcpy(tam_veri, &ar_out, sizeof(anti_replay_t));
    memcpy(tam_veri + sizeof(anti_replay_t), veri, 18);
    uint8_t aad[13];
    _mesh_aad_olustur(p.tip, p.kaynak_mac, p.hedef_mac, aad);
    aes_sifrele_gcm(tam_veri, sizeof(tam_veri), p.sifreli_veri, p.iv, p.tag, aad, sizeof(aad));
    _duplikat_kaydet(&p);
    _mesh_gonder(&p);
}

static inline uint8_t mesh_komsu_sayisi() {
    uint8_t count = 0;
    uint32_t now = millis();
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (_bilinen_nodlar[i].aktif && (now - _bilinen_nodlar[i].son_heartbeat_ms < NODE_TIMEOUT_MS)) {
            count++;
        }
    }
    return count;
}

static inline void _paketi_ilet(const mesh_paket_t* gelen) {
    if (!_broadcast_mi(gelen->hedef_mac))    return;
    if (gelen->atlama_sayisi >= ATLAMA_MAKS) return;
    mesh_paket_t ilet = *gelen;
    ilet.atlama_sayisi++;
    _mesh_gonder(&ilet);
}

static inline void _heartbeat_gonder() {
    // GCM ile sifrele — sahte HB ile MAC listesine girilmesini engeller
    uint8_t bos[18] = {};
    mesh_gonder(bos, TIP_HEARTBEAT);
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
    uint32_t h = p->paket_id ^ ((uint32_t)p->kaynak_mac[5] << 24) ^ ((uint32_t)p->kaynak_mac[4] << 16);
    for (uint8_t i = 0; i < ISR_DUPLIKAT_TAMPON; i++)
        if (_isr_hashler[i] == h) return true;
    _isr_hashler[_isr_hash_idx] = h;
    _isr_hash_idx = (_isr_hash_idx + 1) % ISR_DUPLIKAT_TAMPON;
    return false;
}

static portMUX_TYPE _recv_mux = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR _esp_now_recv_cb(const uint8_t* mac_addr,
                                        const uint8_t* data, int len) {
    // REV B: TIP_RTK buyuk zarfi ayri yoldan isle. Zarf onsozu ortak
    // oldugundan (kaynak_mac[6]+hedef_mac[6]+paket_id[4]+atlama_sayisi[1]
    // = 17 byte sonrasi tip), tam parse etmeden offset 17'ye bakmak
    // guvenli — mesh_paket_t'de de tip ayni offsette.
    if (len >= 18 && data[17] == TIP_RTK) {
        if (len > RTK_ENV_MAKS_TOPLAM) return;
        portENTER_CRITICAL_ISR(&_recv_mux);
        uint8_t sonraki_rtk = (_rtk_recv_yaz + 1) % RTK_RECV_BUFFER_SIZE;
        if (sonraki_rtk == _rtk_recv_oku) {
            portEXIT_CRITICAL_ISR(&_recv_mux);
            return; // buffer dolu, paketi at
        }
        memcpy(_rtk_recv_buffer[_rtk_recv_yaz].veri, data, (size_t)len);
        _rtk_recv_buffer[_rtk_recv_yaz].uzunluk = (uint16_t)len;
        _rtk_recv_yaz = sonraki_rtk;
        _rtk_recv_flag = true;
        portEXIT_CRITICAL_ISR(&_recv_mux);
        return;
    }
    if (len != sizeof(mesh_paket_t)) return;
    const mesh_paket_t* p = reinterpret_cast<const mesh_paket_t*>(data);
    if (_benim_mac_mi(p->kaynak_mac)) return;
    if (_isr_duplikat_mi(p))          return;
    // Kritik bolge — dual-core race condition onleme
    portENTER_CRITICAL_ISR(&_recv_mux);
    uint8_t sonraki = (_recv_yaz + 1) % RECV_BUFFER_SIZE;
    if (sonraki == _recv_oku) {
        portEXIT_CRITICAL_ISR(&_recv_mux);
        return; // buffer dolu, paketi at
    }
    memcpy(&_recv_buffer[_recv_yaz].paket, data, sizeof(mesh_paket_t));
    _recv_yaz = sonraki;
    _recv_flag = true;
    portEXIT_CRITICAL_ISR(&_recv_mux);
}

static void _esp_now_send_cb(const uint8_t* mac, esp_now_send_status_t status) {
    if (status == ESP_NOW_SEND_SUCCESS) _gonderim_basari++;
    else {
        _gonderim_hata++;
        Serial.printf("[MESH] ACK yok: %02X:%02X:%02X:%02X:%02X:%02X\n",
            mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    }
}

// ===== BUFFER'DAN PAKET İŞLE — mesh_loop() içinde çağrılır =====
static inline void _recv_isle() {
    _recv_flag = false; // Once sifirla — sonraki ISR yazimini kaybetme
    while (_recv_oku != _recv_yaz) {
        mesh_paket_t* p = &_recv_buffer[_recv_oku].paket;

        if (!_duplikat_mi(p)) {
            _duplikat_kaydet(p);

            node_durum_t* node = _node_bul_veya_ekle(p->kaynak_mac);
            // peer kaydı GCM dogrulamasindan sonra yapilir (Bug2 fix)

            if (p->tip != TIP_HEARTBEAT) {
                bool benim_icin = _broadcast_mi(p->hedef_mac) ||
                                  _benim_mac_mi(p->hedef_mac);
                if (benim_icin) {
                    // Bug1+Bug3 fix: GCM burda dogrulanir; gecerse node guncellenir
                    uint8_t _acik_cb[24] = {0};
                    uint8_t _aad_cb[13];
                    _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, _aad_cb);
                    if (!aes_coz_gcm(p->sifreli_veri, 24, _acik_cb, p->iv, p->tag, _aad_cb, sizeof(_aad_cb))) {
                        Serial.printf("[MESH] GCM hatasi tip:%d %02X:%02X\n",
                            p->tip, p->kaynak_mac[4], p->kaynak_mac[5]);
                        // Bug2 fix: sahte MAC peer listesinden cikar
                        if (node) { node->aktif = false; node->peer_kayitli = false;
                                    esp_now_del_peer(node->mac); }
                        _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
                        continue;
                    }
                    // GCM gecti — peer kaydet (Bug2 fix: sadece dogrulanmis MAC)
                    if (node && !node->peer_kayitli) {
                        _peer_ekle(p->kaynak_mac);
                        node->peer_kayitli = true;
                    }
                    // Bug1 fix: son_heartbeat_ms sadece GCM sonrasi guncellenir
                    if (node) { node->son_heartbeat_ms = millis(); node->aktif = true; }
                    if (_veri_callback) _veri_callback(p);
                }
                if (_broadcast_mi(p->hedef_mac)) _paketi_ilet(p);
            } else {
                // Heartbeat — GCM dogrulama zorunlu (MAC spoofing onleme)
                uint8_t acik[24];
                uint8_t aad_hb[13];
                _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, aad_hb);
                if (aes_coz_gcm(p->sifreli_veri, 24, acik, p->iv, p->tag, aad_hb, sizeof(aad_hb))) {
                    anti_replay_t* ar = (anti_replay_t*)acik;
                    if (node && _replay_kontrol(node, ar)) {
                        node->son_heartbeat_ms = millis();
                        node->aktif = true;
                    }
                    if (_broadcast_mi(p->hedef_mac)) _paketi_ilet(p);
                } else {
                    Serial.printf("[MESH] Sahte HEARTBEAT! %02X:%02X:%02X:%02X:%02X:%02X\n",
                        p->kaynak_mac[0], p->kaynak_mac[1], p->kaynak_mac[2],
                        p->kaynak_mac[3], p->kaynak_mac[4], p->kaynak_mac[5]);
                    // ORTA-3 FIX: heartbeat GCM basarisiz olursa node'u da
                    // Bug2 fix'teki gibi temizle (non-heartbeat dalinda zaten
                    // yapiliyordu, heartbeat dalinda unutulmustu). Aksi halde
                    // sahte kaynak MAC'li heartbeat NODE_TIMEOUT_MS (12sn)
                    // boyunca "aktif" sayilmaya devam ediyordu.
                    if (node) { node->aktif = false; node->peer_kayitli = false;
                                esp_now_del_peer(node->mac); }
                }
            }
        }

        _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
    }
}

// ===== DUSUK-2 FIX: Ucus-oncesi MANUEL spektrum taramasi =====
// BILINCLI TASARIM KARARI: otomatik kanal degisimi YOK. Dagitik bir mesh'te
// haberlesme kesildiginde cihazlarin "hangi kanala gecelim" diye anlasmasi
// zaten mumkun degil (tavuk-yumurta problemi) — bu yuzden calisma zamaninda
// reaktif kanal degisimi denemek, calismayan bir kanalda senkron kalmaktan
// daha kotu bir arizaya (kalici desync) yol acabilir.
// Bunun yerine: operator ucustan once bu fonksiyonu calistirir, MESH_KANAL
// (11) ve MESH_KANAL_YEDEK (6) uzerindeki trafik/gurultuyu Serial'e raporlar.
// Rapora gore MESH_KANAL define'i gerekirse degistirilip TUM cihazlar
// (base + her drone) AYNI degerle yeniden flaslanir — senkronizasyon boylece
// "ayni kaynak kod, ayni derleme" ile saglanir, calisma-zamaninda haberlesme
// gerektirmez.
static volatile uint32_t _kanal_tara_paket_sayaci = 0;
static volatile int64_t  _kanal_tara_rssi_toplam  = 0;

static void IRAM_ATTR _kanal_tara_rx_cb(void* buf, wifi_promiscuous_pkt_type_t type) {
    wifi_promiscuous_pkt_t* paket = (wifi_promiscuous_pkt_t*)buf;
    _kanal_tara_paket_sayaci++;
    _kanal_tara_rssi_toplam += paket->rx_ctrl.rssi;
}

static inline void mesh_kanal_tara(void) {
    const uint8_t   adaylar[]     = { MESH_KANAL, MESH_KANAL_YEDEK };
    const char*     etiketler[]   = { "birincil", "yedek" };
    const uint16_t  kanal_basi_ms = 1500;

    Serial.println("[KANAL-TARA] Spektrum taramasi basliyor...");
    wifi_promiscuous_filter_t filtre = { .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL };
    esp_wifi_set_promiscuous_filter(&filtre);
    esp_wifi_set_promiscuous_rx_cb(_kanal_tara_rx_cb);
    esp_wifi_set_promiscuous(true);

    for (uint8_t i = 0; i < sizeof(adaylar) / sizeof(adaylar[0]); i++) {
        _kanal_tara_paket_sayaci = 0;
        _kanal_tara_rssi_toplam  = 0;
        esp_wifi_set_channel(adaylar[i], WIFI_SECOND_CHAN_NONE);
        delay(kanal_basi_ms);
        int32_t ort_rssi = _kanal_tara_paket_sayaci
                          ? (int32_t)(_kanal_tara_rssi_toplam / (int64_t)_kanal_tara_paket_sayaci)
                          : 0;
        Serial.printf("[KANAL-TARA] Kanal %2u (%s): %4lu paket, ort RSSI %ld dBm\n",
                      adaylar[i], etiketler[i],
                      (unsigned long)_kanal_tara_paket_sayaci, (long)ort_rssi);
    }

    esp_wifi_set_promiscuous(false);
    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);  // calisma kanaline geri don
    Serial.println("[KANAL-TARA] Bitti. Az paket + zayif RSSI = daha bos kanal.");
    Serial.println("[KANAL-TARA] Degisiklik gerekiyorsa MESH_KANAL degistirip TUM");
    Serial.println("[KANAL-TARA] cihazlari (base + her drone) AYNI degerle yeniden flaslayin.");
}

static inline void mesh_init(mesh_veri_callback_t callback) {
    aes_init(); // Key expansion bir kez yapilir
    _session_id = (uint16_t)(esp_random() & 0xFFFF);
    if (_session_id == 0) _session_id = 1; // 0 deger rezerv
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

// ===== JOYSTICK KOMUT STRUCT (float32 encoding) =====
// !!! BU STRUCT'IN LAYOUT'U pi_bridge ILE PAYLASILAN BIR SOZLESMEDIR.
// Karsi taraf: feature/esp32-bridge, packet_parser.py::_KOMUT_FMT
// '<BBhhhh6x' (alt_tip, flags, roll, pitch, yaw, throttle, 6 dolgu = 16B).
// ESP payload'i OPAK tasir (yorumlamaz), ama alan sirasi/boyutu degisirse
// bridge sessizce yanlis coz UNMAYA baslar — degistirmeden once iki tarafi
// birlikte guncelleyin.
struct __attribute__((packed)) komut_veri_t {
    uint8_t  alt_tip;      // KOMUT_MODE_SWARM_MOVEMENT=1 / KOMUT_MODE_MANEUVER=2
    // #4 FIX: bu byte "rezerv1" degil — pi_bridge onu FLAGS olarak kullaniyor
    // ve icinde GUVENLIK KRITIK deadman biti var (bkz KOMUT_FLAG_* asagida;
    // packet_parser.py: "Bayrak biti olmadiginda her komut sessizce
    // reddedilir"). "rezerv" adi birinin bu byte'i yeniden kullanmasina
    // davetiyeydi; kurban deadman olurdu.
    uint8_t  flags;        // KOMUT_FLAG_* bit alani
    int16_t  roll_x100;    // float * 100 → int16 (±327.67 derece/s)
    int16_t  pitch_x100;
    int16_t  yaw_x100;
    int16_t  throttle_x100;
    uint8_t  rezerv[6];    // toplam 16 byte
};

// pi_bridge::packet_parser.py KOMUT_FLAG_* ile BIREBIR ayni degerler.
#define KOMUT_FLAG_TAKEOFF           0x01
#define KOMUT_FLAG_LAND              0x02
#define KOMUT_FLAG_RTL               0x04
#define KOMUT_FLAG_EMERGENCY         0x08
#define KOMUT_FLAG_FORMATION_CHANGE  0x10
#define KOMUT_FLAG_DEADMAN_PRESSED   0x20
#define KOMUT_MODE_SWARM_MOVEMENT    1
#define KOMUT_MODE_MANEUVER          2

// Layout sozlesmesini derleme zamaninda kilitle: bridge cerceveden SABIT
// 16 byte diliyor (packet_parser.py::cerceve_coz -> govde[2:18]), yani
// boyut 16'dan sapamaz — kucukse bridge cop okur, buyukse sessizce kirpar.
static_assert(sizeof(komut_veri_t) == 16,
              "komut_veri_t 16 byte OLMALI — pi_bridge govde[2:18] ile sabit 16B diliyor");
static_assert(offsetof(komut_veri_t, flags) == 1,
              "flags offset 1 OLMALI — pi_bridge _KOMUT_FMT '<BBhhhh6x' bunu varsayiyor (deadman biti!)");
static_assert(offsetof(komut_veri_t, roll_x100) == 2,
              "roll_x100 offset 2 OLMALI — pi_bridge _KOMUT_FMT ile uyum");
static_assert(offsetof(komut_veri_t, throttle_x100) == 8,
              "throttle_x100 offset 8 OLMALI — pi_bridge _KOMUT_FMT ile uyum");