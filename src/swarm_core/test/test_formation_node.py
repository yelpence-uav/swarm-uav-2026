"""formation_node.py - formasyon düğümü birim testleri."""

import math
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from swarm_core.formation_control.formation_node import (
    FormationControlNode,
)


def _make_node(
    agent_id: int = 1,
    max_speed: float = 3.0,
    svt_gain: float = 0.2,
    svt_threshold: float = 2.0,
    rel_k: float = 0.5,
    rel_threshold: float = 0.2,
    rel_stale_s: float = 0.5,
    rel_enable: bool = True,
) -> FormationControlNode:
    """ROS2 olmadan test için minimal FormationControlNode oluşturur."""
    node = object.__new__(FormationControlNode)
    node._agent_id = agent_id
    node._max_speed_mps = max_speed
    node._svt_k = svt_gain
    node._svt_threshold_m = svt_threshold
    node._svt_k_z = 2.0
    node._svt_threshold_z_m = 0.05
    node._position_tolerance_m = 0.5
    node._heading_tolerance_deg = 5.0
    node._publish_rate_hz = 20.0

    node._current_formation = None
    node._sequence_num = 0

    node._current_pos_x = 0.0
    node._current_pos_y = 0.0
    node._current_pos_z = 0.0
    # OSİLASYON DÜZELTMESİ: tether hız sönümü için gereken alanlar.
    # _current_vel=0 ve ff varsayılan=0 - damping katkısı 0.
    node._svt_damp = 0.2
    node._current_vel_x = 0.0
    node._current_vel_y = 0.0
    node._current_vel_z = 0.0
    node._pos_valid = False
    node._oscillating = False

    # _shared_to_local için gereken alanlar
    node._origin_lat = None
    node._origin_lon = None
    node._gps_valid = False
    node._current_lat = 0.0
    node._current_lon = 0.0

    # Dağıtık slot ataması: yerel hesap yoksa lider ofsetine düşülür.
    node._local_offsets = None
    node._local_offsets_type = None
    node._wing_alpha_rad = math.radians(45.0)

    # A7 — göreli (komşu tabanlı) koruma alanları
    node._rel_enable = rel_enable
    node._rel_k = rel_k
    node._rel_threshold_m = rel_threshold
    node._rel_stale_s = rel_stale_s
    node._neighbors = {}
    node._neighbor_rx_time = {}
    node._neighbor_subs = {}

    _mock_logger = MagicMock()
    node.get_logger = MagicMock(return_value=_mock_logger)
    return node


def _fcmd(agent_ids, off_x, off_y, off_z, heading_deg=0.0) -> SimpleNamespace:
    """A7 testleri için atama+offset içeren sahte FormationCommand."""
    return SimpleNamespace(
        agent_ids=agent_ids,
        offset_x=off_x,
        offset_y=off_y,
        offset_z=off_z,
        heading_deg=heading_deg,
    )


def _neighbor(
    rel_x, rel_y, rel_z,
    link_active=True,
    rel_vx=0.0, rel_vy=0.0, rel_vz=0.0,
) -> SimpleNamespace:
    """Sahte NeighborInfo (göreli konum + göreli hız + link durumu)."""
    return SimpleNamespace(
        relative_x=rel_x,
        relative_y=rel_y,
        relative_z=rel_z,
        relative_vx=rel_vx,
        relative_vy=rel_vy,
        relative_vz=rel_vz,
        link_active=link_active,
    )


def _cmd(
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = -10.0,
) -> SimpleNamespace:
    """Test için sahte FormationCommand (yalnızca merkez alanları)."""
    return SimpleNamespace(
        center_x=center_x,
        center_y=center_y,
        center_z=center_z,
    )


