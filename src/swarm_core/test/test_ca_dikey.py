# Copyright 2026 Yelpence
"""ca_core DIKEY YOL VERME testleri — 23 Agustos 2026.

NEDEN VAR: dikey kacisin isareti ters yazilirsa ucak komsusunun UZERINE
tirmanir ve bu yerde HICBIR belirti vermez. Ayni sinif hata yatay tarafta
komsu_adaptoru'nun basliginda uzun uzun anlatiliyor; dikeyde de ayni kilidi
kuruyoruz.

ROS GEREKTIRMEZ — ca_core saf Python. Dizustunde kosar:
    python3 -m pytest src/swarm_core/test/test_ca_dikey.py -q
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..'))

from swarm_core.collision_avoidance.ca_core import (  # noqa: E402
    CaParams, CollisionAvoidanceCore, NeighborObs, komsu_yerde_pasif)

KATMAN = 3.0


def _p(agent_id=3, **kw):
    """Test parametreleri: saf dikey kip (operator karari)."""
    varsayilan = dict(
        d0=4.0, hard=2.0, r_min=1.5, katman_m=KATMAN,
        k_dikey=1.0, k_yatay=0.0, k_tan=0.0,
        v_dikey_max=1.5, a_dikey_max=1.0, kp_dikey=0.8,
        hist_m=0.5, dt=0.05, dikey_taban_m=4.0,
        agent_id=agent_id,
    )
    varsayilan.update(kw)
    return CaParams(**varsayilan)


def _komsu(aid, dx=2.0, dy=0.0, rel_z=0.0, vx=0.0, vy=0.0, vz=0.0):
    """rel = KOMSU - BEN. rel_z > 0 -> komsu BENDEN ASAGIDA."""
    return NeighborObs(
        rel_x=dx, rel_y=dy, rel_z=rel_z,
        rel_vx=vx, rel_vy=vy, rel_vz=vz,
        distance=math.sqrt(dx * dx + dy * dy + rel_z * rel_z),
        agent_id=aid,
    )


def _kosturmak(ca, komsu_tanim, h0=10.0, tik=200, vf=(0.0, 0.0, 0.0)):
    """N tik kostur, kendi irtifami entegre et. (h, vz) doner.

    komsu_tanim: [(aid, dx, komsu_MUTLAK_irtifasi), ...]

    🔴 rel_z HER TIK YENIDEN hesaplanir. Ilk yazimda sabit NeighborObs
    veriliyordu ve rel_z hic degismiyordu; hedef `h_now + (katman - rel_z)`
    oldugu icin ucak kendi golgesini kovaliyor ve TAVANA kadar tirmaniyordu
    (13 m beklenirken 16 m). Sahada rel_z tazelenir, bu yuzden o bir test
    kusuruydu — ama tazeleme DURURSA (mesh kopmasi) ayni tirmanmanin
    olusacagini gosterdi. Tavan kelepcesi tam bu yuzden var.
    """
    h = h0
    vz = 0.0
    for _ in range(tik):
        komsular = [
            _komsu(aid, dx=dx, rel_z=h - k_h) for aid, dx, k_h in komsu_tanim
        ]
        (_vx, _vy, vz), _risk = ca.compute(vf, komsular, h_now=h)
        h -= vz * ca.p.dt        # NED: vz negatif = tirmanma = h artar
    return h, vz


# =========================================================================
# ISARET — en pahali hata sinifi
# =========================================================================

def test_ayni_seviyedeki_kucuk_kimlige_YUKARI_kacilir():
    """Komsu ayni irtifada ve kimligi kucuk -> BEN tirmanmaliyim."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    (_vx, _vy, vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=0.0)], h_now=10.0)
    assert risk is True
    assert vz < 0.0, 'NED: tirmanma NEGATIF vz olmali'


def test_capa_dikeyde_KIPIRDAMAZ():
    """En kucuk kimlik capadir: komsusu buyukse dikeyde hicbir sey yapmaz."""
    ca = CollisionAvoidanceCore(_p(agent_id=1))
    (_vx, _vy, vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(3, dx=2.0, rel_z=0.0)], h_now=10.0)
    assert vz == 0.0
    assert risk is False, 'capanin yapacagi bir sey yok -> mudahale yok'


