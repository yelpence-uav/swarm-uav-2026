# PLAN — buradan finale

**Son güncelleme:** 17 Ağustos 2026, 14:36

Bu belge **tüm takımın ortak resmi**. Teknik ayrıntı diğer belgelerde;
burada *ne yapıyoruz, neredeyiz, nasıl gideceğiz* var.

Yeni gelen biri bunu 10 dakikada okur ve işe başlayabilir.

---

## 1. Tek cümlede

> Repoda finali yapacak bir sürü yazılımı **zaten var**, ama simülasyon için
> yazıldı ve sahada hiç koşmadı. İşimiz onu **kademeli ve canlı testlerle**
> gerçek uçaklara almak.

---

## 2. Neredeyiz

**Uçuş kanıtı geçildi.** Onu geçiren şey, sürü yazılımı değil; kısa sürede
yazılmış daha basit bir komut yolu:

```
YKİ (bilgisayar) → mesh → uçak: "şu noktaya git"
```

Bu yol çalışıyor, ölçülmüş ve ayarlanmış. Elimizde:

| | Durum |
|---|---|
| ylp00 (drone 1) | ✅ uçuyor |
| ylp01 (drone 2) | ❌ yerde — 2 Ağustos'ta düştü, ESC güç hattı |
| ylp02 (drone 3) | ✅ uçuyor |
| RTK, mesh, kayıt, YKİ arayüzü | ✅ çalışıyor |
| Pilot + kumanda (her uçak için) | ✅ var |
| Kamera | 🟠 yakında takılacak |

---

## 3. Nereye gidiyoruz

**Final görevi.** Şartname iki görev tanımlıyor:

### Görev 1 — Dinamik Sürü Kabiliyeti
Uçaklar rastgele dizilir → tek komutla otonom kalkış → formasyonu koruyarak
QR noktasına git → **kamerayla QR'ı oku** → içindeki görevi yap (formasyon
değişimi / pitch-roll manevrası / irtifa değişimi / **bir uçağın sürüden
ayrılıp renkli alana inmesi, sonra geri katılması**) → sonraki QR'a git →
bitince eve dön ve in.

### Görev 2 — Yarı Otonom Sürü Kontrolü
**Tek kumandayla tüm sürü.** Pilot çubuğu ittiğinde bütün uçaklar formasyonu
bozmadan birlikte hareket eder.

---

## 4. Neden mevcut kod yetmiyor

Şartnamede iki kural var ve ikisi de bugünkü yolumuzu geçersiz kılıyor:

> *"**Dağıtık** sürü algoritması kullanılması gerekmektedir. **Merkezi** sürü
> algoritmaları **eksik puan** olarak değerlendirilecektir."*
>
> *"Hakemler görev sırasında herhangi bir anda **yer kontrol istasyonu
> bağlantısını kesecektir**."*

Bugün kararları YKİ veriyor. Hakem bağlantıyı kestiği anda sürü durur.

**Yani kararlar uçağın kendi içine taşınacak.** YKİ'nin izinli tek rolü
"görevi başlat" demek; gerisi uçakta.

Bu, sürü düğümlerini açmayı **zorunlu** kılıyor — tercih değil.

---

## 5. Plan: 8 aşama

Her aşamada **çalışan bir sistem kalır.** Bir şey bozulursa tek komutla
geri dönülür (`/ws/suru_dugumleri` boşalt + `docker restart`).

| # | Aşama | Ne yapıyor | Risk | Test |
|---|-------|-----------|------|------|
| **0** | Zemin | Öncelik hakemliği, remap'ler, düğüm aç/kapa altyapısı | Yok | Yerde |
| **1** | Bilgi katmanı | Origin, lider seçimi, sürü durumu, görev durumu | ~Yok | Yerde + 1 uçuş |
| **1B** | Kaçınma değişimi | Sürünün kaçınma algoritmasına geçiş | Orta | 2 uçuş |
| **2** | **Formasyon** 🔴 | Formasyonu uçak kendi hesaplar — **merkeziden dağıtığa** | Yüksek | 3 uçuş |
| **3** | Görü | Kamera, QR okuma, renkli alan tespiti | Yok | Çoğu yerde |
| **4** | Görev mantığı | QR'ı oku → görevi yap → sonrakine git | Yüksek | 3 uçuş |
| **5** | Manevra + iniş + üyelik | Pitch/roll, renkli alana hassas iniş, sürüden ayrılma | En yüksek | Kademeli |
| **6** | Görev 2 | Tek kumandayla sürü kontrolü | Orta | 2 uçuş |

**Toplam kaba bütçe: ~15 uçuş.** Aşama 0 ve 3'ün çoğu yerde yapılıyor.

### Sıra neden böyle

- **Önce komut yoluna dokunmayanlar.** Aşama 1'deki dört düğüm sadece
  *durum yayınlıyor*, uçağa komut vermiyor. Açmak neredeyse risksiz.
