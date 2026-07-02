# ZoneMap.msg
# Accumulated/persistent map of detected red/blue landing(detach) zones.
# Producer: swarm_perception/vision_node (ZoneMapCore biriktirir).
# Consumer: precision_landing (hedef rengin en yakın bölgesini seçer), GCS/log.
#
# NEDEN: LandingZoneDetection.msg ANLIK + dron-göreli tespittir; bir kare sonra
# bölge görüş alanından çıkınca "unutulur". Şartname ise bölge konumlarının
# transit sırasında (QR icrası esnasında) tespit edilip KAYDEDİLMESİNİ ister
# (ayrı tarama yasak). ZoneMap bu kalıcı hafızadır: koordinatlar GLOBAL NED.
# Topic: /swarm/perception/zone_map   QoS: RELIABLE, ~2-3 Hz (yavaş değişir).

builtin_interfaces/Time stamp

# Zone colors
uint8 COLOR_UNKNOWN=0
uint8 COLOR_RED=1
uint8 COLOR_BLUE=2

# Bu haritayı yayınlayan ajan (her dron kendi gözlemini biriktirir).
uint8 publisher_agent_id

# Biriktirilmiş benzersiz bölge sayısı (tekrar gözlemler kümelenmiştir).
uint8 zone_count

# Per-zone paralel diziler. Hepsi zone_count uzunluğunda olmalı.
uint8[]   zone_colors          # COLOR_* enum
float32[] zone_x               # GLOBAL NED x, metre
float32[] zone_y               # GLOBAL NED y, metre
float32[] zone_z               # GLOBAL NED z, metre (zemin ~0.0)
uint32[]  observation_count    # bu bölge kaç karede görüldü (kümeleme)
float32[] zone_confidence      # [0.0, 1.0] biriken güven
