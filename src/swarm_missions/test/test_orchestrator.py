"""orchestrator birim testleri — faz → komut kararı."""

import math
from types import SimpleNamespace

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    DetachCmd,
    FormationTargetCmd,
    ManeuverCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
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
    """Origin/tablo yokken hedefe gidilmez ama SURU TUTULUR.

    2 Eylul'e kadar burada `== []` bekleniyordu. O davranis sahada uc ucusu
    bitirdi: komut ureten kimse kalmayinca passthrough=0 oluyor, PX4
    OFFBOARD'i birakiyor ve agent_fsm FAILSAFE veriyordu. `_hedefsiz_tut`
    o boslugu kapatti — hedef yoksa suru mevcut merkezinde formasyonu
    KORUR. Test o gun guncellenmemisti; beklenti burada duzeltildi.
    """
    o = Mission1Orchestrator()
    cmds = o.decide(_inp(S_ROTATE, 0))
    assert len(cmds) == 1
    assert isinstance(cmds[0], FormationTargetCmd)
    assert cmds[0].use_current_centroid       # oldugun yerde kal
    assert not cmds[0].rotate_towards_target  # hedef yok, donme
    assert not o.qr_ready


def test_first_rotate_targets_next_qr():
    """İlk ROTATE önce dizilişi KORUR, sonra hedefe döndürür."""
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
    """Eğim, RİJİT (dondurulmuş) diziliş üzerinde de uygulanmaya devam eder."""
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


# --- RETURN_HOME baslik dondurma (2 Eylul saha olayi) --------------------
# Olay: eve donuste baslik bearing(centroid -> home) ile kuruluyordu. Suru
# eve yaklastikca vektor kisalir, yon tanimsizlasir ve DONER. Sahada
# olculdu: merkez (4,4;0,6) -> (0,0;0,0) giderken baslik -106 -> -169
# derece, 5 saniyede 63 derece. Slotlar basliga gore donduğu icin ylp00
# komsusunun uzerine suruklendi ve ucus elle kesildi.

def _return_home_basliklari(o, noktalar):
    """Verilen centroid dizisi icin RETURN_HOME basliklarini toplar."""
    cikan = []
    for c in noktalar:
        for cmd in o.decide(_inp(S_RETURN_HOME, 0, centroid=c)):
            if isinstance(cmd, FormationTargetCmd):
                cikan.append(cmd.heading_deg)
    return cikan


def test_return_home_baslik_donmuyor():
    """Eve yaklasirken baslik SABIT kalir — kalkistaki deger tasinir.

    Merkez sahadaki izi izliyor: (4,4;0,6) -> (0,0;0,0). Eski kodda bu iz
    boyunca baslik -106 -> -169 dereceye kayiyordu (5 sn'de 63 derece).
    Orkestrator emit-once oldugu icin her nokta ayri bir ornekle olculuyor.
    """
    iz = [(4.4, 0.6, -10.0), (3.0, 0.4, -10.0), (1.5, 0.2, -10.0),
          (0.4, 0.05, -10.0), (0.0, 0.0, -10.0)]
    basliklar = []
    for c in iz:
        o = _ready_orch()
        o.decide(OrchestratorInput(
            mission_state=S_TAKEOFF, qr_step=0, is_leader=True,
            agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
            home=_HOME, swarm_yaw_deg=30.0,
        ))
        basliklar += _return_home_basliklari(o, [c])
    assert len(basliklar) == len(iz)
    assert max(basliklar) - min(basliklar) == 0.0, f'baslik dondu: {basliklar}'
    assert basliklar[0] == 30.0, f'kalkis basligi tasinmadi: {basliklar[0]}'
    # Baslik artik centroid'den TUREMIYOR: eski formul bu izde ~-172 derece
    # verirdi, yeni deger kalkistan gelen 30 derece. (Sahadaki 63 derecelik
    # salinim merkez eve COK yaklasinca, vektor sifira giderken olusuyordu;
    # duz bir izde eski formul de sabit gorunur — bu yuzden olcut "eski
    # deger degismiyor mu" degil, "yeni deger ondan bagimsiz mi".)
    eski_formul = math.degrees(
        math.atan2(_HOME[1] - iz[0][1], _HOME[0] - iz[0][0]))
    assert abs(basliklar[0] - eski_formul) > 90.0


