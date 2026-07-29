# GuidedCommand.msg — YKİ'den tek drone'a doğrudan (guided) uçuş komutu.
#
# Otonom görev (TriggerMission) DIŞINDA, operatörün tek drone'u elle kontrol
# etmesi için: arm / disarm / takeoff / nokta-git / RTL / land. Akış:
#   backend -> /swarm/internal/guided/command
#     -> base esp32_bridge  (TIP_KOMUT[guided] / TIP_GOTO olarak mesh'e)
#       -> drone esp32_bridge (px4_bridge'e String komut + AgentSetpoint)
#         -> px4_bridge -> MavrosCommandSender -> FCU
#
# Hedef konum yerel NED (metre), paylaşılan SwarmOrigin'e göre. Harita
# tıklaması (lat/lon) NED'e YKİ'de çevrilir; manuel x/y/z zaten NED.
#
# QoS: RELIABLE (komut kaybolmamalı).

builtin_interfaces/Time stamp

uint8 agent_id            # hedef drone (1..N). 0 = tümü (broadcast).

# Eylem
uint8 ACTION_ARM=1
uint8 ACTION_DISARM=2
uint8 ACTION_TAKEOFF=3
uint8 ACTION_GOTO=4
uint8 ACTION_RTL=5
uint8 ACTION_LAND=6
uint8 action

# ACTION_TAKEOFF: hedef irtifa (metre, yerden yukarı). 0 -> px4_bridge default (10 m).
float32 altitude_m

# ACTION_GOTO: hedef konum, yerel NED (metre), SwarmOrigin'e göre.
# z NED aşağı-pozitif; irtifa = -z. Yalnızca ACTION_GOTO'da kullanılır.
float32 x
float32 y
float32 z
float32 heading_deg       # hedef yön (derece). heading_valid=False -> yaw serbest.
bool    heading_valid
