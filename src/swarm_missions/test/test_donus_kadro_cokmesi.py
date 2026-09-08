# Copyright 2026 Yelpence
"""RETURN_HOME'a girince kadro bosaliyordu ve donus fazlari HIC calismiyordu.

🔴 8 EYLUL 2026 — GOREV 1'IN ILK ONBOARD UCUSUNDA OLCULDU.

    1788848379.204  mission1 -> RETURN_HOME komutu (faz 0: yerinde yaw)
    1788848379.233  agent_fsm: IN_SWARM -> RETURN_HOME      (29 ms sonra)
                    ...307 saniye TEK KOMUT YOK...
    mission1.log :  RETURN_HOME home=(17.0,-1.4) centroid=(6.5,-8.5)
                    mesafe=12.7m   -> hic azalmadi

ZINCIR
    FORMATION_ACTIVE_STATES = {IN_SWARM, EXECUTING_TASK}   RETURN_HOME YOK
      -> swarm_fsm_node:720  active_agent_ids = []
      -> mission1_node       agent_ids = []
      -> orchestrator.decide()  `if not inp.agent_ids: return`  (ILK SATIR)
      -> donus faz makinesi (eve don / merdiven / dagilma / inis) HIC KOSMADI

Suru son komutta donup kaldi: merkez QR'in ustunde, heading eve dogru —
yani olduğu yerde yaw yapip bekledi. Operatorun gordugu buydu.

Hicbir yerde hata gorunmedi: kadro bos olmak "hata" degil, sadece
"komut uretme" demekti.

IKI KATMAN DUZELTILDI, IKISI DE BURADA SINANIYOR:
  ① kok neden — `agent_states.FORMATION_ACTIVE_STATES`e RETURN_HOME eklendi
  ② ikinci katman — kadro BASKA bir sebeple sifirlansa da (saglik bayragi,
    bayatlama, mesh) gorev donmasin: son TAM kadroya duselim
"""

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_TAKEOFF = 3
S_NAVIGATE = 4
S_EXECUTE = 5
S_ROTATE = 7
S_RETURN_HOME = 9

# Ucustaki gercek konumlar (mission1.log, 8 Eylul).
_POS = [(14.8, 4.7, -15.0), (20.2, 0.3, -15.0), (18.3, -8.7, -15.0)]
_HOME = (17.0, -1.4, -15.0)
_QR_POS = [(6.5, -8.5, -15.0), (11.9, -13.0, -15.0), (10.0, -22.0, -15.0)]
_QR_CEN = (6.5, -8.5, -15.0)


def _inp(state, pos, cen, t, ids=(1, 2, 3)):
    """Kadro bosken konum listesi de bos gelir — sahada oyle oldu."""
    return OrchestratorInput(
        mission_state=state, qr_step=0, is_leader=True,
        agent_ids=list(ids), positions=list(pos) if ids else [],
        centroid=cen, home=_HOME, time_in_state=float(t), swarm_yaw_deg=99.2,
    )


def _ucusa_hazirla():
    """Kalkis -> rotasyon -> seyir -> QR gorevi; RETURN_HOME'un esigine getirir."""
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=3, kamera_ajan_id=1, gorev_formasyon=0,
        qr_okuma_irtifa_m=15.0, donus_katman_m=5.0,
    ))
    o.set_origin(37.0297209, 37.3113894)
    o.set_next_target(True, 37.02977, 37.31123)
    cen0 = tuple(sum(p[i] for p in _POS) / 3 for i in range(3))
    o.decide(_inp(S_TAKEOFF, _POS, cen0, 0.0))
    o.decide(_inp(S_ROTATE, _QR_POS, _QR_CEN, 1.0))
    o.decide(_inp(S_NAVIGATE, _QR_POS, _QR_CEN, 1.0))
    o.decide(_inp(S_EXECUTE, _QR_POS, _QR_CEN, 1.0))
    return o


