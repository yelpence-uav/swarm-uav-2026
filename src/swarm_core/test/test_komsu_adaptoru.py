# Copyright 2026 Yelpence
"""KARAR-01 Test 1 — adaptorun ISARET YONU ve cerceve secimi.

NEDEN BU TEST VAR
`rel` vektorunun yonu ters yazilirsa `ca_core` itmeyi ters cevirir ve ucak
komsusunun USTUNE gider. Bunu ilk kez havada gormek kabul edilemez, o yuzden
adaptor ROS'suz yuklenebilir yazildi ve dogrulama burada, yerde yapiliyor.

Sozlesme: **rel = KOMSU - BEN** (kinematic_fusion_node.py:436 ile ayni,
ca_core.py:98 `away_x = -n.rel_x` bunu varsayiyor).
"""

import math
from types import SimpleNamespace

from swarm_core.collision_avoidance.ca_core import (
    CaParams,
    CollisionAvoidanceCore,
)
from swarm_core.collision_avoidance.komsu_adaptoru import (
    ATLAMA_CERCEVE,
    ATLAMA_GECERSIZ,
    agent_status_to_obs,
)

# Adaptor duck-typing ile calisiyor; gercek AgentStatus'a gerek yok.
_M_PER_DEG_LAT = 111320.0


def _durum(**kw):
    """Varsayilani gecerli olan sahte AgentStatus.

    23 Agustos 2026'da UC ALAN EKLENDI: dikey yol verme icin adaptor artik
    kendi irtifasini `alt_amsl_m - home_alt_amsl_m` ile hesapliyor —
    komsunun mesh'ten gelen degeriyle AYNI FORMUL. Eskiden `pos_z` farki
    aliniyordu ve o iki FARKLI datum'u karistiriyordu (bkz. adaptorun
    DIKEY bolumundeki not).

    `agent_id` de eklendi: dikey rutbe icin gerekli.
    """
    alanlar = {
        'lat_deg': 0.0, 'lon_deg': 0.0,
        # pos_z = -10.0: mesh konvansiyonunda komsunun irtifasi 10 m
        # (NED, yukari negatif) — asagidaki alt_amsl/home ciftiyle AYNI
        # irtifayi anlatiyor. Ikisi tutarsiz birakilirsa iki ucak ayni
        # yerde dururken bile aralarinda 10 m dikey fark GORUNUR ve butun
        # yatay testler sessizce d0'in disina duser.
        'pos_x': 0.0, 'pos_y': 0.0, 'pos_z': -10.0,
        'vel_x': 0.0, 'vel_y': 0.0, 'vel_z': 0.0,
        'xy_valid': True, 'z_valid': True, 'v_xy_valid': True,
        'origin_synced': True, 'state': 0,
        'agent_id': 1,
        # Dikey datum: irtifa = alt_amsl - home_amsl = 10.0 m
        'alt_amsl_m': 1010.0, 'home_alt_amsl_m': 1000.0, 'gps_fix_type': 6,
    }
    alanlar.update(kw)
    return SimpleNamespace(**alanlar)


def test_isaret_yonu_komsu_eksi_ben():
    """Komsu KUZEYDE ise rel_x POZITIF olmali."""
    ben = _durum(pos_x=0.0, pos_y=0.0)
    komsu = _durum(pos_x=10.0, pos_y=0.0)

    obs, neden = agent_status_to_obs(komsu, ben)

    assert neden == ''
    assert obs.rel_x == 10.0, 'rel = komsu - ben olmali'
    assert obs.rel_y == 0.0
    assert math.isclose(obs.distance, 10.0)


def test_itme_komsudan_UZAGA():
    """Zincirin tamami: komsu kuzeyde -> itme GUNEYE (negatif x).

    3 m, yani `hard` (4 m) ICINDE secildi: orada kapi kosulsuz 1.0, itme
    kapanma hizina BAKMADAN cikar. Yon testini hiz kapisindan ayirmak icin.
    """
    ben = _durum(pos_x=0.0, pos_y=0.0)
    komsu = _durum(pos_x=3.0, pos_y=0.0)

    obs, _ = agent_status_to_obs(komsu, ben)
    ca = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
    (vx, _vy, _vz), risk = ca.compute((0.0, 0.0, 0.0), [obs])

    assert risk, 'hard icinde kacinma kosulsuz tetiklenmeli'
    assert vx < 0.0, f'itme GUNEYE olmali, vx={vx} bulundu (isaret TERS!)'


