"""maneuver_mode.py — Manevra Modu.

Şartname §5.2.2 — Manevra Modu:
  - Centroid sabit tutulur.
  - Pitch manevrası: formasyon pitch ekseni etrafında eğilir.
  - Roll manevrası: formasyon roll ekseni etrafında eğilir.
  - Yaw manevrası: formasyon rotasyonu (centroid sabit, Z ekseni etrafında).
  - Throttle: sürü irtifası değişir.

Çıktı: Her drone için AgentSetpoint.
Sürekli joystick kontrolü nedeniyle ExecuteManeuver.action yerine
doğrudan setpoint hesaplaması yapılır.
"""

import math


def compute_agent_setpoints(
    ctx,
    dt: float,
    formation_offsets: dict[int, tuple[float, float, float]],
) -> list[dict]:
    """Her drone için manevra setpoint'i hesaplar.

    Formasyon ofsetlerine pitch/roll eğimi ve yaw rotasyonu uygulayarak
    her drone'un hedef NED pozisyonunu hesaplar.

    Şartname kuralları:
      - pitch_cmd → formasyon pitch ekseni etrafında eğilir
        (arkadaki drone yükselir, öndeki alçalır, merkez sabit)
      - roll_cmd → formasyon roll ekseni etrafında eğilir
        (sağdaki drone yükselir, soldaki alçalır)
      - yaw_cmd → formasyon rotasyonu (Z ekseni, heading güncellenir)
      - throttle_cmd → ortak irtifa değişimi

    Args:
        ctx: ModeContext — joystick girdileri, centroid, heading.
        dt: Zaman adımı (saniye).
        formation_offsets: agent_id → (dx, dy, dz) centroid'e göre
            ofsettler (heading uygulanmadan önce, body frame).

    Returns:
        list[dict]: Her drone için AgentSetpoint parametreleri.
            agent_id, x, y, z (NED), heading_deg.
    """
    # Yaw rotasyonu — heading güncelle
    new_heading = ctx.compute_heading_rotation(ctx.yaw_cmd, dt)

    # Throttle — ortak irtifa değişimi (NED: z negatif = yukarı)
    dz_throttle = -ctx.throttle_cmd * ctx.max_speed_mps * dt

    # Pitch/roll eğim açıları — joystick girdisini açıya çevir
    target_pitch_deg = ctx.pitch_cmd * ctx.max_tilt_deg
    target_roll_deg = ctx.roll_cmd * ctx.max_tilt_deg

    # Eğim açılarını güncelle (ctx'e yazma — node yapacak)
    pitch_rad = math.radians(target_pitch_deg)
    roll_rad = math.radians(target_roll_deg)
    heading_rad = math.radians(new_heading)

    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []

    for agent_id, (ox, oy, oz) in formation_offsets.items():
        # 1. Heading rotasyonu — ofsetleri heading'e göre döndür
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h

        # 2. Pitch eğimi — heading yönünde forward bileşenine göre
        #    Drone'un heading yönündeki uzaklığı (forward bileşen)
        forward_dist = ox  # Body frame forward = ox
        dz_pitch = forward_dist * math.sin(pitch_rad)

        # 3. Roll eğimi — heading'e dik yönde right bileşenine göre
        #    Drone'un heading'e dik uzaklığı (right bileşen)
        right_dist = oy  # Body frame right = oy
        dz_roll = right_dist * math.sin(roll_rad)

        # Hedef pozisyon (NED)
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
    """HOLD durumunda her drone'un mevcut pozisyonunu koruyan
    setpoint üretir.

    Son uygulanan manevra açıları korunur.

    Args:
        ctx: ModeContext.
        formation_offsets: agent_id → (dx, dy, dz) ofsetler.

    Returns:
        list[dict]: Her drone için konum koruma setpoint'i.
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
