"""movement_mode.py — Sürü Hareket Modu.

Şartname §5.2.2 — Sürü Hareket Modu:
  - Formasyon korunarak sürü ileri/geri, sağ/sol ve irtifa
    değişikliklerini topluca yapar.
  - Yaw komutu formasyon rotasyonu + heading güncelleme yapar.
  - Throttle ile irtifa değişimi.

Çıktı: FormationCommand → formation_control → AgentSetpoint.
"""

import math


def compute_formation_command(
    ctx,
    dt: float,
) -> dict:
    """Joystick girdisine göre FormationCommand parametreleri hesaplar.

    Mevcut centroid'e joystick delta'sını ekler ve yeni centroid ile
    heading bilgisini döner. formation_control bu bilgiyle her drone'un
    ofsetini hesaplayıp AgentSetpoint üretir.

    Şartname kuralları:
      - pitch_cmd > 0 → ileri (heading yönünde)
      - roll_cmd > 0 → sağ
      - yaw_cmd > 0 → saat yönüne formasyon rotasyonu
      - throttle_cmd > 0 → irtifa artışı (NED'de z azalır)

    Args:
        ctx: ModeContext — joystick girdileri, centroid ve heading bilgisi.
        dt: Zaman adımı (saniye).

    Returns:
        dict: FormationCommand'a yazılacak alanlar:
            center_x, center_y, center_z (NED),
            heading_deg (0-360),
            formation_type, spacing_m,
            max_speed_mps,
            use_current_centroid (False — açık centroid veriyoruz).
    """
    # Centroid translasyonu
    dx, dy, dz = ctx.compute_centroid_delta(
        ctx.pitch_cmd, ctx.roll_cmd, ctx.throttle_cmd, dt,
    )

    new_cx = ctx.centroid_x + dx
    new_cy = ctx.centroid_y + dy
    new_cz = ctx.centroid_z + dz

    # Heading rotasyonu
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
    """HOLD durumunda mevcut konumu koruma komutu üretir.

    Joystick girdisi olmadan mevcut centroid ve heading'i korur.

    Args:
        ctx: ModeContext — mevcut centroid ve heading.

    Returns:
        dict: FormationCommand'a yazılacak alanlar.
    """
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
