#!/usr/bin/env python3
"""preflight_check.py — CA testi ÖN-KONTROL kapısı (test başlamadan).

Çarpışma önleme testi, dronlar gerçekten uçar/geçerli durumda DEĞİLKEN
başlatılırsa sahte sonuç verir: safety_monitor geçersiz telemetriyi atlar,
ölçüm yapamaz, sen "CA çalışmadı" sanırsın. En sinsi tuzak CPU yükü →
EKF diverge → xy_valid düşer ([[cpu-yuku-ekf-kalkis-sapmasi]]).

Bu node TEK İŞ yapar: her drone için bir telemetri örneği bekler ve
şu kapıları kontrol eder; HEPSİ geçerse exit 0, biri kalırsa exit 1.

KAPILAR (CA'nın çalışması için ZORUNLU önkoşullar):
  - xy_valid && z_valid     : CA yalnızca _pos_ok ise devreye girer
                              (collision_avoidance_node._tick, satır 327)
  - GPS var (lat/lon != 0)  : mesafe GPS/haversine ile ölçülür, local değil
                              ([[mesafe-olcumu-gps-ile-local-degil]])
  - irtifa >= altitude_gate : gate altında CA pasif/passthrough
                              (collision_avoidance_node, altitude_gate_m)
  - state uçuşta (IN_SWARM)  : yerde/arming dronla head-on olmaz

KULLANIM:
    python3 preflight_check.py --ros-args \\
        -p agent_ids:="[1,2,3]" -p altitude_gate_m:=3.0 -p timeout_s:=15.0
    echo $?   # 0 = hazır, 1 = değil
"""

import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import AgentStatus


_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# Head-on için "uçuşta" sayılan state'ler (telemetri uçarken bu enum'larda olur).
_FLYING_STATES = frozenset({
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
})

_STATE_AD = {
    0: 'UNKNOWN', 1: 'IDLE', 2: 'ARMING', 3: 'ARMED', 4: 'TAKEOFF',
    5: 'IN_SWARM', 6: 'EXEC_TASK', 7: 'DETACHED', 8: 'PREC_LAND',
    9: 'WAIT_REJOIN', 10: 'REJOINING', 11: 'RTL', 12: 'LANDING',
    13: 'LANDED', 14: 'FAILSAFE', 15: 'STANDBY',
}


class PreflightCheck(Node):
    """Her drone'dan bir telemetri toplar, hazırlık kapılarını uygular."""

    def __init__(self) -> None:
        super().__init__('preflight_check')
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('altitude_gate_m', 3.0)
        self.declare_parameter('timeout_s', 15.0)
        # Sadece head-on'a giren dronları zorunlu say; nötr dron uçmuyorsa
        # testi bloklamasın (yine de raporlanır).
        self.declare_parameter('required_ids', [0])

        gp = self.get_parameter
        self._ids = [int(x) for x in gp('agent_ids').value]
        self._gate = float(gp('altitude_gate_m').value)
        self._timeout = float(gp('timeout_s').value)
        req = [int(x) for x in gp('required_ids').value if int(x) > 0]
        self._required = set(req) if req else set(self._ids)

        self._latest: dict[int, AgentStatus] = {}
        for did in self._ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/drone{did}/telemetry',
                lambda msg, d=did: self._on_status(d, msg),
                _QOS,
            )

        self.get_logger().info(
            f'preflight_check: agent_ids={self._ids} '
            f'gate={self._gate}m zorunlu={sorted(self._required)} '
            f'timeout={self._timeout}s'
        )

    def _on_status(self, did: int, msg: AgentStatus) -> None:
        self._latest[did] = msg

    def _evaluate_one(self, did: int) -> tuple[bool, str]:
        """Tek drone'u kontrol et → (geçti, açıklama)."""
        msg = self._latest.get(did)
        if msg is None:
            return False, 'telemetri YOK (node yayınlamıyor?)'

        problems = []
        if not msg.xy_valid:
            problems.append('xy_valid=F (EKF/CPU?)')
        if not msg.z_valid:
            problems.append('z_valid=F')
        if msg.lat_deg == 0.0 and msg.lon_deg == 0.0:
            problems.append('GPS yok (lat/lon=0)')
        alt = -float(msg.pos_z)
        if alt < self._gate:
            problems.append(f'irtifa {alt:.1f}m < gate {self._gate:.1f}m')
        # State BİLGİ amaçlı (bloke etmez): manuel sync_takeoff PX4'ü doğrudan
        # arm eder, FSM'i IN_SWARM'a sürmez → state=0 olabilir. "Uçuyor" kanıtı
        # irtifa>gate'tir, FSM state değil. State sadece raporlanır.
        state = int(msg.state)
        sn = _STATE_AD.get(state, str(state))
        flying = ' (uçuşta✓)' if state in _FLYING_STATES else ' (FSM beklemede)'

        if problems:
            return False, '; '.join(problems)
        return True, f'irtifa={alt:.1f}m armed={bool(msg.armed)} state={sn}{flying} OK'

    def run(self) -> int:
        """Tüm zorunlu dronlar geçene kadar (ya da timeout) bekle → exit kodu."""
        deadline = time.monotonic() + self._timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            # Tüm zorunlu dronlar geçer durumdaysa erken çık.
            if all(self._evaluate_one(d)[0] for d in self._required):
                break

        print('\n  ─── ÖN-KONTROL ───')
        all_required_ok = True
        for did in self._ids:
            ok, why = self._evaluate_one(did)
            mark = '✓' if ok else '✗'
            req = ' [zorunlu]' if did in self._required else ' [nötr]'
            print(f'   {mark} drone{did}{req}: {why}')
            if did in self._required and not ok:
                all_required_ok = False

        if all_required_ok:
            print('  ─── HAZIR: head-on testi başlatılabilir ───\n')
            return 0
        print('  ─── HAZIR DEĞİL: test İPTAL (yukarıdaki ✗ giderilmeli) ───')
        print('      İpucu: Gazebo GUI/kamera köprüsünü kapat (CPU→EKF), '
              'dronların IN_SWARM ve hedef irtifada olduğunu doğrula.\n')
        return 1


def main(args=None) -> int:
    rclpy.init(args=args)
    node = PreflightCheck()
    try:
        code = node.run()
    except KeyboardInterrupt:
        code = 1
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass
    return code


if __name__ == '__main__':
    sys.exit(main())