def test_return_home_snapshot_yoksa_eski_yola_duser():
    """Kalkis hic gorulmediyse davranis degismez (sessiz None yok)."""
    o = _ready_orch()
    h = _return_home_basliklari(o, [(4.4, 0.6, -10.0)])
    assert len(h) == 1
    beklenen = math.degrees(math.atan2(_HOME[1] - 0.6, _HOME[0] - 4.4))
    # Baslik artik % 360 ile normalize ediliyor (-172.23 == 187.77): aci
    # karsilastirmasi SARMAYI hesaba katmali, yoksa ayni yon "360 derece
    # fark" gorunur.
    fark = abs((h[0] - beklenen + 180.0) % 360.0 - 180.0)
    assert fark < 1e-9, f'baslik {h[0]} != {beklenen}'


def test_kalkis_basligi_bir_kez_alinir():
    """Snapshot ilk kalkista donar; sonraki tick'ler onu DEGISTIRMEZ."""
    o = _ready_orch()
    for yaw in (30.0, 95.0, -170.0):
        o.decide(OrchestratorInput(
            mission_state=S_TAKEOFF, qr_step=0, is_leader=True,
            agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
            home=_HOME, swarm_yaw_deg=yaw,
        ))
    h = _return_home_basliklari(o, [(4.4, 0.6, -10.0)])
    assert h[0] == 30.0, f'snapshot ezildi: {h[0]}'


# --- Operator ucus profili (2 Eylul gecesi) -----------------------------
# dagitik kalk -> CIZGI -> QR1 -> gorev -> 180 yaw -> ev -> dikey merdiven
# -> herkes KENDI kalkis noktasina (YAVAS) -> irtifa esitle -> inis.
# Bu testler profilin HER halkasini kilitliyor; biri kirilirsa sürü
# ya formasyona hic gecmez ya da eve donuste ust uste biner.

_FRM_CIZGI = 3
_FRM_CUSTOM = 99


def _profil_orch(**kw):
    """Operator profili yapilandirilmis orkestrator."""
    cfg = dict(gorev_formasyon=_FRM_CIZGI, gorev_aralik_m=7.0,
               donus_yaw_deg=180.0, donus_katman_m=5.0,
               dagilma_hiz_mps=1.0, full_agent_count=3)
    cfg.update(kw)
    o = Mission1Orchestrator(OrchestratorConfig(**cfg))
    o.set_origin(41.0, 29.0)
    o.set_next_target(True, 41.001, 29.0)
    return o


def _kalkis(o, yaw=30.0):
    """Kalkis fazini bir kez isler (diziliş snapshot'lanir)."""
    return o.decide(OrchestratorInput(
        mission_state=S_TAKEOFF, qr_step=0, is_leader=True,
        agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
        home=_HOME, swarm_yaw_deg=yaw))


def _donus(o, t):
    """RETURN_HOME'u t saniyede isler; FormationTargetCmd'leri doner."""
    cmds = o.decide(_inp(S_RETURN_HOME, 0, time_in_state=t))
    return [c for c in cmds if isinstance(c, FormationTargetCmd)]


def test_kalkis_dizilisi_ayri_saklaniyor():
    """QR formasyon dayatsa da kalkis dizilisi KAYBOLMAZ."""
    o = _profil_orch()
    _kalkis(o)
    kayit = dict(o._st.kalkis_ofsetleri)
    assert len(kayit) == 3
    o._st.frozen_offsets = {}          # QR bir formasyon dayatti
    assert o._st.kalkis_ofsetleri == kayit


def test_gorev_formasyonu_kalkistan_sonra_kuruluyor():
    """Kalkistan sonra CIZGI + verilen aralik devreye girer (ROTATE fazi)."""
    o = _profil_orch()
    _kalkis(o)
    assert o._st.formation_type == _FRM_CUSTOM   # kalkista juri dizilisi
    o.decide(_inp(S_ROTATE, 0))
    assert o._st.formation_type == _FRM_CIZGI
    assert o._st.spacing_m == 7.0
    # _assign frozen_offsets'i YENIDEN doldurur — ama artik CIZGI slotlariyla
    # (0,0) / (0,-7) / (0,+7). Kalkis dizilisi kalsaydi formasyon kurulmazdi.
    yanal = sorted(round(o[1], 3) for o in o._st.frozen_offsets.values())
    assert yanal == [-7.0, 0.0, 7.0], f'cizgi slotlari degil: {yanal}'


def test_gorev_formasyonu_kapaliyken_davranis_degismez():
    """Kapali profil -> sartname yolu: baslangic dizilisi korunur."""
    o = _profil_orch(gorev_formasyon=0)
    _kalkis(o)
    o.decide(_inp(S_ROTATE, 0))
    assert o._st.formation_type == _FRM_CUSTOM


