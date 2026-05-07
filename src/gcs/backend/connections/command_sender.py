"""MAVLink komut gönderici — listener ile aynı UDP soketini paylaşır.

PX4 SITL ve gerçek Pixhawk için:
  - takeoff:  arm → MAV_CMD_NAV_TAKEOFF (altitude param ile)
              SET_MODE AUTO.TAKEOFF tek başına yetmez, drone armed olmalı.
  - land:     SET_MODE AUTO.LAND moduna geç
  - rtl:      SET_MODE AUTO.RTL moduna geç
  - arm:      MAV_CMD_COMPONENT_ARM_DISARM param1=1
  - disarm:   MAV_CMD_COMPONENT_ARM_DISARM param1=0 (force=21196 opsiyonel)

ÖNEMLİ — multi-vehicle UDP routing:
  mavutil udpin server modunda last_address'e (sete) yazıyor; aynı socket'ten
  3 PX4 instance'ına bağlıyız. Her sysid'in kendi UDP endpoint'ini takip
  ediyoruz; gönderirken last_address'i o sysid'in adresine ayarlayıp tek
  endpoint'e yazıyoruz. Listener her HEARTBEAT'te endpoint'i günceller.
"""

import logging
import threading
import time
from typing import Optional

from pymavlink import mavutil

logger = logging.getLogger(__name__)


# PX4 custom_mode encoding: (main << 16) | (sub << 24)
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
    ARM_TAKEOFF_DELAY_SEC = 0.6  # arm sonrası takeoff'a yetecek bekleme

    def __init__(self, link: mavutil.mavfile, send_lock: threading.Lock):
        self.link = link
        self.send_lock = send_lock

    # --- Endpoint helpers (UDP routing) ------------------------------------

    def _scope_send_to(self, sysid: int) -> bool:
        """Listener'ın takip ettiği per-sysid endpoint'e last_address'i sabitle.

        Sadece udpin (server) modunda anlamlı. Eğer listener endpoint biliyorsa
        True döner ve last_address override edilir; bilinmiyorsa False döner
        (caller bilecek ki broadcast olur).
        """
        get_endpoint = getattr(self.link, "get_sysid_endpoint", None)
        if get_endpoint is None:
            return False
        addr = get_endpoint(sysid)
        if addr is None:
            return False
        # mavutil udpin: last_address bir liste olabilir. Tek hedefe sabitle.
        if hasattr(self.link, "last_address"):
            self.link.last_address = addr
        return True

    # --- Low-level senders --------------------------------------------------

    def _set_mode(self, sysid: int, custom_mode: int) -> None:
        with self.send_lock:
            self._scope_send_to(sysid)
            self.link.mav.set_mode_send(
                sysid,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                custom_mode,
            )
        logger.info("→ sysid=%d SET_MODE custom=%#x", sysid, custom_mode)

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
                sysid, self.DEFAULT_TARGET_COMPONENT,
                command, confirmation,
                p1, p2, p3, p4, p5, p6, p7,
            )
        logger.info(
            "→ sysid=%d CMD_LONG cmd=%d params=(%g,%g,%g,%g,%g,%g,%g)",
            sysid, command, p1, p2, p3, p4, p5, p6, p7,
        )

    # --- Public commands ----------------------------------------------------

    def takeoff(self, sysid: int, altitude_m: Optional[float] = None) -> None:
        """Drone'u arm et + AUTO.TAKEOFF moduna geçir.

        Bu, PX4 `commander takeoff` shell komutunun MAVLink üzerinden eşdeğeri:
          1. MAV_CMD_COMPONENT_ARM_DISARM p1=1            → motor kilidini aç
          2. ~0.6 sn bekle (PX4 arming state'i geçsin)
          3. SET_MODE AUTO.TAKEOFF                         → otonom kalkış başlatır
        Altitude PX4'ün MIS_TAKEOFF_ALT param'ı ile belirlenir (varsayılan 2.5m).
        """
        del altitude_m  # PX4 MIS_TAKEOFF_ALT param'ı ile yönetilir.
        # 1. Arm
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1.0,
        )
        time.sleep(self.ARM_TAKEOFF_DELAY_SEC)
        # 2. Mode change → AUTO.TAKEOFF
        self._set_mode(sysid, _px4_custom_mode(PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_TAKEOFF))

    def land(self, sysid: int) -> None:
        self._set_mode(sysid, _px4_custom_mode(PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_LAND))

    def rtl(self, sysid: int) -> None:
        self._set_mode(sysid, _px4_custom_mode(PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_RTL))

    def loiter(self, sysid: int) -> None:
        self._set_mode(sysid, _px4_custom_mode(PX4_CUSTOM_MAIN_AUTO, PX4_AUTO_SUB_LOITER))

    def arm(self, sysid: int, force: bool = False) -> None:
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1.0,
            p2=21196.0 if force else 0.0,
        )

    def disarm(self, sysid: int, force: bool = False) -> None:
        """Acil dur = force disarm (havadaysa drone düşer!)."""
        self._command_long(
            sysid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=0.0,
            p2=21196.0 if force else 0.0,
        )
