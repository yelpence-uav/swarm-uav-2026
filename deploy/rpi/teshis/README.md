# Saha teşhis betikleri — uçaktan kurtarıldı

**Son güncelleme:** 18 Ağustos 2026, 19:30

Bu 21 betik sahada, sorun ararken yazıldı ve **yalnız ylp00'ın SD kartında**
duruyordu. Versiyonsuz, yedeksiz, tek kopya. Listeleri `COP_TEMIZLIK.md`'deydi,
o belge 16 Ağustos'ta silinince hangi betikler olduğu **hiçbir yerde kalmadı**
(`YAPILACAKLAR.md` P2.5). 18 Ağustos'ta `rsync` ile geri çekilip buraya alındı.

Değerleri şurada: her biri **bir hipotezi test etmek için** yazılmış ve
başlığında neyin neden denendiği yazılı. Yani bunlar yalnız araç değil, aynı
zamanda o günün teşhis kaydı. Silme.

> Parola/anahtar/sabit IP taraması yapıldı, **temiz** — o yüzden depoya
> girebildiler.

---

## 🔴 ÖNCE BUNU OKU — bazıları uçağı ARM EDER

Betikler **konteyner içinde** koşar ve bir kısmı gerçekten motor döndürür.
Kategoriler:

### ⛔ Uçağı ARM eder / motor döndürür — pervanesiz ve pilot başında koşulur

| Betik | Ne yapar |
|-------|----------|
| `arm_dene.sh` | Gerçekten arm edip lider seçimini sıfır sahte girdiyle test eder |
| `arm_secim.sh` | Tamamen gerçek lider seçimi — hiç sahte `AgentStatus` yok |
| `gorev_baslat.sh` | Tam zincir testi (başlığında "pervaneler çıkarık, kullanıcı onaylı" yazıyor) |
| `tam_kalkis.sh` | `MISSION_STARTED → ARMING → ARMED → TAKEOFF` tam akışı |
| `tam_zincir.sh` | Aynısı, `pilot_override_active` engeli kaldırılarak |
| `offboard_armed.sh` | ARMED durumda OFFBOARD denemesi |
| `offboard_once.sh` | Önce OFFBOARD sonra ARM sırasının doğrulaması |
| `offboard_deney.sh` | `px4_bridge` offboard akış hipotezi |

### ⚠️ Sisteme SAHTE veri enjekte eder — teşhis dışında kullanma

| Betik | Ne yapar |
|-------|----------|
| `durum_enjekte.sh` | Sahte `AgentStatus` basar (consensus'un `ELIGIBLE_STATES`'ini aşmak için) |
| `form_yayinla.sh` | Sahte lider bildirir + formasyon hedefi basar |
| `seq_deney.sh` | `consensus_node`'un eskimiş-mesaj filtresini sınar |
| `inc_kanit.sh` | Incarnation/seq kaydı üzerine deney |

### ✅ Salt okuma / ölçüm — güvenli

| Betik | Ne yapar |
|-------|----------|
| `form_izle.sh` | `/swarm/public/formation/target`'ı izler, `/tmp/form_izle.txt`'e yazar |
| `form_sayac.sh` | `esp32_bridge` tanı sayaçlarını okur (log'a değil topic'e gidiyor) |
| `gps_ornek.sh` | GPS ham durumu tek satır (fix_type / uydu / h_acc) |
| `gps_led_teshis.sh` | Here4 LED farkını DroneCAN tarafında arar |
| `rtk_zincir.sh` | RTCM zincirinin drone tarafını ölçer (mesh → bridge → MAVROS) |
| `rtk_param.sh` | RTK parametreleri (`oku` \| `yaz`) |
| `prearm_teshis.sh` | PX4 1.16'nın arm reddini MAVLink Events'ten çözer |
| `inc_dogrula.sh` | Bir düzeltmenin uçtan uca kanıtı |
| `consensus_baslat.sh` | `consensus_node`'u `baslat.sh` ile aynı komutla başlatır |

---

## `form_yayinla.sh` — bunların en değerlisi