def _fazlari_kos(o, kadro):
    """RETURN_HOME'u bastan sona surer; (faz, komut sayisi) doner."""
    komut = 0
    for t in (0.0, 5, 31, 60, 76, 100, 130, 170, 220, 300):
        ids = (1, 2, 3) if t == 0.0 else kadro
        cmds = o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, t, ids))
        komut += sum(1 for c in cmds if isinstance(c, FormationTargetCmd))
    return int(o._st.donus_faz), komut


# ------------------------------------------------------------ asil kusur

def test_KADRO_BOSALSA_DA_DONUS_ILERLER():
    """🔴 Kusurun ta kendisi: kadro bosalinca faz 0'da donup kaliyordu."""
    o = _ucusa_hazirla()
    faz, komut = _fazlari_kos(o, kadro=())
    assert faz >= 4, f'donus faz {faz} de takildi (sahada 0 da takilmisti)'
    assert komut >= 4, f'yalnizca {komut} komut cikti — fazlar islememis'


def test_EVE_DONUS_KOMUTU_GERCEKTEN_EVI_HEDEFLIYOR():
    """Faz 1 merkezi EV olmali. Sahada bu komut hic uretilmedi."""
    o = _ucusa_hazirla()
    o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, 0.0))       # faz 0
    merkezler = []
    for t in (31, 60, 76, 100, 130, 170):
        for c in o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, t, ())):
            if isinstance(c, FormationTargetCmd):
                merkezler.append((round(c.center[0], 1), round(c.center[1], 1)))
    ev = (round(_HOME[0], 1), round(_HOME[1], 1))
    assert ev in merkezler, f'eve donus komutu YOK; uretilenler: {merkezler}'


def test_KADRO_BOSALMASI_GORUNUR():
    """Sessiz yama, yamasizliktan az farkli olurdu — not ve sayac uretilmeli."""
    o = _ucusa_hazirla()
    o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, 0.0))
    o.kadro_notu                                   # tam kadro turunu temizle
    o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, 5.0, ()))
    notu = o.kadro_notu
    assert notu and 'KADRO SIFIRLANDI' in notu
    assert o._st.kadro_bos_sayaci >= 1


# ------------------------------------------------- yedek yol UYGULANMAZ

def test_TAM_KADRO_HIC_GORULMEDIYSE_ESKI_DAVRANIS():
    """Acilista SwarmState bos gelirse hala sessizce cikilmali.

    O kapi ORADA DURUYOR: bos agent_ids ile `compute_slot_offsets`
    total=0 -> ValueError veriyordu. Yedek yol yalnizca bir kez TAM kadro
    gorulduyse aciliyor.
    """
    o = Mission1Orchestrator(OrchestratorConfig(full_agent_count=3))
    o.set_origin(41.0, 29.0)
    assert o.decide(_inp(S_RETURN_HOME, [], _QR_CEN, 0.0, ())) == []
    assert o._st.kadro_bos_sayaci == 0


def test_TAM_KADRO_VARKEN_YEDEK_YOL_ACILMAZ():
    """Kadro doluyken hicbir sey degismemeli."""
    o = _ucusa_hazirla()
    o.decide(_inp(S_RETURN_HOME, _QR_POS, _QR_CEN, 0.0))
    assert o._st.kadro_bos_sayaci == 0


# ------------------------------------------------------ kok neden kilidi

def test_RETURN_HOME_FORMASYON_KUMESINDE():
    """🔴 Kok neden: RETURN_HOME havada ve formasyonda bir durum.

    Kumeden cikarilirsa `swarm_fsm_node` kadroyu bosaltir ve yukaridaki
    butun testler yesil kalsa bile SAHADA ayni ariza geri gelir — cunku
    orkestratore bos kadro ulasir. Kilidi buraya koyuyoruz.
    """
    from swarm_state_machine.agent_fsm.agent_states import (
        FORMATION_ACTIVE_STATES, AgentState,
    )
    assert AgentState.RETURN_HOME in FORMATION_ACTIVE_STATES
    assert AgentState.IN_SWARM in FORMATION_ACTIVE_STATES
    assert AgentState.EXECUTING_TASK in FORMATION_ACTIVE_STATES
    # LANDING BILEREK DISARIDA: orada formasyon surucu degil.
    assert AgentState.LANDING not in FORMATION_ACTIVE_STATES
