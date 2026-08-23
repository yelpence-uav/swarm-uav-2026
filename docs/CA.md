# CA — Çarpışma Önleme: dikey yol verme

**Son güncelleme:** 23 Ağustos 2026, 20:30 — dikey yol verme yazıldı,
dağıtıldı, beş yer testi geçti

> Bu belge çarpışma önlemenin **bugünkü tasarımı ve durumu**. 23 Ağustos
> sabahki sürümü yatay/dikey karşılaştırmasıydı; karar verildi ve uygulandı,
> belge ona göre yeniden yazıldı.
>
> Sayıların hepsi ya **koddan okunarak** ya **benzetimle** ya da **sahada
> ölçülerek** çıkarıldı. Varsayım olanlar 🔴 ile işaretli.

---

## 0. Otuz saniyede

- **Birincil kaçış DİKEY.** Çatışan uçaklardan kimliği büyük olan, küçüğün
  **ölçülen** irtifasından `katman` kadar uzağa gider.
- **Yatay itme SON ÇARE** — yalnız sert kabuğun (`hard`) içinde açılır.
  Normal çatışmada formasyon geometrisine hiç dokunulmaz.
- Rütbe **kadrodan** gelir (`SURU_KADRO`), anlık çatışma kümesinden değil.
  Merdiven **dönüşümlü**: +katman, −katman, +2×katman…
- Kod dağıtıldı, **beş yer testi geçti** (§6). Havada **hiç uçmadı**.
- 🔴 Açık tek büyük bilinmeyen: **tırmanma itki payı** — §7.

```
d0 = 4.0 m    catisma yaricapi (YATAY mesafe, cikis 4.5 m)
hard = 2.5 m  yatay son carenin acildigi kabuk
katman = 3.0 m  ardisik rutbeler arasi dikey ayrim
v_dikey = 1.2 m/s (= PX4 MPC_Z_VEL_MAX_UP)  a = 2.0  kp = 2.0
```

---

## 1. Kural

Her uçak 20 Hz'de şunu hesaplar:

```
1. CATISMA KUMESI
   d_yatay(j) < d0  olan komsular.  (3B DEGIL — gerekce TUZAKLAR §3.12)
   Histerezis: giris d0, cikis d0 + 0.5 m

2. YOL VERECEK MIYIM
   Yalnizca BENDEN KUCUK kimlikli catisan komsuya yol veririm.
   Yoksa CAPAYIM: dikeye hic dokunmam, gorev ne diyorsa o.

3. ZATEN AYRIK MIYIM
   Hepsinden |rel_z| >= katman ise yapacak bir sey YOK.
   (Iki komsunun ARASINDA olup ikisinden de uzak olmak da gecerli.)

4. NEREYE
   hedef = referansin OLCULEN irtifasi + rutbe ofseti
   rutbe 0 -> +0     (capa)
   rutbe 1 -> +katman
   rutbe 2 -> -katman
   rutbe 3 -> +2*katman ...
   Yon YAPISKAN: catisma boyunca degismez.

5. NASIL
   vz = gorev_vz - kp * (hedef - simdi)     NED: yukari = NEGATIF
   hiz ve ivme tavanlariyla kirpilir
```

**Dönüş:** çatışma bittikten (4,5 m yatay) **2 sn** sonra, 0,5 m/s ile
nominale iniş, 0,3 m toleransta bırakma. Toplam ~8 sn.
**Körlükte dönülmez** — §4.

### Neden rütbe kadrodan, komşunun kararından değil

İki uçağın birbirinin *çatışma listesini* tahmin etmesi gerekseydi listeler
tutmazdı. Kusursuz mesh'le bile, 4 m aralıkta çizgi formasyonu:

```
drone1 gorur {2}    -> siralamada 1. -> +0
drone2 gorur {1,3}  -> siralamada 2. -> +1 katman
drone3 gorur {2}    -> siralamada 2. -> +1 katman    <-- 2 ve 3 AYNI KATMANDA
```

Kimse paket kaybetmedi; sorun "çatışma" ikili bir ilişki ama rütbe sıralı bir
liste. **Sabit rütbe** bu sorunu kaldırıyor.

### Neden dönüşümlü merdiven

İlk tasarım "benden küçüklerin en yükseğinin `katman` üstüne çık" diyordu.
Benzetimde çöktü:

```
t=1.45 s -> drone2 13.16 m, drone3 13.16 m, DIKEY AYRIM 0.00 m
```

