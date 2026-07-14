#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include <string.h>   // ORTA-2 FIX: memcmp icin
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "uart_cobs.h"   // REV B: ortak CRC16/COBS/cerceve kur-coz (RX BASE + TX DRONE)
#include "uart_frame_parser.h"  // desync-güvenli ortak COBS çerçeve ayrıştırıcı (native testli)

#define RPI_RX_PIN 18
#define RPI_TX_PIN 19

static void uart_gonder(uint8_t tip, uint8_t kaynak_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;
    uint8_t ham[24];
    uint8_t cobs_buf[32];
    uint16_t cobs_uzunluk = cobs_cerceve_olustur(tip, kaynak_id, payload, payload_uzunluk, ham, cobs_buf);
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
// ORTA-2 FIX: eskiden yalnizca MAC'in son byte'i karsilastiriliyordu; iki
// ESP32'nin son byte'i ayni olursa (Espressif atamasinda mumkun) iki drone
// ayni ID'ye eslenip sessizce kimlik cakismasi olusuyordu. Simdi tam 6 byte
// karsilastiriliyor.
// !!! DIKKAT: asagidaki ilk 5 byte SIFIR PLACEHOLDER'dir. Gercek MAC
// adreslerini (esptool.py chip_id ile veya WiFi.macAddress() ile okunan
// tam adresi) buraya girmeden derleyip yuklemeyin — aksi halde tum
// dronelarin ilk 5 byte'i esit sayilir ve son byte'a geri donmus oluruz.
//
// BUG FIX (#1b): RX BASE'in MAC'i bu tabloda YOKTU. mesh_veri_al()
// mac_to_id()==0 olan her paketi "Bilinmeyen MAC" diye reddettigi icin
// BAZ'DAN GELEN HIC BIR PAKET (TIP_KOMUT/TIP_ORIGIN/TIP_GOREV) dispatch'e
// ulasamiyordu — joystick komut yolu bu yuzden de kopuktu. Baz artik
// BAZ_ID (99) ile tabloda. pi_bridge tarafi da uyumlu: agent_id 1-254
// kabul ediyor ve iha_id==0/kendi agent_id'si disindakileri isliyor,
// yani 99 gecerli bir kaynak kimligi.
static const struct { uint8_t mac[6]; uint8_t id; } drone_tablo[] = {
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0xB4}, 1},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0x88}, 2},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 3},
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0xFF}, 4},
    // TODO: RX BASE'in GERCEK MAC'ini gir — bu satir doldurulmadan baz'dan
    // gelen komutlar reddedilmeye devam eder (mac_to_id -> 0).
    {{0x00, 0x00, 0x00, 0x00, 0x00, 0x63}, BAZ_ID},
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);
static uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < DRONE_SAYISI; i++)
        if (memcmp(drone_tablo[i].mac, mac, 6) == 0)
            return drone_tablo[i].id;
    return 0;
}

