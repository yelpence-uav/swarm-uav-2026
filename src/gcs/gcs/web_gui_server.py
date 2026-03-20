#!/usr/bin/env python3
"""
Yelpençe Web GUI Server
ROS 2 sensör verilerini WebSocket ile frontend'e stream eder.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from px4_msgs.msg import (
    SensorCombined,
    VehicleStatus,
    VehicleAttitude,
    BatteryStatus,
    VehicleOdometry,
    VehicleLocalPosition,
    VehicleGlobalPosition,
    SensorGps,
    ActuatorOutputs,
    ActuatorMotors,
    VehicleCommand,
    VehicleCommandAck,
)
# try:
#     from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint
#     OFFBOARD_AVAILABLE = True
# except (ImportError, SyntaxError):
OFFBOARD_AVAILABLE = False

from actuator_msgs.msg import Actuators
from sensor_msgs.msg import LaserScan, Image
from flask import Flask, render_template
from flask_socketio import SocketIO
import json
from std_msgs.msg import String
import threading
import subprocess
import math
import os
import argparse
import cv2
import base64
import numpy as np
from cv_bridge import CvBridge
from .formation_manager import FormationManager

# ARGS
parser = argparse.ArgumentParser()
parser.add_argument('--count', type=int, default=1, help='Drone sayısı')
args, unknown = parser.parse_known_args()
DRONE_COUNT = args.count

try:
    from ament_index_python.packages import get_package_share_directory
    package_share_directory = get_package_share_directory('gcs')
    template_dir = os.path.join(package_share_directory, 'templates')
except Exception:
    # Fallback for local development
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')

app = Flask(__name__, template_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# PX4 topic'leri "best effort" QoS kullanır
qos_profile = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1
)

# Global state for active cameras (list of drone_ids)
active_drone_cameras = []

@socketio.on('request_camera')
def handle_camera_request(json):
    global active_drone_cameras
    # frontend artık bir liste yolluyor: drone_ids
    active_drone_cameras = json.get('drone_ids', [])
    print(f"INFO: Camera streams requested for Drones: {active_drone_cameras}")

# Global state for altitude lock (drone_id -> target_m)
active_target_altitudes = {}
# Global state for altitude protector (drone_id -> bool)
altitude_protectors = {}
# User-selected global target altitude (meters above ground)
global_target_altitude = None
# Master flag for GCS processing state to avoid floods
is_processing_command = False

# Formation Management
formation_mgr = FormationManager(socketio)


def send_altitude_reposition(drone_id, target_altitude):
    """Send a height-only reposition command using closed-loop altitude correction."""
    global bridge_node
    if bridge_node is None or drone_id not in bridge_node.drones:
        return

    d = bridge_node.drones[drone_id]
    ref_alt = d['ref_alt']
    current_ekf_alt = -d['local_z']

    true_alt = current_ekf_alt
    if d['lidar']:
        true_alt = min(d['lidar'])
    elif d['dist_bottom'] > 0:
        true_alt = d['dist_bottom']

    alt_correction = target_altitude - true_alt
    target_ekf_alt = current_ekf_alt + alt_correction
    target_amsl = ref_alt + target_ekf_alt

    bridge_node.send_command(
        drone_id,
        192,
        param1=-1.0,
        param2=1.0,
        param4=float('nan'),
        param5=float('nan'),
        param6=float('nan'),
        param7=float(target_amsl)
    )


@socketio.on('toggle_altitude_protector')
def handle_toggle_altitude_protector(data):
    global altitude_protectors
    enabled = data.get('enabled', False)
    drone_ids = data.get('drone_ids', [])
    
    # Eğer liste boşsa veya "hepsi" mantığı istenirse (opsiyonel)
    if not drone_ids:
        drone_ids = list(range(1, DRONE_COUNT + 1))
        
    for d_id in drone_ids:
        altitude_protectors[d_id] = enabled
        print(f"Drone {d_id} Altitude Protector is now: {'ENABLED' if enabled else 'DISABLED'}")

@socketio.on('start_formation')
def handle_start_formation(data):
    global formation_mgr, bridge_node, global_target_altitude, active_target_altitudes, altitude_protectors
    leader_id = data.get('leader_id', -1)
    spacing = data.get('spacing', 2.5)
    formation_type = data.get('formation_type', 'arrowhead')
    # Ensure bridge node is set before starting
    formation_mgr.bridge_node = bridge_node
    formation_mgr.start(leader_id, spacing, formation_type)

    if formation_mgr.active:
        # Formation active: only leader is altitude-locked, followers track leader in formation loop.
        active_target_altitudes.clear()
        for d_id in range(1, DRONE_COUNT + 1):
            altitude_protectors[d_id] = (d_id == leader_id)

        if global_target_altitude is not None:
            active_target_altitudes[leader_id] = global_target_altitude
            send_altitude_reposition(leader_id, global_target_altitude)

@socketio.on('stop_formation')
def handle_stop_formation():
    global formation_mgr, global_target_altitude, active_target_altitudes, altitude_protectors, bridge_node
    formation_mgr.stop()

    # Formation stopped: restore altitude lock for all drones if a global target exists.
    if global_target_altitude is not None and bridge_node is not None:
        for d_id in bridge_node.drones.keys():
            active_target_altitudes[d_id] = global_target_altitude
            altitude_protectors[d_id] = True
            send_altitude_reposition(d_id, global_target_altitude)


def quaternion_to_euler(w, x, y, z):
    """Quaternion'u Euler açılarına (derece) çevirir."""
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


