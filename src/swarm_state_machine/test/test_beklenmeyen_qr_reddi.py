# Copyright 2026 Yelpence
"""YOL USTUNDE OKUNAN YABANCI QR GOREVI KACIRTIR — reddedilmeli.

🔴 9 EYLUL 2026, operator sorusu:
"QR1'den QR4'e giderken 3'un ustunden gecse ve onu okusa ne olur?"

OLCULDU: HICBIR SEY ENGELLEMIYORDU. `_on_qr_data` suzgeci yalniz uc seye
bakiyordu — team_id (bizim boru hattimizda HEP esit), decoded/valid, ve
BIR ONCEKI qr_id (tekrar korumasi). Hangi QR'a gidildigine bakan tek
satir yoktu. Sonuc:

    qr_id=3, son kabul 1  ->  KABUL
    ctx.current_qr = QR3          -> gorev paketi ARTIK QR3'unki
    _resolve_next_qr_target(QR3)  -> sonraki hedef QR3'un satirindan

Yani suru QR4'u BIRAKIP bambaska bir rotaya giriyordu ve hicbir yerde
hata gorunmuyordu; YKI'de yalnizca "QR kabul edildi: qr=3" yaziyordu.
Finalde rotayi komple kaybettirecek sinifta bir acik.

KURAL: yalniz GIDILEN QR islenir. Beklenen QR gorev basinda `start_qr`,
sonrasinda son kabul edilen QR'in soyledigi `next_qr`. next_qr=0
(gorev bitti) ise kapi kapanir — donus fazinda okunan QR gorevi
YENIDEN BASLATMAZ.
"""

import inspect

from swarm_state_machine.mission_fsm import mission_fsm_node


def _govde(ad):
    k = inspect.getsource(mission_fsm_node)
    i = k.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = k.find('\n    def ', i + 1)
    return k[i:j if j > 0 else len(k)]


# ------------------------------------------------------------ asil kusur

def test_BEKLENMEYEN_QR_REDDEDILIYOR():
    """🔴 Kusurun ta kendisi: yol ustundeki QR gorevi ele geciriyordu."""
    g = _govde('_on_qr_data')
    assert '_beklenen_qr' in g, (
        'kabul suzgecinde beklenen QR kapisi yok — yol ustunde okunan '
        'yabanci QR gorevi kacirtir (9 Eylul)'
    )
    assert 'return' in g[g.find('_beklenen_qr'):g.find('_beklenen_qr') + 700]


def test_RET_SEBEBI_YAZILIYOR():
    """Sessiz ret, 'QR okundu ama bir sey olmadi' sorusuna donusur."""
    g = _govde('_on_qr_data')
    i = g.find('_beklenen_qr')
    blok = g[i:i + 900]
    assert 'BEKLENMEYEN QR' in blok and 'get_logger' in blok


def test_KAPI_KABULDEN_ONCE():
    """Sira onemli: reddi current_qr atamasindan ONCE olmali."""
    g = _govde('_on_qr_data')
    i_kapi = g.find('_beklenen_qr')
    i_kabul = g.find('self._ctx.current_qr = msg')
    assert 0 < i_kapi < i_kabul, (
        'kapi kabulden SONRA — gorev zaten degismis olur'
    )


def test_BEKLENEN_QR_ILERLIYOR():
    """QR kabul edilince sirada ONUN gosterdigi QR beklenmeli."""
    g = _govde('_resolve_next_qr_target')
    assert '_beklenen_qr' in g and 'qr.next_qr' in g


def test_GOREV_BITINCE_KAPI_KAPANIYOR():
    """next_qr=0 sonrasi okunan QR gorevi YENIDEN BASLATMAMALI."""
    g = _govde('_resolve_next_qr_target')
    i = g.find('_beklenen_qr')
    satir = g[i:i + 200]
    assert 'else 0' in satir or '> 0' in satir


def test_ILK_HEDEF_START_QR():
    """Gorev basinda beklenen QR start_qr olmali."""
    g = _govde('_resolve_initial_target')
    assert '_beklenen_qr' in g and '_start_qr' in g


# --------------------------------------------------- eski korumalar

def test_TEKRAR_KORUMASI_DURUYOR():
    """Ayni QR'in ardisik kareleri hala atlanmali."""
    g = _govde('_on_qr_data')
    assert 'last_accepted_qr_id' in g


def test_GECERSIZ_QR_HALA_ELENIYOR():
    """decoded/valid kapisi kaybolmamali."""
    g = _govde('_on_qr_data')
    assert 'msg.decoded' in g and 'msg.valid' in g
