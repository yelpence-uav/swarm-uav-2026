#pragma once
#include <Arduino.h>
#include <string.h>
#include "mesh_config.h"   // TIP_RTK, BAZ_ID, BROADCAST_MAC, MESH_KANAL, GCM/AAD/replay yardimcilari
#include "uart_cobs.h"     // ortak cobs_cerceve_olustur (CRC TIP+BAZ_ID dahil)
#include "rtk_pure.h"      // sabitler + saf fragmantasyon/reassembly mantigi

// Sabitler.
// RTK_FRAG_PAYLOAD_MAKS, RTK_MAX_FRAGS, RTK_REASSEMBLY_BUF_SIZE,
// RTK_FRAG_TIMEOUT_MS, rtk_mesh_frag_t artik rtk_pure.h'de. Byte butcesi
// hesabinin dokumu rtk_pure.h basinda.
#define RTK_HAM_BUF_SIZE   (1 + 1 + RTK_REASSEMBLY_BUF_SIZE + 2)
#define RTK_COBS_BUF_SIZE  (RTK_HAM_BUF_SIZE + (RTK_HAM_BUF_SIZE / 254) + 2)

// Durum sayaclari - alici (İHA) tarafi.
// Kayip nedenleri ayri tutuluyor; her biri farkli bir mudahale gerektiriyor:
//   gcm      -> anahtar yanlis/eksik, provision uyumsuz (KEY WRITER'a bak)
//   replay   -> eski session; cogu zaman saldiri degil, o peer'in NVS'i
//               silinmistir (bkz mesh_config.h::_session_id_uret NVS erase tuzagi)
//   gecersiz -> bozuk/uyumsuz cerceve; zarf duzeni degistiyse tum node'lar
//               ayni gun flaslanmali
//   timeout  -> fragment havada kayboldu, RF menzil/parazit (anten/mesafe)
// Tek sayacta toplaninca bu dordu ayirt edilemiyordu, ayrildi.
static uint32_t rtk_alinan          = 0;   // kabul edilen FRAGMENT sayisi
static uint32_t rtk_uart_gonderilen = 0;   // Pi'ye iletilen TAM RTCM mesaji
static uint32_t rtk_kayip_gcm       = 0;
static uint32_t rtk_kayip_replay    = 0;
static uint32_t rtk_kayip_gecersiz  = 0;
static uint32_t rtk_kayip_timeout   = 0;

// Durum sayaclari - gonderici (baz) tarafi.
// rtk_mesh_gonder() hem RX BASE'te hem paylasilan kodda yasadigi icin sayac
// burada. RX BASE'in YKİ-girisi sayaclari rtk_sender.h'de.
static uint32_t rtk_tx_frag         = 0;   // mesh'e yayilan fragment
static uint32_t rtk_tx_zarf_hatasi  = 0;   // 3 denemeden sonra da esp_now_send hatasi

static inline uint32_t rtk_kayip_toplam(void) {
    return rtk_kayip_gcm + rtk_kayip_replay + rtk_kayip_gecersiz + rtk_kayip_timeout;
}

// Reassembly durumu (rtk_pure.h'deki saf tip).
static rtk_asm_durum_t _rtk_asm = {};

// Ileri bildirim: rtk_loop() dosyanin sonunda tanimli, rtk_mesh_loop() ondan
// once cagiriyor.
static inline void rtk_loop(void);

// Hedef Pi portu cagiran tarafindan belirlenir.
// Varsayilan Serial1; Pi hatti baska portta olan firmware onu acikca gecer.
// TX DRONE'da Serial1 Pi hattidir, ama RX BASE'te Serial1 YKİ/RTCM giris
// hattina ayrilmistir (Pi protokolu Serial2'de yurur). Port hardcode edilirse
// RX BASE reassemble ettigi RTCM'i YKİ'nin yayin yaptigi hatta geri yazar.
// Tek-baz topolojisinde bu yol ulasilamaz (_benim_mac_mi kendi yayinini eler)
// ama savunma topolojiye emanet edilmez.

