# NeighborInfo.msg
# Relative information between two UAVs.
# Used by inter_drone_comm, consensus, and collision_avoidance.
# Coordinate convention: relative values in local NED frame.

builtin_interfaces/Time stamp

uint8 self_agent_id
uint8 neighbor_agent_id

# Neighbor FSM state — mirrors AgentStatus STATE_* enum.
# Collision avoidance (ORCA/APF) uses this to skip avoidance computation
# for neighbors in DETACHED, PRECISION_LANDING, LANDED, or FAILSAFE states.
# 0 = UNKNOWN (link just established; treat as active until state is known).
uint8 neighbor_state

bool link_active

# Veri yaşı — GERÇEK DONANIM İÇİN KRİTİK
# Xbee/ESP mesh'te paket gecikmesi 50-300ms arasında değişir.
# ORCA velocity obstacle hesabı eski konumla çalışırsa yanlış kaçınma üretir.
# data_age_ms = şimdiki zaman - komşudan son alınan paketin timestamp'i (ms cinsinden)
# Collision avoidance: data_age_ms > 500ms ise bu komşuyu kaçınma hesabından çıkar.
uint32 data_age_ms

float32 distance_m

float32 relative_x
float32 relative_y
float32 relative_z

float32 relative_vx
float32 relative_vy
float32 relative_vz

float32 rssi
float32 packet_loss_percent

string link_type
