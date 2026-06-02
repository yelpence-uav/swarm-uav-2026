"""esp32_bridge paketi için flake8 PEP 8 uyumluluk testi."""
import pytest
from ament_flake8.main import main_with_errors


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """swarm_control/esp32_bridge altındaki Python kodu PEP 8'e uymalı."""
    rc, errors = main_with_errors(argv=['swarm_control/esp32_bridge'])
    assert rc == 0, (
        'Found {} code style errors / warnings:\n'.format(len(errors))
        + '\n'.join(errors)
    )
