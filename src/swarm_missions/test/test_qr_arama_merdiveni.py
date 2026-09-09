# Copyright 2026 Yelpence
"""QR okunamayinca denenen irtifa merdiveni INMELIDIR.

8 EYLUL 2026, operator karari: "ilk QR'da yavas yavas irtifa dusurerek
QR okumaya calisacaklar."

NEDEN VAR: merdiven eskiden (12, 10, 18) idi — once YUKARI, sonra asagi,
sonra COK yukari. Iki somut kusuru vardi ve ikisi de hatasizdi:

  ① 18 m basamagi OLCULEN OKUMA TAVANININ USTUNDE (16.64 m, KAMERA.md
    §13). Her turda 18 saniye kesin okunamayacak bir irtifada harcaniyordu.
  ② Varis irtifasi 10 m'ye cekilince merdiven (10, 10, 18) oluyordu:
    ilk basamak varisla AYNI, yani ETKISIZ. Merdiven bir basamagini
    SESSIZCE kaybediyordu.

Ikisi de "hata vermeden yanlis sonuc" sinifi. Bu dosya merdivenin
YONUNU ve UCLARINI kilitliyor.
"""

import math

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE_QR_TASK = 5
TABAN_M = 10.0                    # orchestrator._SEARCH_ALT_FLOOR_M
# KAMERA.md §13 olcumu: wechat kapali okuma tavani. Merdivenin hicbir
# basamagi bunun ustunde OLMAMALI — orada gecirilen sure bos suredir.
OKUMA_TAVANI_M = 16.64

_IDS = [1, 2, 3]
_POS = [(0.0, 0.0, -15.0), (-7.0, 0.0, -15.0), (7.0, 0.0, -15.0)]
_CEN = (0.0, 0.0, -15.0)


def _orch(varis_m=15.0, basamak=3, adim_s=18.0, gecikme_s=8.0):
    o = Mission1Orchestrator(OrchestratorConfig(
        qr_okuma_irtifa_m=varis_m,
        qr_arama_basamak=basamak,
        qr_search_step_s=adim_s,
        qr_recovery_delay_s=gecikme_s,
    ))
    o.set_origin(41.0, 29.0)
    return o


def _inp(t_s, irtifa_m=15.0):
    """Sürü `irtifa_m`'de duruyor (varsayılan: kalkış irtifası).

    🔴 8 Eylül 2026: irtifa artık PARAMETRE. Süpürme saati takip
    hatasına bakıyor (`qr_arama_takip_tavani_m`); uçaklar hep 15 m'de
    sabit tutulursa süpürme tabana inerken hata 5 m'ye çıkar ve saat
    DURUR. Gerçek uçakta böyle olmaz — komutu takip ederler.
    """
    z = -float(irtifa_m)
    return OrchestratorInput(
        mission_state=S_EXECUTE_QR_TASK, qr_step=0, is_leader=True,
        agent_ids=list(_IDS),
        positions=[(x, y, z) for x, y, _z in _POS],
        centroid=(_CEN[0], _CEN[1], z), home=(0.0, 0.0, 0.0),
        time_in_state=t_s,
    )


# ------------------------------------------------------------- merdiven

def test_merdiven_operator_degerleri():
    """15 m varis, 10 m taban, 3 basamak -> 15.0 / 12.5 / 10.0."""
    assert _orch()._arama_merdiveni() == (15.0, 12.5, 10.0)


def test_merdiven_HEP_INER():
    """Yon garantisi: her basamak bir oncekinden ALCAK.

    Eski (12, 10, 18) merdiveni bu sinamada duserdi.
    """
    for varis in (12.0, 15.0, 16.0, 20.0):
        m = _orch(varis_m=varis)._arama_merdiveni()
        assert all(m[i] > m[i + 1] for i in range(len(m) - 1)), m


def test_uclar_varis_ve_taban():
    """Ilk basamak varis irtifasi, son basamak TABAN — arada bosluk yok."""
    m = _orch(varis_m=15.0)._arama_merdiveni()
    assert math.isclose(m[0], 15.0)
    assert math.isclose(m[-1], TABAN_M)


def test_TABANIN_ALTINA_INMEZ():
    """🔴 10 m tabani operator karari; merdiven onu kirmamali."""
    for varis in (10.0, 12.0, 15.0, 30.0):
        assert min(_orch(varis_m=varis)._arama_merdiveni()) >= TABAN_M


