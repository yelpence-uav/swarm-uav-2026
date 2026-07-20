"""Test flake8 compliance."""
import pytest
from ament_flake8.main import main_with_errors


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """Check PEP 8 compliance with flake8."""
    rc, errors = main_with_errors(
        argv=['swarm_state_machine']
    )
    assert rc == 0, \
        'Found {} code style errors / warnings:\n'.format(len(errors)) + \
        '\n'.join(errors)
