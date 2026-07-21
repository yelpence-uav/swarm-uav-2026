#include "esp_task_wdt.h"
#include <Arduino.h>
#include <WiFi.h>
#include <string.h>   // memcmp icin
#include "esp_wifi.h"
#include "mesh_config.h"
#include "fail_safe.h"
#include "rtk_handler.h"
#include "rtk_sender.h"
#include "uart_cobs.h"   // ortak CRC16/COBS/cerceve kur-coz (RX BASE + TX DRONE)
#include "uart_frame_parser.h"  // desync-guvenli ortak COBS cerceve ayristirici

// TEK_USB_MODU: YKİ tarafinda USB-TTL adaptor yokken kullanilir. Telemetri/komut
// hatti Serial2 (GPIO25/26) yerine ESP32'nin kendi USB portuna (Serial0) tasinir,
// tek kablo yeter. Varsayilan 0 -> Busra'nin iki-UART tasarimi aynen korunur.
//
// Bedeli: USB hatti binary COBS tasidigi icin loop icindeki debug printf'leri
// akisa karisir. Bu yuzden tek-USB modunda susturuluyorlar (DBG_*). Boot
// mesajlari kaliyor: mesh trafigi baslamadan once bir kez basiliyorlar ve MAC
// tablosu hatasini gormek kritik.
//
// RTCM (Serial1) bu modda beslenmez -> RTK yok. Ayni portu iki surec acamaz
// (yki_rtcm_reader + esp32_bridge), birlesik surec yazilana kadar Asama 2.
#ifndef TEK_USB_MODU
#define TEK_USB_MODU 0
#endif

#if TEK_USB_MODU
  #define YKI_SERIAL       Serial
  #define DBG_PRINTLN(x)   do {} while (0)
  #define DBG_PRINTF(...)  do {} while (0)
  // Periyodik RTK/mesh istatistik printf'leri de binary akisa karisirdi.
  #ifndef RTK_ISTATISTIK_LOGLAMA_KAPALI
  #define RTK_ISTATISTIK_LOGLAMA_KAPALI 1
  #endif
#else
  #define YKI_SERIAL       Serial2
  #define DBG_PRINTLN(x)   Serial.println(x)
  #define DBG_PRINTF(...)  Serial.printf(__VA_ARGS__)
#endif

// RTCM_GIRISI_VAR: Serial1'in (GPIO16/17) adanmis RTCM giris hatti olarak
// acilip acilmayacagi. TEK_USB_MODU'dan AYRI tutuluyor, cunku bunlar bagimsiz
// iki soru: "YKİ verisi hangi porttan geliyor?" ve "ayri bir RTCM hatti var mi?"
// Eskiden ikisi tek bayraga bagliydi ve TEK_USB_MODU=0 secmek Serial1'i de
// acmak zorunda birakiyordu.
//
// Varsayilan 0. RTCM kaynagi fiziksel olarak bagli degilken Serial1 acilirsa
// GPIO16 bosta (floating) kalir, gurultu cerceve sanilir ve rtk_serial_isle()
// her hatali cerceve icin Serial'e "[RTK-RX] HATA" basar. Tek-USB modunda bu
// YKİ hattini %100 dolduruyordu (olculdu: 11.6 kB/s -> 4.3 B/s); TTL modunda
// ise debug konsolunu kullanilamaz hale getirir.
//
// Hedef mimaride bu bayrak 0 KALIR: RTCM, YKİ veri hattindan TIP_RTK cercevesi
// olarak gelecek (yki_rtcm_reader -> COBS -> Serial2), adanmis UART'a gerek yok.
#ifndef RTCM_GIRISI_VAR
#define RTCM_GIRISI_VAR 0
#endif

