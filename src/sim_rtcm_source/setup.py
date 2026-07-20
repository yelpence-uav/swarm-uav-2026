from setuptools import find_packages, setup

package_name = 'sim_rtcm_source'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        ('share/' + package_name, ['package.xml']),
        (
            'share/' + package_name + '/sample_data',
            ['sample_data/sample_1005.rtcm'],
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpençe Takımı',
    maintainer_email='osmancevik@pm.me',
    description=(
        'Yalniz-sim RTCM3 uretici (px4_bridge RTK pipeline testi icin)'
    ),
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'sim_rtcm_source = '
            'sim_rtcm_source.sim_rtcm_source_node:main',
        ],
    },
)
