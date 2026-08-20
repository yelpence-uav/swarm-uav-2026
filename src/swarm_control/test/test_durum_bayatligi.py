# Copyright 2026 Yelpence
"""P0.14(b): bayatlik YANLIS AKISI olcuyordu.

Komsunun AgentStatus'unun IKI ayri mesh kaynagi var ve tazelikleri farkli:

    TIP_POSE   10 Hz  -> yalniz konum/hiz tasir AMA onbellekteki TUM kaydi
                         yeniden yayinliyor
    TIP_DURUM   1 Hz  -> state/healthy/estimator_ok BURADAN gelir, tekrari YOK

Tuketici tarafta `consensus_context.update_status` her mesajda `last_update`i
yaziyordu, yani `is_stale()` POSE akisinin tazeligini olcuyor, korudugu
SAGLIK alanlarininkini degil.

Sonucu: liderin DURUM paketleri mesh'te duserse (~%30 kayip) POSE gecmeye
devam eder ve takipciler onu SURESIZ "taze + ARMED + healthy" gorur.
Lider FAILSAFE'e dusse, disarm olsa, IDLE'a donse bile kimse fark etmez.

Kok neden koprude: hangi alanin hangi akistan geldigini yalnizca o biliyor.
"""

import time
from unittest.mock import MagicMock

from swarm_control.esp32_bridge.esp32_bridge_node import Esp32BridgeNode

from swarm_interfaces.msg import AgentStatus


def _kopru(bayat_s=5.0):
    n = object.__new__(Esp32BridgeNode)
    n._komsu_durum = {}
    n._komsu_durum_ts = {}
    n._durum_bayat_uyarildi = {}
    n._komsu_durum_bayat_s = bayat_s
    n._status_pubs = {}
    n.get_logger = MagicMock()
    n.get_clock = MagicMock()
    n.create_publisher = MagicMock(return_value=MagicMock())
    return n


def _status(healthy=True):
    s = AgentStatus()
    s.agent_id = 3
    s.healthy = healthy
    return s


def test_DURUM_tazeyken_healthy_korunur():
    n = _kopru()
    n._komsu_durum_ts[3] = time.monotonic()
    s = _status(healthy=True)
    n._yayinla_status(3, s)
    assert s.healthy is True


def test_DURUM_bayatken_healthy_DUSURULUR():
    """Asil ariza: POSE akmaya devam ederken saglik bilgisi bayatliyordu."""
    n = _kopru(bayat_s=5.0)
    n._komsu_durum_ts[3] = time.monotonic() - 9.0     # 9 sn once
    s = _status(healthy=True)
    n._yayinla_status(3, s)
    assert s.healthy is False, 'bayat DURUM hala healthy gosteriyor'


def test_HIC_DURUM_gelmediyse_healthy_dusurulur():
    """Yalniz POSE gelmis, hic DURUM gorulmemis komsu saglikli sayilmaz."""
    n = _kopru()
    s = _status(healthy=True)
    n._yayinla_status(3, s)
    assert s.healthy is False


def test_esik_ALTINDA_dusurulmez():
    """Tek tuk kayip healthy'yi dusurmemeli — 1 Hz'de bosluk normaldir."""
    n = _kopru(bayat_s=5.0)
    n._komsu_durum_ts[3] = time.monotonic() - 3.0     # esigin altinda
    s = _status(healthy=True)
    n._yayinla_status(3, s)
    assert s.healthy is True


def test_zaten_unhealthy_olan_bozulmaz():
    """Kapi yalniz healthy=True olani dusurur, tersini yapmaz."""
    n = _kopru()
    n._komsu_durum_ts[3] = time.monotonic()
    s = _status(healthy=False)
    n._yayinla_status(3, s)
    assert s.healthy is False


def test_uyari_bir_kez_basilir():
    """Log spam olmasin — 10 Hz POSE her seferinde uyarmamali."""
    n = _kopru(bayat_s=5.0)
    n._komsu_durum_ts[3] = time.monotonic() - 9.0
    for _ in range(5):
        n._yayinla_status(3, _status(healthy=True))
    assert n.get_logger.return_value.warning.call_count == 1
