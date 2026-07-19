from setuptools import find_packages, setup

package_name = "network_proxy"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Yelpençe Takımı",
    maintainer_email="iletisim@yelpence.com",
    description="Suru IHA ESP-NOW Mesh Agi Simulatoru",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "network_proxy_node = network_proxy.network_proxy_node:main"
        ],
    },
)