def test_d0_disinda_itme_yok():
    """KARAR-01 Test 1: komsu 10 m'de -> itme yok."""
    ben = _durum()
    komsu = _durum(pos_x=10.0, vel_x=-6.0)   # uzerimize gelse bile

    obs, _ = agent_status_to_obs(komsu, ben)
    ca = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
    (vx, vy, vz), risk = ca.compute((0.0, 0.0, 0.0), [obs])

    assert not risk
    assert (vx, vy, vz) == (0.0, 0.0, 0.0)


def test_d0_icinde_YAKLASAN_komsuya_DIKEY_kacis_var():
    """KARAR-01 Test 1'in 23 Agustos 2026 hali.

    ⚠️ SOZLESME DEGISTI. Eskiden bu test "6 m'de yaklasan komsuya YATAY
    itme" bekliyordu. Artik birincil kacis DIKEY ve yatay itme yalnizca
    `hard` kabugunun icinde aciliyor (operator karari).

    Yani 6 m'de beklenen tepki: dikey VAR, yatay YOK. Ikisi de burada
    kilitleniyor — "kacinma calisiyor mu" sorusu yon degistirdigi icin
    testin de degismesi gerekiyordu, ama SUSMASI degil.
    """
    ben = _durum(agent_id=3)
    komsu = _durum(agent_id=1, pos_x=6.0, vel_x=-3.0)

    obs, _ = agent_status_to_obs(komsu, ben, komsu_id=1)
    ca = CollisionAvoidanceCore(CaParams(
        d0=8.0, hard=4.0, r_min=1.5, agent_id=3, rutbe=1, katman_m=3.0))
    (vx, vy, vz), risk = ca.compute((0.0, 0.0, 0.0), [obs], h_now=10.0)

    assert risk, 'yaklasan komsuya tepki verilmeli'
    assert vz < 0.0, f'DIKEY kacis beklenir (rutbe 1 -> yukari), vz={vz:.3f}'
    assert abs(vx) < 1e-6 and abs(vy) < 1e-6, (
        f'6 m kabuk disinda YATAY itme olmamali: ({vx:.3f}, {vy:.3f})')


def test_DURAN_komsuya_hard_disinda_itme_YOK():
    """TASARIM — `basit_kacinma`dan en buyuk davranis farki. Surpriz olmasin.

    `ca_core.py:120` — `hard` disinda kapi kapanma hizindan turuyor
    (`gate = smoothstep((c - c_dead)/c_ref)`). Duran komsuda c=0, c_dead=0.2
    oldugu icin kapi 0 -> ITME YOK.

    Yani 5-6 m'de asili duran iki ucak birbirini ITMEZ. `basit_kacinma`
    iterdi (yalniz mesafeye bakiyordu). Bu KARAR-01'in bilerek sectigi
    davranis: yaklasma yoksa carpisma da yok, ve gereksiz itme formasyonla
    cekisir. Sert kabuk (4 m) yine kosulsuz calisiyor.
    """
    ben = _durum()
    for mesafe in (5.0, 6.0, 7.0):
        komsu = _durum(pos_x=mesafe)
        obs, _ = agent_status_to_obs(komsu, ben)
        ca = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
        _, risk = ca.compute((0.0, 0.0, 0.0), [obs])
        assert not risk, f'{mesafe} m, duran komsu — itme beklenmiyor'


