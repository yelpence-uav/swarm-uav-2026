# Copyright 2026 Yelpence

"""
test_frame_grabber.py

FrameGrabber ve SimFrameGrabber birim testleri.

test_telemetry_mapper.py deseni takip edilir:
- SimpleNamespace ile mock nesneler
- unittest.TestCase yapısı
- OpenCV mock ile fiziksel kamera gerektirmez
"""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# cv2 mock'lanmış olsa da frame_grabber'ı import edebilmek için
# conftest.py'deki mock'lar yeterli. Ancak FrameGrabber doğrudan
# cv2 kullandığı için testlerde cv2'yi patch'liyoruz.


class TestSimFrameGrabber(unittest.TestCase):
    """SimFrameGrabber testleri - mock gerektirmez, sentetik frame üretir."""

    def setUp(self):
        # cv2 mock'landığı için SimFrameGrabber'ı burada import
        # ediyoruz - putText mock olarak çalışacak.
        from swarm_perception.camera_driver.frame_grabber import (
            SimFrameGrabber,
        )
        self.SimFrameGrabber = SimFrameGrabber

    def test_open_basarili(self):
        g = self.SimFrameGrabber(width=640, height=480)
        self.assertTrue(g.open_camera())
        self.assertTrue(g.is_opened())

    def test_kapali_grab_basarisiz(self):
        g = self.SimFrameGrabber()
        success, frame = g.grab()
        self.assertFalse(success)
        self.assertIsNone(frame)

    def test_grab_frame_boyut(self):
        g = self.SimFrameGrabber(width=320, height=240)
        g.open_camera()
        success, frame = g.grab()
        self.assertTrue(success)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape[0], 240)  # height
        self.assertEqual(frame.shape[1], 320)  # width
        self.assertEqual(frame.shape[2], 3)    # BGR kanalları

    def test_frame_count_artar(self):
        g = self.SimFrameGrabber(width=160, height=120)
        g.open_camera()
        self.assertEqual(g.frame_count, 0)
        g.grab()
        self.assertEqual(g.frame_count, 1)
        g.grab()
        g.grab()
        self.assertEqual(g.frame_count, 3)

    def test_release(self):
        g = self.SimFrameGrabber()
        g.open_camera()
        self.assertTrue(g.is_opened())
        g.release()
        self.assertFalse(g.is_opened())

    def test_release_sonrasi_grab_basarisiz(self):
        g = self.SimFrameGrabber()
        g.open_camera()
        g.release()
        success, frame = g.grab()
        self.assertFalse(success)

    def test_actual_resolution(self):
        g = self.SimFrameGrabber(width=1280, height=720)
        self.assertEqual(g.actual_resolution, (1280, 720))

    def test_actual_fps_sifir(self):
        g = self.SimFrameGrabber()
        self.assertEqual(g.actual_fps, 0.0)

    def test_last_grab_time_guncellenir(self):
        g = self.SimFrameGrabber(width=160, height=120)
        g.open_camera()
        t0 = g.last_grab_time
        g.grab()
        t1 = g.last_grab_time
        self.assertGreaterEqual(t1, t0)

    def test_varsayilan_boyut_1280x720(self):
        """Varsayılan çözünürlük Gazebo model.sdf ile tutarlı."""
        g = self.SimFrameGrabber()
        self.assertEqual(g.actual_resolution, (1280, 720))


class TestFrameGrabberMock(unittest.TestCase):
    """FrameGrabber testleri - cv2.VideoCapture mock'lanır."""

    def setUp(self):
        from swarm_perception.camera_driver.frame_grabber import (
            FrameGrabber,
        )
        self.FrameGrabber = FrameGrabber

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_open_basarili(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        result = g.open_camera()

        self.assertTrue(result)
        self.assertTrue(g.is_opened())
        mock_cv2.VideoCapture.assert_called_once_with(0)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_open_basarisiz(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=640, height=480, fps=30.0)
        result = g.open_camera()

        self.assertFalse(result)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_grab_basarili(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, test_frame)
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        g.open_camera()
        success, frame = g.grab()

        self.assertTrue(success)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (720, 1280, 3))

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_grab_basarisiz(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        g.open_camera()
        success, frame = g.grab()

        self.assertFalse(success)
        self.assertIsNone(frame)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_flip_vertical(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, test_frame.copy())
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.flip.return_value = test_frame

        g = self.FrameGrabber(
            device_id=0, width=640, height=480, fps=15.0,
            flip_vertical=True,
        )
        g.open_camera()
        g.grab()

        mock_cv2.flip.assert_called_once()
        # flip(frame, 0) - dikey çevirme
        call_args = mock_cv2.flip.call_args
        self.assertEqual(call_args[0][1], 0)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_flip_both(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, test_frame.copy())
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.flip.return_value = test_frame

        g = self.FrameGrabber(
            device_id=0, width=640, height=480, fps=15.0,
            flip_vertical=True, flip_horizontal=True,
        )
        g.open_camera()
        g.grab()

        # flip(frame, -1) - her iki eksen
        call_args = mock_cv2.flip.call_args
        self.assertEqual(call_args[0][1], -1)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_release(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        g.open_camera()
        g.release()

        mock_cap.release.assert_called_once()

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_frame_count(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, test_frame)
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        g.open_camera()
        self.assertEqual(g.frame_count, 0)
        g.grab()
        self.assertEqual(g.frame_count, 1)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_cozunurluk_ayarlari(self, mock_cv2):
        """Kamera açılırken çözünürlük ayarlarının set edildiğini doğrula."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap

        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        g.open_camera()

        # set çağrılarını kontrol et
        set_calls = {
            call[0][0]: call[0][1] for call in mock_cap.set.call_args_list
        }
        self.assertIn(mock_cv2.CAP_PROP_FRAME_WIDTH, set_calls)
        self.assertIn(mock_cv2.CAP_PROP_FRAME_HEIGHT, set_calls)
        self.assertIn(mock_cv2.CAP_PROP_FPS, set_calls)

    @patch('swarm_perception.camera_driver.frame_grabber.cv2')
    def test_kapali_kamerada_grab_basarisiz(self, mock_cv2):
        g = self.FrameGrabber(device_id=0, width=1280, height=720, fps=15.0)
        # open() çağrılmadı
        success, frame = g.grab()
        self.assertFalse(success)
        self.assertIsNone(frame)


if __name__ == '__main__':
    unittest.main()