Bir **yarış**: t=0'da ikisi de yalnız drone1'i görüyor, ikisi de aynı hedefi
hesaplıyor ve aynı hızla oraya tırmanıyor. Kaskad sıralı ama uçaklar eş
zamanlı. Dönüşümlü merdivende hedefler baştan farklı olduğu için uçaklar ilk
andan itibaren **birbirinden ayrılıyor** — ve üç uçakta en büyük sapma
6 m yerine **3 m**.

### Neden yatay tamamen kapalı değil

Benzetim (bir uçak asılı, diğeri üzerine sürülüyor — 22 Ağustos saha
testinin birebir karşılığı), en yakın 3B mesafe:

```
yaklasma    SAF DIKEY   SAF YATAY   DIKEY + SON CARE
 1.0 m/s      2.63 m      2.27 m        2.79 m
 2.5 m/s      1.01 m      2.02 m        2.06 m
 4.0 m/s      0.47 m      1.53 m        1.20 m
```

Dikey yetkiyi gerçekçi olmayan değerlere çıkarmak bile kapatmıyor
(v=5 a=5 → 1,83 m). **Sebep ayar değil geometri:** dikey kaçışın
kazanabileceği en fazla mesafe `katman` kadardır ve onu kurmak 2-3 saniye
alır. Yatay itmenin böyle bir tavanı yok.

Karar: normal çatışmada saf dikey, sert kabukta yatay da açılır.

---

## 2. Görevdeki asıl kullanım — formasyon yakın geçişi

Kafa kafaya karşılaşma görevde nadir (operatör, 23 Ağustos). Asıl yük
formasyon geçişlerinde. Benzetim:

```
yanal aralik  bagil hiz   en yakin 3B   kazanilan dikey   YATAY KAYMA
     3.0 m      3.0 m/s      3.09 m         0.75 m          0.00 m
     3.5 m      3.0 m/s      3.54 m         0.51 m          0.00 m
     2.0 m      3.0 m/s      2.61 m         0.75 m          0.92 m
```

Yatay kayma **sıfır** — formasyon geometrisi bozulmuyor, ayrım yalnız
dikeyden geliyor. Tasarımın hedeflediği davranış tam olarak bu.

---

## 3. Aralık ve şartname

Şartname ajanlar arası mesafeyi **hakemlere** bırakıyor; değer çalışma
anında QR/`FormationCommand` ile geliyor (§5.1: *"Ajanlar arası X (Örn: 5m)"*,
QR örneğinde 6 m). Operatör hakemlerden **3-10 m** aralığını duymuş.

**`d0` = 4,0 SABİT** (operatör kararı). Aralığa bağlanmadı. Aralık `d0`'ın
altına inerse kaçınma normal formasyonda sürekli tetikli olur ve **merdiven
kalıcı hâle gelir** — davranış doğru ama bilinmeli, o yüzden
`_on_formation_command` uyarı logluyor ve `SystemEvent` yayıyor.

---

## 4. Körlükte ayrım bırakılmaz

"Çatışma bitti" kararı komşunun uzakta olmasına dayanıyor. **Komşuyu
kaybetmek de aynı görünüyordu:** bayat veri listeden düşer, çatışma false
olur ve uçak 2 saniye sonra kazandığı ayrımı geri verir — hem de komşusunun
nerede olduğunu bilmediği anda. 21 Ağustos'ta mesh **46,4 saniye** tek yönlü
ölmüştü (`TUZAKLAR` §2.15).

Artık: körlük bayrağı kalkmışken **irtifa tutulur**, dönüş sayacı ilerlemez,
`donus_kor` sayacı artar ve uyarı basılır. Komşu tekrar görülünce normal
akış sürer. Mesh kalıcı koparsa uçak katmanında kalır — güvenli taraf.

---

## 5. Mesh gerçeği — 23 Ağustos'ta ölçüldü

Kaçınmanın gördüğü dünyanın tazeliği. Eskiden "%30 kayıp" varsayılıyordu;
ölçüldü ve **kaynağı radyo değil kendi köprümüz** çıktı (`TUZAKLAR` §2.20).

| | önce | sonra |
|---|---|---|
| komşu tazeleme | 7,1 Hz | **10,5 Hz** |
| en büyük boşluk | 0,41 s | **0,31 s** |
| gerçek havadan kayıp | — | **%1-5** |

Benzetim artık bu sayılarla besleniyor (10 Hz, %5). Tohum taramasında sapma
0,05 m'nin altında — **mesh kalitesi CA sonucunu neredeyse hiç
değiştirmiyor**, sorun bilgi değil manevra.

---

## 6. Yer testleri — hepsi geçti (23 Ağustos)

