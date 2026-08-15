# KARARLAR — verilmiş ama henüz uygulanmamış kararlar

**Son güncelleme:** 15 Ağustos 2026, 13:47

Sohbette verilen kararlar oturum bitince kayboluyor. Bu defter onları
tutuyor: **ne karar verildi, neden, ne zaman uygulanacak, nasıl test edilecek.**

---

## ⚠️ CLAUDE İÇİN KURAL

**Bir aşamaya/işe geldiğinde ÖNCE buraya bak.**

O işle ilgili bir karar varsa:

1. **Operatöre söyle** — "bu konuda şu karar verilmişti"
2. **Önerilen seçeneği belirt** ve gerekçesini hatırlat
3. Operatör farklı bir seçenek isterse **o an detaylıca konuşulur**

Kararı sessizce uygulama, ama her seferinde sıfırdan da tartışma. Karar
zaten verilmiş; işin senin tarafın onu **hatırlatmak** ve **uygulamak**.

Yeni bir önemli karar verilirse **buraya yaz** — özellikle "şimdi değil,
sırası gelince" denilen şeyleri. Onlar en kolay kaybolanlar.

---

## Durum işaretleri

`🟡 BEKLİYOR` — karar verildi, sırası gelmedi
`🔵 SIRASI GELDİ` — aşamaya ulaşıldı, uygulanacak
`✅ UYGULANDI` — bitti, sonucu yazıldı
`❌ VAZGEÇİLDİ` — gerekçesiyle

---

# KARAR-01 — Çarpışma önleme: Seçenek C

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** `SURU_ENTEGRASYON.md` **AŞAMA 1B**
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**`collision_avoidance` kullanılacak, ham `AgentStatus`'tan beslenerek.**
`kinematic_fusion` devreye alınmayacak.

## Neden

Repoda aynı işi yapan iki kod var ve **ikisi de aynı topic yuvasını**
kullanıyor (`/control/setpoint/raw` → `/control/setpoint`), yani aynı anda
koşamazlar. Birini seçmek zorunlu.

| | `basit_kacinma` (sahada) | `collision_avoidance` (sürü) |
|---|---|---|
| **Radyal itme** | yalnız **mesafeye** göre | mesafe **+ yaklaşma hızı** |
| Teğet ("sağa geç") | var | var |
| Dikey | yok | var |
| Komşu kaynağı | ham `AgentStatus` | `NeighborInfo` ← `kinematic_fusion` |

**Belirleyici fark:** `collision_avoidance` radyal itmede **yaklaşma hızını**
hesaba katıyor. 5 m arayla *duran* iki uçak ile 5 m arayla saniyede 6 m
*kapanan* iki uçak — `basit_kacinma` ikisine aynı tepkiyi verir,
`collision_avoidance` ikincisinde çok daha erken iter.

**`kinematic_fusion` neden atlanıyor:** EMA yumuşatması
(`alpha_pos=0.3`) ~2.33 örnek gecikme ekliyor; mesh ~5-7 Hz'de bu **0.35-0.47 s**
demek. 3 m/s'te komşunun **1.2 m önceki** yerine bakmak. Kaçınmada ödenecek
bir bedel değil.

**Atlanabilir olmasının sebebi:** `AgentStatus` mesajında `vel_x/vel_y/vel_z`
**zaten var** — `NeighborInfo`'nun taşıdığı bilgi ham veride mevcut. Fusion'ın
tek kattığı yumuşatma, o da gecikme.

## Nasıl uygulanacak

1. **Adaptör** (~20 satır): `AgentStatus` → `NeighborObs`
   (`rel_x/rel_y/rel_z`, `rel_vx/rel_vy/rel_vz`, `distance`).
   `collision_avoidance_node`'un komşu aboneliği
   `/swarm/agent/drone{ben}/neighbor/drone{N}` yerine
   `/swarm/public/drone{N}/status`'a bağlanır.
2. `basit_kacinma` **kapatılır** (aynı yuva — ikisi birden koşamaz).
3. Parametreler ayarlanır (aşağı).

