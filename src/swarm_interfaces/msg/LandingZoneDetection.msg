# LandingZoneDetection.msg
# Real-time landing zone detection output from swarm_perception/landing_zone_detector.
# Consumer: precision_landing.py (local onboard); optional relay/logging: telemetry_logger, GCS bridge.
# Coordinate convention: relative to the detecting drone, local NED frame.
#
# NEDEN: landing_zone_detector bağımsız bir modül; çıktısı QRMissionData içine
# gömülü değil. precision_landing.py gerçek zamanlı zone takibi için bu topic'i kullanır.
# Topic: /drone_{id}/perception/landing_zone   QoS: BEST_EFFORT, 20-50 Hz

builtin_interfaces/Time stamp

# Landing/detach zone colors
uint8 COLOR_UNKNOWN=0
uint8 COLOR_RED=1
uint8 COLOR_BLUE=2

uint8 detector_agent_id

# At least one zone found in current frame
bool zone_detected

# Number of zones detected in this frame
uint8 zone_count

# Per-zone arrays. All must have equal length (== zone_count).
uint8[]    zone_colors        # COLOR_* enum per zone
float32[]  zone_x             # NED x of zone centre, metres (relative to drone)
float32[]  zone_y             # NED y of zone centre, metres (relative to drone)
float32[]  zone_z             # NED z of zone centre, metres (relative to drone)
float32[]  zone_confidence    # [0.0, 1.0]
float32[]  zone_radius_m      # estimated zone radius, metres

# Best/primary zone for this agent (highest confidence of requested color)
bool       primary_valid           # true if primary_* fields are usable
uint8      primary_color
float32    primary_x
float32    primary_y
float32    primary_z
float32    primary_confidence
float32    primary_radius_m

# Image-space info for debugging / visual HUD
float32 image_x
float32 image_y
float32 image_width
float32 image_height

# Camera frame info
float32 fov_deg           # actual camera FOV used for this detection
