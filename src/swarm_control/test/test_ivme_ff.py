"""Ivme ileri-beslemesi testleri (20 Agustos 2026).

30 m bacakta olculdu: hizlanmada tepe hata 1.12 m, frenlemede asim 1.18 m.
Ikisi de PX4'un komut hizinin degisecegini bilmemesinden. Bu testler ivme
kanalinin dogru YONDE ve dogru CERCEVEDE gittigini kilitler — isaret hatasi
frenlemesi gereken ucagi hizlandirirdi.
"""
import unittest
from unittest.mock import MagicMock

try:
    from builtin_interfaces.msg import Time
    from mavros_msgs.msg import PositionTarget
    from swarm_control.px4_interface.mavros_command_sender import (
        _MASK_POS_VEL, _MASK_POS_VEL_ACC, MavrosCommandSender,
    )
    _VAR = True
except ImportError:
    _VAR = False

_PT = PositionTarget if _VAR else None


def _node():
    n = MagicMock()
    n.get_clock.return_value.now.return_value.to_msg.return_value = Time()
    return n


@unittest.skipUnless(_VAR, 'ROS ortami yok')
class TestMaske(unittest.TestCase):
    def test_acc_maskesinde_IGNORE_AF_bitleri_YOK(self):
        for bit in (_PT.IGNORE_AFX, _PT.IGNORE_AFY, _PT.IGNORE_AFZ):
            self.assertFalse(_MASK_POS_VEL_ACC & bit)

    def test_eski_maskede_IGNORE_AF_bitleri_DURUYOR(self):
        # Ivme verilmediginde davranis DEGISMEMELI.
        for bit in (_PT.IGNORE_AFX, _PT.IGNORE_AFY, _PT.IGNORE_AFZ):
            self.assertTrue(_MASK_POS_VEL & bit)

    def test_iki_maske_yalniz_AF_bitlerinde_ayriliyor(self):
        af = _PT.IGNORE_AFX | _PT.IGNORE_AFY | _PT.IGNORE_AFZ
        self.assertEqual(_MASK_POS_VEL & ~af, _MASK_POS_VEL_ACC & ~af)


@unittest.skipUnless(_VAR, 'ROS ortami yok')
class TestYayin(unittest.TestCase):
    def _gonder(self, **kw):
        n = _node()
        s = MavrosCommandSender(n, '/drone_1')
        s.publish_position_velocity_setpoint(1.0, 2.0, -3.0,
                                             0.5, 0.6, -0.7, **kw)
        return s._setpoint_pub.publish.call_args[0][0]

    def test_ivme_verilmezse_eski_maske_ve_sifir_ivme(self):
        m = self._gonder()
        self.assertEqual(m.type_mask, _MASK_POS_VEL)
        self.assertEqual(m.acceleration_or_force.x, 0.0)

    def test_ivme_verilirse_maske_degisir(self):
        m = self._gonder(ax=1.0, ay=2.0, az=-3.0)
        self.assertEqual(m.type_mask, _MASK_POS_VEL_ACC)

    def test_ivme_NED_ENU_donusumu_konumla_AYNI(self):
        # NED (kuzey=1, dogu=2, asagi=-3) -> ENU (dogu=2, kuzey=1, yukari=3)
        m = self._gonder(ax=1.0, ay=2.0, az=-3.0)
        self.assertAlmostEqual(m.acceleration_or_force.x, 2.0)   # dogu
        self.assertAlmostEqual(m.acceleration_or_force.y, 1.0)   # kuzey
        self.assertAlmostEqual(m.acceleration_or_force.z, 3.0)   # yukari
        # konumla ayni donusum:
        self.assertAlmostEqual(m.position.x, 2.0)
        self.assertAlmostEqual(m.position.y, 1.0)
        self.assertAlmostEqual(m.position.z, 3.0)

    def test_kismi_ivme_yok_sayilir(self):
        # Ucu birden verilmezse eski davranis (yarim veri tehlikeli).
        m = self._gonder(ax=1.0, ay=2.0)
        self.assertEqual(m.type_mask, _MASK_POS_VEL)


if __name__ == '__main__':
    unittest.main()


# --- Yurutucunun ivme turevi (saf matematik, ROS gerekmez) ----------------
class TestProfilTurevi(unittest.TestCase):
    """Yamuk profilin ivmesi: hizlanmada +, frenlemede -, seyirde ~0.

    px4_bridge._yurutucu_ilerlet'teki hesabin ayni formulu; oradaki kod ROS
    node'u ister, burada mantik izole dogrulaniyor.
    """

    @staticmethod
    def _ivme(v_yeni, v_eski, dt, tavan):
        a = (v_yeni - v_eski) / dt
        return max(-tavan, min(tavan, a))

    def test_hizlanma_pozitif(self):
        self.assertAlmostEqual(self._ivme(1.5, 1.2, 0.2, 1.5), 1.5)

    def test_frenleme_negatif(self):
        self.assertAlmostEqual(self._ivme(1.2, 1.5, 0.2, 1.5), -1.5)

    def test_seyirde_sifir(self):
        self.assertAlmostEqual(self._ivme(3.0, 3.0, 0.02, 1.5), 0.0)

    def test_varista_snap_kelepceleniyor(self):
        # Varista hiz tek adimda 0'a duser: -3.0/0.02 = -150 m/s^2 (absurt).
        self.assertAlmostEqual(self._ivme(0.0, 3.0, 0.02, 1.5), -1.5)

    def test_dikey_isaret_asagi_hedefte_ters(self):
        # vz = sign(dz)*hiz  ->  az = sign(dz)*d(hiz)/dt
        import math
        a = self._ivme(1.0, 0.5, 0.5, 1.0)          # +1.0 (hizlaniyor)
        self.assertAlmostEqual(math.copysign(1.0, -5.0) * a, -1.0)  # dz<0
        self.assertAlmostEqual(math.copysign(1.0, +5.0) * a, +1.0)  # dz>0
