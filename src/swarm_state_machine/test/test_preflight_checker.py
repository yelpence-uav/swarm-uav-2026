"""Run_preflight_checks fonksiyonu için birim testleri."""

import unittest

from swarm_state_machine.agent_fsm.agent_context import AgentContext
from swarm_state_machine.agent_fsm.preflight_checker import (
    run_preflight_checks,
)


def _sitl_ctx() -> AgentContext:
    """SITL modunda tüm preflight kontrollerini geçen hazır bağlam."""
    ctx = AgentContext(agent_id=1)
    ctx.sitl_mode = True
    ctx.px4_link_ok = True
    ctx.gps_fix_type = 3
    ctx.gps_hdop = 0.9
    ctx.gps_satellites = 10
    ctx.imu_healthy = True
    ctx.mag_healthy = True
    ctx.baro_healthy = True
    ctx.estimator_ok = True
    ctx.estimator_stable_ticks = 20
    ctx.xy_valid = True
    ctx.z_valid = True
    ctx.v_xy_valid = True
    ctx.battery_voltage_v = 0.0
    return ctx


class TestPreflightSitlBasari(unittest.TestCase):
    """SITL modunda başarılı preflight senaryoları."""

    def test_sitl_tam_gecis(self):
        """SITL modunda tüm kontroller geçmeli."""
        ctx = _sitl_ctx()
        passed, failures = run_preflight_checks(ctx)
        self.assertTrue(passed)
        self.assertEqual(failures, [])


class TestPreflightBaglantiHatalari(unittest.TestCase):
    """PX4 bağlantı hata senaryoları."""

    def test_px4_link_yok(self):
        """PX4 bağlantısı yoksa preflight başarısız olmalı."""
        ctx = _sitl_ctx()
        ctx.px4_link_ok = False
        passed, failures = run_preflight_checks(ctx)
        self.assertFalse(passed)
        self.assertTrue(any('PX4' in f for f in failures))

    def test_kill_switch_aktif(self):
        """Kill switch aktifse preflight başarısız olmalı."""
        ctx = _sitl_ctx()
        ctx.kill_switch_active = True
        passed, failures = run_preflight_checks(ctx)
        self.assertFalse(passed)
        self.assertTrue(any('kill' in f.lower() for f in failures))


class TestPreflightGpsHatalari(unittest.TestCase):
    """GPS hata senaryoları."""

    def test_dusuk_fix(self):
        """GPS fix 3'ün altındaysa preflight başarısız olmalı."""
        ctx = _sitl_ctx()
        ctx.gps_fix_type = 2
        passed, failures = run_preflight_checks(ctx)
        self.assertFalse(passed)
        self.assertTrue(any('GPS fix' in f for f in failures))


class TestPreflightKonum(unittest.TestCase):
    """EKF2 konum tahmini senaryoları."""

    def test_konum_gecersiz(self):
        """Konum tahmini geçersizse preflight başarısız olmalı."""
        ctx = _sitl_ctx()
        ctx.sitl_mode = False
        ctx.home_set = True
        ctx.origin_synced = True
        ctx.xy_valid = False
        passed, failures = run_preflight_checks(ctx)
        self.assertFalse(passed)
        self.assertTrue(any('Konum' in f for f in failures))


class TestPreflightBatarya(unittest.TestCase):
    """Batarya voltaj senaryoları."""

    def test_dusuk_voltaj(self):
        """Voltaj minimum değerin altındaysa preflight başarısız olmalı."""
        ctx = _sitl_ctx()
        ctx.battery_voltage_v = 14.0
        passed, failures = run_preflight_checks(ctx, battery_min_voltage=15.2)
        self.assertFalse(passed)
        self.assertTrue(any('voltaj' in f.lower() for f in failures))

    def test_sifir_voltaj_gecis(self):
        """0V (sim batarya devre dışı) voltaj kontrolünü atlamalı."""
        ctx = _sitl_ctx()
        ctx.battery_voltage_v = 0.0
        passed, failures = run_preflight_checks(ctx)
        self.assertTrue(passed)


if __name__ == '__main__':
    unittest.main()