def test_komsu_yukarida_ise_ASAGI_inilir_icinden_gecilmez():
    """Kucuk kimlikli komsu 1 m ustumde: yukari cikmak ONUN ICINDEN gecmek.

    Asagi inmek 2 m, yukari cikmak 4 m — ucuzu ve carpisma yolundan
    gecmeyeni ASAGI.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    # rel_z = ben_h - komsu_h = -1.0  ->  komsu 1 m YUKARIDA
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=-1.0)], h_now=10.0)
    assert vz > 0.0, 'NED: alcalma POZITIF vz olmali'


def test_iki_komsunun_ARASINDA_yeterince_uzaksam_KIPIRDAMAM():
    """Ikisinden de katman kadar uzaksam ortada durmak gecerli cozumdur."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    komsular = [
        _komsu(1, dx=2.0, rel_z=3.5),     # 3.5 m ASAGIMDA
        _komsu(2, dx=2.0, rel_z=-3.5),    # 3.5 m YUKARIMDA
    ]
    (_vx, _vy, vz), _risk = ca.compute((0.0, 0.0, 0.0), komsular, h_now=10.0)
    assert vz == 0.0


# =========================================================================
# KURAL — ne zaman calisir, ne zaman susar
# =========================================================================

def test_zaten_katman_kadar_ayrikken_KOMUT_YOK():
    """3 m dikey ayrik komsuya tirmanmanin anlami yok."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=KATMAN)], h_now=10.0)
    assert vz == 0.0


def test_10_m_ustteki_komsu_icin_13_m_TIRMANILMAZ():
    """Yatayda cakisan ama 10 m dikey ayrik komsu catisma DEGILDIR.

    Naif kural 'kucuk kimligin ustune cik' derse 13 m tirmanmasi gerekirdi.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=0.5, rel_z=-10.0)], h_now=10.0)
    assert vz == 0.0


def test_uzaktaki_komsu_hic_tetiklemez():
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    v, risk = ca.compute(
        (1.0, 0.5, 0.0), [_komsu(1, dx=12.0, rel_z=0.0)], h_now=10.0)
    assert risk is False
    assert v == (1.0, 0.5, 0.0), 'girdi birebir gecmeli'


def test_kimligi_bilinmeyen_komsuya_dikey_uygulanmaz():
    """agent_id=0 = dikey datum kurulamadi. Uydurma yone tirmanma."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(0, dx=2.0, rel_z=0.0)], h_now=10.0)
    assert vz == 0.0


def test_irtifa_bilinmiyorsa_dikey_kapali():
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=0.0)], h_now=None)
    assert vz == 0.0


def test_k_dikey_sifir_eski_davranisi_birebir_korur():
    ca = CollisionAvoidanceCore(_p(agent_id=3, k_dikey=0.0))
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.7), [_komsu(1, dx=2.0, rel_z=0.0)], h_now=10.0)
    assert vz == 0.7, 'gelen dikey hiz degistirilmeden gecmeli'


# =========================================================================
# XY_GUARD KOR NOKTASI — dikeyin ON KOSULU
# =========================================================================

def test_tam_tepedeki_komsu_listeden_DUSMEZ():
    """CA.md B2: eskiden d_xy < 0.3 olan komsu TAMAMEN atlaniyordu.

    Dikey merdivende ust uste gelmek TASARIMIN KENDISI; bu kor nokta
    kapatilmadan dikey acilamaz.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    # Tam tepemde 1 m yukarida, yatayda 10 cm
    (_vx, _vy, vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=0.1, dy=0.0, rel_z=-1.0)], h_now=10.0)
    assert risk is True, 'tam tepedeki komsu GORULMELI'
    assert vz != 0.0, 've bir kacis uretmeli'


# =========================================================================
# RUTBE — uc ucak merdiveni
# =========================================================================

