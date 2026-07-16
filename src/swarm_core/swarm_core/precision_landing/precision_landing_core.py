# Copyright 2026 Yelpence TEKNOFEST 2026
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
precision_landing_core.py.

Renkli iniş bölgesine hassas iniş mantığı (saf mantık, ROS yok).

Sorumluluk: kendi dronu STATE_PRECISION_LANDING'e girince, hedef rengin
bölgesine gidip kamera ile ortalanarak alçalır ve touchdown'da disarm ister.
Bu sınıf SADECE inişi hesaplar; ayrılma kararı (mission_fsm/QR), bölge tespiti
(vision_node), bölge hafızası (zone_map) ve rejoin (agent_fsm) BAŞKA modüllerin
işidir. agent_fsm PRECISION_LANDING state'inde PX4 komutu basmaz; bu boşluk
bilerek bu modüle bırakılmıştır.

Çıktı bir AgentSetpoint'e çevrilir: SADECE hız (velocity_valid=True,
position_valid=False) — C modu saf-hız mimarisine uygun. Touchdown'da disarm
bayrağı, node tarafından px4_bridge'e 'disarm' komutu olarak iletilir.

precision_landing_node bu sınıfı import edip besler; sınıfın kendisi node
değildir. PEP 8 ve PEP 257 standartlarına uygundur.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Renk sabitleri — swarm_interfaces ZoneMap.msg / LandingZoneDetection.msg ile
# birebir aynı.
COLOR_UNKNOWN = 0
COLOR_RED = 1
COLOR_BLUE = 2

# İniş fazları.
PHASE_IDLE = 0
PHASE_SELECT_ZONE = 1
PHASE_APPROACH = 2
PHASE_DESCEND = 3
PHASE_TOUCHDOWN = 4
PHASE_DONE = 5
PHASE_ABORT = 6


@dataclass
class LandingCommand:
    """precision_landing_core çıktısı — node bunu AgentSetpoint'e çevirir."""

    publish: bool = False          # node bu döngüde setpoint yayınlamalı mı
    phase: int = PHASE_IDLE
    vx: float = 0.0                # NED hız setpoint, m/s
    vy: float = 0.0
    vz: float = 0.0                # NED'de pozitif = aşağı
    heading_deg: float = 0.0
    velocity_valid: bool = False
    disarm: bool = False           # touchdown: px4_bridge'e 'disarm' iste
    done: bool = False
    target_x: float = 0.0          # seçilen bölge global NED (log/teşhis)
    target_y: float = 0.0
    in_view: bool = False          # canlı kamerada bölge görünüyor mu
    message: str = ''


