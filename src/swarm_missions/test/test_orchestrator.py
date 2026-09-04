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


def test_navigate_irtifa_referansi_mandallanir():
    """NAVIGATE komut irtifasi OLCUMU TAKIP ETMEZ — bacak basinda mandallanir.

    4 Eylul 2026 sahada olculdu (ylp00). `_anchor_nearest_to_qr` z olarak
    `inp.centroid[2]`yi — yani O ANKI OLCULEN irtifayi — donduruyordu ve
    `use_current_altitude=False` oldugu icin bu deger dogrudan KOMUT
    oluyordu. Komut olcumun kopyasi olunca ortada REFERANS kalmaz: ucak
    dustugunde dusmus deger yeni hedef olur, geri cekecek kuvvet kalmaz.

    NOT: emit-once (_phase_key) NAVIGATE komutunu bacak basina BIR KEZ
    urettigi icin test `_on_navigate` fonksiyonunu DOGRUDAN cagirir —
    yoksa ikinci cagri bastirilir ve test degisikligi hic gormez.
    """
    o = _ready_orch()
    c0 = o._on_navigate(_inp(S_NAVIGATE, 0))[0].center
    assert abs(c0[2] - _CEN[2]) < 1e-6, 'bacak basinda mandallanmali'

    # Ucak 2 m suzuldu: NED z BUYUR (irtifa duser).
    suzulmus = (_CEN[0], _CEN[1], _CEN[2] + 2.0)
    c1 = o._on_navigate(_inp(S_NAVIGATE, 0, centroid=suzulmus))[0].center
    assert abs(c1[2] - _CEN[2]) < 1e-6, \
        'komut olcumu takip etti — suzulme kendini besliyor'

    # Bacak bitince (NAVIGATE disi bir tick) mandal duser.
    o.decide(_inp(S_ROTATE, 0))
    c2 = o._on_navigate(_inp(S_NAVIGATE, 0, centroid=suzulmus))[0].center
    assert abs(c2[2] - suzulmus[2]) < 1e-6, \
        'yeni bacak o anki irtifayi yeniden mandallamali'


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
    """Eve yaklasirken baslik SABIT kalir — GIRISTE bir kez mandallanir.

    2 Eylul saha olayi: baslik HER TICK bearing(centroid -> home) ile
    hesaplaniyordu; merkez (4,4;0,6) -> (0,0;0,0) giderken vektor kisalip
    yon tanimsizlasti ve baslik -106 -> -169 dereceye kaydi (5 SANIYEDE 63
    DERECE). Slotlar basliga gore dondugu icin 7 m yaricaptaki ucak yay
    cizerek supuruldu; operator PosCtl'e alip elle indirdi.

    Duzeltme "hic hesaplama" degil, "BIR KEZ hesapla": vektor EN UZUNKEN
    olculur ve mandallanir. Bu test ayni orkestratoru izin tamami boyunca
    surdurur — eski kod burada kayardi.
    """
    iz = [(4.4, 0.6, -10.0), (3.0, 0.4, -10.0), (1.5, 0.2, -10.0),
          (0.4, 0.05, -10.0), (0.0, 0.0, -10.0)]
    o = _ready_orch()
    o.decide(OrchestratorInput(
        mission_state=S_TAKEOFF, qr_step=0, is_leader=True,
        agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
        home=_HOME, swarm_yaw_deg=30.0,
    ))
    basliklar = []
    for k, c in enumerate(iz):
        basliklar += [cmd.heading_deg for cmd in
                      o.decide(_inp(S_RETURN_HOME, 0, time_in_state=float(k),
                                    centroid=c))
                      if isinstance(cmd, FormationTargetCmd)]
    assert basliklar, 'hic komut uretilmedi'
    assert max(basliklar) - min(basliklar) == 0.0, f'baslik dondu: {basliklar}'

    # Mandallanan deger, GIRIS anindaki ev yonu olmali (kalkis basligi degil).
    beklenen = math.degrees(
        math.atan2(_HOME[1] - iz[0][1], _HOME[0] - iz[0][0])) % 360.0
    fark = abs((basliklar[0] - beklenen + 180.0) % 360.0 - 180.0)
    assert fark < 1e-9, f'baslik {basliklar[0]} != ev yonu {beklenen}'


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
    """Kalkis snapshot'i ilk kalkista donar; sonraki tick'ler DEGISTIRMEZ.

    Bu deger eve donus BASLIGI icin artik kullanilmiyor (o ev yonunden
    turuyor) ama DAGILMA fazi hala buna bagli: kalkis dizilisi bu basligin
    cercevesinde saklaniyor.
    """
    o = _ready_orch()
    for yaw in (30.0, 95.0, -170.0):
        o.decide(OrchestratorInput(
            mission_state=S_TAKEOFF, qr_step=0, is_leader=True,
            agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
            home=_HOME, swarm_yaw_deg=yaw,
        ))
    assert o._st.kalkis_heading_deg == 30.0, (
        f'snapshot ezildi: {o._st.kalkis_heading_deg}')


