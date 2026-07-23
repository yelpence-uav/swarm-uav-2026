"""gorev1.launch.py — Görev 1 dinamik sürü tam yığın başlatıcı."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _spawn(context, *args, **kwargs):
    """num_drones'a göre sürü-geneli + per-drone düğümlerini üretir."""
    n = int(LaunchConfiguration('num_drones').perform(context))
    team = LaunchConfiguration('team_id').perform(context)
    sitl = LaunchConfiguration('sitl_mode').perform(context).lower() == 'true'
    o_lat = float(LaunchConfiguration('origin_lat').perform(context))
    o_lon = float(LaunchConfiguration('origin_lon').perform(context))
    o_alt = float(LaunchConfiguration('origin_alt').perform(context))
    ids = list(range(1, n + 1))

    nodes = []

    # --- Sürü-geneli düğümler (tek örnek) ---
    nodes += [
        Node(
            package='swarm_state_machine', executable='swarm_fsm_node',
            name='swarm_fsm',
            parameters=[{'agent_count': n, 'sitl_mode': sitl}],
        ),
        # mission_fsm hibrit-dağıtıkta liderde çalışır; SITL'de tek örnek
        # görev beyni olarak yeterli (lider-failover restart'ı sim dışı konu).
        Node(
            package='swarm_state_machine', executable='mission_fsm_node',
            name='mission_fsm',
            parameters=[{'agent_ids': ids, 'team_id': team,
                         'sitl_mode': sitl}],
        ),
        Node(
            package='swarm_core', executable='task_reallocator_node',
            name='task_reallocator',
            parameters=[{'agent_ids': ids}],
        ),
        # path_planner sürü-geneli: /swarm/path_planning/target'ı okur,
        # /swarm/internal/formation/target'a akıtır (agent_id'siz).
        Node(
            package='swarm_core', executable='path_planner',
            name='path_planner',
        ),
        # NED çapası (origin). SITL için fixed_lat/lon sim spawn GPS'ine
        # göre ayarlanmalı — aksi halde NED çözümü kaymalı olur.
        Node(
            package='swarm_control', executable='swarm_origin_publisher',
            name='swarm_origin',
            parameters=[{'origin_source': 'fixed',
                         'fixed_lat': o_lat, 'fixed_lon': o_lon,
                         'fixed_alt': o_alt}],
        ),
    ]

    # --- Per-drone düğümler ---
    for i in ids:
        neighbors = [j for j in ids if j != i]
        nodes += [
            Node(
                package='swarm_control', executable='px4_bridge',
                name=f'px4_bridge_{i}',
                # velocity_only: PX4'e yalnız hız gider (C modu). Konum
                # kontrolü SVT'de; PX4'ün konum kontrolcüsüyle çakışmaz ve
                # paylaşılan koordinat PX4'e lokal sanılarak gönderilmez.
                parameters=[{'agent_id': i, 'sitl_mode': sitl,
                             'velocity_only': True}],
            ),
            Node(
                package='swarm_perception', executable='kinematic_fusion',
                name=f'kinematic_fusion_{i}',
                parameters=[{'agent_id': i, 'neighbor_ids': neighbors}],
            ),
            Node(
                package='swarm_core', executable='consensus_node',
                name=f'consensus_{i}',
                parameters=[{'agent_id': i, 'agent_count': n}],
            ),
            Node(
                package='swarm_state_machine', executable='agent_fsm_node',
                name=f'agent_fsm_{i}',
                parameters=[{'agent_id': i, 'sitl_mode': sitl}],
            ),
            Node(
                package='swarm_core', executable='formation_node',
                name=f'formation_{i}',
                parameters=[{'agent_id': i}],
            ),
            Node(
                package='swarm_core', executable='collision_avoidance',
                name=f'collision_avoidance_{i}',
                parameters=[{'agent_id': i, 'neighbor_ids': neighbors}],
            ),
            Node(
                package='swarm_core', executable='maneuver_executor',
                name=f'maneuver_executor_{i}',
                parameters=[{'agent_id': i}],
            ),
            Node(
                package='swarm_core', executable='precision_landing_node',
                name=f'precision_landing_{i}',
                parameters=[{'agent_id': i}],
            ),
            Node(
                package='swarm_perception', executable='vision_node',
                name=f'vision_{i}',
                parameters=[{'agent_id': i, 'sitl_mode': sitl}],
            ),
            Node(
                package='swarm_missions',
                executable='mission1_dynamic_swarm',
                name=f'mission1_{i}',
                parameters=[{'agent_id': i, 'agent_ids': ids,
                             'team_id': team}],
            ),
        ]
    return nodes


def generate_launch_description():
    """Launch argümanlarını tanımlar ve düğüm üreticisini bağlar."""
    return LaunchDescription([
        DeclareLaunchArgument('num_drones', default_value='3'),
        DeclareLaunchArgument('team_id', default_value=''),
        DeclareLaunchArgument('sitl_mode', default_value='true'),
        # SwarmOrigin, Gazebo dünyasının GPS orijini (SDF spherical_coordinates)
        # ile BİREBİR aynı olmalı. Aksi halde paylaşılan-NED çerçevesi dünyaya
        # göre kayar: QR konumları dünya-referanslı verildiğinden sürü her QR'ın
        # sabit bir ofset kadar yanına gider, üstelik kendi çerçevesinde "vardım"
        # der (yaşanan bug: 41.0441269 → dünya 41.0441 ile arasında ~3 m kuzey
        # kayması vardı; dron QR'ın 3 m yanında duruyordu, kamera QR'ı görmüyordu).
        DeclareLaunchArgument('origin_lat', default_value='41.0441'),
        DeclareLaunchArgument('origin_lon', default_value='29.0017'),
        DeclareLaunchArgument('origin_alt', default_value='0.48'),
        OpaqueFunction(function=_spawn),
    ])
