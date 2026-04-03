from setuptools import find_packages, setup

package_name = "swarm"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="yelpence",
    maintainer_email="yelpence@todo.todo",
    description="TODO: Package description",
    license="TODO: License declaration",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "offboard_control = swarm.offboard_control:main",
            "swarm_commander = swarm.swarm_commander:main",
            "swarm_dashboard = swarm.swarm_dashboard:main",
            "chaos_network = swarm.chaos_network:main",
        ],
    },
)