class TestResolveCenter(unittest.TestCase):
    """_resolve_center artık merkezi doğrudan komuttan döndürür."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node()

    def test_merkez_komuttan_doner(self):
        """Merkez koordinatları komuttaki değerlerle birebir döner."""
        cx, cy, cz = self.node._resolve_center(
            _cmd(center_x=1.0, center_y=2.0, center_z=-15.0)
        )
        self.assertAlmostEqual(cx, 1.0)
        self.assertAlmostEqual(cy, 2.0)
        self.assertAlmostEqual(cz, -15.0)

    def test_sifir_merkez(self):
        """Varsayılan komutta merkez (0, 0, -10) döner."""
        cx, cy, cz = self.node._resolve_center(_cmd())
        self.assertAlmostEqual(cx, 0.0)
        self.assertAlmostEqual(cy, 0.0)
        self.assertAlmostEqual(cz, -10.0)


class TestComputeVelocity(unittest.TestCase):
    """_compute_velocity: yalnızca SVT düzeltmesi (merkezi FF yok)."""

    def setUp(self):
        """svt_gain=0.5, threshold=2.0, max_speed=5.0 node hazırlar."""
        self.node = _make_node(
            svt_gain=0.5,
            svt_threshold=2.0,
            max_speed=5.0,
        )

    def test_pos_valid_yok_sifir_hiz(self):
        """pos_valid=False ise SVT uygulanmaz, sıfır döner."""
        self.node._pos_valid = False
        vx, vy, vz = self.node._compute_velocity(10.0, 0.0, 0.0, 5.0)
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_esik_altinda_svt_uygulanmaz(self):
        """XY hatası < threshold ise SVT katkısı sıfırdır."""
        self.node._pos_valid = True
        self.node._current_pos_x = 9.5
        # Hata = 0.5 < threshold=2.0
        vx, vy, vz = self.node._compute_velocity(10.0, 0.0, 0.0, 5.0)
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_esik_ustunde_svt_uygulanir(self):
        """XY hatası > threshold ise SVT elastik kuvveti hedefe çeker."""
        self.node._pos_valid = True
        self.node._current_pos_x = 5.0
        # hata = 5-10 = -5, dist=5 > 2 -> vx = -0.5*(-5) = 2.5
        vx, vy, vz = self.node._compute_velocity(10.0, 0.0, 0.0, 5.0)
        self.assertAlmostEqual(vx, 2.5)
        self.assertAlmostEqual(vy, 0.0)

    def test_z_svt_uygulanir(self):
        """Z hatası eşiği aşınca dikey SVT uygulanır."""
        self.node._pos_valid = True
        self.node._current_pos_z = 0.0
        # target_z=-1 -> ez = 0-(-1) = 1, vz = -2.0*1 = -2.0
        vx, vy, vz = self.node._compute_velocity(0.0, 0.0, -1.0, 5.0)
        self.assertAlmostEqual(vz, -2.0)

    def test_oscillating_svt_uygulanir(self):
        """C-modu: oscillating=True olsa bile SVT uygulanır (atlanmaz)."""
        self.node._pos_valid = True
        self.node._oscillating = True
        self.node._current_pos_x = 0.0
        vx, vy, vz = self.node._compute_velocity(10.0, 0.0, 0.0, 5.0)
        self.assertAlmostEqual(vx, 5.0)

    def test_max_speed_asimaz(self):
        """Hesaplanan hız max_speed'i aşarsa ölçeklenir."""
        self.node._pos_valid = True
        vx, vy, vz = self.node._compute_velocity(10.0, 10.0, 10.0, 3.0)
        speed = math.sqrt(vx**2 + vy**2 + vz**2)
        self.assertAlmostEqual(speed, 3.0, places=6)


class TestSharedToLocal(unittest.TestCase):
    """_shared_to_local: shared NED -> local NED dönüşümü."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node()

    def test_origin_yoksa_passthrough(self):
        """Origin yoksa shared koordinat aynen döner."""
        self.node._origin_lat = None
        self.node._gps_valid = False
        x, y = self.node._shared_to_local(5.0, 7.0)
        self.assertAlmostEqual(x, 5.0)
        self.assertAlmostEqual(y, 7.0)

    def test_gps_yoksa_passthrough(self):
        """GPS geçerli değilse shared koordinat aynen döner."""
        self.node._origin_lat = 40.0
        self.node._origin_lon = 30.0
        self.node._gps_valid = False
        x, y = self.node._shared_to_local(5.0, 7.0)
        self.assertAlmostEqual(x, 5.0)
        self.assertAlmostEqual(y, 7.0)

    def test_konum_origin_ile_ayni_offset_eklenir(self):
        """Drone GPS'i origin ile aynıysa local = shared + mevcut konum."""
        self.node._origin_lat = 40.0
        self.node._origin_lon = 30.0
        self.node._gps_valid = True
        self.node._current_lat = 40.0
        self.node._current_lon = 30.0
        self.node._current_pos_x = 2.0
        self.node._current_pos_y = 3.0
        # cur_n=0, cur_e=0 -> x = 5-0+2 = 7 ; y = 7-0+3 = 10
        x, y = self.node._shared_to_local(5.0, 7.0)
        self.assertAlmostEqual(x, 7.0)
        self.assertAlmostEqual(y, 10.0)


