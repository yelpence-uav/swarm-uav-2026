"""Sürünün ortak uçuş ayarları — tek kaynak.

Hız değiştirmek için yalnızca DRON_TAVAN_MPS düzenlenir; merkez hızı
buradan türetilir, iki değer birbirinden kopamaz.

Kullanım:
    Python : from swarm_config import DRON_TAVAN_MPS, MERKEZ_HIZ_MPS
    Kabuk  : python3 -c "import swarm_config; print(swarm_config.MERKEZ_HIZ_MPS)"
"""

# Dronun çıkabileceği en yüksek hız (m/s) — formation_node'a max_speed_mps
# olarak verilir. Hızı değiştirmek için sadece bu satır.
DRON_TAVAN_MPS = 1.2

# Merkez, dron tavanının bu oranıyla ilerler. 1.0'ın ALTINDA olmalı:
# aradaki fark dronun açığı kapatma payıdır.
MERKEZ_ORANI = 0.8

# Merkezin seyir hızı (m/s) — türetilir, elle yazılmaz.
MERKEZ_HIZ_MPS = round(DRON_TAVAN_MPS * MERKEZ_ORANI, 3)


# --------------------------------------------------------------------------
# Video senaryosu — sahada değiştirilecek değerler
# --------------------------------------------------------------------------

# Üçgen alan yarıçapı (m). Alan küçükse düşür; 3 köşe otomatik ölçeklenir.
ALAN_YARICAP_M = 17.0

# Kalkış köşesi: sürü merkezinden bu kadar ileri (m).
KALKIS_MESAFE_M = 1.0

# Formasyon tipleri.
FRM_OKBASI, FRM_V, FRM_CIZGI = 1, 2, 3

# Köşe/görev tablosu:
#   (id, açı°, next, formasyon, spacing_m, bekleme_s, irtifa_m, roll°, pitch°)
#   açı None = kalkış köşesi | formasyon/irtifa/roll/pitch 0 = değişme yok
#   next 0 = son köşe, eve dön
KOSELER = [
    (1, None,  2, FRM_OKBASI, 8.0, 15.0,  0.0, 0.0, 0.0),
    (2, 90.0,  3, 0,          0.0, 15.0, 15.0, 0.0, 0.0),
    (3, 210.0, 4, FRM_V,      8.0, 15.0,  0.0, 0.0, 0.0),
    (4, 330.0, 0, 0,          0.0,  2.0,  0.0, 0.0, 0.0),
]

# Origin (yalnız SITL). Gerçek sahada first_fix otomatik okur.
ORIGIN_LAT = 41.0441
ORIGIN_LON = 29.0017