# --- Operator ucus profili (2 Eylul gecesi) -----------------------------
# dagitik kalk -> CIZGI -> QR1 -> gorev -> 180 yaw -> ev -> dikey merdiven
# -> herkes KENDI kalkis noktasina (YAVAS) -> irtifa esitle -> inis.
# Bu testler profilin HER halkasini kilitliyor; biri kirilirsa sürü
# ya formasyona hic gecmez ya da eve donuste ust uste biner.

_FRM_CIZGI = 3
_FRM_CUSTOM = 99


def _profil_orch(**kw):
    """Operator profili yapilandirilmis orkestrator."""
    # donus_yaw_deg ARTIK 0: donus miktari ev yonunden kendiliginden cikiyor
    # (3 Eylul). Bu alan yalnizca EK ofset; uretimde de 0 (ucus_ayarlari).
    cfg = dict(gorev_formasyon=_FRM_CIZGI, gorev_aralik_m=7.0,
               donus_yaw_deg=0.0, donus_katman_m=5.0,
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


# UZAK FIKSTUR: eve donus basligi artik bearing(centroid -> home) ile
# mandallaniyor ve ev vektoru _DONUS_EV_MIN_M'den (3 m) kisaysa yon
# TURETILMIYOR (63 derece/5 sn tuzagi). _CEN eve 2 m uzakta oldugu icin o
# fikstur yeni yolu hic denemiyordu. Bu fikstur ayni goreli geometriyi
# 30 m kuzeye tasiyor: ev tam GUNEYDE, yani bearing = 180.
_POS_UZAK = [(30.0, 0.0, -10.0), (33.0, -3.0, -10.0), (33.0, 3.0, -10.0)]
_CEN_UZAK = (32.0, 0.0, -10.0)


def _inp_uzak(state, step, time_in_state=0.0, centroid=None, home=_HOME):
    """Uzak fikstur icin OrchestratorInput."""
    return OrchestratorInput(
        mission_state=state, qr_step=step, is_leader=True,
        agent_ids=list(_IDS), positions=list(_POS_UZAK),
        centroid=centroid or _CEN_UZAK, home=home,
        time_in_state=time_in_state,
    )


def _faza_getir(o, faz, t=0.0):
    """RETURN_HOME'u istenen alt faza getirir.

    (o fazin FormationTargetCmd'leri, o anki t) doner. Komutlari BURADAN
    almak zorunlu: orkestrator emit-once, yani ayni faz icin ikinci kez
    decide cagirmak BOS liste doner.
    """
    cmds = o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=t))
    guvenlik = 0
    while o._st.donus_faz < faz:
        o._st.donus_settled = True
        t += 1.0
        cmds = o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=t))
        guvenlik += 1
        assert guvenlik < 20, 'faz ilerlemiyor'
    return [c for c in cmds if isinstance(c, FormationTargetCmd)], t


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


def test_donus_fazlari_YAKINSAMAYLA_sirayla_ilerliyor():
    """Yaw -> ev -> merdiven -> dagilma -> esitle; her adim yakinsamayla."""
    o = _profil_orch()
    _kalkis(o)
    t = 0.0
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=t))
    assert o._st.donus_faz == 0, 'yaw fazinda baslamaliydi'
    for beklenen in (1, 2, 3, 4):
        o._st.donus_settled = True
        t += 1.0
        o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=t))
        assert o._st.donus_faz == beklenen, (
            f'yakinsama sonrasi faz {beklenen} bekleniyordu')


