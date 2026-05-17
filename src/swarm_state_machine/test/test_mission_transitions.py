"""evaluate_transitions ve QR yardımcı fonksiyonları için birim testleri."""

import time
import unittest
from types import SimpleNamespace

from swarm_state_machine.mission_fsm.mission_context import MissionContext
from swarm_state_machine.mission_fsm.mission_states import (
    MissionState,
    MissionType,
    QrTaskStep,
)
from swarm_state_machine.mission_fsm.mission_transitions import (
    evaluate_transitions,
    find_first_qr_step,
    find_next_qr_step,
)

# TriggerMission komut sabitleri (srv import etmeden)
_START = 1
_ABORT = 2
_PAUSE = 3
_RESUME = 4
_RTL = 5
_LAND = 6


# =================================================================
# TEST YARDICILARI
# =================================================================

def _status(
    state: int = 5,
    healthy: bool = True,
    origin_synced: bool = True,
    home_set: bool = True,
    gps_fix_type: int = 3,
    gps_hdop: float = 0.9,
) -> SimpleNamespace:
    """Sahte AgentStatus nesnesi döner.

    Args:
        state: AgentStatus.STATE_* değeri (varsayılan IN_SWARM=5).
        healthy: Ajan sağlık durumu.
        origin_synced: NED origin senkronize mi.
        home_set: RTL hedefi set mi.
        gps_fix_type: GPS fix tipi.
        gps_hdop: HDOP değeri.

    Returns:
        Gerekli alanları taşıyan SimpleNamespace.
    """
    return SimpleNamespace(
        state=state,
        healthy=healthy,
        origin_synced=origin_synced,
        home_set=home_set,
        gps_fix_type=gps_fix_type,
        gps_hdop=gps_hdop,
        pos_z=-15.0,
    )


def _qr(
    qr_seq: int = 1,
    formation_active: bool = False,
    altitude_active: bool = False,
    maneuver_active: bool = False,
    detach_active: bool = False,
    complete_mission: bool = False,
    wait_s: float = 0.0,
    next_qr: int = 0,
) -> SimpleNamespace:
    """Sahte QRMissionData nesnesi döner.

    Args:
        qr_seq: QR sıra numarası.
        formation_active: Formasyon değişikliği aktif mi.
        altitude_active: İrtifa değişikliği aktif mi.
        maneuver_active: Manevra aktif mi.
        detach_active: Ajan ayrımı aktif mi.
        complete_mission: Görevi tamamla bayrağı.
        wait_s: QR noktasında bekleme süresi.
        next_qr: Sonraki QR ID'si (0 = son QR).

    Returns:
        Gerekli alanları taşıyan SimpleNamespace.
    """
    return SimpleNamespace(
        qr_seq=qr_seq,
        formation_active=formation_active,
        altitude_active=altitude_active,
        maneuver_active=maneuver_active,
        detach_active=detach_active,
        complete_mission=complete_mission,
        wait_s=wait_s,
        next_qr=next_qr,
    )


def _ctx(
    state: MissionState = MissionState.IDLE,
    mission_type: MissionType = MissionType.DYNAMIC_SWARM,
    sitl_mode: bool = True,
) -> MissionContext:
    """Test için yapılandırılmış MissionContext döner.

    SITL modunda GPS/origin/home kontrolleri atlanır.

    Args:
        state: Başlangıç state'i.
        mission_type: Görev tipi.
        sitl_mode: True ise saha kontrolleri atlanır.

    Returns:
        Hazırlanmış MissionContext.
    """
    ctx = MissionContext(
        agent_ids=[1, 2, 3],
        team_id='YELPENCE',
        sitl_mode=sitl_mode,
    )
    ctx.set_state(state)
    ctx.mission_type = mission_type
    return ctx


def _all_agents(ctx: MissionContext, state: int = 5) -> None:
    """Tüm ajanları verilen state'te sağlıklı olarak ekler.

    Args:
        ctx: Güncellenecek MissionContext.
        state: AgentStatus.STATE_* değeri.
    """
    for aid in ctx.agent_ids:
        ctx.agent_statuses[aid] = _status(state=state)