def test_uc_ucak_HEPSINDEN_ayrilir_arada_KALMAZ():
    """drone1 10 m'de, drone2 13 m'de, drone3 10 m'den basliyor.

    🔴 ILK TASARIM BURADA COKTU: komsu komsu yon secilince drone3
    drone1'den 3 m uzaklasip TAM DRONE2'NIN IRTIFASINDA (13.00 m)
    duruyordu — kararli ama carpisma demek olan bir denge.

    Kume kurali: ya hepsinin ustune (16 m, maliyet 6) ya hepsinin altina
    (7 m, maliyet 3). Ucuzu secilir -> 7 m.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    komsular = [
        (1, 2.0, 10.0),      # capa, 10 m'de sabit
        (2, 2.0, 13.0),      # drone2 kendi katmaninda, 13 m'de sabit
    ]
    h, _vz = _kosturmak(ca, komsular, h0=10.0, tik=400)
    assert 6.5 <= h <= 7.5, f'beklenen ~7 m, olculen {h:.2f}'
    assert abs(h - 13.0) >= KATMAN - 0.5, 'drone2 ile ayni katmanda!'
    assert abs(h - 10.0) >= KATMAN - 0.5, 'drone1 ile ayni katmanda!'


def test_ikili_catismada_tek_katman_yeter_ISRAF_YOK():
    """drone3'un karsisinda YALNIZ drone1 varsa 3 m yeter, 6 m degil."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    h, _vz = _kosturmak(ca, [(1, 2.0, 10.0)], h0=10.0, tik=400)
    assert 12.5 <= h <= 13.5, f'beklenen ~13 m, olculen {h:.2f}'


# =========================================================================
# SINIRLAR
# =========================================================================

