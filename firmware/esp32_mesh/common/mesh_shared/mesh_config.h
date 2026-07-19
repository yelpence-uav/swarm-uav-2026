#pragma once

#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include "esp_wifi.h"      // promiscuous mod kanal taramasi icin
#include "encryption.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rtk_pure.h"      // RTK_ENV_MAKS_TOPLAM vb. tek yerden
#include "replay_pure.h"   // anti_replay_t/replay_state_t + saf replay karari

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

struct __attribute__((packed)) mesh_paket_t {
    uint8_t  kaynak_mac[6];
    uint8_t  hedef_mac[6];
    uint32_t paket_id;
    uint8_t  atlama_sayisi;
    uint8_t  tip;
    uint8_t  iv[12];           // GCM nonce (12 byte, NIST onerisi)
    uint8_t  sifreli_veri[24]; // anti_replay(6) + payload(18)
    uint8_t  tag[16];          // GCM auth tag: sifre cozumunde dogrulanir
};

// Sliding window anti-replay.
// PENCERE_BOYU, anti_replay_t, replay_state_t ve karar mantigi replay_pure.h'de.
// Burasi sadece ince kabuk: loglama + NVS persist.
//
// Sozlesme kilidi (iki pure header arasindaki tek bag): anti_replay_t
// replay_pure.h'de, kablodaki boyutu ise rtk_pure.h'de RTK_ANTI_REPLAY_BOYUTU
// literali (6). Iki header birbirini include etmiyor, bagi kuran tek yer burasi.
// rtk_mesh_gonder() zarfi kurarken memcpy(plaintext, &ar, RTK_ANTI_REPLAY_BOYUTU)
// yapiyor; anti_replay_t buyurse memcpy 6 bayta kirpar ve alicida anti-replay
// coker. RTK_FRAG_PAYLOAD_MAKS degismedigi icin rtk_pure.h'deki "== 191" assert'i
// patlamaz, bu assert o kor noktayi kapatir. Patlarsa once spec §2.3 layout ve
// byte butcesini guncelle, YKİ/pi_bridge'e bildir, sonra sayiyi degistir.
static_assert(sizeof(anti_replay_t) == RTK_ANTI_REPLAY_BOYUTU,
              "anti_replay_t kablo boyutu RTK_ANTI_REPLAY_BOYUTU ile uyumsuz: "
              "rtk_handler.h'deki memcpy sessizce kirpar ve anti-replay coker. "
              "Spec §2.3'u guncelle, YKİ/pi_bridge'e bildir, sonra sayiyi degistir.");
static_assert(offsetof(anti_replay_t, paket_id) == 2,
              "anti_replay_t alan sirasi degisti: tel formati (spec §2.3, "
              "offset 0=session_id/2B, 2=paket_id/4B) bozulur.");
//
// TODO: GPS_TIMESTAMP: HAS_PIXHAWK + MAVLink GPS okumasi hazir oldugunda
//   session_id'nin yerine degil yanina konulacak. Bootstrap sorunu var
//   (boot'ta fix yokken fail-closed = GPS'siz ucamazsin, fail-open =
//   saldirganin istedigi pencere) ve tek basina ayni saniye icindeki
//   replay'i durdurmaz, sayac yine gerekli.

struct node_durum_t {
    uint8_t        mac[6];
    uint32_t       son_heartbeat_ms;
    bool           aktif;
    bool           peer_kayitli;
    replay_state_t replay;
    // Fail-closed yapiskanligi: _peer_session_kaydet() basarisiz olursa tek
    // paketi reddetmek yetmezdi; replay_karar() RAM durumunu persist
    // denemesinden once guncelledigi icin peer'in sonraki paketi "ayni session"
    // dalindan kabul alip persist edilmeden iceri girerdi. Bayrak bir kez
    // kalkinca bu node'un tum paketleri basarili persist olana kadar reddedilir.
    bool           persist_hatasi;
};