// Ortak cobs_cerceve_olustur() kullanir; CRC16 artik TIP_RTK/BAZ_ID prefiksini
// de kapsiyor (eskiden sadece RTCM verisi uzerinden hesaplaniyordu). pi_bridge
// bunu bilmeli: RTK cercevesinin CRC16'si TIP(0x0C)+BAZ_ID(99) dahil.
static inline void _rtk_uart_gonder(const uint8_t* veri, uint16_t uzunluk,
                                     HardwareSerial& uart) {
    static uint8_t ham[RTK_HAM_BUF_SIZE];
    static uint8_t cobs_buf[RTK_COBS_BUF_SIZE];
    uint16_t cobs_len = cobs_cerceve_olustur(TIP_RTK, BAZ_ID, veri, uzunluk, ham, cobs_buf);
    uart.write(cobs_buf, cobs_len);
    rtk_uart_gonderilen++;
    Serial.printf("[RTK] RPiye gonderildi: %u byte (toplam: %lu)\n",
                  uzunluk, rtk_uart_gonderilen);
}

// Fragment reassembly - buyuk zarftan cozulmus icerikle cagrilir.
// Durum-makinesi mantigi rtk_pure.h::rtk_asm_fragment_isle() icinde. Burasi
// sadece rtk_mesh_frag_t basligini ayristirir, pure fonksiyonu cagirir, sonucu
// loglar ve tamamlaninca _rtk_uart_gonder ile Pi'ye yollar. uzunluk sabit
// degil, sadece gercekten gonderilen kadar byte geliyor.
static inline void rtk_mesh_frag_handle(const uint8_t* ham_veri, uint16_t uzunluk,
                                         HardwareSerial& uart) {
    if (uzunluk < RTK_FRAG_HEADER_BOYUTU) {
        Serial.printf("[RTK] HATA: fragment cok kisa (%u byte, beklenen en az %u)\n",
                      uzunluk, (unsigned)RTK_FRAG_HEADER_BOYUTU);
        rtk_kayip_gecersiz++;
        return;
    }

    const rtk_mesh_frag_t* f = (const rtk_mesh_frag_t*)ham_veri;

    if (uzunluk != (uint16_t)(RTK_FRAG_HEADER_BOYUTU + f->frag_uzunluk)) {
        Serial.printf("[RTK] HATA: uzunluk tutarsiz (beklenen %u, gelen %u)\n",
                      (unsigned)(RTK_FRAG_HEADER_BOYUTU + f->frag_uzunluk), uzunluk);
        rtk_kayip_gecersiz++;
        return;
    }

    uint16_t toplam_uzunluk = 0;
    rtk_asm_sonuc_t sonuc = rtk_asm_fragment_isle(
        &_rtk_asm, f->paket_id, f->frag_index, f->frag_total, f->frag_uzunluk,
        f->payload, millis(), &toplam_uzunluk);

    switch (sonuc) {
        case RTK_ASM_REDDEDILDI:
            Serial.printf("[RTK] HATA: gecersiz frag index=%u total=%u len=%u\n",
                          f->frag_index, f->frag_total, f->frag_uzunluk);
            rtk_kayip_gecersiz++;
            return;
        case RTK_ASM_DUPLIKAT:
            Serial.printf("[RTK] Duplikat frag %u, atlaniyor\n", f->frag_index);
            return;
        case RTK_ASM_TASTI:
            Serial.printf("[RTK] HATA: reassembly buffer tasti (paket_id=%lu)\n",
                          (unsigned long)f->paket_id);
            rtk_kayip_gecersiz++;
            return;
        case RTK_ASM_DEVAM:
            rtk_alinan++;
            Serial.printf("[RTK] Mesh frag %u/%u alindi (paket_id=%lu, %uB)\n",
                          f->frag_index + 1, f->frag_total, (unsigned long)f->paket_id,
                          f->frag_uzunluk);
            return;
        case RTK_ASM_TAMAMLANDI:
            rtk_alinan++;
            Serial.printf("[RTK] Mesh frag %u/%u alindi (paket_id=%lu, %uB)\n",
                          f->frag_index + 1, f->frag_total, (unsigned long)f->paket_id,
                          f->frag_uzunluk);
            Serial.printf("[RTK] Birlestirildi: %u byte\n", toplam_uzunluk);
            _rtk_uart_gonder(_rtk_asm.buf, toplam_uzunluk, uart);
            rtk_asm_sifirla(&_rtk_asm);
            return;
    }
}