def test_latlon_origin_farkindan_ETKILENMEZ():
    """Asil sebep: iki ucagin origin'i ayrisiksa pos farki YANILTIR.

    Komsu gercekte 5 m kuzeyde ama kendi pos_x'ini 100 m kaymis bir
    origin'e gore bildiriyor. lat/lon yolu dogru cevabi vermeli.
    """
    ben = _durum(lat_deg=38.6904758, lon_deg=39.1610188, pos_x=0.0)
    komsu = _durum(
        lat_deg=38.6904758 + 5.0 / _M_PER_DEG_LAT,
        lon_deg=39.1610188,
        pos_x=100.0,          # ayrisik origin — TUZAK
    )

    obs, _ = agent_status_to_obs(komsu, ben)

    assert math.isclose(obs.rel_x, 5.0, abs_tol=0.05), (
        f'lat/lon birincil olmali; pos_x kullanilsaydi ~100 cikardi, '
        f'{obs.rel_x:.2f} bulundu')


def test_cerceve_yoksa_komsu_atlanir():
    """lat/lon yok VE origin ayrisik -> sessizce yanlis yone itme, ATLA."""
    ben = _durum(origin_synced=False)
    komsu = _durum(pos_x=5.0, origin_synced=False)

    obs, neden = agent_status_to_obs(komsu, ben)

    assert obs is None
    assert neden == ATLAMA_CERCEVE


def test_gecersiz_konum_atlanir():
    """xy_valid dusukse komsu hic degerlendirilmez."""
    ben = _durum()
    komsu = _durum(pos_x=5.0, xy_valid=False)

    obs, neden = agent_status_to_obs(komsu, ben)

    assert obs is None
    assert neden == ATLAMA_GECERSIZ


def test_kapanma_hizi_itmeyi_ERKEN_tetikler():
    """KARAR-01'in belirleyici gerekcesi: yaklasma hizi hesaba katiliyor.

    Ayni mesafede duran komsu ile uzerimize gelen komsu AYNI tepkiyi
    almamali — `basit_kacinma`nin yapamadigi tam olarak bu.

    ⚠️ MESAFE 7 -> 4.5 m'YE CEKILDI (23 Agustos 2026). Yatay itme artik
    yalnizca `hard` kabugunun icinde acildigi icin 7 m'de her iki komsu da
    sifir tepki aliyor ve test AYRIMI OLCEMEZ hale gelmisti. Olculecek
    ozellik (kapanma hizi itmeyi guclendiriyor mu) DEGISMEDI, yalnizca
    gecerli oldugu bolge daraldi.
    """
    ben = _durum()
    duran = _durum(pos_x=4.5)
    gelen = _durum(pos_x=4.5, vel_x=-6.0)   # bize dogru 6 m/s

    obs_duran, _ = agent_status_to_obs(duran, ben)
    obs_gelen, _ = agent_status_to_obs(gelen, ben)

    # TEK TIK YETMIYOR: ivme siniri (slew) ilk tikte iki cikisi da ayni
    # degere kirpiyor ve fark gorunmuyor. Kararli hale birakiliyor.
    ca1 = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
    ca2 = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
    for _ in range(40):
        (vx_d, vy_d, _), _ = ca1.compute((0.0, 0.0, 0.0), [obs_duran])
        (vx_g, vy_g, _), _ = ca2.compute((0.0, 0.0, 0.0), [obs_gelen])

    assert math.hypot(vx_g, vy_g) > math.hypot(vx_d, vy_d), (
        'yaklasan komsuya daha sert tepki verilmeli')


def test_hiz_gecersizse_hiz_sifir_alinir():
    """v_xy_valid dusukse uydurma hiz kullanilmaz; sert kabuk yine calisir."""
    ben = _durum()
    komsu = _durum(pos_x=3.0, vel_x=-9.0, v_xy_valid=False)

    obs, _ = agent_status_to_obs(komsu, ben)

    assert obs.rel_vx == 0.0

    ca = CollisionAvoidanceCore(CaParams(d0=8.0, hard=4.0, r_min=1.5))
    (vx, _vy, _vz), risk = ca.compute((0.0, 0.0, 0.0), [obs])
    assert risk, 'hard (4 m) icinde tam itme hiza BAKMADAN calismali'
    assert vx < 0.0