def test_faz_YAKINSAYINCA_zaman_asimini_BEKLEMEZ():
    """Erken oturursa hemen gecer — bosuna asili durup pil yakmaz."""
    o = _profil_orch()
    _kalkis(o)
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    o._st.donus_settled = True
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=2.0))
    assert o._st.donus_faz == 1, 'yakinsadi ama faz ilerlemedi'


def test_yakinsama_gelmezse_ZAMAN_ASIMI_ilerletir():
    """Yakinsama hic gelmezse takilip kalinmaz — ust sinir devreye girer.

    Sure FAZ SURESI DEGIL, ust sinir: yaw fazi icin 30 sn (180 derecelik
    donus icin olculen 16.7 sn + pay).
    """
    o = _profil_orch()
    _kalkis(o)
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=29.0))
    assert o._st.donus_faz == 0, 'zaman asimi dolmadan ilerledi'
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=30.0))
    assert o._st.donus_faz == 1, 'zaman asimi ilerletmedi'


def test_donus_fazi_emit_once_anahtarinda():
    """Alt faz anahtarda yoksa emit-once sürüyü ilk fazda DONDURUR."""
    o = _profil_orch()
    _kalkis(o)
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    a = o._phase_key(_inp_uzak(S_RETURN_HOME, 0, time_in_state=1.0))
    o._st.donus_settled = True
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=1.0))
    b = o._phase_key(_inp_uzak(S_RETURN_HOME, 0, time_in_state=1.0))
    assert a != b, 'faz degisti ama anahtar ayni — komut BASTIRILIR'


def test_dagilma_yavas_digerleri_normal():
    """Hiz YALNIZ dagilma bacaginda dusuyor (kafa kafaya gecis)."""
    o = _profil_orch()
    _kalkis(o)
    yaw, t = _faza_getir(o, 0)
    assert yaw[0].max_speed == 0.0                    # yaw
    ev, t = _faza_getir(o, 1, t)
    assert ev[0].max_speed == 0.0                     # eve donus
    dag, t = _faza_getir(o, 3, t)
    assert dag[0].max_speed == 1.0, 'dagilma bacagi YAVAS olmali'
    son, t = _faza_getir(o, 4, t)
    assert son[0].max_speed == 0.0                    # irtifa esitleme


def test_dikey_merdiven_ayrimi():
    """Merdiven basamaklari birbirinden donus_katman_m kadar ayri."""
    o = _profil_orch()
    _kalkis(o)
    cmds, _t = _faza_getir(o, 3)
    cmd = cmds[0]
    z = sorted(off[2] for off in cmd.offsets)
    farklar = [round(z[i + 1] - z[i], 6) for i in range(len(z) - 1)]
    assert all(abs(f - 5.0) < 1e-6 for f in farklar), f'basamaklar: {farklar}'


def test_dagilmada_herkes_KENDI_kalkis_noktasina():
    """CUSTOM tip + kalkis ofsetleri: ofsetler kalkistakiyle ayni."""
    o = _profil_orch()
    _kalkis(o)
    kayit = o._st.kalkis_ofsetleri
    cmds, _t = _faza_getir(o, 4)
    cmd = cmds[0]              # faz 4: katmansiz, saf diziliş
    assert cmd.formation_type == _FRM_CUSTOM
    for a, off in zip(_IDS, cmd.offsets):
        bek = kayit[a]
        assert math.hypot(off[0] - bek[0], off[1] - bek[1]) < 1e-6, (
            f'agent {a}: {off[:2]} != {bek[:2]}')


def test_dagilma_KALKIS_basligini_kullanir():
    """Dagilmada baslik DONUS basligi degil, KALKIS basligi olmali.

    kalkis_ofsetleri kalkis basliginin cercevesinde saklaniyor; asagi akista
    formation_node ofseti komutun heading'iyle donduruyor. Donus basligi
    verilseydi diziliş aradaki fark kadar doner ve 180 derecelik donuste iki
    kanat BIRBIRININ kalkis noktasina inerdi.
    """
    o = _profil_orch()
    _kalkis(o, yaw=30.0)
    cmds, _t = _faza_getir(o, 4)
    cmd = cmds[0]
    assert abs(cmd.heading_deg - 30.0) < 1e-9, (
        f'dagilmada baslik {cmd.heading_deg}, kalkis basligi 30 olmaliydi')


