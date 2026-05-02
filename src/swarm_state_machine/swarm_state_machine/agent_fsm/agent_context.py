"""
agent_context.py

Bir drone'un o anki TÜM bilgilerini tek bir yerde tutan veri yapısı.
Tıpkı bir drone'un "hafızası" gibi düşün:
- PX4'ten gelen sensör verileri burada saklanır
- FSM hangi durumda olduğu burada tutulur
- Sağlık kontrolleri burada yapılır
- Geçiş kararları bu verilerle alınır

Kaynak: swarm_interfaces/msg/AgentStatus.msg
"""

import time  # Zaman ölçümü için — timeout kontrollerinde kullanılır
from dataclasses import dataclass, field  # dataclass: otomatik __init__ oluşturur, field: özel başlangıç değerleri için
from .agent_states import AgentState, AgentRole, FlightMode  # Aynı paketteki durum tanımlarını içe aktar


@dataclass  # Bu dekoratör sayesinde tüm değişkenler otomatik olarak __init__'e eklenir
class AgentContext:
    """
    Tek bir drone'un tüm anlık durumunu tutar.

    Her drone için ayrı bir AgentContext nesnesi oluşturulur.
    agent_health_monitor bu sınıfı günceller.
    agent_fsm_node bu sınıfı okur ve AgentStatus.msg olarak yayınlar.
    """

    # =================================================================
    # KİMLİK
    # =================================================================
    agent_id: int  # Bu drone'un numarası (1, 2, 3...). Her drone benzersiz.

    # =================================================================
    # FSM DURUMU
    # Drone şu an hangi durumda ve ne rolde?
    # =================================================================
    state: AgentState = AgentState.UNKNOWN   # Başlangıçta bilinmiyor, ilk tick'te IDLE'a geçer
    role: AgentRole = AgentRole.UNKNOWN      # Rol atanana kadar bilinmiyor

    # =================================================================
    # BAĞLANTI DURUMU
    # Drone kimlerle iletişim kurabiliyör?
    # =================================================================
    px4_link_ok: bool = False   # PX4 uçuş kontrolcüsüyle bağlantı var mı? (Micro-XRCE-DDS üzerinden)
    gcs_link_ok: bool = False   # Yer kontrol istasyonuyla (GCS) bağlantı var mı?

    # =================================================================
    # ARM ve OFFBOARD DURUMU
    # Drone uçmaya hazır mı, kim kontrol ediyor?
    # =================================================================
    armed: bool = False                          # True = motorlar çalışıyor ve tehlikeli
    offboard_enabled: bool = False               # OFFBOARD modu etkinleştirildi mi?
    offboard_active: bool = False                # OFFBOARD modu şu an aktif mi? (PX4 onayladı mı?)
    flight_mode: FlightMode = FlightMode.UNKNOWN # PX4'ün şu anki uçuş modu (OFFBOARD, RTL, LAND vs.)
    pilot_override_active: bool = False          # Pilot joystick'e dokunduysa True — otomasyon durur

    # =================================================================
    # FAILSAFE ve GENEL SAĞLIK
    # =================================================================
    failsafe_active: bool = False  # PX4'ün kendi failsafe'i aktif mi?

    # =================================================================
    # BATARYA
    # Voltaj değeri kullanılır çünkü daha güvenilir — yüzde yanıltabilir
    # =================================================================
    battery_percent: float = 0.0    # Batarya yüzdesi (0-100), bilgi amaçlı
    battery_voltage_v: float = 0.0  # Anlık voltaj — kritik karar burada: düşükse FAILSAFE
    battery_current_a: float = 0.0  # Anlık akım (amper)

    # =================================================================
    # KONUM ve HIZ — Local NED Koordinat Sistemi
    # NED = North-East-Down (Kuzey-Doğu-Aşağı)
    # ÖNEMLİ: Z ekseni AŞAĞIYA pozitif!
    # Yani 20 metre yükseklikte uçan drone'un pos_z = -20.0
    # =================================================================
    pos_x: float = 0.0   # Kuzey yönünde konum (metre)
    pos_y: float = 0.0   # Doğu yönünde konum (metre)
    pos_z: float = 0.0   # Aşağı yönünde konum — yükseklik için -1 çarp!
    vel_x: float = 0.0   # Kuzey yönünde hız (m/s)
    vel_y: float = 0.0   # Doğu yönünde hız (m/s)
    vel_z: float = 0.0   # Dikey hız — pozitif = aşağı iniyor, negatif = yukarı çıkıyor

    # =================================================================
    # DRONE'UN DURUŞU (ATTITUDE)
    # =================================================================
    heading_deg: float = 0.0  # Hangi yöne bakıyor? (0=Kuzey, 90=Doğu, 180=Güney)
    roll_deg: float = 0.0     # Yan yatma açısı (derece)
    pitch_deg: float = 0.0    # Öne-arkaya eğilme açısı (derece)

    # =================================================================
    # GPS KALİTESİ
    # fix_type: 0=sinyal yok, 2=2D konum, 3=3D konum(yeterli), 6=RTK(mükemmel)
    # hdop: ne kadar küçükse o kadar iyi — 1.5'in altı olmalı
    # =================================================================
    gps_fix_type: int = 0    # GPS fix türü — en az 3 olmalı (preflight şartı)
    gps_hdop: float = 9.9    # Yatay hassasiyet — 1.5'in altında olmalı
    gps_satellites: int = 0  # Görünen uydu sayısı — en az 6 olmalı

    # =================================================================
    # GLOBAL KONUM (GPS koordinatları)
    # =================================================================
    lat_deg: float = 0.0     # Enlem (derece)
    lon_deg: float = 0.0     # Boylam (derece)
    alt_amsl_m: float = 0.0  # Deniz seviyesinden yükseklik (metre)

    # =================================================================
    # HOME KONUMU
    # Drone ilk arm edildiğinde bu konum kaydedilir
    # RTL (Return To Launch) bu noktaya döner
    # =================================================================
    home_set: bool = False          # Home konumu kaydedildi mi? RTL için şart!
    home_lat_deg: float = 0.0       # Home enlemi
    home_lon_deg: float = 0.0       # Home boylamı
    home_alt_amsl_m: float = 0.0    # Home irtifası

    # =================================================================
    # SENSÖR SAĞLIĞI
    # Bu üçü sağlıklı değilse drone kalkmamalı!
    # =================================================================
    imu_healthy: bool = False   # IMU (ivmeölçer + jiroskop) çalışıyor mu?
    mag_healthy: bool = False   # Manyetometre (pusula) çalışıyor mu?
    baro_healthy: bool = False  # Barometre (basınç irtifa sensörü) çalışıyor mu?

    # =================================================================
    # EKF2 ESTIMATOR (Genişletilmiş Kalman Filtresi)
    # PX4'ün sensörleri birleştirerek konum tahmini yapan algoritması
    # Bu olmadan drone nerede olduğunu bilemez!
    # =================================================================
    estimator_ok: bool = False   # EKF2 genel sağlık durumu
    xy_valid: bool = False       # Yatay konum tahmini güvenilir mi?
    z_valid: bool = False        # Dikey konum tahmini güvenilir mi?
    v_xy_valid: bool = False     # Yatay hız tahmini güvenilir mi?

    # =================================================================
    # SWARM ORIGIN SENKRONU
    # Tüm dronelerin aynı koordinat sistemini kullanması şart
    # Lider drone referans noktayı yayınlar, diğerleri senkronize olur
    # =================================================================
    origin_synced: bool = False   # Koordinat sistemi senkronize mi?
    origin_sequence: int = 0      # Kaçıncı origin mesajı alındı (güncelleme takibi için)

    # =================================================================
    # RC (UZAKTAN KUMANDA) ve GÜVENLİK
    # =================================================================
    rc_link_ok: bool = False                # RC kumanda bağlantısı var mı?
    kill_switch_active: bool = False        # Kill switch basıldı mı? — motorlar anında durur!
    rc_signal_failsafe_active: bool = False # RC sinyal kaybı failsafe aktif mi?

    # =================================================================
    # UÇUŞ STABİLİTESİ
    # agent_health_monitor son 2 saniyelik veriden hesaplar
    # =================================================================
    oscillation_detected: bool = False  # Drone sallanıyor mu? (attitude varyansı yüksekse)
    unstable_flight: bool = False       # Tehlikeli kararsız uçuş mu? (çok fazla sallanma veya hız)

    # =================================================================
    # STANDBY / SÜRÜYE KATILMA
    # =================================================================
    wants_to_join: bool = False  # Drone sürüye katılmak istiyor mu? (EVENT_AGENT_JOIN_REQUEST ile set edilir)
    ready_to_arm: bool = False   # PX4 preflight kontrollerini geçti mi? (pre_flight_checks_pass)

    # =================================================================
    # DURUM METNİ
    # GCS ekranında gösterilir, log'a yazılır
    # =================================================================
    status_text: str = ""  # İnsan tarafından okunabilir durum açıklaması

    # =================================================================
    # AŞAĞIDAKILER AgentStatus.msg'DE YOK
    # Sadece FSM içinde kullanılır, dışarıya yayınlanmaz
    # =================================================================

    # SITL = Software In The Loop: gerçek donanım olmadan simülasyon
    # SITL modunda RC link kontrolü atlanır (simülasyonda RC yok)
    sitl_mode: bool = False

    # Görev başlatma sinyali geldiğinde True yapılır
    # ARMED durumunda bu True olursa TAKEOFF'a geçiş başlar
    mission_start_sequence_active: bool = False

    # Bu üçü TAKEOFF → IN_SWARM geçişi için şart:
    altitude_stable: bool = False    # İrtifa son 2 saniyedir sabit mi?
    attitude_stable: bool = False    # Duruş (roll/pitch) sabit mi?
    vertical_speed_ok: bool = False  # Dikey hız yeterince küçük mü?

    # Pilot joystick'e dokunduğunda True — o an otonom komutlar görmezden gelinir
    autonomous_control_paused: bool = False

    # Safety hold aktifken True — geçişler dondurulur, drone olduğu yerde bekler
    hold_active: bool = False

    # Bu state'e ne zaman girildi? — timeout kontrolü için
    # field(default_factory=...) her nesne için ayrı zaman alır
    state_entry_time: float = field(default_factory=time.monotonic)

    # Hedef kalkış irtifası (metre, pozitif yukarı)
    # TAKEOFF bu irtifaya ulaşınca IN_SWARM'a geçer
    target_altitude_m: float = 10.0

    # Hedef irtifaya ulaşıldığında True — agent_health_monitor hesaplar
    target_altitude_reached: bool = False

    # Kritik batarya voltajı eşiği (4S LiPo için varsayılan: 13.6V)
    # Bu eşiğin altına düşünce FAILSAFE tetiklenir
    battery_critical_voltage_v: float = 13.6

    # Jeofen (yasak bölge) ihlali — bu True olunca RTL başlatılır
    # Şartname kural 31: jeofen ihlali → RTL zorunlu
    geofence_violated: bool = False

    # Bir sonraki tick'te geçilmek istenen durum
    # Tick sonunda None yapılır — her tick'te sadece bir kez tüketilir
    pending_state: AgentState | None = None

    @property
    def healthy(self) -> bool:
        """
        Drone şu an uçuşa güvenli mi? — Hesaplanan (cached değil) özellik.

        Bu fonksiyon çağrıldığı anda tüm koşulları kontrol eder.
        Tüm koşullar True ise healthy=True döner.

        NOT: pilot_override bu hesaba dahil DEĞİL (pilot müdahalesi sağlık sorunu değil).
        NOT: oscillation ve unstable_flight tek başına healthy=False yapmaz.
        """
        return (
            self.px4_link_ok                           # PX4 ile bağlantı var
            and (self.rc_link_ok or self.sitl_mode)    # RC bağlı VEYA simülasyon modundayız
            and not self.kill_switch_active            # Kill switch basılı değil
            and not self.rc_signal_failsafe_active     # RC sinyal kaybı yok
            and self.imu_healthy                       # İvmeölçer/jiroskop çalışıyor
            and self.mag_healthy                       # Pusula çalışıyor
            and self.baro_healthy                      # Barometre çalışıyor
            and self.estimator_ok                      # EKF2 konum tahmini güvenilir
            and self.xy_valid                          # Yatay konum geçerli
            and self.z_valid                           # Dikey konum geçerli
            and self.v_xy_valid                        # Yatay hız geçerli
            and self.battery_voltage_v > self.battery_critical_voltage_v  # Batarya kritik değil
            and not self.failsafe_active               # PX4 failsafe aktif değil
        )

    def set_state(self, new_state: AgentState) -> None:
        """
        Drone'un durumunu değiştir ve timeout sayacını sıfırla.

        Timeout sayacı sıfırlanmazsa eski state'in süresi yeni state'e taşınır,
        bu da yanlış timeout'lara neden olur.
        """
        self.state = new_state                    # Yeni durumu kaydet
        self.state_entry_time = time.monotonic()  # Sayacı sıfırla: "şu an bu state'e girdik"

    def time_in_state(self) -> float:
        """
        Bu state'te kaç saniyedir?

        Timeout kontrollerinde kullanılır:
        - TAKEOFF 30 saniye geçerse FAILSAFE
        - LANDING 60 saniye geçerse FAILSAFE
        - RETURN_HOME 120 saniye geçerse safety_hold
        """
        return time.monotonic() - self.state_entry_time  # Şu an - giriş zamanı = geçen süre
