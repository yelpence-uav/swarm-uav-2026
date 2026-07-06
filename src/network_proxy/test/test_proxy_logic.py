"""test_proxy_logic.py — proxy karar mantığı testleri (rclpy, spin YOK).

Deterministik: konumlar ya aynı (0 m → drop olasılığı 0, asla düşmez) ya da
1° uzak (~111 km → cutoff ötesi, hep düşer). Böylece rastgeleliğe gerek yok.
Relay olup olmadığı, gecikme kuyruğuna (_pending) mesaj eklendi mi ile ölçülür.
"""

import pytest
import rclpy

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from network_proxy.network_proxy_node import NetworkProxyNode

_YAKIN = (41.0, 29.0, 0.0)          # 0 m → asla düşmez
_UZAK = (42.0, 29.0, 0.0)           # ~111 km → cutoff ötesi, hep düşer


@pytest.fixture(scope="module")
def node():
    rclpy.init()
    n = NetworkProxyNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _reset(n):
    """Her testten önce: kuyruğu boşalt, fault temizle, herkesi yakına al."""
    n._pending.clear()
    n.unreachable_agents = set()
    for a in n.agent_ids:
        n.positions[a] = _YAKIN


# ---------------- _within_budget (250 byte) ----------------
def test_within_budget_normal_gecer(node):
    _reset(node)
    assert node._within_budget(AgentStatus(), "test") is True


def test_within_budget_asan_dusurulur(node):
    _reset(node)
    msg = AgentStatus()
    msg.status_text = "x" * 300  # 250'yi kesin aşar
    assert node._within_budget(msg, "test") is False


# ---------------- _broadcast_drop (mesafe + fault) ----------------
def test_broadcast_yakin_dusmez(node):
    _reset(node)
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_izole_duser(node):
    """Gönderen TÜM komşularından menzil dışıysa (en yakın komşu bile
    cutoff ötesi) non-kritik yayın düşer — mesh'e hiç giremez."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # gönderen komşularından izole
    assert node._broadcast_drop("drone1") is True


def test_broadcast_bir_komsu_uzak_digeri_yakin_gecer(node):
    """Bir alıcı uzak, bir alıcı yakınsa yayın GEÇER — en yakın komşu
    paketi mesh'e sokar (multi-hop). Eski 'en uzak alıcı' modeli bunu
    yanlışlıkla düşürürdü."""
    _reset(node)
    node.positions["drone3"] = _UZAK  # drone1 hâlâ drone2 ile _YAKIN
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_none_failopen(node):
    _reset(node)
    node.positions["drone1"] = None  # henüz konum bildirmedi
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_unreachable_keser(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    assert node._broadcast_drop("drone1") is True


def test_broadcast_uzak_alici_unreachable_sayilmaz(node):
    _reset(node)
    node.positions["drone2"] = _UZAK
    node.unreachable_agents = {"drone2"}  # "gitmiş" alıcı komşu adayı değil
    assert node._broadcast_drop("drone1") is False


# ---------------- reliability sınıfları (mesh retry hizası) ----------------
def test_control_uzakta_bile_iletilir(node):
    """KOMUT mesh'te kritik/retry → mesafe zarı YOK, hep geçer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_control(SwarmControlCommand())
    assert len(node._pending) == 1


def test_state_gonderen_izole_dusurulur(node):
    """SWARM_STATE non-kritik → mesafe zarı VAR; lider komşularından
    izole ise (en yakın komşu bile cutoff ötesi) düşer."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # lider komşularından izole
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 0


def test_state_yakinda_iletilir(node):
    _reset(node)
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 1


# ---------------- QR: raw_text temizleme + mesafe ----------------
def test_qr_raw_text_temizlenir(node):
    _reset(node)
    m = QRMissionData()
    m.detector_agent_id = 1
    m.raw_text = "team_id=YELPENCE; formation=V"
    m.error_message = "hata"
    node._on_internal_qr(m)
    assert len(node._pending) == 1
    _, _, _, sched = node._pending[0]
    assert sched.raw_text == ""
    assert sched.error_message == ""


def test_qr_gonderen_izole_dusurulur(node):
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # algılayan komşularından izole
    m = QRMissionData()
    m.detector_agent_id = 1
    node._on_internal_qr(m)
    assert len(node._pending) == 0


# ---------------- fault-injection tutarlılığı ----------------
def test_faultinjection_status_kesilir(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    msg = AgentStatus()
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = _YAKIN
    node.internal_status_callback(msg, "drone1")
    assert len(node._pending) == 0


def test_faultinjection_state_de_kesilir(node):
    """Lider menzil dışı → SwarmState de kesilmeli (tutarlılık düzeltmesi)."""
    _reset(node)
    node.unreachable_agents = {"drone1"}
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 0


def test_status_yakinda_iletilir(node):
    _reset(node)
    msg = AgentStatus()
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = _YAKIN
    node.internal_status_callback(msg, "drone1")
    assert len(node._pending) == 1


# ---------------- kritik kanallarda fiziksel menzil (retry menzil dışını
# kurtarmaz — mesh_config.h _mesh_gonder: retry yalnız esp_now_send
# başarısızlığını dener, fiziksel olarak ulaşmayan sinyali kurtaramaz) -----
def test_election_yakinda_iletilir(node):
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 1


def test_election_confirmed_ids_dorde_kirpilir(node):
    """Mesh'te election_veri_t.confirmed_ids sabit 4 slot (mesh_config.h);
    5+ onaylayan ID gelirse proxy ilk 4'e kırpar (gerçek paket kapasitesi)."""
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    m.confirmed_by_agent_ids = [1, 2, 3, 4, 5]
    node._on_internal_election(m)
    assert len(node._pending) == 1
    _, _, _, sched = node._pending[0]
    assert list(sched.confirmed_by_agent_ids) == [1, 2, 3, 4]


