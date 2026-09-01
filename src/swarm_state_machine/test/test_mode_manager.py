# Copyright 2026 Yelpence
"""ModeManager altyapısı birim testleri."""

from dataclasses import dataclass
import time
import unittest

from swarm_state_machine.mode_manager.maneuver_mode import (
    compute_agent_setpoints,
    compute_hold_setpoints,
)
from swarm_state_machine.mode_manager import canli_param
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
    armed: bool = True      # kapi testlerinin cogu ARMLI kadro varsayar


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
        """compute_formation_command fonksiyonunu doğrular.

        🔴 SOZLESME 31 AGUSTOS 2026'DA DEGISTI (B6). Onceden bu test
        `center_x == 12.0` bekliyordu, yani "1 sn'de tam hizda 2 m" —
        cubuk hiza ANINDA cevriliyordu. Artik IVME RAMPASI var:
        1 sn'de hiz ancak a*t = 1.3 m/s'e ciktigi icin yol 1.3 m.
        Testin bu hali rampanin VARLIGINI kilitliyor; ayrintili
        davranis `test_ivme_rampasi.py`de.
        """
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.centroid_x = 10.0
        ctx.centroid_y = 5.0
        ctx.centroid_z = -15.0
        ctx.formation_heading_deg = 0.0
        ctx.pitch_cmd = 1.0
        ctx.max_speed_mps = 2.0
        ctx.max_accel_mps2 = 1.3

        cmd = compute_formation_command(ctx, dt=1.0)
        # Ivme sinirli: 1 sn sonunda hiz 1.3 m/s, yol 1.3 m.
        self.assertAlmostEqual(cmd['center_x'], 11.3, places=6)
        self.assertLess(cmd['center_x'], 12.0,
                        'rampa yok — cubuk aninda tam hiza cikiyor')
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


