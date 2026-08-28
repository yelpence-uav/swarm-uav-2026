# Copyright 2026 Yelpence

"""
test_qr_detector.py.

QRDetector birim testleri.
Pyzbar mocklanarak saf test edilir.
"""

import json
import sys
import unittest
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

    # zxing-cpp 28 Agustos'ta BIRINCIL cozucu oldu (ayni menzil,
    # yari sure). Bu testler AYRISTIRMAYI siniyor, cozuculugu degil;
    # `decode` mock'unun calisabilmesi icin zxing kapatiliyor.
    @patch('swarm_perception.vision_node.qr_detector.zxingcpp', None)
    @patch('swarm_perception.vision_node.qr_detector.decode')
    def test_valid_qr_detection(self, mock_decode: MagicMock) -> None:
        """Geçerli bir şartname JSON QR kodunun başarıyla ayrıştırılması."""
        payload = {
            'qr': 5, 'w': 4,
            'mis': [[['frm', 'v', 2.5]]],
            'team': {'1': [1, 6]},
        }
        mock_obj = MagicMock()
        mock_obj.data = json.dumps(payload).encode('utf-8')
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
        self.assertEqual(res['qr_id'], 5)
        self.assertEqual(res['next_qr'], 6)
        self.assertTrue(res['target_active'])
        self.assertTrue(res['formation_active'])
        self.assertEqual(res['spacing_m'], 2.5)
        self.assertEqual(res['error_message'], '')

    # zxing-cpp 28 Agustos'ta BIRINCIL cozucu oldu (ayni menzil,
    # yari sure). Bu testler AYRISTIRMAYI siniyor, cozuculugu degil;
    # `decode` mock'unun calisabilmesi icin zxing kapatiliyor.
    @patch('swarm_perception.vision_node.qr_detector.zxingcpp', None)
    @patch('swarm_perception.vision_node.qr_detector.decode')
    def test_invalid_team_slot(self, mock_decode: MagicMock) -> None:
        """Takım slotu tabloda yoksa QR geçersiz sayılmalı."""
        payload = {
            'qr': 1, 'w': 4,
            'mis': [[['frm', 'v', 2.5]]],
            'team': {'2': [1, 3]},   # slot 1 tabloda yok
        }
        mock_obj = MagicMock()
        mock_obj.data = json.dumps(payload).encode('utf-8')
        mock_obj.rect.left = 0
        mock_obj.rect.top = 0
        mock_obj.rect.width = 10
        mock_obj.rect.height = 10
        mock_decode.return_value = [mock_obj]

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        results = self.detector.detect(img)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['valid'])
        self.assertIn('slot', results[0]['error_message'].lower())

    def test_parse_formation(self) -> None:
        """Formasyon (frm) komutunun doğru parse edilmesi."""
        text = json.dumps({
            'qr': 1, 'w': 4,
            'mis': [[['frm', 'v', 5.0]]],
            'team': {'1': [1, 3]},
        })
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['valid'])
        self.assertTrue(parsed['formation_active'])
        self.assertEqual(parsed['formation_type'], 2)  # FORMATION_V
        self.assertEqual(parsed['spacing_m'], 5.0)

    def test_parse_maneuver(self) -> None:
        """Manevra (mnv) komutunun doğru parse edilmesi."""
        text = json.dumps({
            'qr': 1, 'w': 4,
            'mis': [[['mnv', -15.5, 0]]],
            'team': {'1': [1, 3]},
        })
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['maneuver_active'])
        self.assertEqual(parsed['pitch_deg'], -15.5)

    def test_parse_detach(self) -> None:
        """Ayrılma (leav) komutunun doğru parse edilmesi."""
        text = json.dumps({
            'qr': 1, 'w': 4,
            'mis': [[['leav', 2, 'r']]],
            'team': {'1': [1, 3]},
        })
        parsed = self.detector._parse_qr_text(text)

        self.assertTrue(parsed['detach_active'])
        self.assertEqual(parsed['detach_color'], 1)  # COLOR_RED


if __name__ == '__main__':
    unittest.main()
