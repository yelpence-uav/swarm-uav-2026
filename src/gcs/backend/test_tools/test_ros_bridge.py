"""ros_bridge bağımsız smoke test.

mock_agent_publisher arka planda çalışıyorken bu script'i 5sn çalıştırınca
'AgentStatus drone=N ...' log satırlarını görmelisin (debug seviyesinde).

Çalıştırma (container içinde):
  source /opt/ros/jazzy/setup.bash
  source /home/yelpence/ros2_ws/install/setup.bash
  source /home/yelpence/venv/bin/activate
  cd /home/yelpence/ros2_ws/src/gcs
  python3 -m backend.test_tools.test_ros_bridge
"""

import logging
import time

from backend.connections.ros_bridge import RosBridge
from backend.core.alert_manager import AlertManager
from backend.core.state_store import StateStore


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    log = logging.getLogger("smoke")

    store = StateStore(offline_timeout_sec=3.0)
    store.register_drone(1, "Drone 1", sysid=1)
    store.register_drone(2, "Drone 2", sysid=2)
    store.register_drone(3, "Drone 3", sysid=3)
    alerts = AlertManager()

    counts = {1: 0, 2: 0, 3: 0}
    swarm_state_count = [0]

    def on_status(drone_id, msg):
        counts[drone_id] += 1

    def on_swarm(snapshot):
        swarm_state_count[0] += 1

    bridge = RosBridge(
        drone_ids=[1, 2, 3],
        store=store,
        alerts=alerts,
        on_agent_status=on_status,
        on_swarm_state=on_swarm,
    )
    bridge.start()

    log.info("8 saniye dinleniyor (event'ler 4 sn aralıkla geliyor)...")
    time.sleep(8)
    bridge.stop()

    log.info("=" * 60)
    log.info("AgentStatus mesaj sayıları: %s (her drone ~40)", counts)
    log.info(
        "SwarmState mesaj sayısı: %d (~16 beklenir, 2Hz × 8sn)",
        swarm_state_count[0],
    )

    log.info("Son SwarmState snapshot:")
    ss = bridge.get_swarm_state()
    if ss:
        log.info(
            "  swarm_state=%d leader=%d active=%d formation=%d mission=%s",
            ss["swarm_state"],
            ss["leader_id"],
            ss["active_agent_count"],
            ss["active_formation"],
            ss["mission_active"],
        )
        log.info(
            "  formation_max_error=%.2fm avg_error=%.2fm",
            ss["formation_max_error_m"],
            ss["formation_avg_error_m"],
        )
        log.info(
            "  current_qr=%d active_mission=%s",
            ss["current_qr_id"],
            ss["active_mission"],
        )
    else:
        log.info("  (henüz SwarmState mesajı gelmedi)")

    log.info("AlertManager event'leri (event bus -> push_event):")
    snapshot_alerts = alerts.evaluate(store.snapshot())
    for a in snapshot_alerts:
        log.info(
            "  [%s] drone=%d code=%s - %s",
            a.severity,
            a.drone_id,
            a.code,
            a.message,
        )

    log.info("StateStore drone snapshot:")
    for d in store.snapshot():
        log.info(
            "  %s | conn=%s armed=%s mode=%s state=%d role=%d "
            "pos=(%.1f,%.1f,%.1f) lat=%.5f lon=%.5f alt=%.1fm "
            "bat=%.1f%% gps=%d(%dsat) origin_sync=%s",
            d.name,
            d.connected,
            d.armed,
            d.mode,
            d.state,
            d.role,
            d.pos_x,
            d.pos_y,
            d.pos_z,
            d.lat,
            d.lon,
            d.alt_m,
            d.battery_percent,
            d.gps_fix_type,
            d.gps_satellites,
            d.origin_synced,
        )


if __name__ == "__main__":
    main()
