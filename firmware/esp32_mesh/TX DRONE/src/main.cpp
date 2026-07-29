#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include <string.h>   // memcmp icin
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "uart_cobs.h"   // ortak CRC16/COBS/cerceve kur-coz (RX BASE + TX DRONE)
#include "uart_frame_parser.h"  // desync-guvenli ortak COBS cerceve ayristirici

#define RPI_RX_PIN 18
#define RPI_TX_PIN 19

// RPI_SERIAL0_MODU: RPi hatti Serial1 (GPIO18/19) yerine kartin USB/Serial0
// pinlerine (GPIO3=RX, GPIO1=TX — kart uzerinde "RX"/"TX" yazan pinler) alinir.
// Sahada GPIO18/19 uzerinden veri gecmedi; Serial0 pinlerinin calistigi ise
// daha once QGC testiyle biliniyordu, o yuzden kanitlanmis hat kullaniliyor.
//
// Bedeli:
//  - Ayni pinler USB-seri cevirici ile paylasimli. Firmware YUKLERKEN RPi
//    kablolari cikarilmali, yoksa iki surucu ayni hatta konusur.
//  - Debug printf'leri binary COBS akisina karisir, o yuzden loop icindekiler
//    susturuluyor (DBG_*). Boot mesajlari kaliyor: mesh trafigi baslamadan
//    bir kez basiliyorlar ve MAC tablosu hatasini gormek kritik.
#ifndef RPI_SERIAL0_MODU
#define RPI_SERIAL0_MODU 0
#endif

#if RPI_SERIAL0_MODU
  #define RPI_SERIAL       Serial
  #define DBG_PRINTLN(x)   do {} while (0)
  #define DBG_PRINTF(...)  do {} while (0)
#else
  #define RPI_SERIAL       Serial1
  #define DBG_PRINTLN(x)   Serial.println(x)
  #define DBG_PRINTF(...)  Serial.printf(__VA_ARGS__)
#endif

static void uart_gonder(uint8_t tip, uint8_t kaynak_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;
    uint8_t ham[24];
    uint8_t cobs_buf[32];
    uint16_t cobs_uzunluk = cobs_cerceve_olustur(tip, kaynak_id, payload, payload_uzunluk, ham, cobs_buf);
    RPI_SERIAL.write(cobs_buf, cobs_uzunluk);
}

volatile unsigned long son_paket_ms         = 0;
bool                   failsafe_tetiklendi  = false;
uint8_t                _failsafe_asama      = 0;
volatile uint8_t       ardisik_kayip_sayisi = 0;
uint8_t                failsafe_active_mode = APM_MODE_RTL;
volatile bool          manevra_aktif        = false;
volatile uint32_t      manevra_bitis_ms     = 0;

// Drone ID eslestirme.
// Tam 6 byte MAC karsilastiriliyor; sadece son byte'a bakilsaydi iki ESP32'nin
// son byte'i ayni oldugunda iki drone ayni ID'ye eslenip sessizce kimlik
// cakismasi olurdu.
// Dikkat: asagidaki ilk 5 byte sifir placeholder'dir. Gercek MAC adreslerini
// (esptool.py chip_id veya WiFi.macAddress() ile) buraya girmeden derleyip
// MAC'ler saha donanimindan tools/mac_reader ile okundu.
//
// RX BASE'in MAC'i de bu tabloda olmali: mesh_veri_al() mac_to_id()==0 olan
// paketleri "bilinmeyen MAC" diye reddettigi icin baz'dan gelen komutlar aksi
// halde dispatch'e ulasamaz.
// Baz'in kimligi BAZ_MESH_ID (10), BAZ_ID (99) degil. 99 RTK UART cercevesinin
// sentinel'idir; baz'a da 99 verilirse pi_bridge baz ile RTK'yi ayirt edemez ve
// RTK trafigi mesh-liveness'i tazeleyip link kopmasini maskeler (bkz mesh_config.h).
static const struct { uint8_t mac[6]; uint8_t id; } drone_tablo[] = {
    {{0xB0, 0xCB, 0xD8, 0xC8, 0xA8, 0x30}, 1},   // ylp00 (drone ESP32)
    {{0xD4, 0xE9, 0xF4, 0xFB, 0x13, 0x88}, 2},   // ylp01
    {{0xA4, 0xF0, 0x0F, 0x64, 0xA9, 0x90}, 3},   // ylp02
    // Drone 4 henuz temin edilmedi; MAC'i tools/mac_reader ile okuyup ac.
    // {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 4},
    {{0xA4, 0xF0, 0x0F, 0x64, 0xB5, 0x34}, BAZ_MESH_ID},   // RX BASE (yer)
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);
static uint8_t mac_to_id(const uint8_t* mac) {
    for (uint8_t i = 0; i < DRONE_SAYISI; i++)
        if (memcmp(drone_tablo[i].mac, mac, 6) == 0)
            return drone_tablo[i].id;
    return 0;
}

