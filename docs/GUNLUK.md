# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 29 Ağustos 2026, 21:54 — YKİ arayüzü sadeleştirildi, RPi sağlık paneli eklendi (SSH-only)

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

## 2026-08-29 21:54 — Osman + Claude (YKİ SADELEŞTİRME + RPi SAĞLIK PANELİ)

> **Uçuş yok, hava muhalefeti.** Gün boyu YKİ arayüzü elden geçti, yeni bir
> özellik eklendi (RPi paneli) ve Arch konteyneri yeniden kuruldu.

**Ne yapıldı — arayüz**

- **Başlık:** SÜRÜ sayacı, ARM ve GÖREV kutuları kaldırıldı; bağlantı durumu
  başlığın altına küçük rozet, RTK sağa yaslandı. **Açık tema tamamen
  kaldırıldı** (`useTheme` silindi, `index.html`'de `data-theme="dark"`
  SABİT — `Map.css`'in leaflet karo filtresi o attribute'a bağlı).
- **Bildirim paneli (YENİ):** başlıkta zil butonu + okunmamış sayacı. Tüm
  olaylar zaman damgalı, **şiddet ve drone süzgeçleriyle**. Kaynak zaten
  vardı (`useGunluk` → `yki_olaylar.jsonl`); eksik olan görünürlüktü.
