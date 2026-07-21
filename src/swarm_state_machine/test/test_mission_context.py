"""MissionContext yardımcı metodları için birim testleri."""

from types import SimpleNamespace
import unittest

from swarm_state_machine.mission_fsm.mission_context import MissionContext
from swarm_state_machine.mission_fsm.mission_states import MissionState


def _status(
    state: int = 5,
    healthy: bool = True,
    origin_synced: bool = True,
    home_set: bool = True,
    gps_fix_type: int = 3,
    gps_hdop: float = 0.9,
    pos_z: float = -15.0,
) -> SimpleNamespace:
    """Sahte AgentStatus nesnesi döner.

    Args:
        state: AgentStatus.STATE_* değeri (varsayılan IN_SWARM=5).
        healthy: Ajan sağlık durumu.
        origin_synced: NED origin senkronize mi.
        home_set: RTL hedefi set mi.
        gps_fix_type: GPS fix tipi (3=3D fix).
        gps_hdop: GPS HDOP değeri.
        pos_z: NED z pozisyonu (metre).

    Returns:
        SimpleNamespace ile AgentStatus alanları.
    """
    return SimpleNamespace(
        state=state,
        healthy=healthy,
        origin_synced=origin_synced,
        home_set=home_set,
        gps_fix_type=gps_fix_type,
        gps_hdop=gps_hdop,
        pos_z=pos_z,
    )


def _ctx(agent_ids=None) -> MissionContext:
    """Test için varsayılan MissionContext döner.

    Args:
        agent_ids: Ajan ID listesi; None ise [1, 2, 3].

    Returns:
        Yapılandırılmış MissionContext.
    """
    return MissionContext(
        agent_ids=agent_ids or [1, 2, 3],
        team_id='YELPENCE',
        sitl_mode=True,
    )


class TestAllAgentsSeen(unittest.TestCase):
    """all_agents_seen property testleri."""

    def test_hic_ajan_yokken_false(self):
        """Hiç mesaj gelmemişse all_agents_seen False olmalı."""
        ctx = _ctx()
        self.assertFalse(ctx.all_agents_seen)

    def test_eksik_ajan_false(self):
        """Yalnızca bir ajan görüldüğünde False olmalı."""
        ctx = _ctx()
        ctx.agent_statuses[1] = _status()
        self.assertFalse(ctx.all_agents_seen)

    def test_tum_ajanlar_gorulunce_true(self):
        """Tüm ID'lerden mesaj alındığında True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status()
        self.assertTrue(ctx.all_agents_seen)


class TestAllAgentsInSwarm(unittest.TestCase):
    """all_agents_in_swarm / all_agents_in_state testleri."""

    def test_hepsinin_in_swarm_olmasi(self):
        """Tüm ajanlar IN_SWARM(5) ise True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(state=5)
        self.assertTrue(ctx.all_agents_in_swarm())

    def test_biri_takeoff_ise_false(self):
        """Bir ajan TAKEOFF(4) ise False olmalı."""
        ctx = _ctx()
        ctx.agent_statuses[1] = _status(state=5)
        ctx.agent_statuses[2] = _status(state=5)
        ctx.agent_statuses[3] = _status(state=4)
        self.assertFalse(ctx.all_agents_in_swarm())

    def test_bos_dict_false(self):
        """Hiç ajan yokken False olmalı."""
        ctx = _ctx()
        self.assertFalse(ctx.all_agents_in_swarm())

    def test_tum_landed(self):
        """Tüm ajanlar LANDED(13) ise all_agents_landed True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(state=13)
        self.assertTrue(ctx.all_agents_landed())

    def test_tum_landing(self):
        """Tüm ajanlar LANDING(12) ise all_agents_landing True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(state=12)
        self.assertTrue(ctx.all_agents_landing())


class TestAllAgentsHealthy(unittest.TestCase):
    """all_agents_healthy testleri."""

    def test_hepsi_saglikli(self):
        """Tüm ajanlar healthy=True ise True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(healthy=True)
        self.assertTrue(ctx.all_agents_healthy())

    def test_biri_sagliksiz(self):
        """Bir ajan healthy=False ise False olmalı."""
        ctx = _ctx()
        ctx.agent_statuses[1] = _status(healthy=True)
        ctx.agent_statuses[2] = _status(healthy=False)
        ctx.agent_statuses[3] = _status(healthy=True)
        self.assertFalse(ctx.all_agents_healthy())

    def test_bos_false(self):
        """Hiç ajan yokken False olmalı."""
        ctx = _ctx()
        self.assertFalse(ctx.all_agents_healthy())


class TestAllAgentsOriginSynced(unittest.TestCase):
    """all_agents_origin_synced testleri."""

    def test_hepsi_synced(self):
        """Tüm ajanlar origin_synced=True ise True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(origin_synced=True)
        self.assertTrue(ctx.all_agents_origin_synced())

    def test_biri_senkron_degil(self):
        """Bir ajan origin_synced=False ise False olmalı."""
        ctx = _ctx()
        ctx.agent_statuses[1] = _status(origin_synced=True)
        ctx.agent_statuses[2] = _status(origin_synced=False)
        ctx.agent_statuses[3] = _status(origin_synced=True)
        self.assertFalse(ctx.all_agents_origin_synced())


class TestAllAgentsGpsOk(unittest.TestCase):
    """all_agents_gps_ok testleri."""

    def test_iyi_gps(self):
        """fix_type>=3 ve hdop<1.5 olunca True olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(gps_fix_type=3, gps_hdop=0.9)
        self.assertTrue(ctx.all_agents_gps_ok())

    def test_dusuk_fix(self):
        """fix_type<3 olunca False olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(gps_fix_type=2, gps_hdop=0.9)
        self.assertFalse(ctx.all_agents_gps_ok())

    def test_yuksek_hdop(self):
        """hdop>=1.5 olunca False olmalı."""
        ctx = _ctx()
        for aid in [1, 2, 3]:
            ctx.agent_statuses[aid] = _status(gps_fix_type=3, gps_hdop=2.0)
        self.assertFalse(ctx.all_agents_gps_ok())


class TestSetState(unittest.TestCase):
    """set_state metodu testleri."""

    def test_state_degisir(self):
        """set_state doğru state'i atamalı."""
        ctx = _ctx()
        ctx.set_state(MissionState.PREFLIGHT)
        self.assertEqual(ctx.state, MissionState.PREFLIGHT)

    def test_bayraklar_sifirlanir(self):
        """set_state çağrısında event ve action bayrakları sıfırlanmalı."""
        ctx = _ctx()
        ctx.action_done = True
        ctx.action_success = True
        ctx.event_formation_reached = True
        ctx.event_rotation_completed = True

        ctx.set_state(MissionState.NAVIGATE_TO_QR)

        self.assertFalse(ctx.action_done)
        self.assertFalse(ctx.action_success)
        self.assertFalse(ctx.event_formation_reached)
        self.assertFalse(ctx.event_rotation_completed)

    def test_zaman_sayaci_sifirlanir(self):
        """set_state sonrası time_in_state küçük bir değer olmalı."""
        ctx = _ctx()
        ctx.set_state(MissionState.IDLE)
        self.assertAlmostEqual(ctx.time_in_state(), 0.0, delta=0.1)


if __name__ == '__main__':
    unittest.main()
