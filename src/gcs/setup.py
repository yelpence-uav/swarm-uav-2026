from setuptools import find_packages, setup

package_name = 'gcs'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/templates', ['gcs/templates/index.html']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Yelpence',
    maintainer_email='iletisim@yelpence.com',
    description='Yelpence Takimi Yer Kontrol Istasyonu Paketi',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'web_gui_server = gcs.web_gui_server:main',
        ],
    },
)
