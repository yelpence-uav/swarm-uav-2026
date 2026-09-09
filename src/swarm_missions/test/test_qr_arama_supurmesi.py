# Copyright 2026 Yelpence
"""QR arama supurmesi SUREKLI olmali — yalniz TABANDA beklenir.

🔴 8 EYLUL 2026, SAHADA OLCULDU, OPERATOR KARARI.

Gorev 1 ucusunda sürü QR1'in ustunde su profili izledi (ucus_izle.py):

    t= 37-55  15.4 m  SABIT
    t= 58-64  -> 13.0 m        (basamak 1)
    t= 64-73  13.0 m  SABIT    9 sn hareketsiz
    t= 76-82  -> 10.4 m        (basamak 2 = taban)
    t= 82-91  10.4 m  SABIT    9 sn hareketsiz
    t= 94-103 -> 15.5 m        BASA 5 METRELIK SICRAMA
    t=112-121 -> 13.0 m        devir bastan

Operator: "in kalk yaptilar surekli... bas cekliydi surekli... yavas
yavas alcalsin, sadece 10 metrede 5 saniye beklesin, onun disinda
bekleme yapmasin, smooth insin ciksin."

YENI PROFIL — ucgen dalga:
    tavan -> taban   sabit hizla (qr_arama_dikey_hiz_mps)
    tabanda           qr_arama_taban_bekleme_s kadar SABIT  <- TEK BEKLEME
    taban -> tavan   ayni sabit hizla
    ve bastan.

Bu dosya profili KILITLIYOR: ara bekleme yok, sicrama yok, tabanda
bekleme var. Ucları `_arama_merdiveni` belirlemeye devam ediyor
(test_qr_arama_merdiveni.py onlari ayrica bekciliyor).
"""

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE_QR_TASK = 5
TAVAN_M = 15.0
TABAN_M = 10.0                    # orchestrator._SEARCH_ALT_FLOOR_M
HIZ = 0.5
BEKLE_S = 5.0
INIS_S = (TAVAN_M - TABAN_M) / HIZ            # 10.0 sn
DEVIR_S = INIS_S * 2.0 + BEKLE_S              # 25.0 sn

_IDS = [1, 2, 3]
_POS = [(0.0, 0.0, -15.0), (-7.0, 0.0, -15.0), (7.0, 0.0, -15.0)]
_CEN = (0.0, 0.0, -15.0)


def _orch(varis_m=TAVAN_M, hiz=HIZ, bekle_s=BEKLE_S, gecikme_s=8.0):
    o = Mission1Orchestrator(OrchestratorConfig(
        qr_okuma_irtifa_m=varis_m,
        qr_arama_dikey_hiz_mps=hiz,
        qr_arama_taban_bekleme_s=bekle_s,
        qr_recovery_delay_s=gecikme_s,
    ))
    o.set_origin(41.0, 29.0)
    return o


def _inp(t_s):
    return OrchestratorInput(
        mission_state=S_EXECUTE_QR_TASK, qr_step=0, is_leader=True,
        agent_ids=list(_IDS), positions=list(_POS),
        centroid=_CEN, home=(0.0, 0.0, 0.0), time_in_state=t_s,
    )


def _profil(o, n=None, dt=0.2):
    """Bir devir boyunca (t, irtifa) ornekleri."""
    adet = n if n is not None else int(DEVIR_S / dt) + 1
    return [(i * dt, o._arama_profili(i * dt)) for i in range(adet)]


# --------------------------------------------------------- asil istek

def test_TABAN_DISINDA_BEKLEME_YOK():
    """🔴 Kusurun ta kendisi: eskiden HER basamakta bekleniyordu."""
    o = _orch()
    duran = [(t, a) for t, a in _profil(o, dt=0.2)
             if abs(a - TABAN_M) > 0.05 and abs(a - o._arama_profili(t + 0.2)) < 1e-6]
    assert not duran, f'taban disinda duraklama var: {duran[:5]}'


def test_TABANDA_5_SANIYE_BEKLIYOR():
    """Operatorun tek istedigi bekleme: 10 m'de 5 saniye."""
    o = _orch()
    dt = 0.1
    tabanda = [t for t, a in _profil(o, n=int(DEVIR_S / dt) + 1, dt=dt)
               if abs(a - TABAN_M) < 1e-6]
    assert tabanda, 'tabana hic inilmiyor'
    sure = max(tabanda) - min(tabanda)
    assert abs(sure - BEKLE_S) < 0.25, f'tabanda {sure:.2f} sn beklendi'


