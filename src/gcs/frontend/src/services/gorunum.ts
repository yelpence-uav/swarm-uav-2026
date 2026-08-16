/**
 * Arayüz görünürlük anahtarları.
 *
 * Burası "özelliği sil" yerine "özelliği gizle" için var. Sahada bir gösterge
 * anlamsızlaştığında kodu sökmek yerine tek satırdan kapatmak isteniyor —
 * donanım geri takıldığında geri açmak da tek satır olsun.
 */

/**
 * Pil göstergesi (drone kartındaki BatteryGauge + harita popup satırı).
 *
 * 2 AĞUSTOS'TA KAPATILDI. Uçaklar regülatörden besleniyor, PX4'te
 * `BAT1_SOURCE` disabled — yani telemetride pil alanı GERÇEK BİR ÖLÇÜM
 * DEĞİL, sıfır/çöp. Ekranda "%0" göstermek, hiç göstermemekten kötü:
 *
 *   1) Şartname YKİ ekranının videoda görünmesini şart koşuyor ve videoya
 *      müdahale yasak. Ekranda duran "%0 pil" hakemde arızalı sistem
 *      izlenimi bırakır.
 *   2) Operatör alışkanlıkla oraya bakar ve yanlış sayıya güvenir.
 *
 * NOT: uyarı motoru tarafında `low_battery`/`critical_battery` ZATEN ayrıca
 * susturulmuş durumda (backend/config.yaml -> alerts.susturulan). Bu anahtar
 * yalnız GÖSTERGEYİ kapatır; ikisi ayrı yerler, ikisi de kapalı olmalı.
 *
 * Pil tekrar bağlanınca: burayı true yap, config.yaml'daki susturma
 * listesinden de batarya kodlarını çıkar.
 */
export const PIL_GOSTER = false;
