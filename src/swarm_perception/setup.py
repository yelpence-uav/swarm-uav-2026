"""swarm_perception paketi icin kurulum ayari."""

from setuptools import find_packages, setup

package_name = 'swarm_perception'

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
    description='Suru algilama paketi',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'kinematic_fusion = '
            'swarm_perception.kinematic_fusion.kinematic_fusion_node:main',
            'camera_driver = '
            'swarm_perception.camera_driver.camera_driver_node:main',
            'vision_node = '
            'swarm_perception.vision_node.vision_node_core:main',
        ],
    },
)
