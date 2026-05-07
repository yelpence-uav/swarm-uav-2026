"""CommandGate kuyruklarını drain eden worker — drone başına ayrı thread.

Her drone için bir thread:
  while not stopped:
      cmd = gate.get(drone_id, timeout=0.5)
      if cmd: dispatch(sender, sysid, cmd)
"""

import logging
import threading

from backend.connections.command_sender import CommandSender
from backend.core.command_gate import Command, CommandGate

logger = logging.getLogger(__name__)


class CommandWorker:
    """Drone başına thread; gate'i sender'a bağlar."""

    def __init__(
        self,
        gate: CommandGate,
        sender: CommandSender,
        drone_id_to_sysid: dict[int, int],
    ):
        self.gate = gate
        self.sender = sender
        self.sysid_map = drone_id_to_sysid
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for drone_id in self.gate.drone_ids():
            t = threading.Thread(
                target=self._run,
                args=(drone_id,),
                daemon=True,
                name=f"cmd-worker-{drone_id}",
            )
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    def _run(self, drone_id: int) -> None:
        sysid = self.sysid_map.get(drone_id)
        if sysid is None:
            logger.error("worker: drone_id=%d için sysid yok", drone_id)
            return
        logger.info("worker başladı: drone=%d sysid=%d", drone_id, sysid)

        while not self._stop.is_set():
            cmd = self.gate.get(drone_id, timeout=0.5)
            if cmd is None:
                continue
            self._dispatch(sysid, cmd)

    def _dispatch(self, sysid: int, cmd: Command) -> None:
        try:
            action = cmd.action
            if action == "takeoff":
                self.sender.takeoff(sysid, cmd.params.get("altitude"))
            elif action == "land":
                self.sender.land(sysid)
            elif action == "rtl":
                self.sender.rtl(sysid)
            elif action == "loiter":
                self.sender.loiter(sysid)
            elif action == "arm":
                self.sender.arm(sysid, force=bool(cmd.params.get("force", False)))
            elif action == "disarm":
                self.sender.disarm(sysid, force=bool(cmd.params.get("force", False)))
            else:
                logger.warning("bilinmeyen action: %s (drone=%d)", action, cmd.drone_id)
        except Exception:
            logger.exception("worker dispatch hata: drone=%d action=%s", cmd.drone_id, cmd.action)
