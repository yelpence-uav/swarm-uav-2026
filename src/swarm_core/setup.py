from setuptools import find_packages, setup

package_name = 'swarm_core'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpence TEKNOFEST 2026',
    maintainer_email='kocakseydagul@gmail.com',
    description='Swarm UAV control core modules',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'formation_node = '
            'swarm_core.formation_control.formation_node:main',
            'formation_test_publisher = '
            'swarm_core.formation_control'
            '.formation_test_publisher:main',
            'collision_avoidance = '
            'swarm_core.collision_avoidance'
            '.collision_avoidance_node:main',
            'path_planner = '
            'swarm_core.path_planning.path_planner_node:main',
            'maneuver_executor = '
            'swarm_core.maneuver_executor.maneuver_executor_node:main',
            'consensus_node = '
            'swarm_core.consensus.consensus_node:main',
            'precision_landing_node = '
            'swarm_core.precision_landing'
            '.precision_landing_node:main',
            'task_reallocator_node = '
            'swarm_core.task_reallocator.task_reallocator_node:main',
        ],
    },
)
