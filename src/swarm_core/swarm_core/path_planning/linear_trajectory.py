"""Doğrusal yörünge oluşturucu (Linear Trajectory Planner) modülü.

Bu modül, yarışma sahasındaki QR noktaları veya hedefler arasında
doğrusal bir yol (waypoint listesi) oluşturmaktan sorumludur.
"""

import math


class LinearTrajectoryPlanner:
    """Başlangıç ve hedef noktaları arasında doğrusal yörünge oluşturur."""

    def __init__(self, max_speed_mps: float, control_rate_hz: float) -> None:
        """
        Yörünge planlayıcıyı başlatır.

        Args:
            max_speed_mps (float): İzin verilen maksimum hız (m/s).
            control_rate_hz (float): Döngü frekansı (Hz).
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
        İki nokta arasında adım adım waypoint listesi üretir.

        Adım mesafesi `max_speed_mps / control_rate_hz` formülüne göre
        belirlenir. Böylece hedef noktaya hız limitlerini aşmadan,
        belirtilen frekansta doğrusal olarak ulaşılır.

        Args:
            start_pos (tuple): Başlangıç [x, y, z] koordinatları.
            target_pos (tuple): Hedef [x, y, z] koordinatları.

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
