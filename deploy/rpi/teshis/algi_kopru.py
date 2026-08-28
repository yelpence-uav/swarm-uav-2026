#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""Algı sonuçlarını JSON'a yazar — kamera sayfası onu gösterir.

NEDEN VAR (27 Ağustos 2026, operatör itirazı)
---------------------------------------------
"abi böyle elle neden yapıyorum, neden direkt qr okuma ve renk okuma
çalışmıyor şuanda."

Zincir zaten çalışıyordu — renk tespiti 5,5 Hz yayın yapıyordu. Eksik olan
şey sonucu GÖRMEKTİ: `ros2 topic echo` yazmak gerekiyordu. Operatör zaten
canlı video sayfasına bakıyor; QR metni ve renk tespiti orada çıkmalı.

KÖPRÜ NEDEN DOSYA: sayfa host'ta koşuyor ve ROS'u yok; ROS konteynerin
içinde. Arada `/ws` (konteyner) = `~/yelpence_ws` (host) bind mount'u var.
Bu düğüm oraya JSON yazıyor, sayfa okuyor. Ek bağımlılık yok, ek port yok.

YAZMA ATOMİK: geçici dosyaya yazıp `rename` ediyoruz. Sayfa 5 Hz okuyor;
yarım yazılmış bir dosyayı okursa JSON çözülmez ve kart boşalırdı.
"""

import json
import os
import time

from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParametersAtomically

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import LandingZoneDetection, QRMissionData

_RELIABLE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)
_BEST_EFFORT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

_RENK_ADLARI = {0: 'bilinmiyor', 1: 'KIRMIZI', 2: 'MAVI'}


class AlgiKopru(Node):
    """QR ve iniş bölgesi sonuçlarını dosyaya yazar."""

    def __init__(self) -> None:
        super().__init__('algi_kopru')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('cikti', '/ws/algi_durum.json')
        self.declare_parameter('ayar_dosyasi', '/ws/algi_ayar.json')
        self.declare_parameter('yazma_hz', 5.0)

        self._agent_id = self.get_parameter('agent_id').value
        self._cikti = self.get_parameter('cikti').value
        self._ayar_dosyasi = self.get_parameter('ayar_dosyasi').value
        hz = float(self.get_parameter('yazma_hz').value)

        # SON ÇÖZÜLEN QR YAPIŞKAN tutuluyor. QR kareye bir saniye girip
        # çıkıyor; anlık durum gösterilseydi operatör tam da okunduğu anda
        # ekrana bakmak zorunda kalırdı. Yaşıyla birlikte gösteriliyor.
        self._son_qr: dict | None = None
        self._qr_sayaci = 0
        self._lz: dict | None = None

        self.create_subscription(
            QRMissionData, '/swarm/internal/perception/qr_data',
            self._qr_geldi, _RELIABLE_QOS)
        self.create_subscription(
            LandingZoneDetection,
            f'/drone_{self._agent_id}/perception/landing_zone',
            self._lz_geldi, _BEST_EFFORT_QOS)

        # ESIK AYARI SAYFADAN — 27 Agustos 2026, operator istegi:
        # "en ufak rengi goruyor, kirmizi ve mavi gormesi lazim ve rengin
        # dairesel olmasi lazim". Dogru esik pede, irtifaya ve isiga bagli;
        # ancak sahada BAKARAK bulunur. Sayfa bir dosya yaziyor, bu dugum
        # onu izleyip vision_node'un parametrelerini set ediyor.
        # Neden dosya: sayfa host'ta ve ROS'u yok (bkz. sinifin baslik notu).
        # ATOMIK: tek tek set edilirse her parametre ayri geri cagri
        # tetikler ve arada KARISIK esik cifti olusur (alan gevsek ama
        # dairesellik hala siki gibi). Kisa surer ama o anin karesi yanlis
        # degerlendirilir. Atomik cagri hepsini tek seferde uygular.
        self._ayar_istemci = self.create_client(
            SetParametersAtomically, '/vision_node/set_parameters_atomically')
        self._son_ayar: dict | None = None

        self.create_timer(1.0 / hz, self._yaz)
        self.create_timer(1.0, self._ayari_izle)
        self.get_logger().info(
            f'AlgiKopru: agent_id={self._agent_id} -> {self._cikti}')

    def _qr_geldi(self, m: QRMissionData) -> None:
        self._qr_sayaci += 1
        self._son_qr = {
            'an': time.time(),
            'detected': bool(m.detected),
            'decoded': bool(m.decoded),
            'valid': bool(m.valid),
            'raw_text': m.raw_text,
            'error_message': m.error_message,
            'qr_id': int(m.qr_id),
            'qr_seq': int(m.qr_seq),
            'team_id': m.team_id,
            'confidence': round(float(m.confidence), 3),
            'image_x': round(float(m.image_x), 4),
            'image_y': round(float(m.image_y), 4),
        }

    def _lz_geldi(self, m: LandingZoneDetection) -> None:
        self._lz = {
            'an': time.time(),
            'zone_detected': bool(m.zone_detected),
            'zone_count': int(m.zone_count),
            'renkler': [_RENK_ADLARI.get(c, str(c)) for c in m.zone_colors],
            # `zone_confidence` DAIRESELLIKTIR: kontur alani / en kucuk
            # cevreleyen dairenin alani. 1.0 = kusursuz daire, kare 0.64.
            'dairesellik': [round(float(g), 3) for g in m.zone_confidence],
            'yaricap_m': [round(float(r), 2) for r in m.zone_radius_m],
            'primary_valid': bool(m.primary_valid),
            'primary_color': _RENK_ADLARI.get(int(m.primary_color), '?'),
            'image_x': round(float(m.image_x), 4),
            'image_y': round(float(m.image_y), 4),
            'image_width': round(float(m.image_width), 4),
            'image_height': round(float(m.image_height), 4),
            'fov_deg': round(float(m.fov_deg), 1),
        }

    def _ayari_izle(self) -> None:
        """Sayfanın yazdığı eşik dosyasını izler, değişince uygular."""
        try:
            with open(self._ayar_dosyasi, encoding='utf-8') as f:
                istek = json.load(f)
        except (OSError, ValueError):
            return
        if istek == self._son_ayar:
            return
        if not self._ayar_istemci.service_is_ready():
            return                      # vision_node henuz ayakta degil

        params = []
        for ad in ('min_zone_area_frac', 'min_circularity',
                   'min_zone_area_px'):
            if ad in istek:
                params.append(Parameter(
                    name=ad,
                    value=ParameterValue(
                        type=ParameterType.PARAMETER_DOUBLE,
                        double_value=float(istek[ad]))))
        if not params:
            self._son_ayar = istek
            return

        istek_msg = SetParametersAtomically.Request()
        istek_msg.parameters = params
        self._ayar_istemci.call_async(istek_msg)
        self._son_ayar = istek
        self.get_logger().info(
            'esik istegi gonderildi: '
            + ', '.join(f'{p.name}={p.value.double_value}' for p in params))

    def _yaz(self) -> None:
        veri = {
            'an': time.time(),
            'agent_id': self._agent_id,
            'qr_sayaci': self._qr_sayaci,
            'qr': self._son_qr,
            'lz': self._lz,
            'esik': self._son_ayar,
        }
        gecici = f'{self._cikti}.tmp'
        try:
            with open(gecici, 'w', encoding='utf-8') as f:
                json.dump(veri, f, ensure_ascii=False)
            os.replace(gecici, self._cikti)
            os.chmod(self._cikti, 0o644)      # host'taki sayfa okuyabilsin
        except OSError as e:
            self.get_logger().warn(f'yazilamadi: {e}',
                                   throttle_duration_sec=10.0)


def main(args=None) -> None:
    """Düğümü başlatır."""
    rclpy.init(args=args)
    dugum = AlgiKopru()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        dugum.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
