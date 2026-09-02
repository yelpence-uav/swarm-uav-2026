# SwarmState.msg
# Global swarm summary for mission_fsm, swarm_fsm, GCS, and telemetry.
# Coordinate convention: local NED frame.
#
# Detailed event flow should use SystemEvent.msg on /swarm/events/system.
# last_event_* fields are kept as the latest-event summary for GCS/telemetry.

builtin_interfaces/Time stamp

# Swarm-level states — swarm_fsm/swarm_states.py ile AYNI tutulmalı
uint8 SWARM_UNKNOWN=0
uint8 SWARM_IDLE=1
uint8 SWARM_FORMING=2
uint8 SWARM_NAVIGATING=3
uint8 SWARM_EXECUTING_TASK=4
uint8 SWARM_ROTATING=5
uint8 SWARM_LANDING=6
uint8 SWARM_RTL=7
uint8 SWARM_FAILSAFE=8
uint8 SWARM_MISSION_COMPLETE=9

# Formation types
uint8 FORMATION_UNKNOWN=0
uint8 FORMATION_OKBASI=1
uint8 FORMATION_V=2
uint8 FORMATION_CIZGI=3
uint8 FORMATION_CUSTOM=99

# Event types — mission_events.py (1-39) ve system_events.py (40-59)
uint8 EVENT_UNKNOWN=0
uint8 EVENT_AGENT_READY=1
uint8 EVENT_AGENT_REACHED_POS=2
uint8 EVENT_AGENT_DETACHED=3
uint8 EVENT_AGENT_LANDED=4
uint8 EVENT_AGENT_REJOINED=5
uint8 EVENT_AGENT_FAULT=6
uint8 EVENT_AGENT_JOIN_REQUEST=7
uint8 EVENT_AGENT_PILOT_OVERRIDE=8
uint8 EVENT_QR_DETECTED=20
uint8 EVENT_QR_PARSED=21
uint8 EVENT_FORMATION_REACHED=22
uint8 EVENT_FORMATION_FAILED=23
uint8 EVENT_MISSION_STARTED=24
uint8 EVENT_MISSION_COMPLETED=25
uint8 EVENT_COLOR_ZONE_DETECTED=26
uint8 EVENT_QR_SEQUENCE_REJECTED=27
uint8 EVENT_PRECISION_LANDING_STARTED=28    # source=detaching agent; value=COLOR_* enum
uint8 EVENT_PRECISION_LANDING_COMPLETED=29  # source=detaching agent; value=COLOR_* enum
uint8 EVENT_ROTATION_STARTED=30             # formation rotation toward next target started
uint8 EVENT_ROTATION_COMPLETED=31           # formation rotation completed
uint8 EVENT_MANEUVER_STARTED=32             # pitch/roll/yaw maneuver started
uint8 EVENT_MANEUVER_COMPLETED=33           # maneuver completed successfully
uint8 EVENT_MANEUVER_FAILED=34              # maneuver failed or timed out
uint8 EVENT_MEMBER_DETACH_STARTED=35        # QR detach/remove flow started
uint8 EVENT_MEMBER_REJOIN_STARTED=36        # rejoin flow started
uint8 EVENT_MEMBER_MANAGEMENT_FAILED=37     # detach/rejoin/replacement failed
uint8 EVENT_GCS_LINK_LOST=40
uint8 EVENT_GCS_LINK_RESTORED=41
uint8 EVENT_BATTERY_LOW=42
uint8 EVENT_COLLISION_RISK=43
uint8 EVENT_OFFBOARD_LOST=44
uint8 EVENT_RTL_TRIGGERED=45
uint8 EVENT_EMERGENCY_LAND=46
uint8 EVENT_PX4_LINK_LOST=47
uint8 EVENT_LEADER_CHANGED=48
uint8 EVENT_SAFETY_HOLD=49
uint8 EVENT_FAILSAFE_CLEARED=50
uint8 EVENT_ORIGIN_READY=51      # shared origin candidate is available
uint8 EVENT_ORIGIN_SYNCED=52     # all required agents applied SwarmOrigin
uint8 EVENT_ORIGIN_FAILED=53     # origin sync failed or timed out
uint8 EVENT_OSCILLATION_DETECTED=54   # formation control oscillation detected; value=agent_id
uint8 EVENT_UNSTABLE_FLIGHT=55        # physical flight instability; value=agent_id
uint8 EVENT_GEOFENCE_VIOLATION=56     # agent exited competition geofence; value=agent_id
uint8 EVENT_ALTITUDE_LIMIT_EXCEEDED=57 # agent exceeded altitude limit; value=altitude_agl_m
uint8 EVENT_RC_LINK_LOST=58           # RC link lost; value=agent_id
uint8 EVENT_KILL_SWITCH_ACTIVATED=59  # RC kill switch activated; value=agent_id