class TelemetryBridge(Node):
    def __init__(self):
        super().__init__('web_gui_bridge')
        self.get_logger().info(f'Yelpençe Web GUI Bridge (v4.0-ROBUST) başlatıldı! Drone Count: {DRONE_COUNT}')
        self.bridge = CvBridge()
        self.cmd_pubs = {}
        
        # Best Effort QoS (telemetry)
        qos_best_effort = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # Reliable QoS (status & commands)
        qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        self.drones = {i+1: {
            'status': {'armed': False, 'mode': 'OFF'},
            'gps': {'lat': 0.0, 'lon': 0.0, 'alt_abs': 0.0, 'alt_rel': 0.0},
            'local_z': 0.0,       # EKF2 fused altitude (NED -z = up)
            'x': 0.0, 'y': 0.0,   # Local EKF2 X, Y
            'yaw': 0.0,           # Heading in degrees
            'dist_bottom': 0.0,   # EKF2 fused ground distance
            'ref_alt': 0.0,       # Home AMSL reference
            'lidar': [],
            'tof': {'front': 0.0, 'back': 0.0, 'left': 0.0, 'right': 0.0},
            'motors': [0, 0, 0, 0]
        } for i in range(DRONE_COUNT)}

        # Motor telemetry smoothing and throttling
        self.motor_ema = {i + 1: [0.0, 0.0, 0.0, 0.0] for i in range(DRONE_COUNT)}
        self.last_motor_time = {i + 1: 0.0 for i in range(DRONE_COUNT)}

        for i in range(DRONE_COUNT):
            drone_id = i + 1
            ns = f'/drone_{drone_id}'
            self.get_logger().info(f'Drone {drone_id} abonelikleri kuruluyor...')
            
            # IMU
            self.create_subscription(SensorCombined, f'{ns}/fmu/out/sensor_combined', 
                lambda msg, d_id=drone_id: self.sensor_callback(msg, d_id), qos_best_effort)
            
            # VehicleLocalPosition — EKF2 fused position (BEST altitude source)
            self.create_subscription(VehicleLocalPosition, f'/swarm{ns}/delayed_local_position', 
                lambda msg, d_id=drone_id: self.local_pos_callback(msg, d_id), qos_best_effort)
            self.create_subscription(VehicleLocalPosition, f'{ns}/fmu/out/vehicle_local_position_v1', 
                lambda msg, d_id=drone_id: self.local_pos_callback(msg, d_id), qos_best_effort)
            
            # Odometry (fallback position)
            self.create_subscription(VehicleOdometry, f'/swarm{ns}/delayed_odometry', 
                lambda msg, d_id=drone_id: self.pos_callback(msg, d_id), qos_best_effort)
            
            # Status (BEST_EFFORT - PX4 uXRCE çıktıları genelde best effort)
            self.create_subscription(VehicleStatus, f'{ns}/fmu/out/vehicle_status', 
                lambda msg, d_id=drone_id: self.status_callback(msg, d_id), qos_best_effort)
            self.create_subscription(VehicleStatus, f'{ns}/fmu/out/vehicle_status_v2', 
                lambda msg, d_id=drone_id: self.status_callback(msg, d_id), qos_best_effort)
            
            # Attitude
            self.create_subscription(VehicleAttitude, f'{ns}/fmu/out/vehicle_attitude', 
                lambda msg, d_id=drone_id: self.attitude_callback(msg, d_id), qos_best_effort)
            
            # Battery (Support standard and v1)
            self.create_subscription(BatteryStatus, f'{ns}/fmu/out/battery_status', 
                lambda msg, d_id=drone_id: self.battery_callback(msg, d_id), qos_best_effort)
            self.create_subscription(BatteryStatus, f'{ns}/fmu/out/battery_status_v1', 
                lambda msg, d_id=drone_id: self.battery_callback(msg, d_id), qos_best_effort)
            
            # LiDAR (Remapped from Gazebo)
            self.create_subscription(LaserScan, f'{ns}/lidar/scan', 
                                     lambda msg, d=drone_id: self.lidar_callback(msg, d), qos_best_effort)
            
            # 4-Way ToF Sensors
            for side in ['front', 'back', 'left', 'right']:
                self.create_subscription(LaserScan, f'{ns}/tof/{side}', 
                                         lambda msg, d=drone_id, s=side: self.tof_callback(msg, d, s), qos_best_effort)
            
            # Camera (Remapped from Gazebo)
            self.create_subscription(Image, f'{ns}/camera/image_raw',
                lambda msg, d_id=drone_id: self.image_callback(msg, d_id), qos_best_effort)
 
            # GPS
            self.create_subscription(SensorGps, f'{ns}/fmu/out/vehicle_gps_position',
                lambda msg, d_id=drone_id: self.gps_callback(msg, d_id), qos_best_effort)
            self.create_subscription(VehicleCommandAck, f'{ns}/fmu/out/vehicle_command_ack',
                lambda msg, d_id=drone_id: self.ack_callback(msg, d_id), qos_best_effort)
 
            # Motors (Authority from PX4 - TOPICS MUST BE BEST_EFFORT)
            self.create_subscription(ActuatorOutputs, f'{ns}/fmu/out/actuator_outputs',
                lambda msg, d_id=drone_id: self.motor_callback(msg, d_id, "outputs"), qos_best_effort)
            
            # Alternative topics for different PX4/SITL versions
            self.create_subscription(ActuatorOutputs, f'{ns}/fmu/out/actuator_outputs_sim',
                lambda msg, d_id=drone_id: self.motor_callback(msg, d_id, "outputs_sim"), qos_best_effort)

            self.create_subscription(ActuatorMotors, f'{ns}/fmu/out/actuator_motors',
                lambda msg, d_id=drone_id: self.motor_callback(msg, d_id, "motors"), qos_best_effort)
            
            # Third fallback: Actuators (actuator_msgs)
            self.create_subscription(Actuators, f'{ns}/fmu/out/actuator_controls_0',
                lambda msg, d_id=drone_id: self.motor_callback(msg, d_id, "actuators"), qos_best_effort)
 
            # Commands (Inbound to PX4)
            self.cmd_pubs[drone_id] = self.create_publisher(VehicleCommand, f'{ns}/fmu/in/vehicle_command', qos_reliable)
            
            if OFFBOARD_AVAILABLE:
                self.offboard_ctrl_pubs[drone_id] = self.create_publisher(OffboardControlMode, f'{ns}/fmu/in/offboard_control_mode', qos_best_effort)
                self.trajectory_setpoint_pubs[drone_id] = self.create_publisher(TrajectorySetpoint, f'{ns}/fmu/in/trajectory_setpoint', qos_best_effort)

        # Global Altitude Status Publisher
        self.altitude_status_pub = self.create_publisher(String, '/swarm/altitude_status', 10)
        
        # Navigation Status Publisher (For Collision Avoidance)
        self.nav_status_pub = self.create_publisher(String, '/swarm/navigation_status', 10)

        # Collision Status Subscriber (From Collision Avoidance Node)
        self.create_subscription(String, '/swarm/collision_status', self.collision_callback, 10)

        # Heartbeat timer to verify executor is spinning
        self.create_timer(1.0, self.heartbeat_callback)

    def collision_callback(self, msg):
        """Relays collision intervention status from ROS to the SocketIO clients."""
        try:
            data = json.loads(msg.data)
            socketio.emit('collision_update', data)
        except Exception as e:
            self.get_logger().error(f"Error in collision_callback: {e}")

    def heartbeat_callback(self):
        self.get_logger().info("HEARTBEAT: ROS Executor is spinning.")

    def publish_offboard_control_mode(self, drone_id):
        """PX4'e Offboard kontrol modunu gönderir."""
        if not OFFBOARD_AVAILABLE: return
        msg = OffboardControlMode()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self.offboard_ctrl_pubs[drone_id].publish(msg)

    def publish_trajectory_setpoint(self, drone_id, x, y, z, yaw):
        """PX4'e hedef pozisyon ve yönelim gönderir."""
        if not OFFBOARD_AVAILABLE: return
        msg = TrajectorySetpoint()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.yaw = float(yaw)
        self.trajectory_setpoint_pubs[drone_id].publish(msg)

    def send_command(self, drone_id, command, param1=0.0, param2=0.0, param3=0.0, param4=0.0, param5=0.0, param6=0.0, param7=0.0):
        """PX4'e VehicleCommand gönderir."""
        msg = VehicleCommand()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.command = int(command)
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.param3 = float(param3)
        msg.param4 = float(param4)
        msg.param5 = float(param5)
        msg.param6 = float(param6)
        msg.param7 = float(param7)
        msg.target_system = drone_id  # Drone ID 1 is System ID 1, ID 2 is System ID 2, etc.
        msg.target_component = 1
        msg.source_system = 255 # GCS System ID
        msg.source_component = 0
        msg.from_external = True
        msg.confirmation = 1
        self.cmd_pubs[drone_id].publish(msg)

    def sensor_callback(self, msg, drone_id):
        data = {
            'type': 'imu',
            'drone_id': drone_id,
            'accel': {'x': float(msg.accelerometer_m_s2[0]), 'y': float(msg.accelerometer_m_s2[1]), 'z': float(msg.accelerometer_m_s2[2])},
            'gyro': {'x': float(msg.gyro_rad[0]), 'y': float(msg.gyro_rad[1]), 'z': float(msg.gyro_rad[2])}
        }
        socketio.emit('telemetry', data)

    def local_pos_callback(self, msg, drone_id):
        """VehicleLocalPosition — En güvenilir irtifa kaynağı (EKF2 Fusion)."""
        if drone_id in self.drones:
            d = self.drones[drone_id]
            d['x'] = float(msg.x)
            d['y'] = float(msg.y)
            d['local_z'] = float(msg.z)              # NED: -z = yukarı
            d['gps']['alt_rel'] = -float(msg.z)      # Pozitif irtifa
            d['ref_alt'] = float(msg.ref_alt)         # Home AMSL
            if msg.dist_bottom_valid:
                d['dist_bottom'] = float(msg.dist_bottom)

        data = {
            'type': 'position',
            'drone_id': drone_id,
            'x': float(msg.x), 'y': float(msg.y), 'z': float(msg.z),
            'vz': float(msg.vz),
            'local_alt': -float(msg.z),
            'dist_bottom': float(msg.dist_bottom) if msg.dist_bottom_valid else -1.0,
            'ref_alt': float(msg.ref_alt)
        }
        socketio.emit('telemetry', data)

    def pos_callback(self, msg, drone_id):
        """VehicleOdometry fallback (only used if LocalPosition not available)."""
        if drone_id in self.drones:
            d = self.drones[drone_id]
            # Only update if local_pos hasn't been set yet
            if d['local_z'] == 0.0 and abs(float(msg.position[2])) > 0.01:
                d['gps']['alt_rel'] = -float(msg.position[2])

    def status_callback(self, msg, drone_id):
        is_armed = msg.arming_state == 2
        
        # Local state update (CRITICAL for fallback)
        if drone_id in self.drones:
            self.drones[drone_id]['status']['armed'] = is_armed

        # Mode text
        nav_names = {
            0: 'MANÜEL', 1: 'ALT-CTL', 2: 'POS-CTL', 3: 'MISSION', 
            4: 'LOITER', 5: 'RTL', 17: 'TAKEOFF', 18: 'LAND', 
            20: 'HOLD', 14: 'OFFBOARD'
        }
        nav_state = nav_names.get(msg.nav_state, f'MOD {msg.nav_state}')
        
        data = {
            'type': 'status',
            'drone_id': drone_id,
            'armed': is_armed,
            'nav_state': nav_state
        }
        socketio.emit('telemetry', data)

    def ack_callback(self, msg, drone_id):
        # Result mapping
        results = {
            0: "ACCEPTED (0)",
            1: "TEMPORARILY_REJECTED (1)",
            2: "DENIED (2)",
            3: "UNSUPPORTED (3)",
            4: "FAILED (4)"
        }
        res_text = results.get(msg.result, f"UNKNOWN ({msg.result})")
        self.get_logger().info(f"PX4_ACK: Drone {drone_id}, Command {msg.command}, Result: {res_text}")
        
        if msg.result == 1: # TEMPORARILY_REJECTED
            self.get_logger().warn(f"!!! Drone {drone_id} henüz hazır değil! (EKF2/GPS hatası olabilir). Lütfen 2-3 saniye bekleyip tekrar ARM yapın.")

    def image_callback(self, msg, drone_id):
        global active_drone_cameras
        if drone_id not in active_drone_cameras:
            return
            
        try:
            # Convert ROS Image to OpenCV image
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # Compress for bandwidth
            _, buffer = cv2.imencode('.jpg', cv_image, [cv2.IMWRITE_JPEG_QUALITY, 40])
            # To Base64
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            socketio.emit('camera_frame', {
                'drone_id': drone_id,
                'frame': jpg_as_text
            })
        except Exception as e:
            self.get_logger().error(f'Camera Error (Drone {drone_id}): {e}')

    def attitude_callback(self, msg, drone_id):
        q = msg.q
        roll, pitch, yaw = quaternion_to_euler(q[0], q[1], q[2], q[3])
        
        # Update local state
        if drone_id in self.drones:
            self.drones[drone_id]['yaw'] = float(yaw)
            
        data = {
            'type': 'attitude',
            'drone_id': drone_id,
            'roll': round(roll, 2), 'pitch': round(pitch, 2), 'yaw': round(yaw, 2)
        }
        socketio.emit('telemetry', data)


    def battery_callback(self, msg, drone_id):
        data = {
            'type': 'battery',
            'drone_id': drone_id,
            'voltage': round(float(msg.voltage_v), 2),
            'remaining': round(float(msg.remaining) * 100, 1)
        }
        socketio.emit('telemetry', data)

    def lidar_callback(self, msg, drone_id):
        """LiDAR verisini alır, filtreler ve saklar."""
        if not msg.ranges:
            return
            
        # 1. Filtreleme: inf, nan ve 0.1m altı parazitleri ayıkla
        valid_ranges = [
            float(r) for r in msg.ranges 
            if not math.isinf(r) and not math.isnan(r) and r > 0.1
        ]
        
        # Eğer hiç geçerli veri yoksa, varsayılan olarak maksimum menzili (8m) ekle
        if not valid_ranges:
            valid_ranges = [8.0]
        
        if drone_id in self.drones:
            # Sadece geçerli filtreli veriyi saklıyoruz
            self.drones[drone_id]['lidar'] = valid_ranges
            
            # Telemetriyi gönder
            socketio.emit('telemetry', {
                'type': 'lidar',
                'drone_id': drone_id,
                'ranges': valid_ranges
            })

    def tof_callback(self, msg, drone_id, side):
        """Dört bir yandaki ToF sensörlerinden gelen mesafe verisi (Optimized: No Emit)."""
        if drone_id in self.drones:
            dist = float(msg.ranges[0]) if len(msg.ranges) > 0 else 0.0
            self.drones[drone_id]['tof'][side] = dist

    def gps_callback(self, msg, drone_id):
        # Update local state
        if drone_id in self.drones:
            self.drones[drone_id]['gps']['lat'] = float(msg.latitude_deg)
            self.drones[drone_id]['gps']['lon'] = float(msg.longitude_deg)
            self.drones[drone_id]['gps']['alt_abs'] = float(msg.altitude_msl_m)

        data = {
            'type': 'gps',
            'drone_id': drone_id,
            'lat': float(msg.latitude_deg),
            'lon': float(msg.longitude_deg),
            'alt': float(msg.altitude_msl_m),
            'sats': int(msg.satellites_used)
        }
        socketio.emit('telemetry', data)

    def motor_callback(self, msg, drone_id, source_type):
        try:
            # 1. Throttling (Max 10Hz to prevent GUI flickering)
            now = self.get_clock().now().nanoseconds / 1e9
            if now - self.last_motor_time.get(drone_id, 0) < 0.1:
                return
            self.last_motor_time[drone_id] = now

            # 2. Extract raw data
            if source_type in ["outputs", "outputs_sim"]:
                raw_outputs = [float(v) for v in msg.output[:4]]
            elif source_type == "motors":
                raw_outputs = [float(v) for v in msg.control[:4]]
            else: # actuators
                raw_outputs = [float(v) for v in msg.position[:4]] 
                
            # Filter out NaNs
            raw_outputs = [0.0 if math.isnan(v) or math.isinf(v) else v for v in raw_outputs]
            
            # 3. Dynamic Scaling Heuristic
            max_val = max(raw_outputs) if raw_outputs else 0
            if max_val > 1100:
                # Likely PWM (1000-2000)
                processed = [float(max(0, v - 1000)) for v in raw_outputs]
            elif max_val > 5.0: 
                # Already 0-1000 range or similar
                processed = [float(v) for v in raw_outputs]
            else:
                # Likely 0-1 (Normalized)
                processed = [float(v * 1000) for v in raw_outputs]

            # 4. Exponential Moving Average (EMA) Filter (Smoothing)
            # ALPHA = 0.2 (Higher = faster response, Lower = smoother)
            ALPHA = 0.25
            filtered = []
            if drone_id not in self.motor_ema:
                self.motor_ema[drone_id] = [0.0] * 4
                
            for i in range(len(processed)):
                prev = self.motor_ema[drone_id][i]
                new_val = (ALPHA * processed[i]) + ((1.0 - ALPHA) * prev)
                self.motor_ema[drone_id][i] = new_val
                filtered.append(int(new_val))

            # FALLBACK: If motors are spinning, force ARMED status
            spinning = any(v > 50 for v in filtered)
            internal_armed = self.drones[drone_id]['status']['armed'] if drone_id in self.drones else False
            effective_armed = internal_armed or spinning

            # 5. Broadcast to SocketIO
            socketio.emit('telemetry', {
                'type': 'motors',
                'drone_id': drone_id,
                'speeds': filtered,
                'raw': raw_outputs,
                'source': source_type,
                'armed': effective_armed
            })
        except Exception as e:
            self.get_logger().error(f"Motor Callback Error (Drone {drone_id}): {e}")

