"""test_proxy_logic.py — proxy karar mantığı testleri (rclpy, spin YOK).

Deterministik: konumlar ya aynı (0 m → drop olasılığı 0, asla düşmez) ya da
1° uzak (~111 km → cutoff ötesi, hep düşer). Böylece rastgeleliğe gerek yok.
Relay olup olmadığı, gecikme kuyruğuna (_pending) mesaj eklendi mi ile ölçülür.
"""

import pytest
import rclpy

from swarm_interfaces.msg import (
    AgentStatus,
    QRMissionData,
    SwarmControlCommand,
    SwarmState,
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


def test_broadcast_uzak_alici_duser(node):
    _reset(node)
    node.positions["drone2"] = _UZAK
    assert node._broadcast_drop("drone1") is True


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
    node.unreachable_agents = {"drone2"}  # "gitmiş" alıcı worst-case'e girmez
    assert node._broadcast_drop("drone1") is False


# ---------------- reliability sınıfları (mesh retry hizası) ----------------
def test_control_uzakta_bile_iletilir(node):
    """KOMUT mesh'te kritik/retry → mesafe zarı YOK, hep geçer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_control(SwarmControlCommand())
    assert len(node._pending) == 1


def test_state_uzakta_dusurulur(node):
    """SWARM_STATE non-kritik → mesafe zarı VAR, uzakta düşer."""
    _reset(node)
    node.positions["drone2"] = _UZAK
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


def test_qr_uzakta_dusurulur(node):
    _reset(node)
    node.positions["drone2"] = _UZAK
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
