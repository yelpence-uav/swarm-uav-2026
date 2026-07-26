# Copyright 2026 Yelpence
"""MAVLink komut gönderici."""

import logging
import threading
import time
from typing import Optional

from pymavlink import mavutil

logger = logging.getLogger(__name__)

PX4_CUSTOM_MAIN_AUTO = 4
PX4_AUTO_SUB_TAKEOFF = 2
PX4_AUTO_SUB_LOITER = 3
PX4_AUTO_SUB_RTL = 5
PX4_AUTO_SUB_LAND = 6


def _px4_custom_mode(main: int, sub: int = 0) -> int:
    return (main << 16) | (sub << 24)


class CommandSender:
    """Listener'ın MAVLink connection'ını paylaşarak komut yazar."""

    DEFAULT_TARGET_COMPONENT = 1
    ARM_TAKEOFF_DELAY_SEC = 0.6

    def __init__(self, link: mavutil.mavfile, send_lock: threading.Lock):
        self.link = link
        self.send_lock = send_lock

    def _scope_send_to(self, sysid: int) -> bool:
        """Hedef adresi sabitle."""
        get_endpoint = getattr(self.link, "get_sysid_endpoint", None)
        if get_endpoint is None:
            return False
        addr = get_endpoint(sysid)
        if addr is None:
            return False
        if hasattr(self.link, "last_address"):
            self.link.last_address = addr
        return True

    def _set_mode(self, sysid: int, custom_mode: int) -> None:
        with self.send_lock:
            self._scope_send_to(sysid)
            self.link.mav.set_mode_send(
                sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                custom_mode,
            )
        logger.info("-> sysid=%d SET_MODE custom=%#x", sysid, custom_mode)

    def _command_long(
        self,
        sysid: int,
        command: int,
        p1: float = 0,
        p2: float = 0,
        p3: float = 0,
        p4: float = 0,
        p5: float = 0,
        p6: float = 0,
        p7: float = 0,
        confirmation: int = 0,
    ) -> None:
        with self.send_lock:
            self._scope_send_to(sysid)
            self.link.mav.command_long_send(
                sysid,
                self.DEFAULT_TARGET_COMPONENT,
                command,
                confirmation,
                p1,
                p2,
                p3,
                p4,
                p5,
                p6,
                p7,
            )
        logger.info(
            "-> sysid=%d CMD_LONG cmd=%d params=(%g,%g,%g,%g,%g,%g,%g)",
            sysid,
            command,
            p1,
            p2,
            p3,
            p4,
            p5,
            p6,
            p7,
        )

    def takeoff(self, sysid: int, altitude_m: Optional[float] = None) -> None:
        """Kalkis komutu."""
        del altitude_m
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1.0,
        )
        time.sleep(self.ARM_TAKEOFF_DELAY_SEC)
        mode = _px4_custom_mode(
            PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_TAKEOFF
        )
        self._set_mode(sysid, mode)

    def land(self, sysid: int) -> None:
        mode = _px4_custom_mode(
            PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_LAND
        )
        self._set_mode(sysid, mode)

    def rtl(self, sysid: int) -> None:
        mode = _px4_custom_mode(
            PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_RTL
        )
        self._set_mode(sysid, mode)

    def loiter(self, sysid: int) -> None:
        mode = _px4_custom_mode(
            PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_LOITER
        )
        self._set_mode(sysid, mode)

    def arm(self, sysid: int, force: bool = False) -> None:
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1.0,
            p2=21196.0 if force else 0.0,
        )

    def disarm(self, sysid: int, force: bool = False) -> None:
        """Motor kilitleme komutu."""
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=0.0,
            p2=21196.0 if force else 0.0,
        )