def _geç(ctx: MissionContext, saniye: float) -> None:
    """State giriş zamanını geriye alarak timeout simüle eder.

    Args:
        ctx: Güncellenecek MissionContext.
        saniye: Geriye alınacak süre.
    """
    ctx.state_entry_time = time.monotonic() - saniye


# =================================================================
# UNKNOWN → IDLE
# =================================================================

class TestUnknownIdle(unittest.TestCase):
    """UNKNOWN → IDLE geçiş testi."""

    def test_unknown_her_zaman_idle(self):
        """UNKNOWN'dan ilk tick'te IDLE'a geçmeli."""
        ctx = _ctx(MissionState.UNKNOWN)
        self.assertEqual(evaluate_transitions(ctx), MissionState.IDLE)


# =================================================================
# IDLE
# =================================================================

class TestIdle(unittest.TestCase):
    """IDLE state geçiş testleri."""

    def test_start_komutu_preflight(self):
        """START komutu gelince IDLE → PREFLIGHT geçmeli."""
        ctx = _ctx(MissionState.IDLE)
        ctx.pending_command = _START
        self.assertEqual(
            evaluate_transitions(ctx), MissionState.PREFLIGHT
        )

    def test_komut_yok_gecis_yok(self):
        """Komut yokken IDLE'da kalmalı."""
        ctx = _ctx(MissionState.IDLE)
        self.assertIsNone(evaluate_transitions(ctx))

    def test_abort_idle_aborted(self):
        """ABORT komutu gelince IDLE → ABORTED geçmeli."""
        ctx = _ctx(MissionState.IDLE)
        ctx.pending_command = _ABORT
        self.assertEqual(
            evaluate_transitions(ctx), MissionState.ABORTED
        )


# =================================================================
# PREFLIGHT
# =================================================================

class TestPreflight(unittest.TestCase):
    """PREFLIGHT state geçiş testleri."""

    def test_ajanlar_hazirsa_takeoff(self):
        """Tüm ajanlar sağlıklı ve SITL modunda → SYNCHRONIZED_TAKEOFF."""
        ctx = _ctx(MissionState.PREFLIGHT)
        _all_agents(ctx, state=1)  # IDLE=1, sağlıklı
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.SYNCHRONIZED_TAKEOFF)

    def test_ajan_gorulmeden_gecis_yok(self):
        """Hiç ajan görülmemişse PREFLIGHT'ta beklemeli."""
        ctx = _ctx(MissionState.PREFLIGHT)
        self.assertIsNone(evaluate_transitions(ctx))

    def test_sagliksiz_ajan_gecis_yok(self):
        """Bir ajan sağlıksız ise PREFLIGHT'ta beklemeli."""
        ctx = _ctx(MissionState.PREFLIGHT)
        for aid in [1, 2]:
            ctx.agent_statuses[aid] = _status(healthy=True)
        ctx.agent_statuses[3] = _status(healthy=False)
        self.assertIsNone(evaluate_transitions(ctx))

    def test_timeout_aborted(self):
        """60s içinde hazır olunmazsa ABORTED geçmeli."""
        ctx = _ctx(MissionState.PREFLIGHT)
        _geç(ctx, 61.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ABORTED)

    def test_gercek_modda_gps_kontrolu(self):
        """SITL=False modunda GPS yetersizse geçiş olmamalı."""
        ctx = _ctx(MissionState.PREFLIGHT, sitl_mode=False)
        for aid in ctx.agent_ids:
            ctx.agent_statuses[aid] = _status(
                healthy=True,
                gps_fix_type=2,   # yetersiz: 2D fix
                gps_hdop=0.9,
            )
        self.assertIsNone(evaluate_transitions(ctx))

    def test_gercek_modda_origin_kontrolu(self):
        """SITL=False modunda origin_synced=False ise geçiş olmamalı."""
        ctx = _ctx(MissionState.PREFLIGHT, sitl_mode=False)
        for aid in ctx.agent_ids:
            ctx.agent_statuses[aid] = _status(
                healthy=True,
                origin_synced=False,
            )
        self.assertIsNone(evaluate_transitions(ctx))


# =================================================================
# SYNCHRONIZED_TAKEOFF
# =================================================================

