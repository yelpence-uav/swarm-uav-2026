"""formation_node.py mantık metodları için birim testleri.

ROS2 runtime gerektirmeyen saf mantık metodları test edilir.
FormationControlNode, object.__new__ ile __init__ atlanarak
oluşturulur; sadece test edilen metodun ihtiyacı olan state
elle set edilir.
"""

import math
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from swarm_core.formation_control.formation_geometry import (
    FORMATION_OKBASI,
    FORMATION_V,
    FORMATION_CIZGI,
)
from swarm_core.formation_control.formation_node import (
    FormationControlNode,
)


def _make_node(
    agent_id: int = 1,
    default_spacing: float = 5.0,
    max_speed: float = 3.0,
    svt_gain: float = 0.2,
    svt_threshold: float = 2.0,
) -> FormationControlNode:
    """
    ROS2 olmadan test için minimal FormationControlNode oluşturur.

    Args:
        agent_id (int): Drone kimlik numarası.
        default_spacing (float): Varsayılan ajan aralığı, metre.
        max_speed (float): Maksimum hız sınırı, m/s.
        svt_gain (float): SVT elastik kazancı.
        svt_threshold (float): SVT aktivasyon eşiği, metre.

    Returns:
        FormationControlNode: Kısmi başlatılmış node.
    """
    node = object.__new__(FormationControlNode)
    node._agent_id = agent_id
    node._default_spacing_m = default_spacing
    node._alpha_deg = 30.0
    node._alpha_rad = math.radians(30.0)
    node._max_speed_mps = max_speed
    node._svt_gain = svt_gain
    node._svt_threshold_m = svt_threshold
    node._position_tolerance_m = 0.5
    node._heading_tolerance_deg = 5.0
    node._publish_rate_hz = 20.0

    node._current_formation = None
    node._latest_swarm_state = None
    node._active_agent_ids = []
    node._sequence_num = 0

    node._current_pos_x = 0.0
    node._current_pos_y = 0.0
    node._current_pos_z = 0.0
    node._pos_valid = False
    node._oscillating = False

    node._centroid_vel_x = 0.0
    node._centroid_vel_y = 0.0
    node._centroid_vel_z = 0.0
    node._prev_centroid_x = 0.0
    node._prev_centroid_y = 0.0
    node._prev_centroid_z = 0.0
    node._prev_centroid_time = None

    _mock_logger = MagicMock()
    node.get_logger = MagicMock(return_value=_mock_logger)

    def _fake_clock():
        _now = MagicMock()
        _now.nanoseconds = int(time.monotonic() * 1e9)
        _c = MagicMock()
        _c.now = MagicMock(return_value=_now)
        return _c

    node.get_clock = _fake_clock
    return node


def _cmd(
    spacing_m: float = 0.0,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = -10.0,
    use_current_centroid: bool = False,
    use_current_altitude: bool = False,
    heading_deg: float = 0.0,
    max_speed_mps: float = 0.0,
    formation_type: int = FORMATION_OKBASI,
) -> SimpleNamespace:
    """
    Test için sahte FormationCommand nesnesi döner.

    Args:
        spacing_m (float): Ajan aralığı; 0 ise default kullanılır.
        center_x (float): Formasyon merkezi NED X, metre.
        center_y (float): Formasyon merkezi NED Y, metre.
        center_z (float): Formasyon merkezi NED Z, metre.
        use_current_centroid (bool): Anlık centroid kullanılsın mı?
        use_current_altitude (bool): Anlık centroid Z kullanılsın mı?
        heading_deg (float): Formasyon yönü, derece.
        max_speed_mps (float): Maksimum hız; 0 ise default.
        formation_type (int): Formasyon tipi sabiti.

    Returns:
        SimpleNamespace: Sahte FormationCommand.
    """
    return SimpleNamespace(
        formation_type=formation_type,
        spacing_m=spacing_m,
        center_x=center_x,
        center_y=center_y,
        center_z=center_z,
        use_current_centroid=use_current_centroid,
        use_current_altitude=use_current_altitude,
        heading_deg=heading_deg,
        max_speed_mps=max_speed_mps,
    )