def ros_thread():
    print("ROS Thread: Starting...")
    rclpy.init()
    global bridge_node
    try:
        bridge_node = TelemetryBridge()
        print("ROS Thread: Node created.")
        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(bridge_node)
        print("ROS Thread: Executor ready, spinning...")
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.01)
            socketio.sleep(0.01)
    except Exception as e:
        print(f"ROS Thread Error: {e}")
    finally:
        bridge_node = None
        print("ROS Thread: Shutting down.")
        if rclpy.ok():
            rclpy.shutdown()

@app.route('/')
def index():
    return render_template('index.html')

# Global bridge instance reference for socket handlers
bridge_node = None

@socketio.on('mass_arm')
def handle_mass_arm(data=None):
    global bridge_node, is_processing_command
    if bridge_node is None or is_processing_command: return
    
    try:
        is_processing_command = True
        drone_ids = []
        if data and 'drone_ids' in data:
            drone_ids = data['drone_ids']
        else:
            drone_ids = list(range(1, DRONE_COUNT + 1))

        bridge_node.get_logger().info(f">>> HEDEF ARM emri alındı! Dronelar: {drone_ids}")
        for drone_id in drone_ids:
            # Önce HOLD (Auto Loiter) moduna geçmeyi dene (Param2: 4, Param3: 3)
            bridge_node.send_command(drone_id, 176, param1=1.0, param2=4.0, param3=3.0)
            socketio.sleep(0.1)
            bridge_node.send_command(drone_id, 400, param1=1.0)
            socketio.sleep(0.1)
    finally:
        is_processing_command = False