class TestSynchronizedTakeoff(unittest.TestCase):
    """SYNCHRONIZED_TAKEOFF state geçiş testleri."""

    def test_gorev1_qr_varsa_rotate(self):
        """Görev 1: tüm ajanlar IN_SWARM ise önce ROTATE_TO_NEXT.

        Şartname: kalkış sonrası sürü ilk QR'a dönerek yaklaşmaya başlar.
        """
        ctx = _ctx(MissionState.SYNCHRONIZED_TAKEOFF)
        _all_agents(ctx, state=5)   # IN_SWARM=5
        ctx.current_qr = _qr()
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ROTATE_TO_NEXT)

    def test_gorev1_qr_yok_yine_rotate(self):
        """Görev 1: ajanlar IN_SWARM ise QR olsa da olmasa da ROTATE_TO_NEXT.

        Şartname: QR koordinatı yarışma öncesi paylaşılır; dönerek yaklaş.
        Eski davranış (current_qr=None ise bekle) kilitlenmeye yol açardı.
        """
        ctx = _ctx(MissionState.SYNCHRONIZED_TAKEOFF)
        _all_agents(ctx, state=5)
        ctx.current_qr = None   # QR henüz okunmadı — yine de geçiş olmalı
        self.assertEqual(
            evaluate_transitions(ctx), MissionState.ROTATE_TO_NEXT
        )

    def test_gorev2_semi_autonomous(self):
        """Görev 2: tüm ajanlar IN_SWARM ise SEMI_AUTONOMOUS."""
        ctx = _ctx(
            MissionState.SYNCHRONIZED_TAKEOFF,
            mission_type=MissionType.SEMI_AUTONOMOUS,
        )
        _all_agents(ctx, state=5)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.SEMI_AUTONOMOUS)

    def test_kalkis_bitmedi_bekle(self):
        """Ajanlar henüz IN_SWARM değilse beklemeli."""
        ctx = _ctx(MissionState.SYNCHRONIZED_TAKEOFF)
        _all_agents(ctx, state=4)   # TAKEOFF=4
        self.assertIsNone(evaluate_transitions(ctx))

    def test_timeout_aborted(self):
        """90s geçince ABORTED olmalı."""
        ctx = _ctx(MissionState.SYNCHRONIZED_TAKEOFF)
        _geç(ctx, 91.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ABORTED)


# =================================================================
# NAVIGATE_TO_QR
# =================================================================

class TestNavigateToQr(unittest.TestCase):
    """NAVIGATE_TO_QR state geçiş testleri."""

    def test_formasyon_ulasinca_execute(self):
        """EVENT_FORMATION_REACHED → EXECUTE_QR_TASK."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        ctx.event_formation_reached = True
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.EXECUTE_QR_TASK)

    def test_event_transitions_okur_yazmaz(self):
        """evaluate_transitions event flag'ı temizlemez; set_state temizler."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        ctx.event_formation_reached = True
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.EXECUTE_QR_TASK)
        # transitions.py okur, yazmaz — flag hâlâ set
        self.assertTrue(ctx.event_formation_reached)
        # node set_state() çağırdığında temizlenir
        ctx.set_state(MissionState.EXECUTE_QR_TASK)
        self.assertFalse(ctx.event_formation_reached)

    def test_bekleme_surerken_gecis_yok(self):
        """Event gelmeden NAVIGATE_TO_QR'da beklemeli."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        self.assertIsNone(evaluate_transitions(ctx))

    def test_timeout_return_home(self):
        """120s geçince RETURN_HOME olmalı."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        _geç(ctx, 121.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)


# =================================================================
# EXECUTE_QR_TASK
# =================================================================

