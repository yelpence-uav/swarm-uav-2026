#!/usr/bin/env python3
"""Yelpençe Takımı Sürü İHA Simülasyon Başlatıcısı."""

import glob
import os
import shutil
import subprocess
import tempfile
import time

WORKSPACE = "/home/yelpence/ros2_ws"
PX4_PATH = os.path.join(WORKSPACE, "src/px4_autopilot")
MODELS_PATH = os.path.join(WORKSPACE, "sim/models")
DEFAULT_WORLD = os.path.join(
    WORKSPACE, "sim/worlds/task1_dynamic_swarm.sdf"
)

TMP_WORLD = os.path.join(tempfile.gettempdir(), "swarm_tmp_world.sdf")
DRONE_COUNT = 3
TMUX_SESSION = "yelpence_swarm"


def cleanup():
    """Eski süreçleri ve tmux oturumlarını temizler."""
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
        "px4_bridge",
        "agent_fsm_node",
        "swarm_fsm_node",
        "mode_manager_node",
        "joystick_interpreter_node",
        "mission_fsm_node",
        "swarm_origin_publisher",
        "formation_node",
        "collision_avoidance",
    ]

    subprocess.run(
        ["pkill", "-9", "-f", "gz sim"], stderr=subprocess.DEVNULL
    )
    subprocess.run(["pkill", "-9", "-f", "ruby"], stderr=subprocess.DEVNULL)

    for proc in processes_to_kill:
        subprocess.run(
            ["pkill", "-9", "-f", proc], stderr=subprocess.DEVNULL
        )

    subprocess.run(
        ["pkill", "-9", "-f", "parameter_bridge"], stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ["pkill", "-9", "-f", "ros_gz_bridge"], stderr=subprocess.DEVNULL
    )

    tmp_dir = tempfile.gettempdir()
    px4_files = glob.glob(
        os.path.join(tmp_dir, "px4-sock-*")
    ) + glob.glob(os.path.join(tmp_dir, "px4_lock-*"))
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
    """Tmux oturumunu başlatır."""
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", TMUX_SESSION, "-n", "Main", "bash"]
    )
    subprocess.run(["tmux", "set-option", "-g", "mouse", "on"])


def run_in_tmux(command, title, log_name=None):
    """Komutu tmux oturumunda çalıştırır."""
    os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
    setup_cmd = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash"
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
    """Komutu arka planda çalıştırır."""
    os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
    log_path = os.path.join(WORKSPACE, f"logs/{log_name}.log")

    full_cmd = (
        "source /opt/ros/jazzy/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && "
        f"{command} >> {log_path} 2>&1"
    )
    return subprocess.Popen(["bash", "-c", full_cmd])


def generate_spawn_sdf(world_path, drone_count):
    """SDF dosyasını güncelleyerek ajanları yerleştirir."""
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
        content[:insertion_point]
        + spawn_elements
        + content[insertion_point:]
    )

    with open(TMP_WORLD, "w") as f:
        f.write(final_content)

    return TMP_WORLD


def setup_gazebo_env():
    """Gazebo model ve dünya dizinlerini ayarlar."""
    ros_share = "/opt/ros/jazzy/share"
    px4_models = os.path.join(PX4_PATH, "Tools/simulation/gz/models")
    px4_worlds = os.path.join(PX4_PATH, "Tools/simulation/gz/worlds")

    current_path = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    new_path = (
        f"{MODELS_PATH}:{px4_models}:{px4_worlds}:{ros_share}:{current_path}"
    )
    os.environ["GZ_SIM_RESOURCE_PATH"] = new_path

    return new_path


