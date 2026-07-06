# network_proxy — Sürü Haberleşme Simülasyonu: Tasarım ve QoS Kontratı

**Belge amacı:** Bu düğümün simülasyonda üstlendiği rolü, uyguladığı fiziksel haberleşme kısıtlarını, kanalların Servis Kalitesi (QoS) sözleşmesini ve geliştirme kurallarını tanımlar. Simülasyondaki `network_proxy` ile saha donanımındaki `esp32_bridge` işlevsel ikizdir: aynı topic'leri, aynı taşıma sınıflarını ve aynı QoS ayarlarını kullanmaları hedeflenir.

## 1. Amaç ve Gerekçe
Simülasyonda İHA'lar ROS 2 üzerinden kusursuz haberleşir: paket kaybı %0, gecikme sıfır, mesafe sınırsız. Gerçek sistemde sürü-içi haberleşme ESP32 modülleri üzerinden ESP-NOW mesh ağıyla yapılır ve radyo paraziti, mesafe ve donanım limitlerine tabidir.

`network_proxy`, iki İHA arasındaki mesaj akışına araya girerek (man-in-the-middle) gerçek radyo kısıtlarını (kayıp, gecikme, menzil, 250 bayt sınırı) simülasyona dayatır. Böylece lider seçimi, çarpışma önleme ve görev koordinasyonu gibi dağıtık davranışlar, sahaya çıkmadan gerçekçi koşullarda test edilebilir.

## 2. Temel İlke: Radyo Modeli ile QoS Ayrı Eksenlerdir
Bir kanalın iki bağımsız özelliği vardır ve karıştırılmamalıdır:

- **Taşıma sınıfı (radyo modeli):** Mesajın ağ üzerinde nasıl davrandığı.
  - **Broadcast:** onaysız, tek denemeli, kaybolabilir — periyodik, "en güncel değer kazanır" mesajlar. Proxy bunlara mesafeye bağlı kayıp zarı uygular.
  - **Onaylı (Acked):** güvenilir, tekrar denemeli — tek seferlik, ulaşması zorunlu mesajlar. Proxy bunlara mesafe zarı uygulamaz (efektif kayıp ≈0), yalnızca gecikme.
- **DDS QoS:** ROS 2'nin mesaj teslim politikası (§4).

Kayıp modeli proxy/radyo tarafından uygulanır. **Teslimatı kritik kanallarda** (heartbeat ve acked kanallar) iletilen paketin DDS katmanında ikinci kez kaybolmaması gerekir → `RELIABLE`. **Yüksek-frekanslı "en güncel değer kazanır" kanallarda** (status, control) ise tazelik teslimattan önceliklidir; bir sonraki kare hemen geleceğinden DDS-katmanı kaybı bilinçli kabul edilir → `BEST_EFFORT`. Dolayısıyla "Broadcast olduğu için QoS best-effort olmalı" gibi bir çıkarım yapılmaz; QoS, taşıma sınıfından değil, kanalın işlevinden (§4 tablosu) okunur.

## 3. Simülasyon Modeli (Fiziksel Kısıtlar)