## 🔴 Parametreler — operatör talimatı

**Önce güvenli mesafeden başla, sonra kıs.**

| Parametre | `collision_avoidance` varsayılanı | **Başlangıç değeri** |
|-----------|-----------------------------------|----------------------|
| `d0_m` (itme başlar) | 4.5 | **8.0** |
| `hard_m` (doyum) | 2.0 | **4.0** |

Varsayılan 4.5 m bizim geometrimize göre **çok dar** — `MIN_AYRIM_M` zaten
4.0. `basit_kacinma`'nın sahada kullandığı 8.0/4.0 ile başlanacak; güven
oluştukça kısılabilir.

> ⚠️ **Dikkat — d0 ile formasyon geometrisi çakışabilir.**
> Aralık 12 m'de planlanan **en yakın yaklaşma 8.41 m**. `d0 = 8.0` bunun
> hemen altında, yani pay **0.49 m**. Gerçek uçuşta yarım metre sapma olursa
> kaçınma **normal formasyon geçişinde** devreye girer ve formasyonla
> çekişir.
>
> Bu bir hata değil, bilinmesi gereken bir denge. İlk uçuşta kayıttan
> **kaçınmanın ne zaman tetiklendiğine** bak:
> - Yalnız gerçek yakınlaşmalarda tetikleniyorsa → 8.0 doğru
> - Her formasyon geçişinde tetikleniyorsa → `d0` 7.0'a indirilir ya da
>   `ARALIK_M` büyütülür

## 🔴 Test — zorunlu, atlanmayacak

**1. Yerde (Y):** Adaptör doğru mu — komşu 10 m'deyken itme 0, 6 m'deyken
sıfırdan büyük ve **doğru yöne** mi. Uçuş yok.

**2. Gözlem (G) — tek uçuş:** `basit_kacinma` komutta kalır,
`collision_avoidance` gözlem modunda (`-r .../control/setpoint:=/gozlem/...`).
İkisi **aynı girdiyi** alır. Kayıttan karşılaştır: aynı anlarda mı, benzer
yönde mi, büyüklük farkı ne kadar. Beklenmeyen fark varsa sebebi bulunmadan
ilerlenmez.

**3. Komutta (K) — `--senaryo asili`:** Bir uçak havada asılı durur,
operatör diğerini **kumandayla yaklaştırır**. Bu test zaten yazılı ve tam bu
iş için var. Kayıttan gör: ne zaman itti, ne kadar itti, geri döndü mü.

**4. İki uçak, saha senaryosu:** Kritik ayrım eşiğin üstünde kaldı mı, ve
kaçınma normal formasyon geçişlerinde tetiklendi mi.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | `basit_kacinma` kalsın | Yaklaşma hızını radyalde görmüyor, dikey yok |
| B | `collision_avoidance` + `kinematic_fusion` | 0.4 s gecikme |
| D | `basit_kacinma`'ya yaklaşma hızı ekle | Sürü kodu kullanılmamış olur |

`basit_kacinma` **silinmeyecek** — C beklenmedik davranırsa tek dosya
değişikliğiyle geri dönülür.

---

# KARAR-02 — Claude effort seviyesi: hep `max`, ultracode noktasal

**Durum:** 🟡 BEKLİYOR — kural yürürlükte, hatırlatma anları henüz gelmedi
**Ne zaman:** Her oturum (kural) + `SURU_ENTEGRASYON.md` **ADIM 1, 3, 4** (hatırlatma)
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**`/effort` menüsü daima `max` kalır. Ultracode menüden AÇILMAZ.**

Çok ajanlı denetim gerektiğinde operatör **o mesajın içine `ultracode`
kelimesini yazar** — o tur çok ajanlı çalışılır, sonraki tur kendiliğinden
`max`'a döner. Menü hiç kurcalanmaz.

## Neden

`/effort` menüsünde ikisi **aynı listede ve birbirini dışlıyor.** Ultracode
seçilince effort `xhigh`'a düşüyor (ayar şemasındaki tanımı birebir:
*"xhigh effort plus standing dynamic-workflow orchestration"*). Yani ultracode
açmak, düşünme derinliğinden bir kademe feragat etmek demek.

