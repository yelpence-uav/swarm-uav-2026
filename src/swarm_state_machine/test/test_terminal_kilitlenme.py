# Copyright 2026 Yelpence
"""TERMINAL DURUM KALICI OLAMAZ — "baslat" hic calismiyordu.

🔴 9 EYLUL 2026 03:45, SAHADA. Operator: "baslat diyorum olmuyor hicbir sey".

ZINCIR
    QR tablosu yayini -> (bu gece eklendi) once GOREV DURDUR
      -> mission_fsm ABORTED
      -> BASLAT yalniz IDLE'dan tetikler
      -> ABORTED -> IDLE donusu `all_agents_landed()` ya da
         `all_agents_in_state(IDLE)` istiyordu
      -> ucaklar PosCtl'de iken agent_fsm otonom gecisleri DURDURUYOR,
         durum UNKNOWN(0) kaliyor
      -> IKI SART DA SAGLANMIYOR -> ABORTED'da SONSUZA KADAR kilit
      -> tek cikis konteyner yeniden baslatmak

Yani "QR gonder + baslat" akisi, kumanda elde tutuldugu HER durumda
kilitleniyordu ve operator dort kez ust uste baslatmayi denedi.

COZUM: terminal durumdan cikis icin ikinci kapi — ajan durumlari
okunamiyorsa IRTIFAYA bakilir. Kimse havada degilse ve terminal durumda
yeterince beklendiyse IDLE'a donulur. HAVADAYKEN DONMEZ.
"""

from swarm_state_machine.mission_fsm import mission_transitions as GEC
from swarm_state_machine.mission_fsm.mission_context import MissionContext
from swarm_state_machine.mission_fsm.mission_states import MissionState


class _Ajan:
    def __init__(self, state=0, pos_z=0.0):
        self.state = state
        self.pos_z = pos_z


def _ctx(durum=MissionState.ABORTED, ajanlar=None, gecen=20.0):
    c = MissionContext(agent_ids=[1, 2, 3])
    c.state = durum
    c.agent_statuses = ajanlar if ajanlar is not None else {
        1: _Ajan(0, 0.05), 2: _Ajan(0, -0.1), 3: _Ajan(0, 0.0)
    }
    c.state_entry_time -= gecen
    return c


# ------------------------------------------------------------ asil kusur

def test_UNKNOWN_DURUMDA_YERDE_IDLE_A_DONER():
    """🔴 Kusurun ta kendisi: durum UNKNOWN iken ABORTED'da kilitleniyordu."""
    assert GEC._from_terminal(_ctx()) == MissionState.IDLE, (
        'ajan durumlari UNKNOWN ve ucaklar yerdeyken terminal durumdan '
        'cikilamadi — "baslat" bir daha asla calismaz (9 Eylul)'
    )


def test_MISSION_COMPLETE_ICIN_DE_GECERLI():
    """Gorev bittiyse de yeniden gorev alinabilmeli."""
    c = _ctx(durum=MissionState.MISSION_COMPLETE)
    assert GEC._from_terminal(c) == MissionState.IDLE


def test_HAVADAYKEN_DONMEZ():
    """🔴 Havadayken "gorev bitti, IDLE'a don" demek TEHLIKELI."""
    havada = {1: _Ajan(0, -12.0), 2: _Ajan(0, -12.0), 3: _Ajan(0, -11.5)}
    assert GEC._from_terminal(_ctx(ajanlar=havada)) is None


def test_TEK_UCAK_HAVADAYSA_DA_DONMEZ():
    """Biri havadayken sürü yeniden gorev almamali."""
    karisik = {1: _Ajan(0, 0.0), 2: _Ajan(0, -9.0), 3: _Ajan(0, 0.1)}
    assert GEC._from_terminal(_ctx(ajanlar=karisik)) is None


def test_ERKEN_DONMEZ():
    """Kurtarma yolu, dogru yola once firsat versin diye gecikmeli."""
    assert GEC._from_terminal(_ctx(gecen=1.0)) is None


def test_NORMAL_YOL_BOZULMADI():
    """LANDED bildiren suru 3 saniyede IDLE'a donmeye devam etmeli."""
    inmis = {1: _Ajan(13, 0.0), 2: _Ajan(13, 0.0), 3: _Ajan(13, 0.0)}
    assert GEC._from_terminal(_ctx(ajanlar=inmis, gecen=4.0)) == MissionState.IDLE


def test_AJAN_YOKSA_TEMKINLI():
    """Veri hic yoksa "havada" varsayilir; kor kurtarma yapilmaz."""
    assert GEC._from_terminal(_ctx(ajanlar={}, gecen=60.0)) is None