// Buyuk RTK zarfi - gonderim.
// mesh_paket_t'nin degisken boyutlu buyuk kardesi. Onsoz duzeni (kaynak_mac..iv)
// mesh_paket_t ile ayni oldugu icin ISR'daki tip-offset kontrolu ortak calisir.
// sifreli_veri ve tag gercek uzunluga gore ard arda yaziliyor, esp_now_send'e
// de gercek toplam uzunluk veriliyor. Anti-replay altyapisini (_paket_sayaci/
// _session_id) ve AAD semasini (_mesh_aad_olustur) mesh_paket_t ile paylasir.
// TIP_RTK icin CSMA + 3 denemelik yerel retry burada tekrarlaniyor, cunku
// _mesh_gonder() TIP_RTK'yi islemiyor.
static inline void rtk_mesh_gonder(const rtk_mesh_frag_t* frag) {
    // --- Plaintext: anti_replay(6) + frag basligi(7) + gercek payload ---
    uint8_t plaintext[RTK_ANTI_REPLAY_BOYUTU + RTK_FRAG_HEADER_BOYUTU + RTK_FRAG_PAYLOAD_MAKS];
    uint32_t mesh_paket_id = ++_paket_sayaci;
    anti_replay_t ar = { _session_id, mesh_paket_id };
    memcpy(plaintext, &ar, RTK_ANTI_REPLAY_BOYUTU);
    memcpy(plaintext + RTK_ANTI_REPLAY_BOYUTU, frag, RTK_FRAG_HEADER_BOYUTU);
    memcpy(plaintext + RTK_ANTI_REPLAY_BOYUTU + RTK_FRAG_HEADER_BOYUTU,
           frag->payload, frag->frag_uzunluk);
    uint16_t plaintext_uzunluk = RTK_ANTI_REPLAY_BOYUTU + RTK_FRAG_HEADER_BOYUTU + frag->frag_uzunluk;

    // --- Zarf onsozu (mesh_paket_t ile ayni alan duzeni) ---
    uint8_t ham[RTK_ENV_MAKS_TOPLAM];
    memcpy(ham, _benim_mac, 6);
    memcpy(ham + 6, BROADCAST_MAC, 6);
    memcpy(ham + 12, &mesh_paket_id, 4);
    ham[16] = 0;            // atlama_sayisi
    ham[17] = TIP_RTK;      // tip: ISR bu offset'e bakiyor
    iv_uret_rastgele(ham + 18);   // iv[12] -> offset 18..29

    uint8_t aad[13];
    _mesh_aad_olustur(TIP_RTK, ham /*kaynak_mac*/, ham + 6 /*hedef_mac*/, aad);

    uint8_t tag[RTK_ENV_TAG_BOYUTU];
    aes_sifrele_gcm(plaintext, plaintext_uzunluk, ham + 30, ham + 18, tag, aad, sizeof(aad));
    memcpy(ham + 30 + plaintext_uzunluk, tag, RTK_ENV_TAG_BOYUTU);

    uint16_t toplam_uzunluk = 30 + plaintext_uzunluk + RTK_ENV_TAG_BOYUTU;

    if (!esp_now_is_peer_exist(BROADCAST_MAC)) {
        esp_now_peer_info_t bp = {};
        memcpy(bp.peer_addr, BROADCAST_MAC, 6);
        bp.channel = MESH_KANAL;
        bp.encrypt = false;
        esp_now_add_peer(&bp);
    }

    uint32_t bekleme = (uint32_t)esp_random() % (CSMA_GECIKME_MAKS_MS + 1);
    if (bekleme > 0) vTaskDelay(pdMS_TO_TICKS(bekleme));

    esp_err_t ret = ESP_FAIL;
    for (int d = 0; d < 3; d++) {
        ret = esp_now_send(BROADCAST_MAC, ham, toplam_uzunluk);
        if (ret == ESP_OK) break;
        if (d < 2) vTaskDelay(pdMS_TO_TICKS(2 + (uint32_t)esp_random() % 6));
    }
    if (ret != ESP_OK) {
        rtk_tx_zarf_hatasi++;
        Serial.printf("[RTK-TX] Zarf gonderimi basarisiz (frag %u/%u)\n",
                      frag->frag_index + 1, frag->frag_total);
        return;
    }
    rtk_tx_frag++;
}