Gerçek mesh verisiyle, gerçek uçaklarda, **uçuş yoluna dokunmadan** (gözlem
modu: ikinci bir CA örneği, girdi/çıktı `/g0…`'a yönlendirilmiş).

| test | ne doğruladı | sonuç |
|---|---|---|
| **G0-1** datum | `rel_z` iki uçaktan zıt işaretli, 3 cm farkla (−0,428 / +0,397) | ✅ |
| **G0-2** rütbe + işaret | çapa 0,000 · rütbe 1 → −1,184 (tavanda doyuyor) | ✅ |
| **G0-3** yatay son çare | 0,6 m arayla açıldı, **zıt yönlerde** (+3,74 / −3,65) | ✅ |
| **G0-4** geçirgenlik | çatışma yokken çıktı girdiyle **birebir**, damga değişmemiş | ✅ |
| **G0-5** körlükte tutma | `donus_kor=1`, uyarı çıktı, ayrım bırakılmadı | ✅ |

Araçlar: `deploy/rpi/teshis/g0_dikey_datum.py` ·
`g0_dikey_gozlem.sh` · `g0_korluk_tutma.sh`

Ek doğrulamalar: uçan düğüm yerde tamamen sessiz (`passthrough=0 avoid=0`) ·
`/control/setpoint` **tek yayıncı** · test kancaları temiz.

**Birim test: 78/78** (`test_ca_dikey.py` 26 + mevcutlar).

---

## 7. 🔴 Açık — uçuştan önce

| # | konu | nasıl kapanır |
|---|---|---|
| 1 | 🔴 **Tırmanma itki payı ölçülmedi.** `a=2.0` → 1,20× askı itkisi (~%72 gaz tahmini); askı gazı %66 ölçülmüş, kalanı bilinmiyor | Operatörün iki uçaklı testinde kayıttan `vfr_hud.throttle` tepesi + gerçekleşen `vz` |
| 2 | `MPC_Z_VEL_MAX_UP = 1,2` tırmanmayı sınırlıyor. 3,0'a çıkarmak yanal kaymayı 4,8 → 1,9 m yapıyor | #1 ölçüldükten sonra ayrı karar; kalkışı ve görev tırmanışlarını da etkiler |
| 3 | Havada **hiç uçmadı** | `KARAR-02` gereği ilk uçuştan önce `ultracode` denetimi |
| 4 | ylp00'ın `home` kaydı 0,41 m bayat | Arm'da PX4 yeniden kurar; arm sonrası G0-1 tekrarı |
| 5 | Üç uçağın **aynı noktadan geçtiği** çapraz slot değişiminde hiçbir ayar kabul eşiğini tutturmuyor (1,76 m) | `formation_node` devreye girerken: o geometri hiç üretilmemeli |

---

## 8. Bilinen algoritma zayıflıkları

| | ne | durum |
|---|---|---|
| B1 | Asılıyken teğet sıfır | ⚪ konu dışı — `k_tan=0`, teğet kapalı |
| B2 | `xy_guard` altı komşu tamamen atlanıyordu | ✅ **kapatıldı** — artık yalnız yön vektörünü koruyor |
| B3 | Uzaklaşan komşuya çekim | ✅ 22 Ağu'da düzeltildi (kabuk içinde geçerli) |
| B4 | Yavaş yaklaşmada koruma `hard`'da başlıyor | açık — dikey kip bunu telafi ediyor |
| B5 | `hard` eşiğinde süreksizlik | ✅ 22 Ağu'da düzeltildi |
| B6 | Merdiven kurulma süresi (3,1 sn) kafa kafaya kapanmadan (0,7 sn) uzun | bilinen, `ucus_ayarlari.py` uyarıyor |

---

## 9. Nerede ne var

| | |
|---|---|
| Çekirdek | `src/swarm_core/swarm_core/collision_avoidance/ca_core.py` |
| Düğüm | `collision_avoidance_node.py` |
| Komşu adaptörü | `komsu_adaptoru.py` (dikey datum düzeltmesi burada) |
| **Benzetim** | `src/gcs/ca_benzetim.py` — gerçek `ca_core`'u koşturur |
| Parametre kaynağı | `src/gcs/ucus_ayarlari.py` (PX4 tavan denetimleri dahil) |
| Başlatma | `deploy/rpi/baslat.sh` — rütbe `SURU_KADRO`'dan |
| Yer testleri | `deploy/rpi/teshis/g0_*.sh|py` |
| Birim testler | `src/swarm_core/test/test_ca_dikey.py` |
| Yedek düğüm | `swarm_control/.../basit_kacinma_node.py` (kapalı, silinmedi) |
| Tuzaklar | `TUZAKLAR` §2.20 §2.21 §2.22 §3.12 §1.23 §1.24 |