| # | Kural | Açıklama |
|---|---|---|
| 3.1 | **Mesafe: GPS/Haversine** | Her uçuş kontrolcüsü kendi yerel orijinini farklı kurduğundan, dronlar arası mesafe yerel konumdan (`pos_x/y/z`) değil, GPS koordinatlarından (`lat/lon/alt_amsl`) haversine ⊕ irtifa farkıyla hesaplanır. |
| 3.2 | **250 bayt sınırı** | ESP-NOW tek pakette en fazla 250 bayt taşır. Proxy, havadan geçen 8 kanalın hepsinde mesajın gerçek serileştirilmiş boyutunu (`serialize_message`) ölçer; sınırı aşarsa paketi düşürür ve uyarı verir. (Saha ikizi `esp32_bridge` ayrıca veriyi sabit 16 baytlık struct'lara paketler; bu, mesajların yalın tutulmasını daha da zorunlu kılar — bkz. §7.) |
| 3.3 | **Mesafeye bağlı kayıp** | Parçalı-doğrusal eğri: 0–50 m ~%0, 150 m ~%0.5, 300 m ~%2.3, 450 m ~%5.1; 450 m ötesi tam kopma. Yalnızca Broadcast kanallara, en uzak alıcıya göre tek zar olarak uygulanır. |
| 3.4 | **Gecikme ve titreşim (jitter)** | İletilen her paket 5–50 ms rastgele bekletilir. Bekletme, kanal başına sırayı koruyan ve simülasyon saatiyle (`get_clock`) çalışan bir yığın kuyruğundan (heap) akar; `threading.Timer` kullanılmaz. |
| 3.5 | **Yer Kontrol İstasyonu (GCS)** | GCS bir ağ ucudur; konumu parametreden alınır (`gcs_lat/lon/alt`). YKİ→İHA komutu (control) GCS mesafesine göre kayba tabidir. İHA→GCS status trafiği için mesafe yalnızca uyarı olarak loglanır (bkz. §7). |
| 3.6 | **Yapısal sınır** | Tüm alıcılar ortak yayın kanalını dinlediğinden proxy bir düğümü herkese görünmez yapabilir (simetrik kesme), ancak "A duyar, B duymaz" türü asimetrik kopmayı üretemez. Bilinçli kısıttır. |

## 4. Kanal ve QoS Kontratı
Bu tablo tüm kanalların tek referansıdır; ilgili tüm yayıncı ve aboneler bu değerleri kullanmalıdır. Değerler mevcut koddan alınmıştır. Altı ortak kanalın (status, heartbeat, control, events, election, origin) QoS'u saha ikizi `esp32_bridge` ile **birebir aynıdır**; `state` ve `qr_data`'nın esp32'de henüz karşılığı yoktur (bkz. §7.1).

| Kanal (internal → public) | Mesaj Tipi | Taşıma | reliability · durability · depth |
|---|---|---|---|
| …/drone{id}/status | AgentStatus | Broadcast | BEST_EFFORT · VOLATILE · 10 |
| …/leader/heartbeat | LeaderHeartbeat | Broadcast | RELIABLE · VOLATILE · 5 |
| …/state | SwarmState | Broadcast | RELIABLE · VOLATILE · 10 |
| …/control/command | SwarmControlCommand | Broadcast | BEST_EFFORT · VOLATILE · 10 |
| …/events/system | SystemEvent | Onaylı | RELIABLE · VOLATILE · 10 |
| …/perception/qr_data | QRMissionData | Onaylı | RELIABLE · VOLATILE · 10 |
| …/election/result | ElectionResult | Onaylı | RELIABLE · TRANSIENT_LOCAL · 10 |
| …/origin | SwarmOrigin | Onaylı | RELIABLE · TRANSIENT_LOCAL · 1 |

**Seçim gerekçeleri:**
- **status BEST_EFFORT:** Yüksek frekanslı, "en güncel değer kazanır" telemetri. RELIABLE burada eski kareyi tekrar iletip head-of-line blocking'e yol açar; ayrıca üreticiler (agent_fsm/vision_node) BEST_EFFORT yayınladığından RELIABLE bir abone DDS'te onlara hiç bağlanamaz.
- **heartbeat RELIABLE, depth 5:** Lider canlılığı 300 ms zaman aşımıyla izlendiğinden proxy'nin ilettiği sinyal DDS'te kaybolmamalıdır (aksi halde yanlış "lider-öldü" kararı). Derinlik 5, saha ikizi `esp32_bridge` ile hizalıdır. VOLATILE olduğu için geç katılana eski sinyal ulaşmaz.
- **control BEST_EFFORT:** Yüksek frekanslı, "en güncel değer kazanır" akış; RELIABLE eski kareyi tekrar iletip gecikme birikmesine yol açar.
- **TRANSIENT_LOCAL (election/origin):** Sonradan katılan İHA'nın güncel lideri ve ortak referans noktasını hemen öğrenmesi için değerler kalıcı (latched) tutulur.

## 5. Geliştirme Kuralları
1. **Ağa gönderilen veri `internal` topic'ine yayınlanır.** Örn. `/swarm/internal/drone1/status`.
2. **Ağdan alınan veri `public` topic'inden dinlenir** (proxy'den geçmiş, gecikmeli/kayıplı sürüm). Örn. `/swarm/public/drone2/status`.
3. **İHA-içi yerel haberleşmeye dokunulmaz.** `/fmu/...` ve dron-içi telemetri topic'leri ağa çıkmaz, proxy'ye girmez. Komşunun mutlak durumu ağdan alınır; göreli konum her alıcının kendi füzyon katmanında hesaplanır.
4. **Mesaj yapıları hafif tutulur.** Telde mutlak durum taşınır; ham/serbest metin alanları (ör. QR `raw_text`) mesh'e çıkarılmaz, ayrıntı ayrı olay mesajlarına yazılır (250 bayt sınırı).

