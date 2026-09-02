# Yer testleri — 2 Eylül 2026

Bu betikler uçuş **gerektirmez**; her biri o gece sahada bulunan bir arızayı
ve düzeltmesini kilitler. Bir daha aynı hatayı yapmamak için burada.

| betik | neyi kilitliyor |
|---|---|
| `yer_testi_kalkis_gecisi.py` | `_from_takeoff` görev node'unun kalkış sinyalini okuyor mu; sağlık kapıları hâlâ kesiyor mu |
| `yer_testi_pil_kesmesi.py` | Pil **ölçülüyor ve uyarıyor** ama kesme kapalıyken FAILSAFE'e düşürmüyor; diğer arızalar hâlâ kesiyor |
| `yer_testi_rota_bekleme.py` | Hedefsiz bekleme süresi ayardan geliyor; ayar 0 ise kod varsayılanı (30 sn) korunuyor |
| `yer_testi_orkestrator.py` | **Hiçbir görev durumu boş komut üretmiyor** (hedefli/hedefsiz 8 kombinasyon) |
| `yer_testi_qr_protokol.py` | QR tablosu paketleyici/çözücü gidiş-dönüşü; paket kaybında tablo tamamlanMAması; sınır değerlerin sessizce kırpılmaması |
| `formasyon_hesapla.py` | Gerçek GPS ile formasyon slotlarını ve **iniş noktalarını** hesaplar (uçuş öncesi harita için) |

## Çalıştırma

```bash
source /opt/ros/jazzy/setup.bash && source install/setup.bash
PYTHONPATH=src/swarm_state_machine python3 deploy/rpi/teshis/yer_testi_kalkis_gecisi.py
PYTHONPATH=src/swarm_core:src/swarm_missions python3 deploy/rpi/teshis/yer_testi_orkestrator.py
PYTHONPATH=src/swarm_control python3 deploy/rpi/teshis/yer_testi_qr_protokol.py
```

⚠️ `formasyon_hesapla.py` içindeki GPS koordinatları 2 Eylül'ün konumları —
kullanmadan önce güncel telemetriden yenile.
