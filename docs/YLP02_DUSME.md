# ylp02 DÜŞME RAPORU — 5 Eylül 2026, 17:21

**Son güncelleme:** 5 Eylül 2026, 18:34 — kök neden: **motor besleme hattında ani güç kesintisi.** Pixhawk canlıydı, motorlar akım çekmeyi bıraktı. Kanıt laptopta.

> Bu dosya tek bir olayı anlatıyor ve **uçak tekrar uçmadan önce okunmalı.**
> Fiziksel kontrol listesi §6'da. Ölçüm yöntemi §8'de — aynı analiz başka bir
> düşmede tekrar edilebilsin diye adım adım yazıldı.

---

## 1. Özet

ylp02 (drone3), Görev 1 denemesinde **13 metrede asılı dururken itkisini
kaybetti ve serbest düşüşle yere çarptı.** Çarpma hızı ~15 m/s.

**Kök neden: motorlara giden güç kesildi.** Pixhawk'ın kendisi güç kaybetmedi
— düşüş boyunca irtifa ölçmeye ve mod değiştirmeye devam etti. Kesinti
**pil → güç dağıtım kartı → ESC** hattında.

**Yazılımın payı yok:** havadaki uçağa disarm gönderilmedi (`armed` düşüş
boyunca `True`), PX4 hiçbir failsafe ilan etmedi, setpoint akışı son ana kadar
sürdü.

**Katkıda bulunan kronik kusur:** m3 ve m4 uçuş boyunca PWM tavanına
(1900) dayanıyordu — itki payı zaten sıfırdı.

---

## 2. Zaman çizgisi (yerel saat)

| Saat | Olay | Kaynak |
|---|---|---|
| 17:19:10 | `Armed by external command` | ylp02 PX4 statustext |
| 17:19:13 | `Takeoff detected`, hedef 15 m | ylp02 PX4 statustext |
| 17:19:32 | KALKIŞ TAMAM, 14.8 m → IN_SWARM | mesh AgentStatus |
| 17:20:32 | mission_fsm: NAVIGATE_TO_QR → RETURN_HOME | ylp01/ylp00 logu |
| 17:20:53.98 | **akım tepesi -24.55 A, gerilim dibi 14.43 V** | ylp02 `mavros/battery` |
| 17:20:55.50 | son `mavros/state`: OFFBOARD, armed, **connected=True** | ylp02 bag |
| 17:20:56.12 | **bag'deki BÜTÜN konular kesiliyor** (yazma önbelleği) | ylp02 bag |
| 17:20:58.39 | 13.00 m, vz +0.01 — `healthy` **True → False**, RET_HOME → FAILSAFE | mesh |
| 17:20:58.59 | **düşüş başlıyor** (vz -0.82) | mesh |
| **17:20:58.90** | **gerilim 14.80 → 15.70 V sıçrıyor** = YÜK KALKTI | mesh |
| 17:20:58.90 | PX4 modu → LAND | mesh |
| 17:20:59.93 | 5.40 m, vz -11.27, mod → POSCTL | mesh |
| 17:21:00.23 | **son mesaj: 1.60 m, vz -13.47 m/s** | mesh |
| ~17:21:00.4 | çarpma, ~15 m/s | türetildi |

⚠️ **17:20:56 ile 17:21:00 arası yalnızca MESH'te var.** ylp02'nin kendi
rosbag'i çarpmada önbelleğini boşaltamadı; son 4 saniye o dosyada YOK.
Veriyi ylp00 ve ylp01'in `/swarm/public/drone3/status` kayıtlarından çıkardık
(§8). İkisi birbirini ±0.01 s doğruluyor.

---

## 3. Kanıt: motorlar güç kaybetti

### 3.1 Serbest düşüş

```
13.00 → 12.70 → 12.40 → 12.00 → 11.50 → 10.90 → 10.30
 → 9.40 → 8.60 → 7.60 → 6.60 → 5.40 → 4.30 → 3.00 → 1.60 m
en hızlı: 13.47 m/s
```

