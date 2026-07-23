# Copyright 2026 Yelpence
"""Suru hareket modu."""


def compute_formation_command(
    ctx,
    dt: float,
) -> dict:
    """Joystick girdisine gore FormationCommand parametreleri hesaplar."""
    dx, dy, dz = ctx.compute_centroid_delta(
        ctx.pitch_cmd, ctx.roll_cmd, ctx.throttle_cmd, dt,
    )

    new_cx = ctx.centroid_x + dx
    new_cy = ctx.centroid_y + dy
    new_cz = ctx.centroid_z + dz

    new_heading = ctx.compute_heading_rotation(ctx.yaw_cmd, dt)

    return {
        'center_x': new_cx,
        'center_y': new_cy,
        'center_z': new_cz,
        'heading_deg': new_heading,
        'formation_type': ctx.active_formation,
        'spacing_m': ctx.requested_spacing_m,
        'max_speed_mps': ctx.max_speed_mps,
        'use_current_centroid': False,
        'use_current_altitude': False,
    }


def compute_hold_command(ctx) -> dict:
    """HOLD durumunda mevcut konumu koruma komutu uretir."""
    return {
        'center_x': ctx.centroid_x,
        'center_y': ctx.centroid_y,
        'center_z': ctx.centroid_z,
        'heading_deg': ctx.formation_heading_deg,
        'formation_type': ctx.active_formation,
        'spacing_m': ctx.requested_spacing_m,
        'max_speed_mps': 0.0,
        'use_current_centroid': False,
        'use_current_altitude': False,
    }