| | Düşünme derinliği | Ajan sayısı |
|---|---|---|
| `max` | en derin | 1 |
| `ultracode` | xhigh (bir kademe altı) | çok + karşıt doğrulama |

**Günlük iş neden `max`:** entegrasyon işi sıralı ve cerrahi — üç satırlık
düzeltme, telemetriden teşhis, komut çalıştırma. Bunlar *derinlik* problemi.
Ayrıca ultracode arka planda dakikalarca sürüyor; sahada pervaneler dönerken
beklenecek şey değil, ve alt ajanlar sohbet bağlamını görmüyor.

**Denetimler neden ultracode:** "%30 paket kaybında hangi senaryoda iki lider
çıkar" bir *kapsama* problemi. Orada 8 bağımsız avcı, 1 derin düşünenden iyi.
Gerekçe somut: Claude bu depoda üç kez çapalama hatası yaptı —
`formation_node`'da ileri-besleme yok dedi (vardı), ylp02'nin eğim değerleri
PX4 varsayılanı dedi (tersiydi), çoklu üretici çakışması çözülmemiş dedi
(susturma ile çözülmüştü). Üçü de tek kanalda bulunamadı. Onu hiç duymamış
bağımsız bir ajan o çapayı miras almıyor.

## 🔴 Claude'un yapacağı — hatırlatma anları

Şu üç adıma gelindiğinde, **uçmadan önce** operatöre söyle:

| Adım | Düğüm | Neden fan-out gerekli |
|------|-------|------------------------|
| **ADIM 1** | `consensus_node` | Kayıplı mesh'te lider seçimi; iki lider senaryosu aranmalı |
| **ADIM 3** | `formation_node` | 50 Hz'de uçağa setpoint yazıyor |
| **ADIM 4** | `collision_avoidance` | İki uçak arasındaki tek koruma katmanı |

Söylenecek cümle: *"Bu düğüm ilk kez havaya kalkacak. KARAR-02 gereği burada
çok ajanlı denetim öneriliyor — bu mesaja `ultracode` yazar mısın?"*

Operatör istemezse tartışılmaz, tek kanalda ilerlenir.

**Genel kural:** havaya kalkacak bir düğüm **ilk kez** açılmadan önce denetim
önerilir. Belge, config, kurulum, düzeltme işlerinde önerilmez — orada israf.

## Ayrıca — Claude effort'unu kendi okuyabilir

```bash
echo $CLAUDE_EFFORT      # max / xhigh / high / ...
```

Ultracode'un açık olup olmadığı Claude'a zaten her turda sistem tarafından
bildiriliyor, komut gerekmiyor.

## ✅ Uygulandı — otomatik uyarı (Claude'un hatırlamasına bağlı değil)

`.claude/settings.json` → `UserPromptSubmit` hook'u → `.claude/effort_bekcisi.sh`.
Effort `max` değilse **her mesajda** operatöre uyarı basıyor, `max` iken
tamamen sessiz. Dosya repoda, yani takımdaki herkeste çalışıyor.

**15 Ağustos'ta ölçülenler** (betiğin başında da yazılı, silme):

| Bulgu | Sonuç |
|-------|-------|
| `$CLAUDE_EFFORT` hook ortamında **yok** (68 değişkene bakıldı) | Oradan okunamaz. İlk deneme bunu varsaymıştı ve max'tayken bile bağırıyordu |
| `$CLAUDE_EFFORT` **Bash aracında canlı ve doğru** | Kesin doğrulama yolu bu |
| Seviye transkriptte her `assistant` kaydında yazılı | Hook oradan okuyor |
| Transkript **bir tur geriden** geliyor | Uyarı bir mesaj gecikmeli çıkabilir |
| Hook'ta `$CLAUDE_PROJECT_DIR` ve `$CLAUDE_CODE_SESSION_ID` **var** | Transkript tahminle değil kesin bulunuyor |

