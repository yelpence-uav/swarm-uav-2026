"""orchestrator birim testleri — faz → komut kararı."""

import math
from types import SimpleNamespace

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    DetachCmd,
    FormationTargetCmd,
    ManeuverCmd,
    Mission1Orchestrator,
    OrchestratorInput,
)

# MissionState
S_TAKEOFF = 3
S_NAVIGATE = 4
S_EXECUTE = 5
S_ROTATE = 7
S_RETURN_HOME = 9
# QrTaskStep
STEP_FORMATION = 1
STEP_MANEUVER = 2
STEP_ALTITUDE = 3
STEP_DETACH = 4
STEP_DONE = 5

_IDS = [1, 2, 3]
_POS = [(0.0, 0.0, -10.0), (3.0, -3.0, -10.0), (3.0, 3.0, -10.0)]
# _POS'un GERÇEK centroid'i. Fikstür centroid'i konumlarla tutarlı olmalıdır:
# ofsetler centroid'e görelidir, dolayısıyla ortalamaları sıfırdır. Tutarsız bir
# centroid, "sürüyü yerinde tut" hesabını kaydırır ve testi gerçek davranıştan
# koparır.
_CEN = (2.0, 0.0, -10.0)
_HOME = (0.0, 0.0, 0.0)


def _ready_orch():
    """Origin + sıradaki hedef (kuzeyde) yüklü orkestratör."""
    o = Mission1Orchestrator()
    o.set_origin(41.0, 29.0)
    o.set_next_target(True, 41.001, 29.0)
    return o


