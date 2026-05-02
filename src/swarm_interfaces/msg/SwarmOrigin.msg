# SwarmOrigin.msg
# Shared NED coordinate frame origin broadcast by the swarm leader.
#
# NEDEN KRİTİK (GERÇEK DONANIM):
# SITL'de tüm drone'lar aynı simülatör origin'inden başlar → local NED paylaşılır.
# Gerçek sahada her drone GPS konumunu local NED origin'i olarak kurar.
# Drone 1'in "x=0, y=0"'ı Drone 2'ninkiyle örtüşmez.
# formation_control NED koordinatlarıyla çalışır; ortak origin olmadan
# farklı dronn'lara gönderilen setpoint'ler farklı fiziksel noktalara işaret eder → sürü dağılır.
#
# ÇÖZÜM:
# Leader drone arming öncesi GPS kilidini aldıktan sonra bu mesajı yayınlar.
# Diğer drone'ların px4_interface'i bu origin'i MAVLink SET_GPS_GLOBAL_ORIGIN
# komutuyla PX4'e gönderir; böylece tüm local NED frame'ler aynı GPS noktasına kilitlenir.
#
# Publisher: leader'ın agent_fsm_node / px4_interface
# Subscribers: tüm diğer drone'ların px4_interface'leri
# Topic: /swarm/origin
# QoS: RELIABLE + TRANSIENT_LOCAL (yeni katılan drone'lar son değeri alabilmeli), 0.2-1 Hz

builtin_interfaces/Time stamp

uint8 leader_agent_id

# GPS origin — WGS84
float64 origin_lat_deg       # latitude,  degrees
float64 origin_lon_deg       # longitude, degrees
float32 origin_alt_amsl_m    # altitude above mean sea level, metres

# Origin validity. Drones must NOT apply the origin until valid=true AND
# gps_fix_type >= 3 (3D fix). Using a poor-quality origin is worse than no origin.
bool valid

# GPS quality at the moment origin was captured
uint8  gps_fix_type         # 0=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK float, 6=RTK fixed
float32 gps_hdop            # horizontal dilution of precision; <1.5 acceptable

# Sequence — increments each time leader re-captures origin (e.g., after GPS glitch recovery).
# Followers must re-apply SET_GPS_GLOBAL_ORIGIN when sequence changes.
uint32 sequence