// Boot'ta provision tablosunun benzersizligini dogrula. Iki satir ayni MAC'e
// sahipse (kopyala-yapistir hatasi, doldurulmamis placeholder vb.) sistemi
// acikca uyar; sessiz kimlik cakismasindansa gurultulu boot hatasi yeglenir.
static void _drone_tablo_dogrula() {
    bool hata = false;
    for (uint8_t i = 0; i < DRONE_SAYISI; i++) {
        // 0 = "bilinmeyen MAC" sentinel'i (mac_to_id donusu), BAZ_ID (99) = RTK
        // UART sentinel'i. Ikisi de mesh kimligi olamaz: 99 verilirse pi_bridge
        // baz ile RTK'yi ayirt edemez ve RTK trafigi mesh-liveness'i maskeler
        // (bkz mesh_config.h).
        if (drone_tablo[i].id == 0 || drone_tablo[i].id == BAZ_ID) {
            Serial.printf("[BOOT] HATA: drone_tablo[%u] gecersiz ID %u "
                          "(0 ve BAZ_ID/%u yasak).\n",
                          i, drone_tablo[i].id, BAZ_ID);
            hata = true;
        }
        for (uint8_t j = i + 1; j < DRONE_SAYISI; j++) {
            if (memcmp(drone_tablo[i].mac, drone_tablo[j].mac, 6) == 0) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI MAC! "
                              "ID %u ve %u cakisiyor.\n",
                              i, j, drone_tablo[i].id, drone_tablo[j].id);
                hata = true;
            }
            // ID benzersizligi: iki satira ayni ID verilirse (or. baz ile bir
            // drone) iki node ayni kimlige eslenir ve pi_bridge kaynagi ayirt
            // edemez.
            if (drone_tablo[i].id == drone_tablo[j].id) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI ID (%u)!\n",
                              i, j, drone_tablo[i].id);
                hata = true;
            }
        }
    }
    if (hata) {
        // ID cakismasi iki drone'un ayni joystick komutuna cevap vermesi demek
        // (guvenlik kritik). Fail-closed: duzeltilmeden mesh'e/ucusa katilamaz.
        Serial.println("[BOOT] drone_tablo duzeltilmeden ucusa cikilmamali!");
        Serial.println("[BOOT] KRITIK: ID cakismasi - baslatma durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
}
// kaynak_mac ESP-NOW alim callback'inden gelir; pakette tasinmiyor.
// Sihir, CRC16 ve duplikat kapilari _recv_isle()'de gecildi. Burada kalan tek
// kapi KIMLIK: drone_tablo'da olmayan MAC reddedilir.
void mesh_veri_al(const uint8_t* kaynak_mac, const mesh_paket_t* p) {
    uint8_t kaynak_id = mac_to_id(kaynak_mac);
    if (kaynak_id == 0) {
        DBG_PRINTLN("[MESH] Bilinmeyen MAC, paket reddedildi");
        return;
    }

    node_durum_t* node = _node_bul_veya_ekle(kaynak_mac);
    if (!node) return;

    // Canlilik kimlik dogrulandiktan SONRA tazelenir: tanimadigimiz bir MAC
    // mesh_komsu_sayisi'ni sisirmemeli.
    node->son_heartbeat_ms = millis();
    node->aktif = true;

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);
    failsafe_reset();

    // HEARTBEAT buraya kadar geldi cunku failsafe zamanlayicisini tazelemesi
    // gerekiyordu (link ayakta demek). Veri tasimadigi icin RPi'ya gitmez.
    if (p->tip == TIP_HEARTBEAT) return;
    // TIP_RTK bu genel yoldan gecmez, kendi buyuk zarfiyla ayri gelir (ISR'da
    // ayristirilir). Buraya ulasmamali; yine de savunma amacli reddediyoruz.
    if (p->tip == TIP_RTK) return;

    const uint8_t* payload = p->veri;
    uint8_t uzunluk = 0;
    // TIP_KOMUT bu listede olmali: yer istasyonundan gelen joystick/surus
    // komutu aksi halde GCM+replay'i gecip son_paket_ms'i tazeledikten sonra
    // "else return" ile sessizce duser ve drone'un Pi'sine hic ulasmaz.
    // pi_bridge tarafi bunu bekliyor (esp32_bridge_node.py::_cerceve_isle ->
    // TIP_KOMUT -> _isle_komut -> SwarmControlCommand).
    if      (p->tip == TIP_KOMUT)       uzunluk = sizeof(komut_veri_t);
    // TIP_GOTO: YKİ'den gelen guided nokta-git; TIP_KOMUT gibi Pi'ye iletilmeli
    // (esp32_bridge_node.py::_isle_goto -> AgentSetpoint). Iletilmezse guided ucus olmaz.
    else if (p->tip == TIP_GOTO)        uzunluk = sizeof(goto_veri_t);
    else if (p->tip == TIP_POSE)        uzunluk = sizeof(pose_veri_t);
    else if (p->tip == TIP_GOREV)       uzunluk = sizeof(gorev_veri_t);
    else if (p->tip == TIP_RENK)        uzunluk = sizeof(renk_veri_t);
    else if (p->tip == TIP_DURUM)       uzunluk = sizeof(durum_veri_t);
    else if (p->tip == TIP_LEADER_HB)   uzunluk = sizeof(leader_hb_veri_t);
    else if (p->tip == TIP_ELECTION)    uzunluk = sizeof(election_veri_t);
    else if (p->tip == TIP_VERSION)     uzunluk = sizeof(version_veri_t);
    else if (p->tip == TIP_SWARM_STATE) uzunluk = sizeof(swarm_state_veri_t);
    else if (p->tip == TIP_QR_DATA)     uzunluk = sizeof(qr_veri_t);
    // TIP_ORIGIN follower'a iletilmeli: bridge _isle_origin -> _son_origin dolar,
    // komsu POSE -> NED donusumu buna bagli. Iletilmezse follower'da _son_origin
    // None kalir ve tum komsu konumlari pos=0/valid=false olur.
    else if (p->tip == TIP_ORIGIN)      uzunluk = sizeof(origin_veri_t);
    else return; // bilinmeyen tip, gonderme
    uart_gonder(p->tip, kaynak_id, payload, uzunluk);
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("[ESP32] Basliyor...");
    _drone_tablo_dogrula();  // MAC benzersizligini boot'ta dogrula

    // baud 460800 (spec + ekip karari). Bu Serial1 hatti RTK'nin yani sira
    // joystick/pose/vb tum Pi<->mesh protokolunu de tasiyor (_rtk_uart_gonder
    // ayni porta yazar), Pi tarafi da ayni baud'a gecmeli. setRxBufferSize()
    // begin()'den once cagrilmali; sonra cagrilirsa sessizce etkisiz kalir.
#if RPI_SERIAL0_MODU
    // RPi hatti Serial0'a alindi (GPIO3/GPIO1 = kart uzerindeki RX/TX pinleri).
    // Baud 460800'e cikariliyor: RPi tarafi bu hizda konusuyor.
    // end()+begin() sirasi RX BASE'deki olcumden geliyor: setRxBufferSize()
    // begin()'den ONCE cagrilirsa UART0 boot dongusune giriyor.
    Serial.end();
    Serial.setRxBufferSize(2048);
    Serial.begin(460800);
    delay(50);
    Serial.println("[UART] RPi hatti Serial0'da (GPIO3/GPIO1, 460800)");
#else
    Serial1.setRxBufferSize(2048);  // spec 3.2: UART RX buffer >= 2048B
    Serial1.begin(460800, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);
    Serial.println("[UART] RPi (Serial1, 460800) bagli");
#endif

    WiFi.mode(WIFI_STA);

    // Ucus oncesi opsiyonel manuel kanal taramasi.
    // Otomatik degisim yok, sadece operator isterse rapor alir.
#if !RPI_SERIAL0_MODU
    // Serial0 modunda atlanir: o hat artik RPi'nin binary kanali, 'T' beklemek
    // RPi'nin ilk cerceve baytlarini yutar ve rastgele bir bayt taramayi
    // tetikler.
    Serial.println("[BOOT] Kanal taramasi icin 3 sn icinde 'T' gonderin (opsiyonel)...");
    uint32_t _tara_bekleme_baslangic = millis();
    while (millis() - _tara_bekleme_baslangic < 3000) {
        if (Serial.available() && Serial.read() == 'T') {
            mesh_kanal_tara();
            break;
        }
    }
#endif

    esp_wifi_set_channel(MESH_KANAL, WIFI_SECOND_CHAN_NONE);
    mesh_init(mesh_veri_al);
    son_paket_ms = millis();

    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);

    Serial.println("[ESP32] Hazir");
}