def _qr(**kw):
    """Varsayılan alanlarla QRMissionData benzeri nesne."""
    base = dict(
        qr_seq=1, valid=True, next_qr=4, formation_type=1, spacing_m=6.0,
        pitch_deg=0.0, roll_deg=0.0, yaw_deg=0.0, altitude_agl_m=20.0,
        target_agent_id=0, detach_wait_s=0.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _inp(state, step, leader=True, qr=None, time_in_state=0.0,
         centroid=_CEN):
    """Test için OrchestratorInput kısayolu."""
    return OrchestratorInput(
        mission_state=state, qr_step=step, is_leader=leader,
        agent_ids=list(_IDS), positions=list(_POS), centroid=centroid,
        home=_HOME, qr=qr, time_in_state=time_in_state,
    )


def test_navigate_blocked_until_qr_ready():
    """Origin/tablo yokken hiçbir komut üretilmez (tekrar denenir)."""
    o = Mission1Orchestrator()
    assert o.decide(_inp(S_ROTATE, 0)) == []
    assert not o.qr_ready


def test_first_rotate_targets_next_qr():
    """İlk ROTATE önce dizilişi KORUR, sonra hedefe döndürür.

    İlk komut heading=0 ile mevcut dizilişi yayınlar: path_planner heading
    rampasını bu ilk komuttan başlatır. Bu komut olmadan rampa, rotasyon
    komutunun heading'inden başlıyor ve kalkış dizilişi ilk tick'te hedefe
    snap'leyip savruluyordu.
    """
    o = _ready_orch()
    cmds = o.decide(_inp(S_ROTATE, 0))
    assert len(cmds) == 2

    koru = cmds[0]
    assert isinstance(koru, FormationTargetCmd)
    assert not koru.rotate_towards_target
    assert koru.heading_deg == 0.0

    doner = cmds[1]
    assert isinstance(doner, FormationTargetCmd)
    assert doner.rotate_towards_target
    assert len(doner.offsets) == 3
    # Hedef kuzeyde → heading ≈ 0.
    assert abs(doner.heading_deg) < 1.0


def test_takeoff_holds_initial_formation():
    """SYNCHRONIZED_TAKEOFF başlangıç formasyonunu mevcut merkezde tutar."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_TAKEOFF, 0))
    assert len(cmds) == 1
    c = cmds[0]
    assert isinstance(c, FormationTargetCmd)
    assert c.center == _CEN               # mevcut merkez, kaymaz
    assert not c.rotate_towards_target    # kalkışta rotasyon yok
    assert c.use_current_altitude         # irtifayı agent_fsm yönetir
    assert len(c.offsets) == 3


def test_takeoff_suppressed_on_follower():
    """Kalkış formasyonu yalnız liderde üretilir (lider-guard)."""
    o = _ready_orch()
    assert o.decide(_inp(S_TAKEOFF, 0, leader=False)) == []


def test_detach_holds_formation():
    """Bir dron ayrılınca kalanlar slotlarını korur (re-form yok — şartname)."""
    o = _ready_orch()
    o._cfg.full_agent_count = 3
    full = o.decide(_inp(S_TAKEOFF, 0))          # tam sürü → slotlar dondurulur
    off = dict(zip(_IDS, full[0].offsets))
    inp2 = OrchestratorInput(
        mission_state=S_ROTATE, qr_step=0, is_leader=True,
        agent_ids=[1, 2], positions=_POS[:2], centroid=_CEN, home=_HOME,
    )
    cmds = o.decide(inp2)                          # aktif=2 → dondurulmuş slot
    assert cmds[0].offsets[0] == off[1]
    assert cmds[0].offsets[1] == off[2]


def test_navigate_anchors_nearest_drone_to_qr():
    """NAVIGATE merkezi QR'a koymaz; en yakın dronu QR'ın üstüne çıpalar."""
    o = _ready_orch()
    ned = o._qr_geo.resolve_ned()
    cmds = o.decide(_inp(S_NAVIGATE, 0))
    assert len(cmds) == 1
    c = cmds[0].center
    # En yakın dron QR'ın üstüne gelmeli: merkez = centroid + (QR − okuyucu)
    reader = min(_POS, key=lambda p: math.hypot(p[0] - ned[0], p[1] - ned[1]))
    assert abs(c[0] - (_CEN[0] + ned[0] - reader[0])) < 1e-6
    assert abs(c[1] - (_CEN[1] + ned[1] - reader[1])) < 1e-6
    # Merkez QR'da DEĞİL (çıpalama farkı belirgin)
    assert math.hypot(c[0] - ned[0], c[1] - ned[1]) > 1.0


def test_emit_once_per_phase():
    """Aynı faz ikinci tick'te komut üretmez."""
    o = _ready_orch()
    # İlk ROTATE: dizilişi koru + hedefe dön (2 komut).
    assert len(o.decide(_inp(S_ROTATE, 0))) == 2
    assert o.decide(_inp(S_ROTATE, 0)) == []


def test_follower_suppresses_formation_command():
    """Lider olmayan drone ROTATE'te FormationTargetCmd üretmez."""
    o = _ready_orch()
    assert o.decide(_inp(S_ROTATE, 0, leader=False)) == []


def test_maneuver_emitted_on_every_drone():
    """MANEUVER her drone'da ManeuverCmd üretir (lider olmasa da)."""
    o = _ready_orch()
    qr = _qr(pitch_deg=-10.0)
    cmds = o.decide(_inp(S_EXECUTE, STEP_MANEUVER, leader=False, qr=qr))
    assert len(cmds) == 1
    assert isinstance(cmds[0], ManeuverCmd)
    assert cmds[0].pitch_deg == -10.0
    # Geçici manevra: bitince bırakır, eğik pozu formation_control korur.
    assert not cmds[0].hold_after_complete


def test_detach_emits_detach_cmd():
    """DETACH adımı hedef ID + bekleme süresiyle DetachCmd üretir (lider)."""
    o = _ready_orch()
    qr = _qr(target_agent_id=2, detach_wait_s=5.0)
    cmds = o.decide(_inp(S_EXECUTE, STEP_DETACH, qr=qr))
    assert len(cmds) == 1
    assert isinstance(cmds[0], DetachCmd)
    assert cmds[0].target_agent_id == 2
    assert cmds[0].detach_wait_s == 5.0


def test_model_b_tilt_baked_after_maneuver():
    """Manevra sonrası irtifa ofsetleri eğik (eğimsizden farklı)."""
    # A: manevrasız irtifa
    oa = _ready_orch()
    cmds_a = oa.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr()))
    # B: önce manevra (pitch -15), sonra irtifa
    ob = _ready_orch()
    ob.decide(_inp(S_EXECUTE, STEP_MANEUVER, qr=_qr(pitch_deg=-15.0)))
    cmds_b = ob.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr(pitch_deg=-15.0)))
    assert cmds_a[0].offsets != cmds_b[0].offsets