// YKİ veri hattinin baud'u — TEK KAYNAK. Iki modda da ayni deger kullanilir,
// yoksa mod degistirince Python tarafindaki -p baud:= parametresini de
// degistirmeyi unutmak cok kolay olurdu (semptomu: hat sessiz, hata yok).
//
// 460800 secildi cunku:
//   - Drone tarafi (RPI_SERIAL0_MODU) zaten 460800'de konusuyor,
//   - yki_rtcm_reader varsayilani --esp-baud 460800,
//   - RTCM (~1 kB/s) telemetriyle ayni hatti paylasacak; 115200'de toplam
//     yuk ~%16 iken 460800'de ~%4 kaliyor ve RTCM burst'u komut baytlarini
//     bekletmiyor.
#define YKI_BAUD  460800

// FreeRTOS queue.
struct uart_mesaj_t {
    uint8_t tip;
    uint8_t iha_id;
    uint8_t payload[18];
    uint8_t uzunluk;
};
static QueueHandle_t uart_kuyruk = nullptr;

// UART paket gonder.
static void uart_gonder(uint8_t tip, uint8_t iha_id,
                        const uint8_t* payload, uint8_t payload_uzunluk) {
    if (payload_uzunluk > 18) return;

    uint8_t ham[22];
    uint8_t cobs_buf[27];
    uint16_t cobs_uzunluk = cobs_cerceve_olustur(tip, iha_id, payload, payload_uzunluk, ham, cobs_buf);
    YKI_SERIAL.write(cobs_buf, cobs_uzunluk);  // tek-USB modunda Serial0
}

// Sistem mesaji.
static void sistem_mesaj(const char* mesaj) {
    uint8_t buf[16] = {0};
    strncpy((char*)buf, mesaj, 15);
    uart_gonder(0xFF, 0x00, buf, 16);
}

volatile unsigned long   son_paket_ms         = 0;
bool                     failsafe_tetiklendi  = false;
uint8_t                  _failsafe_asama      = 0;
volatile uint8_t         ardisik_kayip_sayisi = 0;
uint8_t                  failsafe_active_mode = APM_MODE_RTL;

// Drone ID eslestirme.
// Tam 6 byte MAC karsilastiriliyor; sadece son byte'a bakilsaydi iki ESP32'nin
// son byte'i ayni oldugunda (Espressif atamasinda mumkun) iki drone ayni ID'ye
// eslenip sessizce kimlik cakismasi olurdu.
// Saha donanimi: elde tek drone ESP32 var, MAC'i tools/mac_reader ile okundu.
// Baz'in kendi MAC'i buraya girmez (kendi yayinini _benim_mac_mi eler); baz
// kimligi TX DRONE tarafindaki tabloda BAZ_MESH_ID olarak duruyor.
static const struct { uint8_t mac[6]; uint8_t id; } drone_tablo[] = {
    {{0xB0, 0xCB, 0xD8, 0xC8, 0xA8, 0x30}, 1},   // drone ESP32
    // Drone 2-4 henuz temin edilmedi. Placeholder MAC ile acik birakmak
    // yanlis eslesme riski dogurur: mac_to_id() sahte bir MAC'e ID verirse
    // olmayan bir drone mesh'te "aktif" gorunur ve komsu sayisini sisirir.
    // Donanim gelince MAC'i tools/mac_reader ile okuyup satiri ac.
    // {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 2},
    // {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 3},
    // {{0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, 4},
};
static constexpr uint8_t DRONE_SAYISI = sizeof(drone_tablo) / sizeof(drone_tablo[0]);

uint8_t mac_to_id(const uint8_t* mac) {
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
        // 0 = "bilinmeyen MAC" sentinel'i, BAZ_ID (99) = RTK UART sentinel'i.
        // Ikisi de mesh kimligi olamaz (bkz mesh_config.h).
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
            // ID benzersizligi: iki satira ayni ID verilirse telemetri yanlis
            // drone'a atfedilir.
            if (drone_tablo[i].id == drone_tablo[j].id) {
                Serial.printf("[BOOT] HATA: drone_tablo[%u] ve [%u] AYNI ID (%u)!\n",
                              i, j, drone_tablo[i].id);
                hata = true;
            }
        }
    }
    if (hata) {
        // ID cakismasi iki drone'un telemetrisinin YKİ'ye ayni iha_id ile
        // karismasi demek (yer istasyonu yanlis drone'u gosterir).
        // Fail-closed: duzeltilmeden calismaya devam etmez.
        Serial.println("[BOOT] drone_tablo duzeltilmeden ucusa cikilmamali!");
        Serial.println("[BOOT] KRITIK: ID cakismasi - baslatma durduruldu.");
        Serial.flush();
        while (true) delay(1000);
    }
}