- **Sonra üreticiyi değiştirenler**, teker teker. Aynı uçuşta iki değişiklik
  yok — bir şey ters giderse hangisi olduğu bilinsin.
- **En riskli en sona.** Hassas iniş yere temas ediyor; ona en son ve
  kademeli gidilir (önce 3 m'den).
- **Görü paralel** — kimseyi beklemiyor, ama Aşama 4'ün ön koşulu.

### Bağımlılık

```
0 ──► 1 ──► 1B ──► 2 ──► 4 ──► 5
                    │
       3 (görü) ────┘        6 (görev 2) ──► 2'den sonra, paralel
```

**3. İHA entegrasyonu engellemiyor.** Aşama 0-4 ve 6 iki uçakla tam yürür.
Yalnız Aşama 5'teki üyelik testi üç uçak ister. Final görevinde şart.

---

## 6. Nasıl test ediyoruz

Simülasyon **kullanmıyoruz** — her şey gerçek uçakta. Onun yerine üç kademe:

| Kademe | Ne | Süre |
|--------|----|----|
| **Y — Yerde** | Düğüm açılıyor mu, mantıklı değer üretiyor mu | ~10 dk |
| **G — Gözlem** | Düğüm uçuş sırasında **arka planda** çalışır, çıkışı hiçbir yere bağlı değil. Sonra kayıttan bakılır | 1 uçuş |
| **K — Komutta** | Gerçekten devreye girer. Önce tek uçak alçak/kısa, sonra iki uçak | 1-2 uçuş |

**Gözlem kademesi simülasyonun yerini tutuyor:** kod gerçek telemetriyle
gerçek kararlar üretir, ama uçağa ulaşmaz. Sonra "ne yapardı" ile "ne oldu"
karşılaştırılır.

**G atlanmaz.** Bu projede en pahalı ders, "kod doğru görünüyor" ile "kod
doğru davranıyor" arasındaki farkın uçakla ödenmesi oldu.

**Her uçuştan önce, iki bedava kontrol:**

```bash
./deploy/yki/param_karsilastir.py     # uçaklar aynı ayarda mı
python3 src/gcs/gorev_kanit_ucus.py --kuru --senaryo saha --dronelar 1,3 --lider 3
```

İkincisi *kuru test*: plan kurulur, çarpışma denetimi yapılır, **hiçbir komut
gönderilmez**. Geçmezse uçulmaz.

---

## 7. Oturum düzeni — bilgi kaybolmasın

Tek bilgisayar, sırayla çalışıyoruz. Sohbet geçmişi sonraki kişiye geçmiyor,
o yüzden **devir teslim yazıyla**.

### Oturuma otururken

1. `docs/DURUM.md` — şu an ne çalışıyor, ne bozuk, uçaklarda hangi ayar açık
2. `docs/GUNLUK.md` — **en üstteki kayıt**: son kişi ne yaptı, nerede bıraktı
3. `docs/YAPILACAKLAR.md` — sıradaki iş

Claude `CLAUDE.md`'yi **kendiliğinden okuyor**, ona bir şey söylemene gerek yok.

### Oturumdan kalkarken

Claude'a **"oturumu kapat"** de. Şunları o yazar:

1. `GUNLUK.md`'ye yeni kayıt (ne yapıldı, ne değişti, yarım kalan, sıradaki adım)
2. `DURUM.md` güncellemesi
3. `YAPILACAKLAR.md` işaretlemesi
4. **Uçakta bir şey değiştiysen** `RPI_ESITLEME.md` — sonraki kişi uçağı öyle bulacak

**Bu adım atlanırsa sistem çöker.** Sonraki kişi neyin ne olduğunu bilemez.

---

## 8. Hangi belge ne için

| Dosya | Ne zaman açılır |
|-------|-----------------|
| **`PLAN.md`** (bu) | Genel resmi görmek için |
| `DURUM.md` | "Şu an ne çalışıyor?" |
| `GUNLUK.md` | "Son kişi ne yaptı?" |
| `YAPILACAKLAR.md` | "Sırada ne var?" — 🔴P0 / 🟠P1 / 🟡P2 / ⚪P3 |
| `KARARLAR.md` | "Bu konuda karar verilmiş miydi?" |
| `RPI_ESITLEME.md` | "Uçaklarda ne var, geri gelen drone'a ne yapmalı?" |
| `SURU_ENTEGRASYON.md` | Aşamaların **teknik** ayrıntısı |
| `NAVIGASYON_KAYMA.md` | Uçak hedefinin arkasında kalıyor mu |
| `cihazlar.md` | SSH, IP, MAC, portlar, QGC |

**Ekran görüntüsü:** `ss/` klasörüne at, Claude'a "ss'e attım" de.

**Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**

---

## 9. Günlük kullanılan komutlar

```bash
# Drone'ları bul ve bağlan (IP ezberleme, her ağda değişiyor)
./deploy/yki/drone_bul.sh                 # menü
./deploy/yki/drone_bul.sh --durum         # disk, konteyner, bayraklar
./deploy/yki/drone_bul.sh ylp00 'komut'

# Uçuş öncesi
./deploy/yki/param_karsilastir.py         # uçaklar aynı ayarda mı
python3 src/gcs/gorev_kanit_ucus.py --kuru --senaryo saha --dronelar 1,3 --lider 3

# Uçuş ayarlarını değiştir (hız, ivme, aralık — TEK KAYNAK)
python3 src/gcs/ucus_ayarlari.py          # çözümle + tutarlılık denetle
python3 src/gcs/ucus_ayarlari.py --px4    # uçaklara yazılacak parametreler

# YKİ
src/gcs/yki_baslat.sh · src/gcs/yki_durdur.sh
```

---

## 10. Şu an sırada ne var

> **Aşama 0 bitti.** Öncelik hakemliği hariç maddelerin tamamı yapıldı:
> remap'ler, `/ws/suru_dugumleri` dosyadan okunuyor, kayıt filtresinde
> `/gozlem/` var, düğümler Pi'de tek tek denendi. Hakemliğin aciliyeti
> düştü — çakışma zaten susturma ile çözülmüş (`YAPILACAKLAR` P0.6).
> **Aşama 1'in yer yarısı da geçti** (ADIM 1, 15 Ağustos, lider seçimi).

### 🔵 SIRADAKİ İŞ: G2 — havada gözlem uçuşu

Aşama 1'in **uçuş yarısı**. Uçaklarda `suru_dugumleri` = `origin consensus
fsm formasyon`, yani ADIM 0/0.5/1/2/3'ün düğümleri **açık ve koşuyor** —
ama hepsi yalnız **yerde** sınandı. Merdivenin (`SURU_ENTEGRASYON.md` §4)
neresindeyiz:

| | | |
|---|---|---|
| G0 | yerde açılıyor mu | ✅ |
| G1 | yerde gözlem | ✅ (`formation_node` yerdeki uçak için `vz=1.51 m/s` üretti — yakalandı) |
| **G2** | **havada gözlem** | ❌ **buradasın** |
| G3 | havada komutta | ❌ ADIM 3 |

Uçuş şöyle: kanıtlanmış komut yolu uçağı uçurur, sürü düğümleri arka planda
gerçek telemetriyle gerçek kararlar üretir, `formation_node`'un çıkışı
`/gozlem/`'e gider ve **uçağa ulaşmaz**. Sonra kayıttan "ne yapardı" ile
"ne oldu" karşılaştırılır.

**Alınacak cevaplar:** havada lider seçimi kararlı mı · `swarm_fsm` sürü
durumunu doğru üretiyor mu · `formation_node` uçulan yola yakın bir şey mi
hesaplıyor · 11 düğüm havadayken RAM/CPU ne.

### Uçmadan önce kapatılacaklar

| | Ne | Maliyet |
|---|----|---------|
| ✅ | ~~**P0.8** `formation_node` `sitl_mode` varsayılanı `True`~~ → **düzeltildi (17 Ağu)**, iki yerden bağlandı ve uçaklara dağıtıldı | — |
| `[ ]` | **P1.6** — `TUZAKLAR.md` §0'daki üç bilinmeyen. İkisi doğrudan uçuş izni kapısı: ylp00 clipping kuralı ve alıcı failsafe'i (kumanda kapalıyken CH5=2000 → **kill**) | clipping ~10 dk yerde |
| `[ ]` | **ADIM 1'in kalanı** — iki uçaklı **tam devir teslim**: birini kill'le, diğerini armlı bırak. 15 Ağustos'ta yalnız tek taraflı gözlendi | ~10 dk, uçuş yok |

### Aynı uçuşa binebilecek ölçüm

**P0.4 navigasyon kayması 🔴 hâlâ ölçülmedi** ve tek ihtiyacı bir uçuş:
en az 40 m düz bacak, 2 ve 4 m/s. Komut yolunda **hiçbir şey
değiştirmiyor**, yani "bir uçuşta tek değişiklik" kuralını çiğnemiyor.
Not: P0.4 *tek uçak* diyor, G2 ise iki uçakla anlamlı (lider seçimi) —
ya aynı seansta iki sorti ya da ayrı günler.

### Sonraki aşamaya not

**ADIM 3'e (formasyon komutta) geçerken:** `KARARLAR.md` **KARAR-02** gereği
operatörden o mesaja `ultracode` yazması istenecek. Ayrıca `px4_bridge
velocity_only:=True` ADIM 3'ün şartı — **G2'nin değil**, şimdi dokunma.

Beklemede: **ylp01 onarımı** (ESC güç hattı) ve **kamera montajı**. İkisi de
entegrasyonu durdurmuyor ama finalde şart.