def _state(
    active_agent_ids=None,
    centroid_x: float = 0.0,
    centroid_y: float = 0.0,
    centroid_z: float = -10.0,
    mission_active: bool = True,
    swarm_state: int = 0,
) -> SimpleNamespace:
    """
    Test için sahte SwarmState nesnesi döner.

    Args:
        active_agent_ids (list): Aktif ajan ID listesi.
        centroid_x (float): Sürü centroid NED X, metre.
        centroid_y (float): Sürü centroid NED Y, metre.
        centroid_z (float): Sürü centroid NED Z, metre.
        mission_active (bool): Görev aktif mi?
        swarm_state (int): Sürü durum kodu.

    Returns:
        SimpleNamespace: Sahte SwarmState.
    """
    return SimpleNamespace(
        active_agent_ids=active_agent_ids or [],
        centroid_x=centroid_x,
        centroid_y=centroid_y,
        centroid_z=centroid_z,
        mission_active=mission_active,
        swarm_state=swarm_state,
    )


class TestResolveSpacing(unittest.TestCase):
    """_resolve_spacing metodunun testleri."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node(default_spacing=5.0)

    def test_qr_spacing_kullanilir(self):
        """spacing_m > 0 ise QR'dan gelen değer döner."""
        result = self.node._resolve_spacing(_cmd(spacing_m=8.0))
        self.assertAlmostEqual(result, 8.0)

    def test_default_spacing_kullanilir(self):
        """spacing_m = 0 ise YAML default'u döner."""
        result = self.node._resolve_spacing(_cmd(spacing_m=0.0))
        self.assertAlmostEqual(result, 5.0)

    def test_negatif_spacing_default_donmez(self):
        """Negatif spacing_m = 0 ise default döner."""
        result = self.node._resolve_spacing(_cmd(spacing_m=-1.0))
        self.assertAlmostEqual(result, 5.0)


class TestResolveCenter(unittest.TestCase):
    """_resolve_center metodunun testleri."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node()

    def test_swarm_state_yoksa_cmd_degerleri(self):
        """SwarmState gelmemişse komuttaki merkez döner."""
        self.node._latest_swarm_state = None
        cx, cy, cz = self.node._resolve_center(
            _cmd(center_x=1.0, center_y=2.0, center_z=-15.0)
        )
        self.assertAlmostEqual(cx, 1.0)
        self.assertAlmostEqual(cy, 2.0)
        self.assertAlmostEqual(cz, -15.0)

    def test_use_current_centroid_xy_guncellenir(self):
        """use_current_centroid=True ise X/Y SwarmState'ten alınır."""
        self.node._latest_swarm_state = _state(
            centroid_x=10.0, centroid_y=20.0, centroid_z=-5.0
        )
        cx, cy, cz = self.node._resolve_center(
            _cmd(
                center_x=1.0,
                center_y=2.0,
                center_z=-15.0,
                use_current_centroid=True,
            )
        )
        self.assertAlmostEqual(cx, 10.0)
        self.assertAlmostEqual(cy, 20.0)
        self.assertAlmostEqual(cz, -15.0)

    def test_use_current_altitude_z_guncellenir(self):
        """use_current_altitude=True ise sadece Z SwarmState'ten alınır."""
        self.node._latest_swarm_state = _state(
            centroid_x=10.0, centroid_y=20.0, centroid_z=-5.0
        )
        cx, cy, cz = self.node._resolve_center(
            _cmd(
                center_x=1.0,
                center_y=2.0,
                center_z=-15.0,
                use_current_altitude=True,
            )
        )
        self.assertAlmostEqual(cx, 1.0)
        self.assertAlmostEqual(cy, 2.0)
        self.assertAlmostEqual(cz, -5.0)

    def test_her_iki_flag_birlikte(self):
        """Her iki flag True ise X/Y/Z SwarmState'ten alınır."""
        self.node._latest_swarm_state = _state(
            centroid_x=10.0, centroid_y=20.0, centroid_z=-5.0
        )
        cx, cy, cz = self.node._resolve_center(
            _cmd(
                center_x=1.0,
                center_y=2.0,
                center_z=-15.0,
                use_current_centroid=True,
                use_current_altitude=True,
            )
        )
        self.assertAlmostEqual(cx, 10.0)
        self.assertAlmostEqual(cy, 20.0)
        self.assertAlmostEqual(cz, -5.0)

    def test_flag_false_cmd_degerleri(self):
        """Her iki flag False ise komuttaki değerler korunur."""
        self.node._latest_swarm_state = _state(
            centroid_x=10.0, centroid_y=20.0, centroid_z=-5.0
        )
        cx, cy, cz = self.node._resolve_center(
            _cmd(center_x=1.0, center_y=2.0, center_z=-15.0)
        )
        self.assertAlmostEqual(cx, 1.0)
        self.assertAlmostEqual(cy, 2.0)
        self.assertAlmostEqual(cz, -15.0)


