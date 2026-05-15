"""mission_states.py — MissionState, MissionType, QrTaskStep sabitleri.

BU DOSYA SADECE SABIT TANIMLARINDAN OLUŞUR.
Hiçbir mantık (logic) içermez — sadece sayılara isim verir.
Diğer tüm dosyalar buradan import eder.

IntEnum nedir?
  Normal Python enum'dan farkı: integer gibi davranır.
  Örnek: MissionState.IDLE == 1       → True
         int(MissionState.IDLE)       → 1
  ROS2 UInt8 mesajına yazarken bunu kullanırız:
    msg.data = int(ctx.state)  # MissionState → sayıya çevir
"""

from enum import IntEnum   # integer gibi davranan enum — sayıya çevrilebilir


# =============================================================================
# MİSSION STATE — görevin büyük resmi
# =============================================================================

class MissionState(IntEnum):
    """SÜRÜ GENELİ görev durum makinesi sabitleri.

    Bu FSM tek bir drone'u değil, TÜM SÜRÜYÜ temsil eder.
    Bireysel drone durumları agent_fsm/agent_states.py'dadır (AgentState).

    Mission FSM "sürü ne yapıyor?" sorusuna cevap verir:
      NAVIGATE_TO_QR → sürünün tamamı QR noktasına gidiyor
      EXECUTE_QR_TASK → sürünün tamamı QR görevini icra ediyor
      LANDING → sürünün tamamının inişi bekleniyor

    Sayılar önemli: ROS2 topic'te UInt8 olarak yayınlanır, bu sayılar abone
    node'lar tarafından okunur (formation_control, mission1_dynamic_swarm vb.)
    """

    UNKNOWN = 0   # başlangıç değeri; node ilk tick'te IDLE'a geçer
    IDLE = 1   # GCS'ten START bekleniyor; sürü yerde bekler
    PREFLIGHT = 2   # sürüdeki tüm ajanlar sağlıklı mı, GPS var mı? kontrol aşaması
    SYNCHRONIZED_TAKEOFF = 3  # EVENT_MISSION_STARTED yayınlandı; sürünün tamamı kalkıyor
    NAVIGATE_TO_QR = 4   # sürünün tamamı QR noktasının koordinatına doğru ilerliyor
    EXECUTE_QR_TASK = 5   # QR'dan okunan alt görevler sürü genelinde sırayla çalışıyor
    WAIT_AT_QR = 6   # QR'ın wait_s süresi kadar sürünün tamamı QR noktasında bekliyor
    ROTATE_TO_NEXT = 7   # sürü formasyonu bir sonraki QR yönüne döndürülüyor
    SEMI_AUTONOMOUS = 8   # Görev 2: GCS joystick ile sürünün tamamı yönlendiriliyor
    RETURN_HOME = 9   # RTL tetiklendi; sürünün tamamı başlangıç noktasına dönüyor
    LANDING = 10  # sürünün tamamının inişi izleniyor
    MISSION_COMPLETE = 11  # sürünün tamamı indi, görev başarıyla tamamlandı
    ABORTED = 12  # görev iptal edildi (timeout, arıza veya GCS abort komutu)
    PAUSED = 13  # GCS PAUSE komutu geldi; sürü hover'da bekliyor, RESUME bekleniyor


# =============================================================================
# MİSSION TYPE — hangi görev çalışıyor?
# =============================================================================

class MissionType(IntEnum):
    """TriggerMission.srv'deki mission_id alanıyla birebir eşleşir.

    GCS START komutuyla birlikte mission_id gönderir.
    Bu değer ctx.mission_type'a yazılır.
    SYNCHRONIZED_TAKEOFF'ta bu değere bakılarak:
      DYNAMIC_SWARM  → NAVIGATE_TO_QR'a geçilir
      SEMI_AUTONOMOUS → SEMI_AUTONOMOUS'a geçilir
    """

    UNKNOWN = 0   # henüz belirlenmedi; IDLE state'inde bu değerdedir
    DYNAMIC_SWARM = 1   # Görev 1: QR okuma + dinamik sürü formasyon değişimi
    SEMI_AUTONOMOUS = 2   # Görev 2: GCS joystick ile yarı otonom sürü kontrolü


# =============================================================================
# QR TASK STEP — EXECUTE_QR_TASK içindeki alt adımlar
# =============================================================================

class QrTaskStep(IntEnum):
    """EXECUTE_QR_TASK aşamasındaki sıralı alt görev adımları.

    Şartname 5.1.2 sırası: FORMATION → MANEUVER → ALTITUDE → DETACH

    Bir QR mesajı aynı anda birden fazla bölüm içerebilir.
    Örnek: formation_active=True, maneuver_active=True → önce FORMATION, sonra MANEUVER

    Hangi alan aktif ise o adım çalışır:
      QRMissionData.formation_active → FORMATION adımı var mı?
      QRMissionData.maneuver_active  → MANEUVER  adımı var mı?
      QRMissionData.altitude_active  → ALTITUDE  adımı var mı?
      QRMissionData.detach_active    → DETACH    adımı var mı?

    Adım tamamlanma sinyalleri (kim yayınlar → hangi event):
      FORMATION / ALTITUDE → formation_control    → EVENT_FORMATION_REACHED
      MANEUVER             → maneuver_executor    → EVENT_MANEUVER_COMPLETED
      DETACH               → agent_fsm            → EVENT_AGENT_DETACHED
    """

    NONE = 0   # henüz adım seçilmedi; EXECUTE_QR_TASK'a girilmemiş demektir
    FORMATION = 1   # formasyon tipi değiştiriliyor (ör. okbaşı → V)
    MANEUVER = 2   # pitch/roll manevrası — sürü merkezi sabit kalır (şartname sırası: 2.)
    ALTITUDE = 3   # irtifa değişimi — yüksel veya alçal (şartname sırası: 3.)
    DETACH = 4   # sürüden birey ekleme veya çıkarma
    DONE = 5   # tüm aktif adımlar tamamlandı; ana state geçişi bekleniyor
