#!/usr/bin/env python3
"""
Yelpençe Takımı Sürü İHA Simülasyon Başlatıcısı (Tmux & Gazebo GUI)
Bu script ROS 2, Gazebo Harmonic ve PX4 kullanarak
3 adet İHA'yı belirlenen geçici dünyada başlatır.
Gazebo 3D arayüzü açılır ve süreçler Tmux sekmelerinden yönetilir.
"""

import os
import subprocess
import time
import tempfile
import glob
import shutil

WORKSPACE = "/home/yelpence/ros2_ws"
PX4_PATH = os.path.join(WORKSPACE, "src/px4_autopilot")
MODELS_PATH = os.path.join(WORKSPACE, "sim/models")
DEFAULT_WORLD = os.path.join(WORKSPACE, "sim/worlds/task1_dynamic_swarm.sdf")

TMP_WORLD = os.path.join(tempfile.gettempdir(), "swarm_tmp_world.sdf")
DRONE_COUNT = 3
TMUX_SESSION = "yelpence_swarm"


def cleanup():
    """Arka planda kalmış eski süreçleri ve tmux oturumlarını temizler."""
    print("\n--- Eski süreçler temizleniyor... ---")

    subprocess.run(
        ["tmux", "kill-session", "-t", TMUX_SESSION],
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )

    processes_to_kill = [
        "camera_relay",
        "MicroXRCEAgent",
        "ros_gz_bridge",
        "parameter_bridge",
        "px4",
        "network_proxy_node",
    ]

    subprocess.run(["pkill", "-9", "-f", "gz sim"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ruby"], stderr=subprocess.DEVNULL)

    for proc in processes_to_kill:
        subprocess.run(["pkill", "-9", "-f", proc], stderr=subprocess.DEVNULL)

    subprocess.run(["pkill", "-9", "-f", "parameter_bridge"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "ros_gz_bridge"], stderr=subprocess.DEVNULL)

    tmp_dir = tempfile.gettempdir()
    px4_files = glob.glob(os.path.join(tmp_dir, "px4-sock-*")) + glob.glob(
        os.path.join(tmp_dir, "px4_lock-*")
    )
    for f in px4_files:
        try:
            os.remove(f)
        except OSError:
            pass

    rootfs_path = os.path.join(PX4_PATH, "build/px4_sitl_default/rootfs")
    if os.path.exists(rootfs_path):
        for item in os.listdir(rootfs_path):
            item_path = os.path.join(rootfs_path, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except OSError:
                pass

    time.sleep(2)


def init_tmux_session():
    """Tmux oturumunu arka planda başlatır ve fare/scroll desteğini açar."""
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", TMUX_SESSION, "-n", "Main", "bash"]
    )
    subprocess.run(["tmux", "set-option", "-g", "mouse", "on"])


def run_in_tmux(command, title, log_name=None):
    """
    Verilen komutu tmux oturumunda yeni bir sekme (window) açarak çalıştırır.
    """
    os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
    setup_cmd = (
        f"source /opt/ros/jazzy/setup.bash && " f"source {WORKSPACE}/install/setup.bash"
    )

    if log_name:
        log_path = os.path.join(WORKSPACE, f"logs/{log_name}.log")
        inner_cmd = f"{setup_cmd} && {command} 2>&1 | tee {log_path}"
    else:
        inner_cmd = f"{setup_cmd} && {command}"

    tmux_cmd = [
        "tmux",
        "new-window",
        "-t",
        TMUX_SESSION,
        "-n",
        title,
        f'bash -c "{inner_cmd}; exec bash"',
    ]
    subprocess.run(tmux_cmd)


def run_background(command, log_name):
    """Verilen komutu doğrudan arka planda çalıştırır ve loglar."""
    os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
    log_path = os.path.join(WORKSPACE, f"logs/{log_name}.log")

    full_cmd = (
        f"source /opt/ros/jazzy/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && "
        f"{command} >> {log_path} 2>&1"
    )
    return subprocess.Popen(["bash", "-c", full_cmd])


def generate_spawn_sdf(world_path, drone_count):
    """SDF dosyasını güncelleyerek ajanları dinamik olarak yerleştirir."""
    if not os.path.exists(world_path):
        print(f"HATA: {world_path} bulunamadı!")
        return None

    with open(world_path, "r") as f:
        content = f.read()

    spawn_elements = ""
    for i in range(drone_count):
        drone_name = f"IHA_{i+1}"
        x = 0.0
        y = i * 3.0

        spawn_elements += f"""
    <include>
      <name>{drone_name}</name>
      <uri>model://x500</uri>
      <pose>{x} {y} 0.2 0 0 0</pose>
    </include>
"""

    insertion_point = content.rfind("</world>")
    if insertion_point == -1:
        return None

    final_content = (
        content[:insertion_point] + spawn_elements + content[insertion_point:]
    )

    with open(TMP_WORLD, "w") as f:
        f.write(final_content)

    return TMP_WORLD


def setup_gazebo_env():
    """Gazebo için model ve dünya dizinlerini bağlar."""
    ros_share = "/opt/ros/jazzy/share"
    px4_models = os.path.join(PX4_PATH, "Tools/simulation/gz/models")
    px4_worlds = os.path.join(PX4_PATH, "Tools/simulation/gz/worlds")

    current_path = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    new_path = f"{MODELS_PATH}:{px4_models}:{px4_worlds}:{ros_share}:{current_path}"
    os.environ["GZ_SIM_RESOURCE_PATH"] = new_path

    return new_path


def main():
    cleanup()
    init_tmux_session()

    print("\n--- YELPENÇE SÜRÜ SİMÜLASYONU BAŞLATICI ---")
    gazebo_env_path = setup_gazebo_env()

    # 1. SDF Dosyasının Üretilmesi
    generated_world = generate_spawn_sdf(DEFAULT_WORLD, DRONE_COUNT)
    if not generated_world:
        print("Geçici dosya oluşturulamadı. İşlem sonlandırılıyor.")
        return

    world_name = "task1_dynamic_swarm"

    # 2. Gazebo Simülasyonunu Geçici Dünya İle Başlatma
    # -s parametresi kaldırılarak [3] Gazebo'nun 3D arayüzünün görsel olarak açılması sağlandı.
    print(f">> Gazebo '{world_name}' dünyası görsel arayüz (GUI) ile başlatılıyor...")
    gz_cmd = f"source /opt/ros/jazzy/setup.bash && gz sim -r {generated_world}"

    gz_env = os.environ.copy()
    gz_env["GZ_SIM_RESOURCE_PATH"] = gazebo_env_path
    gz_proc = subprocess.Popen(["bash", "-c", gz_cmd], env=gz_env)

    time.sleep(10)  # Gazebonun ayağa kalkmasını bekle

    # 3. MicroXRCEAgent Haberleşme Köprüsü
    print(">> DDS Agent Tmux üzerinde başlatılıyor...")
    run_in_tmux("MicroXRCEAgent udp4 -p 8888 -v 4", "DDS_Agent", "dds_agent")
    time.sleep(2)

    # 4. Kamera Sensör Köprüleri
    print(f">> {DRONE_COUNT} adet Kamera Köprüsü (Arkaplan) başlatılıyor...")
    for i in range(DRONE_COUNT):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"

        image_gz = (
            f"/world/{world_name}/model/{drone_name}"
            f"/link/camera_link/sensor/camera/image"
        )
        image_ros = f"/drone_{drone_id}/camera/image_raw"

        cmd = (
            f"ros2 run ros_gz_bridge parameter_bridge "
            f"'{image_gz}@sensor_msgs/msg/Image@gz.msgs.Image' "
            f"--ros-args -r '{image_gz}:={image_ros}'"
        )
        run_background(cmd, f"bridge_{drone_id}")

    # 5. PX4 SITL Örnekleri
    print(f">> {DRONE_COUNT} adet PX4 SITL Tmux sekmelerine ekleniyor...")
    for i in range(DRONE_COUNT):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"

        inner_cmd = (
            f"cd {PX4_PATH} && "
            f"export PX4_SYS_AUTOSTART=4001 && "
            f"export PX4_SIM_MODEL=gz_x500 && "
            f"export PX4_UXRCE_DDS_NS=drone_{drone_id} && "
            f"export PX4_GZ_MODEL_NAME={drone_name} && "
            f"export PX4_GZ_STANDALONE=1 && "
            f"export PX4_GZ_WORLD={world_name} && "
            f"export PX4_SIM_SYNC=0 && "
            f"./build/px4_sitl_default/bin/px4 -i {drone_id}"
        )

        run_in_tmux(inner_cmd, f"PX4_{drone_id}")
        time.sleep(1)

        print(f"   >> Drone {drone_id} parametreleri yükleniyor...")
        param_cmds = [
            f"px4-param --instance {drone_id} set MAV_SYS_ID {drone_id}",
            f"px4-param --instance {drone_id} set COM_RCL_EXCEPT 4",
            f"px4-param --instance {drone_id} set NAV_RCL_ACT 0",
            f"px4-param --instance {drone_id} set NAV_DLL_ACT 0",
            f"px4-param --instance {drone_id} set SIM_BAT_ENABLE 0",
            f"px4-param --instance {drone_id} set CBRK_SUPPLY_CHK 894281",
            f"px4-param --instance {drone_id} set COM_RC_IN_MODE 4",
            f"px4-param --instance {drone_id} set COM_ARM_WO_GPS 1",
            f"px4-param --instance {drone_id} set COM_ARM_CHK_ESCS 0",
            f"px4-param --instance {drone_id} set CBRK_IO_SAFETY 22027",
            f"px4-param --instance {drone_id} set MIS_TAKEOFF_ALT 2.5",
        ]

        for cmd in param_cmds:
            full_param_cmd = (
                f"source /opt/ros/jazzy/setup.bash && "
                f"{PX4_PATH}/build/px4_sitl_default/bin/{cmd}"
            )
            subprocess.run(
                ["bash", "-c", full_param_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        reboot_cmd = (
            f"source /opt/ros/jazzy/setup.bash && "
            f"{PX4_PATH}/build/px4_sitl_default/bin/px4-commander "
            f"--instance {drone_id} reboot"
        )
        subprocess.run(
            ["bash", "-c", reboot_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

    # 6. Kamera Relay Yazılımı
    print(">> Kamera Relay Düğümü başlatılıyor...")
    run_background(f"ros2 run swarm camera_relay {DRONE_COUNT}", "camera_relay")

    # 7. RTK Yönetimi (Dahili C++ kodunda halledildiği için iptal edildi)
    # print(">> RTK Baz İstasyonu Köprüsü ve Manager başlatılıyor...")
    # rtk_gz_topic = f"/world/{world_name}/model/rtk_base_station/link/base_link/sensor/navsat_sensor/navsat"
    # rtk_ros_topic = "/rtk_base/navsat"
    # rtk_bridge_cmd = (
    #     f"ros2 run ros_gz_bridge parameter_bridge "
    #     f"'{rtk_gz_topic}@sensor_msgs/msg/NavSatFix[gz.msgs.NavSat' "
    #     f"--ros-args -r '{rtk_gz_topic}:={rtk_ros_topic}'"
    # )
    # run_background(rtk_bridge_cmd, "rtk_bridge")
    # run_background("python3 scripts/rtk_manager.py", "rtk_manager")

    # 8. ESP-NOW Ağ Simülatörü (Network Proxy)
    print(">> ESP-NOW Ağ Köprüsü Tmux üzerinde başlatılıyor...")
    run_in_tmux(
        "ros2 run network_proxy network_proxy_node", "Network_Proxy", "network_proxy"
    )

    # 9. Sim RTCM Kaynağı (her drone için)
    # YALNIZCA-SIM: sim_rtcm_source /drone_{id}/rtcm/in girişini besler.
    # RTK köprüsü artık px4_bridge içine alındı; o bu topic'i dinleyip
    # PX4'e GpsInjectData enjekte eder. Ayrı rtk_bridge başlatılmaz.
    # Sahada esp32_bridge bu topic'i besleyecek; bu launch'a EKLENMEZ.
    for drone_id in range(1, DRONE_COUNT + 1):
        print(f">> Sim RTCM Source (drone_{drone_id}) başlatılıyor...")
        run_in_tmux(
            f"ros2 run sim_rtcm_source sim_rtcm_source "
            f"--ros-args -p agent_id:={drone_id} -p mode:=synthetic "
            f"-p publish_hz:=1.0",
            f"SimRTCM_{drone_id}",
            f"sim_rtcm_source_{drone_id}",
        )

    print("\n--- TÜM SİSTEM BAŞARIYLA BAŞLATILDI ---")
    print(f"Süreçleri izlemek için: tmux attach -t {TMUX_SESSION}")
    print("Tmux'tan çıkmak için: Ctrl+b d")
    print("Sistemi kapatmak için: tmux kill-session -t yelpence_swarm")

    try:
        subprocess.run(["tmux", "attach-session", "-t", TMUX_SESSION])
        gz_proc.wait()
    except KeyboardInterrupt:
        cleanup()
        print("\nSistem Kapatıldı.")


if __name__ == "__main__":
    main()
