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
 * 🟢 31 AĞUSTOS 2026'DA GERİ AÇILDI — kapatma gerekçesi ORTADAN KALKTI.
 *
 * ylp00'a INA226 pil ölçüm modülü takıldı (I²C 0x40, kimlik yazmaçlarıyla
 * doğrulandı: üretici 0x5449, die 0x2260). Uçtan uca ölçüldü:
 *
 *     INA226        15.926 V  %75,7
 *     AgentStatus   15.934 V  %75,9     (mesh'e giden)
 *     YKİ           15.90  V  %75       (ekranda)
 *
 * Yani gösterilen sayı artık GERÇEK BİR ÖLÇÜM. 2 Ağustos'taki iki
 * gerekçe de düşüyor: hakem gerçek pil durumu görüyor ve operatörün
 * güvendiği sayı doğru.
 *
 * 🔴 AMA HENÜZ YALNIZ ylp00'DA MODÜL VAR. Modülü olmayan uçakta
 * px4_bridge hâlâ sabit %100 / 12,6 V yazıyor (gerekçesi orada, "PIL
 * OLCUMU YOK" uyarısıyla birlikte). Yani ylp01/ylp02'de görünen değer
 * ÖLÇÜM DEĞİL. Modüller takılana kadar ekranda buna göre bakılmalı.
 *
 * Uyarı motoru AYRI: `backend/config.yaml -> alerts.susturulan` içindeki
 * batarya kodları HÂLÂ SUSTURULMUŞ. Bilerek — iki uçak sahte %100
 * gösterirken düşük-pil alarmı açmak gürültü üretir. Üç uçakta da modül
 * olunca o liste de temizlenmeli.
 */
export const PIL_GOSTER = true;
