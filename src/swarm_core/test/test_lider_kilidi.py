# Copyright 2026 Yelpence
"""3 Eylul 2026: liderlik BES KEZ el degistirdi, suru bolundu.

Ucus kaydinda olculen zincir: 1 -> 2 -> 1 -> 2 -> 1 -> 3. Kok neden lider
adayinin OLMESI degil, DURUM paketinin bayatlamasiydi — ucak basina 7-8 kez
"DURUM paketi 5.0-5.1 sndir gelmedi" (esik 5.0 sn) goruldu, yani lider
mesh gecikmesi yuzunden anlik olarak uygun kumeden dustu ve hemen geri
dondu. Her degisimde YENI lider slot atamasini bastan hesapladi; ylp01 ile
ylp02 slot degistirdi, birbirinin ustunden gectiler, kacinma binlerce kare
devrede kaldi (avoid=1136 / 1614, yatay_tut=48/52).

Operator karari: lider BIR KEZ secilsin, bir daha DEGISMESIN.

Bu testler kilidin iki seyi ayni anda yaptigini kilitliyor:
  1) DEGISIM dallarinin ikisini de (LEADER_FAULT ve onalma) kapatir
  2) ILK secimi (leader_id == 0) KAPATMAZ — kapatsaydi suru hic lider
     secemez ve formasyon zinciri baslamazdi.
"""

from swarm_core.consensus import election
from swarm_core.consensus.consensus_context import ConsensusContext

from swarm_interfaces.msg import ElectionResult

SIMDI = 1000.0


def _ctx(agent_id=1, leader_id=1, kilit=False):
    c = ConsensusContext(
        agent_id=agent_id, agent_count=3, stale_s=3.0,
        hb_timeout_s=1.0, battery_min_v=0.0, grace_s=1.5,
    )
    c.leader_id = leader_id
    c.is_leader = (leader_id == agent_id)
    c.last_hb_time = SIMDI
    c.lider_kilitli = kilit
    return c


def test_baglam_kilidi_var_ve_VARSAYILAN_KAPALI():
    """Alan yoksa election getattr'siz patlar; varsayilan eski davranis."""
    assert _ctx().lider_kilitli is False


# --- kilit KAPALI iken eski davranis birebir korunuyor --------------------

def test_kilit_kapali_LIDER_FAULT_devri_YAPAR():
    """Regresyon siperi: kilit kapaliyken dusen lider devredilir."""
    c = _ctx(agent_id=2, leader_id=1, kilit=False)
    assert election.decide_change(c, {2, 3}, SIMDI) == (
        2, ElectionResult.REASON_LEADER_FAULT)


def test_kilit_kapali_ONALMA_yapar():
    """Kucuk id, buyuk id liderden liderligi alir (eski davranis)."""
    c = _ctx(agent_id=1, leader_id=3, kilit=False)
    assert election.decide_change(c, {1, 3}, SIMDI) == (
        1, ElectionResult.REASON_UNKNOWN)


# --- kilit ACIK: iki degisim dali de kapali -------------------------------

def test_kilit_acik_LIDER_FAULT_devri_YAPMAZ():
    """Asil hedef: lider bayatlayip kumeden dusse bile devir olmaz.

    3 Eylul'de zincirin her halkasi tam buradan geciyordu.
    """
    c = _ctx(agent_id=2, leader_id=1, kilit=True)
    assert election.decide_change(c, {2, 3}, SIMDI) is None


def test_kilit_acik_ONALMA_YAPMAZ():
    """Kucuk id de liderligi geri alamaz — yoksa 1<->2 titremesi surer."""
    c = _ctx(agent_id=1, leader_id=3, kilit=True)
    assert election.decide_change(c, {1, 3}, SIMDI) is None


def test_kilit_acik_lider_kendisiyse_karar_YOK():
    """Lider zaten aday ise degisim karari zaten uretilmez."""
    c = _ctx(agent_id=1, leader_id=1, kilit=True)
    assert election.decide_change(c, {1, 2, 3}, SIMDI) is None


# --- ILK secim kilitten ETKILENMEZ ---------------------------------------

def test_kilit_acik_ILK_secim_YAPILIR_tam_kadro():
    """Kilit 'degisimi' kapatir, 'secimi' degil. Kadro tamsa hemen secer."""
    c = _ctx(agent_id=2, leader_id=0, kilit=True)
    c.bootstrap_since = SIMDI
    assert election.decide_change(c, {1, 2, 3}, SIMDI) == (
        1, ElectionResult.REASON_UNKNOWN)


def test_kilit_acik_ILK_secim_YAPILIR_grace_dolunca():
    """Eksik kadroda da grace sonunda secim yapilir — kilit engellemez."""
    c = _ctx(agent_id=2, leader_id=0, kilit=True)
    c.bootstrap_since = SIMDI - 2.0          # grace_s = 1.5
    assert election.decide_change(c, {2, 3}, SIMDI) == (
        2, ElectionResult.REASON_UNKNOWN)


def test_kilit_acik_bos_kume_karar_URETMEZ():
    """Uygun aday yokken kilit acik ya da kapali fark etmez."""
    c = _ctx(agent_id=1, leader_id=0, kilit=True)
    c.bootstrap_since = SIMDI - 99.0
    assert election.decide_change(c, set(), SIMDI) is None
