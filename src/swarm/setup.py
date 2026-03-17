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
            # Yeni eklenen çalıştırılabilir komut:
            'swarm_controller = swarm.swarm_controller:main',
            'offboard_control = swarm.offboard_control:main',
            'swarm_commander = swarm.swarm_commander:main',
            'swarm_dashboard = swarm.swarm_dashboard:main',
            'chaos_network = swarm.chaos_network:main',
        ],
    },
)
