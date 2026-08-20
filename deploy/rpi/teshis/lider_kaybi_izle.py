#!/usr/bin/env python3
# Konteyner icinde kosar:  python3 lider_kaybi_izle.py <agent_id> <cikti> <sure_sn>
#
# P0.14 yer testinin OLCUM tarafi. Tek surecte, TEK SAATLE uc olayi kaydeder:
#
#   HB      /swarm/public/leader/heartbeat    lider kalp atisi gelisi
#   SECIM   /swarm/internal/election/result   BU ucagin kendi secim karari
#   DURUMk  /swarm/public/dronek/status       komsu DURUM gelisi
#
# NEDEN TEK SUREC: gecikme = (SECIM ani) - (son HB ani). Iki ayri aractan
# alinan zaman damgalari ayni saate oturmaz; gps_saat farki 3 sn altindaysa
# DOKUNMUYOR, yani Pi'ler arasi saat farki ±1.5 sn olabilir. Bu olcum bu
# yuzden tamamen TAKIPCI ucagin kendi saatinde yapilir; SSH/ag gecikmesi
# olcume hic girmez.
#
# DURUM kayitlari kanit icin: lider olduruldukten sonra komsu DURUM'unun
# AKMAYA DEVAM ettigini gosterir. Boylece tespit P0.14(b) bayatlik yolundan
# degil, tam da hedeflenen kalp atisi zaman asimi yolundan gelmis olur.
#
# QoS'lar consensus_node'un KENDI abonelikleriyle birebir ayni (TUZAKLAR 2.1:
# uyumsuzluk sessizdir — heartbeat RELIABLE, durum BEST_EFFORT):
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import AgentStatus, ElectionResult, LeaderHeartbeat

_HB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
_SECIM_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_DURUM_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


def main() -> None:
    aid = int(sys.argv[1])
    yol = sys.argv[2]
    sure = float(sys.argv[3])

    cikti = open(yol, 'a', buffering=1)  # satir tamponlu: olurse de satirlar diskte
    rclpy.init()
    dugum = Node('lider_kaybi_izle')

    def yaz(tur: str, ek: str) -> None:
        # wallclock + monotonic birlikte: wallclock okunabilirlik, monotonic
        # aritmetik icin (NTP/gps_saat sicramasi olcumu bozamasin).
        cikti.write('%s %.6f %.6f %s\n' % (tur, time.time(), time.monotonic(), ek))

    yaz('BASLA', 'aid=%d' % aid)

    dugum.create_subscription(
        LeaderHeartbeat, '/swarm/public/leader/heartbeat',
        lambda m: yaz('HB', 'lider=%d seq=%d' % (m.leader_id, m.sequence_num)),
        _HB_QOS,
    )
    dugum.create_subscription(
        ElectionResult, '/swarm/internal/election/result',
        lambda m: yaz('SECIM', 'yeni_lider=%d sebep=%d tetikleyen=%d tur=%d msj=%r'
                      % (m.new_leader_id, m.reason, m.triggered_by_agent_id,
                         m.election_round, m.message)),
        _SECIM_QOS,
    )
    for komsu in range(1, 4):
        if komsu == aid:
            continue
        dugum.create_subscription(
            AgentStatus, '/swarm/public/drone%d/status' % komsu,
            (lambda k: lambda m: yaz('DURUM%d' % k,
                                     'state=%d armed=%s' % (m.state, m.armed)))(komsu),
            _DURUM_QOS,
        )

    son = time.monotonic() + sure
    while time.monotonic() < son:
        rclpy.spin_once(dugum, timeout_sec=0.2)
    yaz('BITTI', '')


if __name__ == '__main__':
    main()
