# Copyright 2026 Yelpence
"""ModeManager altyapısı birim testleri."""

from dataclasses import dataclass
import time
import unittest

from swarm_state_machine.mode_manager.maneuver_mode import (
    compute_agent_setpoints,
    compute_hold_setpoints,
)
from swarm_state_machine.mode_manager.mode_context import ModeContext
from swarm_state_machine.mode_manager.mode_states import (
    ControlMode,
    ModeState,
)
from swarm_state_machine.mode_manager.mode_transitions import (
    evaluate_transitions,
)
from swarm_state_machine.mode_manager.movement_mode import (
    compute_formation_command,
    compute_hold_command,
)


@dataclass
class _MockAgentStatus:
    state: int = 5
    healthy: bool = True
    # B15 kalkis kapisi bu ucunu okuyor. NED: pos_z asagi POZITIF,
    # yani -pos_z = yukseklik.
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    heading_deg: float = 0.0


class TestModeContext(unittest.TestCase):
    """ModeContext durum kabı testleri."""

    def test_mode_context_initialization(self):
        """Varsayılan ModeContext değerlerini doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        self.assertEqual(ctx.state, ModeState.IDLE)
        self.assertFalse(ctx.command_valid)
        self.assertFalse(ctx.deadman_pressed)
        self.assertEqual(ctx.control_mode, ControlMode.UNKNOWN)
        self.assertEqual(ctx.agent_ids, [1, 2, 3])

    def test_mode_context_command_active(self):
        """command_active özelliğinin davranışını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.command_valid = True
        ctx.deadman_pressed = True
        ctx.last_valid_command_time = time.monotonic()
        ctx.deadman_timeout_s = 0.5

        self.assertTrue(ctx.command_active)

        ctx.deadman_pressed = False
        self.assertFalse(ctx.command_active)

        ctx.deadman_pressed = True
        ctx.command_valid = False
        self.assertFalse(ctx.command_active)

    def test_mode_context_deadman_timeout(self):
        """deadman_timed_out fonksiyonunun zaman aşımını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.deadman_timeout_s = 0.1

        self.assertTrue(ctx.deadman_timed_out())

        ctx.last_valid_command_time = time.monotonic()
        self.assertFalse(ctx.deadman_timed_out())

        time.sleep(0.15)
        self.assertTrue(ctx.deadman_timed_out())


class TestMovementMode(unittest.TestCase):
    """MovementMode hesaplama testleri."""

    def test_movement_mode_compute_formation_command(self):
        """compute_formation_command fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_x = 10.0
        ctx.centroid_y = 5.0
        ctx.centroid_z = -15.0
        ctx.formation_heading_deg = 0.0
        ctx.pitch_cmd = 1.0
        ctx.max_speed_mps = 2.0

        cmd = compute_formation_command(ctx, dt=1.0)
        self.assertAlmostEqual(cmd['center_x'], 12.0)
        self.assertAlmostEqual(cmd['center_y'], 5.0)
        self.assertAlmostEqual(cmd['center_z'], -15.0)
        self.assertEqual(cmd['heading_deg'], 0.0)

    def test_movement_mode_compute_hold_command(self):
        """compute_hold_command fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_x = 10.0
        ctx.centroid_y = 20.0
        ctx.centroid_z = -30.0
        ctx.formation_heading_deg = 45.0
        ctx.active_formation = 2

        cmd = compute_hold_command(ctx)
        self.assertEqual(cmd['center_x'], 10.0)
        self.assertEqual(cmd['center_y'], 20.0)
        self.assertEqual(cmd['center_z'], -30.0)
        self.assertEqual(cmd['heading_deg'], 45.0)
        self.assertEqual(cmd['formation_type'], 2)
        self.assertEqual(cmd['max_speed_mps'], 0.0)


class TestManeuverMode(unittest.TestCase):
    """ManeuverMode hesaplama testleri."""

    def test_maneuver_mode_compute_agent_setpoints(self):
        """compute_agent_setpoints fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])
        ctx.centroid_x = 0.0
        ctx.centroid_y = 0.0
        ctx.centroid_z = -10.0
        ctx.formation_heading_deg = 0.0
        ctx.pitch_cmd = 1.0
        ctx.max_tilt_deg = 15.0

        offsets = {1: (2.0, 0.0, 0.0), 2: (-2.0, 0.0, 0.0)}
        result = compute_agent_setpoints(
            ctx, dt=0.1, formation_offsets=offsets,
        )

        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 4)

        setpoints, new_heading, pitch_deg, roll_deg = result
        self.assertEqual(len(setpoints), 2)
        self.assertEqual(new_heading, 0.0)
        self.assertEqual(pitch_deg, 15.0)
        self.assertEqual(roll_deg, 0.0)

    def test_maneuver_asimetrik_formasyonda_merkez_sabit(self):
        """OKBAŞI-vari asimetrik ofsetlerde pitch, merkezi KAYDIRMAMALI.

        İlk yazım ortalama çıkarmıyordu ve Görev 1 tarafında aynı hata
        sahada ölçülmüştü (apply_tilt yorumu: sürü 14→10,5 m'ye kaydı).
        Kilit: eğimli z'lerin ortalaması = centroid_z (net kayma 0).
        """
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_z = -10.0
        ctx.pitch_cmd = 1.0
        ctx.max_tilt_deg = 15.0

        # Okbaşı benzeri: lider önde, iki kanat GERİDE (dx<0) — asimetrik.
        offsets = {1: (2.0, 0.0, 0.0), 2: (-2.0, -2.0, 0.0),
                   3: (-2.0, 2.0, 0.0)}
        setpoints, _h, _p, _r = compute_agent_setpoints(
            ctx, dt=0.1, formation_offsets=offsets,
        )
        ort_z = sum(sp['z'] for sp in setpoints) / len(setpoints)
        self.assertAlmostEqual(ort_z, -10.0, places=6)

    def test_maneuver_roll_isareti_gorev1_sozlesmesi(self):
        """roll>0 (sağa yatış) → SAĞDAKİ slot (oy>0) AŞAĞI (NED z artar).

        İlk yazımın işareti Görev 1'de test edilip uçmuş apply_tilt
        sözleşmesinin TERSİYDİ; birleşince kilitlendi. Kumanda-çubuk
        eşlemesinin son sözü G0 işaret-yönü testinde.
        """
        ctx = ModeContext(agent_ids=[1, 2])
        ctx.centroid_z = -10.0
        ctx.roll_cmd = 1.0
        ctx.max_tilt_deg = 15.0

        offsets = {1: (0.0, 3.0, 0.0), 2: (0.0, -3.0, 0.0)}
        setpoints, _h, _p, _r = compute_agent_setpoints(
            ctx, dt=0.1, formation_offsets=offsets,
        )
        z = {sp['agent_id']: sp['z'] for sp in setpoints}
        self.assertGreater(z[1], -10.0)   # sağdaki aşağı (down artar)
        self.assertLess(z[2], -10.0)      # soldaki yukarı

    def test_maneuver_mode_compute_hold_setpoints(self):
        """compute_hold_setpoints fonksiyonunu doğrular."""
        ctx = ModeContext(agent_ids=[1])
        ctx.centroid_x = 5.0
        ctx.centroid_y = 5.0
        ctx.centroid_z = -10.0
        ctx.formation_heading_deg = 0.0
        ctx.maneuver_pitch_deg = 10.0
        ctx.maneuver_roll_deg = 0.0

        offsets = {1: (1.0, 0.0, 0.0)}
        setpoints = compute_hold_setpoints(ctx, formation_offsets=offsets)

        self.assertEqual(len(setpoints), 1)
        self.assertEqual(setpoints[0]['agent_id'], 1)
        self.assertAlmostEqual(setpoints[0]['x'], 6.0)


