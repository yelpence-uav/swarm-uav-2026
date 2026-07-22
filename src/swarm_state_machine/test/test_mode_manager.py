# Copyright 2026 Yelpence
"""ModeManager altyapısı birim testleri."""

from dataclasses import dataclass
import time
import unittest

from swarm_state_machine.mode_manager.maneuver_mode import (
    compute_agent_setpoints,
    compute_hold_setpoints,
)
from swarm_state_machine.mode_manager.mode_context import ModeContext
from swarm_state_machine.mode_manager.mode_states import (
    ControlMode,
    ModeState,
)
from swarm_state_machine.mode_manager.mode_transitions import (
    evaluate_transitions,
)
from swarm_state_machine.mode_manager.movement_mode import (
    compute_formation_command,
    compute_hold_command,
)


@dataclass
class _MockAgentStatus:
    state: int = 5
    healthy: bool = True


class TestModeContext(unittest.TestCase):
    """ModeContext durum kabı testleri."""

    def test_mode_context_initialization(self):
        """Varsayılan ModeContext değerlerini doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        self.assertEqual(ctx.state, ModeState.IDLE)
        self.assertFalse(ctx.command_valid)
        self.assertFalse(ctx.deadman_pressed)
        self.assertEqual(ctx.control_mode, ControlMode.UNKNOWN)
        self.assertEqual(ctx.agent_ids, [1, 2, 3])

    def test_mode_context_command_active(self):
        """command_active özelliğinin davranışını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.command_valid = True
        ctx.deadman_pressed = True
        ctx.last_valid_command_time = time.monotonic()
        ctx.deadman_timeout_s = 0.5

        self.assertTrue(ctx.command_active)

        ctx.deadman_pressed = False
        self.assertFalse(ctx.command_active)

        ctx.deadman_pressed = True
        ctx.command_valid = False
        self.assertFalse(ctx.command_active)

    def test_mode_context_deadman_timeout(self):
        """deadman_timed_out fonksiyonunun zaman aşımını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.deadman_timeout_s = 0.1

        self.assertTrue(ctx.deadman_timed_out())

        ctx.last_valid_command_time = time.monotonic()
        self.assertFalse(ctx.deadman_timed_out())

        time.sleep(0.15)
        self.assertTrue(ctx.deadman_timed_out())


class TestMovementMode(unittest.TestCase):
    """MovementMode hesaplama testleri."""

    def test_movement_mode_compute_formation_command(self):
        """compute_formation_command fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_x = 10.0
        ctx.centroid_y = 5.0
        ctx.centroid_z = -15.0
        ctx.formation_heading_deg = 0.0
        ctx.pitch_cmd = 1.0
        ctx.max_speed_mps = 2.0

        cmd = compute_formation_command(ctx, dt=1.0)
        self.assertAlmostEqual(cmd['center_x'], 12.0)
        self.assertAlmostEqual(cmd['center_y'], 5.0)
        self.assertAlmostEqual(cmd['center_z'], -15.0)
        self.assertEqual(cmd['heading_deg'], 0.0)

    def test_movement_mode_compute_hold_command(self):
        """compute_hold_command fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_x = 10.0
        ctx.centroid_y = 20.0
        ctx.centroid_z = -30.0
        ctx.formation_heading_deg = 45.0
        ctx.active_formation = 2

        cmd = compute_hold_command(ctx)
        self.assertEqual(cmd['center_x'], 10.0)
        self.assertEqual(cmd['center_y'], 20.0)
        self.assertEqual(cmd['center_z'], -30.0)
        self.assertEqual(cmd['heading_deg'], 45.0)
        self.assertEqual(cmd['formation_type'], 2)
        self.assertEqual(cmd['max_speed_mps'], 0.0)


class TestManeuverMode(unittest.TestCase):
    """ManeuverMode hesaplama testleri."""

    def test_maneuver_mode_compute_agent_setpoints(self):
        """compute_agent_setpoints fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])
        ctx.centroid_x = 0.0
        ctx.centroid_y = 0.0
        ctx.centroid_z = -10.0
        ctx.formation_heading_deg = 0.0
        ctx.pitch_cmd = 1.0
        ctx.max_tilt_deg = 15.0

        offsets = {1: (2.0, 0.0, 0.0), 2: (-2.0, 0.0, 0.0)}
        result = compute_agent_setpoints(
            ctx, dt=0.1, formation_offsets=offsets,
        )

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 4)

        setpoints, new_heading, pitch_deg, roll_deg = result
        self.assertEqual(len(setpoints), 2)
        self.assertEqual(new_heading, 0.0)
        self.assertEqual(pitch_deg, 15.0)
        self.assertEqual(roll_deg, 0.0)

    def test_maneuver_mode_compute_hold_setpoints(self):
        """compute_hold_setpoints fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1])
        ctx.centroid_x = 5.0
        ctx.centroid_y = 5.0
        ctx.centroid_z = -10.0
        ctx.formation_heading_deg = 0.0
        ctx.maneuver_pitch_deg = 10.0
        ctx.maneuver_roll_deg = 0.0

        offsets = {1: (1.0, 0.0, 0.0)}
        setpoints = compute_hold_setpoints(ctx, formation_offsets=offsets)

        self.assertEqual(len(setpoints), 1)
        self.assertEqual(setpoints[0]['agent_id'], 1)
        self.assertAlmostEqual(setpoints[0]['x'], 6.0)


class TestModeTransitions(unittest.TestCase):
    """ModeTransitions FSM geçiş testleri."""

    def test_mode_transitions_normal_flow(self):
        """IDLE->PREFLIGHT->TAKEOFF->READY->MOVEMENT akışını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])

        # IDLE -> PREFLIGHT
        ctx.mission_state = 8
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.PREFLIGHT)
        ctx.set_state(ModeState.PREFLIGHT)

        # PREFLIGHT -> TAKEOFF
        ctx.agent_statuses = {1: _MockAgentStatus(), 2: _MockAgentStatus()}
        ctx.takeoff_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.TAKEOFF)
        ctx.set_state(ModeState.TAKEOFF)

        # TAKEOFF -> READY
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.READY)
        ctx.set_state(ModeState.READY)

        # READY -> MOVEMENT
        ctx.command_valid = True
        ctx.deadman_pressed = True
        ctx.last_valid_command_time = time.monotonic()
        ctx.control_mode = ControlMode.SWARM_MOVEMENT
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.MOVEMENT)
        ctx.set_state(ModeState.MOVEMENT)

        # MOVEMENT -> HOLD (Deadman released)
        ctx.deadman_pressed = False
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.HOLD)

    def test_mode_transitions_emergency_and_failsafe(self):
        """Acil durum ve RTL durum geçişlerini doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])
        ctx.set_state(ModeState.MOVEMENT)

        # Emergency stop requested
        ctx.emergency_stop_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.EMERGENCY)

        # Pending abort
        ctx.emergency_stop_requested = False
        ctx.pending_abort = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.EMERGENCY)

        # RTL requested
        ctx.pending_abort = False
        ctx.rtl_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.RTL)


if __name__ == '__main__':
    unittest.main()
