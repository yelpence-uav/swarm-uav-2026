#pragma once

#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include "esp_wifi.h"      // promiscuous mod kanal taramasi icin
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rtk_pure.h"      // RTK_ENV_MAKS_TOPLAM vb. tek yerden
#include "uart_cobs.h"     // cobs_crc16 (CRC16-CCITT-FALSE) — paket butunlugu

// ============================================================================
// GUVENLIK MODELI — NEDEN SIFRELEME YOK
// ----------------------------------------------------------------------------
// Onceki surum AES-128-GCM + anti-replay + NVS'te kalici session sayaci
// kullaniyordu. Kaldirildi. Gerekce:
//
// 1. Sartname (2026 Suru IHA, §5.4) haberlesme sifrelemesi ISTEMIYOR. Tek
//    haberlesme sarti: "haberlesme unitelerini yarisma ortamindaki frekans
//    gurultusunden etkilenmeyecek sekilde secmelidir." Bu bir PARAZIT sarti,
//    gizlilik sarti degil — ve sifreleme parazite karsi koruma saglamaz.
//
// 2. Tehdit modelimiz kasitli saldiri degil, baska takimin ayni kanalda
//    kazara yayin yapmasi. Buna karsi uc katman yeterli ve hepsi duruyor:
//      - MESH_SIHIR (2B)  : yabanci paket ilk iki baytta elenir
//      - drone_tablo[]    : tablodaki MAC'ten gelmeyen paket reddedilir
//      - CRC16            : havada bozulan paket reddedilir
//    Ayrica emniyet zinciri mesh'te degil fiziksel katmanda: her IHA'nin RC
//    kumandasi ve hakemin kill switch yetkisi var (sartname §5.4).
//
// 3. Kaldirilan sistem sahada BIZE ZARAR VERDI. NVS'teki session sayaci bir
//    node'un flash'i silindiginde sifirlaniyor, peer'ler onu "eski session"
//    diye KALICI reddediyordu. Semptomu aldatici: node karsiyi duyar (failsafe
//    atmaz) ama kendi paketleri hicbir yerde kabul edilmez, ve red logu
//    node'un kendi konsolunda degil peer'in konsolunda basilir. Kendiliginden
//    duzelmez. Bu tuzak sahada uc kez tetiklendi.
//
// Kazanc: zarf 70 -> 25 bayt (havada kalma suresi ~3 kat azaldi, carpisma ve
// kayip orani dustu), NVS bagimliligi sifir, provizyon adimi ortadan kalkti.
// ============================================================================

// Paket imzasi: "YE" (Yelpence). Yabanci ESP-NOW trafigi ilk iki baytta,
// CRC hesabina bile girmeden elenir. Sabit tutulmali; degistirilirse TUM
// node'lar (baz + her drone) ayni anda yeniden flaslanmali, yoksa birbirlerini
// duymazlar ve hicbir hata mesaji cikmaz.
#define MESH_SIHIR  0x4559u

#define MESH_KANAL           11   // Birincil: non-overlapping, TR ISM, sahada en az mesgul
#define MESH_KANAL_YEDEK      6   // Yedek: ucus oncesi spektrum analizi olumsuzsa buraya gec
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
#define TIP_ORIGIN      0x08   // RPi -> Mesh origin broadcast
#define TIP_LEADER_HB   0x09   // LeaderHeartbeat: lider secimi
#define TIP_ELECTION    0x0A   // ElectionResult: lider degisimi
#define TIP_VERSION     0x0B   // VersionInfo: boot'ta 1 kez, debug
#define TIP_SWARM_STATE 0x0D   // Sürü seviyesi FSM durumu
#define TIP_QR_DATA     0x0E   // QR tespit ve çözümleme verisi