class TestExecuteQrTask(unittest.TestCase):
    """EXECUTE_QR_TASK state geçiş testleri."""

    def test_action_basarisiz_return_home(self):
        """Action başarısız olursa RETURN_HOME olmalı."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr()
        ctx.qr_task_step = QrTaskStep.FORMATION
        ctx.action_done = True
        ctx.action_success = False
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_done_wait_s_varsa_wait(self):
        """DONE ve wait_s > 0 → WAIT_AT_QR."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(wait_s=3.0, next_qr=2)
        ctx.qr_task_step = QrTaskStep.DONE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.WAIT_AT_QR)

    def test_done_next_qr_varsa_rotate(self):
        """DONE, wait_s=0, next_qr > 0 → ROTATE_TO_NEXT."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(wait_s=0.0, next_qr=2)
        ctx.qr_task_step = QrTaskStep.DONE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ROTATE_TO_NEXT)

    def test_done_complete_mission_return_home(self):
        """DONE ve complete_mission=True → RETURN_HOME."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(complete_mission=True)
        ctx.qr_task_step = QrTaskStep.DONE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_done_son_qr_return_home(self):
        """DONE, wait_s=0, next_qr=0 → RETURN_HOME (son QR)."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(wait_s=0.0, next_qr=0)
        ctx.qr_task_step = QrTaskStep.DONE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_qr_henuz_okunmadi_bekle(self):
        """current_qr=None → kamera gecikmiş olabilir, timeout bekle.

        Eski davranış (hemen RETURN_HOME) yanlış eve dönüşe yol açardı.
        """
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = None
        self.assertIsNone(evaluate_transitions(ctx))  # timeout dolmadı → bekle

    def test_qr_yoksa_timeout_sonrasi_return_home(self):
        """current_qr=None + timeout doldu → RETURN_HOME."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = None
        ctx.state_entry_time -= 91.0   # 91s geçmiş gibi simüle et
        self.assertEqual(evaluate_transitions(ctx), MissionState.RETURN_HOME)

    def test_action_devam_ediyor_bekle(self):
        """Action henüz tamamlanmadıysa beklemeli."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(formation_active=True)
        ctx.qr_task_step = QrTaskStep.FORMATION
        ctx.action_done = False
        self.assertIsNone(evaluate_transitions(ctx))

    def test_timeout_return_home(self):
        """90s geçince RETURN_HOME olmalı."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.current_qr = _qr(formation_active=True)
        ctx.qr_task_step = QrTaskStep.FORMATION
        _geç(ctx, 91.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)


# =================================================================
# WAIT_AT_QR
# =================================================================

class TestWaitAtQr(unittest.TestCase):
    """WAIT_AT_QR state geçiş testleri."""

    def test_deadline_gecti_next_qr_var_rotate(self):
        """Deadline doldu ve next_qr > 0 → ROTATE_TO_NEXT."""
        ctx = _ctx(MissionState.WAIT_AT_QR)
        ctx.current_qr = _qr(next_qr=2)
        ctx.wait_deadline = time.monotonic() - 1.0  # geçmiş deadline
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ROTATE_TO_NEXT)

    def test_deadline_gecti_next_qr_yok_return(self):
        """Deadline doldu ve next_qr=0 → RETURN_HOME."""
        ctx = _ctx(MissionState.WAIT_AT_QR)
        ctx.current_qr = _qr(next_qr=0)
        ctx.wait_deadline = time.monotonic() - 1.0
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_deadline_dolmadi_bekle(self):
        """Deadline gelmemişse WAIT_AT_QR'da beklemeli."""
        ctx = _ctx(MissionState.WAIT_AT_QR)
        ctx.current_qr = _qr(next_qr=2)
        ctx.wait_deadline = time.monotonic() + 10.0  # ileride
        self.assertIsNone(evaluate_transitions(ctx))

    def test_deadline_yok_bekle(self):
        """wait_deadline=None ise beklemeli (henüz set edilmedi)."""
        ctx = _ctx(MissionState.WAIT_AT_QR)
        ctx.current_qr = _qr()
        ctx.wait_deadline = None
        self.assertIsNone(evaluate_transitions(ctx))

    def test_complete_mission_return_home(self):
        """Deadline doldu ve complete_mission=True → RETURN_HOME."""
        ctx = _ctx(MissionState.WAIT_AT_QR)
        ctx.current_qr = _qr(next_qr=2, complete_mission=True)
        ctx.wait_deadline = time.monotonic() - 1.0
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)


# =================================================================
# ROTATE_TO_NEXT
# =================================================================