def main():
    cleanup()
    init_tmux_session()

    print("\n--- YELPENÇE SÜRÜ SİMÜLASYONU BAŞLATICI ---")
    gazebo_env_path = setup_gazebo_env()

    generated_world = generate_spawn_sdf(DEFAULT_WORLD, DRONE_COUNT)
    if not generated_world:
        print("Geçici dosya oluşturulamadı. İşlem sonlandırılıyor.")
        return

    world_name = "task1_dynamic_swarm"

    print(
        f">> Gazebo '{world_name}' dünyası görsel arayüz ile başlatılıyor..."
    )
    gz_cmd = f"source /opt/ros/jazzy/setup.bash && gz sim -r {generated_world}"

    gz_env = os.environ.copy()
    gz_env["GZ_SIM_RESOURCE_PATH"] = gazebo_env_path
    gz_proc = subprocess.Popen(["bash", "-c", gz_cmd], env=gz_env)

    time.sleep(10)

    print(f">> {DRONE_COUNT} adet Kamera Köprüsü başlatılıyor...")
    for i in range(DRONE_COUNT):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"

        image_gz = (
            f"/world/{world_name}/model/{drone_name}"
            f"/link/camera_link/sensor/camera/image"
        )
        image_ros = f"/drone_{drone_id}/camera/image_raw"

        cmd = (
            "ros2 run ros_gz_bridge parameter_bridge "
            f"'{image_gz}@sensor_msgs/msg/Image@gz.msgs.Image' "
            f"--ros-args -r '{image_gz}:={image_ros}'"
        )
        run_background(cmd, f"bridge_{drone_id}")

    print(f">> {DRONE_COUNT} adet PX4 SITL başlatılıyor...")
    for i in range(DRONE_COUNT):
        drone_id = i + 1
        drone_name = f"IHA_{drone_id}"

        inner_cmd = (
            f"cd {PX4_PATH} && "
            "export PX4_SYS_AUTOSTART=4001 && "
            "export PX4_SIM_MODEL=gz_x500 && "
            f"export PX4_GZ_MODEL_NAME={drone_name} && "
            "export PX4_GZ_STANDALONE=1 && "
            f"export PX4_GZ_WORLD={world_name} && "
            "export PX4_SIM_SYNC=0 && "
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
            f"px4-param --instance {drone_id} set SIM_BAT_ENABLE 1",
            f"px4-param --instance {drone_id} set CBRK_SUPPLY_CHK 894281",
            f"px4-param --instance {drone_id} set COM_RC_IN_MODE 4",
            f"px4-param --instance {drone_id} set COM_ARM_WO_GPS 1",
            f"px4-param --instance {drone_id} set COM_ARM_CHK_ESCS 0",
            f"px4-param --instance {drone_id} set CBRK_IO_SAFETY 22027",
            f"px4-param --instance {drone_id} set MIS_TAKEOFF_ALT 2.5",
            f"px4-param --instance {drone_id} set EKF2_GPS_CHECK 0",
            f"px4-param --instance {drone_id} set COM_ARM_MAG_STR 0",
        ]

        for cmd in param_cmds:
            full_param_cmd = (
                "source /opt/ros/jazzy/setup.bash && "
                f"{PX4_PATH}/build/px4_sitl_default/bin/{cmd}"
            )
            subprocess.run(
                ["bash", "-c", full_param_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        reboot_cmd = (
            "source /opt/ros/jazzy/setup.bash && "
            f"{PX4_PATH}/build/px4_sitl_default/bin/px4-commander "
            f"--instance {drone_id} reboot"
        )
        subprocess.run(
            ["bash", "-c", reboot_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

    print(">> Kamera Relay Düğümü başlatılıyor...")
    run_background(
        f"ros2 run swarm camera_relay {DRONE_COUNT}", "camera_relay"
    )

    print(">> ESP-NOW Ağ Köprüsü başlatılıyor...")
    run_in_tmux(
        "ros2 run network_proxy network_proxy_node",
        "Network_Proxy",
        "network_proxy",
    )

    for drone_id in range(1, DRONE_COUNT + 1):
        print(f">> Sim RTCM Source (drone_{drone_id}) başlatılıyor...")
        run_in_tmux(
            "ros2 run sim_rtcm_source sim_rtcm_source "
            f"--ros-args -p agent_id:={drone_id} -p mode:=synthetic "
            "-p publish_hz:=1.0",
            f"SimRTCM_{drone_id}",
            f"sim_rtcm_source_{drone_id}",
        )

    # ROS 2 sürü düğümleri
    print(f">> {DRONE_COUNT} adet mavros_node başlatılıyor...")
    for drone_id in range(1, DRONE_COUNT + 1):
        fcu = f"udp://:{14540 + drone_id}@127.0.0.1:{14580 + drone_id}"
        run_in_tmux(
            "ros2 run mavros mavros_node --ros-args "
            f"-p fcu_url:={fcu} "
            f"-r __ns:=/drone_{drone_id}/mavros",
            f"Mavros_{drone_id}",
            f"mavros_{drone_id}",
        )
        time.sleep(1)

    print(f">> {DRONE_COUNT} adet PX4 Bridge başlatılıyor...")
    for drone_id in range(1, DRONE_COUNT + 1):
        run_in_tmux(
            "ros2 run swarm_control px4_bridge --ros-args "
            f"-p agent_id:={drone_id} -p sitl_mode:=True "
            f"-r __node:=px4_bridge_{drone_id}",
            f"PX4Bridge_{drone_id}",
            f"px4_bridge_{drone_id}",
        )
        time.sleep(1)

    print(f">> {DRONE_COUNT} adet Agent FSM başlatılıyor...")
    for drone_id in range(1, DRONE_COUNT + 1):
        run_in_tmux(
            "ros2 run swarm_state_machine agent_fsm_node --ros-args "
            f"-p agent_id:={drone_id} -p sitl_mode:=True "
            f"-r __node:=agent_fsm_{drone_id}",
            f"AgentFSM_{drone_id}",
            f"agent_fsm_{drone_id}",
        )
        time.sleep(1)

    print(">> Sürü FSM düğümleri başlatılıyor...")
    run_in_tmux(
        "ros2 run swarm_state_machine swarm_fsm_node --ros-args "
        f"-p agent_count:={DRONE_COUNT} -p sitl_mode:=True",
        "SwarmFSM",
        "swarm_fsm",
    )
    time.sleep(1)
    run_in_tmux(
        "ros2 run swarm_state_machine mode_manager_node --ros-args "
        "-p sitl_mode:=True",
        "ModeManager",
        "mode_manager",
    )
    time.sleep(1)
    run_in_tmux(
        "ros2 run swarm_state_machine joystick_interpreter_node",
        "Joystick",
        "joystick_interpreter",
    )
    time.sleep(1)
    run_in_tmux(
        "ros2 run swarm_state_machine mission_fsm_node --ros-args "
        "-p sitl_mode:=True",
        "MissionFSM",
        "mission_fsm",
    )
    time.sleep(1)

    # Sürü icra düğümleri (swarm_core)
    print(">> SwarmOrigin yayıncısı başlatılıyor...")
    run_in_tmux(
        "ros2 run swarm_control swarm_origin_publisher --ros-args "
        "-p origin_source:=fixed "
        "-p fixed_lat:=41.0441269 -p fixed_lon:=29.0016997 -p fixed_alt:=0.48 "
        "-p rate_hz:=1.0",
        "SwarmOrigin",
        "swarm_origin",
    )
    time.sleep(2)

    print(f">> {DRONE_COUNT} adet Formation Control başlatılıyor...")
    for drone_id in range(1, DRONE_COUNT + 1):
        run_in_tmux(
            "ros2 run swarm_core formation_node --ros-args "
            f"-p agent_id:={drone_id} -r __node:=formation_node_{drone_id}",
            f"Formation_{drone_id}",
            f"formation_{drone_id}",
        )
        time.sleep(1)

    print(f">> {DRONE_COUNT} adet Collision Avoidance başlatılıyor...")
    for drone_id in range(1, DRONE_COUNT + 1):
        neighbor_ids = [j for j in range(1, DRONE_COUNT + 1) if j != drone_id]
        nb = "[" + ",".join(str(j) for j in neighbor_ids) + "]"
        run_in_tmux(
            "ros2 run swarm_core collision_avoidance --ros-args "
            f"-p agent_id:={drone_id} -p neighbor_ids:={nb} "
            f"-r __node:=collision_avoidance_{drone_id}",
            f"CollAvoid_{drone_id}",
            f"collision_avoidance_{drone_id}",
        )
        time.sleep(1)

    print(">> YKİ (GCS) backend başlatılıyor -> http://localhost:8000 ...")
    run_in_tmux(
        f"cd {WORKSPACE}/src/gcs && "
        "uvicorn backend.main:app --host 0.0.0.0 --port 8000",
        "GCS_Backend",
        "gcs_backend",
    )
    time.sleep(2)

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
