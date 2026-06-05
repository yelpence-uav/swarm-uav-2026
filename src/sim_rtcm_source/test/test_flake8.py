"""sim_rtcm_source paketi icin flake8 PEP 8 uyumluluk testi."""
import pytest
from ament_flake8.main import main_with_errors


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    """sim_rtcm_source altindaki Python kodu PEP 8'e uymali."""
    rc, errors = main_with_errors(argv=['sim_rtcm_source'])
    assert rc == 0, (
        'Found {} code style errors / warnings:\n'.format(len(errors))
        + '\n'.join(errors)
    )