class TestModeTransitions(unittest.TestCase):
    """ModeTransitions FSM geçiş testleri."""

    def test_mode_transitions_normal_flow(self):
        """IDLE->PREFLIGHT->TAKEOFF->READY->MOVEMENT akışını doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])

        # IDLE -> PREFLIGHT
        ctx.mission_state = 8
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.PREFLIGHT)
        ctx.set_state(ModeState.PREFLIGHT)

        # PREFLIGHT -> TAKEOFF
        ctx.agent_statuses = {1: _MockAgentStatus(), 2: _MockAgentStatus()}
        ctx.takeoff_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.TAKEOFF)
        ctx.set_state(ModeState.TAKEOFF)

        # TAKEOFF -> READY
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.READY)
        ctx.set_state(ModeState.READY)

        # READY -> MOVEMENT
        ctx.command_valid = True
        ctx.deadman_pressed = True
        ctx.last_valid_command_time = time.monotonic()
        ctx.control_mode = ControlMode.SWARM_MOVEMENT
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.MOVEMENT)
        ctx.set_state(ModeState.MOVEMENT)

        # MOVEMENT -> HOLD (Deadman released)
        ctx.deadman_pressed = False
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.HOLD)

    def test_mode_transitions_emergency_and_failsafe(self):
        """Acil durum ve RTL durum geçişlerini doğrular."""
        ctx = ModeContext(agent_ids=[1, 2])
        ctx.set_state(ModeState.MOVEMENT)

        # Emergency stop requested
        ctx.emergency_stop_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.EMERGENCY)

        # Pending abort
        ctx.emergency_stop_requested = False
        ctx.pending_abort = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.EMERGENCY)

        # RTL requested
        ctx.pending_abort = False
        ctx.rtl_requested = True
        next_state = evaluate_transitions(ctx)
        self.assertEqual(next_state, ModeState.RTL)


if __name__ == '__main__':
    unittest.main()


class TestKalkisKapisi(unittest.TestCase):
    """B15 — KALKIS KAPISI regresyonlari (30 Agustos 2026).

    Kapatilan kaza: mode_manager READY'de _dispatch_hold() ile
    FormationCommand yayinliyor; centroid swarm_fsm hic centroid
    hesaplamadiysa (0,0,0)'da kaliyor. B3'un test_hazir_atla'si FSM'i
    yerde READY'ye atlatinca sonuc "sürü NED ORIGIN'e gider" oluyordu.
    """

    @staticmethod
    def _ctx(**kw):
        c = ModeContext(agent_ids=[1, 2, 3], **kw)
        c.kalkis_esik_m = 2.0
        return c

    @staticmethod
    def _kadro(yukseklikler, x=30.0, y=15.0):
        """Verilen yuksekliklerde (metre, YUKARI +) sahte kadro uretir."""
        return {
            i + 1: _MockAgentStatus(pos_x=x, pos_y=y, pos_z=-h)
            for i, h in enumerate(yukseklikler)
        }

    def test_kapi_yerde_KAPALI(self):
        """Uc ucak da yerdeyken kapi ACILMAZ."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())
        self.assertFalse(ctx.kalkis_tamam)

    def test_kapi_ORIGIN_KAZASI_regresyonu(self):
        """🔴 Asil kaza: yerde, centroid (0,0,0), test_hazir_atla ACIK.

        Kapi kapali kaldigi surece hicbir tarif yayinlanmaz; yayinlansaydi
        merkez (0,0,0) olurdu ve sürü NED origin'e giderdi.
        """
        ctx = self._ctx()
        ctx.test_hazir_atla = True
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0], x=30.0, y=15.0)
        self.assertEqual((ctx.centroid_x, ctx.centroid_y, ctx.centroid_z),
                         (0.0, 0.0, 0.0))
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_kapi_eksik_ajanla_ACILMAZ(self):
        """Bir ucagin durumu hic gelmediyse kapi ACILMAZ."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            1: _MockAgentStatus(pos_z=-8.0),
            2: _MockAgentStatus(pos_z=-8.0),
        }
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_kapi_biri_yerdeyken_ACILMAZ(self):
        """Ikisi havada biri yerdeyse kapi ACILMAZ (min alinir)."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([8.0, 8.0, 0.5])
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_kapi_esikte_ACILMAZ_ustunde_ACILIR(self):
        """Esik kesin: altinda kapali, uzerinde acik."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([1.9, 1.9, 1.9])
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

        ctx2 = self._ctx()
        ctx2.agent_statuses = self._kadro([2.1, 2.1, 2.1])
        self.assertTrue(ctx2.kalkis_kapisi_degerlendir())

    def test_kapi_acilinca_centroid_UCAKLARDAN_tohumlanir(self):
        """Kapi acilirken centroid SwarmState'ten degil ucaklardan gelir."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            1: _MockAgentStatus(pos_x=10.0, pos_y=0.0, pos_z=-8.0),
            2: _MockAgentStatus(pos_x=20.0, pos_y=6.0, pos_z=-8.0),
            3: _MockAgentStatus(pos_x=30.0, pos_y=-6.0, pos_z=-8.0),
        }
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        self.assertAlmostEqual(ctx.centroid_x, 20.0, places=6)
        self.assertAlmostEqual(ctx.centroid_y, 0.0, places=6)
        self.assertAlmostEqual(ctx.centroid_z, -8.0, places=6)

    def test_kapi_MANDAL_geri_kapanmaz(self):
        """Kapi bir kez acilinca KAPANMAZ — havada yayin kesilmemeli."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([8.0, 8.0, 8.0])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())

        # bir ucagin durumu tamamen kayboldu (mesh bayatlamasi)
        ctx.agent_statuses = {}
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        self.assertTrue(ctx.kalkis_tamam)

    def test_kapi_acildiktan_sonra_centroid_YENIDEN_tohumlanmaz(self):
        """Mandal acikken centroid entegratordur; ucaklar onu EZMEZ."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([8.0, 8.0, 8.0], x=10.0, y=10.0)
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())

        ctx.centroid_x = 99.0            # hareket modu entegratoru ilerletti
        ctx.agent_statuses = self._kadro([8.0, 8.0, 8.0], x=0.0, y=0.0)
        ctx.kalkis_kapisi_degerlendir()
        self.assertEqual(ctx.centroid_x, 99.0)


