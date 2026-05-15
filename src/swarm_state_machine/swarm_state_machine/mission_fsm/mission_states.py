"""mission_states.py — MissionState, MissionType, QrTaskStep sabitleri.

Bu dosya yalnizca sabit tanimlarindan olusur; hicbir mantik icermez.
Diger tum dosyalar buradan import eder.
"""

from enum import IntEnum


# =============================================================================
# MISSION STATE
# =============================================================================

class MissionState(IntEnum):
    """
    Suru geneli gorev durum makinesi sabitleri.

    Bu FSM tek bir drone'u degil, TUM SURUYU temsil eder.
    Bireysel drone durumlari agent_fsm/agent_states.py'dadir.

    Sayilar ROS2 topic'te UInt8 olarak yayinlanir; abone node'lar
    (formation_control, mission1_dynamic_swarm vb.) bu sayilari okur.
    """

    UNKNOWN = 0             # baslangic degeri; node ilk tick'te IDLE'a gecer
    IDLE = 1                # GCS'ten START bekleniyor
    PREFLIGHT = 2           # tum ajanlar saglikli mi, GPS var mi?
    SYNCHRONIZED_TAKEOFF = 3  # EVENT_MISSION_STARTED yayinlandi; suru kalkiyor
    NAVIGATE_TO_QR = 4      # suru QR noktasina dogru ilerliyor
    EXECUTE_QR_TASK = 5     # QR'dan okunan alt gorevler sirasyla calistirilyor
    WAIT_AT_QR = 6          # QR'in wait_s suresi kadar bekleniyor
    ROTATE_TO_NEXT = 7      # formasyon bir sonraki QR yonune dondurulüyor
    SEMI_AUTONOMOUS = 8     # Gorev 2: GCS joystick ile suru yonlendiriliyor
    RETURN_HOME = 9         # RTL tetiklendi; suru baslangic noktasina doniyor
    LANDING = 10            # surunun tamaminın inisi izleniyor
    MISSION_COMPLETE = 11   # tum suru indi, gorev basariyla tamamlandi
    ABORTED = 12            # gorev iptal edildi (timeout, ariza veya GCS komutu)
    PAUSED = 13             # GCS PAUSE komutu; suru hover'da, RESUME bekleniyor


# =============================================================================
# MISSION TYPE
# =============================================================================

class MissionType(IntEnum):
    """
    TriggerMission.srv'deki mission_id alaniyla birebir eslesir.

    GCS START komutuyla birlikte mission_id gonderir.
    SYNCHRONIZED_TAKEOFF'ta bu degere bakilarak sonraki state secilir:
      DYNAMIC_SWARM   -> NAVIGATE_TO_QR
      SEMI_AUTONOMOUS -> SEMI_AUTONOMOUS
    """

    UNKNOWN = 0         # henuz belirlenmedi
    DYNAMIC_SWARM = 1   # Gorev 1: QR okuma + dinamik suru formasyon degisimi
    SEMI_AUTONOMOUS = 2  # Gorev 2: GCS joystick ile yari otonom suru kontrolu


# =============================================================================
# QR TASK STEP
# =============================================================================

class QrTaskStep(IntEnum):
    """
    EXECUTE_QR_TASK asamasindaki sirali alt gorev adimlari.

    Sartname 5.1.2 sirasi: FORMATION -> MANEUVER -> ALTITUDE -> DETACH

    Hangi alan aktifse o adim calisir:
      QRMissionData.formation_active -> FORMATION
      QRMissionData.maneuver_active  -> MANEUVER
      QRMissionData.altitude_active  -> ALTITUDE
      QRMissionData.detach_active    -> DETACH

    Adim tamamlanma sinyalleri:
      FORMATION / ALTITUDE -> formation_control  -> EVENT_FORMATION_REACHED
      MANEUVER             -> maneuver_executor  -> EVENT_MANEUVER_COMPLETED
      DETACH               -> agent_fsm          -> EVENT_AGENT_DETACHED
    """

    NONE = 0       # henuz adim secilmedi
    FORMATION = 1  # formasyon tipi degistiriliyor
    MANEUVER = 2   # pitch/roll manevrasi
    ALTITUDE = 3   # irtifa degisimi
    DETACH = 4     # suruden birey ekleme veya cikarma
    DONE = 5       # tum aktif adimlar tamamlandi
