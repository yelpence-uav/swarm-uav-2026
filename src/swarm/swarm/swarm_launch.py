#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import signal
import math
import random

WORKSPACE = "/home/yelpence/ros2_ws"
PX4_PATH = os.path.join(WORKSPACE, "src/PX4-Autopilot")
WORLDS_DIR = os.path.join(WORKSPACE, "sim/worlds")
MODELS_PATH = os.path.join(WORKSPACE, "sim/models")

def cleanup():
    print("\n--- Eski süreçler temizleniyor... ---")
    processes_to_kill = [
        "web_gui_server",
        "lidar_relay",
        "camera_relay",
        "tof_relay",
        "chaos_network",
        "MicroXRCEAgent",
        "ros_gz_bridge",
        "parameter_bridge",
        "px4",
        "xterm",
        "gz"
    ]
    for proc in processes_to_kill:
        if proc == "gz":
            subprocess.run("pkill -9 -f 'gz sim'", shell=True, stderr=subprocess.DEVNULL)
            subprocess.run("killall -9 ruby", shell=True, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-9", "-f", proc], stderr=subprocess.DEVNULL)
    
    # Force kill any remaining bridge processes 
    subprocess.run("pkill -9 -f parameter_bridge", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run("pkill -9 -f ros_gz_bridge", shell=True, stderr=subprocess.DEVNULL)
    
    # Remove stale PX4 lock files and sockets
    subprocess.run("rm -f /tmp/px4-sock-* /tmp/px4_lock-*", shell=True, stderr=subprocess.DEVNULL)
    
    time.sleep(2)

def run_in_xterm(command, title, log_name=None):
    os.makedirs("/home/yelpence/ros2_ws/logs", exist_ok=True)
    # Ensure ROS is sourced in every spawned xterm
    if log_name:
        inner_cmd = f"source /opt/ros/jazzy/setup.bash && source {WORKSPACE}/install/setup.bash && {command} 2>&1 | tee /home/yelpence/ros2_ws/logs/{log_name}.log"
    else:
        inner_cmd = f"source /opt/ros/jazzy/setup.bash && source {WORKSPACE}/install/setup.bash && {command}"
    
    full_cmd = ["xterm", "-hold", "-T", title, "-e", "bash", "-c", inner_cmd]
    return subprocess.Popen(full_cmd)

def run_background(command, log_name):
    os.makedirs("/home/yelpence/ros2_ws/logs", exist_ok=True)
    full_cmd = f"source /opt/ros/jazzy/setup.bash && source {WORKSPACE}/install/setup.bash && {command} >> /home/yelpence/ros2_ws/logs/{log_name}.log 2>&1"
    return subprocess.Popen(["bash", "-c", full_cmd])

def get_worlds(worlds_dir):
    if not os.path.exists(worlds_dir):
        return []
    worlds = [f for f in os.listdir(worlds_dir) if f.endswith('.sdf')]
    return sorted(worlds)

def generate_spawn_sdf(world_path, drone_count):
    if not os.path.exists(world_path):
        print(f"HATA: {world_path} bulunamadı!")
        return None
    with open(world_path, 'r') as f:
        content = f.read()

    import random
    spawn_elements = ""
    used_positions = [] # (x, y) listesi
    
    for i in range(drone_count):
        drone_name = f"IHA_{i+1}"
        
        # YENİ DÜZEN: Dronlar X=0 hizasında, Y ekseninde 3'er metre arayla dizilir.
        x = 0.0
        y = i * 3.0 
            
        spawn_elements += f"""
    <include>
      <name>{drone_name}</name>
      <uri>model://x500_lidar_down</uri>
      <pose>{x} {y} 0.2 0 0 0</pose>
    </include>
"""

    insertion_point = content.rfind("</world>")
    if insertion_point == -1:
        return None
        
    final_content = content[:insertion_point] + spawn_elements + content[insertion_point:]
    
    tmp_world = "/tmp/swarm_tmp_world.sdf"
    with open(tmp_world, 'w') as f:
        f.write(final_content)
    return tmp_world

def main():
    cleanup()

    # GZ_SIM_RESOURCE_PATH ayarı
    ros_share = "/opt/ros/jazzy/share"
    px4_gz_models = os.path.join(PX4_PATH, "Tools/simulation/gz/models")
    px4_gz_worlds = os.path.join(PX4_PATH, "Tools/simulation/gz/worlds")
    
    current_path = os.environ.get('GZ_SIM_RESOURCE_PATH', '')
    new_path = f"{MODELS_PATH}:{px4_gz_models}:{px4_gz_worlds}:{ros_share}:{current_path}"
    os.environ['GZ_SIM_RESOURCE_PATH'] = new_path
    print(f">> GZ_SIM_RESOURCE_PATH güncellendi.")

    worlds = get_worlds(WORLDS_DIR)
    if not worlds:
        print(f"HATA: {WORLDS_DIR} dizininde dünya bulunamadı!")
        return

    print("\n--- YELPENÇE SÜRÜ SİMÜLASYONU BAŞLATICI ---")
    print("Mevcut Dünyalar:")
    for idx, w in enumerate(worlds):
        print(f"[{idx+1}] {w}")

    try:
        if "--headless" in sys.argv:
            world_idx = 0
            drone_count = 5
            print(f"\nHeadless mod aktif. Varsayılan dünya ({worlds[0]}) ve 5 drone seçildi.")
        else:
            world_sel = input(f"\nDünya seçin (numara, varsayılan 1): ") or "1"
            world_idx = int(world_sel) - 1
            drone_count = int(input("Kaç adet drone spawn edilecek? (varsayılan 1): ") or "1")
    except (ValueError, EOFError):
        print("\nGirdi alınamadı veya arkaplanda çalışıyor. Varsayılan (1. dünya, 5 drone) seçildi.")
        world_idx = 0
        drone_count = 5

    selected_world = os.path.join(WORLDS_DIR, worlds[world_idx])
    world_name = worlds[world_idx].replace('.sdf', '')
    tmp_world = generate_spawn_sdf(selected_world, drone_count)
    
    # 0. Gazebo Simulation (Arka planda başlat)
    print(f">> Gazebo '{worlds[world_idx]}' dünyası ile arkaplanda başlatılıyor...")
    # Sourcing ROS to get 'gz' command in PATH
    gz_cmd = f"source /opt/ros/jazzy/setup.bash && gz sim -r {tmp_world}"
    if "--headless" in sys.argv:
        gz_cmd += " -s" # Server only mode for headless
    
    gz_env = os.environ.copy()
    gz_env['GZ_SIM_RESOURCE_PATH'] = new_path
    gz_proc = subprocess.Popen(["bash", "-c", gz_cmd], env=gz_env)
    
    print(">> Gazebo'nun açılması bekleniyor (10 saniye)...")
    time.sleep(10)

    # 1. MicroXRCEAgent
    print(">> DDS Agent başlatılıyor...")
    run_in_xterm("MicroXRCEAgent udp4 -p 8888 -v 4", "DDS Agent", "dds_agent")
    time.sleep(2)

    # 2. Sensor bridges (Her drone için ayrı bridge)
    print(f">> {drone_count} adet Sensor Bridge başlatılıyor...")
    for i in range(drone_count):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"
        # Full absolute scoped Gazebo topics (Harmonic requirement for reliability)
        lidar_gz = f"/world/{world_name}/model/{drone_name}/link/lidar_sensor_link/sensor/lidar/scan"
        image_gz = f"/world/{world_name}/model/{drone_name}/link/camera_link/sensor/camera/image"
        
        # Clean ROS 2 topics
        lidar_ros = f"/drone_{drone_id}/lidar/scan"
        image_ros = f"/drone_{drone_id}/camera/image_raw"

        # CLI Bridge Command (Using @ delimiter for types, more shell-safe than [)
        cmd = f"ros2 run ros_gz_bridge parameter_bridge "
        cmd += f"'{lidar_gz}@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan' "
        cmd += f"'{image_gz}@sensor_msgs/msg/Image@gz.msgs.Image' "
        
        # 4x ToF Sensors
        for side in ['front', 'back', 'left', 'right']:
            gz_tof = f"/world/{world_name}/model/{drone_name}/link/tof_{side}_link/sensor/tof_{side}/scan"
            ros_tof = f"/drone_{drone_id}/tof/{side}"
            cmd += f"'{gz_tof}@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan' "
        
        # Remappings
        cmd += f"--ros-args -r '{lidar_gz}:={lidar_ros}' -r '{image_gz}:={image_ros}' "
        for side in ['front', 'back', 'left', 'right']:
            gz_tof = f"/world/{world_name}/model/{drone_name}/link/tof_{side}_link/sensor/tof_{side}/scan"
            ros_tof = f"/drone_{drone_id}/tof/{side}"
            cmd += f"-r '{gz_tof}:={ros_tof}' "
        
        run_background(cmd, f"bridge_{drone_id}")

    # 3. PX4 Instances
    print(f">> {drone_count} adet PX4 SITL başlatılıyor...")
    for i in range(drone_count):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"
        # PX4 SITL başlatma - ensure we are in PX4_PATH and use the built binary
        inner_cmd = (
            f"cd {PX4_PATH} && "
            f"export PX4_SYS_AUTOSTART=4016 && "
            f"export PX4_UXRCE_DDS_NS=drone_{drone_id} && "
            f"export PX4_GZ_MODEL_NAME={drone_name} && "
            f"export PX4_GZ_STANDALONE=1 && "
            f"export PX4_GZ_WORLD={world_name} && "
            f"./build/px4_sitl_default/bin/px4 -i {drone_id}"
        )
        run_in_xterm(inner_cmd, f"PX4 Drone {drone_id}", f"px4_{drone_id}")
        time.sleep(1)

        # 3. Parametreleri ayarla (Arming için GCS/RC gereksinimini ve Batarya kontrolünü devre dışı bırak)
        print(f">> Drone {drone_id} (İHA_{drone_id}) parametreleri yapılandırılıyor (Instance: {drone_id})...")
        param_cmds = [
            f"px4-param --instance {drone_id} set MAV_SYS_ID {drone_id}",
            f"px4-param --instance {drone_id} set COM_RCL_EXCEPT 4",
            f"px4-param --instance {drone_id} set NAV_RCL_ACT 0",
            f"px4-param --instance {drone_id} set NAV_DLL_ACT 0",
            f"px4-param --instance {drone_id} set SIM_BAT_ENABLE 0",
            f"px4-param --instance {drone_id} set CBRK_SUPPLY_CHK 894281",
            f"px4-param --instance {drone_id} set COM_RC_IN_MODE 4",
            f"px4-param --instance {drone_id} set EKF2_MAG_TYPE 0",
            f"px4-param --instance {drone_id} set EKF2_MAG_NOISE 0.5",
            f"px4-param --instance {drone_id} set COM_ARM_EKF_YAW 1.0",
            f"px4-param --instance {drone_id} set EKF2_DECL_TYPE 0",
            f"px4-param --instance {drone_id} set EKF2_HGT_MODE 0",
            f"px4-param --instance {drone_id} set CBRK_MAG_CHK 894281",
            f"px4-param --instance {drone_id} set CBRK_USB_CHK 894281",
            f"px4-param --instance {drone_id} set CBRK_IO_SAFETY 22027",
            f"px4-param --instance {drone_id} set COM_ARM_WO_GPS 1",
            f"px4-param --instance {drone_id} set COM_ARM_CHK_ESCS 0",
            f"px4-param --instance {drone_id} set CBRK_BUZZER 782097",
            f"px4-param --instance {drone_id} set COM_POWER_COUNT 0",
            f"px4-param --instance {drone_id} set COM_ARM_IMU_ACC 1.0",
            f"px4-param --instance {drone_id} set COM_ARM_IMU_GYR 0.7",
            f"px4-param --instance {drone_id} set MIS_TAKEOFF_ALT 2.5",
            f"px4-param --instance {drone_id} set MPC_XY_P 0.5",
            f"px4-param --instance {drone_id} set MPC_Z_P 0.6",
            f"px4-param --instance {drone_id} set MPC_TKO_SPEED 0.8",
            f"px4-param --instance {drone_id} set COM_DISARM_PRFLT -1",
            f"px4-param --instance {drone_id} set COM_DISARM_LAND 2.0"
        ]
        for cmd in param_cmds :
            full_param_cmd = f"source /opt/ros/jazzy/setup.bash && {PX4_PATH}/build/px4_sitl_default/bin/{cmd}"
            res = subprocess.run(["bash", "-c", full_param_cmd], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"   [OK] {cmd}")
            else:
                print(f"   [ERR] {cmd} : {res.stderr.strip()}")
        
        # Bazı parametreler (COM_RC_IN_MODE) reboot gerektirir — PX4'ü yeniden başlat
        print(f"   >> PX4 Instance {drone_id} yeniden başlatılıyor (param reload)...")
        reboot_cmd = f"source /opt/ros/jazzy/setup.bash && {PX4_PATH}/build/px4_sitl_default/bin/px4-commander --instance {drone_id} reboot"
        subprocess.run(["bash", "-c", reboot_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)  # PX4'ün yeniden başlamasını bekle


    # 4.1 Lidar and Camera Relays (Sensor Management)
    print(f">> {drone_count} adet Lidar ve Kamera Relay başlatılıyor...")
    run_background(f"ros2 run swarm lidar_relay {drone_count}", "lidar_relay")
    run_background(f"ros2 run swarm camera_relay {drone_count}", "camera_relay")
    run_background(f"ros2 run swarm tof_relay {drone_count}", "tof_relay")

    # 4.5 Chaos Network & Collision Avoidance
    print(">> Chaos Network ve Çarpışma Önleyici başlatılıyor...")
    run_background(f"ros2 run network chaos_network {drone_count}", "chaos_network")
    run_background(f"ros2 run swarm collision_avoidance {drone_count}", "collision_avoidance")
    run_background(f"ros2 run swarm manual_control", "manual_control")

    # 4.6 QGroundControl
    print(">> QGroundControl başlatılıyor...")
    run_in_xterm("/home/yelpence/ros2_ws/tools/QGroundControl.AppImage --appimage-extract-and-run", "QGroundControl", "qgc")

    # 5. Web GUI
    print(">> Web GUI Sunucusu başlatılıyor...")
    run_in_xterm(f"export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && ros2 run gcs web_gui_server --count {drone_count}", "Web GUI Server", "web_gui")

    try:
        gz_proc.wait()
    except KeyboardInterrupt:
        cleanup()
        print("\nSonlandırıldı.")

if __name__ == "__main__":
    main()
