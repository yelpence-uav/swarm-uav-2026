# Copyright 2026 Yelpence
"""Dogrusal yoringe olusturucu modul."""

import math


class LinearTrajectoryPlanner:
    """Baslangic ve hedef noktalari arasinda dogrusal yoringe olusturur."""

    def __init__(
        self,
        max_speed_mps: float,
        control_rate_hz: float,
        accel_time_s: float = 2.0,
        max_vertical_speed_mps: float = 0.0,
    ) -> None:
        """Yoringe planlayiciyi baslatir."""
        self.max_speed_mps = max_speed_mps
        self.control_rate_hz = control_rate_hz
        self.step_distance = max_speed_mps / control_rate_hz
        self.accel_time_s = max(0.0, float(accel_time_s))
        # DIKEY HIZ TAVANI (0 = kapali, eski davranis). Yorunge duz 3B cizgi
        # ve adim boyu TOPLAM hizdan turetiliyor; dikey bilesen ayrica
        # sinirlanmazsa 28 m -> 10 m gibi bir alcalmada dron neredeyse tam
        # hizla asagi iner. QR okuma bunun tersini istiyor: sure ver, kare
        # netlessin. Bkz. 4 Eylul 2026 operator istegi.
        self.max_vertical_speed_mps = max(0.0, float(max_vertical_speed_mps))

    def generate_waypoints(
        self,
        start_pos: tuple[float, float, float],
        target_pos: tuple[float, float, float],
        max_speed_mps: float | None = None,
    ) -> list[tuple[float, float, float]]:
        """Iki nokta arasinda adim adim waypoint listesi uretir."""
        x0, y0, z0 = start_pos
        x1, y1, z1 = target_pos

        if max_speed_mps is None or max_speed_mps <= 0.0:
            hiz = self.max_speed_mps
        else:
            hiz = min(float(max_speed_mps), self.max_speed_mps)
        step_distance = hiz / self.control_rate_hz

        dx = x1 - x0
        dy = y1 - y0
        dz = z1 - z0

        total_distance = math.sqrt(dx * dx + dy * dy + dz * dz)

        # DIKEY TAVAN: adimin dikey bileseni |dz|/total oranindadir. Dikey
        # hizi tavanda tutmak icin adim boyunu o oranla olcekleyip kirpiyoruz.
        # Yon birim vektoru DEGISMEZ — yorunge duz kalir, yalnizca YAVASLAR;
        # yani ucak once yatayda varip sonra inmez, ikisini birlikte yapar.
        if self.max_vertical_speed_mps > 0.0 and abs(dz) > 1e-9:
            dikey_tavan_adim = (
                (self.max_vertical_speed_mps / self.control_rate_hz)
                * (total_distance / abs(dz))
            )
            step_distance = min(step_distance, dikey_tavan_adim)

        if total_distance <= step_distance or total_distance == 0.0:
            return [(x1, y1, z1)]

        # HIZ RAMPASI (ease-in)
        # Eskiden tum adimlar esit buyukteydi: merkez ILK tick'te 0'dan tam
        # hiza sicriyordu. Dron fiziksel olarak o hiza aninda cikamadigi icin
        # ivmelenme suresince GERIDE kaliyor; sonra da kapatamiyor, cunku
        # dronun toplam hiz komutu (v_ff + v_svt) max_speed'e KIRPILIYOR →
        # dron merkezle AYNI hizda gider, aradaki acik sabit kalir. Her yeni
        # bacakta acik ustune eklenir (olculdu: 5.0 → 12.5 → 20.4 m; uc dronun
        # hatasi birebir ayni, yani formasyon degil TOPLU gecikme).
        # Cozum: merkez de dron gibi yumusak hizlansin. Ayni mantik donus icin
        # zaten uygulanmis (rot_tangential_accel); ilerlemede eksikti.
        birim = (dx / total_distance, dy / total_distance,
                 dz / total_distance)
        ramp_adim = int(round(self.accel_time_s * self.control_rate_hz))

        waypoints = []
        gidilen = 0.0
        i = 0
        while gidilen < total_distance:
            i += 1
            if ramp_adim > 0 and i <= ramp_adim:
                # Dogrusal ivme: adim boyu 1/n, 2/n, ... n/n oraninda buyur.
                adim = step_distance * (i / ramp_adim)
            else:
                adim = step_distance
            gidilen = min(gidilen + adim, total_distance)
            waypoints.append((
                x0 + birim[0] * gidilen,
                y0 + birim[1] * gidilen,
                z0 + birim[2] * gidilen,
            ))
            if len(waypoints) > 100000:      # guvenlik: sonsuz dongu olmasin
                break

        waypoints[-1] = (x1, y1, z1)
        return waypoints
