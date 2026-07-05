"""test_qos_contract.py — §3 QoS kontratı guard-testi (Kural 5).

§3 tablosu tek gerçektir. Herhangi bir QoS sabiti tablodan saparsa bu test
kırmızı olur → sessiz drift CI'da anında yakalanır. Değer değişecekse hem
kod hem bu tablo (ve esp32_bridge) birlikte güncellenmelidir.
"""

from rclpy.qos import DurabilityPolicy, ReliabilityPolicy

from network_proxy import network_proxy_node as npn

# (reliability, durability, depth) — §3 tablosuyla birebir.
_BEKLENEN = {
    "_STATUS_QOS": (ReliabilityPolicy.BEST_EFFORT, DurabilityPolicy.VOLATILE, 10),
    "_HEARTBEAT_QOS": (ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, 5),
    "_STATE_QOS": (ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, 10),
    "_CONTROL_QOS": (ReliabilityPolicy.BEST_EFFORT, DurabilityPolicy.VOLATILE, 10),
    "_EVENT_QOS": (ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, 10),
    "_ELECTION_QOS": (
        ReliabilityPolicy.RELIABLE, DurabilityPolicy.TRANSIENT_LOCAL, 10),
    "_ORIGIN_QOS": (
        ReliabilityPolicy.RELIABLE, DurabilityPolicy.TRANSIENT_LOCAL, 1),
    "_FORMATION_QOS": (
        ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, 10),
}


def test_qos_kontrati_birebir():
    """Her QoS sabiti §3'teki değerle birebir eşleşmeli."""
    for isim, (rel, dur, depth) in _BEKLENEN.items():
        prof = getattr(npn, isim)
        assert prof.reliability == rel, f"{isim}: reliability drift"
        assert prof.durability == dur, f"{isim}: durability drift"
        assert prof.depth == depth, f"{isim}: depth drift"


def test_espnow_mtu_250():
    """ESP-NOW tek çerçeve sınırı 250 byte olmalı."""
    assert npn._ESPNOW_MTU_BYTES == 250
