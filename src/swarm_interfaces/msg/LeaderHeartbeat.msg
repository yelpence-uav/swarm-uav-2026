# LeaderHeartbeat.msg
# Consensus katmanı sağlık sinyali — yalnızca aktif lider yayınlar.
#
# NEDEN AgentStatus YETMEZ:
# AgentStatus → agent_fsm_node / px4_interface tarafından yayınlanır (uçuş telemetrisi).
# LeaderHeartbeat → consensus_fsm tarafından yayınlanır (consensus katmanı sağlığı).
# px4_interface çöküp consensus_fsm ayaktaysa AgentStatus gelmeye devam eder ama
# consensus katmanı ölmüş olabilir. İki katman ayrı izlenmelidir.
#
# Topic : /swarm/leader/heartbeat
# QoS   : RELIABLE + VOLATILE, depth=5
# Kim   : consensus_fsm (sadece STATE_IN_SWARM + ROLE_LEADER olan node)
# Hz    : 10 Hz
#
# FOLLOWER KURALI:
# Son heartbeat'ten 300ms geçmişse lider timeout → election başlat.
# Bully variant: aktif ajanlar arasında en küçük agent_id lider olur.
#   En düşük ID birincil drone; drone-1 ayaktayken election başlamaz.
#   STANDBY ve DETACHED ajanlar election dışı; yalnızca STATE_IN_SWARM ajanlar katılır.
# election_round her yeni election başladığında +1 artar (stale mesaj koruması).

builtin_interfaces/Time stamp

uint8  leader_id
uint32 sequence_num          # her publish'te +1; sıra atlama = paket kaybı uyarısı
uint8  election_round        # mevcut election turu; stale mesajları ezmek için
uint8  active_agent_count    # liderin gördüğü aktif ajan sayısı (follower çapraz doğrulama)
bool   mission_active        # görev devam ediyor mu (follower'lar için bağlam)
