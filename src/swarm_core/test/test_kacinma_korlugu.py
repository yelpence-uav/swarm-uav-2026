# Copyright 2026 Yelpence
"""P0.15: mesh tek yonlu olunce kacinma KOR kaliyor ve alarm yoktu.

21 AGUSTOS 2026, UCUSTA OLCULDU. Operator ylp02'yi ylp00'a 3 METREYE kadar
yaklastirdi (irtifalar 10 ve 8 m); `collision_avoidance` HIC tetiklenmedi.
Sebep algoritma degildi — ylp00 komsusunu 46.4 SANIYE hic gormedi:

    ylp02'nin ylp00'dan aldigi : ortanca 0.10  p90 0.20  MAKS  0.4 sn
    ylp00'in ylp02'den aldigi  : ortanca 0.10  p90 0.20  MAKS 46.4 sn

Ayni anda ters yon kusursuz calisiyordu. Bkz. TUZAKLAR 2.15.

IKI KUSUR VARDI:
  1. Korluk SESSIZDI — yalniz `skip_stale` sayacinda artiyor, 5 sn'de bir
     basilan tani satirinin icinde kayboluyordu. 47 saniye alarm YOK.
  2. Korluk "engel yok" diye yorumlaniyordu. Oysa "nerede oldugunu
     BILMIYORUM" demek: komsu son gorulen yerden v_max ile her yone
     gidebilir. Formasyonda kor uctaki ucak komsusuna dogru YURUMEYE
     DEVAM ederdi.

DUZELTME: korluk birinci sinif bir durum. Alarm (log + SystemEvent) ve
esik asilinca YATAY HAREKET DURDURULUR. Dikey serbest — irtifa ayrimi
yedek garanti ve tirmanis/inis kesilmemeli.
"""

from unittest.mock import MagicMock

from swarm_core.collision_avoidance.collision_avoidance_node import (
    CollisionAvoidanceNode,
)

from swarm_interfaces.msg import AgentSetpoint, AgentStatus

# swarm_interfaces conftest'te TAMAMEN mock (ROS'suz kosabilmek icin), yani
# sinif sabitleri de MagicMock donuyor ve `raw.priority >= PRIORITY_FAILSAFE`
# TypeError atiyor. Sabitleri AgentSetpoint.msg'deki GERCEK degerlere
# baglıyoruz — deger degisirse test kirilir ve bu DOGRU davranis: kacinmanin
# oncelik esikleri sessizce kaymamali.
AgentSetpoint.PRIORITY_FAILSAFE = 100            # AgentSetpoint.msg:26
AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE = 80  # AgentSetpoint.msg:25
AgentSetpoint.SOURCE_COLLISION_AVOIDANCE = 4     # AgentSetpoint.msg:17


def _dugum(alarm_s=2.0, tut_s=5.0):
    n = object.__new__(CollisionAvoidanceNode)
    n._agent_id = 1
    n._neighbor_rx_stale_s = 1.5
    n._korluk_alarm_s = alarm_s
    n._korluk_tut_s = tut_s
    n._v_max_mps = 4.0
    n._cur_vz = 0.0
    n._neighbors = {}
    n._neighbor_rx = {}
    n._komsu_gorulmus = set()
    n._korluk_bildirildi = set()
    n._n_korluk = 0
    n._n_korluk_tut = 0
    n._korluk_tut_aktif = False
    n._n_skip_stale = 0
    n._n_skip_state = 0
    n._n_skip_adaptor = {}
    n._sequence_num = 0
    n._ben = None
    n.get_logger = MagicMock()
    n.get_clock = MagicMock()
    n._event_pub = MagicMock()
    n._setpoint_pub = MagicMock()
    return n


def _st(state=AgentStatus.STATE_ARMED):
    m = AgentStatus()
    m.state = state
    m.xy_valid = True
    m.z_valid = True
    m.v_xy_valid = True
    m.lat_deg = 38.69
    m.lon_deg = 39.16
    return m


