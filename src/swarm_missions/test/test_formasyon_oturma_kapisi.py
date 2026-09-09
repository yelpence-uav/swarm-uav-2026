# Copyright 2026 Yelpence
"""QR ADIMI "OTURDU" DEMEDEN ILERLEMEZ — plato+durdu YETMEZ.

🔴 9 EYLUL 2026 03:15, SAHADA OLCULDU.

Yakinsama olcutu iki TUREVSEL sarttan olusuyordu:
    plato  : hata artik iyilesmiyor
    durdu  : ucaklar kipirdamiyor
Ikisi de suru slotundan METRELERCE UZAKTA TAKILDIGINDA da saglanir.
Olculen:

    "Formasyon kuruldu ama slot hatasi buyuk: 8.35 m"
    "Formasyon kuruldu ama slot hatasi buyuk: 8.51 m"

ve adim yine "tamamlandi" sayildi. Iki somut sonucu oldu:

  ① QR1'in 25 m irtifa adimi 10 SANIYEDE bitti sanildi. Komut
    (merkez z=-25.0) 02:47:23'te gitti, 02:47:33'te QR4 bacagiyla
    degistirildi; suru 15.9 m'deyken "25 m yapildi" sayildi.
  ② QR4'e VARIS hic taninmadi. Kamerali ucak (ylp00) hedefinden 5.2 m
    otede asili kaldi, QR4'un ustune ylp01 denk geldi, QR okunmadi.
    Operator "QR4'un uzerinden gecti" diye gordu.

Yani adimlar sirayla "oldu" diye isaretlenirken sahada HICBIRI olmuyordu.

COZUM: QR gorevinde hata GERCEKTEN toleransin altina insin. Kilitlenme
korumasi zaten var (settle_timeout_s): tutmazsa zaman asimina kadar
beklenir, sonra `clean=False` ile ilerlenir ve dugum "slot hatasi buyuk"
diye bagirir. Suru takilip kalmaz, ama "oturdu" yalani biter.

⚠️ KAPSAM: yalniz QR gorevi. Eve donus faz makinesi (yaw -> eve don ->
merdiven -> dagilma) ayni sinyalle ilerliyor; oraya mutlak kapi konunca
her faz 30 sn zaman asimina yaslanir. Rotasyonda ise `progressed` zaten
tolerans kontrolu yapiyor.
"""

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationReachedCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE = 5
S_RETURN = 9
_STEP_FORMATION = 1
_IDS = [1, 2, 3]


def _orch(tol=0.5, timeout=30.0):
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=3, formation_settle_tol_m=tol,
        settle_timeout_s=timeout, settle_window_ticks=3,
        gorev_aralik_m=7.0,
    ))
    o.set_origin(41.0, 29.0)
    # CUSTOM (99) birakilirsa `_assign` mevcut dizilisin FOTOGRAFINI cekiyor
    # ve sekil hatasi tanim geregi ~0 cikiyor — kapi sinanamaz. Gercek bir
    # tip (CIZGI) ve 7 m aralik veriyoruz ki "komut edilen sekil" ile
    # "ucaklarin durdugu yer" ayrisabilsin.
    o._st.formation_type = 3
    o._st.spacing_m = 7.0
    return o


def _inp(t, pos, step=_STEP_FORMATION, state=S_EXECUTE):
    return OrchestratorInput(
        mission_state=state, qr_step=step, is_leader=True,
        agent_ids=list(_IDS), positions=list(pos),
        centroid=(sum(p[0] for p in pos) / 3.0,
                  sum(p[1] for p in pos) / 3.0, -15.0),
        home=(0.0, 0.0, 0.0), time_in_state=t,
    )


def _sabit_dur(o, pos, n=10, t0=0.0, adim=0.5, **kw):
    """Suru KIPIRDAMADAN n tick: plato + durdu saglanir."""
    cikan = []
    for k in range(n):
        c = o._maybe_formation_settled(_inp(t0 + k * adim, pos, **kw))
        if c is not None:
            cikan.append(c)
    return cikan


# ------------------------------------------------------------ asil kusur

def test_BUYUK_HATAYLA_OTURDU_DENMEZ():
    """🔴 Kusurun ta kendisi: 8.5 m hatayla "formasyon kuruldu" deniyordu."""
    o = _orch(timeout=1e6)              # zaman asimi devre disi
    # ucaklar birbirine cok yakin: 7 m arali formasyondan METRELERCE uzak
    pos = [(0.0, 0.0, -15.0), (0.5, 0.0, -15.0), (1.0, 0.0, -15.0)]
    assert not _sabit_dur(o, pos, n=12), (
        'suru slotundan uzakta takiliyken "oturdu" sinyali cikti — '
        'adim bos yere ilerler (9 Eylul: 25 m adimi 10 sn'"'"'de bitti sanildi)'
    )


def test_ZAMAN_ASIMI_KILITLENMEYI_ONLER():
    """Tolerans tutmasa da suru sonsuza kadar beklemez."""
    o = _orch(timeout=2.0)
    pos = [(0.0, 0.0, -15.0), (0.5, 0.0, -15.0), (1.0, 0.0, -15.0)]
    cikan = _sabit_dur(o, pos, n=14, adim=0.5)
    assert cikan, 'zaman asimi ilerletmedi — suru kilitlenir'
    assert isinstance(cikan[0], FormationReachedCmd)
    assert cikan[0].timed_out is True
    assert cikan[0].clean is False, 'buyuk hata "temiz" isaretlenmis'


def test_EVE_DONUS_KAPIDAN_ETKILENMEZ():
    """Donus faz makinesi ayni sinyalle ilerliyor — kapi oraya konmaz."""
    o = _orch(timeout=1e6)
    pos = [(0.0, 0.0, -15.0), (0.5, 0.0, -15.0), (1.0, 0.0, -15.0)]
    # RETURN_HOME'da ayni dagilmis diziliş: sinyal YINE de gelebilmeli
    o._st.donus_faz = 0
    _sabit_dur(o, pos, n=12, state=S_RETURN, step=0)
    # burada sinyal cikmasi ya da faz ilerlemesi olabilir; kritik olan
    # kapinin donus dalina UYGULANMAMASI:
    import inspect
    kaynak = inspect.getsource(Mission1Orchestrator._maybe_formation_settled)
    i = kaynak.find('oturdu = True')
    assert 'if qr_task:' in kaynak[i:i + 120], (
        'mutlak kapi donus/rotasyon dalina da uygulanmis'
    )


def test_KAPI_TOLERANSI_KULLANIYOR():
    """Esik `formation_settle_tol_m` olmali — ikinci bir sabit dogmasin."""
    import inspect
    kaynak = inspect.getsource(Mission1Orchestrator._maybe_formation_settled)
    i = kaynak.find('oturdu =')
    assert 'formation_settle_tol_m' in kaynak[i:i + 260]


def test_GEREKCE_KODDA():
    """Nicin oldugunu bilmeyen biri bu kapiyi 'gereksiz' diye silebilir."""
    import inspect
    kaynak = inspect.getsource(Mission1Orchestrator._maybe_formation_settled)
    assert '8.35' in kaynak and 'TUREVSEL' in kaynak