def test_donecek_sey_yoksa_yaw_fazi_ATLANIR():
    """Varis basligi zaten ev yonuyse yaw fazi acilmaz (bosuna bekleme)."""
    o = _profil_orch()
    _kalkis(o, yaw=30.0)
    o._st.heading_deg = 180.0          # ev tam guneyde: bearing = 180
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    assert o._st.donus_yaw_gerekli is False
    assert o._st.donus_faz == 1, 'donecek sey yokken yaw fazi acildi'


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
# --- Eve donus acisi: EV YONUNDEN turuyor (3 Eylul operator karari) ------


def test_donus_acisi_EV_YONUNDEN_turetiliyor_180():
    """Ev bacagin TAM TERSINDEyse donus 180 derece olur.

    3 EYLUL, OLCULDU: temel aci LIDERIN KALKIS PUSULASI idi ve buna 180
    ekleniyordu. Lider bacak yonunun tersine bakinca ikisi birbirini yedi:
    bacak 325.6, lider 147.7, komut 327.7 -> QR1'de FIILEN DONULEN 2.1
    DERECE. "180 derece yaw" hic yapilmadi ve hicbir hata gorunmedi.
    """
    o = _profil_orch(donus_yaw_deg=0.0)
    _kalkis(o, yaw=147.7)              # lider bacagin tersine bakiyor
    o._st.heading_deg = 0.0            # QR1'e varis basligi: kuzey
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    # Ev tam guneyde (centroid N+32, home N0) -> bearing 180
    assert abs(o._st.donus_heading_deg - 180.0) < 1e-9
    donulen = abs((o._st.donus_heading_deg - 0.0 + 180.0) % 360.0 - 180.0)
    assert abs(donulen - 180.0) < 1e-9, f'donulen aci {donulen}, 180 olmaliydi'


def test_donus_acisi_EV_YONUNDEN_turetiliyor_90():
    """Ev 90 derece yandaysa donus de 90 derece olur — sabit 180 degil."""
    o = _profil_orch(donus_yaw_deg=0.0)
    _kalkis(o, yaw=147.7)
    o._st.heading_deg = 90.0           # varista doguya bakiyoruz
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    donulen = abs((o._st.donus_heading_deg - 90.0 + 180.0) % 360.0 - 180.0)
    assert abs(donulen - 90.0) < 1e-9, f'donulen aci {donulen}, 90 olmaliydi'


def test_ev_COK_YAKINSA_yon_TURETILMEZ():
    """Vektor kisayken yon tanimsizlasir — eski yola (kalkis basligi) duser.

    2 Eylul'deki 63 derece/5 sn salinimi tam bu bolgede olusmustu.
    """
    o = _profil_orch(donus_yaw_deg=0.0)
    _kalkis(o, yaw=30.0)
    yakin = (1.0, 0.0, -10.0)          # eve 1 m: _DONUS_EV_MIN_M = 3.0 alti
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0, centroid=yakin))
    assert abs(o._st.donus_heading_deg - 30.0) < 1e-9, (
        'ev vektoru kisayken yon ondan turetildi')


# --- "EVE VARDIK" sinyali: yalniz SON fazda -----------------------------

def test_yaw_fazinda_EVE_VARDI_sinyali_URETILMEZ():
    """Ara fazlarda FormationReachedCmd cikmamali.

    mission_fsm `event_formation_reached` gorunce DOGRUDAN LANDING'e
    geciyor. Sinyal her alt fazda uretilseydi suru yaw fazi oturur oturmaz
    -- hala QR1'in ustunde, evden 31 m uzakta -- inise gecerdi.
    """
    from swarm_missions.mission1_dynamic_swarm.orchestrator import (
        FormationReachedCmd,
    )
    o = _profil_orch()
    _kalkis(o)
    o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=0.0))
    assert o._st.donus_faz == 0
    cmds = []
    for k in range(1, 12):             # yakinsama penceresi dolsun
        cmds += o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=float(k)))
    assert not any(isinstance(c, FormationReachedCmd) for c in cmds), (
        'ara fazda "eve vardik" sinyali cikti -> suru QR1 uzerinde inerdi')
    assert o._st.donus_faz >= 1, 'yakinsama fazi ilerletmedi'