## 6. Kontrol ve Gözlemlenebilirlik (yalnızca simülasyon)
- **Bağlantı kesme (fault-injection):** `/swarm/proxy/unreachable` (std_msgs/String) topic'ine virgülle ayrılmış düğüm adları yazılarak (`"drone1,drone2"`) o düğümlerin gönderdiği trafik çalıştırma-zamanında kesilir; boş string ile geri açılır. Lider seçimi ve yeniden katılma senaryolarının test aracıdır.
- **Belirlenimcilik:** `rng_seed` parametresi (≥0) ile kayıp/jitter dizisi tohumlanabilir; aynı senaryo birebir tekrar oynatılır. Verilmezse (-1) sistem entropisi kullanılır.

## 7. Bilinen Sınırlamalar ve İkiz Parite Boşlukları
Aşağıdakiler mevcut kodda bilinen açık maddelerdir.

1. **state / qr_data ikiz paritesi:** Proxy bu iki kanalı tam mesajıyla taşır; ancak saha ikizi `esp32_bridge` `SwarmState`'i hiç taşımaz ve `QRMissionData`'yı dar bir `SystemEvent`/GOREV temsiline sıkıştırır (16 baytlık sabit paket). İkiz paritesi için firmware paketlerinin genişletilmesi gerekir.
2. **Açılış konumu (3.1):** Bir düğüm ilk konumunu bildirene kadar kod onu `(0,0,0)` (GPS'te ~5500 km uzak) kabul eder; bu, açılışta sahte kayıp/kopma üretebilir. Doğrusu "bildirene kadar hesaba katılmaz" olmalıdır.
3. **GCS asimetrisi (3.5):** `control` GCS mesafesine göre düşürülürken `status→GCS` yalnızca loglanır; ayrıca `gcs_lat/lon` verilmezse tüm `control` komutları %100 düşer. GCS'in ayrı telemetri radyosunda mı yoksa mesh'te mi olduğu netleşmelidir.
4. **Kayıp eğrisi (3.3):** Kopma eşiği 450 m. Şartname 110 m gerektiriyorsa eğri buna göre ayarlanmalıdır.
5. **formation/target yönlendirmesi:** Kontrata göre bu kanal yerel türetilir; ancak `mode_manager` `/internal/formation/target`'a yazar ve tüketiciler `/public`'ten okur. Formasyon slot atamasının merkezi (lider yayınlar) mi yoksa dağıtık (her dron hesaplar) mı olduğu netleşmeli; buna göre ya köprülenmeli ya üretici doğrudan `/public`'e yazmalıdır.
6. **Otomatik test yok:** `network_proxy` için birim/entegrasyon testi bulunmuyor; `rf_model` bağımsız çalıştırılabilir, ancak proxy mantığı için mock-tabanlı bir test harness'ı önerilir.
