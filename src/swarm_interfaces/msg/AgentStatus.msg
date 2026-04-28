# AgentStatus.msg
# Single UAV / agent status message.
# Coordinate convention: local NED frame.
# x,y,z are metres. z positive is down. heading_deg is degrees.
#
# STATE enum — swarm_state_machine/agent_fsm/agent_states.py ile AYNI tutulmalı.

builtin_interfaces/Time stamp

# Agent roles
uint8 ROLE_UNKNOWN=0
uint8 ROLE_LEADER=1
uint8 ROLE_FOLLOWER=2
uint8 ROLE_STANDBY=3
uint8 ROLE_DETACHED=4

# Agent FSM states — agent_states.py ile eşleştirildi
uint8 STATE_UNKNOWN=0
uint8 STATE_IDLE=1
uint8 STATE_ARMING=2
uint8 STATE_ARMED=3
uint8 STATE_TAKEOFF=4
uint8 STATE_IN_SWARM=5
uint8 STATE_EXECUTING_TASK=6
uint8 STATE_DETACHED=7
uint8 STATE_PRECISION_LANDING=8
uint8 STATE_WAITING_REJOIN=9
uint8 STATE_REJOINING=10
uint8 STATE_RETURN_HOME=11
uint8 STATE_LANDING=12
uint8 STATE_LANDED=13
uint8 STATE_FAILSAFE=14
uint8 STATE_STANDBY=15    # reserve drone: waits on ground, requests to join swarm

# PX4 flight mode enum — px4_interface maps VehicleStatus.nav_state to this field.
# mode_manager and failsafe_fsm use this to distinguish MANUAL/POSCTL/OFFBOARD/RTL/LAND.
uint8 FLIGHT_MODE_UNKNOWN=0
uint8 FLIGHT_MODE_MANUAL=1
uint8 FLIGHT_MODE_ALTCTL=2
uint8 FLIGHT_MODE_POSCTL=3
uint8 FLIGHT_MODE_OFFBOARD=4
uint8 FLIGHT_MODE_AUTO_MISSION=5
uint8 FLIGHT_MODE_AUTO_LOITER=6
uint8 FLIGHT_MODE_AUTO_RTL=7
uint8 FLIGHT_MODE_AUTO_LAND=8
uint8 FLIGHT_MODE_ACRO=9
uint8 FLIGHT_MODE_STABILIZED=10

uint8 agent_id
uint8 role
uint8 state

# Link / PX4 status
bool px4_link_ok
bool gcs_link_ok
bool armed

# offboard_enabled kept for backward compatibility. offboard_active is the canonical
# field used by mode_manager/failsafe_fsm. px4_interface should set both identically.
bool offboard_enabled
bool offboard_active
uint8 flight_mode
bool pilot_override_active

bool failsafe_active
bool healthy

# --- BATTERY ---
# battery_percent: estimated SoC. Useful for display; do NOT use for failsafe thresholds.
# battery_voltage_v: raw cell voltage under load. PX4 failsafe is voltage-based.
# Under full throttle, a "40%" LiPo can sag below 3.5V/cell and trigger PX4 cutoff.
# GCS and failsafe_manager must monitor voltage, not percent alone.
float32 battery_percent
float32 battery_voltage_v    # total pack voltage, volts
float32 battery_current_a    # current draw, amperes (0.0 if not available)

# --- POSITION (local NED) ---
# WARNING — GERÇEK DONANIM: Bu alanlar local NED frame'dedir.
# Her drone kendi GPS origin'inden NED kurar. SwarmOrigin.msg ile paylaşılan origin
# tüm drone'lara uygulanmadan bu değerler formation_control için kullanılamaz.
float32 pos_x
float32 pos_y
float32 pos_z

float32 vel_x
float32 vel_y
float32 vel_z

# --- ATTITUDE ---
# Görev 2 pitch/roll manevra izleme ve GCS için gerekli.
# heading_deg: yaw / pusula yönü (kuzeyden saat yönüne, 0-360)
# roll_deg / pitch_deg: gerçek gövde açıları, derece (PX4'ten okunur)
float32 heading_deg
float32 roll_deg
float32 pitch_deg

# --- GPS (gerçek donanım için kritik) ---
# fix_type: 0=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK float, 6=RTK fixed
# hdop: yatay doğruluk göstergesi; <1.5 iyi, >2.5 arming'e izin verme
# GCS arming öncesi bu alanları kontrol etmeli.
uint8   gps_fix_type
float32 gps_hdop
uint8   gps_satellites

# Gerçek GPS koordinatları — formation_control ve consensus için paylaşılan
# referans noktası. SwarmOrigin ile aynı frame'e çekildikten sonra kullanılır.
float64 lat_deg
float64 lon_deg
float32 alt_amsl_m

# --- HOME POSITION ---
# RTL hedefi. Arming anında PX4 tarafından kaydedilir.
# GCS, uçuş öncesi her drone'un home noktasını burada doğrulamalıdır.
# home_set=false ise drone RTL komutunu reddeder.
bool    home_set
float64 home_lat_deg
float64 home_lon_deg
float32 home_alt_amsl_m

# --- SENSOR HEALTH (gerçek donanım pre-arm ve in-flight izleme) ---
# SITL'de bunlar her zaman true'dur; gerçek donanımda bozulabilir.
bool imu_healthy
bool mag_healthy
bool baro_healthy

# --- EKF2 / ESTIMATOR HEALTH (gerçek donanım için kritik) ---
# Sensörler sağlıklı görünse bile EKF2 pozisyon/hız tahmini diverge edebilir.
# formation_control ve px4_interface, estimator_ok=false veya ilgili valid flag=false
# olan drone'a normal formasyon setpoint'i göndermemeli; HOLD/FAILSAFE'e geçmelidir.
bool estimator_ok    # EKF2 overall health; false ise normal formasyon setpoint'i gönderme
bool xy_valid        # yatay pozisyon tahmini güvenilir
bool z_valid         # dikey pozisyon güvenilir
bool v_xy_valid      # yatay hız tahmini güvenilir

# --- SWARM ORIGIN SYNC ---
# Bu drone'un SwarmOrigin.msg'den aldığı paylaşılan origin'i uygulayıp uygulamadığı.
# formation_control, origin_synced=false olan drone'lara setpoint göndermemeli.
bool   origin_synced         # true = SwarmOrigin uygulandı
uint32 origin_sequence       # uygulanan SwarmOrigin.sequence değeri

# --- RC / KILL SWITCH ---
# rc_link_ok: RC kumanda bağlantısı kurulu (SBUS/CRSF/SPEKTRUM).
# kill_switch_active: RC kill switch tetiklendi; PX4 motor keser, failsafe_manager bu ajanı swarm'dan çıkarır.
# rc_signal_failsafe_active: PX4 RC signal loss failsafe eşiğini aştı ve aksiyon başlattı.
#   rc_link_ok anlık bağlantı durumu; bu alan PX4 failsafe'i resmi tetiklendiğinde true olur.
bool rc_link_ok
bool kill_switch_active
bool rc_signal_failsafe_active

# --- UÇUŞ KALİTESİ ---
# oscillation_detected: formasyon setpoint etrafında salınım; şartname -10 puan.
# unstable_flight: EKF/sensör kaynaklı fiziksel uçuş kararsızlığı; estimator_ok'tan bağımsız.
bool oscillation_detected
bool unstable_flight

# Join request — STATE_STANDBY drone sets these true when it wants to join the swarm.
# consensus_fsm monitors these; on approval calls AssignRole.srv.
bool wants_to_join
bool ready_to_arm

string status_text
