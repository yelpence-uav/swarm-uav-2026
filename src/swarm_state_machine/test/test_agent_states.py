"""AgentState, AgentRole ve FlightMode enum testleri."""

import unittest

from swarm_state_machine.agent_fsm.agent_states import (
    AgentRole,
    AgentState,
    AVOIDANCE_EXCLUDE_STATES,
    FlightMode,
)


class TestAgentState(unittest.TestCase):
    """AgentState enum değerlerini doğrular."""

    def test_unknown_sifir(self):
        """UNKNOWN değeri 0 olmalı."""
        self.assertEqual(AgentState.UNKNOWN, 0)

    def test_idle_bir(self):
        """IDLE değeri 1 olmalı."""
        self.assertEqual(AgentState.IDLE, 1)

    def test_failsafe_ondort(self):
        """FAILSAFE değeri 14 olmalı."""
        self.assertEqual(AgentState.FAILSAFE, 14)

    def test_toplam_durum_sayisi(self):
        """16 adet AgentState tanımlı olmalı."""
        self.assertEqual(len(AgentState), 16)

    def test_avoidance_exclude_states(self):
        """Çarpışma önleme dışında tutulan durumlar doğru olmalı."""
        self.assertIn(AgentState.FAILSAFE, AVOIDANCE_EXCLUDE_STATES)
        self.assertIn(AgentState.LANDED, AVOIDANCE_EXCLUDE_STATES)
        self.assertNotIn(AgentState.IN_SWARM, AVOIDANCE_EXCLUDE_STATES)


class TestAgentRole(unittest.TestCase):
    """AgentRole enum değerlerini doğrular."""

    def test_unknown_sifir(self):
        """UNKNOWN değeri 0 olmalı."""
        self.assertEqual(AgentRole.UNKNOWN, 0)

    def test_leader_bir(self):
        """LEADER değeri 1 olmalı."""
        self.assertEqual(AgentRole.LEADER, 1)

    def test_toplam_rol_sayisi(self):
        """5 adet AgentRole tanımlı olmalı."""
        self.assertEqual(len(AgentRole), 5)


class TestFlightMode(unittest.TestCase):
    """FlightMode enum değerlerini doğrular."""

    def test_unknown_sifir(self):
        """UNKNOWN değeri 0 olmalı."""
        self.assertEqual(FlightMode.UNKNOWN, 0)

    def test_offboard_dort(self):
        """OFFBOARD değeri 4 olmalı."""
        self.assertEqual(FlightMode.OFFBOARD, 4)

    def test_auto_land_sekiz(self):
        """AUTO_LAND değeri 8 olmalı."""
        self.assertEqual(FlightMode.AUTO_LAND, 8)


if __name__ == '__main__':
    unittest.main()