def test_SON_fazda_EVE_VARDI_sinyali_URETILIR():
    """Faz 4'te sinyal cikmali; yoksa suru hic inmez (sert timeout bekler)."""
    from swarm_missions.mission1_dynamic_swarm.orchestrator import (
        FormationReachedCmd,
    )
    o = _profil_orch()
    _kalkis(o)
    _c, t = _faza_getir(o, 4)
    cmds = []
    for k in range(1, 12):
        cmds += o.decide(_inp_uzak(S_RETURN_HOME, 0, time_in_state=t + k))
    assert any(isinstance(c, FormationReachedCmd) for c in cmds), (
        'son fazda "eve vardik" sinyali cikmadi -> inis tetiklenmez')


# ===================================================================
# TOPLANMA MERDIVENI (4 Eylul 2026, operator istegi)
#
# Gorev 1'de ucaklari HAKEM yere rastgele koyuyor. Kalkistan sonra herkes
# kendi slotuna giderken yollar kesisebilir: kim nerede duracagi konumdan
# turetiliyor (Macar atama), diziliste hicbir garanti yok.
#
# Merdiven kalkista kurulur, ilk formasyon YATAYDA oturunca kalkar. Iki
# yonlu kilit: acikken ayirma GERCEKTEN var mi, ve kalkarken irtifa
# esitleniyor mu — ikincisi kacirilirsa suru QR'a 5 m'lik katmanlarda
# asili gider ve sartnamenin istedigi formasyon havada BOZUK ucar.
# ===================================================================

def _merdivenli_orch(katman=5.0, **kw):
    kw.setdefault('toplanma_katman_m', katman)
    return _profil_orch(**kw)


def _dz(cmd):
    """Komuttaki ofsetlerin z bilesenleri."""
    return [round(o[2], 3) for o in cmd.offsets]


def _xy(cmd):
    return [(round(o[0], 3), round(o[1], 3)) for o in cmd.offsets]


def test_merdiven_VARSAYILAN_KAPALI():
    """Ayar verilmezse davranis eskisinin AYNISI — irtifalar esit."""
    o = _profil_orch()                       # toplanma_katman_m yok
    cmds = [c for c in _kalkis(o) if isinstance(c, FormationTargetCmd)]
    assert cmds, 'kalkis komutu yok'
    assert len(set(_dz(cmds[0]))) == 1, 'kapaliyken katman olusmus'
    assert not o._st.toplanma_merdiveni


def test_merdiven_KALKISTA_kuruluyor():
    """Ayirma kalkis aninda var — gecisin ortasinda degil."""
    o = _merdivenli_orch()
    cmds = [c for c in _kalkis(o) if isinstance(c, FormationTargetCmd)]
    dz = _dz(cmds[0])
    assert len(set(dz)) == 3, f'uc ayri katman bekleniyordu: {dz}'
    assert o._st.toplanma_merdiveni


def test_merdiven_DETERMINISTIK_kimlik_sirasina_gore():
    """Ucu de AYNI sirayi hesaplamali; yoksa katmanlar cakisir."""
    o = _merdivenli_orch(katman=4.0)
    cmds = [c for c in _kalkis(o) if isinstance(c, FormationTargetCmd)]
    dz = _dz(cmds[0])
    # ids [1,2,3] sirali; NED'de yukari = z KUCULUR
    assert dz == [0.0, -4.0, -8.0], dz


def test_merdiven_YATAYA_DOKUNMUYOR():
    """Ayirma yalniz dikeyde. Yatay bozulursa dizilis snapshot'i gider."""
    duz = _profil_orch()
    mrd = _merdivenli_orch()
    a = [c for c in _kalkis(duz) if isinstance(c, FormationTargetCmd)][0]
    b = [c for c in _kalkis(mrd) if isinstance(c, FormationTargetCmd)][0]
    assert _xy(a) == _xy(b)


