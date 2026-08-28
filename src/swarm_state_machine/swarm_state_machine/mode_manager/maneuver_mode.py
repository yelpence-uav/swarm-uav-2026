# Copyright 2026 Yelpence
"""Sürü manevra modu hesaplama modülü (Görev 2, MANEVRA).

EĞİM MATEMATİĞİ TEK KAYNAKTAN: `manual_kinematics.apply_tilt`. Bu modülün
ilk yazımı kendi kopyasını taşıyordu ve o kopyada Görev 1 tarafında
ÖLÇÜLEREK düzeltilen hata aynen duruyordu (apply_tilt docstring'i:
asimetrik formasyonda — okbaşı/V — ham dz'nin ortalaması sıfır olmadığı
için bütün sürü kayıyordu, 14→10,5 m ölçüldü). Ayrıca roll işareti
Görev 1 sözleşmesinin TERSİYDİ (-oy·sin yerine +dy·tan olmalı: roll>0 =
sağa yatış = sağdaki slot AŞAĞI). Şartname 5.2.2 "sürü merkezi sabit
tutularak" diyor; ortalama-çıkarma o şartın kendisi.

Kumanda-yön eşlemesinin (çubuk ileri = hangi işaret) son sözü yerde
ölçülür — G0 işaret-yönü testi (komsu_adaptoru geleneği).
"""

import math

from swarm_core.formation_control.manual_kinematics import apply_tilt


def _egik_ofsetler(
    formation_offsets: dict[int, tuple[float, float, float]],
    pitch_deg: float,
    roll_deg: float,
) -> dict[int, tuple[float, float, float]]:
    """Ofsetleri apply_tilt'ten geçirip kimliğe geri eşler.

    Sıralama kimliğe göre SABİT: apply_tilt liste alır, ortalamayı
    listeden çıkarır — çağrılar arasında sıra değişirse sonuç değişmez
    ama okunabilirlik için deterministik tutuluyor.
    """
    sirali = sorted(formation_offsets.items())
    egik = apply_tilt([ofs for _aid, ofs in sirali], pitch_deg, roll_deg)
    return {aid: egik[i] for i, (aid, _ofs) in enumerate(sirali)}


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

    egik = _egik_ofsetler(
        formation_offsets, target_pitch_deg, target_roll_deg
    )

    heading_rad = math.radians(new_heading)
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []
    for agent_id, (ox, oy, _oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h
        # Eğim yalnız z'yi modüle eder (apply_tilt xy'ye dokunmaz);
        # merkez sabitliği apply_tilt'in ortalama-çıkarmasıyla garanti.
        ez = egik[agent_id][2]

        setpoints.append({
            'agent_id': agent_id,
            'x': ctx.centroid_x + rx,
            'y': ctx.centroid_y + ry,
            'z': ctx.centroid_z + ez + dz_throttle,
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
    egik = _egik_ofsetler(
        formation_offsets, ctx.maneuver_pitch_deg, ctx.maneuver_roll_deg
    )

    heading_rad = math.radians(ctx.formation_heading_deg)
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []
    for agent_id, (ox, oy, _oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h
        ez = egik[agent_id][2]

        setpoints.append({
            'agent_id': agent_id,
            'x': ctx.centroid_x + rx,
            'y': ctx.centroid_y + ry,
            'z': ctx.centroid_z + ez,
            'heading_deg': ctx.formation_heading_deg,
        })

    return setpoints
