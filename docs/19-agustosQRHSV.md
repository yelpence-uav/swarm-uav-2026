# 19 Ağustos 2026 — Kamera / Görü (QR + Renk) Test Günlüğü

**Branch:** `feature/kamera-goru-test` (taban `ec04de5` = `feature/yki-gelistirme` = `feature/mesh-suru-entegrasyon` ile aynı commit; güncel `swarm_perception` kodu).
**Amaç (kaptan talimatı):** QR okuma + renkli iniş alanı (kırmızı/mavi) okumayı **bizim paketlerle** (`camera_driver` + `vision_node`) test etmek; uçuş testinden ayrı kişi/ayrı branch.

---

## 1. Özet — ne yaptık
1. **Deneme Pi'sine** (`raspberrypi`, kullanıcı `yelpencedeneme`, o gün 172.20.10.5, IMX477 CSI kamera) erişip kamerayı çalıştırdık.
2. **QR okumayı kanıtladık.**
3. **Kırmızı okumayı kanıtladık.**
4. **Düzeltilecek eksikleri bulduk** (HSV, çerçeveleme, camera_driver/CSI).
5. Canlı test aracı **`scripts/goru_viewer.py`** yazdık (bounding box + web görüntü + log + ses).
6. **Gerçek drone ylp00'a** geçmeye çalıştık → **kamera enumerate olmadı** (fiziksel engel, çözülmedi).

---

## 2. Kanıtlananlar ✅
- **Kamera QR okuyor:** yarışma formatında **QR5** okundu.
- **Bizim `qr_detector` parser'ı doğru çözdü:** `valid=True`, formasyon **OKBAŞI**, spacing **5 m**, pitch **15°**, roll **−5°**, irtifa **28 m**, `next_qr=0` (görev biter).
- **Bizim `landing_zone_detector` kırmızı/mavi buluyor.**
- **Kırmızı kart**, çerçeveyi doldurunca **`KIRMIZI 0.94`** güvenle tespit edildi.

---

## 3. Bulunan eksikler ⚠️
1. **`camera_driver`'ın `cv2.VideoCapture(0)`'ı CSI (IMX477) kamerada AÇILMIYOR** (`opened=False`; `/dev/video0` = unicam ham Bayer). → `FrameGrabber`'a **libcamera/Picamera2** yolu eklenmeli. *(Asıl branch işi.)*
2. **Varsayılan HSV eşikleri gerçek pad'lere uymuyor.** Pad'ler soluk: mavi **mor-lacivert**, kırmızı **pembemsi**. Eşikler fazla "koyu-doygun" (`mavi S≥150`, `kırmızı S/V≥100`) → kaçırıyor.
3. **Çerçeveleme/mesafe kritik.** Pad küçük/uzaksa merkezdeki renkli piksel azalıyor **ve kamera beyaz dengesi (AWB) rengi turuncuya (H~22-29) kaydırıyor** → tespit yok. Uçuşta (25-30 m) pad küçük görünecek → **aynı risk.**
4. **Mavi eşiği fazla gevşek** (kalibrede `S≥45` yaptık) → **beyazı "mavi" sanıyor** (yanlış pozitif).
5. **Glare/parlama** parlak kartta ara sıra sahte mavi üretiyor.
6. **`pyzbar` bu Debian'da paketli değil** (host'ta). `zbar` var, onu kullandık; parse yine bizim kod. *(Gerçek drone'da pyzbar konteynerde mevcut.)*

---

## 4. Ölçülen HSV değerleri (OpenCV: H 0-180, S/V 0-255)
| Kart | H (5/50/95) | S | V | Not |
|------|-------------|---|---|-----|
| Mavi pad | 105 / 116 / 121 | 47-147 | 76-208 | mor-lacivert, soluk |
| Kırmızı pad | ~170-177 (ve 0-12) | 74-208 | 96-171 | pembemsi; iyi çerçevede net kırmızı |

**`goru_viewer` test config'inde kalibre edildi** (henüz `vision_params.yaml`'a YAZILMADI):
```
red_lower_1=[0,60,60]   red_upper_1=[12,255,255]
red_lower_2=[160,60,60] red_upper_2=[180,255,255]
blue_lower=[98,45,40]   blue_upper=[130,255,255]
min_zone_area_px=4000
```
> Mavi `S≥45` beyazı yanlış tetikliyor; gerçek kamerada ölçüp `S_min`'i ~70-80'e çekmek gerekiyor (bekliyor).