def test_merdiven_TOPLANMADA_da_uygulaniyor():
    """Asil risk kalkisda degil, formasyona GECERKEN. Orada da katmanli."""
    o = _merdivenli_orch()
    _kalkis(o)
    cmds = [c for c in o.decide(_inp(S_ROTATE, 0))
            if isinstance(c, FormationTargetCmd)]
    assert cmds
    assert len(set(_dz(cmds[-1]))) == 3, _dz(cmds[-1])


def test_merdiven_ANAHTARDA__emit_once_bastirmasin():
    """Merdiven bayragi emit-once anahtarinda mi.

    🔴 Bayrak _phase_key'de olmazsa merdiven kalktiginda duz komut
    BASTIRILIR ve suru merdivende asili kalir — sessizce. Bu testin
    dusmesi tam olarak o demektir.
    """
    o = _merdivenli_orch()
    _kalkis(o)
    inp = _inp(S_ROTATE, 0)
    k_acik = o._phase_key(inp)
    o._st.toplanma_merdiveni = False
    k_kapali = o._phase_key(inp)
    assert k_acik != k_kapali, 'merdiven bayragi anahtari degistirmiyor'


def test_merdiven_OTURUNCA_kalkiyor_ve_SINYAL_GECIKIYOR():
    """Merdiven once iner, rotasyon-bitti sinyali sonra gider.

    Sinyal merdiven acikken giderse mission_fsm NAVIGATE'e gecer ve suru
    QR'a katmanlarda asili gider. 3 Eylul'de eve donuste birebir bu hata
    vardi.
    """
    o = _merdivenli_orch()
    _kalkis(o)
    o.decide(_inp(S_ROTATE, 0))
    assert o._st.toplanma_merdiveni

    # Yakinsamayi zorla: zaman asimi dali da ayni kapidan geciyor.
    o._st.settle_key_t0 = 0.0
    cmd = o._maybe_formation_settled(
        _inp(S_ROTATE, 0, time_in_state=10_000.0))
    assert cmd is None, 'merdiven acikken rotasyon-bitti sinyali gitti'
    assert not o._st.toplanma_merdiveni, 'merdiven inmedi'


def test_merdiven_indikten_SONRA_sinyal_geliyor():
    """Merdiven indikten sonra sinyal ARTIK gitmeli.

    Kapi tek seferlik olmazsa gorev ROTATE'te sonsuza kadar takilir.
    """
    from swarm_missions.mission1_dynamic_swarm.orchestrator import (
        RotationCompletedCmd,
    )
    o = _merdivenli_orch()
    _kalkis(o)
    o.decide(_inp(S_ROTATE, 0))
    o._st.settle_key_t0 = 0.0
    o._maybe_formation_settled(_inp(S_ROTATE, 0, time_in_state=10_000.0))
    assert not o._st.toplanma_merdiveni

    # Merdiven inince ANAHTAR degisti ve yakinsama sayaci SIFIRDAN
    # basliyor — dogru davranis: duz irtifadaki oturmayi gercekten olcmeli,
    # eski turun zaman asimini devralmamali. Bu yuzden once anahtari kuran
    # bir cagri, sonra zaman asimi.
    o._maybe_formation_settled(_inp(S_ROTATE, 0, time_in_state=10_001.0))
    o._st.settle_key_t0 = 0.0
    cmd = o._maybe_formation_settled(
        _inp(S_ROTATE, 0, time_in_state=20_000.0))
    assert isinstance(cmd, RotationCompletedCmd), cmd


def test_merdiven_indikten_sonra_IRTIFA_ESITLENIYOR():
    """Merdiven kalkinca uretilen ofsetler DUZ olmali."""
    o = _merdivenli_orch()
    _kalkis(o)
    o.decide(_inp(S_ROTATE, 0))
    o._st.toplanma_merdiveni = False
    cmds = [c for c in o.decide(_inp(S_ROTATE, 0, time_in_state=1.0))
            if isinstance(c, FormationTargetCmd)]
    assert cmds, 'merdiven indikten sonra komut uretilmedi'
    assert len(set(_dz(cmds[-1]))) == 1, _dz(cmds[-1])
