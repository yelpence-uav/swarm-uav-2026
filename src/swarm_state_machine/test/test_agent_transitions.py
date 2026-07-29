"""Evaluate_transitions fonksiyonu için birim testleri."""

import unittest

from swarm_state_machine.agent_fsm.agent_context import AgentContext
from swarm_state_machine.agent_fsm.agent_states import (
    AgentState,
    FlightMode,
)
from swarm_state_machine.agent_fsm.agent_transitions import (
    evaluate_transitions,
)


def _sitl_ctx() -> AgentContext:
    """SITL modunda sağlıklı, uçuşa hazır bir bağlam döner."""
    ctx = AgentContext(agent_id=1)
    ctx.sitl_mode = True
    # Saglikli baglam, tanimi geregi telemetri almis demektir; bu bayrak
    # olmadan saglik kontrolleri "henuz bilmiyorum" dalina duser.
    ctx.telemetri_alindi = True
    ctx.px4_link_ok = True
    ctx.rc_link_ok = True
    ctx.imu_healthy = True
    ctx.mag_healthy = True
    ctx.baro_healthy = True
    ctx.estimator_ok = True
    ctx.xy_valid = True
    ctx.z_valid = True
    ctx.v_xy_valid = True
    ctx.battery_voltage_v = 0.0
    return ctx


def _preflight_ready(ctx: AgentContext) -> AgentContext:
    """Preflight kontrollerini geçmesi için bağlamı hazırlar."""
    ctx.gps_fix_type = 3
    ctx.gps_hdop = 0.9
    ctx.gps_satellites = 10
    ctx.estimator_stable_ticks = 20
    return ctx


class TestUnknownIdleGecis(unittest.TestCase):
    """UNKNOWN -> IDLE geçiş testleri."""

    def test_telemetri_geldiyse_idle(self):
        """Telemetri alındıysa UNKNOWN → IDLE."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.UNKNOWN
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.IDLE)

    def test_telemetri_yokken_unknown_da_bekler(self):
        """Telemetri gelmeden IDLE denmemeli — 'hazırım' yalanı olur.

        Regresyon: node açılışında px4_link_ok varsayılan False olduğu için
        ilk tick (t~0.1 sn, DDS keşfi bitmeden) 'PX4 link koptu' deyip
        FAILSAFE'e düşüyordu ve _from_failsafe dışarıdan pending_state
        beklediği için bir daha çıkamıyordu.
        """
        ctx = _sitl_ctx()
        ctx.telemetri_alindi = False
        ctx.px4_link_ok = False          # veri gelmemis, varsayilan deger
        ctx.state = AgentState.UNKNOWN
        result = evaluate_transitions(ctx)
        self.assertIsNone(result, 'telemetri yokken geçiş yapılmamalı')

    def test_telemetri_geldikten_sonra_link_kaybi_failsafe(self):
        """Telemetri bir kez geldiyse gerçek link kaybı FAILSAFE tetiklemeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IN_SWARM
        ctx.px4_link_ok = False
        from swarm_state_machine.agent_fsm import agent_health_monitor
        sonuc = agent_health_monitor.check(ctx)
        self.assertTrue(sonuc.critical_fault, 'link kaybı yakalanmalıydı')


class TestIdleArmingGecis(unittest.TestCase):
    """IDLE -> ARMING geçiş testleri."""

    def test_arming_talebi_preflight_gecis(self):
        """Preflight başarılıysa IDLE -> ARMING geçmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IDLE
        ctx.pending_state = AgentState.ARMING
        _preflight_ready(ctx)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.ARMING)

    def test_arming_talebi_yok_gecis_yok(self):
        """Arming talebi yoksa IDLE'da kalmalı."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IDLE
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)

    def test_arming_talebi_preflight_basarisiz(self):
        """GPS fix yetersizse IDLE -> ARMING geçmemeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IDLE
        ctx.pending_state = AgentState.ARMING
        ctx.gps_fix_type = 1
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)


class TestArmingGecisleri(unittest.TestCase):
    """ARMING durumundan geçiş testleri."""

    def test_arm_onayinda_armed(self):
        """PX4 arm onayı gelince ARMING -> ARMED geçmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.ARMING
        ctx.armed = True
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.ARMED)

    def test_saglik_kaybinda_idle(self):
        """Sağlık kaybında ARMING -> IDLE geçmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.ARMING
        ctx.px4_link_ok = False
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.IDLE)


class TestFailsafeGecisi(unittest.TestCase):
    """Failsafe tetikleme testleri."""

    def test_sagliksiz_ucus_failsafe(self):
        """Uçuşta sağlık bozulunca FAILSAFE'e geçmeli."""
        ctx = _sitl_ctx()
        ctx.sitl_mode = False
        ctx.state = AgentState.IN_SWARM
        ctx.px4_link_ok = False
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.FAILSAFE)

    def test_hold_aktifken_gecis_yok(self):
        """hold_active=True iken geçiş yapılmamalı."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IN_SWARM
        ctx.hold_active = True
        ctx.px4_link_ok = False
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)

    def test_pause_aktifken_gecis_yok(self):
        """autonomous_control_paused=True iken geçiş yapılmamalı."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IN_SWARM
        ctx.autonomous_control_paused = True
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)


