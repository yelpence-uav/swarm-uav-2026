"""test_qos_contract.py - QoS kontrati testi."""

from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
from network_proxy import network_proxy_node as npn

_BEKLENEN = {
    "_STATUS_QOS": (
        ReliabilityPolicy.BEST_EFFORT,
        DurabilityPolicy.VOLATILE,
        10
    ),
    "_HEARTBEAT_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.VOLATILE,
        5
    ),
    "_STATE_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.VOLATILE,
        10
    ),
    "_CONTROL_QOS": (
        ReliabilityPolicy.BEST_EFFORT,
        DurabilityPolicy.VOLATILE,
        10
    ),
    "_EVENT_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.VOLATILE,
        10
    ),
    "_ELECTION_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.TRANSIENT_LOCAL,
        10
    ),
    "_ORIGIN_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.TRANSIENT_LOCAL,
        1
    ),
    "_FORMATION_QOS": (
        ReliabilityPolicy.RELIABLE,
        DurabilityPolicy.VOLATILE,
        10
    ),
}


def test_qos_kontrati_birebir():
    """Her QoS sabiti beklenen degerle birebir eslesmeli."""
    for isim, (rel, dur, depth) in _BEKLENEN.items():
        prof = getattr(npn, isim)
        assert prof.reliability == rel, f"{isim}: reliability drift"
        assert prof.durability == dur, f"{isim}: durability drift"
        assert prof.depth == depth, f"{isim}: depth drift"


def test_espnow_mtu_250():
    """ESP-NOW tek cerceve siniri 250 byte olmali."""
    assert npn._ESPNOW_MTU_BYTES == 250