---

## 5. Kullanılan yöntem / kütüphaneler
| İş | Kütüphane | Nasıl |
|----|-----------|-------|
| Kamera kare | **OpenCV** `cv2.VideoCapture` | `frame_grabber.py` (CSI'da çalışmıyor) |
| **QR okuma** | **pyzbar → ZBar** (OpenCV DEĞİL) | `decode()` |
| QR parse | **stdlib `json`** (bizim kod) | JSON `{qr,w,mis,team}` → görev alanları |
| **Renk** | **OpenCV** `cv2` (HSV) | `inRange` + `findContours` + `minEnclosingCircle` |
> OpenCV'nin kendi QR okuyucusu (`cv2.QRCodeDetector`) daha zayıf — canlıda QR'ı kaçırdı, zbar okudu.

---

## 6. Kod olarak ne ekledik
- **`scripts/goru_viewer.py`** (YENİ, untracked) — canlı test aracı:
  picam-web yayınından (`:8080/stream`) kare → **bizim `qr_detector`+`landing_zone_detector`** → **bounding box** → `:8090` web görüntü + `tespit.log` + tespit olunca **laptop'a UDP ses sinyali**.
- **Asıl kod DEĞİŞMEDİ:** `qr_detector.py`, `landing_zone_detector.py`, `vision_params.yaml` → git'te 0 değişiklik.
- ⚠️ `goru_viewer` **deneme Pi'sine göre** yazıldı (picam-web + host'ta cv2/zbar varsayar). **ylp00'da olduğu gibi çalışmaz** (picam-web yok, kütüphaneler konteynerde).

---

