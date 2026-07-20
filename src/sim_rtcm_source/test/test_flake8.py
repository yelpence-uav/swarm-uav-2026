"""PEP 8 uyumluluk testi."""
from ament_flake8.main import main_with_errors
import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """Paket kodu PEP 8 standartlarina uymali."""
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, (
        'Found {} code style errors / warnings:\n'.format(len(errors))
        + '\n'.join(errors)
    )
