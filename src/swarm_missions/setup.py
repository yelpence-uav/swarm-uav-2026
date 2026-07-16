import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'swarm_missions'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
         glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpence TEKNOFEST 2026',
    maintainer_email='kocakseydagul@gmail.com',
    description='Sürü görev orkestrasyonu: Görev 1 dinamik sürü akışı.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mission1_dynamic_swarm = '
            'swarm_missions.mission1_dynamic_swarm.mission1_node:main',
        ],
    },
)