## 7. ylp00 (gerçek uçuş drone'u) durumu
- `ssh yelpence00@172.20.10.3`, hostname **`ylp00`** (anahtar laptop'tan kuruldu).
- **WiFi çok kararsız** (güç tasarrufu/menzil) — kısa komutlar tutuyor, uzun oturum düşüyor.
- **Flight stack AKTİF:** `drone1` konteyneri up, **MAVROS FCU'ya bağlı** (`/dev/ttyAMA0`). → üzerinde deneysel görü kodu = **kaynak riski.**
- **Host'ta cv2/zbar/pyzbar YOK** (sadece numpy) — hepsi **docker konteynerinde**. **picam-web YOK.**
- **KAMERA ENGELİ (çözülmedi):**
  - CSI kamera: `rpicam-hello` → "No cameras available!", `/dev/video0` yok, dmesg'de imx/unicam izi yok. Config sağlam (`camera_auto_detect=1`) → **fiziksel/kablo.**
  - USB kamera (sonradan takıldı): `lsusb` sadece kök hub'ları gösteriyor, `uvcvideo` yüklü değil, dmesg'de yeni USB cihaz yok → **USB porta enumerate olmadı.**

---

## 8. Şartname notları (görü ile ilgili — V2)
- **Renkli iniş alanları: DAİRE, 100 cm yarıçap (2 m çap)**, kırmızı veya mavi. (madde 450)
- İniş: alan **merkezinden 2.5 m yarıçap içine**; dışına/yanlış renge = **puan yok.** (madde 453)
- Alanlar **UÇUŞ SIRASINDA tespit edilip konumları KAYDEDİLMELİ** — ayrı tarama yasak, konumlar önceden verilmez. → **`zone_map`** (kalıcı bölge haritası) birebir bunun için. (madde 457-460)
- **Görüntü işlemeyle hassas iniş OPSİYONEL.** (madde 455)
- **Alt irtifa 10 m** — altına inmek yasak (iniş hariç). (madde 443)
- **En az 1 İHA** QR okumalı; **çözülen QR YKİ'de en az 1 kez gösterilmeli** yoksa ceza.

---

## 9. Plan / bekleyen işler
1. **[Ertelendi]** QR şimdilik bırakıldı (temel çalışır kanıtlandı).
2. **Daire + renk füzyonu ekle** → "İniş hedefi = renkli DAİRE".
   - Yol A (öneri): renk maskesi + **dairesellik** (`4π·Alan/Çevre²`, morfolojik kapama ile glare deliklerini doldur).
   - Yol B: **`cv2.HoughCircles`** ile daireyi bul → merkez rengine bak. (Kullanıcı bunu tercih ediyor; parametreye hassas, canlıda denenip görülecek.)
   - Her ikisi de "beyazı mavi sanma" yanlış pozitifini temizler.
3. **Mavi eşiğini gerçek kamerada ölç ve düzelt** (`S_min` beyazı eleyecek şekilde ~70-80).
4. **Kalibre HSV'yi asıl config'e** (`config/vision_params.yaml`) yaz — asıl deliverable.
5. **`camera_driver`'a libcamera/Picamera2 yolu** ekle (CSI için). *(USB kamera çalışırsa bu gerekmez — cv2.VideoCapture direkt çalışır.)*
6. **ylp00 kamerasını çalışır hale getir** (fiziksel: sağlam USB kamera enumerate etmeli, ya da CSI kablo/modül).
7. **Gerçek senaryo: 25-30 m irtifada test.** Pad ~73-89 px görünür → `min_area` düşür; önce **yerde pad'i uzağa koyup** doğrula.
8. **Güvenlik:** görü kodu uçuş stack'iyle yarışmasın (`nice`/düşük öncelik). Uçuşta WiFi kopabilir → **canlı izleme/ses yerine drone üzerinde kaydet + yerde incele.**
9. **Branch'i commit'le** (`scripts/goru_viewer.py` + config değişiklikleri).

---

## 9.5 İrtifa (25-30 m) hazırlık analizi — KRİTİK

2 m çaplı pad, 1280 px + ~60° FOV kamerada (fx≈1108):
| İrtifa | Pad çapı | Yarıçap | Alan |
|---|---|---|---|
| 25 m | ~89 px | ~44 px | ~6200 px² |
| 30 m | ~74 px | ~37 px | ~4300 px² |
(1024'e küçültülmüş karede: yarıçap ~25-35 px, alan ~2800-3900 px².)

Tezgah ayarlarının İRTİFADA patlayan üçü (düzeltildi/karara bağlandı):
1. Hough `minRadius w*0.06 (~61px)` pad'i hiç aramıyordu → **`max(10, w*0.015)`** yapıldı,
   `param2 50→35` (küçük dairede daha az kenar oyu); sahte daireleri %75
   renk-baskınlık filtresi eler.
2. `min_zone_area_px 4000` (tezgah) 30 m'de pad'i elerdi → uçuş config'i
   (`vision_params.yaml`) **500'de bırakıldı** — bilinçli karar.
3. Tek-hedef seçimi → **renk BAŞINA en büyük daire** (şartname 457-460 iki
   rengin de konumunu ister).
Ek düzeltme: daire yolunun hue sınırları artık **cfg'den türetiliyor** —
yeniden kalibrasyonda iki yol (renk kutusu + daire) ayrışamaz.

**Çözülmemiş irtifa riski — AWB (beyaz dengesi):** pad karede küçükken (irtifada
karenin ~%0.5'i) beyaz dengesini zemin belirler; ölçüldü: kırmızı H~22-29'a
(turuncu) kayıyor, eşik ≤12 kaçırır. Çare adayları: kamerada **AWB kilidi/sabit
gains** (tercih), ya da açık havada gerçek mesafeden ölçüp kırmızı üst hue'yu
genişletmek. **Saha protokolü:** uçuştan önce pad'i 25-30 m yatay mesafeden
kameraya gösterip `tespit.log`'daki HAM_DAIRE + merkezHSV ile doğrula — irtifayı
uçmadan taklit eder.

## 10. Riskler / dikkat
- **Uçan drone'un bilgisayarında deneysel kod** = MAVROS/px4_bridge ile kaynak yarışı (25-30 m'de tehlikeli). İzole/düşük öncelikli çalıştır.
- **ylp00 WiFi kararsız** → uçuşta canlı web izleme + ses **güvenilmez.**
- **Pad 25-30 m'de küçük** (~73-89 px, lense göre) → tespit zorlaşır; AWB + JPEG + titreşim ekle.
- goru_viewer'ın kare kaynağı ylp00'da **yeniden düşünülmeli** (picam-web yok, libler konteynerde).