// Hiz limiti zaman damgalari mesh_config.h'de, tip basina (_son_tip_gonderim_ms[]).
#define JOYSTICK_MIN_ARALIK_MS 200
#define MESH_GONDERIM_MIN_MS 50



// Mesh callback.
// kaynak_mac ESP-NOW alim callback'inden gelir; pakette tasinmiyor.
// Sihir, CRC16 ve duplikat kapilari _recv_isle()'de gecildi. Burada kalan tek
// kapi KIMLIK: drone_tablo'da olmayan MAC reddedilir.
void mesh_veri_al(const uint8_t* kaynak_mac, const mesh_paket_t* p) {
    uint8_t iha_id = mac_to_id(kaynak_mac);
    if (iha_id == 0) {
        DBG_PRINTLN("[MESH] Bilinmeyen MAC, paket reddedildi");
        return;
    }
    node_durum_t* node = _node_bul_veya_ekle(kaynak_mac);
    if (!node) return;

    // Canlilik kimlik dogrulandiktan SONRA tazelenir: tanimadigimiz bir MAC
    // mesh_komsu_sayisi'ni sisirmemeli. TX DRONE::mesh_veri_al ile ayni sira.
    node->son_heartbeat_ms = millis();
    node->aktif            = true;

    portENTER_CRITICAL(&_recv_mux);
    ardisik_kayip_sayisi = 0;
    son_paket_ms = millis();
    portEXIT_CRITICAL(&_recv_mux);

    failsafe_reset();

    // HEARTBEAT failsafe zamanlayicisini tazelemek icin buraya kadar geldi;
    // veri tasimadigi icin YKİ'ye iletilmez.
    if (p->tip == TIP_HEARTBEAT) return;
    if (p->tip == TIP_RTK)       return;   // kendi buyuk zarfiyla ayri gelir

    uart_mesaj_t msg = {};
    msg.tip    = p->tip;
    msg.iha_id = iha_id;

    if      (p->tip == TIP_POSE)      msg.uzunluk = sizeof(pose_veri_t);
    else if (p->tip == TIP_GOREV)     msg.uzunluk = sizeof(gorev_veri_t);
    else if (p->tip == TIP_RENK)      msg.uzunluk = sizeof(renk_veri_t);
    else if (p->tip == TIP_DURUM)     msg.uzunluk = sizeof(durum_veri_t);
    else if (p->tip == TIP_LEADER_HB)  msg.uzunluk = sizeof(leader_hb_veri_t);
    else if (p->tip == TIP_ELECTION)   msg.uzunluk = sizeof(election_veri_t);
    else if (p->tip == TIP_VERSION)    msg.uzunluk = sizeof(version_veri_t);
    else if (p->tip == TIP_SWARM_STATE) msg.uzunluk = sizeof(swarm_state_veri_t);
    else if (p->tip == TIP_QR_DATA)    msg.uzunluk = sizeof(qr_veri_t);
    else return; 

    memcpy(msg.payload, p->veri, msg.uzunluk);

    if (uart_kuyruk) {
        if (xQueueSend(uart_kuyruk, &msg, pdMS_TO_TICKS(5)) != pdPASS) { // 5ms timeout
            static volatile uint32_t _kuyruk_dolu_sayisi = 0;
            _kuyruk_dolu_sayisi++;
        }
    }
}

