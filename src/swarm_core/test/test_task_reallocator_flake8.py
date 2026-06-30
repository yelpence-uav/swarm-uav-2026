"""task_reallocator dizini için flake8 uyumluluk testi."""
import pytest
from ament_flake8.main import main_with_errors


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """task_reallocator paketinde PEP 8 uyumunu denetler."""
    rc, errors = main_with_errors(
        argv=['swarm_core/task_reallocator']
    )
    assert rc == 0, (
        'Found {} code style errors / warnings:\n'.format(len(errors))
        + '\n'.join(errors)
    )
