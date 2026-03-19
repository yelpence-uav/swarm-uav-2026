#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from px4_msgs.msg import SensorCombined, SensorGps, VehicleAirData, VehicleLocalPosition
import os

class SensorSuiteTestNode(Node):
    def __init__(self):
        super().__init__('sensor_suite_diagnostic')
        
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            depth=5)
            
        # 1. IMU (Gyro & Accel)
        self.create_subscription(SensorCombined, '/drone_1/fmu/out/sensor_combined', self.imu_cb, qos)
        # 2. GPS
        self.create_subscription(SensorGps, '/drone_1/fmu/out/vehicle_gps_position', self.gps_cb, qos)
        # 3. Barometer / Air Data
        self.create_subscription(VehicleAirData, '/drone_1/fmu/out/vehicle_air_data', self.air_cb, qos)
        # 4. EKF2 Local Position (Fused Alt)
        self.create_subscription(VehicleLocalPosition, '/drone_1/fmu/out/vehicle_local_position', self.ekf_cb, qos)
        
        self.data = {
            'imu': None,
            'gps': None,
            'air': None,
            'ekf': None
        }
        
        self.create_timer(0.5, self.display)
        print("Sensör Paketi Testi Başlatıldı: Drone 1 dinleniyor...")

    def imu_cb(self, msg): self.data['imu'] = msg
    def gps_cb(self, msg): self.data['gps'] = msg
    def air_cb(self, msg): self.data['air'] = msg
    def ekf_cb(self, msg): self.data['ekf'] = msg

    def display(self):
        os.system('clear')
        print("="*50)
        print("SENSÖR PAKETİ TESTİ (Drone 1)")
        print("="*50)
        
        # IMU
        if self.data['imu']:
            print("[IMU/Gyro]:  X:%.3f, Y:%.3f, Z:%.3f" % tuple(self.data['imu'].gyro_rad))
            print("[IMU/Accel]: X:%.3f, Y:%.3f, Z:%.3f" % tuple(self.data['imu'].accelerometer_m_s2))
        else: print("[IMU]: Bekleniyor...")
            
        # GPS
        if self.data['gps']:
            # SensorGps usually has latitude_deg, longitude_deg, altitude_msl_m
            print("[GPS]:       Lat:%.6f, Lon:%.6f, Alt:%.2f" % (
                getattr(self.data['gps'], 'latitude_deg', 0.0), 
                getattr(self.data['gps'], 'longitude_deg', 0.0), 
                getattr(self.data['gps'], 'altitude_msl_m', 0.0)))
        else: print("[GPS]: Bekleniyor...")
            
        # Barometer
        if self.data['air']:
            print("[BARO]:      Basınç:%.2f hPa, Sıcaklık:%.2f C" % (self.data['air'].baro_pressure_pa/100, self.data['air'].baro_temp_celcius))
        else: print("[BARO]: Bekleniyor...")
            
        # EKF
        if self.data['ekf']:
            print("[EKF Alt]:   Z(Local):%.2f m, DistBottom:%.2f m" % (self.data['ekf'].z, self.data['ekf'].dist_bottom))
        else: print("[EKF]: Bekleniyor...")
            
        print("-"*50)
        print("Çıkmak için Ctrl+C")

def main(args=None):
    rclpy.init(args=args)
    node = SensorSuiteTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
