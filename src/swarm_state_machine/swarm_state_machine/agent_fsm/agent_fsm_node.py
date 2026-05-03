"""
agent_fsm_node.py

Tüm sistemin bir araya geldiği ROS2 node'u.
Bunu bir orkestra şefi gibi düşün:
- PX4'ten gelen telemetriyi dinler (keman, davul, flüt...)
- Swarm event bus'ını dinler (diğer dronelerden mesajlar)
- Her tick'te sağlık kontrolü yapar
- FSM geçişlerini değerlendirir
- Drone'un durumunu yayınlar

Her drone için ayrı bir instance çalışır:
    ros2 run swarm_state_machine agent_fsm_node --ros-args -p agent_id:=1

Kullanım:
    ros2 run swarm_state_machine agent_fsm_node \
        --ros-args -p agent_id:=1
"""

import rclpy                    # ROS2 Python istemci kütüphanesi
from rclpy.node import Node     # Tüm ROS2 node'larının temel sınıfı
from rclpy.qos import (
    # Mesaj kalıcılığı: VOLATILE (geçici) veya TRANSIENT_LOCAL (kalıcı)
    DurabilityPolicy,
    HistoryPolicy,       # Kaç mesaj saklanacak
    QoSProfile,          # Quality of Service profili — güvenilirlik ayarları
    # RELIABLE (kesin ulaşsın) veya BEST_EFFORT (ulaşmazsa geç)
    ReliabilityPolicy,
)

# Komut yayını için basit string mesajı (FSM → px4_bridge)
from std_msgs.msg import String

# Swarm sistemi mesaj ve servis tipleri
from swarm_interfaces.msg import AgentStatus, SwarmOrigin, SystemEvent
from swarm_interfaces.srv import AssignRole  # Rol atama servisi

# Kendi modüllerimiz
from .agent_context import AgentContext
from .agent_health_monitor import (
    HealthCheckResult, check as health_check
)
from .agent_states import AgentRole, AgentState, FlightMode
from .agent_transitions import evaluate_transitions
from .preflight_checker import run_preflight_checks

# =============================================================================
# QoS PROFİLLERİ
# QoS = Quality of Service: mesajların ne kadar güvenilir iletileceği
# =============================================================================

# SwarmOrigin: RELIABLE + TRANSIENT_LOCAL
# RELIABLE: Mesajın kesinlikle ulaşması şart (koordinat sistemi kritik)
# TRANSIENT_LOCAL: Sonradan bağlanan drone'lar son değeri alsın
_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,          # Kesinlikle ulaşsın
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    # Geç gelen drone'a son değeri ver
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# Kill switch FAILSAFE → LANDED geçişi için yere değme hız eşiği
# Bu kadar yavaşsa drone yere değmiş demektir
_GROUND_VEL_THR = 0.3  # 0.3 m/s altında → yerde sayılır


