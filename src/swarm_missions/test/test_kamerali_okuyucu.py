# Copyright 2026 Yelpence
"""Okuyucu dron KAMERALI ucaktir, en yakin olan degil.

5 EYLUL 2026, operator karari: "sadece ylp00 okuma yapacak".

NEDEN VAR: `_anchor_nearest_to_qr` okuyucuyu GEOMETRIYLE seciyordu — QR'a o
an en yakin dron QR'in ustune cipalaniyordu. Ama kamera TEK UCAKTA (ylp00;
ayni gun ylp02'nin kamerasi ylp00'a takildi). En yakin ucak ylp01/ylp02
cikarsa suru KAMERASIZ bir ucagi QR'in ustune oturtur: QR hic okunmaz ve
hicbir yerde hata gorunmez.

Sabit lider (ylp00 slot 0 = ortada) bunu KISMEN iyilestirir ama GARANTI
etmez: hangi slotun QR'a en yakin dustugu formasyon sekline ve yaklasma
basligina baglidir.

⚠️ IKI YER BIRDEN sinaniyor. Cipalama ve varis tespiti AYNI dronu
gostermek zorunda; ayrilirlarsa cipa ylp00'i QR'a goturur ama varisi baska
bir ucak tetikler ve suru, kamera daha yoldayken EXECUTE'a gecer.
"""

import math

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_NAVIGATE = 4

# Ajan 1 = ylp00 = KAMERALI ve QR'a EN UZAK olan.  Ajan 3 QR'a en yakin.
# Sira bilerek boyle: "en yakin" ile "kamerali" farkli ucak olmazsa test
# eski davranisi da gecer ve hicbir sey kanitlamaz.
_IDS = [1, 2, 3]
_POS = [
    (-20.0, 0.0, -10.0),   # ajan 1 — kamerali, QR'a 20 m
    (-10.0, 0.0, -10.0),   # ajan 2 — QR'a 10 m
    (-2.0, 0.0, -10.0),    # ajan 3 — QR'a 2 m, EN YAKIN
]
_CEN = (-32.0 / 3.0, 0.0, -10.0)
_HOME = (0.0, 0.0, 0.0)
_NED = (0.0, 0.0, -10.0)          # QR burada
_OFFSETS = [(-6.0, 0.0), (0.0, 0.0), (6.0, 0.0)]


def _orch(kamera_ajan_id):
    o = Mission1Orchestrator(OrchestratorConfig(
        kamera_ajan_id=kamera_ajan_id,
        qr_arrival_threshold_m=3.0,
        qr_arrival_stable_ticks=1,
    ))
    o.set_origin(41.0, 29.0)
    # Hedefi ORIGIN'e koyuyoruz: resolve_ned() -> (0, 0), yani _NED.
    # set_next_target cagrilmazsa `_maybe_qr_arrival` daha ilk satirda
    # None doner ve test hicbir sey sinamaz.
    o.set_next_target(True, 41.0, 29.0)
    return o


def _inp(ids=None, positions=None):
    return OrchestratorInput(
        mission_state=S_NAVIGATE, qr_step=0, is_leader=True,
        agent_ids=list(ids if ids is not None else _IDS),
        positions=list(positions if positions is not None else _POS),
        centroid=_CEN, home=_HOME,
    )


# --------------------------------------------------------------- okuyucu

def test_kamerali_ajan_secilir_en_yakin_degil():
    """kamera_ajan_id=1 iken okuyucu ajan 1, QR'a en uzak olsa bile."""
    o = _orch(1)
    assert o._okuyucu_indeks(_inp(), _NED) == 0


def test_kapali_iken_en_yakin_secilir():
    """kamera_ajan_id=0 = ESKI DAVRANIS; regresyon korumasi."""
    o = _orch(0)
    assert o._okuyucu_indeks(_inp(), _NED) == 2


def test_kamerali_ajan_kadroda_yoksa_en_yakina_duser():
    """Kamerali ucak ucmuyorsa gorev DURMAZ, geometriye doner.

    Bilincli secim: okuma garantisi kalmaz ama suru havada asili kalmaz.
    """
    o = _orch(9)                      # kadroda olmayan id
    assert o._okuyucu_indeks(_inp(), _NED) == 2


def test_pozisyon_yokken_none():
    """Konum yoksa okuyucu secilemez; cagiran None'i ele almali."""
    o = _orch(1)
    assert o._okuyucu_indeks(_inp(positions=[]), _NED) is None


# --------------------------------------------------------------- cipalama

def test_cipa_kamerali_ucagi_qr_ustune_koyar():
    """Merkez = QR - ofset(kamerali).  Ajan 1'in ofseti (-6, 0) -> merkez (6, 0)."""
    o = _orch(1)
    ax, ay, _az = o._anchor_nearest_to_qr(_inp(), _NED, _OFFSETS, 0.0)
    assert math.isclose(ax, 6.0, abs_tol=1e-6)
    assert math.isclose(ay, 0.0, abs_tol=1e-6)
    # Merkeze ofseti ekleyince ajan 1 TAM QR'in ustunde olmali.
    assert math.isclose(ax + _OFFSETS[0][0], _NED[0], abs_tol=1e-6)


def test_cipa_kapaliyken_en_yakina_gore():
    """Eski davranis: ajan 3 (ofset (6,0)) QR'a gider -> merkez (-6, 0)."""
    o = _orch(0)
    ax, _ay, _az = o._anchor_nearest_to_qr(_inp(), _NED, _OFFSETS, 0.0)
    assert math.isclose(ax, -6.0, abs_tol=1e-6)


# ------------------------------------------------------------------ varis

def test_varis_mesafesi_kamerali_ucaktan_olculur():
    """En yakin ucak esigin ICINDE ama kamerali DISINDA -> varis YOK.

    Bu, ayrilma senaryosunun ta kendisi: eski kod `min(...)` ile olctugu
    icin ajan 3'un 2 m'sini gorup "vardim" derdi.
    """
    o = _orch(1)
    inp = _inp()
    assert o._maybe_qr_arrival(inp) is None
    assert math.isclose(o._st.last_qr_distance_m, 20.0, abs_tol=1e-6)


def test_varis_kamerali_ucak_gelince_bildirilir():
    """Kamerali ucak esigin icine girince varis BILDIRILIR."""
    o = _orch(1)
    yakin = list(_POS)
    yakin[0] = (-1.0, 0.0, -10.0)      # kamerali ucak QR'in ustunde
    cmd = o._maybe_qr_arrival(_inp(positions=yakin))
    assert cmd is not None
    assert math.isclose(o._st.last_qr_distance_m, 1.0, abs_tol=1e-6)


def test_varis_kapaliyken_en_yakindan_olculur():
    """Regresyon: kamera_ajan_id=0 iken eski davranis aynen kalir."""
    o = _orch(0)
    cmd = o._maybe_qr_arrival(_inp())
    assert cmd is not None                       # ajan 3 esigin icinde
    assert math.isclose(o._st.last_qr_distance_m, 2.0, abs_tol=1e-6)
