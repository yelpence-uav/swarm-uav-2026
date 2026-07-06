# QRCoordinates.msg — yarışma öncesi paylaşılan QR konum tablosu.
#
# Şartname: tüm QR kodlarının konumları yarışma öncesi paylaşılır. QR kodu
# yalnızca "next_qr" numarasını verir; ilgili numaranın KONUMU bu tablodan
# çözülür. Operatör YKİ'den girer; GCS /swarm/internal/mission/qr_coords'a
# yayınlar; proxy (sim) / ESP32 mesh (saha) /swarm/public/mission/qr_coords'a
# iletir; her drone (mission_fsm / path_planning) tabloyu saklar.
#
# QoS: RELIABLE + TRANSIENT_LOCAL, depth=1 (latched — SwarmOrigin gibi;
# sonradan katılan/yeniden başlayan drone son tabloyu otomatik alır).
#
# Mesh boyutu: 6 QR × (lat_1e7 4B + lon_1e7 4B + alt_dm 2B) = 60 byte,
# ESP-NOW tek çerçeve bütçesi (~198B) altında — chunk gerekmez.

builtin_interfaces/Time stamp

# Paralel diziler — hepsi aynı uzunlukta (tipik 6: QR 1..6).
uint8[]   qr_ids        # QR numaraları, örn. [1, 2, 3, 4, 5, 6]
float64[] lat_deg       # her QR'ın enlemi (WGS84 derece)
float64[] lon_deg       # her QR'ın boylamı (WGS84 derece)
float32[] alt_m         # her QR'ın irtifası (metre, AGL)
