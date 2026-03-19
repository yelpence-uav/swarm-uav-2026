from setuptools import find_packages, setup

package_name = 'swarm'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name, ['swarm/swarm_launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpence',
    maintainer_email='iletisim@yelpence.com',
    description='Yelpence Takimi Suru Algoritmalari Paketi',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'swarm_launch = swarm.swarm_launch:main',
            'lidar_relay = swarm.lidar_relay:main',
            'camera_relay = swarm.camera_relay:main',
            'tof_relay = swarm.tof_relay:main',
        ],
    },
)