// Dikkat: iki ayri isim uzayi, karistirma:
//
// (1) BAZ_ID = RTK UART cercevesinin sentinel'i. Sadece UART cerceve
//     prefiksinin ikinci baytidir (spec §2.2):
//         COBS( TIP_RTK + BAZ_ID + rtcm + crc16_be ) + 0x00
//     Paylasilan header'da olmasi sart: RX BASE (cerceveyi cozup ID'yi
//     dogrular) ve rtk_handler.h (cerceveyi kurar) ayni degeri gormeli.
//     Bu bir mesh kimligi degildir; drone_tablo'da kullanma.
//
// (2) BAZ_MESH_ID = baz istasyonunun mesh kaynak kimligi (drone_tablo'da,
//     mac_to_id() bunu dondurur, pi_bridge'e iha_id olarak gider).
//
// Neden ayrilar: baz'a da 99 verilirse pi_bridge tarafinda baz ile RTK ayirt
// edilemez hale gelir:
//   - Bridge'in whitelist'i 99'u icerdigi anda RTK cerceveleri mesh-liveness'i
//     tazeler; RTK ~1Hz aktigi icin tum telemetri olse bile link_ok kalici
//     True olur.
//   - "99'dan paket geldi" artik "baz canli" demez, "RTK akiyor" da olabilir;
//     baz-ozel liveness imkansizlasir.
//   - _komsu_son_goruldu[99] hayalet komsu mesru kayda donusur.
// Kural: baz'in mesh kimligi 0 ve 99 disinda, drone id araliginin
// (1..MESH_MAX_NODES) ustunde bir deger olmali.
#define BAZ_ID          99   // (1) sadece RTK UART sentinel'i, mesh kimligi degil
#define BAZ_MESH_ID     10   // (2) baz'in mesh/drone_tablo kimligi

// Sozlesme kilidi: baz'in mesh kimligi drone ID araliginin (1..MESH_MAX_NODES)
// ustunde olmali, yoksa bir drone ile baz ayni ID'ye duser ve pi_bridge kaynagi
// ayirt edemez. Patlarsa BAZ_MESH_ID'yi yeni MESH_MAX_NODES'un ustune tasi ve
// pi_bridge ekibine bildir (agent_id esleme tablolari degisir).
static_assert(BAZ_MESH_ID > MESH_MAX_NODES,
              "BAZ_MESH_ID drone ID araligina girdi: baz bir drone ile ayni "
              "kimlige duser. BAZ_MESH_ID'yi yukselt ve pi_bridge'e bildir.");
static_assert(BAZ_MESH_ID != BAZ_ID,
              "BAZ_MESH_ID ile BAZ_ID ayni olamaz: 99 RTK UART sentinel'i, "
              "mesh kimligi degil (bkz yukaridaki iki-isim-uzayi notu).");

#define FORMASYON_OKBASI  0x01
#define FORMASYON_V       0x02
#define FORMASYON_CIZGI   0x03

#define GOREV_FORMASYON   0x01
#define GOREV_MANEVRA     0x02
#define GOREV_IRTIFA      0x03
#define GOREV_AYRIL       0x04

#define RENK_KIRMIZI      0x01
#define RENK_MAVI         0x02

// durum_veri_t.durum kodlari (14 degerli enum).
// KAYNAK-DOGRU: pi_bridge esp32_bridge_node.py::_DURUM_STATE_MAP / _STATE_DURUM_MAP
// ve swarm_interfaces AgentStatus.STATE_*. Su an DURUM'u pi_bridge uretip
// pi_bridge tuketiyor (firmware opak tasir, HAS_PIXHAWK=0). HAS_PIXHAWK=1 olup
// durum_veri_t'yi firmware DOLDURMAYA baslarsa BU degerler kullanilmali; aksi
// halde bridge yanlis esler (or. eski DURUM_AYRILDI=2 -> bridge'te "KALKIS").
// Eski 3-degerli DURUM_AKTIF/AYRILDI/INDI (1/2/3) kaldirildi: hic kullanilmiyordu
// ve bridge'in 14-degerli semasiyla celisiyordu. Degistirmeden once swarm_interfaces
// ile birlikte guncelle.
#define DURUM_BILINMIYOR   0
#define DURUM_BOSTA        1
#define DURUM_KALKIS       2
#define DURUM_SURUDE       3
#define DURUM_GOREV        4
#define DURUM_AYRILDI      5
#define DURUM_HASSAS_INIS  6
#define DURUM_KATILMA      7
#define DURUM_BEKLIYOR     8
#define DURUM_RTL          9
#define DURUM_INIS         10
#define DURUM_INDI         11
#define DURUM_FAILSAFE     12
#define DURUM_STANDBY      13

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

