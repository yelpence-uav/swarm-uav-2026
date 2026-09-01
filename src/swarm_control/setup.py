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
    maintainer='Yelpençe Takımı',
    maintainer_email='osmancevik@pm.me',
    description='PX4 interface bridge',
    license='MIT',
    entry_points={
        'console_scripts': [
            'px4_bridge = '
            'swarm_control.px4_interface.px4_bridge:main',
            'swarm_origin_publisher = '
            'swarm_control.swarm_origin_publisher:main',
            'esp32_bridge = '
            'swarm_control.esp32_bridge.esp32_bridge_node:main',
            'ic_dis_kopru = '
            'swarm_control.ic_dis_kopru:main',
            'rc_ibus_kopru = '
            'swarm_control.rc_ibus.rc_ibus_kopru_node:main',
            'ina226_node = '
            'swarm_control.pil.ina226_node:main',
        ],
    },
)
