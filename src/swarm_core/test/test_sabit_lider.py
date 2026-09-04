# Copyright 2026 Yelpence
"""SABIT LIDER — 4 Eylul 2026 operator karari, YALNIZ GOREV 2.

NEDEN VAR: Gorev 2'de formasyon tarifini YALNIZ lider basiyor (tek-yayinci,
KARAR-16) ve lider kilidi (3 Eylul) ILK secimi NIHAI yapiyor. Ilk secimin
ylp00'a dusmesi bugun TESADUFE bagli: `candidate = min(effective)` + tam
kadro beklemesi. Tam kadro `kilit_tam_kadro_s` (8 sn) icinde olusmazsa yedek
yol devreye giriyor ve O AN uygun olan kim varsa KALICI lider oluyor.
Ucaklar arasi evre kaymasi 3 Eylul ucusunda 25 SANIYE olculdu — yani 8 sn'lik
pencere guvenilir degil ve yanlis lider bir daha duzelmiyor.

Bu testler iki seyi ayni anda kilitliyor:

  1) KAPSAM — `sabit_lider = 0` iken HICBIR SEY degismez. Gorev 1 profilinde
     baslat.sh consensus'a 0 geciriyor; asagidaki regresyon testleri o
     yolun bire bir eski davranisi surdurdugunu kanitliyor. Gorev 1'in
     liderligine dokunulmadi.

  2) DEGISMEZLIK — sabit lider acikken lider hicbir kosulda degismez:
     uygunlugunu yitirse de, daha kucuk id'li bir aday cikssa da,
     `effective` kumesinden dusse de.

⚠️ Bu dosya liderin degisebildigi DORT yoldan yalnizca birincisini
(`decide_change`) kapsar; digerleri ROS dugumunun icinde
(`_liderligi_birak`, `_adopt_leader`, `_rakip_tahkim`) ve orada ayrica
kapatildi. Biri atlanirsa mesh'ten gelen tek bir kalp atisi sabit lideri
devirir — bu yuzden dordunun de kapali oldugu kod incelemesiyle
dogrulanmali.
"""

from swarm_core.consensus import election
from swarm_core.consensus.consensus_context import ConsensusContext

from swarm_interfaces.msg import ElectionResult

SIMDI = 1000.0


def _ctx(agent_id=1, leader_id=0, sabit=0, kilit=False):
    c = ConsensusContext(
        agent_id=agent_id, agent_count=3, stale_s=3.0,
        hb_timeout_s=1.0, battery_min_v=0.0, grace_s=1.5,
    )
    c.leader_id = leader_id
    c.is_leader = (leader_id == agent_id)
    c.last_hb_time = SIMDI
    c.sabit_lider = sabit
    c.lider_kilitli = kilit
    return c


# ---------------------------------------------------------------------------
# 1. KAPSAM — varsayilan KAPALI, Gorev 1 davranisi degismedi
# ---------------------------------------------------------------------------

def test_baglam_sabit_lider_VARSAYILAN_KAPALI():
    """Yeni alanin varsayilani 0 olmali.

    0 olmasaydi, parametreyi hic gecirmeyen her cagirici (Gorev 1 dahil)
    sessizce sabit lider davranisina gecerdi.
    """
    c = ConsensusContext(
        agent_id=1, agent_count=3, stale_s=3.0,
        hb_timeout_s=1.0, battery_min_v=0.0, grace_s=1.5,
    )
    assert c.sabit_lider == 0


def test_kapaliyken_ILK_SECIM_eski_yoldan_yapilir():
    """GOREV 1 REGRESYONU: sabit kapaliyken tam kadro -> min(effective)."""
    c = _ctx(leader_id=0, sabit=0)
    c.bootstrap_since = SIMDI - 5.0
    karar = election.decide_change(c, {1, 2, 3}, SIMDI)
    assert karar is not None
    assert karar[0] == 1          # min(effective)