@socketio.on('mass_takeoff')
def handle_mass_takeoff(data=None):
    """
    Belirtilen droneları güvenli bir şekilde kaldırır.
    """
    global bridge_node, is_processing_command
    if bridge_node is None or is_processing_command: return
    
    try:
        is_processing_command = True
        drone_ids = []
        if data and 'drone_ids' in data:
            drone_ids = data['drone_ids']
        else:
            drone_ids = list(range(1, DRONE_COUNT + 1))

        bridge_node.get_logger().info(f">>> HEDEF KALKIŞ DÖNGÜSÜ BAŞLATILDI: {drone_ids}")
        
        for drone_id in drone_ids:
            # ARM (Command 400)
            bridge_node.send_command(drone_id, 400, param1=1.0)
        
        socketio.sleep(2.0) 

        for drone_id in drone_ids:
            bridge_node.send_command(drone_id, 176, param1=1.0, param2=4.0, param3=2.0)
            bridge_node.get_logger().info(f"Drone {drone_id}: Kalkış emri verildi.")
    finally:
        is_processing_command = False

@socketio.on('set_target_altitude')
@socketio.on('mass_equalize_altitude')
def handle_set_target_altitude(data):
    """Tüm droneları belirtilen hedef irtifaya çıkarır/indirir.
    
    Strateji: Droneların farklı zemin/barometre kalibrasyonlarından kaynaklanan EKF driftlerini hesaba katarak
    Gerçek yüksekliği (LiDAR) baz alan kapalı döngü bir düzeltme yapar.
    """
    global bridge_node, global_target_altitude, active_target_altitudes, altitude_protectors
    if bridge_node is None: return
    
    target_altitude = data.get('altitude_m', 5.0)
    global_target_altitude = target_altitude
    drone_ids = data.get('drone_ids', [])
    if not drone_ids:
        drone_ids = list(range(1, DRONE_COUNT + 1))

    if formation_mgr.active and formation_mgr.leader_id in bridge_node.drones:
        target_ids = [formation_mgr.leader_id]
        active_target_altitudes.clear()
        for d_id in range(1, DRONE_COUNT + 1):
            altitude_protectors[d_id] = (d_id == formation_mgr.leader_id)
        bridge_node.get_logger().info(
            f">>> HEDEF İRTİFA (Formasyon Aktif): {target_altitude}m | Lider: {formation_mgr.leader_id}"
        )
    else:
        target_ids = drone_ids
        bridge_node.get_logger().info(f">>> HEDEF İRTİFA: {target_altitude}m | Seçili: {target_ids}")

    for drone_id in target_ids:
        active_target_altitudes[drone_id] = target_altitude
        altitude_protectors[drone_id] = True
        send_altitude_reposition(drone_id, target_altitude)
        socketio.sleep(0.05)