Serbest düşüşte 10 m **1.43 saniye** sürer ve **14 m/s**'ye ulaşır. Ölçülen
13.47 m/s. PX4 o sırada **LAND** modundaydı ve komutlu iniş 1-1.5 m/s'dir —
uçak komut edilenin **on katı** hızla düşmüş. Motorlar itki üretmiyordu.

### 3.2 🔴 Gerilim yükselmesi — belirleyici kanıt

| Saat | Gerilim | % |
|---|---|---|
| 17:20:58.59 | 14.80 V | 33 |
| **17:20:58.90** | **15.70 V** | 42 |
| 17:20:59.42 | 15.80 V | 49 |
| 17:20:59.93 | 15.50 V | 56 |

**Düşen bir uçakta pil gerilimi yükselemez.** Tek açıklaması yükün kalkması.
Bag'de ölçülen akım 16-19 A idi; o yük kesilince çökmüş bir 4S pak ~1 V
toparlar. Görülen tam olarak bu, ve düşüşün başlangıcından **0.3 saniye
sonra**.

Yükselen yüzde de aynı şeyin sonucu: PX4'ün SoC kestirimi gerilime bakıyor.

---

## 4. Katkıda bulunan kronik kusur: motor doygunluğu

Uçuş boyunca motor çıkışları (PWM tavanı **1900**):

| Motor | ortalama | max | **tavanda** |
|---|---|---|---|
| m1 | 1633 | 1847 | 2 örnek (%0.2) |
| m2 | 1613 | 1900 | 2 örnek (%0.2) |
| **m3** | **1803** | **1900** | **39 örnek (%4.1)** |
| **m4** | **1799** | **1900** | **48 örnek (%5.1)** |

m3/m4 ile m1/m2 arasında **ortalama 186 PWM** kalıcı fark (en büyük 614).

PX4 quad-X diziliminde **m3 ve m4 aynı dönüş yönündeki çifttir** (m1/m2 CCW,
m3/m4 CW). Bir dönüş çiftinin sürekli daha sert çalışması **kalıcı bir yalpa
torkuyla boğuşmak** demektir — ağırlık merkezi kayması değil, **hizalama**
sorunu (bükülmüş kol, eğik motor yatağı, yanlış hatveli pervane).

⚠️ Bu kusur düşmeyi **tetiklemedi** ama **payı sıfırlamıştı**: doygun motorun
artıracak yeri yoktur. Güç kesilmese bile bu uçak marjsız uçuyordu.