class TestRtlHomeSetDegil(unittest.TestCase):
    """Şartname kural 13: home set değilken RTL -> acil iniş."""

    def test_home_set_degil_rtl_landing_olur(self):
        """Home set değilken RTL talebi LANDING'e yönlenmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.IN_SWARM
        ctx.pending_state = AgentState.RETURN_HOME
        ctx.home_set = False
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.LANDING)


class TestLandedGecisleri(unittest.TestCase):
    """LANDED durumundan geçiş testleri."""

    def test_landed_idle_talebi(self):
        """LANDED -> IDLE geçmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.LANDED
        ctx.pending_state = AgentState.IDLE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.IDLE)

    def test_landed_standby_talebi(self):
        """LANDED -> STANDBY geçmeli."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.LANDED
        ctx.pending_state = AgentState.STANDBY
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.STANDBY)

    def test_landed_talep_yok(self):
        """Aciklama: LANDED'da talep yoksa geçiş olmamalı."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.LANDED
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)


class TestReturnHomeGecisi(unittest.TestCase):
    """RETURN_HOME durumundan geçiş testleri."""

    def test_auto_land_modu_landing(self):
        """AUTO_LAND moduna geçince RETURN_HOME -> LANDING olmalı."""
        ctx = _sitl_ctx()
        ctx.state = AgentState.RETURN_HOME
        ctx.flight_mode = FlightMode.AUTO_LAND
        result = evaluate_transitions(ctx)
        self.assertEqual(result, AgentState.LANDING)


if __name__ == '__main__':
    unittest.main()


class TestKillSwitch(unittest.TestCase):
    """Kill switch — havada arıza, yerde kararlı durum."""

    def test_yerde_kill_ariza_degil(self):
        """Yerde disarm haldeyken kill switch kritik arıza sayılmamalı.

        Regresyon: kill'i her durumda arıza saymak, _tick()'teki
        'FAILSAFE + kill + yerde → LANDED' kuralıyla çakışıyor ve FSM
        saniyede birkaç kez FAILSAFE ↔ LANDED zıplıyordu (saha, 2026-07-22).
        """
        from swarm_state_machine.agent_fsm import agent_health_monitor
        ctx = _sitl_ctx()
        ctx.sitl_mode = False          # RC kontrolü SITL'de atlanıyor
        ctx.state = AgentState.LANDED
        ctx.armed = False
        ctx.kill_switch_active = True
        sonuc = agent_health_monitor.check(ctx)
        self.assertFalse(sonuc.critical_fault,
                         'yerde kill switch arıza sayılmamalı')

    def test_havada_kill_kritik_ariza(self):
        """Uçarken kill switch kritik arıza olmalı — koruma korunuyor."""
        from swarm_state_machine.agent_fsm import agent_health_monitor
        ctx = _sitl_ctx()
        ctx.sitl_mode = False
        ctx.state = AgentState.IN_SWARM
        ctx.armed = True
        ctx.kill_switch_active = True
        sonuc = agent_health_monitor.check(ctx)
        self.assertTrue(sonuc.critical_fault,
                        'uçarken kill switch arıza olmalı')

    def test_armed_ama_yerde_kill_kritik(self):
        """Yerde ama armed ise kill hâlâ kritik — pervaneler dönüyor olabilir."""
        from swarm_state_machine.agent_fsm import agent_health_monitor
        ctx = _sitl_ctx()
        ctx.sitl_mode = False
        ctx.state = AgentState.IDLE
        ctx.armed = True
        ctx.kill_switch_active = True
        sonuc = agent_health_monitor.check(ctx)
        self.assertTrue(sonuc.critical_fault)
