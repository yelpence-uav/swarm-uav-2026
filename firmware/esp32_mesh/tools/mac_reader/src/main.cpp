// ESP32 MAC adresi okuyucu — mesh firmware'i icin peer tablosu doldurur.
//
// mesh firmware'inde drone_tablo[] ve RX BASE peer tanimlari tam 6 byte MAC
// karsilastiriyor (sadece son byte'a bakilsaydi iki ESP32'nin son byte'i
// cakisabilirdi). Depodaki degerlerin ilk 5 byte'i sifir placeholder; bu araci
// her karta sirayla yukleyip cikan satiri firmware'e kopyalayin.
//
// ESP-NOW STA arayuzunu kullanir, o yuzden WiFi.mode(WIFI_STA) sonrasi okunan
// MAC dogru olan. Bluetooth/AP MAC'i farklidir, karistirmayin.

#include <Arduino.h>
#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    delay(1000);

    WiFi.mode(WIFI_STA);   // mesh firmware'i ile ayni mod
    delay(100);

    uint8_t mac[6];
    WiFi.macAddress(mac);

    Serial.println();
    Serial.println("=====================================");
    Serial.println("  ESP32 STA MAC (ESP-NOW adresi)");
    Serial.println("=====================================");
    Serial.printf("  Okunabilir : %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.println();
    Serial.println("  firmware'e yapistirilacak satir:");
    Serial.printf("    {{0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X}, <ID>},\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.println();
    Serial.println("  <ID> yerine: drone icin 1..4, baz icin BAZ_MESH_ID(10)");
    Serial.println("=====================================");
}

void loop() {
    // Monitor gec acilirsa satir kacmasin diye 5 sn'de bir tekrarla.
    delay(5000);
    uint8_t mac[6];
    WiFi.macAddress(mac);
    Serial.printf("MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}
