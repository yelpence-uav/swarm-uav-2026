# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

# İçindekiler Tablosu
* [Dizin Yapısı](#dizin-yapısı)
* [Kurulum](#kurulum)
* [İletişim](#iletişim)

# Dizin Yapısı

Projemiz, modülerlik ve sürdürülebilirlik prensipleriyle aşağıdaki dizin mimarisi üzerine kurgulanmıştır:

```text
yelpence-2026-swarm
├── .github/        # CI/CD süreçlerini ve kod kalitesini denetleyen otomatik iş akışlarını içerir.
├── docker/         # Geliştirme ortamının tüm platformlarda izole ve tutarlı çalışmasını sağlayan yapılandırmaları barındırır.
├── scripts/        # Görev senaryoları üretme ve sistemi hızlıca ayağa kaldırma gibi operasyonel yardımcı betikleri içerir.
├── sim/            # İHA'ların fiziksel modellerini ve yarışma görevlerinin icra edileceği simülasyon dünyalarını barındırır.
└── src/            # Sürü zekası, haberleşme protokolleri ve otonom kontrol algoritmalarımızın bulunduğu ana kaynak kod dizinidir.
```