// ISR-safe paket buffer: callback sadece buraya yazar, mesh_loop() okur.
#define RECV_BUFFER_SIZE 16
static struct {
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

// Peer session kaliciligi (alici yarisi).
// session_id gonderici tarafinda monoton (bkz mesh_init: NVS boot sayaci). Bu
// tek basina yetmez: alici da son gordugu session_id'yi persist etmezse
// saldirgan "aliciyi reboot ettir, eski session'i oynat" senaryosuna kayar.
// Yazma sikligi: peer basina, peer'in boot'u basina bir kez (session
// degisiminde). Paket basina yazma yok, flash omru sorunu olmaz.
struct __attribute__((packed)) peer_session_kayit_t {
    uint8_t  mac[6];
    uint16_t session_id;   // 0 = kayit yok
};   // 8 byte

// Tablo boyutu MESH_MAX_NODES degil, MESH_MAX_NODES+1: mesh'te en fazla
// MESH_MAX_NODES drone ve ayrica baz istasyonu var, hepsi ayri birer peer.
// MESH_MAX_NODES (8) olsaydi 8 drone + baz = 9 peer'de tablo dolar ve son peer
// kalici replay korumasindan mahrum kalirdi.
#define PEER_SESS_TABLO_BOYU  (MESH_MAX_NODES + 1)

// Sozlesme kilidi: tablo her zaman tum droneler + baz'i alabilmeli. Gevsetilirse
// _peer_session_kaydet()'in fail-closed dali (peer'in paketlerini reddet) sahada
// tetiklenir. Patlarsa PEER_SESS_TABLO_BOYU'nu buyut, tabloyu kucultme.
static_assert(PEER_SESS_TABLO_BOYU >= MESH_MAX_NODES + 1,
              "peer session tablosu tum droneleri + bazi alamiyor: son peer "
              "reboot-replay korumasiz kalir (fail-closed'da ise REDDEDILIR). "
              "PEER_SESS_TABLO_BOYU'nu buyut.");

static peer_session_kayit_t _peer_sessions[PEER_SESS_TABLO_BOYU] = {};

static inline uint16_t _peer_session_getir(const uint8_t* mac) {
    for (uint8_t i = 0; i < PEER_SESS_TABLO_BOYU; i++)
        if (_peer_sessions[i].session_id != 0 && _mac_esit(_peer_sessions[i].mac, mac))
            return _peer_sessions[i].session_id;
    return 0;   // kayit yok
}

// Fail-closed: basarisizsa false doner ve cagiran taraf paketi reddeder.
// Repodaki diger guvenlik yollari (aes_init provision-yok, drone_tablo ID
// cakismasi, _session_id_uret NVS hatasi) da fail-closed. "Tablo dolu" yolu
// PEER_SESS_TABLO_BOYU assert'i sayesinde normalde ulasilamaz; bu dal o assert'in
// gevsetildigi senaryonun sigortasi.
static inline bool _peer_session_kaydet(const uint8_t* mac, uint16_t sid) {
    int8_t slot = -1;
    for (uint8_t i = 0; i < PEER_SESS_TABLO_BOYU; i++) {
        if (_peer_sessions[i].session_id != 0 && _mac_esit(_peer_sessions[i].mac, mac)) { slot = (int8_t)i; break; }
        if (_peer_sessions[i].session_id == 0 && slot < 0) slot = (int8_t)i;   // ilk bos
    }
    if (slot < 0) {
        Serial.printf("[REPLAY] KRITIK: peer_sess tablosu dolu, %02X:%02X REDDEDILIYOR "
                      "(kalici replay korumasi verilemiyor). PEER_SESS_TABLO_BOYU'nu buyut.\n",
                      mac[4], mac[5]);
        return false;
    }
    memcpy(_peer_sessions[slot].mac, mac, 6);
    _peer_sessions[slot].session_id = sid;
    Preferences prefs;
    if (!prefs.begin("mesh_sec", false)) {
        // RAM kaydi guncellendi ama NVS'e yazilamadi: bu oturumda koruma calisir
        // ama biz reboot edersek kayit kaybolur, "aliciyi reboot ettir, eski
        // session'i oynat" acigi geri acilir. Kalici garanti veremiyoruz,
        // o yuzden fail-closed.
        Serial.printf("[REPLAY] KRITIK: NVS acilamadi, %02X:%02X icin peer session "
                      "PERSIST EDILEMEDI -> REDDEDILIYOR\n", mac[4], mac[5]);
        return false;
    }
    size_t yazilan = prefs.putBytes("peer_sess", _peer_sessions, sizeof(_peer_sessions));
    prefs.end();
    if (yazilan != sizeof(_peer_sessions)) {
        Serial.printf("[REPLAY] KRITIK: peer_sess yazilamadi (%u/%u byte), %02X:%02X "
                      "REDDEDILIYOR\n", (unsigned)yazilan, (unsigned)sizeof(_peer_sessions),
                      mac[4], mac[5]);
        return false;
    }
    return true;
}

static inline void _peer_session_yukle(void) {
    Preferences prefs;
    if (prefs.begin("mesh_sec", true)) {
        // Kayit yoksa getBytes 0 doner; dizi sifir kalir (= kayit yok).
        prefs.getBytes("peer_sess", _peer_sessions, sizeof(_peer_sessions));
        prefs.end();
    }
}

// session_id kurali monoton: "farkli" degil, "daha buyuk" olmali.
//   ar->session_id  < bilinen  -> eski session, reddet (reboot-replay saldirisi)
//   ar->session_id == bilinen  -> ayni session, normal pencere mantigi
//   ar->session_id  > bilinen  -> gonderici reboot etti, kabul + persist
//
// Kalan bosluk (bilincli): ayni session icinde node NODE_TIMEOUT_MS boyunca
// susarsa replay penceresi RAM'de sifirlanir (en_yuksek_id persist edilmiyor,
// flash omru). Bunu daraltmak icin _node_bul_veya_ekle() pasif ama tanidik
// MAC'i replay durumunu koruyarak canlandiriyor; bosluk sadece node tablodan
// tamamen dusurulup slot'u baskasina verilirse acilir. Tam cozum GPS zaman
// damgasi TODO'sunda. Karar replay_pure.h::replay_karar()'da, burasi yalnizca
// NVS persist + loglama yapar.
static inline bool _replay_kontrol(node_durum_t* node, const anti_replay_t* ar) {
    // Fail-closed yapiskanligi: bu node icin kalici kayit verilemediyse duzelene
    // kadar hicbir paketini kabul etme (bkz node_durum_t::persist_hatasi).
    if (node->persist_hatasi) {
        Serial.printf("[REPLAY] %02X:%02X persist hatasi nedeniyle reddediliyor "
                      "(kalici replay korumasi yok)\n", node->mac[4], node->mac[5]);
        return false;
    }

    uint16_t kalici = _peer_session_getir(node->mac);
    replay_sonuc_t s = replay_karar(&node->replay, ar->session_id, ar->paket_id, kalici);

    switch (s) {
        case REPLAY_KABUL_YENI_SESSION:
            // Yeni (daha buyuk) session kabul edildi, kalici kaydi guncelle.
            // Peer basina, peer'in boot'u basina tek yazma. Fail-closed:
            // persist edemezsek bu paketi de sonrakileri de reddet, cunku kalici
            // garanti veremedigimiz peer'i kabul etmek reboot-replay acigini acar.
            if (!_peer_session_kaydet(node->mac, ar->session_id)) {
                node->persist_hatasi = true;
                return false;
            }
            return true;
        case REPLAY_KABUL:
            return true;
        case REPLAY_RED_ESKI_SESSION:
            // Bu log sahadaki tek ipucu. sid cok dusukse (or. 1-2) muhtemelen
            // saldiri degil, o peer'in NVS'i silinmistir (erase_flash) ve boot
            // sayaci sifirlanmistir; bkz _session_id_uret() basindaki NVS erase tuzagi.
            Serial.printf("[REPLAY] ESKI SESSION reddedildi: %02X:%02X sid=%u < kalici=%u\n",
                          node->mac[4], node->mac[5], ar->session_id, kalici);
            if (ar->session_id <= 2) {
                Serial.printf("[REPLAY] ^ sid cok dusuk: %02X:%02X NVS'i silinmis olabilir "
                              "(erase_flash). Bu peer KALICI reddedilir. Kurtarma: "
                              "bkz mesh_config.h::_session_id_uret NVS ERASE TUZAGI\n",
                              node->mac[4], node->mac[5]);
            }
            return false;
        case REPLAY_RED_DUPLIKAT:
        case REPLAY_RED_ESKI_PAKET:
        default:
            return false;
    }
}

static inline uint32_t _paket_hash(const mesh_paket_t* p) {
    // paket_id tam 32 bit; MAC'in alt baytlariyla XOR'lanip karistiriliyor.
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
    node_durum_t* bos    = nullptr;
    node_durum_t* tanidik = nullptr;
    for (uint8_t i = 0; i < MESH_MAX_NODES; i++) {
        if (_mac_esit(_bilinen_nodlar[i].mac, mac)) {
            if (_bilinen_nodlar[i].aktif) return &_bilinen_nodlar[i];
            // Pasif ama tanidik MAC. Replay durumu sifirlanarak yeniden
            // eklenirse (ilk_paket=true -> pencere sifir) saldirgan
            // NODE_TIMEOUT_MS (12s) boyunca jam yapip node'u dusurdukten sonra
            // ayni session'in eski paketlerini tekrar oynatabilir. O yuzden
            // pasif tanidik node replay durumu korunarak canlandirilir.
            tanidik = &_bilinen_nodlar[i];
            break;
        }
        if (!_bilinen_nodlar[i].aktif && _bilinen_nodlar[i].replay.session_id == 0 &&
            bos == nullptr)
            bos = &_bilinen_nodlar[i];   // hic kullanilmamis slot
    }
    if (tanidik) {
        // aktif=true: slot rezerve kalir (asagidaki "en eski pasif node'u geri
        // don" reuse yolu bu node'u kapmasin, replay durumu korunsun).
        tanidik->aktif = true;
        // son_heartbeat_ms BILEREK tazelenmez: node canliligi (mesh_komsu_sayisi
        // + node timeout, ikisi de son_heartbeat_ms tazeligine bakar) ancak paket
        // replay'i GECTIKTEN sonra ilerlemeli. Aksi halde replay'de dusecek bir
        // tekrar-oynatma, olu komsuyu burada "taze" yapip mesh_komsu_sayisi'ni
        // sisirir ve timeout'u baskilardi (ORTA-1/O1). Tazeleme replay sonrasi
        // yapilir: veri -> callback (mesh_veri_al), heartbeat -> _recv_isle.
        // replay durumuna dokunulmaz: pencere ve session_id korunur.
        return tanidik;
    }
    if (bos == nullptr) {
        // Hic bos slot yok: en eski pasif node'un yerini al. Replay durumu
        // kaybolur ama NVS'teki peer_session kaydi eski session'i yine reddeder.
        for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
            if (!_bilinen_nodlar[i].aktif) { bos = &_bilinen_nodlar[i]; break; }
    }
    if (bos) {
        memcpy(bos->mac, mac, 6);
        bos->aktif = true;
        bos->peer_kayitli = false;
        bos->son_heartbeat_ms = millis();
        bos->replay = {};
        bos->replay.ilk_paket = true;
        // Slot baska bir MAC'e veriliyor: persist bayragi eski MAC'e aitti,
        // yeni sahibine miras kalmamali (yoksa yeni peer haksiz reddedilir).
        // Tanidik MAC'in canlandirildigi yolda bayrak korunur, burada sifirlanir.
        bos->persist_hatasi = false;
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

    // Kritik paketler icin retry (3 deneme, aralikli).
    // Hedef broadcast oldugu icin ESP-NOW donanim ACK'i yoktur; bu retry sadece
    // yerel gonderim hatasini (TX kuyrugu dolu, esp_now_send() basarisiz)
    // kurtarir, havada/menzil disinda kaybolan paketi kurtaramaz.
    // TIP_RTK bu listede yok: artik _mesh_gonder() yolundan gecmiyor,
    // rtk_mesh_gonder() kendi CSMA+3-deneme mantigini ayri uyguluyor.
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

// GCM AAD (ek dogrulanmis veri).
// tip + kaynak_mac + hedef_mac AAD olarak verilir; boylece bu 3 alan sifreli
// payload'i bozmadan degistirilemez (or. TIP_POSE -> TIP_GOREV). atlama_sayisi
// kasitli olarak disarida: _paketi_ilet() her hop'ta onu artirip ayni iv/tag
// ile iletir, AAD'e girseydi relay ilk hop'ta tag'i gecersiz kilardi.
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
    // Anti-replay basligini (session_id + paket_id) sifreli payload icine gom.
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

static inline void _paketi_ilet(const mesh_paket_t* gelen) {
    if (!_broadcast_mi(gelen->hedef_mac))    return;
    if (gelen->atlama_sayisi >= ATLAMA_MAKS) return;
    mesh_paket_t ilet = *gelen;
    ilet.atlama_sayisi++;
    _mesh_gonder(&ilet);
}

static inline void _heartbeat_gonder() {
    // GCM ile sifrele: sahte HB ile MAC listesine girilmesini engeller
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

// ISR callback: sadece buffer'a yazar.
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
    // TIP_RTK buyuk zarfi ayri yoldan isle. Zarf onsozu ortak oldugundan
    // (kaynak_mac[6]+hedef_mac[6]+paket_id[4]+atlama_sayisi[1] = 17 byte sonrasi
    // tip) tam parse etmeden offset 17'ye bakmak guvenli; mesh_paket_t'de de tip
    // ayni offsette.
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
    // Kritik bolge: dual-core race condition onleme
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

// Buffer'dan paket isle, mesh_loop() icinde cagrilir.
static inline void _recv_isle() {
    _recv_flag = false; // Once sifirla: sonraki ISR yazimini kaybetme
    while (_recv_oku != _recv_yaz) {
        mesh_paket_t* p = &_recv_buffer[_recv_oku].paket;

        if (!_duplikat_mi(p)) {
            _duplikat_kaydet(p);

            node_durum_t* node = _node_bul_veya_ekle(p->kaynak_mac);
            // peer kaydi GCM dogrulamasindan sonra yapilir

            if (p->tip != TIP_HEARTBEAT) {
                bool benim_icin = _broadcast_mi(p->hedef_mac) ||
                                  _benim_mac_mi(p->hedef_mac);
                if (benim_icin) {
                    // GCM burada dogrulanir; gecerse node guncellenir
                    uint8_t _acik_cb[24] = {0};
                    uint8_t _aad_cb[13];
                    _mesh_aad_olustur(p->tip, p->kaynak_mac, p->hedef_mac, _aad_cb);
                    if (!aes_coz_gcm(p->sifreli_veri, 24, _acik_cb, p->iv, p->tag, _aad_cb, sizeof(_aad_cb))) {
                        Serial.printf("[MESH] GCM hatasi tip:%d %02X:%02X\n",
                            p->tip, p->kaynak_mac[4], p->kaynak_mac[5]);
                        // sahte MAC peer listesinden cikar
                        if (node) { node->aktif = false; node->peer_kayitli = false;
                                    esp_now_del_peer(node->mac); }
                        _recv_oku = (_recv_oku + 1) % RECV_BUFFER_SIZE;
                        continue;
                    }
                    // GCM gecti: sadece dogrulanmis MAC'i peer olarak kaydet
                    if (node && !node->peer_kayitli) {
                        _peer_ekle(p->kaynak_mac);
                        node->peer_kayitli = true;
                    }
                    // Node canliligi (son_heartbeat_ms/aktif) BURADA tazelenmez:
                    // veri paketinin replay kontrolu callback icinde yapiliyor ve
                    // canlilik ancak replay GECTIKTEN sonra ilerlemeli (ORTA-1/O1).
                    // GCM'i gecmis ama replay'de dusecek bir tekrar-oynatma aksi
                    // halde olu komsuyu "taze" tutup mesh_komsu_sayisi'ni sisirirdi.
                    // Tazeleme callback'te (mesh_veri_al) replay dogrulandiktan
                    // sonra yapilir. Heartbeat yolu (asagida) ayni sirayi izler.
                    if (_veri_callback) _veri_callback(p);
                }
                if (_broadcast_mi(p->hedef_mac)) _paketi_ilet(p);
            } else {
                // Heartbeat: GCM dogrulama zorunlu (MAC spoofing onleme)
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
                    // Heartbeat GCM basarisiz olursa node'u temizle (non-heartbeat
                    // dalinda yapiliyordu, burada da gerekli). Aksi halde sahte
                    // kaynak MAC'li heartbeat NODE_TIMEOUT_MS (12sn) boyunca
                    // "aktif" sayilmaya devam ediyordu.
                    if (node) { node->aktif = false; node->peer_kayitli = false;
                                esp_now_del_peer(node->mac); }
                }
            }
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

// Monoton session id (gonderici yarisi).
// _session_id = esp_random() olsaydi rastgele ve kalici olmaz; alici
// "session_id farkli" gorunce reboot varsayip pencereyi sifirladigi icin
// saldirgan yakaladigi eski session paketlerini reboot sonrasi tekrar
// oynatabilirdi (session_id authenticated, uyduramaz ama aynen oynatabilir).
// Bu yuzden NVS'te monoton artan boot sayaci kullaniliyor; alici kucuk olani
// reddeder (bkz _replay_kontrol). Boot basina tek yazma, flash omru sorunu yok.
//
// 16-bit sarma: session_id uint16 (tel formati). 65535 boot'ta sararsa "kucukse
// reddet" kurali kirilirdi, o yuzden sarma yok, fail-closed durulur. 65535 boot
// gunde 10 boot'ta ~18 yil, pratikte erisilmez.
//
// NVS erase tuzagi (sahada bilinmesi sart, okumadan erase_flash yapma):
//   1. Drone A calisti, boot_ctr=47. Peer'lerin NVS'inde _peer_sessions[A]=47.
//   2. Biri A'ya erase_flash yapar: aes_key de boot_ctr de gider.
//   3. Anahtar yeniden yazilip firmware flaslanir ama boot_ctr 0'dan baslar,
//      A artik session_id=1 gonderir.
//   4. Peer'ler kurali dogru uygular: 1 < 47 -> A'yi kalici reddeder.
// Semptom aldatici: A peer'lerin heartbeat'lerini kabul eder (failsafe atmaz)
// ama kendi paketleri hicbir yerde kabul edilmez; red logu A'da degil peer'in
// konsolunda basilir ve durum kendiliginden duzelmez. Otomatik kurtarma yok,
// cunku bu durum saldiriyla ayirt edilemez; dusuk sid'i otomatik kabul etmek
// korumayi geri alir. Kurtarma: bir node'un NVS'ini silersen surunun tamamini
// (baz + tum droneler) birlikte erase + yeniden provision + flasla. Sadece
// peer_sess'i silmek de yeterli (NVS namespace "mesh_sec", anahtar "peer_sess").
static inline void _session_id_uret(void) {
    Preferences prefs;
    if (!prefs.begin("mesh_sec", false)) {
        Serial.println("[MESH] KRITIK: NVS acilamadi — session_id monoton olamaz.");
        Serial.println("[MESH] Replay korumasi saglanamadigi icin durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
    uint32_t boot_sayaci = prefs.getUInt("boot_ctr", 0) + 1;
    if (boot_sayaci > 0xFFFF) {
        prefs.end();
        Serial.println("[MESH] KRITIK: boot sayaci 65535'i asti (session_id uint16).");
        Serial.println("[MESH] Monoton session garantisi bitti — durduruldu.");
        Serial.println("[MESH] Cozum: tum node'larda NVS boot_ctr sifirlanip AES anahtari");
        Serial.println("[MESH] yenilenmeli (eski trafik ancak boylece replay edilemez).");
        Serial.flush();
        while (true) delay(1000);
    }
    prefs.putUInt("boot_ctr", boot_sayaci);
    prefs.end();
    _session_id = (uint16_t)boot_sayaci;   // 1..65535, 0 asla (sayac 1'den basliyor)
    Serial.printf("[MESH] session_id=%u (monoton boot sayaci, NVS)\n", _session_id);
    if (boot_sayaci <= 2) {
        // NVS erase tuzagi icin erken uyari. Tuzagi bu cihazin kendi konsolunda
        // gorunur kilan tek yer; red logu peer'in konsolunda basiliyor. Gercekten
        // ilk boot ise zararsiz bir bilgi satiri.
        Serial.println("[MESH] UYARI: boot sayaci ~sifirdan basladi (NVS yeni ya da silinmis).");
        Serial.println("[MESH] Bu cihaz DAHA ONCE mesh'te calistiysa peer'ler onu KALICI");
        Serial.println("[MESH] reddeder (eski session gorunur). 'Duyar ama duyulmaz' semptomu.");
        Serial.println("[MESH] Kurtarma: bkz mesh_config.h::_session_id_uret NVS ERASE TUZAGI");
    }
}

static inline void mesh_init(mesh_veri_callback_t callback) {
    aes_init(); // Key expansion bir kez yapilir
    _session_id_uret();     // monoton, NVS'te kalici (gonderici yarisi)
    _peer_session_yukle();  // peer_mac -> son session_id (alici yarisi)
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