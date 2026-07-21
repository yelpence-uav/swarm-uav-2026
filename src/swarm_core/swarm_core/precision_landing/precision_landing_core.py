# Copyright 2026 Yelpence
"""Renkli inis bolgesine hassas inis mantigi (saf Python)."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

COLOR_UNKNOWN = 0
COLOR_RED = 1
COLOR_BLUE = 2

PHASE_IDLE = 0
PHASE_SELECT_ZONE = 1
PHASE_APPROACH = 2
PHASE_DESCEND = 3
PHASE_TOUCHDOWN = 4
PHASE_DONE = 5
PHASE_ABORT = 6


@dataclass
class LandingCommand:
    """Hassas inis kontrol ciktisi."""

    publish: bool = False
    phase: int = PHASE_IDLE
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    heading_deg: float = 0.0
    velocity_valid: bool = False
    disarm: bool = False
    done: bool = False
    target_x: float = 0.0
    target_y: float = 0.0
    in_view: bool = False
    message: str = ''


@dataclass
class PrecisionLandingCore:
    """Hassas inis durum makinesi ve hiz kontrolcusu."""

    approach_speed_mps: float = 1.5
    descend_speed_mps: float = 0.4
    descend_h_cap_mps: float = 0.6
    kp: float = 0.8
    xy_align_tol_m: float = 0.5
    touchdown_alt_m: float = 0.3
    landing_timeout_s: float = 45.0
    min_height_m: float = 0.5
    target_radius_m: float = 2.5

    _phase: int = field(default=PHASE_IDLE, init=False)
    _target: Optional[Tuple[float, float]] = field(default=None, init=False)
    _start_time: Optional[float] = field(default=None, init=False)

    def reset(self) -> None:
        """Ic durumu sifirlar."""
        self._phase = PHASE_IDLE
        self._target = None
        self._start_time = None

    @property
    def phase(self) -> int:
        """Mevcut iniş fazı."""
        return self._phase

    def update(
        self,
        active: bool,
        pose: Optional[Tuple[float, float, float, float]],
        target_color: int,
        zone_map: List[Dict[str, float]],
        live_zone: Optional[Dict[str, float]],
        now: float,
    ) -> LandingCommand:
        """Kontrol dongusunu calistirir."""
        if not active or pose is None:
            self.reset()
            return LandingCommand(publish=False, phase=PHASE_IDLE)

        if self._phase == PHASE_IDLE:
            self._start_time = now
            self._phase = PHASE_SELECT_ZONE

        if self._phase == PHASE_SELECT_ZONE:
            self._select_zone(target_color, zone_map)

        if (self._phase not in (PHASE_DONE, PHASE_ABORT)
                and self._start_time is not None
                and (now - self._start_time) > self.landing_timeout_s):
            self._phase = PHASE_ABORT

        x, y, z, heading = pose
        alt_agl = -z

        if self._phase == PHASE_ABORT:
            return LandingCommand(
                publish=True, phase=PHASE_ABORT, velocity_valid=True,
                heading_deg=heading, message='iniş iptal/bekleme',
            )

        if self._phase == PHASE_DONE:
            return LandingCommand(publish=False, phase=PHASE_DONE, done=True)

        in_view = (
            live_zone is not None
            and live_zone.get('valid', False)
            and int(live_zone.get('color', 0)) == target_color
        )
        if in_view:
            tx, ty = self._project_live(live_zone, pose, alt_agl)
        elif self._target is not None:
            tx, ty = self._target
        else:
            self._phase = PHASE_ABORT
            return LandingCommand(
                publish=True, phase=PHASE_ABORT, velocity_valid=True,
                heading_deg=heading, message='hedef bölge yok',
            )

        err_x = tx - x
        err_y = ty - y
        dist = math.hypot(err_x, err_y)

        if self._phase == PHASE_APPROACH:
            vx, vy = self._horizontal_velocity(
                err_x, err_y, self.approach_speed_mps
            )
            cmd = LandingCommand(
                publish=True, phase=PHASE_APPROACH, vx=vx, vy=vy, vz=0.0,
                velocity_valid=True, heading_deg=heading,
                target_x=tx, target_y=ty, in_view=in_view,
            )
            if dist <= self.xy_align_tol_m:
                self._phase = PHASE_DESCEND
            return cmd

        if self._phase == PHASE_DESCEND:
            vx, vy = self._horizontal_velocity(
                err_x, err_y, self.descend_h_cap_mps
            )
            if alt_agl <= self.touchdown_alt_m:
                self._phase = PHASE_TOUCHDOWN
                return LandingCommand(
                    publish=True, phase=PHASE_TOUCHDOWN, vx=0.0, vy=0.0,
                    vz=0.0, velocity_valid=True, heading_deg=heading,
                    disarm=True, target_x=tx, target_y=ty, in_view=in_view,
                    message='touchdown: disarm',
                )
            return LandingCommand(
                publish=True, phase=PHASE_DESCEND, vx=vx, vy=vy,
                vz=self.descend_speed_mps, velocity_valid=True,
                heading_deg=heading, target_x=tx, target_y=ty,
                in_view=in_view,
            )

        if self._phase == PHASE_TOUCHDOWN:
            self._phase = PHASE_DONE
            return LandingCommand(publish=False, phase=PHASE_DONE, done=True)

        return LandingCommand(publish=False, phase=self._phase)

    def _select_zone(
        self, target_color: int, zone_map: List[Dict[str, float]]
    ) -> None:
        """Hedef renkten en cok gorulen bolgeyi secer."""
        if target_color not in (COLOR_RED, COLOR_BLUE):
            self._phase = PHASE_ABORT
            return
        best = None
        best_count = -1.0
        for z in zone_map:
            if int(z.get('color', 0)) != target_color:
                continue
            count = float(z.get('count', 0.0))
            if count > best_count:
                best_count = count
                best = z
        if best is None:
            self._phase = PHASE_ABORT
            return
        self._target = (float(best['x']), float(best['y']))
        self._phase = PHASE_APPROACH

    def _horizontal_velocity(
        self, err_x: float, err_y: float, cap: float
    ) -> Tuple[float, float]:
        """Konum hatasini cap'li hiz vektorune cevirir."""
        vx = self.kp * err_x
        vy = self.kp * err_y
        speed = math.hypot(vx, vy)
        if speed > cap and speed > 0.0:
            scale = cap / speed
            vx *= scale
            vy *= scale
        return vx, vy

    def _project_live(
        self,
        live_zone: Dict[str, float],
        pose: Tuple[float, float, float, float],
        alt_agl: float,
    ) -> Tuple[float, float]:
        """Kamera olcumunu global NED koordinatlarina yansitir."""
        x, y, _z, heading_deg = pose
        h = max(alt_agl, self.min_height_m)
        fov = live_zone.get('fov_deg', 60.0)
        fov = fov if fov > 1.0 else 60.0
        frac_fwd = live_zone.get('frac_fwd', 0.0)
        frac_right = live_zone.get('frac_right', 0.0)
        off_fwd = h * math.tan(math.radians(frac_fwd * fov))
        off_right = h * math.tan(math.radians(frac_right * fov))
        hd = math.radians(heading_deg)
        tx = x + off_fwd * math.cos(hd) - off_right * math.sin(hd)
        ty = y + off_fwd * math.sin(hd) + off_right * math.cos(hd)
        return tx, ty
