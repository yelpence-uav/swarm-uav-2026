"""
qr_detector.py

Pyzbar kullanarak BGR görüntülerde QR kod tespiti yapan saf modül.
ROS 2 bağımlılığı taşımaz, yalnızca numpy ve pyzbar kullanır.
"""

from typing import Any, Dict, List

import numpy as np
from pyzbar.pyzbar import decode


class QRDetector:
    """Görüntüdeki QR kodlarını bulup ayrıştıran sınıf."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        """
        QRDetector sınıfını ilklendirir.

        Args:
            min_confidence (float): Asgari güven eşiği (pyzbar desteklemez,
                ancak mimari uyumu için korunmuştur).
        """
        self._min_confidence = min_confidence

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Verilen BGR görüntü üzerindeki QR kodları bulur ve ayrıştırır.

        Args:
            image (np.ndarray): cv2 formatında BGR görüntü matrisi.

        Returns:
            List[Dict[str, Any]]: Ayrıştırılmış QR veri sözlüğü listesi.
        """
        if image is None or image.size == 0:
            return []

        # Pyzbar decode işlemi (RGB veya BGR fark etmez)
        decoded_objects = decode(image)

        results = []
        for obj in decoded_objects:
            try:
                raw_text = obj.data.decode('utf-8')
            except UnicodeDecodeError:
                continue

            # Sınırlayıcı kutu (Bounding Box) koordinatları
            rect = obj.rect
            img_h, img_w = image.shape[:2]

            # QRMissionData formatına uygun veri yapısı
            qr_data = {
                'raw_text': raw_text,
                'image_x': float(rect.left + rect.width / 2) / img_w,
                'image_y': float(rect.top + rect.height / 2) / img_h,
                'image_width': float(rect.width) / img_w,
                'image_height': float(rect.height) / img_h,
            }

            parsed_fields = self._parse_qr_text(raw_text)
            qr_data.update(parsed_fields)

            results.append(qr_data)

        return results

    def _parse_qr_text(self, text: str) -> Dict[str, Any]:
        """
        QR kod metnini noktalı virgül (;) ile ayrıştırır.

        Örnek metin:
        team_id=YELPENCE; qr_id=1; next_qr=4; formation=OKBASI; spacing_m=6

        Args:
            text (str): QR kod içerisinden okunan ham metin.

        Returns:
            Dict[str, Any]: Anahtar-değer çiftlerinden oluşan sözlük.
        """
        parsed = {
            'team_id': '',
            'qr_id': 0,
            'qr_seq': 0,
            'next_qr': 0,
            'formation_type': 0,
            'spacing_m': 0.0,
            'altitude_agl_m': 0.0,
            'pitch_deg': 0.0,
            'roll_deg': 0.0,
            'yaw_deg': 0.0,
            'wait_s': 0.0,
            'target_agent_id': 0,
            'detach_color': 0,
            'detach_wait_s': 0.0,
            'formation_active': False,
            'target_active': False,
            'maneuver_active': False,
            'altitude_active': False,
            'detach_active': False,
            'complete_mission': False,
            'valid': False,
            'error_message': '',
        }

        # Takım eşleştirmesi
        parts = [p.strip() for p in text.split(';') if p.strip()]

        for part in parts:
            if '=' not in part:
                continue

            key, val = part.split('=', 1)
            key = key.strip().lower()
            val = val.strip()

            try:
                self._assign_field(parsed, key, val)
            except ValueError as e:
                parsed['error_message'] = str(e)
                return parsed

        # Temel doğrulama: team_id YELPENCE olmalı
        if parsed['team_id'] == 'YELPENCE':
            parsed['valid'] = True
        else:
            parsed['error_message'] = 'Gecersiz takim ID'

        return parsed

    def _assign_field(
        self, parsed: Dict[str, Any], key: str, val: str
    ) -> None:
        """
        Ayrıştırılan alanı veri sözlüğüne atar.

        Args:
            parsed (Dict[str, Any]): Verilerin saklandığı sözlük.
            key (str): İşlenecek alanın anahtarı.
            val (str): Alana atanacak değer.
        """
        if key == 'team_id':
            parsed['team_id'] = val
        elif key == 'qr_id':
            parsed['qr_id'] = int(val)
        elif key == 'qr_seq':
            parsed['qr_seq'] = int(val)
        elif key == 'next_qr':
            parsed['next_qr'] = int(val)
            parsed['target_active'] = True
        elif key == 'formation':
            parsed['formation_active'] = True
            if val.upper() == 'OKBASI':
                parsed['formation_type'] = 1
            elif val.upper() == 'V':
                parsed['formation_type'] = 2
            elif val.upper() == 'CIZGI':
                parsed['formation_type'] = 3
        elif key == 'spacing_m':
            parsed['spacing_m'] = float(val)
        elif key == 'altitude_agl_m':
            parsed['altitude_agl_m'] = float(val)
            parsed['altitude_active'] = True
        elif key == 'pitch_deg':
            parsed['pitch_deg'] = float(val)
            parsed['maneuver_active'] = True
        elif key == 'detach_color':
            parsed['detach_active'] = True
            if val.upper() == 'RED':
                parsed['detach_color'] = 1
            elif val.upper() == 'BLUE':
                parsed['detach_color'] = 2