def test_egim_donmus_dizilisin_ustunde_de_korunur():
    """Eğim, RİJİT (dondurulmuş) diziliş üzerinde de uygulanmaya devam eder.

    Şartname: manevradan sonra yeni bir formasyon/manevra komutu gelene kadar
    sürü eğimini KORUR. Dondurulmuş ofsetler ham döndürülürse eğim ilk irtifa
    komutunda kayboluyor, sürü düzleşiyordu (manevra kaleminden puan gider).
    """
    o = _ready_orch()
    # Diziliş kalkışta dondurulur (jüri snapshot'ı).
    o.decide(_inp(S_TAKEOFF, 0))
    # Manevra: pitch -15 → eğim durumda saklanır.
    o.decide(_inp(S_EXECUTE, STEP_MANEUVER, qr=_qr(pitch_deg=-15.0)))
    # Sonraki irtifa görevi dondurulmuş dizilişi kullanır AMA eğik olmalı.
    cmds = o.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr(pitch_deg=-15.0)))

    z = [off[2] for off in cmds[0].offsets]
    assert any(abs(v) > 1e-6 for v in z), 'egim kayboldu: ofsetler duz'


def test_egimsizken_ofsetler_duz_kalir():
    """Manevra yokken ofsetlerde dikey bileşen oluşmaz (eğim sızıntısı yok)."""
    o = _ready_orch()
    o.decide(_inp(S_TAKEOFF, 0))
    cmds = o.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr()))

    z = [off[2] for off in cmds[0].offsets]
    assert all(abs(v) < 1e-6 for v in z)


def test_formation_change_resets_tilt():
    """Formasyon değişimi eğimi sıfırlar; manevralı ve manevrasız eşit çıkar."""
    # Manevra → formasyon değişimi → irtifa
    o = _ready_orch()
    o.decide(_inp(S_EXECUTE, STEP_MANEUVER, qr=_qr(pitch_deg=-15.0)))
    o.decide(_inp(S_EXECUTE, STEP_FORMATION, qr=_qr(formation_type=1)))
    cmds = o.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr()))
    # Kontrol: aynı formasyon değişimi ama önce manevra YOK
    ctrl = _ready_orch()
    ctrl.decide(_inp(S_EXECUTE, STEP_FORMATION, qr=_qr(formation_type=1)))
    cmds_ctrl = ctrl.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr()))
    assert cmds[0].offsets == cmds_ctrl[0].offsets


def test_altitude_sets_center_z():
    """İrtifa adımı center_z'yi -alt_agl yapar (NED down)."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_EXECUTE, STEP_ALTITUDE, qr=_qr(altitude_agl_m=30.0)))
    assert cmds[0].center[2] == -30.0
    assert not cmds[0].use_current_altitude


def test_return_home_targets_home():
    """RETURN_HOME merkezi home konumuna kurar."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_RETURN_HOME, 0))
    assert len(cmds) == 1
    assert cmds[0].center == _HOME


def test_hold_tilt_published_after_maneuver():
    """Manevra sonrası DONE'da eğik pozu koruyan formasyon yayınlanır."""
    o = _ready_orch()
    o.decide(_inp(S_EXECUTE, STEP_MANEUVER, qr=_qr(pitch_deg=-12.0)))
    cmds = o.decide(_inp(S_EXECUTE, STEP_DONE, qr=_qr(pitch_deg=-12.0)))
    forms = [c for c in cmds if isinstance(c, FormationTargetCmd)]
    assert len(forms) == 1


def test_no_hold_tilt_without_maneuver():
    """Eğim yokken DONE hiçbir formasyon komutu üretmez."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_EXECUTE, STEP_DONE, qr=_qr()))
    assert cmds == []


def test_qr_recovery_descends_when_stuck():
    """QR okunmadan süre aşılınca okuma irtifasına alçalır (10m tabanı)."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_EXECUTE, 0, time_in_state=10.0,
                         centroid=(0.0, 0.0, -20.0)))
    forms = [c for c in cmds if isinstance(c, FormationTargetCmd)]
    assert len(forms) == 1
    assert forms[0].center[2] == -12.0
    assert not forms[0].use_current_altitude


def test_qr_recovery_not_before_delay():
    """Süre eşiği aşılmadan alçalma yapılmaz."""
    o = _ready_orch()
    cmds = o.decide(_inp(S_EXECUTE, 0, time_in_state=2.0,
                         centroid=(0.0, 0.0, -20.0)))
    assert not any(isinstance(c, FormationTargetCmd) for c in cmds)


def test_qr_recovery_emitted_once():
    """Alçalma bir kez yapılır; takılma sürse de tekrar etmez."""
    o = _ready_orch()
    o.decide(_inp(S_EXECUTE, 0, time_in_state=10.0, centroid=(0.0, 0.0, -20.0)))
    cmds = o.decide(_inp(S_EXECUTE, 0, time_in_state=12.0,
                         centroid=(0.0, 0.0, -20.0)))
    assert not any(isinstance(c, FormationTargetCmd) for c in cmds)
