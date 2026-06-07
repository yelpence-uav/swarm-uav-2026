"""Komut otoritesi — drone başına sıralı kuyruk.

Aynı drone'a iki yerden komut gelirse race olmasın diye buradan tek tek geçer.
Worker thread'i `CommandWorker` (ayrı dosya) bu kuyruktan çekip CommandSender'a iletir.
"""

import logging
import threading
import queue
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Command:
    drone_id: int
    action: str           # "takeoff" | "land" | "rtl" | "arm" | "disarm" | "loiter"
    params: dict[str, Any] = field(default_factory=dict)


class CommandGate:
    """Drone başına Queue. submit() çabuk döner, worker drain eder."""

    QUEUE_MAXSIZE = 10

    def __init__(self) -> None:
        self._queues: dict[int, queue.Queue[Command]] = {}
        self._lock = threading.Lock()

    def register_drone(self, drone_id: int) -> None:
        with self._lock:
            if drone_id not in self._queues:
                self._queues[drone_id] = queue.Queue(maxsize=self.QUEUE_MAXSIZE)

    def submit(self, cmd: Command) -> bool:
        """Komutu kuyruğa al. Drone tanımlı değilse veya kuyruk doluysa False."""
        q = self._queues.get(cmd.drone_id)
        if q is None:
            logger.warning("submit: bilinmeyen drone_id=%d", cmd.drone_id)
            return False
        try:
            q.put_nowait(cmd)
            logger.info("submit OK: drone=%d action=%s params=%s",
                        cmd.drone_id, cmd.action, cmd.params)
            return True
        except queue.Full:
            logger.warning("submit FULL: drone=%d action=%s", cmd.drone_id, cmd.action)
            return False

    def drone_ids(self) -> list[int]:
        with self._lock:
            return list(self._queues.keys())

    def get(self, drone_id: int, timeout: float = 0.5) -> Command | None:
        """Worker thread çağırır. timeout sonra None döner."""
        q = self._queues.get(drone_id)
        if q is None:
            return None
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None
