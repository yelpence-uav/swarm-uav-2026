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
    description='Swarm UAV control core: formation control, consensus, collision avoidance, path planning',
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
        ],
    },
)
