from setuptools import find_packages, setup

package_name = 'swarm_state_machine'

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
    description='Swarm UAV state machine layer',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'agent_fsm_node = '
            'swarm_state_machine.agent_fsm.agent_fsm_node:main',
            'mission_fsm_node = '
            'swarm_state_machine.mission_fsm.mission_fsm_node:main',
            'swarm_fsm_node = '
            'swarm_state_machine.swarm_fsm.swarm_fsm_node:main',
            'mode_manager_node = '
            'swarm_state_machine.mode_manager.mode_manager_node:main',
            'joystick_interpreter_node = '
            'swarm_state_machine.mode_manager'
            '.joystick_interpreter_node:main',
        ],
    },
)
