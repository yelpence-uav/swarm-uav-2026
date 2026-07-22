# Copyright 2026 Yelpence
"""Sürü manevra modu hesaplama modülü."""

import math


def compute_agent_setpoints(
    ctx,
    dt: float,
    formation_offsets: dict[int, tuple[float, float, float]],
) -> tuple[list[dict], float, float, float]:
    """Her İHA için manevra konum setpoint'lerini hesaplar.

    Args:
        ctx (ModeContext): Sürü modu çalışma zamanı bağlamı.
        dt (float): Zaman adımı farkı (saniye).
        formation_offsets (dict): İHA ID bazlı (ox, oy, oz) ofsetleri.

    Returns:
        tuple[list[dict], float, float, float]: İHA setpoint listesi,
            yeni heading (derece), hedef pitch (derece), hedef roll (derece).
    """
    new_heading = ctx.compute_heading_rotation(ctx.yaw_cmd, dt)

    dz_throttle = -ctx.throttle_cmd * ctx.max_speed_mps * dt

    target_pitch_deg = ctx.pitch_cmd * ctx.max_tilt_deg
    target_roll_deg = ctx.roll_cmd * ctx.max_tilt_deg

    pitch_rad = math.radians(target_pitch_deg)
    roll_rad = math.radians(target_roll_deg)
    heading_rad = math.radians(new_heading)

    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []

    for agent_id, (ox, oy, oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h

        forward_dist = ox
        dz_pitch = forward_dist * math.sin(pitch_rad)

        right_dist = oy
        dz_roll = right_dist * math.sin(roll_rad)

        target_x = ctx.centroid_x + rx
        target_y = ctx.centroid_y + ry
        target_z = (
            ctx.centroid_z + oz + dz_throttle - dz_pitch - dz_roll
        )

        setpoints.append({
            'agent_id': agent_id,
            'x': target_x,
            'y': target_y,
            'z': target_z,
            'heading_deg': new_heading,
        })

    return setpoints, new_heading, target_pitch_deg, target_roll_deg


def compute_hold_setpoints(
    ctx,
    formation_offsets: dict[int, tuple[float, float, float]],
) -> list[dict]:
    """HOLD durumunda her İHA'nın mevcut eğimli konumunu korur.

    Args:
        ctx (ModeContext): Sürü modu çalışma zamanı bağlamı.
        formation_offsets (dict): İHA ID bazlı (ox, oy, oz) ofsetleri.

    Returns:
        list[dict]: Sabit konum İHA setpoint listesi.
    """
    pitch_rad = math.radians(ctx.maneuver_pitch_deg)
    roll_rad = math.radians(ctx.maneuver_roll_deg)
    heading_rad = math.radians(ctx.formation_heading_deg)

    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []

    for agent_id, (ox, oy, oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h

        forward_dist = ox
        dz_pitch = forward_dist * math.sin(pitch_rad)

        right_dist = oy
        dz_roll = right_dist * math.sin(roll_rad)

        target_x = ctx.centroid_x + rx
        target_y = ctx.centroid_y + ry
        target_z = ctx.centroid_z + oz - dz_pitch - dz_roll

        setpoints.append({
            'agent_id': agent_id,
            'x': target_x,
            'y': target_y,
            'z': target_z,
            'heading_deg': ctx.formation_heading_deg,
        })

    return setpoints
