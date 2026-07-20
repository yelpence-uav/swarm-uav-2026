# Copyright 2026 Yelpence
"""Pyzbar kullanarak BGR goruntulerde QR kod tespiti yapan modul."""

from typing import Any, Dict, List

import numpy as np

from pyzbar.pyzbar import decode


class QRDetector:
    """Goruntudeki QR kodlarini bulup ayristiran sinif."""

    def __init__(self, min_confidence: float = 0.5) -> None:
        """
        QRDetector sinifini ilklendirir.

        Args:
            min_confidence (float): Asgari guven esigi.
        """
        self._min_confidence = min_confidence

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        BGR goruntu uzerindeki QR kodlari bulur ve ayristirir.

        Args:
            image: cv2 formatinda BGR goruntu matrisi.

        Returns:
            List[Dict[str, Any]]: Ayristirilmis QR veri sozluk listesi.
        """
        if image is None or image.size == 0:
            return []

        decoded_objects = decode(image)
        results = []
        for obj in decoded_objects:
            try:
                raw_text = obj.data.decode('utf-8')
            except UnicodeDecodeError:
                continue

            rect = obj.rect
            img_h, img_w = image.shape[:2]

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
        """QR kod metnini noktalı virgül (;) ile ayristirir."""
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

        if parsed['team_id'] == 'YELPENCE':
            parsed['valid'] = True
        else:
            parsed['error_message'] = 'Gecersiz takim ID'

        return parsed

    def _assign_field(
        self, parsed: Dict[str, Any], key: str, val: str
    ) -> None:
        """Ayristirilan alani veri sozlugune atar."""
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