void setup() {
    Serial.begin(115200);
#if TEK_USB_MODU
    // UART0'in RX tamponu buyutuluyor: tek-USB modunda YKİ komut/telemetri
    // hatti da bu porttan geciyor ve varsayilan 256B @115200 yalnizca ~22ms
    // veri tutar (Serial2'deki O3 gerekcesinin aynisi).
    //
    // begin()'den ONCE cagirmak UART0'da ise yaramiyor - kart boot dongusune
    // giriyor (olcumle bulundu: orijinal iki-UART yolu ayni kartta sorunsuz
    // acilirken tek-USB derlemesi 'entry 0x400805e4' sonrasi surekli
    // SW_RESET veriyordu). UART0 Arduino core tarafindan erken kuruluyor;
    // begin()'den sonra end()+yeniden begin() ile tampon guvenle degisiyor.
    Serial.end();
    Serial.setRxBufferSize(2048);
    Serial.begin(YKI_BAUD);   // tek-USB modunda USB hatti = YKİ veri hatti
#endif
    delay(1000);
    _drone_tablo_dogrula();  // MAC benzersizligini boot'ta dogrula

    // RTCM girisi icin Serial1. Baslatilmazsa Serial1.available() hep 0 kalir
    // ve RTK base RTCM okuyamaz.
    // Dikkat: asagidaki pin numaralari placeholder'dir. Ucus/saha oncesi gercek
    // RTCM kaynaginizin (YKİ/PC) hangi GPIO'lara bagli oldugunu dogrulayin.
    #define RTK_RX_PIN 16   // TODO: gercek YKİ->ESP RX pinini dogrula
    #define RTK_TX_PIN 17   // TODO: gercek YKİ->ESP TX pinini dogrula (genelde kullanilmaz)
    // baud 460800 (spec + ekip karari). setRxBufferSize() begin()'den once
    // cagrilmali; sonra cagrilirsa sessizce etkisiz kalir (varsayilan 256B ring
    // buffer kullanilmaya devam eder).
#if RTCM_GIRISI_VAR
    Serial1.setRxBufferSize(2048);  // spec 3.2: UART RX buffer >= 2048B
    Serial1.begin(460800, SERIAL_8N1, RTK_RX_PIN, RTK_TX_PIN);
    Serial.println("[UART] RTCM girisi (Serial1, 460800) acildi - PIN DOGRULAMASI GEREKLI");
#else
    // Bilerek acilmiyor: bkz RTCM_GIRISI_VAR notu (floating GPIO16 -> sahte
    // cerceve -> rtk_serial_isle() hata spam'i -> hat doygunlugu).
    Serial.println("[UART] RTCM girisi kapali (Serial1 acilmadi)");
#endif

    // RTCM durum LED'i (saha teshisi icin yanip soner).
    // TODO: pin placeholder, gercek donanimda dogrulanmali (cogu ESP32 kartinda
    // GPIO2 yerlesik LED'e bagli).
    pinMode(RTK_LED_PIN, OUTPUT);

    // YKİ komut/telemetri COBS binary protokolu USB Serial yerine Serial2'de,
    // boylece debug printf'leriyle carpismaz. (Yerde RPi YOK: Serial2'nin karsisi
    // YKİ laptobudur, "Pi" degil. Isim drone tarafindan miras kalmisti.)
    // Dikkat: asagidaki pin numaralari placeholder'dir, YKİ UART kablolamasina
    // gore dogrulayin.
    #define YKI_RX_PIN 25    // TODO: gercek YKİ TX -> ESP32 RX pinini dogrula
    #define YKI_TX_PIN 26    // TODO: gercek YKİ RX -> ESP32 TX pinini dogrula
    // ORTA-3/O3: YKİ komut hatti da >=2048B RX buffer'a cikarildi. Varsayilan
    // 256B ring buffer @115200 ~22ms veri tutar; RTCM burst'u loop()'u tek turda
    // ~60ms+ bloke edebildiginden (rtk_mesh_gonder fragment basina CSMA+retry)
    // varsayilan buffer tasip YKİ komut baytlari sessizce dusebiliyordu. Serial1
    // (RTCM) zaten 2048'e cikarilmisti; bu hat asimetrik kalmisti.
    // setRxBufferSize() begin()'den ONCE cagrilmali (sonra etkisiz).
#if TEK_USB_MODU
    // Serial2 hic acilmiyor: YKİ hatti USB'ye (Serial0) tasindi, GPIO25/26 bosta.
    Serial.printf("[UART] YKİ komut/telemetri TEK-USB modunda (Serial0, %d)\n", YKI_BAUD);
#else
    Serial2.setRxBufferSize(2048);
    Serial2.begin(YKI_BAUD, SERIAL_8N1, YKI_RX_PIN, YKI_TX_PIN);
    Serial.printf("[UART] YKİ komut/telemetri (Serial2, %d) baslatildi\n", YKI_BAUD);
#endif


    uart_kuyruk = xQueueCreate(20, sizeof(uart_mesaj_t));
    sistem_mesaj("RX BASE HAZIR");


    WiFi.mode(WIFI_STA);

    // Ucus oncesi opsiyonel manuel kanal taramasi.
    // Otomatik degisim yok, sadece operator isterse rapor alir.
#if TEK_USB_MODU
    // Tek-USB modunda atlaniyor: ayni port binary COBS tasiyor, 'T' beklemek
    // YKİ'nin ilk komut baytlarini yutar ve rastgele bir bayt taramayi tetikler.
#else
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
    // Watchdog: 8 saniye, loop donerse ESP32 reset atar
    esp_task_wdt_init(8, true);
    esp_task_wdt_add(NULL);
    son_paket_ms = millis();
    sistem_mesaj("MESH HAZIR");
}




