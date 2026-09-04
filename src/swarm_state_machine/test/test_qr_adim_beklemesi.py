# Copyright 2026 Yelpence
"""QR alt-adimlari ARASINDA `w` kadar bekleme (4 Eylul 2026).

Sartnamenin QR belgesi `w`'yi "GOREVLER ARASI bekleme suresi" diye
tanimliyor ve sirayi acikca sayiyor:

    1 formasyona gec · 2 w bekle · 3 manevra · 4 w bekle
    5 irtifa         · 6 w bekle · 7 sonraki QR

Yani uc gorevlik pakette `w` UC KEZ uygulanir. Bizde yalnizca SONUNCUSU
vardi (WAIT_AT_QR, ana sartname madde 10); aradaki iki bekleme eksikti —
w=4 icin 12 saniye yerine 4 saniye tutuyorduk.

Neden onemli: hakem her komut edilen durumu gorup puanliyor. Formasyonu
kurup hemen manevraya gecersek o formasyon net tutulmus sayilmayabilir.

Test iki yonu birden kilitliyor:
  * bekleme GERCEKTEN oluyor mu    (yoksa sartname sirasi uygulanmaz)
  * sonunda ILERLIYOR mu           (yoksa gorev QR'da sonsuza takilir)
"""

import time
from types import SimpleNamespace

from swarm_state_machine.mission_fsm.mission_context import MissionContext
from swarm_state_machine.mission_fsm.mission_fsm_node import MissionFsmNode
from swarm_state_machine.mission_fsm.mission_states import (
    MissionState,
    QrTaskStep,
)


def _qr(w=4.0, frm=True, mnv=True, alt=True, leav=False):
    return SimpleNamespace(
        wait_s=w,
        formation_active=frm, maneuver_active=mnv,
        altitude_active=alt, detach_active=leav,
    )


class _Kayitci:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass


def _dugum(qr, adim=QrTaskStep.FORMATION):
    """MissionFsmNode'u __init__ CAGIRMADAN kurar (conftest deseni)."""
    d = object.__new__(MissionFsmNode)
    ctx = MissionContext(agent_ids=[1, 2, 3])
    ctx.current_qr = qr
    ctx.qr_task_step = adim
    ctx.state = MissionState.EXECUTE_QR_TASK
    d._ctx = ctx
    d.get_logger = _Kayitci
    return d, ctx


def test_ARADAKI_adimda_BEKLIYOR():
    """FORMASYON bitince MANEVRAYA hemen gecilmemeli."""
    d, ctx = _dugum(_qr(w=4.0))
    d._advance_qr_step()
    assert ctx.qr_task_step == QrTaskStep.FORMATION, 'beklemeden ilerledi'
    assert ctx.qr_step_bekleme_bitis is not None


def test_bekleme_dolunca_ILERLIYOR():
    """Kilitlenme yok: sure dolunca bir sonraki adima gecmeli."""
    d, ctx = _dugum(_qr(w=4.0))
    d._advance_qr_step()
    ctx.qr_step_bekleme_bitis = time.monotonic() - 0.01   # sure doldu
    d._qr_bekleme_kontrol()
    assert ctx.qr_task_step == QrTaskStep.MANEUVER
    assert ctx.qr_step_bekleme_bitis is None


def test_SON_adimda_EK_BEKLEME_YOK():
    """Son adimdan sonra DONE gelir; oradaki beklemeyi WAIT_AT_QR yapiyor.
    Burada da beklersek sonuncusu CIFT beklenirdi."""
    d, ctx = _dugum(_qr(w=4.0), adim=QrTaskStep.ALTITUDE)
    d._advance_qr_step()
    assert ctx.qr_task_step == QrTaskStep.DONE
    assert ctx.qr_step_bekleme_bitis is None


def test_w_SIFIRSA_davranis_ESKISI():
    """QR bekleme istemiyorsa hicbir sey degismemeli."""
    d, ctx = _dugum(_qr(w=0.0))
    d._advance_qr_step()
    assert ctx.qr_task_step == QrTaskStep.MANEUVER
    assert ctx.qr_step_bekleme_bitis is None


def test_UC_GOREVLIK_pakette_IKI_ara_bekleme():
    """Sartname sirasi: frm -w- mnv -w- alt -> DONE (-w- WAIT_AT_QR)."""
    d, ctx = _dugum(_qr(w=4.0))
    beklemeler = 0
    for _ in range(6):
        onceki = ctx.qr_task_step
        d._advance_qr_step()
        if ctx.qr_step_bekleme_bitis is not None:
            beklemeler += 1
            ctx.qr_step_bekleme_bitis = time.monotonic() - 0.01
            d._qr_bekleme_kontrol()
        if ctx.qr_task_step == QrTaskStep.DONE:
            break
        assert ctx.qr_task_step != onceki, 'adim ilerlemedi'
    assert ctx.qr_task_step == QrTaskStep.DONE
    assert beklemeler == 2, f'aradaki bekleme sayisi {beklemeler}, beklenen 2'


def test_DURUM_DEGISINCE_bekleme_IPTAL():
    """FAILSAFE/RETURN_HOME'a gecilirse bekleme anlamini yitirir.
    Damga kalsaydi sonraki QR'da yanlis ilerletme yapardi."""
    d, ctx = _dugum(_qr(w=4.0))
    d._advance_qr_step()
    assert ctx.qr_step_bekleme_bitis is not None
    ctx.state = MissionState.RETURN_HOME
    d._qr_bekleme_kontrol()
    assert ctx.qr_step_bekleme_bitis is None
    assert ctx.qr_task_step == QrTaskStep.FORMATION, 'durum disinda ilerletti'


def test_DURUM_GECISI_damgayi_SIFIRLIYOR():
    """Yeni QR'in ilk adimi onceki QR'in damgasini devralmamali.

    `set_state` her gecisde adim durumunu sifirliyor; damga da orada
    temizleniyor. Kalsaydi sonraki QR'in ilk adimi ya hic beklemez ya
    olculemeyecek kadar uzun beklerdi.
    """
    d, ctx = _dugum(_qr(w=4.0))
    d._advance_qr_step()
    assert ctx.qr_step_bekleme_bitis is not None
    ctx.set_state(MissionState.NAVIGATE_TO_QR)
    assert ctx.qr_step_bekleme_bitis is None
