# Copyright 2026 Yelpence
"""GCS heartbeat gonderici."""

import logging
import threading

from pymavlink import mavutil

logger = logging.getLogger(__name__)


class HeartbeatSender:
    """1Hz GCS heartbeat gönderir."""

    INTERVAL_SEC = 1.0

    def __init__(self, link: mavutil.mavfile, send_lock: threading.Lock):
        self.link = link
        self.send_lock = send_lock
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="gcs-heartbeat"
        )
        self._thread.start()
        logger.info("heartbeat sender başladı (1Hz)")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self.send_lock:
                    self.link.mav.heartbeat_send(
                        mavutil.mavlink.MAV_TYPE_GCS,
                        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                        0,
                        0,
                        mavutil.mavlink.MAV_STATE_ACTIVE,
                    )
            except Exception:
                logger.exception("heartbeat send hatası")
            self._stop.wait(self.INTERVAL_SEC)
