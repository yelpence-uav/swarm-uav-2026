# Copyright 2026 Yelpence
"""Yorunge dikey hiz tavani — QR okuma icin alcalma YAVAS olmali.

4 Eylul 2026 operator istegi: "dikey alcalma yavas olmali, QR okuyacak."

NEDEN GEREKLI. `generate_waypoints` duz 3B cizgi uretiyor ve adim boyu
TOPLAM hizdan turetiliyor (max_speed_mps / control_rate_hz). Dikey bilesen
ayrica sinirlanmazsa, 25 m -> 10 m gibi bir alcalmada dikey hiz toplam
hiza yaklasir (yatay mesafe kisaysa neredeyse TAMAMI dikey olur) ve kamera
netleyemeden inilir. Tavan, adim boyunu dz oraniyla kirparak dikey hizi
sinirliyor; YON birim vektoru degismedigi icin yorunge duz kalir — ucak
once yatayda varip sonra inmez, ikisini birlikte ama yavas yapar.
"""

from swarm_core.path_planning.linear_trajectory import LinearTrajectoryPlanner


HZ = 5.0


def _dikey_hizlar(wps, z0):
    """Ardisik waypoint'ler arasi dikey hiz (m/s)."""
    zler = [z0] + [w[2] for w in wps]
    return [abs(zler[i + 1] - zler[i]) * HZ for i in range(len(zler) - 1)]


def test_tavan_kapaliyken_dikey_hiz_serbest():
    """Tavan 0 = eski davranis: dikey hiz toplam hiza kadar cikabilir."""
    p = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                accel_time_s=0.0)
    wps = p.generate_waypoints((0.0, 0.0, -25.0), (0.0, 0.0, -10.0))
    assert max(_dikey_hizlar(wps, -25.0)) > 2.5, 'tavansiz halde hizli inmeli'


def test_dikey_tavan_saf_alcalmada_uygulanir():
    """Yatay hareket yokken dikey hiz tavani ASILMAZ."""
    p = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                accel_time_s=0.0, max_vertical_speed_mps=0.5)
    wps = p.generate_waypoints((0.0, 0.0, -25.0), (0.0, 0.0, -10.0))
    assert max(_dikey_hizlar(wps, -25.0)) <= 0.5 + 1e-6


def test_dikey_tavan_egik_yolda_da_uygulanir():
    """Yatay + dikey birlikte: dikey bilesen yine tavanin altinda kalir."""
    p = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                accel_time_s=0.0, max_vertical_speed_mps=0.5)
    wps = p.generate_waypoints((0.0, 0.0, -15.0), (20.0, 0.0, -10.0))
    assert max(_dikey_hizlar(wps, -15.0)) <= 0.5 + 1e-6
    # Hedefe yine de VARILIR (tavan yolu kisaltmaz, yalnizca yavaslatir).
    assert abs(wps[-1][0] - 20.0) < 1e-6
    assert abs(wps[-1][2] - (-10.0)) < 1e-6


def test_yatay_yol_tavandan_ETKILENMEZ():
    """dz=0 iken tavan devreye girmemeli — seyir yavaslamasin."""
    p_tavansiz = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                         accel_time_s=0.0)
    p_tavanli = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                        accel_time_s=0.0,
                                        max_vertical_speed_mps=0.5)
    a = p_tavansiz.generate_waypoints((0.0, 0.0, -15.0), (30.0, 0.0, -15.0))
    b = p_tavanli.generate_waypoints((0.0, 0.0, -15.0), (30.0, 0.0, -15.0))
    assert len(a) == len(b), 'duz yatay yol tavandan etkilenmemeli'


def test_15m_den_10m_ye_inis_suresi():
    """Saha senaryosu: kalkis 15 m -> QR okuma 10 m, 0.5 m/s ile ~10 sn."""
    p = LinearTrajectoryPlanner(max_speed_mps=3.0, control_rate_hz=HZ,
                                accel_time_s=0.0, max_vertical_speed_mps=0.5)
    wps = p.generate_waypoints((0.0, 0.0, -15.0), (0.0, 0.0, -10.0))
    sure_s = len(wps) / HZ
    assert 9.0 <= sure_s <= 11.5, f'beklenen ~10 sn, olculen {sure_s:.1f} sn'