class TestKapiArmSarti(unittest.TestCase):
    """🔴 30 Ağustos açık alan ölçümü: esik ORIGIN'e goreli, yere degil.

    Ucaklar YERDE dururken olculen yukseklikler: ylp00 +1,7 · ylp01 -0,1 ·
    ylp02 0,0 m. Yani yerlesim tek basina 2,0 m esigin %85'ini yiyordu.
    Origin'den 2,5 m yuksege konan bir ucakta kapi YERDE ACILIRDI.
    """

    @staticmethod
    def _ctx():
        c = ModeContext(agent_ids=[1, 2, 3])
        c.kalkis_esik_m = 2.0
        return c

    @staticmethod
    def _kadro(yukseklikler, armed=True):
        return {i + 1: _MockAgentStatus(pos_z=-h, armed=armed)
                for i, h in enumerate(yukseklikler)}

    def test_DISARM_ucaklar_esigin_USTUNDE_olsa_bile_KAPI_ACILMAZ(self):
        """🔴 Asil kaza: kotu origin ofseti + disarm = yerde acilan kapi."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([3.0, 3.0, 3.0], armed=False)
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())
        self.assertFalse(ctx.kalkis_tamam)

    def test_ARMLI_ve_esigin_ustunde_ACILIR(self):
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([3.0, 3.0, 3.0], armed=True)
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())

    def test_TEK_disarm_ucak_bile_KAPATIR(self):
        ctx = self._ctx()
        kadro = self._kadro([8.0, 8.0, 8.0], armed=True)
        kadro[2].armed = False
        ctx.agent_statuses = kadro
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_armli_ama_ALCAK_yine_kapali(self):
        """Iki sart AYRI: arm tek basina yetmez."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([0.1, 0.1, 0.1], armed=True)
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_mandal_acildiktan_sonra_disarm_KAPATMAZ(self):
        """Kapi MANDAL: acildiktan sonra disarm gorulse bile kapanmaz."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([8.0, 8.0, 8.0], armed=True)
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        ctx.agent_statuses = self._kadro([8.0, 8.0, 8.0], armed=False)
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())


class TestGecersizPaketteIptal(unittest.TestCase):
    """🔴 command_valid=False iken IPTAL gecer, KALKIS gecmez.

    B18 gaz kapisi command_valid'i false yapan yeni bir sebep. Eskiden kod
    bu durumda TUM aksiyonlari dusuruyordu, yani "SwA acik + gaz ortada
    degil" halinde pilot LAND VEREMIYORDU. CLAUDE.md: iptal her zaman land.
    """

    def test_land_kapisini_ASAR(self):
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.state = ModeState.MOVEMENT
        ctx.land_requested = True          # _on_control_command'in yapacagi
        self.assertEqual(evaluate_transitions(ctx), ModeState.LANDING)

    def test_acil_durum_kapisini_ASAR(self):
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.state = ModeState.MOVEMENT
        ctx.emergency_stop_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.EMERGENCY)

    def test_kalkis_gecersiz_pakette_ISTENMEZ(self):
        """takeoff_requested kurulmazsa PREFLIGHT'ta kalinir.

        mission_state=8: G2-K10'un UCUNCU kapisi (gorev YKI'den baslatilmis)
        30 Agustos'ta eklendi; bu test paket gecerliligini olcuyor, yetkiyi
        degil — o kapi TestB2KumandadanKalkis'ta ayrica kilitli.
        """
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.state = ModeState.PREFLIGHT
        ctx.mission_state = 8
        ctx.agent_statuses = {
            i: _MockAgentStatus(state=3, healthy=True) for i in (1, 2, 3)
        }
        ctx.takeoff_requested = False
        self.assertIsNone(evaluate_transitions(ctx))
        ctx.takeoff_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.TAKEOFF)


class TestInisHerDurumdanUlasilir(unittest.TestCase):
    """🔴 30 Agustos 2026: iptal yolu DURUMA BAGLI OLAMAZ.

    Olayda ucaklar ARMED'daydi ve agent_fsm'in LANDING istegini yalniz
    IN_SWARM / RETURN_HOME / FAILSAFE durumlarindan kabul ettigi olculdu
    (agent_transitions.py:207/316/387) — istek sessizce kayboldu ve pilot
    inis veremedi. mode_manager tarafinda ayni delik OLMAMALI.
    """

    # IDLE/PREFLIGHT ucakta zaten yerde ve DISARM: inis anlamsiz, kapi
    # bilerek disliyor. COMPLETED terminal. Gerisi HAVADA olabilir.
    HAVADA_OLABILEN = (
        ModeState.TAKEOFF,
        ModeState.READY,
        ModeState.MOVEMENT,
        ModeState.MANEUVER,
        ModeState.HOLD,
    )

    def test_land_her_havada_durumdan_LANDING_verir(self):
        for durum in self.HAVADA_OLABILEN:
            with self.subTest(durum=durum.name):
                ctx = ModeContext(agent_ids=[1, 2, 3])
                ctx.state = durum
                ctx.land_requested = True
                self.assertEqual(
                    evaluate_transitions(ctx), ModeState.LANDING
                )

    def test_acil_her_havada_durumdan_EMERGENCY_verir(self):
        for durum in self.HAVADA_OLABILEN:
            with self.subTest(durum=durum.name):
                ctx = ModeContext(agent_ids=[1, 2, 3])
                ctx.state = durum
                ctx.emergency_stop_requested = True
                self.assertEqual(
                    evaluate_transitions(ctx), ModeState.EMERGENCY
                )

    def test_TAKEOFF_sirasinda_inis_verilebilir(self):
        """Olayin birebir hali: kalkis basladi, pilot vazgecti."""
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.state = ModeState.TAKEOFF
        ctx.land_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.LANDING)

    def test_LANDING_kendi_uzerine_gecis_yapmaz(self):
        """Mandal basili kaldikca her tick yeniden LANDING'e girilmemeli.

        Girilseydi _on_state_entry her tick calisir, 1 Hz tekrar yerine
        50 Hz komut yagardi.
        """
        ctx = ModeContext(agent_ids=[1, 2, 3])
        ctx.state = ModeState.LANDING
        ctx.land_requested = True
        self.assertNotEqual(evaluate_transitions(ctx), ModeState.LANDING)


class TestB2KumandadanKalkis(unittest.TestCase):
    """B2 / madde 25 — kumandadan kalkis ve G2-K10 ARM yetkisi.

    30 Agustos saha olayinin koku arm'in ORTUK gerceklesmesiydi: SwD'ye
    dokunmak EVENT_MISSION_STARTED yayinliyor, agent_fsm onu ARM'a
    ceviriyordu ve UC UCAK birden armlaniyordu (gorev2.md §7.6). G2-K10
    secenek (a) arm'i ACIK ve UC KAPILI hale getirdi; bu testler o
    kapilarin acilmadigini kilitliyor.
    """

    @staticmethod
    def _ctx(**kw):
        c = ModeContext(agent_ids=[1, 2, 3], **kw)
        c.kalkis_esik_m = 2.0
        c.kalkis_irtifa_m = 8.0
        return c

    @staticmethod
    def _kadro(yukseklikler, state=3, zemin=0.0):
        """Verilen yuksekliklerde (YUKARI +) kadro. state=3 -> ARMED."""
        return {
            i + 1: _MockAgentStatus(state=state, pos_z=zemin - h)
            for i, h in enumerate(yukseklikler)
        }

    # --- UCUNCU KAPI: gorev YKI'den baslatilmis olacak ---------------------

    def test_YETKI_test_bayragiyla_ACILMAZ(self):
        """🔴 En kritik kilit: test_hazir_atla ARM YETKISI VERMEZ.

        Verseydi 30 Agustos'un aynisini "test" adi altinda tekrarlardik.
        """
        ctx = self._ctx()
        ctx.test_hazir_atla = True
        self.assertFalse(ctx.kalkis_yetkisi_var())

        ctx.mission_state = 8
        self.assertTrue(ctx.kalkis_yetkisi_var())

    def test_PREFLIGHT_yetkisiz_SwD_TAKEOFF_a_GECIRMEZ(self):
        """Bugunku ucaklarin hali: /ws/mod_test var, mission_fsm YOK."""
        ctx = self._ctx()
        ctx.test_hazir_atla = True
        ctx.state = ModeState.PREFLIGHT
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        ctx.takeoff_requested = True
        self.assertIsNone(evaluate_transitions(ctx))

    def test_PREFLIGHT_yetkiliyken_TAKEOFF(self):
        """Madde 27+28 bitince: gorev baslatilmis, SwD kalkis verir."""
        ctx = self._ctx()
        ctx.state = ModeState.PREFLIGHT
        ctx.mission_state = 8
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        ctx.takeoff_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.TAKEOFF)

    def test_saglıksiz_kadro_yetkili_olsa_bile_KALKMAZ(self):
        """all_agents_healthy kapisi yerinde duruyor."""
        ctx = self._ctx()
        ctx.state = ModeState.PREFLIGHT
        ctx.mission_state = 8
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        ctx.agent_statuses[2].healthy = False
        ctx.takeoff_requested = True
        self.assertIsNone(evaluate_transitions(ctx))

    # --- ZEMIN TOHUMLAMA: yukseklik origin'e gore OLCULMEZ -----------------

    def test_zemin_HER_UCAGIN_KENDI_z_sinden_tohumlanir(self):
        """§7.5: yerde ylp00 +1,7 · ylp01 -0,1 · ylp02 0,0 m okunuyordu."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            1: _MockAgentStatus(pos_z=-1.7),
            2: _MockAgentStatus(pos_z=0.1),
            3: _MockAgentStatus(pos_z=0.0),
        }
        ctx.kalkis_zeminini_tohumla()
        self.assertEqual(set(ctx.kalkis_zemin_z), {1, 2, 3})
        self.assertAlmostEqual(ctx.kalkis_zemin_z[1], -1.7, places=6)

    def test_ORIGIN_SAPMASI_olcutu_bozmaz(self):
        """Uc ucak da KENDI zemininden 6,4 m tirmandi -> ulasildi."""
        ctx = self._ctx()
        ctx.agent_statuses = {
            1: _MockAgentStatus(pos_z=-1.7),
            2: _MockAgentStatus(pos_z=0.1),
            3: _MockAgentStatus(pos_z=0.0),
        }
        ctx.kalkis_zeminini_tohumla()
        self.assertFalse(ctx.kalkis_irtifasina_ulasildi())

        for aid, zemin in ((1, -1.7), (2, 0.1), (3, 0.0)):
            ctx.agent_statuses[aid].pos_z = zemin - 6.5   # olcut 0.8x8.0=6.4
        self.assertTrue(ctx.kalkis_irtifasina_ulasildi())

    def test_GERIDE_KALAN_ucak_olcutu_DUSURUR(self):
        """Biri geride kaldiysa TAKEOFF bitmez — suru bolunmez."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([0.0, 0.0, 0.0])
        ctx.kalkis_zeminini_tohumla()
        for aid, h in ((1, 7.0), (2, 7.0), (3, 3.0)):
            ctx.agent_statuses[aid].pos_z = -h
        self.assertFalse(ctx.kalkis_irtifasina_ulasildi())

    def test_tohumsuz_olcut_ASLA_dogru_donmez(self):
        """Kalkis komutu verilmediyse "ulasildi" diyemeyiz."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([20.0, 20.0, 20.0])
        self.assertFalse(ctx.kalkis_irtifasina_ulasildi())

    # --- TAKEOFF BITIS OLCUTU: 2 m kapisi DEGIL, hedef irtifa -------------

    def test_KAPI_ACILINCA_READY_VERMEZ_tirmanis_surer(self):
        """🔴 REGRESYON: suru 2 m'de READY olsaydi TIRMANIS ORADA DURURDU.

        _dispatch_hold() kapinin acildigi andaki centroid_z'yi (2 m) hedef
        gosteren tarif yayinlar; formation_node onu tutar ve ucaklar 8 m
        yerine 2 m'de kalir. Hicbir yerde hata gorunmez.
        """
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.test_hazir_atla = True          # bugunku ucaklarin hali
        ctx.kalkis_komutu_verildi = True
        ctx.kalkis_tamam = True             # 2 m kapisi ACIK
        ctx.agent_statuses = self._kadro([2.5, 2.5, 2.5])
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        self.assertIsNone(evaluate_transitions(ctx))

    def test_hedefe_ulasinca_READY(self):
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.kalkis_komutu_verildi = True
        ctx.agent_statuses = self._kadro([6.5, 6.5, 6.5])
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        self.assertEqual(evaluate_transitions(ctx), ModeState.READY)

    def test_tirmanis_takilirsa_90_sn_sonra_EMERGENCY(self):
        """Bes dakika armli beklemek yerine inise gecer."""
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.kalkis_komutu_verildi = True
        ctx.agent_statuses = self._kadro([1.0, 1.0, 1.0])
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        ctx.state_entry_time = time.monotonic() - 91.0
        self.assertEqual(evaluate_transitions(ctx), ModeState.EMERGENCY)

    def test_IN_SWARM_yolu_hala_ONDE(self):
        """Gercek ajan FSM'i IN_SWARM diyorsa olcut aranmaz."""
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.kalkis_komutu_verildi = True
        ctx.agent_statuses = self._kadro([6.5, 6.5, 6.5], state=5)
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        self.assertEqual(evaluate_transitions(ctx), ModeState.READY)

    def test_kalkis_sirasinda_INIS_hala_ustunde(self):
        """Iptal yolu her seyin ustunde kalmali (madde 24)."""
        ctx = self._ctx()
        ctx.state = ModeState.TAKEOFF
        ctx.kalkis_komutu_verildi = True
        ctx.agent_statuses = self._kadro([1.0, 1.0, 1.0])
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        ctx.land_requested = True
        self.assertEqual(evaluate_transitions(ctx), ModeState.LANDING)

    # --- READY'de centroid TAZELENIR (yoksa suru 2 m'ye geri dalar) -------

    def test_READY_oncesi_centroid_KAPIDA_kalirsa_dalis_olurdu(self):
        """🔴 REGRESYON: kapi 2 m'de tohumluyor, READY 6,4 m'de geliyor."""
        ctx = self._ctx()
        ctx.agent_statuses = self._kadro([2.5, 2.5, 2.5])
        self.assertTrue(ctx.kalkis_kapisi_degerlendir())
        self.assertAlmostEqual(ctx.centroid_z, -2.5, places=6)

        # Tirmanis surdu; ucaklar artik 7 m'de ve 3 m yana suruklendi.
        for aid in (1, 2, 3):
            ctx.agent_statuses[aid].pos_z = -7.0
            ctx.agent_statuses[aid].pos_x = 3.0
        self.assertTrue(ctx.konumdan_tohumla())
        self.assertAlmostEqual(ctx.centroid_z, -7.0, places=6)
        self.assertAlmostEqual(ctx.centroid_x, 3.0, places=6)

    def test_tohumlama_eksik_ajanla_YAZMAZ(self):
        """Eksik durum varsa bayat centroid EZILMEZ, False doner."""
        ctx = self._ctx()
        ctx.centroid_z = -7.0
        ctx.agent_statuses = {1: _MockAgentStatus(pos_z=0.0)}
        self.assertFalse(ctx.konumdan_tohumla())
        self.assertAlmostEqual(ctx.centroid_z, -7.0, places=6)