#define MESH_GONDERIM_MIN_MS 50



void loop() {
    // rtk_loop() rtk_mesh_loop() icinden cagriliyor (RTK buyuk zarfini
    // _rtk_recv_buffer'dan bosaltip cozer).
    //
    // RPI_SERIAL ACIKCA gecilmeli, varsayilana (Serial1) birakilmamali.
    // Eskiden burada argumansiz cagriliyordu ve yorum "TX DRONE'da Serial1 Pi
    // hattidir" diyordu — bu RPI_SERIAL0_MODU eklenmeden ONCE dogruydu. O mod
    // RPi hattini Serial0'a tasidi ama bu cagri yerinde kaldi: drone RTCM'i
    // havadan aliyor, birlestiriyor ve RPi'ye BAGLI OLMAYAN Serial1'e yaziyordu.
    // Semptom sinsi: baz "gonderdim" der, drone ESP'si "aldim" der, RPi'de
    // rtk sayaci 0 kalir ve sorun RF'de aranir. (Uctan uca testte yakalandi.)
    rtk_mesh_loop(RPI_SERIAL);
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

    // rtk_mesh_loop ile AYNI hata buradaydi: varsayilan Serial1'e yaziyordu,
    // oysa RPI_SERIAL0_MODU'da RPi hatti Serial0. Sonucu daha agir: failsafe
    // bildirimi (0xFA -> RTL/LAND) RPi'ye hic ulasmiyordu, yani mesh kopunca
    // esp32_bridge::_isle_failsafe ATESLENMIYORDU. RX BASE bunu dogru yapiyor
    // (failsafe_kontrol(YKI_SERIAL)), TX DRONE atlanmisti.
    failsafe_kontrol(RPI_SERIAL);

#ifndef RTK_ISTATISTIK_LOGLAMA_KAPALI
    // Periyodik RTK istatistik logu (spec 3.3). build_flags'a
    // -D RTK_ISTATISTIK_LOGLAMA_KAPALI eklenerek kapatilabilir.
    static uint32_t son_rtk_istatistik_ms = 0;
    if (millis() - son_rtk_istatistik_ms >= 10000) {
        son_rtk_istatistik_ms = millis();
        rtk_istatistik_yazdir();
        // QR dahil hiz limitinde dusen cerceveler. TIP_QR_DATA burada gorunuyorsa
        // sartname s.13 cezasi riske girmis demektir (bkz mesh_config.h notu).
        mesh_tip_dusen_yazdir();
    }
#endif

    {
        // Ortak, desync-guvenli COBS cerceve ayristirici (bkz uart_frame_parser.h).
        // Cerceve durumu whitelist'ten ayri: idx her 0x00'da kosulsuz sifirlanir
        // (uart_frame_parser_push), whitelist sadece donen cerceveye uygulanir ve
        // durumu etkileyemez. Aksi halde whitelist-disi bir tipte "break" okuma
        // dongusunu kirip index'i bozar ve komut hatti desync olurdu.
        static uart_frame_parser_t pi_parser;
        uint8_t okunan = 0;

        while (RPI_SERIAL.available() && okunan < 32) {
            uint8_t b = (uint8_t)RPI_SERIAL.read();
            okunan++;

            uint8_t tip_byte, id_byte_unused;
            const uint8_t* cerceve_payload;
            uint16_t cerceve_payload_uzunluk;
            if (!uart_frame_parser_push(&pi_parser, b, &tip_byte, &id_byte_unused,
                                        &cerceve_payload, &cerceve_payload_uzunluk))
                continue;

            // mesh_gonder() her zaman 18 byte okuyor (memcpy(tam_veri+6, veri,
            // 18)), o yuzden buffer 18B. Cap 18: POSE 18B'dir (vz dahil, REV B)
            // ve tam kopyalanmali; 16'da kalirsa 16-17. bayt (vz) sifirlanip
            // mesh'e sifir gitmesine yol acardi. 16B tipler (DURUM vb.) icin
            // fazladan baytlar zaten sifir dolgu.
            uint8_t payload[18]     = {0};
            uint8_t payload_uzunluk = (uint8_t)min((int)cerceve_payload_uzunluk, 18);
            memcpy(payload, cerceve_payload, payload_uzunluk);

            // Whitelist: sadece Pi'den gelmesi beklenen tipler. TIP_POSE dahil:
            // bridge _on_own_status kendi konumunu 10Hz TIP_POSE olarak yolluyor;
            // bu whitelist'te olmazsa POSE mesh'e hic girmez ve komsu konum
            // paylasimi (carpisma onleme) korlesir. TIP_LEADER_HB ve TIP_ELECTION
            // dahil (aksi halde her drone kendi consensus mesajini gonderemez ->
            // split-brain).
            const bool izinli = (tip_byte == TIP_KOMUT  ||
                                  tip_byte == TIP_POSE   ||
                                  tip_byte == TIP_GOREV  ||
                                  tip_byte == TIP_RENK   ||
                                  tip_byte == TIP_ORIGIN ||
                                  tip_byte == TIP_DURUM  ||
                                  tip_byte == TIP_SWARM_STATE ||
                                  tip_byte == TIP_QR_DATA ||
                                  tip_byte == TIP_LEADER_HB ||
                                  tip_byte == TIP_ELECTION);
            // Hiz limiti tip basina (bkz mesh_config.h::mesh_tip_gecebilir). Tek
            // paylasilan damga olsaydi TIP_QR_DATA, 50ms icinde cikan bir POSE/
            // LEADER_HB yuzunden sessizce dusebilirdi; QR tek atimlik ve cezali.
            if (izinli && mesh_tip_gecebilir(tip_byte, millis(), MESH_GONDERIM_MIN_MS))
                mesh_gonder(payload, tip_byte);
        }
    }
}