class TestB3TestHazirAtla(unittest.TestCase):
    """B3 — test_hazir_atla, B15 kapisini BAYPAS EDEMEZ."""

    @staticmethod
    def _ctx():
        c = ModeContext(agent_ids=[1, 2, 3])
        c.kalkis_esik_m = 2.0
        return c

    def test_idle_preflight_mission_fsm_OLMADAN(self):
        """mission_fsm kapali (mission_state != 8) ama test_hazir_atla acik."""
        ctx = self._ctx()
        ctx.state = ModeState.IDLE
        self.assertIsNone(evaluate_transitions(ctx))   # bayrak yokken takili

        ctx.test_hazir_atla = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.PREFLIGHT)

    def test_takeoff_READY_ANCAK_kapi_acikken(self):
        """🔴 En kritik kilit: test_hazir_atla tek basina READY VERMEZ."""
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.test_hazir_atla = True
        ctx.agent_statuses = {
            1: _MockAgentStatus(state=3),   # ARMED — IN_SWARM degil
            2: _MockAgentStatus(state=3),
            3: _MockAgentStatus(state=3),
        }
        ctx.kalkis_tamam = False
        self.assertIsNone(evaluate_transitions(ctx))

        ctx.kalkis_tamam = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.READY)

    def test_in_swarm_yolu_bayraksiz_da_calisir(self):
        """Gercek akis (IN_SWARM) test bayragi olmadan da READY verir."""
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.agent_statuses = {
            1: _MockAgentStatus(state=5),
            2: _MockAgentStatus(state=5),
            3: _MockAgentStatus(state=5),
        }
        self.assertEqual(evaluate_transitions(ctx), ModeState.READY)

    def test_kapi_acilinca_ofsetler_de_OLCULEN_geometriden(self):
        """Pilot ilk is MANEVRA'ya gecerse gomulu ucgen egilmemeli."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            1: _MockAgentStatus(pos_x=10.0, pos_y=0.0, pos_z=-8.0),
            2: _MockAgentStatus(pos_x=20.0, pos_y=6.0, pos_z=-8.0),
            3: _MockAgentStatus(pos_x=30.0, pos_y=-6.0, pos_z=-8.0),
        }
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())

        ofs = ctx.olculen_ofsetler()
        self.assertEqual(set(ofs), {1, 2, 3})
        self.assertAlmostEqual(ofs[1][0], -10.0, places=6)   # 10 - 20
        self.assertAlmostEqual(ofs[2][1], 6.0, places=6)
        self.assertAlmostEqual(ofs[3][0], 10.0, places=6)    # 30 - 20
        # ofsetlerin ortalamasi SIFIR olmali (centroid tanimi)
        self.assertAlmostEqual(sum(o[0] for o in ofs.values()), 0.0, places=6)
        self.assertAlmostEqual(sum(o[1] for o in ofs.values()), 0.0, places=6)
        self.assertTrue(all(o[2] == 0.0 for o in ofs.values()))


class TestHoldVeRtlKapilari(unittest.TestCase):
    """G2-K6 (HOLD otomatik inisi yok) + B8 (land RTL'i KESEBILIR)."""

    @staticmethod
    def _ctx(state):
        c = ModeContext(agent_ids=[1, 2, 3])
        c.state = state
        return c

    def test_hold_komutsuz_INMEZ(self):
        """G2-K6: komut kesilse de HOLD'da kalir, kendiliginden INMEZ."""
        ctx = self._ctx(ModeState.HOLD)
        ctx.state_entry_time = time.monotonic() - 600.0   # 10 dakika
        self.assertFalse(ctx.command_active)
        self.assertIsNone(evaluate_transitions(ctx))
        self.assertEqual(ctx.state, ModeState.HOLD)

    def test_hold_komut_gelince_moda_doner(self):
        """Komut geri gelince HOLD kilitlenmis olmamali."""
        ctx = self._ctx(ModeState.HOLD)
        ctx.command_valid = True
        ctx.deadman_pressed = True
        ctx.last_valid_command_time = time.monotonic()
        ctx.control_mode = ControlMode.SWARM_MOVEMENT
        self.assertEqual(evaluate_transitions(ctx), ModeState.MOVEMENT)

    def test_land_RTL_i_KESEBILIR(self):
        """🔴 B8 kilidi: land kapisina RTL EKLENMEMELI.

        CLAUDE.md "iptal her zaman land" diyor; pilotun SwD ile verdigi
        inis komutu RTL'i kesebilmek ZORUNDA. B8'in dogru cozumu bu kapiyi
        daraltmak degil, dugumun kendi olayina tepki vermesini durdurmakti.
        """
        ctx = self._ctx(ModeState.RTL)
        ctx.land_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.LANDING)

    def test_rtl_kendi_basina_LANDING_e_dusmez(self):
        """B8: istek olmadan RTL kendiliginden LANDING'e gecmez."""
        ctx = self._ctx(ModeState.RTL)
        self.assertIsNone(evaluate_transitions(ctx))


