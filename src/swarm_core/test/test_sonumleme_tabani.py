# Copyright 2026 Yelpence
"""B3: uzaklasan komsu CEKIM uretiyordu — sonumleme tabani yoktu.

22 AGUSTOS 2026'da olculdu (d0=10 hard=6):

    komsu 2 m/s UZAKLASIRKEN, 6.5 m'de CA cikisi:  +1.34 m/s
                                                    ^ KOMSUYA DOGRU

Yani carpisma onleme, giden komsuyu KOVALIYORDU.

SEBEP: `damp = c_damp * c * dist_scale`. `c` kapanma hizi — yaklasirken +,
uzaklasirken -. Tabansiz birakilinca damp negatif oluyor ve
`f_radial = mag + damp` isaret degistiriyor. `hard` ile `d0` arasinda
kapanma hizi kapisi `mag`'i zaten sifirladigi icin geriye YALNIZ negatif
damp kaliyor -> net cekim.

Klasik yay-sonumleyicide negatif damp DOGRUDUR (mesafeyi KORUMAK icin), ama
burasi mesafe koruma degil carpisma onleme: uzaklasmanin zarari yok, geri
cekmenin anlami yok. Aralik korumasi formation_node'un isi.

21 Agustos ucus kaydindaki ters yonlu kacis satirlari (v=(-0.02,0.15),
v=(-0.04,0.29)) bunun sahadaki iziydi.
"""


from swarm_core.collision_avoidance.ca_core import (
    CaParams,
    CollisionAvoidanceCore,
    NeighborObs,
)

P = CaParams(d0=10.0, hard=6.0, dt=0.05)   # sahadaki degerler


def _kos(d3, kapanma, tik=40):
    """Komsu +X'te d3 metrede; kapanma>0 yaklasiyor, <0 uzaklasiyor."""
    ca = CollisionAvoidanceCore(P)
    ca.reset((0.0, 0.0, 0.0))
    n = NeighborObs(rel_x=d3, rel_y=0.0, rel_z=0.0,
                    rel_vx=-kapanma, rel_vy=0.0, rel_vz=0.0, distance=d3)
    vx = vy = 0.0
    for _ in range(tik):
        (vx, vy, _vz), _risk = ca.compute((0.0, 0.0, 0.0), [n])
    return vx


def test_UZAKLASAN_komsuya_CEKIM_YOK():
    """Asil ariza. Cikis komsuya dogru (+) OLMAMALI."""
    for d3 in (9.0, 8.0, 7.0, 6.5):
        for kapanma in (-0.5, -1.0, -2.0, -4.0):
            vx = _kos(d3, kapanma)
            assert vx <= 1e-6, (
                f'{d3} m, {kapanma} m/s uzaklasirken CA komsuya dogru '
                f'{vx:.3f} m/s veriyor — giden komsuyu kovaliyor'
            )


def test_YAKLASAN_komsuda_itme_BOZULMADI():
    """Duzeltme korumayi zayiflatmamali — asil is bu."""
    for d3, en_az in ((9.0, 0.5), (8.0, 2.0), (7.0, 3.0), (6.5, 3.0)):
        vx = _kos(d3, 1.0)
        assert vx <= -en_az, (
            f'{d3} m yaklasmada itme zayifladi: {vx:.3f} m/s '
            f'(en az {en_az} bekleniyor)'
        )


def test_SERT_KABUK_bozulmadi():
    """d3 <= hard: kapanma hizi ne olursa olsun TAM itme."""
    for kapanma in (-2.0, 0.0, 1.0, 3.0):
        vx = _kos(5.0, kapanma)      # hard=6.0'in ICINDE
        assert vx <= -3.0, (
            f'sert kabukta (5 m) itme yetersiz: {vx:.3f} m/s, '
            f'kapanma={kapanma}'
        )


def test_DURAN_komsu_notr_ya_da_itiyor():
    """Kapanma sifirken cekim olmamali."""
    for d3 in (9.0, 7.0):
        assert _kos(d3, 0.0) <= 1e-6


def test_d0_DISINDA_hicbir_sey_yok():
    for d3 in (10.5, 12.0, 20.0):
        for kapanma in (-2.0, 0.0, 2.0):
            assert abs(_kos(d3, kapanma)) < 1e-9


def test_uzaklasan_komsuda_RISK_de_dusmeli():
    """Cekim gitti; risk bayragi da gereksiz yere acik kalmamali."""
    ca = CollisionAvoidanceCore(P)
    ca.reset((0.0, 0.0, 0.0))
    n = NeighborObs(8.0, 0.0, 0.0, 2.0, 0.0, 0.0, 8.0)   # 2 m/s uzaklasiyor
    for _ in range(40):
        (vx, vy, _vz), risk = ca.compute((0.0, 0.0, 0.0), [n])
    assert abs(vx) < 1e-6 and abs(vy) < 1e-6, 'uzaklasan komsuda komut var'