class TestFindRank(unittest.TestCase):
    """_find_rank metodunun testleri."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node(agent_id=2)

    def test_rank_bulunur(self):
        """agent_id listede varsa doğru rank döner."""
        self.node._active_agent_ids = [1, 2, 3]
        self.assertEqual(self.node._find_rank(), 1)

    def test_lider_rank_sifir(self):
        """En küçük ID her zaman rank 0 (lider)."""
        self.node._agent_id = 1
        self.node._active_agent_ids = [1, 2, 3]
        self.assertEqual(self.node._find_rank(), 0)

    def test_listede_yok_none(self):
        """agent_id listede yoksa None döner."""
        self.node._active_agent_ids = [1, 3, 4]
        self.assertIsNone(self.node._find_rank())

    def test_bos_liste_none(self):
        """Liste boşsa None döner."""
        self.node._active_agent_ids = []
        self.assertIsNone(self.node._find_rank())

    def test_tek_eleman_rank_sifir(self):
        """Tek drone varsa rank 0 döner."""
        self.node._agent_id = 5
        self.node._active_agent_ids = [5]
        self.assertEqual(self.node._find_rank(), 0)


class TestComputeVelocity(unittest.TestCase):
    """_compute_velocity metodunun testleri."""

    def setUp(self):
        """Her test için svt_gain=0.5, threshold=2.0 node hazırlar."""
        self.node = _make_node(
            svt_gain=0.5,
            svt_threshold=2.0,
            max_speed=5.0,
        )

    def test_pos_valid_yok_sifir_hiz(self):
        """pos_valid=False ise SVT ve FF uygulanmaz, sıfır döner."""
        self.node._pos_valid = False
        vx, vy, vz = self.node._compute_velocity(
            10.0, 0.0, 0.0, max_speed=5.0
        )
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_esik_altinda_svt_uygulanmaz(self):
        """Hata < threshold ise SVT katkısı sıfırdır."""
        self.node._pos_valid = True
        self.node._current_pos_x = 9.5
        self.node._current_pos_y = 0.0
        self.node._current_pos_z = 0.0
        # Hata = 0.5 < threshold=2.0
        vx, vy, vz = self.node._compute_velocity(
            10.0, 0.0, 0.0, max_speed=5.0
        )
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_esik_ustunde_svt_uygulanir(self):
        """Hata > threshold ise SVT elastik kuvveti eklenir."""
        self.node._pos_valid = True
        self.node._current_pos_x = 5.0
        self.node._current_pos_y = 0.0
        self.node._current_pos_z = 0.0
        # Hedef x=10, hata=5 > threshold=2 → vx = 0.5*5 = 2.5
        vx, vy, vz = self.node._compute_velocity(
            10.0, 0.0, 0.0, max_speed=5.0
        )
        self.assertAlmostEqual(vx, 2.5)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_oscillating_svt_bypass(self):
        """oscillating=True ise SVT uygulanmaz."""
        self.node._pos_valid = True
        self.node._oscillating = True
        self.node._current_pos_x = 0.0
        # Hata büyük ama oscilasyon → SVT sıfır
        vx, vy, vz = self.node._compute_velocity(
            10.0, 0.0, 0.0, max_speed=5.0
        )
        self.assertAlmostEqual(vx, 0.0)

    def test_max_speed_asimaz(self):
        """Hesaplanan hız max_speed'i aşarsa ölçeklenir."""
        self.node._pos_valid = True
        self.node._current_pos_x = 0.0
        self.node._current_pos_y = 0.0
        self.node._current_pos_z = 0.0
        # Hata = sqrt(100+100+100) ≈ 17.3, gain=0.5 → hız büyük
        vx, vy, vz = self.node._compute_velocity(
            10.0, 10.0, 10.0, max_speed=3.0
        )
        speed = math.sqrt(vx**2 + vy**2 + vz**2)
        self.assertAlmostEqual(speed, 3.0, places=6)

    def test_ff_xy_aktif(self):
        """use_ff_xy=True ise centroid XY hızı eklenir."""
        self.node._pos_valid = False
        self.node._centroid_vel_x = 2.0
        self.node._centroid_vel_y = 1.0
        self.node._centroid_vel_z = 0.5
        vx, vy, vz = self.node._compute_velocity(
            0.0, 0.0, 0.0, max_speed=5.0,
            use_ff_xy=True, use_ff_z=False,
        )
        self.assertAlmostEqual(vx, 2.0)
        self.assertAlmostEqual(vy, 1.0)
        self.assertAlmostEqual(vz, 0.0)

    def test_ff_z_aktif(self):
        """use_ff_z=True ise centroid Z hızı eklenir."""
        self.node._pos_valid = False
        self.node._centroid_vel_x = 2.0
        self.node._centroid_vel_y = 1.0
        self.node._centroid_vel_z = 0.5
        vx, vy, vz = self.node._compute_velocity(
            0.0, 0.0, 0.0, max_speed=5.0,
            use_ff_xy=False, use_ff_z=True,
        )
        self.assertAlmostEqual(vx, 0.0)
        self.assertAlmostEqual(vy, 0.0)
        self.assertAlmostEqual(vz, 0.5)