class TestB19CompletedCikisi(unittest.TestCase):
    """B19 — COMPLETED artik cikmaz-sokak DEGIL (30 Agustos 2026).

    Gorev basina UC HAKKIMIZ var; eskiden ikinci kalkis icin konteyner
    yeniden baslatmak gerekiyordu.
    """

    @staticmethod
    def _ctx(armli=False):
        c = ModeContext(agent_ids=[1, 2, 3])
        c.state = ModeState.COMPLETED
        c.agent_statuses = {
            i: _MockAgentStatus(state=3, armed=armli) for i in (1, 2, 3)
        }
        return c

    def test_disarm_ve_mandal_dusukse_IDLE(self):
        ctx = self._ctx(armli=False)
        self.assertEqual(evaluate_transitions(ctx), ModeState.IDLE)

    def test_SwD_hala_inis_konumundaysa_BEKLER(self):
        """Mandal basiliyken cikmak "pilot inis istiyor"u yok saymak olurdu."""
        ctx = self._ctx(armli=False)
        ctx.land_requested = True
        self.assertIsNone(evaluate_transitions(ctx))

    def test_BIR_ucak_bile_ARMLIYKEN_cikmaz(self):
        """Havada ucak varken defteri temizlemek ikinci kalkisi acardi."""
        ctx = self._ctx(armli=False)
        ctx.agent_statuses[2].armed = True
        self.assertIsNone(evaluate_transitions(ctx))

    def test_eksik_ajan_durumu_varken_cikmaz(self):
        ctx = self._ctx(armli=False)
        del ctx.agent_statuses[3]
        self.assertIsNone(evaluate_transitions(ctx))

    def test_COMPLETED_hala_acil_RTL_inis_KABUL_ETMEZ(self):
        """Erken donus korunuyor: EMERGENCY'de takilip kalmayalim."""
        for alan in ('emergency_stop_requested', 'rtl_requested',
                     'pending_abort'):
            with self.subTest(alan=alan):
                ctx = self._ctx(armli=True)      # cikis kosulu SAGLANMIYOR
                setattr(ctx, alan, True)
                self.assertIsNone(evaluate_transitions(ctx))

    def test_defter_sifirlaninca_kapi_KAPANIR(self):
        """🔴 En kritik: kalkis_tamam MANDAL — temizlenmezse yerde ACIK."""
        ctx = self._ctx(armli=False)
        ctx.kalkis_tamam = True
        ctx.kalkis_komutu_verildi = True
        ctx.kalkis_zemin_z = {1: 0.0, 2: 0.0, 3: 0.0}
        ctx.maneuver_pitch_deg = 7.0

        ctx.ucus_durumunu_sifirla()

        self.assertFalse(ctx.kalkis_tamam)
        self.assertFalse(ctx.kalkis_komutu_verildi)
        self.assertEqual(ctx.kalkis_zemin_z, {})
        self.assertEqual(ctx.maneuver_pitch_deg, 0.0)
        self.assertEqual(ctx.maneuver_roll_deg, 0.0)

    def test_ikinci_denemede_kapi_yerde_ACILMAZ(self):
        """Sifirlama sonrasi kapi gercekten bastan degerlendiriliyor mu."""
        ctx = self._ctx(armli=False)
        ctx.kalkis_tamam = True
        ctx.ucus_durumunu_sifirla()
        # Ucaklar yerde ve DISARM -> kapi acilmamali
        self.assertFalse(ctx.kalkis_kapisi_degerlendir())

    def test_IDLE_e_donunce_gorev_hala_acikken_PREFLIGHT(self):
        """Ikinci deneme icin YKI'ye tekrar basmak gerekmiyor."""
        ctx = self._ctx(armli=False)
        ctx.mission_state = 8
        self.assertEqual(evaluate_transitions(ctx), ModeState.IDLE)
        ctx.set_state(ModeState.IDLE)
        self.assertEqual(evaluate_transitions(ctx), ModeState.PREFLIGHT)

    def test_SwD_yukari_kenarindaki_kalkis_istegi_YUTULUR(self):
        """Mandali dusuren hareket AYNI ZAMANDA kalkis kenari uretir.

        Suru kendiliginden kalkmamali: set_state istegi temizler.
        """
        ctx = self._ctx(armli=False)
        ctx.mission_state = 8
        ctx.takeoff_requested = True        # SwD yukari kenari
        self.assertEqual(evaluate_transitions(ctx), ModeState.IDLE)
        ctx.set_state(ModeState.IDLE)
        self.assertFalse(ctx.takeoff_requested)
        self.assertEqual(evaluate_transitions(ctx), ModeState.PREFLIGHT)
        ctx.set_state(ModeState.PREFLIGHT)
        self.assertIsNone(evaluate_transitions(ctx))   # TAKEOFF'a GECMEZ


