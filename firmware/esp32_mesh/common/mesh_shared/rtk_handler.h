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
//   crc      -> zarf havada bozuldu; parazit/menzil gostergesi
//   gecersiz -> bozuk/uyumsuz cerceve duzeni; zarf formati degistiyse tum
//               node'lar ayni gun flaslanmali
//   timeout  -> fragment havada kayboldu, RF menzil/parazit (anten/mesafe)
// Tek sayacta toplaninca bu ucu ayirt edilemiyordu, ayrildi.
static uint32_t rtk_alinan          = 0;   // kabul edilen FRAGMENT sayisi
static uint32_t rtk_uart_gonderilen = 0;   // Pi'ye iletilen TAM RTCM mesaji
static uint32_t rtk_kayip_crc       = 0;   // CRC16 tutmadi (parazit/bozulma)
static uint32_t rtk_kayip_gecersiz  = 0;
static uint32_t rtk_kayip_timeout   = 0;

// Durum sayaclari - gonderici (baz) tarafi.
// rtk_mesh_gonder() hem RX BASE'te hem paylasilan kodda yasadigi icin sayac
// burada. RX BASE'in YKİ-girisi sayaclari rtk_sender.h'de.
static uint32_t rtk_tx_frag         = 0;   // mesh'e yayilan fragment
static uint32_t rtk_tx_zarf_hatasi  = 0;   // 3 denemeden sonra da esp_now_send hatasi

static inline uint32_t rtk_kayip_toplam(void) {
    return rtk_kayip_crc + rtk_kayip_gecersiz + rtk_kayip_timeout;
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
//
// Tel formati (toplam <= 250, ESP-NOW siniri):
//   [sihir 2][tip=TIP_RTK 1][msg_id 4][idx 1][toplam 1][uzunluk 1][veri N][crc16 2]
//    \____ mesh_paket_t ile ayni onsoz ____/
//
// Onsozun ilk 3 bayti kucuk paketle ayni: ISR offset 0'da sihiri, offset 2'de
// tipi okuyup hangi ring buffer'a yazacagina tam parse etmeden karar verebiliyor.
//
// hedef: nullptr -> broadcast. RTCM icin cagiran taraf unicast hedefi vermeli;
// parca kaybi TUM mesaji oldurdugu icin 802.11 ACK+retry burada cok kiymetli
// (bkz mesh_config.h::_mesh_gonder UNICAST vs BROADCAST notu).
static inline void rtk_mesh_gonder(const rtk_mesh_frag_t* frag,
                                    const uint8_t* hedef = nullptr) {
    uint8_t ham[RTK_ENV_MAKS_TOPLAM];
    uint16_t sihir = MESH_SIHIR;
    memcpy(ham, &sihir, 2);
    ham[2] = TIP_RTK;
    // frag basligi: msg_id(4) + idx(1) + toplam(1) + uzunluk(1)
    memcpy(ham + RTK_ENV_ONSOZ_BOYUTU, frag, RTK_FRAG_HEADER_BOYUTU);
    memcpy(ham + RTK_ENV_ONSOZ_BOYUTU + RTK_FRAG_HEADER_BOYUTU,
           frag->payload, frag->frag_uzunluk);

    uint16_t crc_oncesi = RTK_ENV_ONSOZ_BOYUTU + RTK_FRAG_HEADER_BOYUTU + frag->frag_uzunluk;
    uint16_t crc = cobs_crc16(ham, crc_oncesi);
    memcpy(ham + crc_oncesi, &crc, RTK_CRC_BOYUTU);
    uint16_t toplam_uzunluk = crc_oncesi + RTK_CRC_BOYUTU;

    if (hedef == nullptr) hedef = BROADCAST_MAC;
    if (!esp_now_is_peer_exist(hedef)) {
        esp_now_peer_info_t bp = {};
        memcpy(bp.peer_addr, hedef, 6);
        bp.channel = MESH_KANAL;
        bp.encrypt = false;
        esp_now_add_peer(&bp);
    }

    uint32_t bekleme = (uint32_t)esp_random() % (CSMA_GECIKME_MAKS_MS + 1);
    if (bekleme > 0) vTaskDelay(pdMS_TO_TICKS(bekleme));

    esp_err_t ret = ESP_FAIL;
    for (int d = 0; d < 3; d++) {
        ret = esp_now_send(hedef, ham, toplam_uzunluk);
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

            // En kisa gecerli zarf: onsoz + frag basligi + en az 1 bayt veri + crc
            if (uzunluk < RTK_ENV_ONSOZ_BOYUTU + RTK_FRAG_HEADER_BOYUTU + 1 + RTK_CRC_BOYUTU) {
                rtk_kayip_gecersiz++;
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            // CRC: sihir kapisi ISR'da gecildi, burada butunluk dogrulaniyor.
            uint16_t crc_oncesi = uzunluk - RTK_CRC_BOYUTU;
            uint16_t crc_gelen; memcpy(&crc_gelen, veri + crc_oncesi, RTK_CRC_BOYUTU);
            if (crc_gelen != cobs_crc16(veri, crc_oncesi)) {
                rtk_kayip_crc++;
                _rtk_recv_oku = (_rtk_recv_oku + 1) % RTK_RECV_BUFFER_SIZE;
                continue;
            }

            rtk_mesh_frag_handle(veri + RTK_ENV_ONSOZ_BOYUTU,
                                  (uint16_t)(crc_oncesi - RTK_ENV_ONSOZ_BOYUTU),
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
                  "(crc=%lu gecersiz=%lu timeout=%lu)\n",
                  (unsigned long)rtk_alinan,
                  (unsigned long)rtk_uart_gonderilen,
                  (unsigned long)rtk_kayip_toplam(),
                  (unsigned long)rtk_kayip_crc,
                  (unsigned long)rtk_kayip_gecersiz,
                  (unsigned long)rtk_kayip_timeout);
}