`formation_node`'u **uçakta gerçek komutla** besleyen tek araç. Lideri
`/swarm/internal/election/result`'a bildirip formasyon hedefini
`/swarm/internal/formation/target`'a basıyor; `esp32_bridge` loopback ile
yerel `/swarm/public/formation/target`'a koyuyor.

**Neden önemli:** komut **uçakta doğduğu** için yer→hava firmware whitelist'ine
takılmıyor (0x11-0x15 RX BASE'de bilerek kapalı — `YAPILACAKLAR` P0.10).
18 Ağustos'ta `formation_node`'un ilk gerçek ölçümü bununla yapıldı:

```
komut : merkez 12.3 / -45.6 / -8.0   heading 137.5   max_speed 3.5
cikti : x=12.2990 y=-45.6019 z=-8.000   (merkeze 0.9 mm)
        |v| = 3.500 m/s (tam tavan)     position_valid: FALSE
```

İçinde belgelere geçmiş bir QoS tuzağı da yazılı (`TUZAKLAR.md` §2.9):
`/swarm/internal/election/result` **TRANSIENT_LOCAL** ister, `ros2 topic pub`
varsayılanı VOLATILE — bayraksız yayın **hiç ulaşmaz ve hata da vermez**.

---

## Kullanım

Betikler konteyner içinde koşar, kendi ROS ortamlarını kendileri kaynaklar:

```bash
./deploy/yki/drone_bul.sh ylp00 'docker exec drone1 bash /ws/form_izle.sh 1 30'
```

⚠️ Şu an uçaktaki kopyalar `~/yelpence_ws/` altında (yani konteynerde `/ws/`).
`dagit.sh` bunları **dağıtmıyor** — depoya alındılar ama uçağa geri yazılmadı.
Uçaktaki kopyalarla depodaki kopyalar ayrışabilir; bir betiği değiştirirsen
ikisini de güncelle ya da dağıtım yoluna ekle.

## Kurtarılmayanlar

| Dosya | Neden alınmadı |
|-------|----------------|
| `core.50` (**353 MB**) | Core dump. Disk 14 Ağustos'ta dolmuştu — **silinmeli** |
| `bozuk_223218/` | 31 Temmuz'a ait 303 KB'lık bozuk `.mcap` kaydı |
| `baslat.sh.yedek_20260802_184714`, `..._20260814_212708` | Eski `baslat.sh` yedekleri; güncel sürüm depoda |
| `baslat.sh`, `run_drone.sh`, `gps_saat.py`, `mesaj_hizlari.py`, `Dockerfile` | Zaten `deploy/rpi/` altında |

## Kayıt çözümleme betikleri (20 Ağustos 2026)

Uçuş kayıtlarından navigasyon kaymasını çıkarır. **Uçakta, konteyner içinde**
koşarlar; `setpoint_raw/local` (nereye dedik) ile `local_position/pose`
(nereye gitti) farkını çözerler.

```bash
./deploy/yki/drone_bul.sh ylp00 \
  'docker exec -i drone1 bash -lc "source /opt/ros/jazzy/setup.bash && \
   source /ws/install/setup.bash && python3 - /ws/kayit/<DIZIN> 1"' \
  < deploy/rpi/teshis/kayma_coz.py
```

| Betik | Ne verir |
|-------|----------|
| `kayma_coz.py` | Bacak bacak: **kalıcı kayma · tepe geçici hata · oturma süresi** |
| `varis_izi.py` | Bacak sonundaki **aşım** ve düzelme süresi (satır satır iz) |
| `kalkis_izi.py` | Kalkış fazının izi — çapa/komut sıçramaları burada görünür |

⚠️ **İki tuzak (20 Ağustos'ta ikisine de düşüldü):**
1. Kayıt **hâlâ yazılıyorsa** `metadata.yaml` kapanmamıştır ve dizin
   açılamaz (`Could not open ... read failed`). Betikler bu yüzden parça
   `.mcap` dosyalarını **tek tek** okuyor — `ros2 bag reindex` gerekmiyor.
2. Bu yerel çerçevede **yer seviyesi z ≈ 1.17 m**, sıfır değil. "z > 1"
   ölçütü yerdeki uçağı da havada sanır; kalkış eşiği en az 4 m olmalı.
