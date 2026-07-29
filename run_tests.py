import sys
from unittest.mock import MagicMock
sys.modules['swarm_interfaces'] = MagicMock()
sys.modules['swarm_interfaces.msg'] = MagicMock()
sys.modules['ament_flake8'] = MagicMock()
sys.modules['ament_flake8.main'] = MagicMock()

import unittest
sys.path.insert(0, 'src/swarm_state_machine')

if __name__ == '__main__':
    loader = unittest.TestLoader()
    tests = loader.discover('src/swarm_state_machine/test')
    testRunner = unittest.runner.TextTestRunner(verbosity=2)
    testRunner.run(tests)