class TestB17HeadingTohumlama(unittest.TestCase):
    """B17 — kapi acilirken heading OLCULEN yaw'dan gelir."""

    @staticmethod
    def _ctx():
        c = ModeContext(agent_ids=[1, 2, 3])
        c.kalkis_esik_m = 2.0
        return c

    @staticmethod
    def _kadro(headingler):
        return {i + 1: _MockAgentStatus(pos_z=-8.0, heading_deg=h)
                for i, h in enumerate(headingler)}

    def test_heading_olculenden_tohumlanir(self):
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([90.0, 90.0, 90.0])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        self.assertAlmostEqual(ctx.formation_heading_deg, 90.0, places=4)
        self.assertGreater(ctx.kalkis_heading_tutarlilik, 0.99)

    def test_KUZEY_sarmasi_guneye_donmez(self):
        """🔴 B17'nin ta kendisi: 359/0/1 -> 0, 120 DEGIL."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([359.0, 0.0, 1.0])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        h = ctx.formation_heading_deg
        self.assertLess(min(abs(h), abs(h - 360.0)), 1.0)

    def test_kapi_kapaliyken_heading_YAZILMAZ(self):
        """Yerdeyken tohumlama YOK — kapi hala kapali."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            i + 1: _MockAgentStatus(pos_z=0.0, heading_deg=90.0)
            for i in range(3)
        }
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())
        self.assertEqual(ctx.formation_heading_deg, 0.0)

    def test_daginik_yaw_TUTARLILIK_dusuk(self):
        """Ucaklar farkli yone bakiyorsa dugum uyarabilsin."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([0.0, 120.0, 240.0])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        self.assertLess(ctx.kalkis_heading_tutarlilik, 0.9)

    def test_heading_kapi_acildiktan_sonra_ENTEGRATOR(self):
        """Mandal acikken yeni yaw okumalari heading'i EZMEZ."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([90.0, 90.0, 90.0])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        ctx.formation_heading_deg = 135.0          # pilot yaw verdi
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        ctx.kalkis_kapisi_degerlendir()
        self.assertEqual(ctx.formation_heading_deg, 135.0)