def test_gorev_tirmanisinda_merdiven_TAKIP_EDER():
    """Capa gorev geregi tirmaniyorsa merdiven onunla birlikte yukselir.

    Eski "catisma basina sabitlenmis tavan" tasarimi bu kaskadi keserdi.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    h = 10.0
    komsu_h = 10.0
    # Suru TOPLUCA tirmaniyor: gorev ikisine de ayni dikey komutu veriyor.
    # (NED: -0.5 = 0.5 m/s tirmanma)
    for _ in range(600):
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, -0.5), [_komsu(1, dx=2.0, rel_z=h - komsu_h)],
            h_now=h)
        h -= vz * ca.p.dt
        komsu_h += 0.5 * ca.p.dt      # capa gorev hiziyla tirmaniyor
    assert komsu_h > 20.0, 'capa gercekten tirmanmis olmali'
    assert abs((h - komsu_h) - KATMAN) < 0.6, (
        f'merdiven gorevle birlikte yukselmedi: ben {h:.2f}, '
        f'capa {komsu_h:.2f}')


def test_taban_engelleyince_YUKARI_secilir_ve_bildirilir():
    """Asagi daha kisa ama irtifa kapisinin altina dusuyor -> yukari."""
    ca = CollisionAvoidanceCore(_p(agent_id=3, dikey_taban_m=4.0))
    # Komsu 1 m ustumde, ben 5 m'deyim: asagi hedef 5-1-3 = 1 m < taban 4
    (_vx, _vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=-1.0)], h_now=5.0)
    assert vz < 0.0, 'taban engelledi -> YUKARI secilmeli'
    assert ca.dikey_yetersiz is True, 'sessiz kalmamali'


def test_dikey_inis_tabanin_altina_inmez():
    ca = CollisionAvoidanceCore(_p(agent_id=3, dikey_taban_m=4.0))
    h, _vz = _kosturmak(ca, [(1, 2.0, 5.5)], h0=4.5, tik=400)
    assert h >= 3.9, f'irtifa kapisinin altina inildi: {h:.2f}'


def test_dikey_hiz_ve_ivme_tavanlari_tutuyor():
    ca = CollisionAvoidanceCore(_p(agent_id=3, v_dikey_max=1.5,
                                   a_dikey_max=1.0))
    onceki = 0.0
    for _ in range(100):
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=0.0)], h_now=10.0)
        assert abs(vz) <= 1.5 + 1e-9, f'hiz tavani asildi: {vz}'
        assert abs(vz - onceki) <= 1.0 * ca.p.dt + 1e-9, 'ivme tavani asildi'
        onceki = vz


# =========================================================================
# SAF DIKEY KIP — yatay bozulmamali
# =========================================================================

def test_saf_dikeyde_yatay_komut_DEGISMEZ():
    """k_yatay=0: formasyon geometrisine dokunulmaz."""
    ca = CollisionAvoidanceCore(_p(agent_id=3, k_yatay=0.0))
    (vx, vy, _vz), _risk = ca.compute(
        (2.0, 1.0, 0.0), [_komsu(1, dx=2.5, rel_z=0.0)], h_now=10.0)
    assert abs(vx - 2.0) < 1e-6 and abs(vy - 1.0) < 1e-6


def test_emniyet_projeksiyonu_saf_dikeyde_de_calisir():
    """r_min icinde komsuya YAKLASAN bilesen sifirlanir (operator karari)."""
    ca = CollisionAvoidanceCore(_p(agent_id=1, k_yatay=0.0, r_min=1.5))
    # Komsu 1 m ileride (+x), ben +x yonunde 2 m/s gidiyorum -> ustune
    (vx, _vy, _vz), _risk = ca.compute(
        (2.0, 0.0, 0.0), [_komsu(3, dx=1.0, rel_z=0.0)], h_now=10.0)
    assert vx < 2.0, 'yaklasma bileseni kirpilmali'


# =========================================================================
# HISTEREZIS ve DONUS
# =========================================================================

def test_histerezis_d0_civarinda_titremeyi_onler():
    ca = CollisionAvoidanceCore(_p(agent_id=3, d0=4.0, hist_m=0.5))
    # Once catismaya sok (3.5 m)
    ca.compute((0.0, 0.0, 0.0), [_komsu(1, dx=3.5)], h_now=10.0)
    # 4.2 m: giris esiginin disinda ama CIKIS esiginin (4.5) icinde
    (_vx, _vy, vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=4.2)], h_now=10.0)
    assert risk is True, 'histerezis bandinda catisma SURMELI'
    assert vz < 0.0


def test_catisma_bitince_nominale_donuluyor():
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    h, _vz = _kosturmak(ca, [(1, 2.0, 10.0)], h0=10.0, tik=400)
    assert h > 12.0, 'once tirmanmis olmali'
    # Komsu uzaklasti
    for _ in range(1000):
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=20.0, rel_z=h - 10.0)], h_now=h)
        h -= vz * ca.p.dt
    assert abs(h - 10.0) < 0.6, f'nominale donmedi: {h:.2f}'


def test_genis_histerezis_komsu_GERCEKTEN_uzaklasana_kadar_tutar():
    """hist_m 0.5 -> 2.5 (24 Agustos, KARARLAR). Cikis d0+hist = 6.5 m.

    23 Agustos ucusunda cikis 4.5 m'ydi ve komsu 4.9 m'de dururken 3 m'lik
    ayrim 6 saniyede geri verildi — operator bunu yo-yo olarak gordu.
    Yeni degerle: komsu 5.5 m'de DURURKEN (eski cikisin disi, yeni cikisin
    ici) ayrim TUTULMALI; 7 m'ye cekilince donus yine islemeli.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3, d0=4.0, hist_m=2.5))
    h, _vz = _kosturmak(ca, [(1, 3.5, 10.0)], h0=10.0, tik=400)
    assert h > 12.5, 'once tirmanmis olmali'
    # Komsu 5.5 m'ye acildi: eski cikis (4.5) disari derdi, yeni (6.5) ici
    (_vx, _vy, _vz2), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=5.5, rel_z=h - 10.0)], h_now=h)
    assert risk is True, 'komsu 5.5 m\'de: catisma SURMELI (cikis 6.5 m)'
    # Komsu 7 m'ye cikti — donus bozulmamali
    for _ in range(1200):
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=7.0, rel_z=h - 10.0)], h_now=h)
        h -= vz * ca.p.dt
    assert abs(h - 10.0) < 0.6, f'komsu 7 m\'deyken nominale donmedi: {h:.2f}'


# =========================================================================
# YATAY SON CARE — "dikey birincil, yatay son care" (operator, 23 Agustos)
# =========================================================================

def test_yatay_itme_d0_da_ACILMAZ():
    """Normal catismada saf dikey: formasyon geometrisi bozulmaz."""
    ca = CollisionAvoidanceCore(_p(agent_id=3, k_yatay=1.0, hard=2.5))
    # 3.5 m: d0 (4.0) icinde ama hard (2.5) bandinin disinda
    (vx, vy, _vz), _risk = ca.compute(
        (2.0, 0.0, 0.0), [_komsu(1, dx=3.5, rel_z=0.0)], h_now=10.0)
    assert abs(vx - 2.0) < 1e-6 and abs(vy) < 1e-6, (
        f'yatay itme erken acildi: ({vx:.3f}, {vy:.3f})')