Pil de zayıftı: %32-36, yük altında 14.4-15.4 V (4S'te hücre başına ~3.6 V).
Düşen gerilim aynı PWM'de daha az itki demek — doygunluğu hızlandırır.

---

## 5. Elenen hipotezler

| Hipotez | Neden elendi |
|---|---|
| **Pixhawk güç kaybetti** | Düşüş boyunca 10 Hz'de **taze irtifa** basıyor (13.00 → 1.60 m) ve **mod değiştiriyor** (OFFBOARD → LAND → POSCTL). Ölü FCU bunları yapamaz. `px4_link_ok` son mesaja kadar `True` |
| **Yazılım disarm etti** | `armed` düşüş boyunca **True**. Kod zaten havada disarm'ı engelliyor; ihlal yok |
| **PX4 failsafe'i** | ylp02'nin kendi statustext'inde uçuş boyunca **yalnız iki mesaj** var: `Armed by external command`, `Takeoff detected`. Failsafe mesajı **yok**. `failsafe_active` hep `False` |
| **Setpoint kesildi (OFFBOARD düştü)** | `/drone_3/control/setpoint` bag'in sonuna kadar akıyor. OFFBOARD → LAND geçişi düşüş **başladıktan sonra** |
| **Kaçınma manevrası** | `collision_avoidance` `avoid=0` — hiç devreye girmedi |
| **Mesh kaybı** | Zaman aşımlarının olduğu pencerede lider alımı **%0-2 kayıp**. Ayrı bir sorun ama düşmenin sebebi değil |
| **Bilgisayar (Pi) öldü** | Mesh yayını çarpmaya kadar sürdü ve **taze** veri taşıdı |

---

## 6. 🔴 FİZİKSEL KONTROL LİSTESİ — uçmadan önce

Kanıt **motor besleme hattını** işaret ediyor. Sırayla:

1. **Pil ana konnektörü (XT60/XT90).** Yük altında ark yapıp kesen gevşek ya
   da oksitli bağlantı ilk aday. **Çıkar ve gözle bak:** yanık izi, kararmış
   pim, gevşek geçme. Ark yapmış bir konnektör gözle bellidir.
2. **Güç dağıtım kartı (PDB) lehimleri** — özellikle ESC besleme yolları.
   Soğuk lehim titreşimle açılır.
3. **ESC güç kabloları**, öncelikle **m3 ve m4**'ünkiler.
4. **Pilin kendisi.** %32'de 14.43 V'a düşüp 24.55 A çekiyordu. Zayıf hücre
   ya da iç bara olabilir. Şüpheliyse kullanma.
5. **m3 ve m4 mekaniği** (§4'teki doygunluk): pervane hasarı/hatvesi/yönü,
   motor yatağı sürtünmesi, **kol bükülmesi**, motor oturma açısı.
6. Açık P0 **gevşek PX4 güç soketi** bu uçuşla doğrulanmadı ama çürütülmedi
   de — ayrıca bakılsın.

### 6.1 Doğrulama testi — yerde, ~10 dakika

**Pervaneler SÖKÜLÜ**, uçak sabitlenmiş hâlde:

1. Motorları düşük gazda döndür.
2. **Pil konnektörünü, PDB'yi, ESC kablolarını tek tek elle oynat.**
3. Akım/gerilim telemetrisini izle — **anlık düşme ya da kesilme** görürsen
   suçlu odur.

Telemetriyi Claude okur; kabloları oynatmak operatörün işi. Pervane takılıyken
yapılmaz — burada kanıt toplanıyor, uçuş denenmiyor.

### 6.2 Motor karşılaştırması

Gövdeye fiziksel iş yapıldıysa `python3 src/gcs/titresim_olc.py ylp02`
zaten koşulmalı (`CLAUDE.md` §9, saha günü listesi). Ayrıca her motoru ayrı
çalıştırıp **akım/devir** karşılaştırmak zayıf motoru 10 dakikada bulur.

---

## 7. Kanıt nerede

Oturum sonunda laptopta:

```
scratchpad/kanit/ylp02/ylp02_20260905_171826/   ylp02 kendi rosbag'i (6.8 MB)
scratchpad/kanit/ylp02/gunluk_hepsi.tgz         ylp02 bütün konteyner logları
scratchpad/kanit/ylp01/ylp01_20260905_171813/   ylp01 rosbag'i (65 MB)
scratchpad/kanit/ylp01/gunluk.tgz               ylp01 logları
```

🔴 **Bunlar `/tmp` altında ve makine yeniden başlayınca SİLİNİR.** Kalıcı
saklanacaksa taşınmalı. ylp00'ın bag'i (`ylp00_20260905_171802`) hâlâ uçakta;
kayıt sınırı 5 oturum, yeni uçuşlar silecek.

---

## 8. Ölçüm yöntemi — tekrar edilebilsin diye

Düşen uçağın **kendi kaydı çarpmada kesilir** (rosbag yazma önbelleği
boşaltılamaz). Bu yüzden son saniyeler **diğer uçakların mesh kaydından**
çıkarılır:

* Her uçak komşularının `AgentStatus`'unu `/swarm/public/droneN/status`
  konusunda **kaydediyor**. İçinde `pos_z`, `vel_z`, `battery_voltage_v`,
  `state`, `flight_mode`, `armed`, `healthy`, `px4_link_ok` var.
* `rosbag2_py.SequentialReader` ile mcap dosyaları **metadata olmadan da**
  okunabilir (`storage_id="mcap"`, dosyayı tek tek aç).
* İki ayrı komşunun kaydını karşılaştır — ±0.01 s uyuşuyorsa veri gerçek,
  alım artefaktı değil.

Kullanılan betikler `scratchpad/` altında: `ylp02_iz.py` (mesh'ten yeniden
kurma), `ylp02_son.py` (son saniyeler, tam çözünürlük), `ylp02_motor.py` /
`ylp02_motor2.py` (motor doygunluğu), `ylp02_px4.py` (statustext + mod),
`son_mesaj.py` (hangi konu ne zaman sustu).

**Bir sonraki düşmede ilk iş:** uçak ağa gelir gelmez, başka hiçbir şey
yapmadan bag'ini ve loglarını çek. Kayıt sınırı eskisini siler.

---

## 9. Bu olaydan çıkan yan bulgular

Düşmeyle doğrudan ilgili değil ama aynı uçuşta ölçüldü:

* 🔴 **`land` komutu her otonom inişte YANLIŞ failsafe tetikliyor.**
  `agent_health_monitor.py`: `_OFFBOARD_LOSS_TIMEOUT_S = 5.0` ve `LANDING`
  durumu `_AIRBORNE` kümesinde. Bizim `land`'imiz PX4'ü OFFBOARD'dan
  AUTO.LAND'e alıyor, 5 saniye sonra "OFFBOARD kayboldu" kritik arıza
  sayılıyor. ylp01'de ölçüldü: `land` 17:21:09.25 → failsafe 17:21:14.25,
  **tam 5.000 saniye**. İniş bittiği için zararı olmadı; uçuş ortasında bir
  `land` verilirse otonomi orada donar.
* 🔴 **Üç uçakta da pil telemetrisi güvenilmez.** ylp00 sabit değer,
  ylp01 `65.54 V / -1%` sabit, ylp02'nin mesh'e gönderdiği değerler
  düşerken yükseliyordu. **Pil tabanlı hiçbir korumaya güvenilemez.**
* 🔴 **ylp00'da kumanda alıcısı ölü:** `rc_ibus_kopru: i-BUS HİÇ GEÇERLİ
  ÇERÇEVE YOK (/dev/ttyAMA2)`. O uçakta pilot müdahalesi mümkün değildi.
* **ylp00 da aynı dakikada sert indi** — 11 m'den 4.48 m/s, sekerek. Kendi
  logunda `Batarya dusuk: 14.8V` ve sağlık kapısı. Ayrı olay, daha hafif.
* **MAVROS statustext düşürülüyor:** ylp00'da `mavconn: DROPPED Message-Id
  253 — TX queue overflow`. Message 253 = STATUSTEXT. PX4'ün açıklamaları
  kuyruk taşmasında kaybolabiliyor — arıza analizini körleştiriyor.
* **Lider ile takipçi aynı görevi yaşamadı:** ylp00 17:20:15'te
  EXECUTE_QR_TASK'a geçti (QR'a 0.18 m yaklaştı), ylp01 bunu hiç öğrenmedi ve
  NAVIGATE_TO_QR'da 30 sn zaman aşımına düşüp eve döndü. Görev durumu
  yayılımı ayrı bir kusur, ayrıca kazılmalı.

---

## 10. Karar gerekiyor: ulog

`CLAUDE.md` §9 *"Pixhawk'ta log açma"* diyor (RAM sınırı). Ama:

* Bu **aynı uçakta ikinci açıklanamayan havada arıza** (öncekisi
  `YAPILACAKLAR.md` P0: *"ylp02'nin havadaki failsafe sebebi BİLİNMİYOR"*).
* PX4'ün kendi gerekçesi iki kez de okunamadı — ulog kapalı, statustext
  düşürülüyor.

**ulog geçici açılmadan üçüncüsünde de aynı yerde olacağız.** Bu bir operatör
kararı; `YAPILACAKLAR.md` zaten "geçici istisna operatör kararı" diye
bırakmış.