# Event severity
uint8 SEVERITY_INFO=0
uint8 SEVERITY_WARNING=1
uint8 SEVERITY_CRITICAL=2
uint8 SEVERITY_EMERGENCY=3

uint8 swarm_state
uint8 leader_id
# 🔴 active_agent_count ile active_agent_ids AYNI SEYI OLCMEZ — 3 Eylul 2026.
#   count = CANLILIK: kac ajandan yakin zamanda haber aldik (tek sart:
#           bayat degil). YERDE, IDLE'da bile 3 olur.
#   ids   = FORMASYONA UYGUNLUK: healthy + origin_synced + taze +
#           state in FORMATION_ACTIVE_STATES. Yerde IDLE iken BOS olur.
# Yerde olculen gercek mesaj:
#     active_agent_count: 3   active_agent_ids: []   centroid: (0,0)
# mission1 "sayi > 0 ise konumlar da vardir" varsayimiyla HOME'u (0,0)'a
# kilitledi ve RETURN_HOME suruyu kalkis merkezi yerine origin'e cagirdi
# (5 m yanlis, home_xy_set=True diyerek). Duzeltildi (8fbfec0) ama ayni
# varsayimi yapacak bir sonraki tuketici icin bu not burada duruyor.
# ⚠️ IKISINI ESITLEMEK COZUM DEGIL: count bir FAILSAFE'i besliyor
# (swarm_fsm_node: count==0 and total>0 -> EMERGENCY_LAND). Listeye
# esitlenirse yerde bekleyen suru "iletisim kesildi" sanilip indirilir.
# KONUM LAZIMSA active_agent_ids / agent_pos_* KULLAN, count'a bakma.
uint8 active_agent_count
uint8 active_formation

bool mission_active
bool formation_reached
bool formation_stable
bool emergency_active

# Swarm centroid in local NED frame
float32 centroid_x
float32 centroid_y
float32 centroid_z

float32 formation_heading_deg

# Formation quality metrics
float32 formation_max_error_m
float32 formation_avg_error_m
float32 formation_heading_error_deg

AgentStatus[] agents

# Aktif ajan ID'leri ve pozisyonları — swarm_fsm tarafından doldurulur.
# active_agent_ids ile paralel diziler (aynı indeks = aynı drone).
# formation_node optimal rank ataması için bu pozisyonları kullanır.
uint8[] active_agent_ids
float32[] agent_pos_x
float32[] agent_pos_y
float32[] agent_pos_z

string active_mission
string status_text

# Active QR mission progress — mission_fsm writes these.
# GCS and logger can track which step of the QR sequence is being executed.
uint32 current_qr_id       # qr_id of the QR being executed; 0 = none
uint32 current_qr_seq      # qr_seq of the QR being executed; 0 = none

# Son olay bilgisi (events/event_bus.py bu alanları okur)
uint8   last_event_type      # EVENT_* enum; 0 = olay yok
uint8   last_event_severity  # SEVERITY_* enum
uint8   last_event_source    # kaynak ajan ID; 0 = sistem geneli
float32 last_event_value     # sayısal değer (örn. batarya %, COLOR_* enum)
float32 last_event_pos_x     # NED x; last_event_has_position=false ise yok say
float32 last_event_pos_y     # NED y; last_event_has_position=false ise yok say
float32 last_event_pos_z     # NED z; last_event_has_position=false ise yok say
bool    last_event_has_position # true ise last_event_pos_x/y/z geçerli
string  last_event_message