class TestCanliParamKapisi(unittest.TestCase):
    """G2-K9 / madde 29 — canlı ayar kapısı (saf modül).

    Kapılar (kalkis_esik_m, test_hazir_atla) ve kimlik (agent_id) bilerek
    dışarıda: uçuş sırasında değiştirilmeleri B15'i ya da G2-K10'un üçüncü
    kapısını canlı canlı devre dışı bırakmak olurdu.
    """

    def test_izinli_alanlar_gecer(self):
        self.assertEqual(
            canli_param.dogrula(
                'default_spacing_m', 5.0, canli_param.MODE_MANAGER_CANLI),
            5.0,
        )
        self.assertEqual(
            canli_param.dogrula(
                'kalkis_irtifa_m', 15, canli_param.MODE_MANAGER_CANLI),
            15.0,
        )
        self.assertEqual(
            canli_param.dogrula(
                'default_spacing_m', 7, canli_param.JOYSTICK_CANLI),
            7.0,
        )

    def test_KAPILAR_ve_KIMLIK_reddedilir(self):
        """🔴 En kritik kilit: tek bir param set güvenliği bozamamalı."""
        for yasak in ('kalkis_esik_m', 'test_hazir_atla', 'agent_id',
                      'agent_ids', 'tick_hz', 'deadman_threshold',
                      'gaz_merkez_pay', 'sitl_mode'):
            with self.subTest(param=yasak):
                with self.assertRaises(canli_param.ParamRed):
                    canli_param.dogrula(
                        yasak, 1.0, canli_param.MODE_MANAGER_CANLI)

    def test_joystick_kumesi_DAR(self):
        """Kalkış irtifası joystick'te YOK — orada karşılığı da yok."""
        with self.assertRaises(canli_param.ParamRed):
            canli_param.dogrula(
                'kalkis_irtifa_m', 15.0, canli_param.JOYSTICK_CANLI)

    def test_sifir_ve_negatif_reddedilir(self):
        """aralik=0 compute_slot_offsets'i ValueError'a sokardı (B10 sınıfı)."""
        for deger in (0.0, -1.0, 0):
            with self.subTest(deger=deger):
                with self.assertRaises(canli_param.ParamRed):
                    canli_param.dogrula(
                        'default_spacing_m', deger,
                        canli_param.MODE_MANAGER_CANLI)

    def test_sayi_olmayan_reddedilir(self):
        for deger in ('yedi', None, [7.0]):
            with self.subTest(deger=deger):
                with self.assertRaises(canli_param.ParamRed):
                    canli_param.dogrula(
                        'default_spacing_m', deger,
                        canli_param.MODE_MANAGER_CANLI)

    def test_BOOL_sayi_sayilmaz(self):
        """bool int'in alt sınıfı — float(True)=1.0 sessizce geçerdi."""
        with self.assertRaises(canli_param.ParamRed):
            canli_param.dogrula(
                'default_spacing_m', True, canli_param.MODE_MANAGER_CANLI)

    def test_red_sebebi_OPERATORE_ANLAMLI(self):
        """Sebep doğrudan `ros2 param set` çıktısında görünüyor."""
        with self.assertRaises(canli_param.ParamRed) as cm:
            canli_param.dogrula(
                'kalkis_esik_m', 3.0, canli_param.MODE_MANAGER_CANLI)
        mesaj = str(cm.exception)
        self.assertIn('kalkis_esik_m', mesaj)
        self.assertIn('default_spacing_m', mesaj)   # ne YAPILABILIR