def test_OKUMA_TAVANININ_USTUNE_CIKMAZ():
    """Olculen okuma tavaninin (16.64 m) ustunde basamak olmamali.

    Varis irtifasi zaten tavanin altinda secildigi surece merdiven de
    altinda kalir — ustune cikan tek basamak bile turun tamamini bos
    gecirir. Eski 18 m basamagi tam olarak bunu yapiyordu.
    """
    m = _orch(varis_m=15.0)._arama_merdiveni()
    assert max(m) <= OKUMA_TAVANI_M


def test_varis_TABANA_ESITSE_TEK_BASAMAK():
    """Inecek yer yoksa merdiven tek basamak olur; bolme hatasi vermez."""
    assert _orch(varis_m=TABAN_M)._arama_merdiveni() == (TABAN_M,)


def test_varis_TABANIN_ALTINDAYSA_TABANA_KIRPILIR():
    """Yanlis ayar (varis < taban) merdiveni ters cevirmemeli."""
    assert _orch(varis_m=6.0)._arama_merdiveni() == (TABAN_M,)


def test_basamak_sayisi_uygulanir():
    """qr_arama_basamak gercekten basamak sayisini belirler."""
    assert len(_orch(varis_m=15.0, basamak=5)._arama_merdiveni()) == 5
    # 2'nin altina dusurulemez: tek basamakli "merdiven" inis degildir.
    assert len(_orch(varis_m=15.0, basamak=1)._arama_merdiveni()) == 2


# ------------------------------------------------------- kurtarma akisi

def _kurtarma_z(o, t_s):
    """Verilen anda uretilen kurtarma komutunun irtifasi (m); yoksa None.

    Uçakları BİR ÖNCEKİ komuta yerleştirir — yani takip eden bir sürüyü
    canlandırır. Takip kopukluğu ayrı dosyada sınanıyor
    (`test_supurme_takip_korumasi.py`).
    """
    onceki = o._st.search_alt_m
    cmd = o._maybe_qr_recovery(
        _inp(t_s, 15.0 if onceki != onceki else onceki))
    if cmd is None:
        return None
    assert isinstance(cmd, FormationTargetCmd)
    return -cmd.center[2]


def test_GECIKMEDEN_ONCE_KOMUT_YOK():
    """qr_recovery_delay_s dolmadan sürü kipirdamaz."""
    o = _orch()
    assert _kurtarma_z(o, 0.0) is None
    assert _kurtarma_z(o, 7.9) is None


# 🔴 8 EYLUL 2026 — AYRIK BASAMAKLAR BIRAKILDI, SUPURME SUREKLI OLDU.
# Operator sahada gordu ve degistirdi: "bas cekliydi surekli... yavas yavas
# alcalsin, sadece 10 metrede 5 saniye beklesin". Asagidaki uc test eskiden
# basamakli davranisi (8 s -> tam 15.0, ara komut yok) kilitliyordu; artik
# profil sureklidir ve gecikmeden 0.1 sn sonra irtifa 14.95'tir.
# UCLAR ve YON hala burada bekcileniyor — degisen yalniz ARADAKI hareket.
# Profilin kendisi test_qr_arama_supurmesi.py'de kilitli.

def test_zaman_icinde_INEREK_ilerler():
    """Supurme tavandan baslar ve zamanla TABANA iner (yon garantisi)."""
    o = _orch()
    bas = _kurtarma_z(o, 8.1)
    assert bas is not None and abs(bas - 15.0) < 0.2, bas
    # Inis 0.5 m/s: 8 + 10 = 18. sn'de taban.
    assert abs(_kurtarma_z(o, 18.0) - 10.0) < 0.2
    # Tabanda 5 sn beklenir, sonra tirmanis; 33. sn'de yine tavan.
    assert abs(_kurtarma_z(o, 33.0) - 15.0) < 0.2


def test_TABANDA_SURU_SABIT_DURUR():
    """Kamera net kare alsin diye TABANDA duraklanir — tek duraklama orasi.

    Eskiden HER basamakta durulurdu; operator o beklemeleri kaldirtti,
    yalnizca 10 m'deki 5 saniyeyi birakti.
    """
    o = _orch()
    _kurtarma_z(o, 8.1)
    assert abs(_kurtarma_z(o, 18.0) - 10.0) < 0.2      # tabana varis
    assert _kurtarma_z(o, 20.0) is None                # bekleme suruyor
    assert _kurtarma_z(o, 22.5) is None


def test_QR_COZULUNCE_KURTARMA_DURUR():
    """qr_step ilerlediyse supurme islemez (okuma zaten oldu)."""
    o = _orch()
    assert _kurtarma_z(o, 8.1) is not None
    inp = _inp(26.1)
    inp.qr_step = 1
    assert o._maybe_qr_recovery(inp) is None
