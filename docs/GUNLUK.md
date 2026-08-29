# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 29 Ağustos 2026, 17:50 — defter son 2 kayda indirildi (öncesi git'te, `783afab`)

Tek bilgisayar, sırayla çalışıyoruz. Biri kalkıp diğeri oturduğunda **hem
kişi hem Claude** nerede kalındığını buradan anlar.

**En yeni kayıt en üstte.** Her oturumun sonunda yeni bir kayıt ekle —
atlanırsa sistem çöker, çünkü sohbet geçmişi sonraki kişiye geçmiyor.

Claude'a **"oturumu kapat"** dersen bu kaydı o yazar.

---

## Şablon (kopyala, en üste yapıştır)

```markdown
## YYYY-AA-GG SS:DD — <isim>

**Ne yapıldı**
- (somut, ölçülmüş sonuçlarla; "denedik" değil "şu çıktı")

**Ne değişti**
- kod: `dosya:satır` — ne, neden
- uçakta: hangi bayrak/parametre/dosya değişti (SONRAKİ KİŞİ ÖYLE BULACAK)
- belge: hangi md güncellendi

**Yarım kalan / tuzak**
- (bir sonraki kişinin bilmediğinde zaman kaybedeceği her şey)

**Sıradaki adım**
- (tek cümle, net; YAPILACAKLAR.md'deki madde numarasıyla)

**Uçakların bırakıldığı hâl**
- ylp00: (kill switch? pil? nerede? konteyner ayakta mı?)
- ylp02:
```

---

## 2026-08-28 21:40 — Berk + Claude (GÖREV 2 MANEVRA MODU: şartname incelendi, 4 boşluk kapatıldı, test PLANLANDI — yarına)

**Ne yapıldı**