def test_SICRAMA_YOK_SUREKLI():
    """Ardisik ornekler arasi adim, hiz x dt kadar olmali — sicrama yok."""
    dt = 0.2
    o = _orch()
    ornek = _profil(o, n=int(DEVIR_S * 3 / dt), dt=dt)
    for (t0, a0), (t1, a1) in zip(ornek, ornek[1:]):
        assert abs(a1 - a0) <= HIZ * dt + 1e-6, (
            f't={t0:.1f} -> {t1:.1f} arasinda {abs(a1 - a0):.2f} m sicrama')


# ------------------------------------------------------- profil sekli

def test_TAVANDAN_BASLAR_TABANA_INER():
    o = _orch()
    assert abs(o._arama_profili(0.0) - TAVAN_M) < 1e-6
    assert abs(o._arama_profili(INIS_S) - TABAN_M) < 1e-6


def test_BEKLEMEDEN_SONRA_TIRMANIR_VE_TAVANA_DONER():
    o = _orch()
    assert abs(o._arama_profili(INIS_S + BEKLE_S) - TABAN_M) < 1e-6
    assert o._arama_profili(INIS_S + BEKLE_S + 2.0) > TABAN_M
    assert abs(o._arama_profili(DEVIR_S) - TAVAN_M) < 1e-6


def test_TAVANDA_BEKLEME_YOK():
    """Tepede duraklamak bos vakittir — devir hemen yeniden baslar."""
    o = _orch()
    hemen_once = o._arama_profili(DEVIR_S - 0.2)
    tepe = o._arama_profili(DEVIR_S)
    hemen_sonra = o._arama_profili(DEVIR_S + 0.2)
    assert hemen_once < tepe and hemen_sonra < tepe


def test_DEVIR_TEKRARLAR():
    o = _orch()
    for t in (0.0, 3.7, INIS_S, INIS_S + 2.0, 21.4):
        assert abs(o._arama_profili(t) - o._arama_profili(t + DEVIR_S)) < 1e-6


def test_UCLAR_MERDIVENDEN_GELIYOR():
    """Tek kaynak: varis irtifasi degisince profil kendiliginden uyar."""
    for varis in (12.0, 15.0, 20.0):
        o = _orch(varis_m=varis)
        m = o._arama_merdiveni()
        assert abs(o._arama_profili(0.0) - m[0]) < 1e-6
        en_dusuk = min(o._arama_profili(i * 0.1) for i in range(400))
        assert abs(en_dusuk - m[-1]) < 1e-6


def test_INECEK_YER_YOKSA_TABANDA_KALIR():
    """Varis tabana esitse bolme hatasi degil, sabit taban donmeli."""
    o = _orch(varis_m=TABAN_M)
    assert all(abs(o._arama_profili(t * 0.5) - TABAN_M) < 1e-6
               for t in range(40))


def test_HIZ_AYARI_PROFILI_DEGISTIRIR():
    """Hiz iki katina cikinca inis suresi yariya inmeli."""
    o = _orch(hiz=1.0)
    assert abs(o._arama_profili((TAVAN_M - TABAN_M) / 1.0) - TABAN_M) < 1e-6


# ------------------------------------------------- tuketici davranisi

def test_RAMPADA_KOMUT_AKAR_TABANDA_TEK_KOMUT():
    """Inis boyunca yeni hedef uretilmeli; tabandaki 5 sn'de mesh bosa
    doldurulmamali (irtifa sabit -> tek komut)."""
    o = _orch()
    gecikme = 8.0
    def kos(t0, t1, dt=0.2):
        n = 0
        t = t0
        while t <= t1:
            for c in o.decide(_inp(gecikme + t)):
                if isinstance(c, FormationTargetCmd):
                    n += 1
            t += dt
        return n
    inis = kos(0.0, INIS_S - 0.4)
    tabanda = kos(INIS_S + 0.4, INIS_S + BEKLE_S - 0.4)
    assert inis >= 10, f'inis boyunca yalniz {inis} komut — surekli degil'
    assert tabanda <= 1, f'tabanda {tabanda} komut — mesh bosa dolduruluyor'