void loop() {
    // rtk_mesh_loop() cagrilmali: _esp_now_recv_cb ISR'i RX BASE'te de TIP_RTK
    // zarflarini _rtk_recv_buffer'a yaziyor ve bu buffer'i bosaltan tek yer bu.
    // Tek-baz topolojisinde RX BASE kendi yayinini geri almaz (_benim_mac_mi
    // eler) ama RF ortaminda/testte gelecek herhangi bir TIP_RTK paketi bosalma
    // olmadan bu 8 girislik ring buffer'i tikayabilir. rtk_mesh_loop() zaten
    // rtk_loop()'u kendi icinde cagirir.
    //
    // Serial2 acikca verilir: RX BASE'te Serial1 YKİ/RTCM giris hattidir, YKİ
    // komut/telemetri protokolu Serial2'de yurur. Varsayilan (Serial1) birakilirsa
    // reassemble edilen RTCM mesaji YKİ'nin yayin yaptigi hatta geri yazilirdi.
    rtk_mesh_loop(YKI_SERIAL);
#if RTCM_GIRISI_VAR
    rtk_serial_isle(Serial1);
#endif
    // RTCM_GIRISI_VAR=0 iken Serial1 hic acilmadi; cagirmak acilmamis UART'tan
    // okumak olurdu.
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


    // RX BASE'in YKİ hatti Serial2'dir (Serial1 RTCM'e ayrildi), o yuzden acikca
    // Serial2 verilir; aksi halde bildirim varsayilan Serial1'e (RTCM giris
    // hattina) gider ve YKİ'ye hic ulasmaz. Kademeli (UYARI/RTL/LAND) bildirim
    // TX DRONE ile ayni formatta calisir.
    failsafe_kontrol(YKI_SERIAL);

#ifndef RTK_ISTATISTIK_LOGLAMA_KAPALI
    // Gonderici tarafi RTK istatistigi (TX DRONE'daki alici karsiligiyla ayni
    // periyot/flag). Baz'in kendi yayin sagligini gorunur kilar: bu satir
    // olmadan "RTK yok" sikayetinde baz'in hic yayin yapmadigi ile havada
    // kaybolmasi ayirt edilemiyordu (bkz rtk_sender.h okuma kilavuzu).
    static uint32_t son_rtk_tx_istatistik_ms = 0;
    if (millis() - son_rtk_tx_istatistik_ms >= 10000) {
        son_rtk_tx_istatistik_ms = millis();
        rtk_tx_istatistik_yazdir();
        mesh_tip_dusen_yazdir();   // hiz limitinde dusen cerceveler (tip bazinda)
    }
#endif

    uart_mesaj_t gelen;
    while (xQueueReceive(uart_kuyruk, &gelen, 0) == pdPASS) {
        uart_gonder(gelen.tip, gelen.iha_id, gelen.payload, gelen.uzunluk);
    }

    // Ortak, desync-guvenli COBS cerceve ayristirici (bkz uart_frame_parser.h).
    // Whitelist/dispatch mantigi sadece tamamlanmis cerceveye uygulanir; hicbir
    // dali ayristirici durumunu (idx) etkilemez.
    static uart_frame_parser_t pi_parser;
    uint8_t okunan = 0;
    while (YKI_SERIAL.available() && okunan < 32) {  // tek-USB modunda Serial0
        uint8_t b = YKI_SERIAL.read();
        okunan++;
        uint8_t tip_byte, id_byte_unused;
        const uint8_t* cerceve_payload;
        uint16_t cerceve_payload_uzunluk;
        if (!uart_frame_parser_push(&pi_parser, b, &tip_byte, &id_byte_unused,
                                    &cerceve_payload, &cerceve_payload_uzunluk))
            continue;

        uint32_t simdi = millis();
        // mesh_gonder() her zaman 18 byte okur (memcpy(tam_veri+6, veri, 18)),
        // o yuzden buffer 18B. 16B olsaydi 2 byte stack over-read (UB) olurdu.
        // Gercek payload struct'lari 16B, payload_uzunluk siniri 16'da kaliyor,
        // fazladan 2 byte zaten sifirlanmis dolgu.
        uint8_t veri[18] = {0};
        uint8_t payload_uzunluk = (uint8_t)min((int)cerceve_payload_uzunluk, 16);
        memcpy(veri, cerceve_payload, payload_uzunluk);

        // Acik whitelist + reddet: TIP_KOMUT kendi (daha siki) joystick hiz
        // sinirini korur, bilinen diger tipler ait olduklari tiple gonderilir,
        // taninmayan tip atilir. Bilinmeyen bir tip TIP_KOMUT'a donusturulup
        // joystick sanilmaz. Hiz limiti tip basina (mesh_tip_gecebilir);
        // TIP_KOMUT kendi 200ms araligini korur.
        // Bu blokta Serial'e YAZMA: tek-USB modunda Serial, YKİ'nin binary COBS
        // hattidir. Duz metin akisin ortasina girer, bir sonraki 0x00'a kadar
        // mevcut cerceveye yapisir ve o telemetri paketi CRC'de duser (olculdu:
        // her komut bir telemetri cercevesi oldururdu). Teshis gerekirse
        // DBG_PRINTF kullan - tek-USB'de bilerek susturulmustur.
        if (tip_byte == TIP_KOMUT) {
            if (mesh_tip_gecebilir(TIP_KOMUT, simdi, JOYSTICK_MIN_ARALIK_MS))
                mesh_gonder(veri, TIP_KOMUT);
        } else if (tip_byte == TIP_RENK  || tip_byte == TIP_DURUM ||
                   tip_byte == TIP_SWARM_STATE || tip_byte == TIP_QR_DATA ||
                   tip_byte == TIP_ORIGIN || tip_byte == TIP_GOREV) {
            if (mesh_tip_gecebilir(tip_byte, simdi, MESH_GONDERIM_MIN_MS))
                mesh_gonder(veri, tip_byte);
        }
        // else: taninmayan tip sessizce atilir. TIP_LEADER_HB/TIP_ELECTION
        // bilerek dahil edilmedi: baz, drone consensus'una taraf degil.
    }

    static uint32_t son_durum = 0;
    if (millis() - son_durum >= 5000) {
        son_durum = millis();
        uint8_t aktif = 0;
        portENTER_CRITICAL(&_recv_mux);
        for (uint8_t i = 0; i < MESH_MAX_NODES; i++)
            if (_bilinen_nodlar[i].aktif) aktif++;
        portEXIT_CRITICAL(&_recv_mux);
        uint8_t buf[16] = {0};
        buf[0] = aktif;
        buf[1] = MESH_MAX_NODES;
        uart_gonder(0xFD, 0x00, buf, 16);
    }
}