- Şartname 5.1/5.2 tam okundu (pdf → metin, `pdfenv` scratchpad'de).
  Üç ayrı "pitch/roll/yaw" bağlamı ayrıştırıldı: Görev 1 QR-eğim /
  Görev 2 hareket modu (öteleme) / **Görev 2 MANEVRA modu** (merkez
  sabit eğim+rotasyon — test edilecek olan). Rapor sohbette; özet ve
  puan/ceza notları **KARAR-11**'de.
- Zincir HAZIR ÇIKTI: mode_manager (605) + joystick_interpreter (534,
  FlySky FS-i6X eşlemeli) + köprü TIP_KOMUT iki yönde. Ama hiç koşmamış
  ve 4 boşluğu vardı → **kapatıldı, commit `f6f8498`** (KARAR-11):
  joystick anahtarı+remap · çıkış /raw'a + formasyon susturması
  (3 sn bayat-bırakma) · eğim matematiği apply_tilt'e (merkez-kayması
  ve ters roll işareti düzeldi, 2 regresyon testi) · MOD_* tek kaynak
  (yaw 25°/s = PX4'ten türetme). Testler 11/11.
- **Manevra testi planlandı** (tek buton, SSH'siz, kumandasız sürücü) ve
  plan sırasında koddan **2 yeni engel** çıktı (formation_change ofset
  güncellemiyor → ışınlanma; FSM READY'ye ulaşamıyor) — KARAR-11'de.

**Ne değişti**

- kod: `f6f8498` (repo'da; ⚠️ **uçaklara DAĞITILMADI** — şarjdalar)
- uçakta: hiçbir şey (19:50 kaydındaki hâl geçerli)
- belge: KARARLAR (KARAR-11 + test planı), YAPILACAKLAR (P1.31-33)

**Yarım kalan / tuzak**

- Manevra testi kodu YAZILMADI — operatör "yarına kalsın" dedi.
  🔴 Yarın İLK İŞ: KARAR-11'deki **3 onay sorusu** (sürücü uçağı? /
  genlikler ±10°, yaw 12,5°/s? / iniş slot üstüne?) → sonra kod.
- mode_manager HOLD'da 5 sn komutsuz kalınca kendiliğinden LANDING'e
  geçiyor (bugün etkisiz ama sürücü tasarımını belirledi — yayın sonda
  kesilmeyecek).

**Sıradaki adım**

- Onay soruları → manevra test kodu (KARAR-11 merdiveni 1) → uçaklar
  açılınca dağıtım + G0 (P1.31).

**Uçakların bırakıldığı hâl**

- Üçü de kapalı, piller şarjda. Kod `403b99f` (f6f8498 dağıtılmadı),
  `sekans` anahtarı YOK, gozlem YOK.

---

## 2026-08-28 19:50 — Berk + Claude (FORMASYON GEÇİŞ TESTİ UÇTU ✅ — sekans UÇAKTA, YKİ butonuyla)

> **Üç uçak, tek uçuş, tek buton.** Çizgi→ok başı→V→çizgi→EVE sekansı
> tamamen uçakta koştu (yeni `formasyon_sekans` düğümü, KARAR-10); YKİ
> yalnız arm+takeoff verdi, izledi, sonda kalkış noktalarına indirdi.
> Operatör: *"çalıştı, gayet de iyiydi."*

**Ne yapıldı (uçuş, ölçülmüş)**

- Sekans logu (ylp00, lider d2): merkez (+6.5,-3.2), heading 310.6°
  (dizilimden otomatik), atama [2,1,3] — çizgi t0 → ok t0+26 → V t0+51 →
  çizgi t0+76 → EVE t0+97 → **BITTI t0+123 s** (plan 120).
- **Kaçınma hiç tetiklenmedi: `avoid=0` üç uçakta** — 7 m aralıkta
  geçişler nominal kaldı (kuru öngörüsü: en dar an 4,95 m > d0 4,0).
- İzleme: en yakın çift uçuş boyunca ~8,0 m; irtifa ~9,0-9,2 m
  (hedef 8 + bilinen ~1 m EKF/origin farkı, 26 Ağu ile aynı).
- Kayıtlar dizüstünde: **`~/yelpence-kayitlar/20260828_formasyon_gecis/`**
  (uçak başına rosbag ~34 MB + uçuş açılışının tüm günlükleri + YKİ
  kosucu çıktısı + haritalar).

**Gün içinde G0'ın yakaladığı 4 gerçek hata** (uçuşa çıkmadan düzeltildi):
kopru'nun lider-kapısı baypası → kapı üreticiye; iç veriyolu RELIABLE;
YAML param tip tuzağı ×2 → string+dynamic_typing; AgentStatus yayıncısı
agent_fsm'miş (FSM'siz G0 imkânsız). Kuru test de gerçek yerleşimde iki
atama kuralını eledi → çizgi dönüş koridoru + ilk-faz-Macar sabit sahiplik.

**Ne değişti**

- kod: `formasyon_sekans_cekirdek/node` (yeni), `ucus_ayarlari` SEKANS_*,
  `gorev_kanit_ucus` formasyon_gecis senaryosu + `harita_yaz_sekans`
  (okunaklı harita), `baslat.sh` `sekans` anahtarı, kosucu+KosucuPanel
  GEÇİCİ buton. Commit'ler `36531c4..403b99f`, uçaklarda `403b99f`.
- uçakta: **`sekans` anahtarı test sonrası SİLİNDİ** (`suru_dugumleri` =
  `origin consensus fsm formasyon ca` — normal düzen); `/ws/gozlem` YOK
  (formasyon-sürer mod). Konteynerler restart EDİLMEDİ — bir sonraki
  açılışta sekanssız kalkacaklar. `ucus_ayarlari.env` yenilendi (SEKANS_*).
- belge: KARARLAR (KARAR-10), YAPILACAKLAR, DURUM.

**Yarım kalan / tuzak**

- ⚠️ ros2 `-p x:=90` tam sayıyı INTEGER yapar, double declare düğümü
  ÖLDÜRÜR — iki kez yaşandı; yeni düğüm yazan `dynamic_typing` kullansın
  (TUZAKLAR'a aday).
- ⚠️ ylp01 paralel dagit'te ilk denemede düşüyor, tekli geçiyor (Wi-Fi).
- İrtifa ~1 m yüksek oturuyor (EKF/origin) — bilinen, analiz P0 HOME ile.
- 🔴 HOME kayması P0 HÂLÂ AÇIK (bu uçuş RTL kullanmadı, EVE fazı çözdü).

**Sıradaki adım**

- Uçuş kaydı analizi (isteğe bağlı): slot oturma hataları + faz geçiş
  temizliği mcap'ten. Aparat, mission1 sahaya alınınca silinecek (KARAR-10).

**Uçakların bırakıldığı hâl**

- Üçü de uçuştan sonra kalkış noktalarında, disarm; operatör şarj için
  kapatıyor. `sekans` anahtarı YOK, gozlem YOK, kod `403b99f`.

---
## Daha eski kayıtlar

21 oturum kaydı (2 → 28 Ağustos) 29 Ağustos 2026'da bu dosyadan çıkarıldı.
Silinmediler — git'te tam hâlleriyle duruyorlar:

```bash
git show 783afab:docs/GUNLUK.md          # kesimden önceki tam defter
git log --follow -- docs/GUNLUK.md       # dosyanın bütün geçmişi
```

Sebep: finale 8 gün kala açılış ritüeli 5.866 satırdı; devir teslim için
gereken son iki kayıt, geri kalanı arşiv.
