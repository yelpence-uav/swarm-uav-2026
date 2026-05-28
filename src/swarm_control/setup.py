from setuptools import find_packages, setup

package_name = 'swarm_control'

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
    description='PX4 interface bridge',
    license='MIT',
    entry_points={
        'console_scripts': [
            'px4_bridge = swarm_control.px4_interface.px4_bridge:main',
            'swarm_origin_publisher = swarm_control.swarm_origin_publisher:main',
        ],
    },
)
