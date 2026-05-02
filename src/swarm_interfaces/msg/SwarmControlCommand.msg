# SwarmControlCommand.msg
# Semi-autonomous mission command generated from joystick/RC/GCS interpreter.
# Used mainly for Mission 2: Sürü Hareket Modu and Manevra Modu.
# This message is swarm-level; it is not sent directly to PX4.

# SAFETY / DEADMAN RULE:
# command_valid must be true and deadman_pressed must be true for motion commands to be applied.
# If no valid command is received for deadman_timeout_s (default recommendation: 0.5 s),
# swarm_movement_mode / maneuver_mode must transition to HOLD and publish zero motion.
#
# SIGN CONVENTION FOR NORMALIZED INPUTS:
# pitch_cmd    > 0 : forward movement / positive pitch manoeuvre
# roll_cmd     > 0 : right movement / positive roll command from joystick
# yaw_cmd      > 0 : clockwise/right yaw command when viewed from above
# throttle_cmd > 0 : climb / altitude increases (human-readable positive-up)

builtin_interfaces/Time stamp

uint32 sequence_num

# Deadman/validity guard for real RC/joystick use.
bool command_valid
bool deadman_pressed
float32 deadman_timeout_s

# Mission-2 mode
uint8 MODE_UNKNOWN=0
uint8 MODE_SWARM_MOVEMENT=1   # formation is preserved while centroid moves
uint8 MODE_MANEUVER=2         # formation tilts/rotates around fixed centroid

# Formation types
uint8 FORMATION_UNKNOWN=0
uint8 FORMATION_OKBASI=1
uint8 FORMATION_V=2
uint8 FORMATION_CIZGI=3
uint8 FORMATION_CUSTOM=99

uint8 mode

# Normalized command inputs in range [-1.0, +1.0] unless stated otherwise.
# SWARM_MOVEMENT mode:
#   pitch_cmd    -> forward/back movement
#   roll_cmd     -> left/right movement
#   yaw_cmd      -> formation yaw rotation / heading change
#   throttle_cmd -> climb/descent
# MANEUVER mode:
#   pitch_cmd    -> pitch tilt manoeuvre
#   roll_cmd     -> roll tilt manoeuvre
#   yaw_cmd      -> yaw manoeuvre around centroid
#   throttle_cmd -> common altitude change
float32 pitch_cmd
float32 roll_cmd
float32 yaw_cmd
float32 throttle_cmd

# Optional discrete commands
bool takeoff
bool land
bool rtl
bool emergency_stop

# Optional formation change request
bool formation_change_requested
uint8 requested_formation
float32 requested_spacing_m

# Optional command duration. 0.0 means continuous until next command.
float32 duration_s

# Optional limiting parameters
float32 max_speed_mps
float32 max_yaw_rate_deg_s
float32 max_tilt_deg

string source_module