@dataclass
class PrecisionLandingCore:
    """Renkli bölgeye hassas iniş durum makinesi + hız kontrolcüsü."""

    approach_speed_mps: float = 1.5
    descend_speed_mps: float = 0.4
    descend_h_cap_mps: float = 0.6
    kp: float = 0.8
    xy_align_tol_m: float = 0.5
    touchdown_alt_m: float = 0.3
    landing_timeout_s: float = 45.0
    landing_time_margin_s: float = 45.0
    min_height_m: float = 0.5
    target_radius_m: float = 2.5

    _phase: int = field(default=PHASE_IDLE, init=False)
    _target: Optional[Tuple[float, float]] = field(default=None, init=False)
    _start_time: Optional[float] = field(default=None, init=False)
    _deadline: Optional[float] = field(default=None, init=False)

    def reset(self) -> None:
        """İç durumu başa alır (state PRECISION_LANDING'den çıkınca)."""
        self._phase = PHASE_IDLE
        self._target = None
        self._start_time = None
        self._deadline = None

    def _time_budget_s(
        self, pose: Tuple[float, float, float, float]
    ) -> float:
        """Seçilen bölgeye inmek için gereken süreyi hesaplar (saniye).

        Ayrılma noktası ile iniş pedi arasındaki mesafe göreve göre değişir
        (QR'lar ve pedler yarışma sabahı belli olur) — sabit bir süre sınırı bir
        senaryoda bol, diğerinde yetersiz kalır. Bütçe fiilî geometriden
        türetilir: yatay yol / yaklaşma hızı + irtifa / alçalma hızı, üstüne
        hizalanma ve rüzgâr payı. Sonuç yapılandırılmış tabanın altına inmez.
        """
        if self._target is None:
            return self.landing_timeout_s
        x, y, z, _heading = pose
        dist = math.hypot(self._target[0] - x, self._target[1] - y)
        alt_agl = max(0.0, -z)
        travel = dist / max(0.1, self.approach_speed_mps)
        descent = alt_agl / max(0.05, self.descend_speed_mps)
        return max(
            self.landing_timeout_s,
            travel + descent + self.landing_time_margin_s,
        )

    @property
    def phase(self) -> int:
        """Mevcut iniş fazı (PHASE_* sabiti)."""
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
        """
        Bir kontrol döngüsü hesaplar.

        Args:
            active (bool): Kendi state'imiz STATE_PRECISION_LANDING mı.
            pose (Optional[Tuple]): Global NED (x, y, z, heading_deg); z aşağı
                pozitif. None ise poz bilinmiyor.
            target_color (int): İnilecek renk (COLOR_RED/COLOR_BLUE).
            zone_map (List[Dict]): Biriktirilen bölgeler
                [{'color','x','y','count'}, ...] (global NED).
            live_zone (Optional[Dict]): Canlı kamera tespiti
                {'valid','color','frac_fwd','frac_right','fov_deg'} veya None.
                frac_* görüntü merkezinden normalize sapma [-0.5, 0.5].
            now (float): Şimdiki zaman, saniye (monotonik).

        Returns:
            LandingCommand: Bu döngünün hız/disarm kararı.
        """
        if not active or pose is None:
            self.reset()
            return LandingCommand(publish=False, phase=PHASE_IDLE)

        if self._phase == PHASE_IDLE:
            self._start_time = now
            self._phase = PHASE_SELECT_ZONE

        if self._phase == PHASE_SELECT_ZONE:
            self._select_zone(target_color, zone_map)
            if self._phase == PHASE_APPROACH:
                self._deadline = now + self._time_budget_s(pose)
            elif (self._phase == PHASE_SELECT_ZONE
                  and self._start_time is not None
                  and (now - self._start_time) > self.landing_timeout_s):
                # Hedef renk bölgesi HÂLÂ yok: burada pes edilir. Ama tek boş
                # bakışta DEĞİL — bölge haritası ayrılma anında birkaç yüz ms
                # gecikmeyle dolabiliyor; ilk tick'te iptal edip donmak (yaşanan
                # bug: ped 0.45 m'de biliniyorken havada asılı kalma) yerine
                # bulunana kadar her tick yeniden aranır.
                self._phase = PHASE_ABORT

        # Zaman aşımı: bütçe bölge seçilirken geometriden hesaplanır.
        if (self._phase not in (PHASE_DONE, PHASE_ABORT)
                and self._deadline is not None
                and now > self._deadline):
            self._phase = PHASE_ABORT

        x, y, z, heading = pose
        alt_agl = -z

        if self._phase == PHASE_ABORT:
            # Havada güvenli bekleme (disarm YOK); FSM failsafe devralır.
            return LandingCommand(
                publish=True, phase=PHASE_ABORT, velocity_valid=True,
                heading_deg=heading, message='iniş iptal/bekleme',
            )

        if self._phase == PHASE_DONE:
            return LandingCommand(publish=False, phase=PHASE_DONE, done=True)

        # Hedef nokta: bölge kamerada görünüyorsa canlı projeksiyon (yakında
        # daha doğru), yoksa hafızadaki kayıt.
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
            # Ne harita ne canlı: inilecek yer yok → iptal/bekle.
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

    # =================================================================
    # YARDIMCILAR
    # =================================================================
    def _select_zone(
        self, target_color: int, zone_map: List[Dict[str, float]]
    ) -> None:
        """Hedef renkten EN ÇOK GÖRÜLEN bölgeyi seçer (false positive eler).

        Bölge bulunursa PHASE_APPROACH'a geçer. Bulunmazsa faz DEĞİŞTİRİLMEZ
        (SELECT_ZONE'da kalır) → çağıran her tick yeniden dener; iptal kararını
        süre aşımı verir, tek boş bakış değil. Yalnız GEÇERSİZ RENK komutu
        (yapılandırma hatası) anında iptaldir — o bölge hiç oluşmaz.
        """
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
            return
        self._target = (float(best['x']), float(best['y']))
        self._phase = PHASE_APPROACH

    def _horizontal_velocity(
        self, err_x: float, err_y: float, cap: float
    ) -> Tuple[float, float]:
        """Konum hatasını cap'li hız vektörüne çevirir (P-kontrol)."""
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
        """Canlı kamera tespitini global NED hedef konumuna çevirir.

        Kamera geometrisi burada BİLİNMEZ: vision_node bölgeyi zaten metre
        cinsinden, drona göre NED ofseti olarak yayınlar (kamerayı bilen tek
        düğüm odur). Burada yapılan tek şey kendi konumumuzu eklemektir.

        Aynı projeksiyonun üç ayrı düğümde tekrarlanması, tek bir işaret/ölçek
        hatasının üç yerde birden yaşamasına ve dronun komşu pede inmesine yol
        açıyordu.
        """
        x, y, _z, _heading_deg = pose
        ned_dx = float(live_zone.get('ned_dx', 0.0))
        ned_dy = float(live_zone.get('ned_dy', 0.0))
        return x + ned_dx, y + ned_dy