class TestRotateToNext(unittest.TestCase):
    """ROTATE_TO_NEXT state geçiş testleri."""

    def test_rotasyon_tamamlandi_navigate(self):
        """EVENT_ROTATION_COMPLETED → NAVIGATE_TO_QR."""
        ctx = _ctx(MissionState.ROTATE_TO_NEXT)
        ctx.event_rotation_completed = True
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.NAVIGATE_TO_QR)

    def test_event_transitions_okur_yazmaz(self):
        """evaluate_transitions event flag'ı temizlemez; set_state temizler."""
        ctx = _ctx(MissionState.ROTATE_TO_NEXT)
        ctx.event_rotation_completed = True
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.NAVIGATE_TO_QR)
        # transitions.py okur, yazmaz — flag hâlâ set
        self.assertTrue(ctx.event_rotation_completed)
        # node set_state() çağırdığında temizlenir
        ctx.set_state(MissionState.NAVIGATE_TO_QR)
        self.assertFalse(ctx.event_rotation_completed)

    def test_bekleme_surerken_gecis_yok(self):
        """Event gelmeden ROTATE_TO_NEXT'te beklemeli."""
        ctx = _ctx(MissionState.ROTATE_TO_NEXT)
        self.assertIsNone(evaluate_transitions(ctx))

    def test_timeout_yine_de_navigate(self):
        """30s geçince yanıt beklenmeden NAVIGATE_TO_QR olmalı."""
        ctx = _ctx(MissionState.ROTATE_TO_NEXT)
        _geç(ctx, 31.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.NAVIGATE_TO_QR)


# =================================================================
# SEMI_AUTONOMOUS (Görev 2)
# =================================================================

class TestSemiAutonomous(unittest.TestCase):
    """SEMI_AUTONOMOUS state geçiş testleri."""

    def test_rtl_komutu_return_home(self):
        """RTL komutu → RETURN_HOME."""
        ctx = _ctx(
            MissionState.SEMI_AUTONOMOUS,
            mission_type=MissionType.SEMI_AUTONOMOUS,
        )
        ctx.pending_command = _RTL
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_land_komutu_return_home(self):
        """LAND komutu → RETURN_HOME."""
        ctx = _ctx(
            MissionState.SEMI_AUTONOMOUS,
            mission_type=MissionType.SEMI_AUTONOMOUS,
        )
        ctx.pending_command = _LAND
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)

    def test_aktif_bekle(self):
        """Komut yokken SEMI_AUTONOMOUS'ta beklemeli."""
        ctx = _ctx(
            MissionState.SEMI_AUTONOMOUS,
            mission_type=MissionType.SEMI_AUTONOMOUS,
        )
        self.assertIsNone(evaluate_transitions(ctx))


# =================================================================
# RETURN_HOME
# =================================================================

class TestReturnHome(unittest.TestCase):
    """RETURN_HOME state geçiş testleri."""

    def test_ajanlar_landing_ise_landing(self):
        """Tüm ajanlar LANDING(12) ise LANDING state'ine geç."""
        ctx = _ctx(MissionState.RETURN_HOME)
        _all_agents(ctx, state=12)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.LANDING)

    def test_ajanlar_landed_ise_landing(self):
        """Tüm ajanlar LANDED(13) ise de LANDING'e geç."""
        ctx = _ctx(MissionState.RETURN_HOME)
        _all_agents(ctx, state=13)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.LANDING)

    def test_ucus_devam_bekle(self):
        """Ajanlar hâlâ RETURN_HOME(11) ise beklemeli."""
        ctx = _ctx(MissionState.RETURN_HOME)
        _all_agents(ctx, state=11)
        self.assertIsNone(evaluate_transitions(ctx))


# =================================================================
# LANDING
# =================================================================

class TestLanding(unittest.TestCase):
    """LANDING state geçiş testleri."""

    def test_hepsi_landed_complete(self):
        """Tüm ajanlar LANDED → MISSION_COMPLETE."""
        ctx = _ctx(MissionState.LANDING)
        _all_agents(ctx, state=13)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.MISSION_COMPLETE)

    def test_timeout_complete(self):
        """90s geçince kayıp ajan toleransıyla MISSION_COMPLETE olmalı."""
        ctx = _ctx(MissionState.LANDING)
        _geç(ctx, 91.0)
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.MISSION_COMPLETE)

    def test_inis_devam_bekle(self):
        """Ajanlar henüz inmemişse beklemeli."""
        ctx = _ctx(MissionState.LANDING)
        _all_agents(ctx, state=12)
        self.assertIsNone(evaluate_transitions(ctx))


# =================================================================
# PAUSED
# =================================================================