def test_yatay_itme_SERT_KABUKTA_acilir():
    """Dikey yetisememisse yatay devreye girer."""
    ca = CollisionAvoidanceCore(_p(agent_id=3, k_yatay=1.0, hard=2.5))
    (vx, _vy, _vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=0.0)], h_now=10.0)
    assert risk is True
    assert vx < -0.05, f'sert kabukta yatay itme yok: vx={vx:.3f}'


def test_k_yatay_sifir_yine_saf_dikey_birakir():
    """Operator saf dikeye donmek isterse tek parametre yeter."""
    ca = CollisionAvoidanceCore(_p(agent_id=3, k_yatay=0.0, hard=2.5))
    (vx, vy, vz), _risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=1.0, rel_z=0.0)], h_now=10.0)
    assert abs(vx) < 1e-6 and abs(vy) < 1e-6
    assert vz < 0.0, 'dikey yine calismali'


# =========================================================================
# KORLUKTE AYRIM BIRAKILMAZ — 23 Agustos 2026, operator sorusu uzerine
# =========================================================================

def test_korlukte_nominale_DONULMEZ():
    """Komsuyu kaybetmek "komsu gitti" ile AYNI gorunuyordu.

    Bayat veri listeden dusuyor -> catisma false -> 2 sn sonra ucak
    kazandigi ayrimi geri veriyordu; hem de komsusunun nerede oldugunu
    BILMEDIGI anda. 21 Agustos'ta mesh 46.4 sn tek yonlu olmustu.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    # Once catistir ve tirmandir
    h, _vz = _kosturmak(ca, [(1, 2.0, 10.0)], h0=10.0, tik=300)
    assert h > 12.0, 'once tirmanmis olmali'

    # Komsu KAYBOLDU (listede yok) ve KORLUK bayragi var
    for _ in range(400):
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [], h_now=h, kor=True)
        h -= vz * ca.p.dt
    assert h > 12.0, f'korlukte ayrim birakildi: {h:.2f} m'
    assert ca.dikey_donus_kor is True, 'durum sessiz kalmamali'


def test_korluk_bitince_donus_BASLAR():
    """Komsu tekrar gorulunce normal donus isler."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    h, _vz = _kosturmak(ca, [(1, 2.0, 10.0)], h0=10.0, tik=300)
    for _ in range(100):                      # korlukte tut
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [], h_now=h, kor=True)
        h -= vz * ca.p.dt
    for _ in range(600):                      # korluk bitti, komsu uzakta
        (_vx, _vy, vz), _r = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=20.0, rel_z=h - 10.0)],
            h_now=h, kor=False)
        h -= vz * ca.p.dt
    assert abs(h - 10.0) < 0.6, f'korluk bitince donmedi: {h:.2f} m'


# =========================================================================
# 🔴 YO-YO — ILK UCUSTA SAHADA GORULDU (23 Agustos 2026)
# =========================================================================
# Operator gozlemi: "02 surekli kendini asagi birakiyor ama 00 risk
# alaninda durdugu icin tekrar yukari atiyor. Yoyo gibi gidip geliyordu."
#
# Sebep: ayrim saglanir saglanmaz CA dikey yetkiyi GOREV katmanina geri
# veriyordu. Guided gorev setpoint'i bir KONUM hedefi (asili durulan
# irtifa), yani PX4 ucagi hemen geri cekiyor -> ayrim bozuluyor -> CA
# tekrar tirmaniyor -> ...
#
# Ne benzetim ne birim test yakaladi: benzetimde "gorev" bir HIZ komutu
# (sifir), birakinca geri ceken bir sey yok.


def _yoyo_kosusu(ca, komsu_h, h0, nominal, tik=1200):
    """PX4'un KONUM hedefini modelleyen kosu.

    CA yetkiyi birakirsa (risk False) ucak `nominal`e dogru cekilir —
    guided asili durmada PX4'un yaptigi tam olarak budur. Yetki CA'dayken
    onun vz'si uygulanir.
    """
    h = h0
    izler = []
    for _ in range(tik):
        (_vx, _vy, vz), risk = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=h - komsu_h)],
            h_now=h)
        if risk:
            h -= vz * ca.p.dt
        else:
            # PX4 konum hedefine geri cekiyor (MPC_Z_VEL_MAX_DN=1.5)
            fark = nominal - h
            h += max(-1.5, min(1.5, 2.0 * fark)) * ca.p.dt
        izler.append(h)
    return izler