def test_kapaliyken_LIDER_ARIZASI_devri_calisir():
    """GOREV 1 REGRESYONU: lider effective'den duserse devir olur."""
    c = _ctx(agent_id=2, leader_id=1, sabit=0)
    karar = election.decide_change(c, {2, 3}, SIMDI)
    assert karar is not None
    assert karar[0] == 2
    assert karar[1] == ElectionResult.REASON_LEADER_FAULT


def test_kapaliyken_eksik_kadroda_grace_bekler():
    """GOREV 1 REGRESYONU: tam kadro yoksa grace dolmadan secim YOK."""
    c = _ctx(leader_id=0, sabit=0)
    c.bootstrap_since = SIMDI - 0.5      # grace_s = 1.5
    assert election.decide_change(c, {2, 3}, SIMDI) is None


# ---------------------------------------------------------------------------
# 2. ACIKKEN — lider VERILIR, secilmez
# ---------------------------------------------------------------------------

def test_acikken_lider_ANINDA_kurulur():
    """Uygunluk beklenmez: `effective` BOS olsa bile sabit lider atanir.

    Bilerek boyle: uygunluk beklemek, ylp00 gec arm oldugunda yine yedek
    yola dusme riskini birakirdi — kapatmaya calistigimiz sey tam o.
    """
    c = _ctx(leader_id=0, sabit=1)
    karar = election.decide_change(c, set(), SIMDI)
    assert karar is not None
    assert karar[0] == 1


def test_acikken_TAM_KADRO_BEKLENMEZ():
    """Kilit acik + eksik kadro: eski yol beklerdi, sabit lider beklemez.

    `kilit_tam_kadro_s` 8 sn; sabit liderde o pencere hic islemez, yani
    kalkis oncesi 8 saniyelik lidersiz bosluk da olusmaz.
    """
    c = _ctx(leader_id=0, sabit=1, kilit=True)
    c.bootstrap_since = SIMDI          # daha yeni basladi
    karar = election.decide_change(c, {3}, SIMDI)
    assert karar is not None
    assert karar[0] == 1


def test_acikken_UYGUN_OLMAYAN_aday_yine_lider_olur():
    """Sabit lider uygun kumede olmasa bile secilir (kume {2,3})."""
    c = _ctx(agent_id=3, leader_id=0, sabit=1)
    karar = election.decide_change(c, {2, 3}, SIMDI)
    assert karar[0] == 1


def test_acikken_kurulduktan_sonra_DEGISMEZ():
    """Lider bir kez kurulunca decide_change artik None doner."""
    c = _ctx(leader_id=1, sabit=1)
    assert election.decide_change(c, {1, 2, 3}, SIMDI) is None


def test_acikken_LIDER_ARIZASI_devri_YAPILMAZ():
    """🔴 En kritik test: sabit lider effective'den dusse bile devir YOK.

    Eski yol burada REASON_LEADER_FAULT ile devrederdi. Sabit liderin
    tanimi "hicbir yoldan degismez" oldugu icin bu dal kapali olmak
    zorunda. BEDELI bilerek kabul edildi: sabit lider gercekten duserse
    takipciler son formasyon komutunda kalir, cikis yolu kill switch.
    """
    c = _ctx(agent_id=2, leader_id=1, sabit=1)
    assert election.decide_change(c, {2, 3}, SIMDI) is None


def test_acikken_KUCUK_ID_onalmasi_YAPILMAZ():
    """Sabit lider 3 iken, id'si 1 olan ucak onalmaya kalkmaz."""
    c = _ctx(agent_id=1, leader_id=3, sabit=3)
    c.onalma_bastir_until = 0.0        # bastirma KAPALI — yine de degismemeli
    assert election.decide_change(c, {1, 2, 3}, SIMDI) is None


def test_acikken_YANLIS_lider_kuruluysa_DUZELTILIR():
    """leader_id sabit olandan farkliysa sabit olana CEKILIR.

    Bu, dugum yeniden baslamadan parametre degistirilirse ya da baska bir
    yol leader_id'yi kirletirse kendini toparlamayi saglar.
    """
    c = _ctx(agent_id=1, leader_id=2, sabit=1)
    karar = election.decide_change(c, {1, 2, 3}, SIMDI)
    assert karar is not None
    assert karar[0] == 1
