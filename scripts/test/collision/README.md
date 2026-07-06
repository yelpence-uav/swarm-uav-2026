# Çarpışma Önleme (APF) Test Akışı

Üç kademe: önce ucuz/izole test geçmeden pahalı/entegre teste geçme.

## Kademe 1 — Birim testler (saniyeler, ROS gerekmez)

APF matematiğini doğrular (itici yön, clamp'ler, deadlock tespiti).

```bash
source install/setup.bash
python3 -m pytest src/swarm_core/test/test_apf.py -v   # 27 passed beklenir
```

## Kademe 2 — Offline simülasyon (saniyeler, ROS gerekmez)

25 senaryonun tamamı. **Çarpışma + formasyon bozulması + osilasyon** ölçer.

```bash
python3 scripts/test/collision/apf_sim.py
```

Çıktı: kategori bazında % başarı tablosu + her senaryo `min(m)/slot_dev/salınım`.
CSV → `analysis/collision_sim/` (jüri grafiği için `plot_min_distance.py`).

## Kademe 3 — SITL (dakikalar, gerçek node + PX4)

**Workflow: kurulum otomatik, çarpışma senaryosu MANUEL.**
Drone'lar kalkışta aynı anda aynı irtifaya gelmediği için, senaryoyu sen
hepsinin aynı yüksekliğe geldiğini Gazebo'da görünce tetiklersin.

**İzole test:** her senaryo bağımsız — her test için `1) setup → 2) senaryo →
3) report` döngüsünü baştan çalıştır (her seferinde aynı irtifa beklenir,
ama testler birbirini etkilemez).

### 1) Kurulum (otomatik — kalkış + formasyon)

```bash
bash scripts/test/collision/setup_only.sh
```

Yapar: stack + GPS fix + safety_monitor (emniyet 1.5 m, osilasyon takibi) +
kalkış + form-up [1,2,3] @ −15 m. Sonra **DURUR**, senaryoyu beklemez.

### 2) Senaryo (MANUEL — aynı irtifaya gelince SEN başlat)

4 aşamalı plana göre, izole'den entegre'ye:

| Aşama | Komut | Ne test eder |
|-------|-------|--------------|
| **1. Baseline** | (setup_only çıktısı) | formasyon sabit + irtifa kararlı mı (`irtifaΔ`) |
| **2. Kademeli yaklaşma** | `bash approach_test.sh cizgi` | spacing 6→3.0 adımlı → CA yumuşak girer mi, **osilasyon** (min spacing ≥ hard_radius=2m) |
| **2b. Yaklaşma duvarı** | `bash converge_test.sh` | hepsi merkeze ANINDA → şok girdi, osilasyon stresi |
| **4. Swap (worst-case)** | `bash do_swap.sh` | koordinasyonsuz kafa-kafaya + yatayda **irtifa kaybı** |
| Swap (parametrik) | `bash swap_conflict.sh cizgi 6` | v/cizgi/okbasi + spacing seçilir |

Aşama 3 (esnek bağ + feedforward) ayrı senaryo değil — kodda hazır (SVT soft
tether + slew ani-sıçrama önleme + setpoint hız feedforward). Hız pürüzsüzlüğü
yukarıdaki senaryolarda `salınım` (osilasyon) metriğiyle dolaylı görülür.

Canlı izleme: `tail -f /tmp/sm_manual.log`
(satırlar: `min=... | dek min=... | ihlal=... | salınım=... | irtifaΔ=...`)

### 3) Rapor (senaryo bitince — özet + jüri grafiği)

```bash
bash scripts/test/collision/report.sh
```

Yapar: yayıncıyı durdurur → monitor'ü düzgün kapatır (özet + events CSV) →
jüri grafiğini üretir (`analysis/collision_sitl/collision_run.png`).

Özette: min mesafe, ihlal tick, uyarı süresi %, kritik anlar, **salınım sayısı**
→ `TEMİZ ✓ / İHLAL ✗`.

## Başarı kriterleri (jüri)

- `min ikili mesafe ≥ 1.5 m` (merkez-merkez) — çarpışma yok
- `salınım toplam ≈ 0` — osilasyon yok (şartname −10 p)
- `max irtifa farkı` küçük/kararlı — yatay manevrada irtifa kaybı yok (Aşama 4)
- formasyon senaryo sonrası toparlanır (slot_dev tavanına yapışıp kalmaz)

## Dosyalar

| Dosya | Rol |
|-------|-----|
| `setup_only.sh` | kurulum (kalkış + formasyon), DURUR |
| `do_swap.sh` | saf swap tetiği (manuel) |
| `swap_conflict.sh` | parametrik swap (formasyon/spacing seçimli) |
| `converge_test.sh` | yaklaşma duvarı (osilasyon testi) |
| `report.sh` | monitor kapat + özet + jüri grafiği |
| `safety_monitor.py` | ölçüm node'u (min mesafe + osilasyon), KOMUT VERMEZ |
| `apf_sim.py` | offline 25-senaryo simülasyonu |
| `plot_min_distance.py` | min-mesafe–zaman grafiği (sim + SITL CSV) |
| `scenarios.py` | senaryo tanımları (tek kaynak) |