def test_election_confirmed_ids_dortten_azsa_dokunulmaz(node):
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    m.confirmed_by_agent_ids = [1, 2]
    node._on_internal_election(m)
    _, _, _, sched = node._pending[0]
    assert list(sched.confirmed_by_agent_ids) == [1, 2]


def test_election_gonderen_izole_dusurulur(node):
    """Yeni lider (new_leader_id) TÜM komşularından menzil dışıysa (izole)
    election düşer — mesh'e paketi sokacak komşu yok. Gönderen uzakta,
    komşular birbirine yakın (başka bir kümede)."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # gönderen komşularından ~111 km uzak
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 0


def test_election_bir_komsuya_yakinsa_iletilir(node):
    """Multi-hop: lider bir komşuyla menzilde, diğeri uzak olsa bile
    election iletilir — yakın komşu paketi mesh'e sokup geri kalana yayar.
    (Eski 'en uzak alıcı' modeli bunu yanlışlıkla düşürürdü.)"""
    _reset(node)
    # drone1 (gönderen/lider) drone2 ile _YAKIN, drone3 uzak
    node.positions["drone3"] = _UZAK
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 1


def test_election_gonderen_unreachable_keser(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 0


def test_event_kaynaksiz_menzil_kontrolsuz_iletilir(node):
    """source_agent_id==0 (sistem/GCS) → fiziksel verici yok, menzil
    kontrolü uygulanmaz, her zaman geçer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    m = SystemEvent()
    m.source_agent_id = 0
    node._on_internal_event(m)
    assert len(node._pending) == 1


def test_event_kaynak_izole_dusurulur(node):
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # kaynak komşularından izole
    m = SystemEvent()
    m.source_agent_id = 1
    node._on_internal_event(m)
    assert len(node._pending) == 0


# ---------------- QRCoordinates (latched, origin sınıfı) ----------------
def test_qr_coords_uzakta_bile_iletilir(node):
    """QR tablosu latched/statik (origin sınıfı) → mesafe zarı yok, hep geçer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    m = QRCoordinates()
    m.qr_ids = [1, 2, 3, 4, 5, 6]
    m.lat_deg = [41.0] * 6
    m.lon_deg = [29.0] * 6
    m.alt_m = [15.0] * 6
    node._on_internal_qr_coords(m)
    assert len(node._pending) == 1


def test_qr_coords_asiri_buyuk_dusurulur(node):
    """Çok fazla QR (250 byte'ı aşan tablo) bütçe kontrolünde düşer."""
    _reset(node)
    m = QRCoordinates()
    n = 300  # 300 QR → 250 byte'ı kesin aşar
    m.qr_ids = [1] * n
    m.lat_deg = [41.0] * n
    m.lon_deg = [29.0] * n
    m.alt_m = [15.0] * n
    node._on_internal_qr_coords(m)
    assert len(node._pending) == 0


def test_control_gcs_konumsuzken_muaf(node):
    """gcs_lat/gcs_lon verilmediyse (varsayılan) control menzil kontrolünden
    muaf kalır — mevcut davranış korunur (bkz. test_control_uzakta_bile_iletilir)."""
    _reset(node)
    assert node._gcs_configured is False
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_control(SwarmControlCommand())
    assert len(node._pending) == 1


def test_gcs_isolated_hesabi_dogru(node):
    """_gcs_configured=False olduğundan _on_internal_control bu fonksiyonu
    hiç çağırmaz; fonksiyonun kendisini doğrudan, GCS konumunu elle vererek
    test ediyoruz (test node'da gcs_lat/lon parametreyle verilmedi)."""
    _reset(node)
    node.positions["gcs"] = _YAKIN
    assert node._gcs_isolated() is False  # en az bir drone menzilde
    # GCS bir drone'a ulaşabildiği sürece izole değil (multi-hop yayar)
    node.positions["drone1"] = _UZAK
    assert node._gcs_isolated() is False
    # Ancak TÜM droneler menzil dışıysa GCS izole → komut mesh'e giremez
    node.positions["drone2"] = _UZAK
    node.positions["drone3"] = _UZAK
    assert node._gcs_isolated() is True