Bu yüzden iki katmanlı: **hook** hızlı ama gecikmeli tripwire (operatöre
ekranda uyarı), **Claude** `echo $CLAUDE_EFFORT` ile kesin doğrulama.
Betik okuyamadığında operatörü rahatsız etmiyor, yalnız Claude'a
"doğrula ve bildir" diyor — bozuk okuma kurt masalına dönüşmesin.

Hook çalışmıyorsa: bir kez `/hooks` menüsünü aç (ayar dosyasını yeniden
okutuyor) ya da oturumu yeniden başlat.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | Menüde hep ultracode | Her turda xhigh; sahada arka plan beklemesi; belge işinde israf |
| B | Aşamaya göre menüden gidip gel | Aynı sonucu veriyor ama elle iş; tek kelime yazmak daha ucuz |
| C | Hiç fan-out yok | Denetimler tek kanalda kalır — çapalama riski karşılıksız |

---

# KARAR-03 — Pil failsafe'i, ölçer modül gelince açılacak

**Durum:** 🟡 BEKLİYOR — donanım alınmadı
**Ne zaman:** LiPo pil ölçer modül alınıp RPi'ye bağlandığında
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**Pil failsafe'i şimdi açılmayacak.** İleride bir **LiPo pil ölçer modül**
alınacak, voltaj verisi doğrudan **RPi'ye** verilecek. O zaman:

1. Pil değerleri YKİ arayüzünde görünecek
2. Pil failsafe'i o zaman devreye alınacak

## Neden şimdi değil

Uçaklar **regülatörden** besleniyor, PX4'te `BAT1_SOURCE` disabled. Okunan
3.1 V gerçek pil voltajı değil. Bu yüzden pil izleme **üç yerde birden**
kapalı (`BATARYA_KRITIK_V=0.0`). Olmayan bir ölçüme dayanarak failsafe
açmak, uçağı yerde tutan sahte bir alarm üretir.

## Nasıl uygulanacak — açılması artık TEK parametre

15 Ağustos'taki `preflight_checker` düzeltmesinden sonra eşik üç yerde de
`ctx.battery_critical_voltage_v`'den geliyor. Modül gelince yapılacak:

| Adım | Ne |
|------|-----|
| 1 | Modülün voltajını yayınlayan küçük bir düğüm (I2C/UART, ~60 satır) |
| 2 | `AgentStatus.battery_voltage_v` bu kaynaktan beslensin (şu an MAVROS'tan) |
| 3 | `deploy/rpi/baslat.sh` → `BATARYA_KRITIK_V=13.6` |
| 4 | `src/gcs/frontend/src/services/gorunum.ts` → `PIL_GOSTER = true` |
| 5 | `src/gcs/backend/config.yaml` → `alerts.susturulan`'dan batarya kodlarını çıkar |

⚠️ **3, 4, 5 birlikte yapılmazsa** sistem tutarsız davranır: biri pili
umursar, diğeri umursamaz. `DURUM.md` §3'te de yazılı.

## Test

- **Yerde:** modül takılı, pil takılı → okunan voltaj çok metreyle uyuşuyor mu
- **Yerde:** eşiği geçici olarak okunan voltajın üstüne çek → preflight
  arming'i engelliyor mu (`test_esik_baglamdan_gelir` bunu zaten kilitliyor)
- **Yerde:** eşiği 0.0'a çek → engel kalkıyor mu
- Uçuş testi **gerekmiyor**; failsafe yolu zaten ölçülmüş kod

---

# Karar şablonu (yeni karar eklerken kopyala)

```markdown
# KARAR-NN — <konu>

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** <hangi aşama / hangi iş>
**Karar veren:** <kim> (<tarih>)

## Karar
<tek cümle: ne yapılacak>

## Neden
<gerekçe, ölçüm varsa sayılarla>

## Nasıl uygulanacak
<adımlar, maliyet>

## Test
<zorunlu testler>

## Diğer seçenekler (operatör isterse)
<tablo: seçenek, neden seçilmedi>
```