// ORTA-2 FIX: boot'ta provision tablosunun benzersizligini dogrula.
// Iki satir ayni MAC'e sahipse (kopyala-yapistir hatasi, doldurulmamis
// placeholder vb.) sistemi acikca uyar — sessiz kimlik cakismasindansa
// gurultulu bir boot hatasi tercih edilir.
static void _drone_tablo_dogrula() {
    bool hata = false;
    for (uint8_t i = 0; i < DRONE_SAYISI; i++) {
        for (uint8_t j = i + 1; j < DRONE_SAYISI; j++) {
            if (memcmp(drone_tablo[i].mac, drone_tablo[j].mac, 6) == 0) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI MAC! "
                              "ID %u ve %u cakisiyor.\n",
                              i, j, drone_tablo[i].id, drone_tablo[j].id);
                hata = true;
            }
        }
    }
    if (hata) {
        // BUG FIX (satır satır inceleme): eskiden sadece loglayip devam
        // ediyordu — yorum "gurultulu bir boot hatasi tercih edilir" diyordu
        // ama kod sessizce ucusa izin veriyordu. ID cakismasi iki drone'un
        // AYNI joystick komutuna cevap vermesi demek (guvenlik kritik) —
        // encryption.h::aes_init()'teki provision-yok durumuyla ayni fail-
        // closed desenine getirildi: duzeltilmeden mesh'e/ucusa katilamaz.
        Serial.println("[BOOT] drone_tablo duzeltilmeden ucusa cikilmamali!");
        Serial.println("[BOOT] KRITIK: ID cakismasi - baslatma durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
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
    // REV B: TIP_RTK artik bu genel mesh_paket_t/mesh_veri_al yolundan hic
    // gecmiyor — kendi buyuk zarfiyla ayri geliyor (bkz rtk_handler.h::
    // rtk_mesh_loop(), loop()'ta mesh_loop() ile birlikte cagriliyor).
    // Buraya TIP_RTK asla ulasmamali (ISR'da ayristiriliyor); yine de
    // savunma amacli birakiyoruz.
    if (p->tip == TIP_RTK) return;

    uint8_t* payload = acik + sizeof(anti_replay_t);
    uint8_t uzunluk = 0;
    // BUG FIX (#1a): TIP_KOMUT bu listede YOKTU -> joystick/surus komutu
    // GCM+replay'i gecip son_paket_ms'i tazeledikten sonra "else return" ile
    // SESSIZCE DUSUYORDU. Yani yer istasyonundan gelen komutlar drone'un
    // Pi'sine hic ulasmiyordu (ESP mesh uzerinden ucus komut yolu kopuk).
    // pi_bridge (feature/esp32-bridge) tarafi bunu BEKLIYOR:
    // esp32_bridge_node.py::_cerceve_isle -> TIP_KOMUT -> _isle_komut() ->
    // /swarm/public/control/command (SwarmControlCommand: takeoff/land/rtl/
    // emergency_stop/deadman). Sim'de ROS2/DDS dogrudan kullanildigi icin
    // bu yol hic egzersiz edilmemis, o yuzden fark edilmemis.
    if      (p->tip == TIP_KOMUT)       uzunluk = sizeof(komut_veri_t);
    else if (p->tip == TIP_POSE)        uzunluk = sizeof(pose_veri_t);
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
    _drone_tablo_dogrula();  // ORTA-2 FIX: MAC benzersizligini boot'ta dogrula

    // REV B: baud 460800 kesinlesti (spec + ekip karari). Bu Serial1 hatti
    // RTK'nin yani sira joystick/pose/vb TUM Pi<->mesh protokolunu de tasiyor
    // (rtk_handler.h::_rtk_uart_gonder ayni porta yazar) — Pi tarafi da ayni
    // baud'a gecmeli. setRxBufferSize() begin()'DEN ONCE cagrilmali; sonra
    // cagrilirsa ESP32 Arduino corede SESSIZCE etkisiz kalir.
    Serial1.setRxBufferSize(2048);  // spec 3.2: UART RX buffer >= 2048B
    Serial1.begin(460800, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);
    Serial.println("[UART] RPi (Serial1, 460800) bagli");

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
    // REV B: rtk_loop() artik rtk_mesh_loop() icinden cagriliyor (RTK buyuk
    // zarfini _rtk_recv_buffer'dan bosaltip cozen fonksiyon).
    // Port varsayilani (Serial1) burada DOGRU: TX DRONE'da Serial1 gercekten
    // Pi hattidir. (RX BASE'te oyle degil, orada Serial2 acikca gecilir.)
    rtk_mesh_loop();
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

#ifndef RTK_ISTATISTIK_LOGLAMA_KAPALI
    // ADIM 5: periyodik RTK istatistik logu (spec 3.3 "periyodik debug
    // satiri"). build_flags'a -D RTK_ISTATISTIK_LOGLAMA_KAPALI eklenerek
    // kapatilabilir.
    static uint32_t son_rtk_istatistik_ms = 0;
    if (millis() - son_rtk_istatistik_ms >= 10000) {
        son_rtk_istatistik_ms = millis();
        rtk_istatistik_yazdir();
    }
#endif

    {
        // Ortak, desync-güvenli COBS çerçeve ayrıştırıcı (bkz uart_frame_parser.h).
        // BUG FIX (satır satır inceleme) TASARIMLA KALICI: eski kodda whitelist
        // dışı tip gelince "break" tüm okuma döngüsünü kırıp rpi_rx_idx=0'ı
        // atlıyordu -> bir sonraki loop()'ta yeni baytlar reddedilmiş çerçevenin
        // ortasından devam eden index'e yazılıyor, komut hattı bozuluyordu.
        // Ayrıştırıcı artık çerçeve durumunu whitelist'ten tamamen ayırıyor:
        // idx her 0x00'da koşulsuz sıfırlanır (uart_frame_parser_push), whitelist
        // sadece DÖNEN çerçeveye uygulanır ve durumu etkileyemez.
        static uart_frame_parser_t pi_parser;
        static uint32_t son_rpi_mesh_ms = 0;
        uint8_t okunan = 0;

        while (Serial1.available() && okunan < 32) {
            uint8_t b = (uint8_t)Serial1.read();
            okunan++;

            uint8_t tip_byte, id_byte_unused;
            const uint8_t* cerceve_payload;
            uint16_t cerceve_payload_uzunluk;
            if (!uart_frame_parser_push(&pi_parser, b, &tip_byte, &id_byte_unused,
                                        &cerceve_payload, &cerceve_payload_uzunluk))
                continue;

            // ORTA-2 FIX: mesh_gonder() her zaman 18 byte okuyor (memcpy(
            // tam_veri+6, veri, 18)); 16 byte'lik buffer'dan okumak 2 byte
            // stack over-read'e (UB) yol aciyordu. payload_uzunluk siniri 16'da
            // kaliyor; fazladan 2 byte sadece zaten-sifirlanmis dolgu.
            uint8_t payload[18]     = {0};
            uint8_t payload_uzunluk = (uint8_t)min((int)cerceve_payload_uzunluk, 16);
            memcpy(payload, cerceve_payload, payload_uzunluk);

            // Whitelist: sadece Pi'den gelmesi beklenen tipler. TIP_LEADER_HB
            // ve TIP_ELECTION dahil (aksi halde her drone kendi consensus
            // mesajini gonderemez -> split-brain).
            const bool izinli = (tip_byte == TIP_KOMUT  ||
                                  tip_byte == TIP_GOREV  ||
                                  tip_byte == TIP_RENK   ||
                                  tip_byte == TIP_ORIGIN ||
                                  tip_byte == TIP_DURUM  ||
                                  tip_byte == TIP_SWARM_STATE ||
                                  tip_byte == TIP_QR_DATA ||
                                  tip_byte == TIP_LEADER_HB ||
                                  tip_byte == TIP_ELECTION);
            if (izinli) {
                uint32_t simdi = millis();
                if (simdi - son_rpi_mesh_ms >= MESH_GONDERIM_MIN_MS) {
                    son_rpi_mesh_ms = simdi;
                    mesh_gonder(payload, tip_byte);
                }
            }
        }
    }
}
