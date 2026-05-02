from enum import IntEnum  # IntEnum: hem sayı hem enum özelliği taşır, ROS mesajlarıyla birebir eşleşir


class AgentState(IntEnum):
    """Ajan FSM durum sabitleri. AgentStatus.msg STATE_* ile birebir eşleşir."""

    # Her durum bir tam sayıya karşılık gelir (0'dan 15'e)
    # Bu sayılar AgentStatus.msg'deki STATE_* sabitleriyle aynı olmalı
    UNKNOWN = 0           # Başlangıç: drone henüz ne durumda bilinmiyor
    IDLE = 1              # Bekliyor: uçuşa hazır değil, komut bekliyor
    ARMING = 2            # Motor kilidi açılıyor (arm ediliyor)
    ARMED = 3             # Motorlar hazır ama drone henüz kalkmadı
    TAKEOFF = 4           # Kalkış yapıyor, hedef irtifaya çıkıyor
    IN_SWARM = 5          # Sürüde uçuyor, formasyon koruyor
    EXECUTING_TASK = 6    # Görev yapıyor (manevra, rotasyon, QR tarama vs.)
    DETACHED = 7          # Sürüden ayrıldı, hassas inişe geçecek
    PRECISION_LANDING = 8  # Hassas iniş yapıyor (belirli bir noktaya)
    WAITING_REJOIN = 9    # Yerde bekliyor, sürüye katılma izni bekliyor
    REJOINING = 10        # Sürüye geri katılıyor
    RETURN_HOME = 11      # Eve dönüyor (RTL - Return To Launch)
    LANDING = 12          # Normal iniş yapıyor
    LANDED = 13           # İndi, disarm edildi
    FAILSAFE = 14         # ACİL DURUM: kritik hata, güvenli moda geçildi
    STANDBY = 15          # Bekleme modu: pasif, göreve hazır değil


class AgentRole(IntEnum):
    """Ajan rol sabitleri. AgentStatus.msg ROLE_* ile birebir eşleşir."""

    # Drone'un sürüdeki rolünü belirler
    UNKNOWN = 0    # Rol henüz atanmadı
    LEADER = 1     # Lider: sürüyü yönlendiren, diğerleri onu takip eder
    FOLLOWER = 2   # Takipçi: liderin arkasında formasyon uçuşu yapar
    STANDBY = 3    # Pasif: sürüye dahil değil, bekliyor
    DETACHED = 4   # Kopuk: sürüden ayrılmış, bağımsız hareket ediyor


class FlightMode(IntEnum):
    """PX4 uçuş modu sabitleri. AgentStatus.msg FLIGHT_MODE_* ile eşleşir."""

    # PX4'ün nav_state değerlerinden gelen uçuş modları
    UNKNOWN = 0       # Bilinmeyen mod
    MANUAL = 1        # Pilot tamamen manuel kontrol ediyor
    ALTCTL = 2        # İrtifa kontrolü: pilot yatay, sistem dikey kontrol
    POSCTL = 3        # Pozisyon kontrolü: joystick bırakınca sabit kalır
    OFFBOARD = 4      # Dış bilgisayar kontrol ediyor (bizim kodumuz)
    AUTO_MISSION = 5  # Önceden programlanmış görev çalışıyor
    AUTO_LOITER = 6   # Havada sabit bekliyor (loiter)
    AUTO_RTL = 7      # Otomatik eve dönüş başladı
    AUTO_LAND = 8     # Otomatik iniş yapıyor
    ACRO = 9          # Akrobasi modu: sadece açısal hız kontrolü
    STABILIZED = 10   # Stabilize: bırakınca düzlenir ama sürüklenir


# Bu durumlar çarpışma önleme hesabına (ORCA/APF) dahil edilmez
# Çünkü bu durumlardaki drone'lar ya yerde ya da bağımsız hareket eder
AVOIDANCE_EXCLUDE_STATES = frozenset({
    AgentState.DETACHED,           # Sürüden ayrılmış, bağımsız
    AgentState.PRECISION_LANDING,  # Hassas iniş, kendi rotasında
    AgentState.LANDED,             # Yerde, zaten hareket etmiyor
    AgentState.FAILSAFE,           # Acil durum, PX4 kontrolünde
})