class AgentFsmNode(Node):
    """
    Tek bir drone'un FSM node'u.

    Bu sınıf tüm sistemi bir araya getirir:
    - PX4 telemetrisini dinler → AgentContext'i günceller
    - SystemEvent'leri dinler → pending_state'i günceller
    - Her tick'te sağlık kontrolü + geçiş değerlendirmesi yapar
    - AgentStatus yayınlar → diğer node'lar durumu görebilir

    Çıktı: /swarm/agent/{agent_id}/status (AgentStatus)
    Servis: /swarm/agent/{agent_id}/assign_role (AssignRole)
    Dinler: /swarm/events/system, /swarm/origin, PX4 telemetri
    Yayınlar: /swarm/events/system (FSM event'leri için)
    """

    def __init__(self) -> None:
        super().__init__('agent_fsm_node')  # ROS2 node adı: 'agent_fsm_node'

        self._declare_params()

        # Bu drone'un AgentContext nesnesini oluştur — tüm veriler burada
        # tutulur
        self._ctx = AgentContext(
            agent_id=self._agent_id,
            sitl_mode=self._sitl_mode,
            battery_critical_voltage_v=self._batt_crit_v,
            target_altitude_m=self._target_altitude_m,
        )

        self._px4_landed: bool = False  # VehicleLandDetected.landed
        # Önceki tick'te pilot override vardı mı? (kenar tespiti)
        self._prev_pilot_override: bool = False

        self._setup_publishers()   # Yayıncıları kur
        self._setup_subscribers()  # Abonelikleri kur
        self._setup_services()     # Servisleri kur

        # FSM tick timer: her 1/tick_hz saniyede bir _tick() çağır
        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick  # Örnek: 10 Hz → 0.1 saniyede bir
        )

        self.get_logger().info(
            f'AgentFsmNode başlatıldı: agent_id={self._agent_id}'
        )

    # ==========================================================================
    # BAŞLATMA YARDIMCI FONKSİYONLARI
    # ==========================================================================

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımla ve oku.

        Parametreler launch dosyasından veya komut satırından verilir:
        ros2 run swarm_state_machine agent_fsm_node --ros-args -p agent_id:=2
        """
        # Parametreleri varsayılan değerleriyle tanımla
        # Drone numarası
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('sitl_mode',
                               False)                   # Simülasyon modu
        self.declare_parameter(
            'battery_critical_voltage_v',
            13.6)  # Kritik batarya eşiği
        # FSM hızı (Hz)
        self.declare_parameter('tick_hz', 10.0)
        self.declare_parameter(
            'target_altitude_m',
            10.0)           # Hedef kalkış irtifası

        # Parametreleri oku ve instance değişkenlerine kaydet
        self._agent_id: int = (
            self.get_parameter('agent_id').value
        )
        self._sitl_mode: bool = (
            self.get_parameter('sitl_mode').value
        )
        self._batt_crit_v: float = (
            self.get_parameter('battery_critical_voltage_v').value
        )
        self._tick_hz: float = (
            self.get_parameter('tick_hz').value
        )
        self._target_altitude_m: float = (
            self.get_parameter('target_altitude_m').value
        )

    def _setup_publishers(self) -> None:
        """Yayıncıları (publisher) oluştur.

        Bu node iki topic'e yayın yapar:
        1. AgentStatus: drone'un tam durum raporu
        2. SystemEvent: FSM'in tetiklediği olaylar (landing, failsafe vs.)
        """
        aid = self._agent_id
        # Her drone'un kendi status topic'i var: /swarm/agent/1/status,
        # /swarm/agent/2/status...
        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/agent/drone{aid}/status',
            10,  # QoS depth: 10 mesaj tamponu
        )
        # Swarm event bus: tüm droneler ve swarm manager bu topic'i dinler
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/events/system',
            10,
        )
        # FSM komut publisher: px4_bridge bunu dinler ve PX4'e iletir
        # ("arm", "disarm", "takeoff:10.0", "land", "rtl", "offboard")
        self._command_pub = self.create_publisher(
            String,
            f'/swarm/agent/drone{aid}/commands',
            10,
        )

    def _setup_subscribers(self) -> None:
        """Abonelikleri (subscriber) oluştur.

        Bu node şu kaynaklardan veri alır:
        1. px4_bridge'den gelen telemetri (AgentStatus formatında)
        2. Swarm event bus
        3. Swarm origin (koordinat sistemi)
        """
        aid = self._agent_id

        # px4_bridge telemetrisi — AgentStatus'a maplenmiş
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{aid}/telemetry',
            self._on_telemetry,
            10,
        )

        # Swarm event bus — tüm dronelerden ve swarm manager'dan gelen olaylar
        self.create_subscription(
            SystemEvent,
            '/swarm/events/system',
            self._on_event,
            10,
        )

        # Swarm origin — lider drone'un yayınladığı referans koordinat sistemi
        # TRANSIENT_LOCAL: geç bağlanan drone'lar son değeri alır
        self.create_subscription(
            SwarmOrigin,
            '/swarm/origin',
            self._on_origin,
            _ORIGIN_QOS,
        )

    def _setup_services(self) -> None:
        """Servisleri oluştur.

        AssignRole: swarm manager bu servisi çağırarak rolü atar.
        """
        aid = self._agent_id
        self.create_service(
            AssignRole,
            f'/swarm/agent/drone{aid}/assign_role',
            self._handle_assign_role,
        )

    # ==========================================================================
    # FSM TICK — Her 0.1 saniyede bir çalışır (10 Hz)
    # ==========================================================================

    def _tick(self) -> None:
        """FSM ana döngüsü — saniyede 10 kez çalışır.

        Sırasıyla:
        1. Sağlık kontrolü yap → kritik hata varsa FAILSAFE
        2. Geçiş değerlendirmesi → state değişmeli mi?
        3. Kill switch kontrolü → FAILSAFE'den LANDED'a geç
        4. pending_state'i sıfırla → her tick'te bir kez tüketilir
        5. AgentStatus yayınla → diğer node'lar durumu görsün
        """
        ctx = self._ctx

        # -----------------------------------------------------------
        # ADIM 1: SAĞLIK KONTROLÜ
        # agent_health_monitor tüm kontrolleri yapar, sonucu döndürür
        # -----------------------------------------------------------
        result: HealthCheckResult = health_check(ctx)

        if result.critical_fault and ctx.state != AgentState.FAILSAFE:
            # Kritik hata var ve henüz FAILSAFE'de değil → hemen geç
            self._transition(AgentState.FAILSAFE)
            self._pub_event(
                result.event_type,
                SystemEvent.SEVERITY_EMERGENCY,  # En yüksek önem seviyesi
                result.reason,
            )
        elif result.safety_hold and not ctx.hold_active:
            # Safety hold → dur ve bekle, state değişmez
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'
            self._pub_event(
                SystemEvent.EVENT_SAFETY_HOLD,
                SystemEvent.SEVERITY_WARNING,
                result.reason,
            )
        elif result.warning:
            # Sadece uyarı → log at, devam et
            ctx.status_text = result.reason
            self.get_logger().warn(result.reason)

        # -----------------------------------------------------------
        # ADIM 2: GEÇİŞ DEĞERLENDİRMESİ
        # evaluate_transitions hangi state'e geçileceğini söyler
        # -----------------------------------------------------------
        next_s = evaluate_transitions(ctx)
        if next_s is not None and next_s != ctx.state:
            self._transition(next_s)  # Yeni state'e geç

        # -----------------------------------------------------------
        # ADIM 3: KİLL SWİTCH FAILSAFE → LANDED DOĞRULAMASI
        # Kill switch basıldıktan sonra drone gerçekten yere indi mi?
        # 6 koşulun hepsi sağlanmalı (roadmap 7.1)
        # -----------------------------------------------------------
        if (
            ctx.state == AgentState.FAILSAFE    # FAILSAFE'deyiz
            and ctx.kill_switch_active           # Kill switch basılı
            and not ctx.armed                    # Disarm oldu (motorlar durdu)
            and self._px4_landed                 # PX4 yere değdi diyor
            and abs(ctx.vel_z) < _GROUND_VEL_THR  # Dikey hız çok küçük
            and ctx.attitude_stable              # Drone sakin, sallanmıyor
        ):
            self._transition(AgentState.LANDED)  # Güvenli iniş tamamlandı
            self._pub_event(
                SystemEvent.EVENT_AGENT_LANDED,
                SystemEvent.SEVERITY_INFO,
                'Kill switch: landed+disarmed+stable doğrulandı',
            )

        # -----------------------------------------------------------
        # ADIM 4: PENDING_STATE SIFIRLA
        # pending_state her tick'te bir kez tüketilir, sonra None yapılır
        # Böylece aynı komut iki kez işlenmez
        # -----------------------------------------------------------
        ctx.pending_state = None

        # -----------------------------------------------------------
        # ADIM 5: AgentStatus YAYINLA
        # Drone'un tüm durumu diğer node'lara gönderilir
        # -----------------------------------------------------------
        self._publish_status()

    def _transition(self, new_state: AgentState) -> None:
        """State geçişini uygula ve log at.

        ARMED → TAKEOFF geçişinde mission_start_sequence_active sıfırlanır.
        Böylece bir sonraki mission start'ta tekrar kullanılabilir.
        """
        old = self._ctx.state
        self._ctx.set_state(new_state)  # State'i değiştir, timer'ı sıfırla

        # ARMED → TAKEOFF: Görev başlatma flag'ini temizle
        if old == AgentState.ARMED and new_state == AgentState.TAKEOFF:
            self._ctx.mission_start_sequence_active = False

        # Her geçişi logla: "[agent 1] IDLE -> ARMING"
        self.get_logger().info(
            f'[agent {self._ctx.agent_id}] '
            f'{old.name} -> {new_state.name}'
        )

    # ==========================================================================
    # SystemEvent CALLBACK — Swarm event bus'ından gelen olaylar
    # ==========================================================================

    def _on_event(self, msg: SystemEvent) -> None:
        """
        Gelen SystemEvent'e göre ctx ve pending_state günceller.

        Swarm manager ve diğer dronelerden gelen tüm olaylar buraya gelir.
        Her event tipi için farklı bir davranış tanımlanmıştır.

        is_mine: Bu event bu drone'a mı ait?
        target_agent_id=0 → tüm dronelere, diğer → sadece o drone'a

        Args:
            msg: Dinlenen SystemEvent mesajı.
        """
        ctx = self._ctx
        aid = ctx.agent_id       # Bu drone'un ID'si
        eid = msg.event_type     # Event tipi (EVENT_MISSION_STARTED vs.)
        tgt = msg.target_agent_id  # Hedef drone ID'si (0 = herkese)
        is_mine = tgt == 0 or tgt == aid  # Bu event bana mı geliyor?

        if eid == SystemEvent.EVENT_MISSION_STARTED:
            # Görev başlatma sinyali — tüm dronelere gönderilir
            if ctx.state == AgentState.IDLE:
                # IDLE'daysa hem arming hazırlığı yap hem de arming talebi
                # oluştur
                ctx.mission_start_sequence_active = True
                ctx.pending_state = AgentState.ARMING
            elif ctx.state == AgentState.ARMED:
                # Önceden arm edilmiş drone — sadece görev flag'ini set et
                # Bir sonraki tick'te TAKEOFF'a geçer
                ctx.mission_start_sequence_active = True

        elif eid == SystemEvent.EVENT_RTL_TRIGGERED and is_mine:
            # Eve dön komutu — bu drone'a özel veya herkese
            ctx.pending_state = AgentState.RETURN_HOME

        elif eid == SystemEvent.EVENT_EMERGENCY_LAND and is_mine:
            # Acil iniş komutu — hemen in, eve gitme
            ctx.pending_state = AgentState.LANDING

        elif eid == SystemEvent.EVENT_SAFETY_HOLD:
            # Güvenlik beklemesi — tüm otonom hareketler dur
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'

        elif eid == SystemEvent.EVENT_FAILSAFE_CLEARED:
            # Failsafe temizlendi — normal operasyona dön
            ctx.hold_active = False
            self._handle_failsafe_cleared()

        elif eid == SystemEvent.EVENT_PX4_LINK_LOST:
            # PX4 bağlantısı koptu — health monitor zaten tespit eder ama
            # event gelirse de güncelleyelim
            ctx.px4_link_ok = False

        elif eid == SystemEvent.EVENT_OFFBOARD_LOST:
            # OFFBOARD modu kayboldu
            ctx.offboard_active = False

        elif eid == SystemEvent.EVENT_GCS_LINK_LOST:
            # Yer kontrol istasyonu bağlantısı kesildi
            ctx.gcs_link_ok = False
            ctx.status_text = 'GCS link lost'

        elif eid == SystemEvent.EVENT_GCS_LINK_RESTORED:
            # GCS bağlantısı geri geldi — status_text'i temizle
            ctx.gcs_link_ok = True
            ctx.status_text = ''

        elif eid == SystemEvent.EVENT_MEMBER_DETACH_STARTED:
            # Bu drone sürüden ayrılacak
            if tgt == aid:
                ctx.pending_state = AgentState.DETACHED

        elif eid == SystemEvent.EVENT_MEMBER_REJOIN_STARTED:
            # Bu drone sürüye geri katılacak — önce preflight kontrolü
            if tgt == aid:
                passed, failures = run_preflight_checks(ctx)
                if passed:
                    ctx.pending_state = AgentState.REJOINING
                else:
                    # Preflight başarısız — sebeplerini logla
                    ctx.status_text = (
                        'Rejoin preflight failed: '
                        + '; '.join(failures[:2])  # İlk 2 hatayı göster
                    )
                    self.get_logger().warn(
                        f'[agent {aid}] Rejoin preflight başarısız: '
                        + ', '.join(failures)
                    )

        elif eid in (
            SystemEvent.EVENT_MANEUVER_STARTED,    # Manevra başladı
            SystemEvent.EVENT_ROTATION_STARTED,    # Rotasyon başladı
        ):
            # IN_SWARM'dayken görev komutu geldi → EXECUTING_TASK'a geç
            if is_mine and ctx.state == AgentState.IN_SWARM:
                ctx.pending_state = AgentState.EXECUTING_TASK

        elif eid in (
            SystemEvent.EVENT_MANEUVER_COMPLETED,  # Manevra tamamlandı
            SystemEvent.EVENT_ROTATION_COMPLETED,  # Rotasyon tamamlandı
            SystemEvent.EVENT_FORMATION_REACHED,
        ):
            # Görev bitti → sürüye geri dön
            if is_mine and ctx.state == AgentState.EXECUTING_TASK:
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_MANEUVER_FAILED and is_mine:
            # Manevra başarısız oldu → sürüye geri dön
            if ctx.state == AgentState.EXECUTING_TASK:
                ctx.status_text = 'Manevra başarısız, sürüye dönülüyor'
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_AGENT_JOIN_REQUEST and is_mine:
            # Bu drone sürüye katılmak istiyor
            ctx.wants_to_join = True

        elif eid == SystemEvent.EVENT_KILL_SWITCH_ACTIVATED:
            # Kill switch basıldı — motorlar anında duracak
            ctx.kill_switch_active = True

        elif eid == SystemEvent.EVENT_RC_LINK_LOST:
            # RC bağlantısı kesildi
            ctx.rc_link_ok = False

        elif eid == SystemEvent.EVENT_OSCILLATION_DETECTED:
            # Sallanma tespit edildi
            ctx.oscillation_detected = True

        elif eid == SystemEvent.EVENT_UNSTABLE_FLIGHT:
            # Tehlikeli kararsız uçuş
            ctx.unstable_flight = True

        elif eid == SystemEvent.EVENT_MISSION_COMPLETED:
            # Görev tamamlandı — drone inmiş olmalı, IDLE'a hazırlan
            if ctx.state == AgentState.LANDED:
                ctx.pending_state = AgentState.IDLE

        elif eid == SystemEvent.EVENT_ORIGIN_SYNCED:
            # Swarm koordinat sistemi senkronize edildi
            ctx.origin_synced = True

        elif eid == SystemEvent.EVENT_GEOFENCE_VIOLATION:
            # Jeofen ihlali — health monitor RTL başlatacak
            ctx.geofence_violated = True

    def _handle_failsafe_cleared(self) -> None:
        """
        EVENT_FAILSAFE_CLEARED alındı — ne yapacağımıza karar ver.

        Drone'un o anki fiziksel durumuna göre hedef belirlenir:
        - Disarm ise → IDLE (yerde, güvende, sıfırdan başla)
        - Arm + yerde ise → LANDING (zaten yerde, iniş tamamla)
        - Arm + havada ise → RETURN_HOME (güvenli şekilde eve dön)

        geofence_violated failsafe temizlenince sıfırlanır.
        """
        ctx = self._ctx
        ctx.geofence_violated = False

        if not ctx.armed:
            # Disarm — yerde ve güvende, IDLE'a dön
            ctx.pending_state = AgentState.IDLE
        elif self._px4_landed:
            # Arm ama yerde — iniş prosedürünü tamamla
            # _from_failsafe bu LANDING isteğini işler → LANDED'a geçer
            ctx.pending_state = AgentState.LANDING
        else:
            # Arm ve havada — güvenli şekilde eve dön
            ctx.pending_state = AgentState.RETURN_HOME

    # ==========================================================================
    # SWARM CALLBACK'LERİ
    # ==========================================================================

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """
        SwarmOrigin mesajı alındı — sürünün referans koordinat sistemi.

        Lider drone GPS referans noktasını yayınlar.
        Bu mesaj alınınca px4_interface SET_GPS_GLOBAL_ORIGIN uygular.
        Burada sadece sequence güncellenir ve origin_synced set edilir.
        Gerçek senkronizasyon px4_interface'in sorumluluğunda.
        """
        if msg.valid and msg.gps_fix_type >= 3:
            # Geçerli bir origin ve yeterli GPS fix → senkronize
            self._ctx.origin_synced = True
            self._ctx.origin_sequence = msg.sequence  # Kaçıncı güncelleme?

    # ==========================================================================
    # AssignRole SERVİSİ
    # ==========================================================================

    def _handle_assign_role(
        self,
        request: AssignRole.Request,
        response: AssignRole.Response,
    ) -> AssignRole.Response:
        """
        /swarm/agent/{id}/assign_role servis handler.

        Swarm manager bu servisi çağırarak drone'a rol atar.
        Örnek: "Drone 1, sen LEADER ol"

        STANDBY rolü atanırsa drone hemen STANDBY state'ine geçer.

        Args:
            request: AssignRole.Request (role, target_agent_id, reason)
            response: AssignRole.Response (success, message)

        Returns:
            AssignRole.Response
        """
        ctx = self._ctx

        # Sayısal rol kodunu AgentRole enum'una çevir
        role_map = {
            AssignRole.Request.ROLE_LEADER: AgentRole.LEADER,
            AssignRole.Request.ROLE_FOLLOWER: AgentRole.FOLLOWER,
            AssignRole.Request.ROLE_STANDBY: AgentRole.STANDBY,
            AssignRole.Request.ROLE_DETACHED: AgentRole.DETACHED,
        }
        new_role = role_map.get(request.role)

        if new_role is None:
            # Bilinmeyen rol kodu geldi → hata döndür
            response.success = False
            response.message = f'Bilinmeyen rol: {request.role}'
            return response

        ctx.role = new_role  # Rolü güncelle

        # STANDBY rolü atanınca hemen STANDBY state'ine geç
        if new_role == AgentRole.STANDBY:
            ctx.set_state(AgentState.STANDBY)

        response.success = True
        response.message = f'Rol atandı: {ctx.role.name}'
        self.get_logger().info(
            f'[agent {ctx.agent_id}] Rol: {ctx.role.name}'
        )
        return response

    # ==========================================================================
    # TELEMETRİ CALLBACK
    # px4_bridge'den gelen AgentStatus'u AgentContext'e kopyalar.
    # PX4 mesajlarının çevirisi px4_bridge tarafında yapılır (px4_interface).
    # ==========================================================================

    def _on_telemetry(self, msg: AgentStatus) -> None:
        """px4_bridge → AgentContext kopyalama.

        px4_bridge AgentStatus'un PX4 alanlarını doldurmuş halde gönderir.
        FSM bu alanları kendi context'ine kopyalar; state, role, healthy
        gibi FSM'e özel alanları AgentContext kendisi yönetir.
        """
        ctx = self._ctx
        prev_pilot = ctx.pilot_override_active

        # Bağlantı / arm / mod
        ctx.px4_link_ok = msg.px4_link_ok
        ctx.armed = msg.armed
        ctx.offboard_enabled = msg.offboard_enabled
        ctx.offboard_active = msg.offboard_active
        ctx.flight_mode = FlightMode(msg.flight_mode)
        ctx.pilot_override_active = msg.pilot_override_active
        ctx.failsafe_active = msg.failsafe_active
        ctx.rc_signal_failsafe_active = msg.rc_signal_failsafe_active
        ctx.rc_link_ok = msg.rc_link_ok

        # Batarya
        ctx.battery_voltage_v = msg.battery_voltage_v
        ctx.battery_current_a = msg.battery_current_a
        ctx.battery_percent = msg.battery_percent

        # Konum ve hız (NED)
        ctx.pos_x = msg.pos_x
        ctx.pos_y = msg.pos_y
        ctx.pos_z = msg.pos_z
        ctx.vel_x = msg.vel_x
        ctx.vel_y = msg.vel_y
        ctx.vel_z = msg.vel_z

        # Attitude
        ctx.roll_deg = msg.roll_deg
        ctx.pitch_deg = msg.pitch_deg
        ctx.heading_deg = msg.heading_deg

        # GPS
        ctx.gps_fix_type = msg.gps_fix_type
        ctx.gps_hdop = msg.gps_hdop
        ctx.gps_satellites = msg.gps_satellites
        ctx.lat_deg = msg.lat_deg
        ctx.lon_deg = msg.lon_deg
        ctx.alt_amsl_m = msg.alt_amsl_m

        # Home
        ctx.home_set = msg.home_set
        ctx.home_lat_deg = msg.home_lat_deg
        ctx.home_lon_deg = msg.home_lon_deg
        ctx.home_alt_amsl_m = msg.home_alt_amsl_m

        # Sensör sağlığı
        ctx.imu_healthy = msg.imu_healthy
        ctx.mag_healthy = msg.mag_healthy
        ctx.baro_healthy = msg.baro_healthy

        # EKF
        ctx.estimator_ok = msg.estimator_ok
        ctx.xy_valid = msg.xy_valid
        ctx.z_valid = msg.z_valid
        ctx.v_xy_valid = msg.v_xy_valid

        # Yere değme tespiti — px4_bridge altitude alanını yayınlamadığı için
        # disarm + düşük dikey hız varsayımıyla tahmin ediyoruz
        self._px4_landed = (
            not ctx.armed and abs(ctx.vel_z) < _GROUND_VEL_THR
        )

        # Pilot override kenar tespiti — IDLE'dan pilot moduna geçişte event
        # yayınla
        if ctx.pilot_override_active and not prev_pilot:
            ctx.autonomous_control_paused = True
            ctx.status_text = (
                'Pilot override active, autonomous control paused'
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_PILOT_OVERRIDE,
                SystemEvent.SEVERITY_WARNING,
                'Manuel mod tespit edildi',
            )
        elif not ctx.pilot_override_active:
            ctx.autonomous_control_paused = False

        self._prev_pilot_override = ctx.pilot_override_active

    # ==========================================================================
    # AgentStatus YAYINI
    # ==========================================================================

    def _publish_status(self) -> None:
        """AgentContext'teki tüm veriyi AgentStatus.msg'e dönüştürüp yayınlar.

        Bu mesaj swarm manager, GCS ve diğer droneler tarafından okunur.
        Drone'un tam anlık durumunu içerir.
        """
        ctx = self._ctx
        m = AgentStatus()  # Boş mesaj oluştur
        m.stamp = self.get_clock().now().to_msg()  # Zaman damgası ekle

        # Kimlik ve FSM durumu
        m.agent_id = ctx.agent_id
        m.role = int(ctx.role)      # Enum → int (ROS mesajı int istiyor)
        m.state = int(ctx.state)    # Enum → int

        # Bağlantı durumu
        m.px4_link_ok = ctx.px4_link_ok
        m.gcs_link_ok = ctx.gcs_link_ok

        # Arm ve offboard durumu
        m.armed = ctx.armed
        m.offboard_enabled = ctx.offboard_enabled
        m.offboard_active = ctx.offboard_active
        m.flight_mode = int(ctx.flight_mode)
        m.pilot_override_active = ctx.pilot_override_active

        # Failsafe ve sağlık
        m.failsafe_active = ctx.failsafe_active
        m.healthy = ctx.healthy  # @property — anlık hesaplanır

        # Batarya
        m.battery_percent = ctx.battery_percent
        m.battery_voltage_v = ctx.battery_voltage_v
        m.battery_current_a = ctx.battery_current_a

        # Konum ve hız (NED)
        m.pos_x = ctx.pos_x
        m.pos_y = ctx.pos_y
        m.pos_z = ctx.pos_z
        m.vel_x = ctx.vel_x
        m.vel_y = ctx.vel_y
        m.vel_z = ctx.vel_z

        # Attitude
        m.heading_deg = ctx.heading_deg
        m.roll_deg = ctx.roll_deg
        m.pitch_deg = ctx.pitch_deg

        # GPS kalitesi
        m.gps_fix_type = ctx.gps_fix_type
        m.gps_hdop = ctx.gps_hdop
        m.gps_satellites = ctx.gps_satellites

        # Global konum
        m.lat_deg = ctx.lat_deg
        m.lon_deg = ctx.lon_deg
        m.alt_amsl_m = ctx.alt_amsl_m

        # Home konumu
        m.home_set = ctx.home_set
        m.home_lat_deg = ctx.home_lat_deg
        m.home_lon_deg = ctx.home_lon_deg
        m.home_alt_amsl_m = ctx.home_alt_amsl_m

        # Sensör sağlığı
        m.imu_healthy = ctx.imu_healthy
        m.mag_healthy = ctx.mag_healthy
        m.baro_healthy = ctx.baro_healthy

        # EKF2 estimator
        m.estimator_ok = ctx.estimator_ok
        m.xy_valid = ctx.xy_valid
        m.z_valid = ctx.z_valid
        m.v_xy_valid = ctx.v_xy_valid

        # Swarm origin
        m.origin_synced = ctx.origin_synced
        m.origin_sequence = ctx.origin_sequence

        # RC ve güvenlik
        m.rc_link_ok = ctx.rc_link_ok
        m.kill_switch_active = ctx.kill_switch_active
        m.rc_signal_failsafe_active = ctx.rc_signal_failsafe_active

        # Uçuş stabilitesi
        m.oscillation_detected = ctx.oscillation_detected
        m.unstable_flight = ctx.unstable_flight

        # Standby / join
        m.wants_to_join = ctx.wants_to_join
        m.ready_to_arm = ctx.ready_to_arm

        # Durum metni
        m.status_text = ctx.status_text

        self._status_pub.publish(m)  # Yayınla!

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """
        SystemEvent yayınla — swarm manager ve diğer droneler dinler.

        Args:
            event_type: SystemEvent.EVENT_* sabiti (EVENT_AGENT_LANDED vs.)
            severity: SystemEvent.SEVERITY_* (INFO, WARNING, EMERGENCY)
            message: İsteğe bağlı açıklama metni (loglarda görünür)
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()  # Zaman damgası
        m.event_type = event_type                  # Ne oldu?
        m.severity = severity                      # Ne kadar önemli?
        m.source_agent_id = self._ctx.agent_id    # Kim gönderdi?
        m.source_module = 'agent_fsm'             # Hangi modül gönderdi?
        m.message = message                        # Açıklama
        self._event_pub.publish(m)                 # Yayınla!


def main(args=None) -> None:
    """ROS2 node giriş noktası.

    ros2 run komutuyla çalıştırılınca burası çağrılır.
    rclpy.init → node oluştur → spin (mesaj döngüsü) → temizle
    """
    rclpy.init(args=args)          # ROS2 iletişim altyapısını başlat
    node = AgentFsmNode()          # Node'u oluştur
    try:
        # Mesaj gelene kadar bekle, callback'leri çalıştır
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass                       # Ctrl+C ile düzgün kapat
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