@socketio.on('mass_land')
def handle_mass_land(data=None):
    global bridge_node, active_target_altitudes, is_processing_command
    if bridge_node is None or is_processing_command:
        return

    is_processing_command = True
    drone_ids = []
    if data and 'drone_ids' in data:
        drone_ids = data['drone_ids']
    else:
        drone_ids = list(range(1, DRONE_COUNT + 1))

    print(f">>> HEDEF İNİŞ emri alındı! Dronelar: {drone_ids}")
    for drone_id in drone_ids:
        # İrtifa kilidini bu drone için temizle
        if drone_id in active_target_altitudes:
            del active_target_altitudes[drone_id]
            
        # Land command (Command 21)
        bridge_node.send_command(drone_id, 21)
        print(f"Drone {drone_id}: Land gönderildi.")
        socketio.sleep(0.05)
    
    is_processing_command = False

@socketio.on('mass_disarm')
def handle_mass_disarm(data=None):
    global bridge_node, active_target_altitudes, is_processing_command
    if bridge_node is None or is_processing_command:
        return
 
    is_processing_command = True
    drone_ids = []
    if data and 'drone_ids' in data:
        drone_ids = data['drone_ids']
    else:
        drone_ids = list(range(1, DRONE_COUNT + 1))

    print(f">>> HEDEF MOTOR DURDURMA emri alındı! Dronelar: {drone_ids}")
    for drone_id in drone_ids:
        # İrtifa kilidini temizle
        if drone_id in active_target_altitudes:
            del active_target_altitudes[drone_id]

        # Disarm command (Command 400, Param1: 0.0)
        bridge_node.send_command(drone_id, 400, param1=0.0)
        print(f"Drone {drone_id}: Disarm gönderildi.")
        socketio.sleep(0.05)
        
    is_processing_command = False