// Buyuk RTK zarfi - alim.
// ISR'in ayirdigi _rtk_recv_buffer'i bosaltir. mesh_loop()'tan bagimsiz, ayri
// cagrilir; diger TIP'lerin _recv_isle() yolunu etkilemez.
// uart: birlestirilen RTCM mesajinin yazilacagi Pi portu (yukaridaki port
// notuna bak). Varsayilan Serial1 (TX DRONE Pi hatti), RX BASE Serial2 gecer.
static inline void rtk_mesh_loop(HardwareSerial& uart = Serial1) {
    if (_rtk_recv_flag) {
        _rtk_recv_flag = false;
        while (_rtk_recv_oku != _rtk_recv_yaz) {
            const uint8_t* veri    = _rtk_recv_buffer[_rtk_recv_oku].veri;
            uint16_t       uzunluk = _rtk_recv_buffer[_rtk_recv_oku].uzunluk;

            if (uzunluk < RTK_ENV_SABIT_TOPLAM + RTK_ANTI_REPLAY_BOYUTU + RTK_FRAG_HEADER_BOYUTU) {
                rtk_kayip_gecersiz++;
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            const uint8_t* kaynak_mac = veri;
            const uint8_t* hedef_mac  = veri + 6;
            const uint8_t* iv         = veri + 18;
            const uint8_t* sifreli    = veri + 30;
            uint16_t sifreli_uzunluk  = uzunluk - RTK_ENV_SABIT_TOPLAM;
            const uint8_t* tag        = veri + 30 + sifreli_uzunluk;

            if (_benim_mac_mi(kaynak_mac)) {
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            uint8_t aad[13];
            _mesh_aad_olustur(TIP_RTK, kaynak_mac, hedef_mac, aad);

            static uint8_t acik[RTK_ENV_MAKS_SIFRELI];
            if (!aes_coz_gcm(sifreli, sifreli_uzunluk, acik, iv, tag, aad, sizeof(aad))) {
                Serial.println("[RTK] GCM hatasi - zarf reddedildi (anahtar/provision uyumsuz olabilir)");
                rtk_kayip_gcm++;
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            node_durum_t* node = _node_bul_veya_ekle(kaynak_mac);
            if (!node || !_replay_kontrol(node, (const anti_replay_t*)acik)) {
                Serial.println("[RTK] Replay/eski zarf reddedildi (peer NVS'i silinmis olabilir "
                               "- bkz NVS ERASE TUZAGI)");
                rtk_kayip_replay++;
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            rtk_mesh_frag_handle(acik + RTK_ANTI_REPLAY_BOYUTU,
                                  (uint16_t)(sifreli_uzunluk - RTK_ANTI_REPLAY_BOYUTU),
                                  uart);

            _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
        }
    }
    rtk_loop();
}

// Timeout kontrol, rtk_mesh_loop()'tan cagrilir.
static inline void rtk_loop(void) {
    if (rtk_asm_timeout_kontrol(&_rtk_asm, millis())) {
        Serial.println("[RTK] Assembly timeout — sifirlandi (fragment havada kayboldu = RF)");
        rtk_kayip_timeout++;
    }
}

// Alici (İHA) istatistigi. Kayip kovalarinin anlami icin sayac tanimlarinin
// basindaki nota bak; "kayip" tek sayi olarak bakildiginda yaniltir.
static inline void rtk_istatistik_yazdir(void) {
    Serial.printf("[RTK] alinan=%lu uart_gonderilen=%lu kayip=%lu "
                  "(gcm=%lu replay=%lu gecersiz=%lu timeout=%lu)\n",
                  (unsigned long)rtk_alinan,
                  (unsigned long)rtk_uart_gonderilen,
                  (unsigned long)rtk_kayip_toplam(),
                  (unsigned long)rtk_kayip_gcm,
                  (unsigned long)rtk_kayip_replay,
                  (unsigned long)rtk_kayip_gecersiz,
                  (unsigned long)rtk_kayip_timeout);
}