class TestPaused(unittest.TestCase):
    """PAUSED state geçiş testleri."""

    def test_resume_navigate(self):
        """RESUME komutu → NAVIGATE_TO_QR."""
        ctx = _ctx(MissionState.PAUSED)
        ctx.pending_command = _RESUME
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.NAVIGATE_TO_QR)

    def test_resume_yok_bekle(self):
        """RESUME gelmeden PAUSED'da beklemeli."""
        ctx = _ctx(MissionState.PAUSED)
        self.assertIsNone(evaluate_transitions(ctx))


# =================================================================
# GLOBAL KOMUTLAR (her state'ten tetiklenir)
# =================================================================

class TestGlobalAbort(unittest.TestCase):
    """ABORT komutu tüm aktif state'lerden ABORTED'a götürmeli."""

    def _abort_testi(self, state: MissionState):
        ctx = _ctx(state)
        ctx.pending_command = _ABORT
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.ABORTED, msg=state.name)

    def test_abort_preflight(self):
        self._abort_testi(MissionState.PREFLIGHT)

    def test_abort_synchronized_takeoff(self):
        self._abort_testi(MissionState.SYNCHRONIZED_TAKEOFF)

    def test_abort_navigate_to_qr(self):
        self._abort_testi(MissionState.NAVIGATE_TO_QR)

    def test_abort_execute_qr_task(self):
        self._abort_testi(MissionState.EXECUTE_QR_TASK)

    def test_abort_wait_at_qr(self):
        self._abort_testi(MissionState.WAIT_AT_QR)

    def test_abort_semi_autonomous(self):
        self._abort_testi(MissionState.SEMI_AUTONOMOUS)

    def test_abort_terminal_state_etkilemez(self):
        """MISSION_COMPLETE state'inde ABORT etkisiz olmalı."""
        ctx = _ctx(MissionState.MISSION_COMPLETE)
        ctx.pending_command = _ABORT
        result = evaluate_transitions(ctx)
        self.assertIsNone(result)


class TestGlobalRtl(unittest.TestCase):
    """RTL/LAND komutu aktif uçuş state'lerinden RETURN_HOME'a götürmeli."""

    def _rtl_testi(self, state: MissionState):
        ctx = _ctx(state)
        ctx.pending_command = _RTL
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME, msg=state.name)

    def test_rtl_navigate(self):
        self._rtl_testi(MissionState.NAVIGATE_TO_QR)

    def test_rtl_execute_qr(self):
        self._rtl_testi(MissionState.EXECUTE_QR_TASK)

    def test_rtl_wait_at_qr(self):
        self._rtl_testi(MissionState.WAIT_AT_QR)

    def test_rtl_rotate_to_next(self):
        self._rtl_testi(MissionState.ROTATE_TO_NEXT)

    def test_rtl_paused(self):
        self._rtl_testi(MissionState.PAUSED)

    def test_land_komutu_da_rtl(self):
        """LAND komutu da RETURN_HOME tetiklemeli."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        ctx.pending_command = _LAND
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.RETURN_HOME)


class TestGlobalPause(unittest.TestCase):
    """PAUSE komutu uçuş state'lerinden PAUSED'a götürmeli."""

    def test_pause_navigate(self):
        """NAVIGATE_TO_QR → PAUSED."""
        ctx = _ctx(MissionState.NAVIGATE_TO_QR)
        ctx.pending_command = _PAUSE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.PAUSED)

    def test_pause_execute_qr(self):
        """EXECUTE_QR_TASK → PAUSED."""
        ctx = _ctx(MissionState.EXECUTE_QR_TASK)
        ctx.pending_command = _PAUSE
        result = evaluate_transitions(ctx)
        self.assertEqual(result, MissionState.PAUSED)

    def test_pause_idle_etkisiz(self):
        """IDLE'da PAUSE etkisiz olmalı."""
        ctx = _ctx(MissionState.IDLE)
        ctx.pending_command = _PAUSE
        # IDLE'dan PAUSE tanımsız; START olmadan PREFLIGHT'a da geçmemeli
        result = evaluate_transitions(ctx)
        self.assertNotEqual(result, MissionState.PAUSED)


# =================================================================
# FIND_FIRST_QR_STEP
# =================================================================

