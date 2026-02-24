# Yelpence F450 – Bileşen Ağırlıkları

> SDF dosyasındaki (`model.sdf`) tüm custom link'lerin ağırlık bilgileri.
> X3 UAV base frame (gövde + 4 motor + pervane) Gazebo Fuel'den yüklenir, bu listede yer almaz.

## Bileşen Listesi

| # | Bileşen | Link Adı | SDF Ağırlık (g) | Kaynak |
|---|---------|----------|----------------|--------|
| 1 | RPLidar A1 | `lidar_link` | 170 | Resmi spec |
| 2 | RealSense D435i | `camera_link` | 72 | Intel spec |
| 3 | Here3 GPS | `gps_link` | 50 | Holybro spec |
| 4 | Uçuş Kontrol Birimi (FCU) | `fc_link` | 75 | Generic FC |
| 5 | Batarya – 4S LiPo 5200mAh | `battery_link` | 490 | THK spec |
| 6 | İniş takımı – Sol skid tüpü | `skid_left_link` | 17 | F450 landing kit |
| 7 | İniş takımı – Sağ skid tüpü | `skid_right_link` | 17 | F450 landing kit |
| 8 | İniş takımı – Bağlantı kolu ÖN-SOL | `strut_fl_link` | 9 | F450 landing kit |
| 9 | İniş takımı – Bağlantı kolu ÖN-SAĞ | `strut_fr_link` | 9 | F450 landing kit |
| 10 | İniş takımı – Bağlantı kolu ARKA-SOL | `strut_bl_link` | 9 | F450 landing kit |
| 11 | İniş takımı – Bağlantı kolu ARKA-SAĞ | `strut_br_link` | 9 | F450 landing kit |
| 12 | Telemetri anten | `telemetry_link` | 30 | SiK 915 MHz |
| 13 | TF-Luna Lidar (aşağı) | `tf_luna_link` | 5 | Benewake spec |
| 14 | TOF400C – Ön | `tof_front_link` | 5 | VL53L1X board |
| 15 | TOF400C – Arka | `tof_back_link` | 5 | VL53L1X board |
| 16 | TOF400C – Sağ | `tof_right_link` | 5 | VL53L1X board |
| 17 | TOF400C – Sol | `tof_left_link` | 5 | VL53L1X board |

## Özet

| Kategori | Toplam (g) |
|---|---|
| Sensörler (LiDAR, kamera, GPS, IMU, TOF×4, TF-Luna) | 342 |
| Batarya | 490 |
| İniş takımı (2 skid + 4 strut) | 70 |
| Telemetri | 30 |
| **Custom bileşenler toplamı** | **932** |
| X3 base frame (tahmini, Fuel modeli) | ~560 |
| **Genel toplam (tahminî)** | **~1492** |