class TestOnSwarmState(unittest.TestCase):
    """_on_swarm_state metodundaki centroid reset mantığının testleri."""

    def setUp(self):
        """Her test için node hazırlar."""
        self.node = _make_node(agent_id=2)

    def _call(self, active_ids, cx=0.0, cy=0.0, cz=0.0):
        """Sahte SwarmState ile _on_swarm_state çağırır."""
        self.node._prev_centroid_time = None
        self.node._latest_swarm_state = None
        self.node._active_agent_ids = []
        msg = _state(
            active_agent_ids=active_ids,
            centroid_x=cx,
            centroid_y=cy,
            centroid_z=cz,
        )
        self.node._on_swarm_state(msg)

    def test_active_ids_guncellenir(self):
        """Yeni active_agent_ids listesi saklanır."""
        self._call([1, 2, 3])
        self.assertEqual(self.node._active_agent_ids, [1, 2, 3])

    def test_n_degisince_centroid_vel_sifirlanir(self):
        """Aktif ajan sayısı değişince centroid hızı sıfırlanır."""
        self.node._centroid_vel_x = 5.0
        self.node._centroid_vel_y = 3.0
        self.node._centroid_vel_z = 1.0
        self._call([1, 2])
        self.assertAlmostEqual(self.node._centroid_vel_x, 0.0)
        self.assertAlmostEqual(self.node._centroid_vel_y, 0.0)
        self.assertAlmostEqual(self.node._centroid_vel_z, 0.0)

    def test_n_degismeyince_vel_korunur(self):
        """Aynı ID listesiyle centroid hızı sıfırlanmaz."""
        self.node._active_agent_ids = [1, 2, 3]
        self.node._prev_centroid_time = None
        self.node._centroid_vel_x = 5.0
        msg = _state(active_agent_ids=[1, 2, 3])
        self.node._on_swarm_state(msg)
        self.assertAlmostEqual(self.node._centroid_vel_x, 5.0)

    def test_sortlanmis_liste_saklanir(self):
        """ID listesi her zaman küçükten büyüğe sıralanır."""
        self._call([3, 1, 2])
        self.assertEqual(self.node._active_agent_ids, [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
