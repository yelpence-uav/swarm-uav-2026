# Copyright 2026 Yelpence
"""Dogrusal yoringe olusturucu modul."""

import math


class LinearTrajectoryPlanner:
    """Baslangic ve hedef noktalari arasinda dogrusal yoringe olusturur."""

    def __init__(self, max_speed_mps: float, control_rate_hz: float) -> None:
        """
        Yoringe planlayiciyi baslatir.

        Args:
            max_speed_mps: Izin verilen maksimum hiz (m/s).
            control_rate_hz: Dongu frekansi (Hz).
        """
        self.max_speed_mps = max_speed_mps
        self.control_rate_hz = control_rate_hz
        self.step_distance = max_speed_mps / control_rate_hz

    def generate_waypoints(
        self,
        start_pos: tuple[float, float, float],
        target_pos: tuple[float, float, float]
    ) -> list[tuple[float, float, float]]:
        """
        Iki nokta arasinda adim adim waypoint listesi uretir.

        Args:
            start_pos: Baslangic [x, y, z] koordinatlari.
            target_pos: Hedef [x, y, z] koordinatlari.

        Returns:
            list: Waypoint'lerin [(x, y, z), ...] listesi.
        """
        x0, y0, z0 = start_pos
        x1, y1, z1 = target_pos

        dx = x1 - x0
        dy = y1 - y0
        dz = z1 - z0

        total_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

        if total_distance <= self.step_distance or total_distance == 0.0:
            return [(x1, y1, z1)]

        num_steps = int(math.ceil(total_distance / self.step_distance))
        step_x = dx / num_steps
        step_y = dy / num_steps
        step_z = dz / num_steps

        waypoints = []
        for i in range(1, num_steps):
            waypoints.append((
                x0 + step_x * i,
                y0 + step_y * i,
                z0 + step_z * i
            ))

        waypoints.append((x1, y1, z1))

        return waypoints
