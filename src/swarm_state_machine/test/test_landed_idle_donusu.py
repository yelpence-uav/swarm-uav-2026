# Copyright 2026 Yelpence
"""İnen uçak `LANDED`'da KİLİTLENİYORDU — bir daha kalkamıyordu.

🔴 8 EYLÜL 2026, SAHADA ÖLÇÜLDÜ.

Görev başlatıldı; ylp00 ve ylp01 `IDLE → TAKEOFF` yapıp kalktı, **ylp02
hiç kalkmadı.** Uçuş kaydı (`ucus_izle.py`, 666 örnek):

    d3  state = 13 (LANDED)  BASINDAN SONUNA SABIT
        armed = False        hic degismedi
        irtifa 0.10 m        yerden hic kalkmadi
    d1  state IDLE(1) -> TAKEOFF(4)   t+12.2s
    d2  state IDLE(1) -> TAKEOFF(4)   t+12.4s

ZİNCİR
    `_from_landed` yalniz `pending_state == IDLE` ile cikis veriyordu
      -> o alani KIMSE doldurmuyordu
      -> ucak LANDED'da SONSUZA KADAR kaliyordu
    kalkis kapisi ise yalniz IDLE/ARMED tanıyordu
      -> `if ctx.state == AgentState.IDLE: pending_state = ARMING`
      -> LANDED'dan arm HIC istenmiyordu

Yani **bir kez inen ucak bir daha asla kalkamiyordu** ve hicbir yerde
hata gorunmuyordu: "gorev basladi, ucak duruyor."

İKİ KATMAN DÜZELTİLDİ, İKİSİ DE BURADA SINANIYOR:
  ① `_from_landed` disarm + kisa bekleme sonrasi KENDILIGINDEN IDLE'a doner
  ② gorev baslatma kapisi LANDED'i da tanir (ilk katman gecikirse gorev
    sessizce kaybolmasin)
"""

from swarm_state_machine.agent_fsm.agent_context import AgentContext
from swarm_state_machine.agent_fsm.agent_states import AgentState
from swarm_state_machine.agent_fsm import agent_transitions as GEC


def _ctx(**kw):
    c = AgentContext(agent_id=3)
    c.state = AgentState.LANDED
    c.armed = False
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _yaslandir(ctx, sn):
    """Duruma girişi `sn` saniye geriye alır (saat beklemeden)."""
    ctx.state_entry_time -= sn


# ------------------------------------------------------ asil kusur

def test_LANDED_KENDILIGINDEN_IDLE_A_DONER():
    """🔴 Kusurun ta kendisi: eskiden burada sonsuza kadar kalınıyordu."""
    c = _ctx()
    _yaslandir(c, GEC._LANDED_IDLE_BEKLEME_S + 1.0)
    assert GEC._from_landed(c) == AgentState.IDLE


def test_BEKLEME_DOLMADAN_DONMEZ():
    """Disarm ile 'gerçekten oturdu' arasında pay olmalı."""
    c = _ctx()
    _yaslandir(c, GEC._LANDED_IDLE_BEKLEME_S - 1.0)
    assert GEC._from_landed(c) is None


def test_ARMLIYKEN_IDLE_A_DONMEZ():
    """Pervaneler dönerken IDLE'a geçmek kalkış kapısını açık bırakırdı."""
    c = _ctx(armed=True)
    _yaslandir(c, 60.0)
    assert GEC._from_landed(c) is None


def test_ACIK_ISTEK_HALA_CALISIYOR():
    """`pending_state` ile açık geçiş yolu korunmalı (geriye uyum)."""
    c = _ctx()
    c.pending_state = AgentState.IDLE
    assert GEC._from_landed(c) == AgentState.IDLE
    c2 = _ctx()
    c2.pending_state = AgentState.STANDBY
    assert GEC._from_landed(c2) == AgentState.STANDBY


def test_STANDBY_ONCELIKLI():
    """Pasife alma isteği, kendiliğinden IDLE dönüşünü EZMELİ."""
    c = _ctx()
    c.pending_state = AgentState.STANDBY
    _yaslandir(c, 60.0)
    assert GEC._from_landed(c) == AgentState.STANDBY


# ------------------------------------------------- ikinci katman

def test_GOREV_BASLATMA_KAPISI_LANDED_I_TANIYOR():
    """Kalkış kapısı LANDED'ı tanımalı — kaynakta doğrudan sınanıyor.

    Düğüm testi ROS bağlamı ister; burada kritik olan KAPININ VARLIĞI.
    Kaynaktan okumak kırılgan ama alternatifi (tam düğüm kurulumu) bu
    kusurun tekrarını yakalamak için orantısız.
    """
    import inspect
    from swarm_state_machine.agent_fsm import agent_fsm_node
    kaynak = inspect.getsource(agent_fsm_node)
    assert 'if ctx.state == AgentState.LANDED:' in kaynak, (
        'gorev baslatma kapisi LANDED i tanimiyor — inen ucak bir daha '
        'kalkamaz (8 Eylul, ylp02)'
    )