def test_ayrim_saglaninca_YETKI_BIRAKILMAZ():
    """Ayrim saglandi diye yetki birakilirsa gorev ucagi geri ceker."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    h, _vz = _kosturmak(ca, [(1, 2.0, 10.0)], h0=10.0, tik=400)
    assert h > 12.5, 'once tirmanmis olmali'
    (_vx, _vy, _vz), risk = ca.compute(
        (0.0, 0.0, 0.0), [_komsu(1, dx=2.0, rel_z=h - 10.0)], h_now=h)
    assert risk is True, (
        'ayrim saglaninca yetki BIRAKILMAMALI — gorevin konum hedefi '
        'ucagi geri ceker ve yo-yo baslar')


def test_komsu_risk_alaninda_KALIRSA_yoyo_YOK():
    """Asil saha senaryosu: komsu risk alanindan CIKMIYOR.

    Ucak ayrimi kurup ORADA KALMALI. Genlik katman'in yarisini asarsa
    yo-yo geri gelmis demektir.
    """
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    izler = _yoyo_kosusu(ca, komsu_h=10.0, h0=10.0, nominal=10.0)
    yerlesik = izler[len(izler) // 3:]        # ilk tirmanmayi atla
    genlik = max(yerlesik) - min(yerlesik)
    assert genlik < KATMAN / 2, (
        f'YO-YO: irtifa {min(yerlesik):.2f}-{max(yerlesik):.2f} m '
        f'arasinda salindi (genlik {genlik:.2f} m)')
    assert min(yerlesik) > 10.0 + KATMAN - 0.7, (
        f'ayrim korunmadi: en dusuk {min(yerlesik):.2f} m')


def test_komsu_CIKINCA_nominale_donuluyor():
    """Yo-yo duzeltmesi donusu bozmamali — operator bunu da gozledi."""
    ca = CollisionAvoidanceCore(_p(agent_id=3))
    izler = _yoyo_kosusu(ca, komsu_h=10.0, h0=10.0, nominal=10.0, tik=600)
    h = izler[-1]
    for _ in range(1200):                     # komsu uzaklasti
        (_vx, _vy, vz), risk = ca.compute(
            (0.0, 0.0, 0.0), [_komsu(1, dx=20.0, rel_z=h - 10.0)], h_now=h)
        if risk:
            h -= vz * ca.p.dt
        else:
            h += max(-1.5, min(1.5, 2.0 * (10.0 - h))) * ca.p.dt
    assert abs(h - 10.0) < 0.5, f'nominale donmedi: {h:.2f} m'


# --- korluk yerde-pasif muafiyeti — 25 Agustos 2026 saha bulgusu ---------
#
# Kapali (yerde+disarm) ylp02 yuzunden ylp01'in donusu 34 sn bloke kaldi.
# Muafiyet YALNIZ yerde VE disarm VE z gecerli olan kayip komsuya uygulanir.

def test_korluk_muaf_yerde_ve_disarm():
    """Kapali ucak: yerde (z~0), disarm -> tutma YOK."""
    assert komsu_yerde_pasif(
        armed=False, pos_z_ned=-0.2, z_valid=True, yer_esigi_m=1.5)


def test_korluk_muaf_DEGIL_havada_kaybolan():
    """46.4 sn'lik mesh kopmasi sinifi: havada kaybolan KORUNUR."""
    assert not komsu_yerde_pasif(
        armed=True, pos_z_ned=-5.0, z_valid=True, yer_esigi_m=1.5)


def test_korluk_muaf_DEGIL_yerde_ama_armli():
    """Yerde ama ARM'li: her an kalkabilir -> tutma SURER."""
    assert not komsu_yerde_pasif(
        armed=True, pos_z_ned=-0.1, z_valid=True, yer_esigi_m=1.5)


def test_korluk_muaf_DEGIL_z_gecersiz():
    """Konuma guvenilmiyorsa guvenli taraf: tutma SURER."""
    assert not komsu_yerde_pasif(
        armed=False, pos_z_ned=0.0, z_valid=False, yer_esigi_m=1.5)


def test_korluk_muaf_DEGIL_disarm_ama_yuksekte():
    """Disarm gorunen ama yuksekte kaybolan (supheli veri) KORUNUR."""
    assert not komsu_yerde_pasif(
        armed=False, pos_z_ned=-4.0, z_valid=True, yer_esigi_m=1.5)