def altitude_correction_loop():
    """Her 3 saniyede bir çalışan yumuşak irtifa düzeltme döngüsü."""
    global bridge_node, active_target_altitudes
    print("Altitude Correction Loop: Started.")
    
    while True:
        socketio.sleep(0.5)
        if bridge_node is None:
            continue
            
        if not active_target_altitudes:
            continue
            
        for drone_id, target_altitude in list(active_target_altitudes.items()):
            # Formation aktifken sadece liderin sabit irtifası korunur.
            if formation_mgr.active and drone_id != formation_mgr.leader_id:
                continue

            # Sadece bu drone için koruyucu aktifse devam et
            if not altitude_protectors.get(drone_id, False):
                continue
                
            if drone_id not in bridge_node.drones:
                continue
                
            d = bridge_node.drones[drone_id]
            ref_alt = d['ref_alt']
            current_ekf_alt = -d['local_z']
            
            # Gerçek yüksekliği belirle
            true_alt = current_ekf_alt
            if d['lidar']:
                true_alt = min(d['lidar'])
            elif d['dist_bottom'] > 0:
                true_alt = d['dist_bottom']
            
            # Sapma miktarını hesapla
            error = target_altitude - true_alt
            
            # ÖNEMLİ: Sadece 5cm'den fazla sapma varsa düzeltme yap (Daha agresif takip)
            if abs(error) > 0.05:
                # EKF'ye göre yeni hedef
                target_ekf_alt = current_ekf_alt + error
                target_amsl = ref_alt + target_ekf_alt
                
                # MAV_CMD_DO_REPOSITION (192) - Sadece Z güncelleniyor
                bridge_node.send_command(drone_id, 192, 
                                         param1=-1.0, 
                                         param2=1.0,
                                         param4=float('nan'), 
                                         param5=float('nan'), 
                                         param6=float('nan'), 
                                         param7=float(target_amsl))
                
                if formation_mgr.active and drone_id == formation_mgr.leader_id:
                    bridge_node.get_logger().info(
                        f"[DÖNGÜ] Lider {drone_id}: İrtifa kilidi düzeltmesi. Hata: {error:.2f}m"
                    )
                else:
                    bridge_node.get_logger().info(
                        f"[DÖNGÜ] Drone {drone_id}: Düzeltme Uygulanıyor (Bireysel). Hata: {error:.2f}m"
                    )


def main():
    print("=" * 50)
    print("  YELPENÇE WEB GUI SERVER")
    print("  http://localhost:5000")
    print(f"  Drone Count: {DRONE_COUNT}")
    print("=" * 50)
    
    try:
        print("Starting ROS background task...")
        socketio.start_background_task(ros_thread)
        print("Starting Altitude Correction background task...")
        socketio.start_background_task(altitude_correction_loop)
        print("Starting Formation Flight background task...")
        socketio.start_background_task(formation_mgr.run_loop)
        print("Starting SocketIO server...")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f"Main Error: {e}")

if __name__ == '__main__':
    main()