- **Drone kartı:** renkli nokta gitti; UÇAMAZ/BOŞTA/YERDE rozetleri başlığa;
  LOG/Kontrol/RPi butonları alt şeride SOLA, konum+mesafe sağa (çubukla
  ayrık); puntolar 1-2 birim büyüdü (ham px yerine token'a bağlandı).
  **Kart içi log katmanı KALDIRILDI** — kart kısa, defter sığmıyordu; LOG
  artık bildirim panelini o drone'a süzülmüş açıyor. `DroneLog` silindi.
- **Kontrol paneli** sağ kenar çubuğundan **haritanın sağ altına** taşındı.
  Komut butonlarından ikonlar kalktı; onay metinleri "emin misin" yerine
  **operatörün bakması gereken şeyi** soruyor ("Pervanelerin çevresi boş mu?").
- Ayarlar paneli ve bildirim metinleri sade Türkçeye çevrildi (İngilizce
  kalıntılar, iç jargon, kısaltmalar). 29 olay etiketi + 5 uyarı mesajı.

**Ne yapıldı — RPi sağlık paneli (YENİ ÖZELLİK)**

🔴 **Veri MESH'TEN GEÇMİYOR — yalnız SSH.** Operatör kararı. Mesh 16 baytlık
paketler taşıyor ve görev telemetrisi için; teşhis verisi oraya konmuyor.
SSH yoksa `ssh_ok:false` döner, arayüz "bilinmiyor" gösterir — **değer
uydurulmaz.**

```
RPi butonu -> GET /api/rpi/{id} -> drone_bul.sh ylpXX 'bash -s' < rpi_durum.sh
           -> SSH -> Pi: sicaklik, throttle, CPU, bellek, disk, Wi-Fi, ROS
```

Ölçüm betiği **stdin'den** geçiyor: uçağa dağıtım GEREKMEZ, uçaklardaki kod
sürümünden bağımsız. Kimlik/IP `drone_bul.sh --tablo`'dan (ikinci tablo yok).
Eşikler ölçümden: Pi 5 boşta 56-64 °C → uyarı 70, kritik 80.

**Ne değişti**

- kod: `backend/api/rpi.py` (yeni), `deploy/rpi/teshis/rpi_durum.sh` (yeni),
  `components/BildirimPanel/` + `RpiPanel/` (yeni), 20 dosya düzenlendi,
  `DroneLog` + `useTheme` silindi
- **YKİ makinesi (Osman/Arch):** konteyner YENİDEN KURULDU —
  `arch-docker/Dockerfile`'a `openssh-client iproute2 iputils-ping net-tools
  nmap`, `yki_konteyner.sh`'e `~/.ssh` (ro) + drone önbelleği bağları ve
  `~/.cache` sahiplik düzeltmesi. (Bu dosyalar gitignore'da, kişisel.)
- uçakta: **hiçbir şey** — RPi özelliği uçak tarafına dokunmuyor

**Yarım kalan / tuzak**

- 🔴 **`kur_yki.sh` 6/8'de bir kez düştü** (pip PyPI zaman aşımı, hotspot).
  YKİ o sürede kapalı kaldı. `PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10` ile
  tekrar koşunca geçti. Dalgalı ağda yeniden kurulum riskli.
- ✅ **TUZAKLAR §2.11b burada da vuracaktı:** yerel `install/`'da silinmiş
  `ExecuteFormation`'dan 18 artık vardı; `kur`'un artımlı derlemesi aynı
  `undefined symbol` hatasını üretecekti. Derlemeden ÖNCE
  `build/`+`install/swarm_interfaces` silindi → temiz derleme 24,3 sn
  (artımlı ~5 sn sürer ve bozuk çıkar — süre farkı tek başına işaret).
- ⚠️ **ylp01'in RAM'i yarısı: 4049 MB** (diğer ikisi 8062). 24 Ağustos klon
  yeni Pi'ye yapılmıştı. Bugün sorun değil, görü zinciri açılınca üçü aynı
  davranmayabilir. `RPI_ESITLEME`'ye YAZILMADI (operatör: "şimdilik kalsın").
- ⚠️ `yelpence/yki:araclar` imajı 323 MB'lık hazır venv içeriyor — kurulum
  yine düşerse kurtarma yolu.

**Sıradaki adım**

- Görev 2 manevra modu: KARAR-11'deki 3 onay sorusu → test kodu.

**Uçakların bırakıldığı hâl**

- Üçü de açık, ağda, **disarm**, 11 düğüm, kod `04f3828 +KIRLI`. Uçaklara
  bugün hiç dokunulmadı.

---

## 2026-08-29 19:16 — Osman + Claude (REPO SADELEŞTİRMESİ + HIZLI DÖNGÜ · üç uçağa dağıtıldı)

> **Uçuş yok, yer işi.** Repo sadeleştirildi, uçuş öncesi kontroller
> gevşetildi, kod değişikliği döngüsü kısaltıldı. Üç uçağa dağıtıldı —
> **dağıtım sırasında üç uçak da düştü ve düzeltildi** (aşağıda).

**Ne yapıldı**

- **Ölü kod silindi** (`04f3828`): `basit_kacinma` (sürü zincirinde zaten
  ölüydü — yalnız `position_valid=True` setpoint'lerde çalışıyordu),
  `kinematic_fusion` (KARAR-01 ile elenmişti), `backend/test_tools`,
  `ExecuteFormation.action`, `px4_autopilot` submodule, `ca_benzetim.py`,
  `kacinma_testi.py`, `on_ucus_kontrol.py` (IP'leri/eşikleri bayattı),
  `pusula_olc.py`, `CA.md`, `WORKFLOW_BULGULAR.md`. **−11.655 satır.**
- **Belgeler kesildi:** 16.102 → 8.775 satır. Açılış ritüeli
  (DURUM+GUNLUK+YAPILACAKLAR) **5.866 → 768 satır**. Arşiv git'te
  (`git show 783afab:docs/<dosya>`).
- **Uçuş öncesi kontroller gevşetildi** (operatör kararı): `param_karsilastir`
  ve `titresim_olc` uçuş başınadan **saha gününe** indi · `uptime`/md5/düğüm
  sayısı `drone_bul.sh --durum` içinde birleşti · **QGC 14550 link kontrolü
  tamamen operatöre bırakıldı** · G2 yalnız *uçağı süren* düğümler için ·
  KARAR-02'nin ultracode hatırlatma görevi kaldırıldı.
- **Hızlı döngü araçları yazıldı ve SAHADA DOĞRULANDI:**
  `dagit.sh --paket <ad>` (yalnız değişen paketi derle) ve
  `baslat.sh --yalniz <düğüm>` (altyapıya dokunmadan tek düğüm yenile).

**🔴 Dağıtımda yaşanan arıza — kök neden bulundu, TUZAKLAR §2.11b**

`ExecuteFormation.action` silinince artımlı `colcon build` C kütüphanesini
yeniden üretti ama **Python typesupport uzantısını üretmedi**; eski uzantı
`undefined symbol: ...execute_formation...` verdi ve **on düğümün hepsi
açılışta öldü.** `colcon` "6 packages finished" diyerek BAŞARILI raporladı.
Ayırt edici işaret: artımlı **4,7 sn**, temiz derleme **1 dk 19 sn**.
Çözüm: üç uçakta `build/`+`install/swarm_interfaces` silinip temiz derlendi.

Ayrıca `colcon` silinen entry-point'leri kaldırmıyor — `basit_kacinma` ve
`kinematic_fusion` üç uçakta da **çalıştırılabilir** duruyordu; konteyner
içinden temizlendi (host kullanıcısı silemiyor, dosyalar root'a ait).

**Ne değişti**

- kod: `baslat.sh` (`--yalniz`, `basit_kacinma`/`fusion` blokları kalktı),
  `dagit.sh` (`--paket`), `drone_bul.sh` (`--durum`'a md5 + düğüm sayısı)
- uçakta: üçü de **`04f3828 +KIRLI`**, konteynerler yeniden başlatıldı,
  `swarm_interfaces` temiz derlendi, ölü düğüm artıkları silindi
- belge: CLAUDE, README, DURUM, PLAN, KARARLAR, TUZAKLAR (§2.11b yeni),
  RPI_ESITLEME (§3'e A20/A21/A22), YAPILACAKLAR, GUNLUK

**Doğrulanan hâl (üç uçakta da aynı)**

```
baslat.sh md5 : depo ile AYNI      ros2 dugum : 79 (11'i bizim)
mesh komsu    : 10,7-11,9 Hz       CA         : avoid=0, saglikli
telemetri     : bagli, DISARM, 31-32 uydu, Auto.Loiter
--yalniz ca   : ca PID 270->1249 (12 sn) · mavros/px4/esp/fsm/formasyon PID DEGISMEDI
```

**Yarım kalan / tuzak**

- **RTK yok (`fix=3`)** — baz istasyonu RTCM yayınlamıyor. Uçuştan önce ayrı iş.
- **ylp02 diski %79 dolu** (5,9 GB boş); ylp00 %42, ylp01 %36.
- ylp01'in SSH host anahtarı `known_hosts`'a eklendi (24 Ağu klonlamasında
  yeniden üretilmişti; üç anahtarın da farklı olduğu doğrulandı).
- `baslat.sh` **644'tür, çalıştırılabilir değil** — çağrı `bash /ws/baslat.sh`.
  `docker exec -d drone1 /ws/baslat.sh` "permission denied" verir.
- ⚠️ `--yalniz` **uçuş sırasında kullanılmaz** — düğüm saniyelerce yok olur.

**Sıradaki adım**

- Görev 2 manevra modu: KARAR-11'deki **3 onay sorusu** → test kodu.

**Uçakların bırakıldığı hâl**

- Üçü de açık, ağda, **disarm**, Auto.Loiter, 11 düğüm ayakta.
  `suru_dugumleri = origin consensus fsm formasyon ca`, `gozlem` YOK
  (formasyon-sürer mod), `kacinma` YOK.

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
