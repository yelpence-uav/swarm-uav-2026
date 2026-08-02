#pragma once
#include <Arduino.h>

// ============================================================================
// PAYLASILAN HEADER'LARDAKI CALISMA-ZAMANI LOGLARI ICIN TEK KAPI
// ----------------------------------------------------------------------------
// Sorun: mesh_config.h / rtk_handler.h / fail_safe.h, Serial'e KOSULSUZ yaziyor.
// Bazi derlemelerde `Serial` bir debug konsolu DEGIL, binary veri hattidir:
//
//   TX DRONE  + RPI_SERIAL0_MODU=1  ->  Serial = RPi'nin COBS hatti (460800)
//   RX BASE   + TEK_USB_MODU=1      ->  Serial = YKİ'nin COBS hatti (460800)
//
// O derlemelerde her printf duz metni binary akisin ortasina sokar. Alici
// parser bir sonraki 0x00'a kadar biriktirdigi icin metin mevcut cerceveye
// yapisir ve o cerceve CRC'de duser. Saha gunlugunde olculdu: "her komut bir
// telemetri cercevesi oldururdu" (20 Temmuz, §7 ve esp32_bridge crc_fail=3).
//
// RTCM ile bu teorik olmaktan cikiyor: rtk_handler.h fragment BASINA log
// basiyor ve RTCM ~7 fragment/sn uretecek, yani hat surekli kirlenir. RTCM'in
// kendisi de ayni hattan gectigi icin sonuc "RTCM geliyor ama bozuk" olur ve
// sebep RF'de aranir.
//
// Bu makrolar SADECE calisma-zamani loglarini kapatir. BOOT mesajlari bilerek
// dokunulmadan Serial'de kalir (mesh_init MAC/hazir satirlari, drone_tablo
// dogrulamasi): bir kez, mesh trafigi baslamadan once basiliyorlar ve MAC
// tablosu hatasini gormek kritik. Bu, mevcut tasarimin kararidir.
//
// Bayraklar platformio.ini'den -D ile geliyor, yani derleyici komut satirinda
// tanimli ve TUM ceviri birimlerinde (header'lar dahil) gorunur. main.cpp'deki
// `#ifndef ... #define ... 0` varsayilanlari yalnizca temel env icindir ve
// buradaki kontrolu bozmaz (tanimsiz makro #if icinde 0 sayilir).
// ============================================================================

#if (defined(RPI_SERIAL0_MODU) && RPI_SERIAL0_MODU) || \
    (defined(TEK_USB_MODU)     && TEK_USB_MODU)
#define MESH_LOG_HATTI_VERI 1
#else
#define MESH_LOG_HATTI_VERI 0
#endif

#if MESH_LOG_HATTI_VERI
// Serial = veri hatti. Calisma-zamani loglari SUSTURULUR.
// do{}while(0) sarmali: `if (x) MESH_LOG_PRINTLN(y); else ...` gibi
// kullanimlarda bos ifade sozdizimini bozmasin.
#define MESH_LOG_PRINT(x)      do {} while (0)
#define MESH_LOG_PRINTLN(x)    do {} while (0)
#define MESH_LOG_PRINTF(...)   do {} while (0)
#else
// Serial = ayri debug konsolu. Loglar acik; saha teshisinin ana kaynagi.
#define MESH_LOG_PRINT(x)      Serial.print(x)
#define MESH_LOG_PRINTLN(x)    Serial.println(x)
#define MESH_LOG_PRINTF(...)   Serial.printf(__VA_ARGS__)
#endif