class TestFindFirstQrStep(unittest.TestCase):
    """find_first_qr_step fonksiyon testleri."""

    def test_hic_aktif_yok_done(self):
        """Aktif bölüm yoksa DONE dönmeli."""
        qr = _qr()
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.DONE)

    def test_sadece_formation(self):
        """Yalnızca formation_active=True → FORMATION."""
        qr = _qr(formation_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.FORMATION)

    def test_sadece_altitude(self):
        """Yalnızca altitude_active=True → ALTITUDE."""
        qr = _qr(altitude_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.ALTITUDE)

    def test_sadece_maneuver(self):
        """Yalnızca maneuver_active=True → MANEUVER."""
        qr = _qr(maneuver_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.MANEUVER)

    def test_sadece_detach(self):
        """Yalnızca detach_active=True → DETACH."""
        qr = _qr(detach_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.DETACH)

    def test_formation_ve_maneuver_formation_once(self):
        """formation ve maneuver aktifse önce FORMATION gelmeli."""
        qr = _qr(formation_active=True, maneuver_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.FORMATION)

    def test_maneuver_ve_altitude_maneuver_once(self):
        """Maneuver ve altitude aktifse şartnameye göre MANEUVER önce gelmeli.

        Şartname sırası: FORMATION → MANEUVER → ALTITUDE → DETACH.
        """
        qr = _qr(maneuver_active=True, altitude_active=True)
        self.assertEqual(find_first_qr_step(qr), QrTaskStep.MANEUVER)

    def test_none_qr_done(self):
        """qr=None ise DONE dönmeli."""
        self.assertEqual(find_first_qr_step(None), QrTaskStep.DONE)


# =================================================================
# FIND_NEXT_QR_STEP
# =================================================================

class TestFindNextQrStep(unittest.TestCase):
    """find_next_qr_step fonksiyon testleri."""

    def test_formation_sonrasi_altitude(self):
        """FORMATION tamamlandı, altitude aktif → ALTITUDE."""
        qr = _qr(formation_active=True, altitude_active=True)
        result = find_next_qr_step(qr, QrTaskStep.FORMATION)
        self.assertEqual(result, QrTaskStep.ALTITUDE)

    def test_formation_sonrasi_sadece_maneuver(self):
        """FORMATION tamamlandı, altitude yok, maneuver aktif → MANEUVER."""
        qr = _qr(formation_active=True, maneuver_active=True)
        result = find_next_qr_step(qr, QrTaskStep.FORMATION)
        self.assertEqual(result, QrTaskStep.MANEUVER)

    def test_son_adim_done(self):
        """Son aktif adım tamamlandı → DONE."""
        qr = _qr(formation_active=True)
        result = find_next_qr_step(qr, QrTaskStep.FORMATION)
        self.assertEqual(result, QrTaskStep.DONE)

    def test_altitude_sonrasi_detach(self):
        """ALTITUDE tamamlandı, detach aktif → DETACH."""
        qr = _qr(altitude_active=True, detach_active=True)
        result = find_next_qr_step(qr, QrTaskStep.ALTITUDE)
        self.assertEqual(result, QrTaskStep.DETACH)

    def test_none_qr_done(self):
        """qr=None ise DONE dönmeli."""
        result = find_next_qr_step(None, QrTaskStep.FORMATION)
        self.assertEqual(result, QrTaskStep.DONE)

    def test_tum_adimlar_aktif_sira(self):
        """Tüm adımlar aktifken sıra: FORMATION→MANEUVER→ALTITUDE→DETACH."""
        qr = _qr(
            formation_active=True,
            altitude_active=True,
            maneuver_active=True,
            detach_active=True,
        )
        self.assertEqual(
            find_next_qr_step(qr, QrTaskStep.FORMATION),
            QrTaskStep.MANEUVER,
        )
        self.assertEqual(
            find_next_qr_step(qr, QrTaskStep.MANEUVER),
            QrTaskStep.ALTITUDE,
        )
        self.assertEqual(
            find_next_qr_step(qr, QrTaskStep.ALTITUDE),
            QrTaskStep.DETACH,
        )
        self.assertEqual(
            find_next_qr_step(qr, QrTaskStep.DETACH),
            QrTaskStep.DONE,
        )


if __name__ == '__main__':
    unittest.main()