// TODO: HAS_PIXHAWK=1 oldugunda durum_veri_t doldur ve loop() icinde TIP_DURUM
// gonder (500ms). Bagimliliklar: mesh_komsu_sayisi(), MAVLink SYS_STATUS/
// GPS_RAW_INT/EKF_STATUS_REPORT okuma fonksiyonlari.
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
    uint8_t  mesh_komsu_sayisi; // aktif mesh node sayisi: failsafe + lider secimi + ground izleme
};

static const uint8_t BROADCAST_MAC[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

// Mesh paketi — 25 bayt (onceki sifreli surum 70 bayttti).
//
// Tasinmayan alanlar ve nedenleri:
//   kaynak_mac : ESP-NOW alim callback'i gonderenin MAC'ini zaten veriyor
//                (_esp_now_recv_cb'nin ilk parametresi). Pakette tasimak
//                6 baytin bosa gitmesiydi.
//   hedef_mac  : Hedef artik esp_now_send()'in adresi. Unicast'te donanim
//                zaten dogru alicaya goturur, broadcast'te herkese gider.
//   atlama     : Coklu-atlama (relay) kaldirildi; ESP-NOW menzili saha icin
//                fazlasiyla yeterli ve relay tek yuvali RTK reassembly'sini
//                bozuyordu (bkz rtk_pure.h on kosul (b)).
//   iv/tag     : Sifreleme kaldirildi (bkz yukaridaki GUVENLIK MODELI).
struct __attribute__((packed)) mesh_paket_t {
    uint16_t sihir;      // MESH_SIHIR — yabanci paket filtresi
    uint8_t  tip;        // TIP_*
    uint16_t paket_id;   // duplikat tespiti (unicast retry kopyalari icin)
    uint8_t  veri[18];   // payload (mesh_gonder her zaman 18 bayt yazar)
    uint16_t crc;        // CRC16-CCITT-FALSE, sihir..veri uzerinden
};

// Sozlesme kilidi: paket ESP-NOW'in tek seferlik siniri icinde kalmali.
static_assert(sizeof(mesh_paket_t) <= 250,
              "mesh_paket_t ESP-NOW 250 bayt sinirini asti.");
// CRC, paketin son iki bayti haric her seyi kapsar. Alan eklenirse bu offset
// kayar ve _paket_crc_hesapla() sessizce yanlis araligi hesaplar.
static_assert(offsetof(mesh_paket_t, crc) == sizeof(mesh_paket_t) - 2,
              "crc alani paketin sonunda olmali — _paket_crc_hesapla() bunu varsayiyor.");

// Paketin CRC'si: bastan crc alanina kadar olan her sey.
static inline uint16_t _paket_crc_hesapla(const mesh_paket_t* p) {
    return cobs_crc16((const uint8_t*)p, (uint16_t)(sizeof(mesh_paket_t) - 2));
}

struct node_durum_t {
    uint8_t  mac[6];
    uint32_t son_heartbeat_ms;
    bool     aktif;
    bool     peer_kayitli;
};

// ISR-safe paket buffer: callback sadece buraya yazar, mesh_loop() okur.
#define RECV_BUFFER_SIZE 16
static struct {
    uint8_t      kaynak_mac[6];   // ESP-NOW callback'inden; pakette tasinmiyor
    mesh_paket_t paket;
} _recv_buffer[RECV_BUFFER_SIZE];
static volatile uint8_t _recv_yaz  = 0;
static volatile uint8_t _recv_oku  = 0;
static volatile bool    _recv_flag = false;

// TIP_RTK: ayri, degisken boyutlu ISR-safe buffer.
// RTK sabit mesh_paket_t zarfini degil, degisken uzunlukta buyuk zarfi
// kullaniyor. Diger TIP'lerin _recv_buffer/mesh_paket_t yolunu degistirmemek
// icin RTK'ye ayri ring buffer ayrildi. Zarf onsozu her iki zarf tipinde de
// ayni bayt duzeninde oldugundan (offset 17'de tip byte'i) ISR tam parse
// etmeden bu offset'e bakip hangi buffer'a yazacagina karar verebiliyor.
#define RTK_RECV_BUFFER_SIZE  8
static struct {
    uint8_t  veri[RTK_ENV_MAKS_TOPLAM];
    uint16_t uzunluk;
} _rtk_recv_buffer[RTK_RECV_BUFFER_SIZE];
static volatile uint8_t _rtk_recv_yaz  = 0;
static volatile uint8_t _rtk_recv_oku  = 0;
static volatile bool    _rtk_recv_flag = false;

// son_paket_ms volatile: callback ve loop arasinda paylasiliyor
extern volatile unsigned long son_paket_ms;

static uint8_t  _benim_mac[6];
static uint16_t _paket_sayaci     = 0;
static uint32_t _son_heartbeat_ms = 0;
static node_durum_t _bilinen_nodlar[MESH_MAX_NODES] = {};
static uint32_t _duplikat_tampon[DUPLIKAT_TAMPON]   = {};
static uint8_t  _duplikat_indeks                    = 0;

// Callback artik gonderenin MAC'ini ayri parametre olarak aliyor: MAC pakette
// tasinmiyor, ESP-NOW alim callback'inden geliyor (bkz mesh_paket_t notu).
typedef void (*mesh_veri_callback_t)(const uint8_t* kaynak_mac,
                                      const mesh_paket_t* paket);
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

// Duplikat tespiti: unicast'te WiFi katmani ACK kaybolursa paketi tekrar
// gonderir ve alici ayni paketi iki kez gorebilir. paket_id + MAC karisimi
// son DUPLIKAT_TAMPON pakette tutulur.
//
// NOT: Bu bir GUVENLIK mekanizmasi DEGIL, sadece kopya elemesi. Eski surumdeki
// anti-replay (NVS'te kalici session sayaci) kaldirildi — bkz dosya basindaki
// GUVENLIK MODELI notu.
// MAC artik pakette olmadigi icin disaridan (callback parametresinden) gelir.
static inline uint32_t _paket_hash(const uint8_t* kaynak_mac, const mesh_paket_t* p) {
    uint32_t mac_part = ((uint32_t)kaynak_mac[5] << 24)
                      | ((uint32_t)kaynak_mac[4] << 16)
                      | ((uint32_t)kaynak_mac[3] << 8)
                      |  (uint32_t)kaynak_mac[2];
    return mac_part ^ ((uint32_t)p->paket_id | ((uint32_t)p->tip << 16));
}
static inline bool _duplikat_mi(const uint8_t* kaynak_mac, const mesh_paket_t* p) {
    uint32_t h = _paket_hash(kaynak_mac, p);
    for (uint8_t i = 0; i < DUPLIKAT_TAMPON; i++)
        if (_duplikat_tampon[i] == h) return true;
    return false;
}
static inline void _duplikat_kaydet(const uint8_t* kaynak_mac, const mesh_paket_t* p) {
    _duplikat_tampon[_duplikat_indeks] = _paket_hash(kaynak_mac, p);
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
    node_durum_t* bos    = nullptr;
    node_durum_t* tanidik = nullptr;
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (_mac_esit(_bilinen_nodlar[i].mac, mac)) {
            if (_bilinen_nodlar[i].aktif) return &_bilinen_nodlar[i];
            // Pasif ama tanidik MAC: slotu koruyarak canlandirilir.
            tanidik = &_bilinen_nodlar[i];
            break;
        }
        // Hic kullanilmamis slot: MAC'i hala sifir olan.
        if (!_bilinen_nodlar[i].aktif && bos == nullptr) {
            static const uint8_t _sifir_mac[6] = {0};
            if (_mac_esit(_bilinen_nodlar[i].mac, _sifir_mac))
                bos = &_bilinen_nodlar[i];
        }
    }
    if (tanidik) {
        // aktif=true: slot rezerve kalir, asagidaki reuse yolu bu node'u kapmasin.
        tanidik->aktif = true;
        // son_heartbeat_ms BILEREK tazelenmez: canlilik (mesh_komsu_sayisi ve
        // node timeout, ikisi de bu damgaya bakar) ancak KIMLIK dogrulandiktan
        // sonra ilerlemeli. Tazeleme mesh_veri_al icinde, mac_to_id whitelist'i
        // gectikten sonra yapilir; aksi halde tanimadigimiz bir MAC'in paketi
        // komsu sayisini sisirirdi.
        return tanidik;
    }
    if (bos == nullptr) {
        // Hic bos slot yok: en eski pasif node'un yerini al.
        for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
            if (!_bilinen_nodlar[i].aktif) { bos = &_bilinen_nodlar[i]; break; }
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
static volatile uint32_t _gonderim_basari = 0;
static volatile uint32_t _gonderim_hata  = 0;
static volatile uint32_t _paket_dustu    = 0;
static volatile uint32_t _crc_hatasi     = 0;   // CRC16 tutmayan paket (parazit gostergesi)

// hedef == nullptr -> broadcast, aksi halde unicast.
//
// UNICAST vs BROADCAST — neden ikisi de var:
//   Unicast'te 802.11 katmani donanim ACK'i uretir ve kaybolan paketi KENDI
//   yeniden gonderir. Broadcast'te ACK yoktur: paket havada kaybolursa kimse
//   fark etmez ve telafi edilmez. Bu yuzden hedefi belli olan kritik trafik
//   (YKİ <-> drone telemetri/komut, RTCM) unicast gider; herkese ayni anda
//   ulasmasi gereken trafik (komsu konumu, heartbeat) broadcast kalir —
//   orada tek iletim N alicaya ulasir ve kayip bir sonraki periyotta kapanir.
static inline esp_err_t _mesh_gonder(mesh_paket_t* p, const uint8_t* hedef) {
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

    if (hedef == nullptr) hedef = BROADCAST_MAC;
    // Unicast hedefi peer olarak kayitli degilse esp_now_send() ESP_ERR_ESPNOW_NOT_FOUND
    // dondurur. Kaydi burada tamamla; aksi halde henuz heartbeat duymadigimiz bir
    // node'a ilk komut sessizce duserdi.
    if (!_broadcast_mi(hedef) && !esp_now_is_peer_exist(hedef)) {
        esp_now_peer_info_t peer = {};
        memcpy(peer.peer_addr, hedef, 6);
        peer.channel = MESH_KANAL;
        peer.encrypt = false;
        esp_now_add_peer(&peer);
    }

    // Kritik paketler icin yerel retry (3 deneme, aralikli). Bu retry
    // esp_now_send()'in YEREL hatasini (TX kuyrugu dolu) kurtarir. Havada
    // kaybolan paketi ise yalnizca unicast kurtarir (802.11 ACK + retry);
    // broadcast'te oyle bir mekanizma yoktur.
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

static inline void mesh_gonder(const uint8_t* veri, uint8_t tip,
                                const uint8_t* hedef = nullptr) {
    mesh_paket_t p = {};
    p.sihir    = MESH_SIHIR;
    p.tip      = tip;
    p.paket_id = ++_paket_sayaci;
    memcpy(p.veri, veri, sizeof(p.veri));
    p.crc      = _paket_crc_hesapla(&p);
    _duplikat_kaydet(_benim_mac, &p);   // kendi yayinimizi kopya sanmayalim
    _mesh_gonder(&p, hedef);
}

// TIP basina gonderim hiz limiti (Pi -> mesh yonu).
// Tek bir zaman damgasi tum tipler arasinda paylasilsaydi bir cerceve, baska
// bir tipin gonderiminden sonraki 50ms icinde gelince sessizce duserdi
// (kuyruk/retry/log/sayac yok).
//
// Neden kritik: TIP_QR_DATA tek atimlik bir olay ve sartname cezasi "QR
// mesajinin gorev boyunca en az bir kez dahi goruntulenememesi" (s.13).
// Periyodik telemetriyle (POSE ~10Hz, LEADER_HB) ayni kapiyi paylasinca QR
// sistematik olarak en pahali mesaj oluyordu.
//
// Karar: tip basina ayri zaman damgasi. Kapinin amaci "hatali bir Pi mesh'i
// bogmasin" ve bu korunuyor; her tip hala kendi araligiyla sinirli. Kalkan tek
// sey tiplerin birbirini yemesi.
//
// Kalan sinir (bilincli): ayni tipten art arda iki cerceve 50ms icinde gelirse
// biri yine duser (or. iki QR). Sayac bunu gorunur kilar.
//
// Dizi TIP byte'i ile dogrudan indexlenir (paralel esleme tablosu yok): yeni
// TIP eklendiginde tabloyu guncellemeyi unutma riski olmasin diye.
#define MESH_TIP_TABLO_BOYU 16
static_assert(TIP_QR_DATA < MESH_TIP_TABLO_BOYU,
              "En buyuk TIP hiz-limiti tablosuna sigmiyor: MESH_TIP_TABLO_BOYU'nu buyut.");

static uint32_t _son_tip_gonderim_ms[MESH_TIP_TABLO_BOYU] = {};
static uint32_t _tip_dusen[MESH_TIP_TABLO_BOYU]           = {};

// true donerse cagiran mesh_gonder() yapabilir. Dusen cerceve tip bazinda
// sayilir: "QR neden gitmedi" ile "Pi kacak yapiyor" zit teshisler ve tek sayac
// ikisini ayirt etmez.
static inline bool mesh_tip_gecebilir(uint8_t tip, uint32_t simdi, uint32_t min_aralik_ms) {
    if (tip >= MESH_TIP_TABLO_BOYU) {
        // Yeni bir TIP eklenmis ama tablo buyutulmemis. Fail-closed + gurultulu
        // log: sessizce gecirmek o tip icin hiz limitini komple kaldirirdi.
        // (static_assert bunu derlemede yakalar; bu dal o assert'in gevsetildigi
        // senaryonun sigortasi.)
        Serial.printf("[MESH] KRITIK: TIP 0x%02X hiz-limiti tablosuna sigmiyor "
                      "(boyut %u) - REDDEDILDI. MESH_TIP_TABLO_BOYU'nu buyut.\n",
                      tip, (unsigned)MESH_TIP_TABLO_BOYU);
        return false;
    }
    if (simdi - _son_tip_gonderim_ms[tip] < min_aralik_ms) {
        _tip_dusen[tip]++;
        return false;
    }
    _son_tip_gonderim_ms[tip] = simdi;
    return true;
}

static inline void mesh_tip_dusen_yazdir(void) {
    Serial.print("[MESH] hiz-limitinde dusen cerceve:");
    bool var = false;
    for (uint8_t t = 0; t < MESH_TIP_TABLO_BOYU; t++) {
        if (_tip_dusen[t]) {
            Serial.printf(" tip0x%02X=%lu", t, (unsigned long)_tip_dusen[t]);
            var = true;
        }
    }
    if (!var) Serial.print(" yok");
    Serial.println();
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

// NOT: _paketi_ilet() (coklu-atlama relay) kaldirildi. Gerekce:
//   - ESP-NOW menzili (100m+ acik alan) yarisma sahasi icin fazlasiyla yeterli;
//     3 drone ve bir baz dogrudan menzil icinde.
//   - Relay, RTK'nin tek yuvali reassembly'sini bozuyordu: gecikmis bir kopya
//     devam eden birlestirmeyi siliyor ve o RTCM mesaji bir daha gelmiyordu
//     (bkz rtk_pure.h on kosul (b)).
//   - Her relay havada ekstra iletim demek; carpisma olasiligini artiriyordu.
// Menzil sorunu cikarsa cozum relay degil, once anten/konumlandirma.

static inline void _heartbeat_gonder() {
    uint8_t bos[18] = {};
    mesh_gonder(bos, TIP_HEARTBEAT);   // broadcast: canlilik herkesi ilgilendirir
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

// ISR callback: sadece buffer'a yazar.
#define ISR_DUPLIKAT_TAMPON 4
static DRAM_ATTR uint32_t _isr_hashler[ISR_DUPLIKAT_TAMPON] = {};
static DRAM_ATTR uint8_t  _isr_hash_idx = 0;

static inline IRAM_ATTR bool _isr_duplikat_mi(const uint8_t* kaynak_mac,
                                               const mesh_paket_t* p) {
    uint32_t h = (uint32_t)p->paket_id
               ^ ((uint32_t)kaynak_mac[5] << 24)
               ^ ((uint32_t)kaynak_mac[4] << 16)
               ^ ((uint32_t)p->tip << 8);
    for (uint8_t i = 0; i < ISR_DUPLIKAT_TAMPON; i++)
        if (_isr_hashler[i] == h) return true;
    _isr_hashler[_isr_hash_idx] = h;
    _isr_hash_idx = (_isr_hash_idx + 1) % ISR_DUPLIKAT_TAMPON;
    return false;
}

static portMUX_TYPE _recv_mux = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR _esp_now_recv_cb(const uint8_t* mac_addr,
                                        const uint8_t* data, int len) {
    // Ilk kapi: sihir. Baska takimin ESP-NOW trafigi burada, CRC hesabina bile
    // girmeden elenir. Kucuk paket ve RTK zarfi ayni onsozu paylasir
    // (sihir[2] + tip[1]), o yuzden tek kontrol ikisini de kapsar.
    if (len < 3) return;
    uint16_t sihir; memcpy(&sihir, data, 2);
    if (sihir != MESH_SIHIR) return;

    // Kendi yayinimizi geri alirsak (broadcast'te olur) isleme.
    if (_benim_mac_mi(mac_addr)) return;

    // TIP_RTK degisken boyutlu buyuk zarf kullanir, kendi ring buffer'ina gider.
    if (data[2] == TIP_RTK) {
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
    if (_isr_duplikat_mi(mac_addr, p)) return;
    // Kritik bolge: dual-core race condition onleme
    portENTER_CRITICAL_ISR(&_recv_mux);
    uint8_t sonraki = (_recv_yaz + 1) % RECV_BUFFER_SIZE;
    if (sonraki == _recv_oku) {
        portEXIT_CRITICAL_ISR(&_recv_mux);
        return; // buffer dolu, paketi at
    }
    memcpy(_recv_buffer[_recv_yaz].kaynak_mac, mac_addr, 6);
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

// Buffer'dan paket isle, mesh_loop() icinde cagrilir.
// Buffer'dan paket isle, mesh_loop() icinde cagrilir.
//
// Kabul zinciri (her kapi bir onceki gectikten sonra):
//   1. sihir     -> ISR'da elendi (yabanci trafik buraya hic gelmez)
//   2. CRC16     -> havada bozulan paket burada duser
//   3. duplikat  -> unicast retry kopyasi burada duser
//   4. mac_to_id -> tablodaki MAC degilse callback icinde reddedilir
static inline void _recv_isle() {
    _recv_flag = false; // Once sifirla: sonraki ISR yazimini kaybetme
    while (_recv_oku != _recv_yaz) {
        const uint8_t* kaynak_mac = _recv_buffer[_recv_oku].kaynak_mac;
        mesh_paket_t*  p          = &_recv_buffer[_recv_oku].paket;

        // CRC: havada bozulan paketi ele. 802.11 FCS'i zaten var ama bu bizim
        // kendi cerceveleme/kopyalama hatalarimizi da yakalar ve ucuz (2 bayt).
        if (p->crc != _paket_crc_hesapla(p)) {
            _crc_hatasi++;
            _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
            continue;
        }

        if (!_duplikat_mi(kaynak_mac, p)) {
            _duplikat_kaydet(kaynak_mac, p);

            node_durum_t* node = _node_bul_veya_ekle(kaynak_mac);

            // Peer kaydi: unicast ile cevap verebilmek icin sart. Eskiden GCM
            // dogrulamasindan sonra yapiliyordu; artik CRC + sihir kapisi ayni
            // isi goruyor.
            if (node && !node->peer_kayitli) {
                _peer_ekle(kaynak_mac);
                node->peer_kayitli = true;
            }

            // TIP_HEARTBEAT dahil TUM tipler callback'e gider.
            //
            // Eskiden heartbeat burada ayri isleniyor ve callback'e HIC
            // ulasmiyordu. Sonucu: heartbeat failsafe zamanlayicisini
            // (son_paket_ms) tazelemiyordu. Baz yalnizca heartbeat yayinlarken
            // (komut akmayan sessiz donem) drone kendini kopmus sanip failsafe'e
            // girebiliyordu — oysa heartbeat'in tek isi "link ayakta" demek.
            // Artik canlilik tazelemesi callback icinde, mac_to_id whitelist'i
            // GECTIKTEN sonra yapiliyor (tanimadigimiz MAC komsu sayisini
            // sismesin) ve heartbeat oradan UART'a iletilmeden donuyor.
            if (_veri_callback) _veri_callback(kaynak_mac, p);
        }

        _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
    }
}

// Ucus oncesi manuel spektrum taramasi.
// Otomatik kanal degisimi bilincli olarak yok: dagitik mesh'te haberlesme
// kesilince cihazlarin "hangi kanala gecelim" diye anlasmasi mumkun degil
// (tavuk-yumurta), reaktif kanal degisimi kalici desync'e yol acabilir.
// Bunun yerine operator ucustan once bu fonksiyonu calistirir, MESH_KANAL (11)
// ve MESH_KANAL_YEDEK (6) uzerindeki trafik/gurultuyu Serial'e raporlar. Rapora
// gore gerekirse MESH_KANAL define'i degistirilip tum cihazlar ayni degerle
// yeniden flaslanir; senkron boylece ayni kaynak kod ile saglanir.
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

// NVS'e hic dokunmaz. Onceki surum burada AES anahtarini okuyor ve monoton
// boot sayacini artiriyordu; ikisi de kaldirildi (bkz dosya basindaki GUVENLIK
// MODELI). Pratik sonuc: firmware yuklemesi artik hicbir kalici durumu
// bozamaz, provizyon adimi yok, "duyar ama duyulmaz" arizasi imkansiz.
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
    Serial.printf("  Aktif: %d/%d  crc_hatasi=%lu paket_dustu=%lu\n",
        aktif, MESH_MAX_NODES,
        (unsigned long)_crc_hatasi, (unsigned long)_paket_dustu);
    Serial.println("==================");
}

// Joystick komut struct (float32 encoding).
// Bu struct'in layout'u pi_bridge ile paylasilan bir sozlesmedir. Karsi taraf:
// feature/esp32-bridge, packet_parser.py::_KOMUT_FMT '<BBhhhh6x' (alt_tip, flags,
// roll, pitch, yaw, throttle, 6 dolgu = 16B). ESP payload'i opak tasir ama alan
// sirasi/boyutu degisirse bridge sessizce yanlis cozer; degistirmeden once iki
// tarafi birlikte guncelleyin.
struct __attribute__((packed)) komut_veri_t {
    uint8_t  alt_tip;      // KOMUT_MODE_SWARM_MOVEMENT=1 / KOMUT_MODE_MANEUVER=2
    // Bu byte "rezerv1" degil: pi_bridge onu flags olarak kullaniyor ve icinde
    // guvenlik kritik deadman biti var (bkz KOMUT_FLAG_* asagida; bayrak biti
    // yoksa her komut sessizce reddedilir). "rezerv" adi bu byte'in yeniden
    // kullanilmasina davetiye olurdu, kurban deadman olurdu.
    uint8_t  flags;        // KOMUT_FLAG_* bit alani
    int16_t  roll_x100;    // float * 100 -> int16 (+-327.67 derece/s)
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

// Layout sozlesmesini derleme zamaninda kilitle: bridge cerceveden sabit 16 byte
// diliyor (packet_parser.py::cerceve_coz -> govde[2:18]), boyut 16'dan sapamaz;
// kucukse bridge cop okur, buyukse sessizce kirpar.
static_assert(sizeof(komut_veri_t) == 16,
              "komut_veri_t 16 byte OLMALI — pi_bridge govde[2:18] ile sabit 16B diliyor");
static_assert(offsetof(komut_veri_t, flags) == 1,
              "flags offset 1 OLMALI — pi_bridge _KOMUT_FMT '<BBhhhh6x' bunu varsayiyor (deadman biti!)");
static_assert(offsetof(komut_veri_t, roll_x100) == 2,
              "roll_x100 offset 2 OLMALI — pi_bridge _KOMUT_FMT ile uyum");
static_assert(offsetof(komut_veri_t, throttle_x100) == 8,
              "throttle_x100 offset 8 OLMALI — pi_bridge _KOMUT_FMT ile uyum");