class TestRelativeCorrection(unittest.TestCase):
    """_compute_relative_correction (A7 göreli koruma) testleri."""

    def setUp(self):
        """agent_id=1, rel_k=0.5, threshold=0.2 node hazırlar."""
        self.node = _make_node(agent_id=1, rel_k=0.5, rel_threshold=0.2)
        # offset: drone1=(0,0,0), drone2=(0,8,0) -> istenen göreli (0,+8)
        self.msg = _fcmd(
            agent_ids=[1, 2],
            off_x=[0.0, 0.0],
            off_y=[0.0, 8.0],
            off_z=[0.0, 0.0],
            heading_deg=0.0,
        )

    def test_rel_disable_sifir(self):
        """rel_enable=False ise düzeltme sıfırdır."""
        self.node._rel_enable = False
        self.node._neighbors = {2: _neighbor(0.0, 10.0, 0.0)}
        self.node._neighbor_rx_time = {2: 100.0}
        v = self.node._compute_relative_correction(self.msg, 0, 0.0, 100.0)
        self.assertEqual(v, (0.0, 0.0, 0.0))

    def test_komsu_yok_sifir(self):
        """Hiç komşu verisi yoksa düzeltme sıfırdır."""
        self.node._neighbors = {}
        v = self.node._compute_relative_correction(self.msg, 0, 0.0, 100.0)
        self.assertEqual(v, (0.0, 0.0, 0.0))

    def test_komsu_uzaksa_yaklasir(self):
        """Komşu istenen mesafeden uzaksa o yöne doğru düzeltir."""
        # istenen (0,8), gerçek (0,10) -> hata=+2 -> vy = 0.5*2 = 1.0
        self.node._neighbors = {2: _neighbor(0.0, 10.0, 0.0)}
        self.node._neighbor_rx_time = {2: 100.0}
        vx, vy, vz = self.node._compute_relative_correction(
            self.msg, 0, 0.0, 100.0
        )
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 1.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_komsu_yakinsa_uzaklasir(self):
        """Komşu istenenden yakınsa ters yöne düzeltir."""
        # istenen (0,8), gerçek (0,6) -> hata=-2 -> vy = 0.5*-2 = -1.0
        self.node._neighbors = {2: _neighbor(0.0, 6.0, 0.0)}
        self.node._neighbor_rx_time = {2: 100.0}
        vx, vy, vz = self.node._compute_relative_correction(
            self.msg, 0, 0.0, 100.0
        )
        self.assertAlmostEqual(vy, -1.0)

    def test_esik_altinda_sifir(self):
        """Hata deadband eşiğinin altındaysa düzeltme sıfırdır."""
        # istenen (0,8), gerçek (0,8.1) -> hata=0.1 < 0.2 -> 0
        self.node._neighbors = {2: _neighbor(0.0, 8.1, 0.0)}
        self.node._neighbor_rx_time = {2: 100.0}
        vx, vy, vz = self.node._compute_relative_correction(
            self.msg, 0, 0.0, 100.0
        )
        self.assertAlmostEqual(vy, 0.0)

    def test_link_kopuk_atlanir(self):
        """link_active=False komşu hesaba katılmaz (mutlak fallback)."""
        self.node._neighbors = {2: _neighbor(0.0, 10.0, 0.0,
                                             link_active=False)}
        self.node._neighbor_rx_time = {2: 100.0}
        v = self.node._compute_relative_correction(self.msg, 0, 0.0, 100.0)
        self.assertEqual(v, (0.0, 0.0, 0.0))

    def test_bayat_veri_atlanir(self):
        """Eski (stale) NeighborInfo hesaba katılmaz."""
        self.node._neighbors = {2: _neighbor(0.0, 10.0, 0.0)}
        # rx=100, now=101 -> 1.0s > rel_stale_s=0.5 -> bayat
        self.node._neighbor_rx_time = {2: 100.0}
        v = self.node._compute_relative_correction(self.msg, 0, 0.0, 101.0)
        self.assertEqual(v, (0.0, 0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
