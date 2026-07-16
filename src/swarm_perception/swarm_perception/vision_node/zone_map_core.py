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
zone_map_core.py.

Renkli iniş/ayrılma bölgelerinin KALICI global haritası (saf mantık, ROS yok).

landing_zone_detector.py anlık + dron-göreli tespit verir; bir kare sonra bölge
görüş alanından çıkınca "unutulur". Şartname ise bölge konumlarının transit
sırasında tespit edilip KAYDEDİLMESİNİ ister (ayrı tarama yasak). Bu sınıf o
hafızadır: anlık tespiti drone pozu + irtifa ile GLOBAL NED'e projekte eder ve
aynı bölgenin tekrar gözlemlerini kümeleyerek tek kayıt olarak biriktirir.

vision_node_core bu sınıfı import edip besler; sınıfın kendisi bir node
değildir. PEP 8 ve PEP 257 standartlarına uygundur.
"""

import math
from typing import Dict, List, Optional, Tuple

# Renk sabitleri — swarm_interfaces ZoneMap.msg / LandingZoneDetection.msg ile
# birebir aynı tutulmalı.
COLOR_UNKNOWN = 0
COLOR_RED = 1
COLOR_BLUE = 2


def zone_offset_ned_m(
    u_px: float,
    v_px: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    height_m: float,
    heading_deg: float,
) -> Tuple[float, float]:
    """Görüntüdeki bölge merkezinin drona göre NED ofseti (metre).

    Nadir bakan pinhole kamera: zemindeki yatay ofset, piksel sapmasının odak
    uzaklığına oranı ile irtifanın çarpımıdır. Odak uzaklıkları kameranın kendi
    beyanından (CameraInfo) gelir; sabit bir görüş açısı varsayılmaz. fx ve fy
    ayrı verildiğinden görüntünün en-boy oranı da kendiliğinden doğrudur.

    İşaret: kamera gövdeye 90° pitch ile monte edilir (aşağı bakar); bu dönüşte
    görüntünün ALT yönü gövdenin GERİSİNE düşer. Bu yüzden ileri bileşen
    negatiflenir. Ters işaret öndeki pedi arkaya kaydedip hatayı gerçek ofsetin
    iki katına çıkarıyor, dronu komşu pede indiriyordu.

    Args:
        u_px (float): Bölge merkezinin yatay piksel konumu.
        v_px (float): Bölge merkezinin dikey piksel konumu.
        fx (float): Yatay odak uzaklığı (piksel).
        fy (float): Dikey odak uzaklığı (piksel).
        cx (float): Görüntü merkezinin yatay piksel konumu.
        cy (float): Görüntü merkezinin dikey piksel konumu.
        height_m (float): Drone'un zeminden yüksekliği (AGL, metre).
        heading_deg (float): Drone heading'i (derece, NED).

    Returns:
        Tuple[float, float]: Drona göre NED ofseti (kuzey, doğu), metre.
    """
    right_m = height_m * (u_px - cx) / fx
    fwd_m = -height_m * (v_px - cy) / fy

    hd = math.radians(heading_deg)
    ned_x = fwd_m * math.cos(hd) - right_m * math.sin(hd)
    ned_y = fwd_m * math.sin(hd) + right_m * math.cos(hd)
    return ned_x, ned_y


class ZoneMapCore:
    """Renkli bölgeleri global NED'de biriktiren hafıza + projeksiyon."""

    def __init__(
        self,
        merge_dist_m: float = 2.0,
        min_height_m: float = 0.5,
        confidence_obs_full: int = 5,
    ) -> None:
        """
        Bölge haritasını verilen eşiklerle ilklendirir.

        Args:
            merge_dist_m (float): Aynı renkteki yeni tespit, mevcut bir bölgeye
                bu mesafeden (metre) yakınsa ayrı kayıt açılmaz, mevcut kayıtla
                birleştirilir (kümeleme). Bölgeler ~1 m yarıçaplı olduğundan
                varsayılan 2.0 m aynı bölgenin tekrar gözlemlerini toplar.
            min_height_m (float): Projeksiyonda kullanılan en düşük AGL.
                Çok alçakta sıfıra bölme/aşırı büyümeyi önler.
            confidence_obs_full (int): Güvenin 1.0'a ulaşması için gereken
                gözlem sayısı. Çok görülen bölge daha güvenilirdir.
        """
        self._merge_dist_m = float(merge_dist_m)
        self._min_height_m = float(min_height_m)
        self._obs_full = max(1, int(confidence_obs_full))
        self._zones: List[Dict[str, float]] = []

    # =================================================================
    # =================================================================
    # BIRIKTIRME / KUMELEME
    # =================================================================
    def add(
        self,
        color: int,
        gx: float,
        gy: float,
        gz: float = 0.0,
        detection_confidence: float = 1.0,
    ) -> None:
        """
        Global NED'de bir bölge gözlemini haritaya ekler veya birleştirir.

        Aynı renkten, merge_dist_m içinde mevcut kayıt varsa yeni kayıt
        açılmaz: konum koşan ortalama ile güncellenir, gözlem sayısı artırılır.
        Böylece her gerçek bölge tek kayıt olur; çok görüldükçe daha
        güvenilir konumlanır.

        Args:
            color (int): COLOR_* enum (yalnızca RED/BLUE biriktirilir).
            gx (float): Global NED x, metre.
            gy (float): Global NED y, metre.
            gz (float): Global NED z, metre.
            detection_confidence (float): Bu karedeki tespit güveni [0, 1].
        """
        if color not in (COLOR_RED, COLOR_BLUE):
            return

        existing = self._find_existing(color, gx, gy)
        if existing is None:
            self._zones.append({
                'color': float(color),
                'x': float(gx),
                'y': float(gy),
                'z': float(gz),
                'count': 1.0,
                'confidence': float(_clamp01(detection_confidence)),
            })
            return

        n = existing['count']
        existing['x'] = (existing['x'] * n + gx) / (n + 1.0)
        existing['y'] = (existing['y'] * n + gy) / (n + 1.0)
        existing['z'] = (existing['z'] * n + gz) / (n + 1.0)
        existing['count'] = n + 1.0
        # Güven: gözlem sayısı arttıkça 1.0'a doğru; tespit güveniyle harmanla.
        obs_conf = min(1.0, existing['count'] / self._obs_full)
        existing['confidence'] = _clamp01(
            max(obs_conf, detection_confidence)
        )

    def _find_existing(
        self, color: int, gx: float, gy: float
    ) -> Optional[Dict[str, float]]:
        """
        Aynı renkten, merge_dist_m içinde en yakın mevcut kaydı döndürür.

        Args:
            color (int): COLOR_* enum.
            gx (float): Global NED x, metre.
            gy (float): Global NED y, metre.

        Returns:
            Optional[Dict[str, float]]: Birleştirilecek kayıt veya None.
        """
        best = None
        best_d = self._merge_dist_m
        for z in self._zones:
            if int(z['color']) != color:
                continue
            d = math.hypot(z['x'] - gx, z['y'] - gy)
            if d <= best_d:
                best_d = d
                best = z
        return best

    # =================================================================
    # SORGU / DISA AKTARIM
    # =================================================================
    def nearest(
        self, color: int, x: float, y: float
    ) -> Optional[Dict[str, float]]:
        """
        Verilen renkten, (x, y) konumuna en yakın bölgeyi döndürür.

        precision_landing "kırmızıya in" dediğinde hedefi seçmek için kullanır
        (bu sınıf node değildir; sorgu ROS tarafından yapılır).

        Args:
            color (int): COLOR_* enum.
            x (float): Referans global NED x, metre.
            y (float): Referans global NED y, metre.

        Returns:
            Optional[Dict[str, float]]: En yakın bölge kaydının kopyası
                veya None.
        """
        best = None
        best_d = float('inf')
        for z in self._zones:
            if int(z['color']) != color:
                continue
            d = math.hypot(z['x'] - x, z['y'] - y)
            if d < best_d:
                best_d = d
                best = z
        return dict(best) if best is not None else None

    @property
    def zones(self) -> List[Dict[str, float]]:
        """Biriktirilen bölge kayıtlarının kopyasını döndürür."""
        return [dict(z) for z in self._zones]

    def zone_count(self) -> int:
        """Biriktirilen benzersiz bölge sayısını döndürür."""
        return len(self._zones)


def _clamp01(value: float) -> float:
    """Bir değeri [0.0, 1.0] aralığına kırpar."""
    return max(0.0, min(1.0, float(value)))
