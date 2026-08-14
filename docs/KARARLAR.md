# KARARLAR — verilmiş ama henüz uygulanmamış kararlar

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