# --- KORLUK TESPITI --------------------------------------------------------

def test_hic_gorulmemis_komsu_KORLUK_SAYILMAZ():
    """Yerdeki ylp01 hic veri gondermiyor — bu alarm degil, normal hal."""
    n = _dugum()
    n._neighbors = {2: _st()}
    n._neighbor_rx = {2: 0.0}          # hic gorulmedi
    n._ben = _st()
    n._korluk_tara(now=100.0)
    assert n._korluk_bildirildi == set(), 'hic gorulmemis komsu alarm uretti'
    assert not n._event_pub.publish.called


def test_gorulmus_komsu_kaybolunca_ALARM():
    """Asil ariza: 21 Agustos'ta 47 saniye sessiz kalindi."""
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)     # taze -> gorulmus olarak isaretle
    assert 3 in n._komsu_gorulmus
    n._korluk_tara(now=103.0)     # 3 sn sessizlik
    assert 3 in n._korluk_bildirildi, 'korluk bildirilmedi'
    assert n._event_pub.publish.called, 'SystemEvent yayinlanmadi (YKI gormez)'


def test_alarm_esigin_ALTINDA_uretilmez():
    """Saglikli linkte maks bosluk 0.4 sn olculdu; yanlis alarm olmamali."""
    n = _dugum(alarm_s=2.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    n._korluk_tara(now=101.7)     # 1.7 sn: stale ama alarm esigi altinda
    assert n._korluk_bildirildi == set()


def test_alarm_YALNIZ_BIR_KEZ_basilir():
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    for t in (103.0, 104.0, 105.0, 110.0):
        n._korluk_tara(now=t)
    assert n._n_korluk == 1, 'alarm tekrar tekrar basildi (log bogulur)'


def test_komsu_geri_gelince_korluk_BITER():
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    n._korluk_tara(now=105.0)
    assert 3 in n._korluk_bildirildi
    n._neighbor_rx[3] = 106.0          # tekrar veri geldi
    n._korluk_tara(now=106.0)
    assert 3 not in n._korluk_bildirildi, 'korluk temizlenmedi'


def test_korluk_bitince_YENIDEN_bildirilebilir():
    """Ikinci kopma da bir olaydir; bir kez bildirip susmak yanlis olurdu."""
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    n._korluk_tara(now=105.0)     # 1. korluk
    n._neighbor_rx[3] = 106.0
    n._korluk_tara(now=106.0)     # duzeldi
    n._korluk_tara(now=110.0)     # 2. korluk
    assert n._n_korluk == 2


# --- KORLUKTE DURMA (ucus yolu — en kritik kisim) ---------------------------

def _tik_kur(n, tik_t, ham_vz=0.0, hiz_var=False):
    """_tick_inner'i ROS'suz kosturmak icin gereken en az durum.

    `tik_t` SART: `_tick_inner` ilk isi olarak ham setpoint'in yasina bakiyor
    (`now - _raw_stamp > _raw_timeout_s` -> return). Damga tik anina gore
    bayat kalirsa fonksiyon daha korluk mantigina VARMADAN cikar ve test
    yanlislikla "calismadi" der. Ilk yazimda bu oldu; kod degil test yanlisti.
    """
    # AgentSetpoint conftest'te MOCK — gercek mesaj degil, alanlari
    # MagicMock donuyor ve `raw.priority >= ...` karsilastirmasi TypeError
    # atiyor. Bu yuzden yerel sade bir tasiyici kullaniyoruz; kod yalniz
    # alan okuyup deepcopy'liyor, tip onemli degil.
    class _Sp:
        def __init__(self):
            self.priority = 0        # normal seyir; FAILSAFE(100) altinda
            self.hold_position = False
            self.land_now = False
            self.rtl_now = False
            self.velocity_valid = hiz_var
            self.position_valid = not hiz_var
            self.vx = 0.0
            self.vy = 0.0
            self.vz = ham_vz
            self.stamp = None
            self.sequence_num = 0
            self.source = 0
            self.acceleration_valid = False
            self.max_speed_mps = 0.0
            self.source_module = ''
    raw = _Sp()
    n._raw = raw
    n._raw_stamp = tik_t          # taze
    n._raw_timeout_s = 0.5
    n._pos_ok = True
    n._cur_z = -10.0          # 10 m havada
    n._cur_vx = n._cur_vy = 0.0
    n._altitude_gate_m = 3.0
    n._ca = MagicMock()
    n._ca.compute.return_value = ((0.0, 0.0, 0.0), False)
    n._relay = MagicMock()
    n._n_passthrough = 0
    n._n_avoid = 0
    n._n_gate_alt = 0
    return raw


def test_korlukte_YATAY_HAREKET_DURUR():
    """Asil duzeltme: kor uctaki ucak komsusuna dogru yurumeye devam etmesin."""
    n = _dugum(tut_s=5.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 106.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(106.0 * 1e9)
    n._tick()
    assert n._setpoint_pub.publish.called, 'setpoint yayinlanmadi'
    cik = n._setpoint_pub.publish.call_args[0][0]
    assert cik.vx == 0.0 and cik.vy == 0.0, 'yatay hareket durmadi'
    assert cik.velocity_valid is True
    assert cik.position_valid is False, 'konum hedefi kalirsa ucak yurumeye devam eder'
    assert n._n_korluk_tut == 1
    assert not n._relay.called, 'ham setpoint aynen gecirildi — tutma calismadi'


def test_korlukte_DIKEY_KORUNUR():
    """Irtifa ayrimi yedek garantimiz; tirmanis/inis kesilmemeli."""
    n = _dugum(tut_s=5.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 106.0, ham_vz=-1.5, hiz_var=True)   # 1.5 m/s tirmanis
    n.get_clock.return_value.now.return_value.nanoseconds = int(106.0 * 1e9)
    n._tick()
    cik = n._setpoint_pub.publish.call_args[0][0]
    assert cik.vz == -1.5, 'dikey hiz kesildi — irtifa ayrimi bozulur'


def test_TUTMA_ESIGI_ALTINDA_normal_akis():
    """3 sn korluk: alarm evet, tutma HAYIR. Gecici sarsintida ucak durmasin."""
    n = _dugum(alarm_s=2.0, tut_s=5.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 103.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(103.0 * 1e9)
    n._tick()
    assert 3 in n._korluk_bildirildi, 'alarm basilmali'
    assert n._n_korluk_tut == 0, 'esik altinda tutma tetiklendi'
    assert n._relay.called, 'normal akis kesildi'


def test_tutma_KAPATILABILIR():
    """korluk_tut_s=0 -> yalniz alarm. Operator karari acik kalsin."""
    n = _dugum(tut_s=0.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 120.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(120.0 * 1e9)
    n._tick()
    assert n._n_korluk_tut == 0
    assert n._relay.called


def test_komsu_geri_gelince_tutma_KALKAR():
    n = _dugum(tut_s=5.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 106.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(106.0 * 1e9)
    n._tick()
    assert n._korluk_tut_aktif is True
    n._neighbor_rx[3] = 107.0                  # veri geri geldi
    n._raw_stamp = 107.0                       # ham setpoint de taze
    n._relay.reset_mock()
    n.get_clock.return_value.now.return_value.nanoseconds = int(107.0 * 1e9)
    n._tick()
    assert n._korluk_tut_aktif is False, 'tutma kalkmadi — ucak kilitli kalir'
    assert n._relay.called, 'normal akisa donulmedi'


def test_hic_gorulmemis_komsu_TUTMA_uretmez():
    """ylp01 yerde. Onun yoklugu ucagi durdurmamali."""
    n = _dugum(tut_s=5.0)
    n._neighbors = {2: _st()}
    n._ben = _st()
    n._neighbor_rx = {2: 0.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 200.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(200.0 * 1e9)
    n._tick()
    assert n._n_korluk_tut == 0, 'hic gorulmemis komsu ucagi durdurdu'
    assert n._relay.called


def test_korluk_ciktisi_DOGRU_ONCELIK_ve_KAYNAK_tasir():
    """px4_bridge ve kayit bu alanlara bakiyor; sessizce degismemeli.

    priority=PRIORITY_COLLISION_AVOIDANCE (80) ve
    source=SOURCE_COLLISION_AVOIDANCE (4) — px4_bridge'in yurutucu kapisi
    kaynagi bu sabitle karsilastiriyor (px4_bridge.py:665-669): kacinma
    cikisinda yurutucu DEVRE DISI kalmali, yoksa kacis 2 m/s'e yavaslar.
    """
    n = _dugum(tut_s=5.0)
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._korluk_tara(now=100.0)
    _tik_kur(n, 106.0)
    n.get_clock.return_value.now.return_value.nanoseconds = int(106.0 * 1e9)
    n._tick()
    cik = n._setpoint_pub.publish.call_args[0][0]
    assert cik.priority == AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
    assert cik.source == AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
    assert cik.source_module == 'collision_avoidance:korluk', \
        'kayitta korluk tutmasi normal kacistan ayirt edilemez'


# --- KORLUK SETPOINT AKISINDAN BAGIMSIZ (P0.15, ikinci bulgu) --------------

def test_SETPOINT_YOKKEN_de_korluk_tespit_edilir():
    """21 Agustos aksami YERDE olculdu: setpoint akmayinca korluk gorunmuyordu.

    `_tick_inner` `raw is None` ile erken cikiyor; korluk tespiti onun
    icindeyse HIC calismiyor. Iki ucak yerde, mesh kesildi, veri gercekten
    durdu (`ros2 topic hz` bos) ama korluk=0 kaldi ve uyari cikmadi.

    Ucak HAVADA da setpoint akisi kesilebilir (gorev bitti, bekleme evresi,
    YKI koptu) ve tam o anda komsusunu kaybetmis olabilir.
    """
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n._raw = None                      # SETPOINT YOK — ucak yerde/bekliyor
    n._raw_stamp = 0.0
    n._raw_timeout_s = 0.5
    n.get_clock.return_value.now.return_value.nanoseconds = int(100.0 * 1e9)
    n._tick()
    assert 3 in n._komsu_gorulmus, 'setpoint yokken komsu hic taninmadi'
    n.get_clock.return_value.now.return_value.nanoseconds = int(105.0 * 1e9)
    n._tick()
    assert 3 in n._korluk_bildirildi, \
        'setpoint akmiyorken korluk tespit edilmedi (asil ariza buydu)'
    assert n._event_pub.publish.called


def test_tick_ISTISNAYI_yutuyor_ama_korluk_ONCE_kosuyor():
    """`_tick` try/except ile sariyor; korluk taramasi `_tick_inner`den ONCE
    kosmali ki oradaki bir hata korlugu de sessizce oldurmesin."""
    n = _dugum()
    n._neighbors = {3: _st()}
    n._ben = _st()
    n._neighbor_rx = {3: 100.0}
    n.get_clock.return_value.now.return_value.nanoseconds = int(100.0 * 1e9)
    n._tick()
    # _tick_inner'i patlat
    n._raw = object()                  # beklenmedik tip -> iceride hata
    n._raw_stamp = 105.0
    n._raw_timeout_s = 0.5
    n.get_clock.return_value.now.return_value.nanoseconds = int(105.0 * 1e9)
    n._tick()                          # istisna yutulur
    assert 3 in n._korluk_bildirildi, \
        'tick_inner hatasi korlugu de sessizce oldurdu'
