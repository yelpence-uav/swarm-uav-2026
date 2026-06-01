from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'swarm_perception'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpence TEKNOFEST 2026',
    maintainer_email='kocakseydagul@gmail.com',
    description='Camera driver, vision processing and kinematic fusion for swarm UAVs',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_driver = swarm_perception.camera_driver.camera_driver_node:main',
            'vision_node = swarm_perception.vision_node.vision_node_core:main',
        ],
    },
)
