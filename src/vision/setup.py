from setuptools import find_packages, setup

package_name = 'vision'

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
    description='Yelpence Takimi Goruntu Isleme Paketi',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Yeni eklenen çalıştırılabilir komut:
            'qr_detector = vision.qr_detector:main',
        ],
    },
)
