# MissionTarget.msg — mission_fsm'in çözdüğü "gidilecek sonraki QR" hedefi.
#
# mission_fsm yayınlar (/swarm/internal/mission/next_target); proxy (sim) /
# ESP mesh (saha) /swarm/public/mission/next_target'a iletir; mission1_dynamic_swarm
# dinleyip navigasyonu yapar (GPS lat/lon -> yerel NED çevirisi mission1'de).
#
# "Hangi QR sıradaki" kararı YALNIZCA mission_fsm'de verilir (tek doğru kaynak);
# mission1 kendi lookup'ını yapmaz, buradan gelen hedefe gider.
#
# QoS: RELIABLE (hedef her QR'da değişir; kaybolmamalı).

builtin_interfaces/Time stamp

uint32  qr_id       # gidilecek QR numarası (next_qr ya da görev başında start_qr)
bool    valid       # False -> konum tabloda YOK (route_unknown); mission1 navige etmez
float64 lat_deg     # hedef QR enlemi (WGS84 derece)
float64 lon_deg     # hedef QR boylamı (WGS84 derece)