def test_donus_fazlari_sirayla_ilerliyor():
    """Yaw -> ev -> merdiven -> dagilma -> esitle."""
    o = _profil_orch()
    _kalkis(o)
    beklenen = [(1.0, 0), (20.0, 1), (46.0, 2), (55.0, 3), (90.0, 4)]
    for t, faz in beklenen:
        o._donus_fazi(_inp(S_RETURN_HOME, 0, time_in_state=t))
        assert o._donus_fazi(_inp(S_RETURN_HOME, 0, time_in_state=t)) == faz, \
            f't={t} icin faz {faz} bekleniyordu'


def test_donus_fazi_emit_once_anahtarinda():
    """Alt faz anahtarda yoksa emit-once sürüyü ilk fazda DONDURUR."""
    o = _profil_orch()
    _kalkis(o)
    a = o._phase_key(_inp(S_RETURN_HOME, 0, time_in_state=1.0))
    b = o._phase_key(_inp(S_RETURN_HOME, 0, time_in_state=20.0))
    assert a != b, 'faz degisti ama anahtar ayni — komut BASTIRILIR'


def test_dagilma_yavas_digerleri_normal():
    """Hiz YALNIZ dagilma bacaginda dusuyor (kafa kafaya gecis)."""
    o = _profil_orch()
    _kalkis(o)
    assert _donus(o, 1.0)[0].max_speed == 0.0     # yaw
    assert _donus(o, 20.0)[0].max_speed == 0.0    # eve donus
    dagilma = _donus(o, 55.0)
    assert dagilma[0].max_speed == 1.0, 'dagilma bacagi YAVAS olmali'
    assert _donus(o, 90.0)[0].max_speed == 0.0    # irtifa esitleme


def test_dikey_merdiven_ayrimi():
    """Merdiven basamaklari birbirinden donus_katman_m kadar ayri."""
    o = _profil_orch()
    _kalkis(o)
    cmd = _donus(o, 55.0)[0]
    z = sorted(off[2] for off in cmd.offsets)
    farklar = [round(z[i + 1] - z[i], 6) for i in range(len(z) - 1)]
    assert all(abs(f - 5.0) < 1e-6 for f in farklar), f'basamaklar: {farklar}'


def test_dagilmada_herkes_KENDI_kalkis_noktasina():
    """CUSTOM tip + kalkis ofsetleri: ofsetler kalkistakiyle ayni."""
    o = _profil_orch()
    _kalkis(o)
    kayit = o._st.kalkis_ofsetleri
    cmd = _donus(o, 90.0)[0]           # faz 4: katmansiz, saf diziliş
    assert cmd.formation_type == _FRM_CUSTOM
    for a, off in zip(_IDS, cmd.offsets):
        bek = kayit[a]
        assert math.hypot(off[0] - bek[0], off[1] - bek[1]) < 1e-6, \
            f'agent {a}: {off[:2]} != {bek[:2]}'


def test_yaw_kapaliyken_eski_davranis():
    """Yaw kapaliyken baslik kalkistaki degerde kalir, yaw fazi YOK."""
    o = _profil_orch(donus_yaw_deg=0.0)
    _kalkis(o, yaw=30.0)
    assert o._donus_fazi(_inp(S_RETURN_HOME, 0, time_in_state=1.0)) == 1
    assert _donus(o, 1.0)[0].heading_deg == 30.0


def test_kurulum_hizi_rotate_komutlarinda():
    """Formasyon kurulumu YAVAS, seyir normal — 3 Eylül operatör isteği.

    O uçuşta dağınık dizilişten çizgiye geçiş ROTA_MAKS_HIZ (3.0 m/s) ile
    koştu ve operatör "çok hızlı yaptılar" dedi. Kurulum tek atımlık bir
    manevra; hızlı olmasının değeri yok, görünürlüğü ise kötü.
    """
    o = _profil_orch(gorev_kurulum_hiz_mps=1.0)
    _kalkis(o)
    cmds = [c for c in o.decide(_inp(S_ROTATE, 0))
            if isinstance(c, FormationTargetCmd)]
    assert cmds, 'ROTATE komut uretmedi'
    for c in cmds:
        assert c.max_speed == 1.0, f'kurulum hizi uygulanmadi: {c.max_speed}'


def test_kurulum_hizi_kapaliyken_degistirmez():
    """0.0 = dokunma; düğümün kendi varsayılanı geçerli kalır."""
    o = _profil_orch(gorev_kurulum_hiz_mps=0.0)
    _kalkis(o)
    cmds = [c for c in o.decide(_inp(S_ROTATE, 0))
            if isinstance(c, FormationTargetCmd)]
    assert cmds
    assert all(c.max_speed == 0.0 for c in cmds)
