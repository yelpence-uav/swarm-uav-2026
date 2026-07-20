# Copyright 2026 Yelpence

"""
test_qr_detector.py

QRDetector birim testleri.
Pyzbar mocklanarak saf test edilir.
"""

import unittest
import sys
from unittest.mock import MagicMock, patch

import numpy as np

# Pyzbar GitHub Actions uzerinde bulunamazsa testlerin
# 'ModuleNotFoundError' vererek patlamasini onlemek icin
# sahte (mock) modul yuklenir.
sys.modules['pyzbar'] = MagicMock()
sys.modules['pyzbar.pyzbar'] = MagicMock()

from swarm_perception.vision_node.qr_detector import QRDetector  # noqa: E402


class TestQRDetector(unittest.TestCase):
    """QRDetector sınıfı için birim testler."""

    def setUp(self) -> None:
        self.detector = QRDetector()

    def test_empty_image(self) -> None:
        """Boş görüntü verildiğinde boş liste dönmeli."""
        self.assertEqual(self.detector.detect(None), [])
        self.assertEqual(self.detector.detect(np.array([])), [])

    @patch('swarm_perception.vision_node.qr_detector.decode')
    def test_valid_qr_detection(self, mock_decode: MagicMock) -> None:
        """Geçerli bir YELPENCE QR kodunun başarıyla ayrıştırılması."""
        mock_obj = MagicMock()
        mock_obj.data = b'team_id=YELPENCE; qr_id=5; next_qr=6; spacing_m=2.5'
        mock_obj.rect.left = 100
        mock_obj.rect.top = 100
        mock_obj.rect.width = 50
        mock_obj.rect.height = 50
        mock_decode.return_value = [mock_obj]

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        results = self.detector.detect(img)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res['valid'])
        self.assertEqual(res['team_id'], 'YELPENCE')
        self.assertEqual(res['qr_id'], 5)
        self.assertEqual(res['next_qr'], 6)
        self.assertTrue(res['target_active'])
        self.assertEqual(res['spacing_m'], 2.5)
        self.assertEqual(res['error_message'], '')

    @patch('swarm_perception.vision_node.qr_detector.decode')
    def test_invalid_team_id(self, mock_decode: MagicMock) -> None:
        """Farklı bir takıma ait QR kodunun geçersiz sayılması."""
        mock_obj = MagicMock()
        mock_obj.data = b'team_id=BASKATAKIM; qr_id=1'
        mock_obj.rect.left = 0
        mock_obj.rect.top = 0
        mock_obj.rect.width = 10
        mock_obj.rect.height = 10
        mock_decode.return_value = [mock_obj]

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        results = self.detector.detect(img)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['valid'])
        self.assertEqual(results[0]['error_message'], 'Gecersiz takim ID')

    def test_parse_formation(self) -> None:
        """Formasyon verilerinin doğru parse edilmesi."""
        text = 'team_id=YELPENCE; formation=V; spacing_m=5.0'
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['valid'])
        self.assertTrue(parsed['formation_active'])
        self.assertEqual(parsed['formation_type'], 2)  # FORMATION_V
        self.assertEqual(parsed['spacing_m'], 5.0)

    def test_parse_maneuver(self) -> None:
        """Manevra verilerinin doğru parse edilmesi."""
        text = 'team_id=YELPENCE; pitch_deg=-15.5'
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['maneuver_active'])
        self.assertEqual(parsed['pitch_deg'], -15.5)

    def test_parse_detach(self) -> None:
        """Ayrılma ve renk verilerinin doğru parse edilmesi."""
        text = 'team_id=YELPENCE; detach_color=RED'
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['detach_active'])
        self.assertEqual(parsed['detach_color'], 1)  # COLOR_RED


if __name__ == '__main__':
    unittest.main()
