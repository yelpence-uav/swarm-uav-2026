#!/usr/bin/env python3
"""
Sürü İHA ESP-NOW Mesh Ağı Simülatörü (ROS 2 Proxy Node)
İç (Internal) topic'lerden gelen verileri alır, fiziksel engellerden
ve mesafe kısıtlamalarından geçirerek Dış (Public) topic'lere aktarır.
"""

import heapq
import itertools

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rclpy.serialization import serialize_message
from std_msgs.msg import String, UInt8

# Fiziksel Radyo Modelimiz
from network_proxy.rf_model import ESPNowRFModel

# Swarm Interfaces
from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    LeaderHeartbeat,
    MissionTarget,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmOrigin,
    SwarmState,
    SystemEvent,
)


# Heartbeat: RELIABLE + VOLATILE + KEEP_LAST(5). Donanım ikizi esp32_bridge
# ile aynı derinlik; kısa süre takılan bir tüketici son birkaç heartbeat'i
# kaçırmasın. "Broadcast" radyo modelidir; DDS reliability AYRI eksen. Radyo
# kaybını proxy modelliyor (drop ederek); GEÇİRDİĞİ paket DDS bacağında ikinci
# kez düşmesin diye RELIABLE. VOLATILE olduğu için "eski heartbeat replay"
# olmaz (o yalnız TRANSIENT_LOCAL'de olur).
_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# Aşağıdaki 5 profil; proxy, esp32_bridge ve tüketicilerin hepsi birebir aynı
# değerleri kullanmalı. Ortak bir QoS paketi olmadığından değerler her tarafta
# elle hizalanır.
_STATE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_CONTROL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
# Formation: lider slot atamasını (agent_ids + offset) yayınlar (merkezi atama).
# Üretici (mode_manager) ve tüketiciler (formation_node, collision_avoidance)
# hepsi RELIABLE kullandığından RELIABLE.
_FORMATION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# Status: yüksek frekanslı, "en güncel değer kazanır" telemetri. Saha ikizi
# esp32_bridge (_MESH_QOS) ve üreticiler (agent_fsm/vision_node) ile aynı:
# BEST_EFFORT. RELIABLE burada head-of-line blocking yaratır; ayrıca
# BEST_EFFORT üreticiyle RELIABLE abone DDS'te hiç bağlanmaz (uyumsuz QoS).
_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# ESP-NOW tek çerçeve üst sınırı (byte). Havadan geçen her paket bu bütçenin
# altında kalmalı; aşan mesaj gerçek meshte tek çerçevede gönderilemez.
_ESPNOW_MTU_BYTES = 250

# Bir komşunun konumu bu süreden eskiyse "ölü" sayılır ve mesafe hesabına
# katılmaz. Gerçek mesh'teki düğüm zaman aşımıyla (mesh_config.h NODE_TIMEOUT_MS
# = 12000 ms) hizalı: bir düğüm 12 sn heartbeat göndermezse komşu listesinden
# düşürülür. Susan/çöken bir drone'un bayat konumu, canlı komşu gibi sayılıp
# yanlış mesafe/kayıp kararı üretmesin diye.
_STALE_LIMIT_S = 12.0


class NetworkProxyNode(Node):
    def __init__(self):
        super().__init__("network_proxy_node")

        # 1. RF Modelini Başlat. rng_seed >= 0 verilirse kayıp/jitter dizisi
        # tekrarlanabilir olur — aynı senaryoyu birebir tekrar oynatıp hata
        # ayıklamak için. Verilmezse (-1) sistem entropisi kullanılır (her
        # koşuda farklı rastgelelik).
        self.declare_parameter("rng_seed", -1)
        rng_seed = int(self.get_parameter("rng_seed").value)
        self.rf_model = ESPNowRFModel(seed=rng_seed if rng_seed >= 0 else None)

        # 2. Ajanların (İHA'lar ve YKİ) güncel GPS konumlarını tutacağımız
        # sözlük: (lat_deg, lon_deg, alt_amsl_m). YKİ'nin konumu parametre —
        # sabit (0,0,0) GPS'te Gine Körfezi'nde bir nokta demektir (~5500 km
        # uzak); saha lat/lon'una göre gerçek değer VERİLMEDEN GCS mesafe
        # kontrolü anlamsız çıkar (her zaman "çok uzak" der).
        self.declare_parameter("gcs_lat", 0.0)
        self.declare_parameter("gcs_lon", 0.0)
        self.declare_parameter("gcs_alt", 0.0)
        gcs_lat = float(self.get_parameter("gcs_lat").value)
        gcs_lon = float(self.get_parameter("gcs_lon").value)
        gcs_alt = float(self.get_parameter("gcs_alt").value)
        self._gcs_configured = not (gcs_lat == 0.0 and gcs_lon == 0.0)
        if not self._gcs_configured:
            self.get_logger().warn(
                "gcs_lat/gcs_lon verilmedi (varsayılan 0,0) — GCS mesafe "
                "kontrolü sahanın gerçek GPS konumu verilmeden ANLAMSIZDIR. "
                "Control kanalı bu durumda menzil kontrolünden muaf tutulur."
            )
        self.positions = {"gcs": (gcs_lat, gcs_lon, gcs_alt)}

        # Her drone'un konumunun en son NE ZAMAN güncellendiği (node saati, s).
        # _min_neighbor_distance bunu okuyup _STALE_LIMIT_S'ten eski konumları
        # atar. GCS bu sözlükte YOK — sabit parametre, asla bayatlamaz.
        self._pos_stamp: dict[str, float] = {}

        # Güncel lider ID'si — heartbeat (leader_id) ve election (new_leader_id)
        # handler'larında, drop kararından ÖNCE yakalanır (proxy gerçek lideri
        # /internal'dan her zaman bilir, ilettiği /public düşse bile). Gönderen
        # kimliği taşımayan ama LİDERDEN çıkan kanallar (formation, mission fazı)
        # bunu kullanıp mesafe kaybını liderin konumuna göre uygular. Lider henüz
        # bilinmiyorsa None → fail-open. Bkz. _leader_drop.
        self._current_leader_id: int | None = None

        # Sistemdeki İHA listesi — diğer TÜM node'lar gibi 'drone{id}'
        # adlandırması. Sayı parametreyle ayarlanır (launch'taki drone
        # sayısıyla uyumlu olmalı; varsayılan 3).
        self.declare_parameter("num_drones", 3)
        num_drones = int(self.get_parameter("num_drones").value)
        self.agent_ids = [f"drone{i}" for i in range(1, num_drones + 1)]

        # Fault-injection: menzil dışı sayılan düğümler. Kesme düğüm
        # seviyesindedir; public topic paylaşımlı olduğundan link-seviyesi
        # (asimetrik) kesme yapılamaz. Bir drone burada listelenirse GÖNDERDİĞİ
        # mesajlar (gönderen kimliği olan tüm kanallar: status/heartbeat/state/
        # qr/events/election) relay edilmez — failover/rejoin testinin aracı.
        # Test: `ros2 topic pub /swarm/proxy/unreachable std_msgs/msg/String
        # "{data: 'drone1'}"`.
        self.unreachable_agents: set[str] = set()
        self.create_subscription(
            String, "/swarm/proxy/unreachable", self._on_unreachable_set, 10
        )

        # Sıralı gecikme kuyruğu — threading.Timer YERİNE. Timer her mesaj
        # için bağımsız duvar-saati zamanlayıcısı kurar; rastgele jitter
        # yüzünden art arda gelen mesajlar SIRASI BOZULARAK yayınlanabilir
        # (B, A'dan sonra gönderilse bile önce çıkabilir) ve sim-time'ı
        # bilmez. Bu kuyruk node saatiyle (get_clock) çalışır ve kanal
        # başına sırayı korur (_last_scheduled ile monotonluk zorlanır).
        self._pending: list = []  # heap: (hedef_zaman_s, seq, publisher, msg)
        self._seq_counter = itertools.count()
        self._last_scheduled: dict[str, float] = {}
        self.create_timer(0.002, self._drain_pending)

        # 3. Publisher ve Subscriber'ları Dinamik Oluştur
        self.internal_subs = {}
        self.public_pubs = {}

        for agent in self.agent_ids:
            # İHA'ların KÖPRÜYE gönderdiği GİZLİ (Internal) topic'leri dinle
            internal_topic = f"/swarm/internal/{agent}/status"
            self.internal_subs[agent] = self.create_subscription(
                AgentStatus,
                internal_topic,
                lambda msg, a=agent: self.internal_status_callback(msg, a),
                _STATUS_QOS,
            )

            # KÖPRÜNÜN diğer İHA'lara ileteceği GENEL (Public) topic'leri oluştur
            public_topic = f"/swarm/public/{agent}/status"
            self.public_pubs[agent] = self.create_publisher(
                AgentStatus, public_topic, _STATUS_QOS
            )

            # Konum ilk status gelene kadar BİLİNMİYOR (None). (0,0,0) GPS'te
            # Gine Körfezi (~5500 km) demek olurdu ve açılışta sahte kayıp
            # üretirdi; None → _broadcast_drop o dronu hesaba katmaz (fail-open).
            self.positions[agent] = None

        # --- Consensus heartbeat kanalı (BEST_EFFORT broadcast) ---
        # Lider topic'i paylaşımlı (drone{id} ad-uzaylı DEĞİL). Gönderici
        # mesajdaki leader_id'den çözülür. Bu relay olmadan follower'lar
        # heartbeat alamaz → 300ms sahte timeout → split-brain.
        self._hb_pub = self.create_publisher(
            LeaderHeartbeat, "/swarm/public/leader/heartbeat", _HEARTBEAT_QOS
        )
        self.create_subscription(
            LeaderHeartbeat,
            "/swarm/internal/leader/heartbeat",
            self._on_internal_heartbeat,
            _HEARTBEAT_QOS,
        )

        # --- SwarmState (Broadcast) — gönderen = leader_id (lider yayını).
        # Mesh'te non-kritik (SWARM_STATE, retry YOK) → liderin en yakın
        # komşusuna göre tek-zar radyo kaybı (heartbeat ile aynı sınıf).
        self._state_pub = self.create_publisher(
            SwarmState, "/swarm/public/state", _STATE_QOS
        )
        self.create_subscription(
            SwarmState, "/swarm/internal/state", self._on_internal_state,
            _STATE_QOS,
        )

        # --- SwarmControlCommand (YKİ->İHA) — havadan gider, kaybolabilir:
        # (gcs konumu verildiyse) GCS'in en yakın drone'una göre mesafe kaybı
        # zarı + jitter. Kritik olması havada koruma sağlamaz (ACK yok).
        # Bkz. _on_internal_control.
        self._control_pub = self.create_publisher(
            SwarmControlCommand, "/swarm/public/control/command", _CONTROL_QOS
        )
        self.create_subscription(
            SwarmControlCommand, "/swarm/internal/control/command",
            self._on_internal_control, _CONTROL_QOS,
        )

        # --- SystemEvent, ElectionResult, SwarmOrigin: havadan giden yayınlar,
        # kaybolabilir. events/election gönderen kimliğine sahip → gönderenin
        # en yakın komşusuna göre mesafe kaybı zarı (bkz. ilgili handler'lar).
        # origin'de gönderen-ID yok → mesafe uygulanamaz (yalnız jitter).
        # QRMissionData da havadan gider → algılayan drona göre tek-zar.
        self._event_pub = self.create_publisher(
            SystemEvent, "/swarm/public/events/system", _EVENT_QOS
        )
        self.create_subscription(
            SystemEvent, "/swarm/internal/events/system",
            self._on_internal_event, _EVENT_QOS,
        )

        self._qr_pub = self.create_publisher(
            QRMissionData, "/swarm/public/perception/qr_data", _EVENT_QOS
        )
        self.create_subscription(
            QRMissionData, "/swarm/internal/perception/qr_data",
            self._on_internal_qr, _EVENT_QOS,
        )

        # Latched: geç katılan da güncel lideri anında alsın.
        self._election_pub = self.create_publisher(
            ElectionResult, "/swarm/public/election/result", _ELECTION_QOS
        )
        self.create_subscription(
            ElectionResult, "/swarm/internal/election/result",
            self._on_internal_election, _ELECTION_QOS,
        )

        # Latched: geç katılan origin'i anında alsın. NOT: origin'in
        # gerçekten bu köprüden geçmesi için swarm_origin_publisher'ın
        # /internal/origin'e yazması gerekir (ayrı pakette düzeltildi).
        self._origin_pub = self.create_publisher(
            SwarmOrigin, "/swarm/public/origin", _ORIGIN_QOS
        )
        self.create_subscription(
            SwarmOrigin, "/swarm/internal/origin",
            self._on_internal_origin, _ORIGIN_QOS,
        )

        # --- FormationCommand (lider→followers) — havadan gider, kaybolabilir.
        # Mesajda gönderen drone kimliği yok ama fiziksel gönderen = güncel lider
        # (heartbeat/election'dan izlenir) → mesafe kaybı liderin konumuna göre
        # (_leader_drop). Lider slot atamasını (agent_ids + offset_x/y/z) yayınlar;
        # formation_node/collision_avoidance /public'ten okur.
        self._formation_pub = self.create_publisher(
            FormationCommand, "/swarm/public/formation/target", _FORMATION_QOS
        )
        self.create_subscription(
            FormationCommand, "/swarm/internal/formation/target",
            self._on_internal_formation, _FORMATION_QOS,
        )

        # --- QRCoordinates (yarışma öncesi paylaşılan QR konum tablosu) —
        # latched (origin ile aynı QoS). GCS/operatör yayınlar; fiziksel dron
        # kimliği yok → mesafe uygulanamaz, yalnız jitter (origin ile aynı sınır).
        self._qr_coords_pub = self.create_publisher(
            QRCoordinates, "/swarm/public/mission/qr_coords", _ORIGIN_QOS
        )
        self.create_subscription(
            QRCoordinates, "/swarm/internal/mission/qr_coords",
            self._on_internal_qr_coords, _ORIGIN_QOS,
        )

        # --- Görev fazı (mission_fsm liderde→tüm dronlar) — MissionState ve
        # QrTaskStep (UInt8). Her drone'un mission1'i ve formation_control gate'i
        # bu fazı /public'ten okur. Havadan gider, kaybolabilir; düz UInt8 kimlik
        # taşımasa da fiziksel gönderen = güncel lider → mesafe kaybı liderin
        # konumuna göre (_leader_drop).
        self._mission_state_pub = self.create_publisher(
            UInt8, "/swarm/public/mission/state", _FORMATION_QOS
        )
        self.create_subscription(
            UInt8, "/swarm/internal/mission/state",
            self._on_internal_mission_state, _FORMATION_QOS,
        )
        self._mission_qr_step_pub = self.create_publisher(
            UInt8, "/swarm/public/mission/qr_step", _FORMATION_QOS
        )
        self.create_subscription(
            UInt8, "/swarm/internal/mission/qr_step",
            self._on_internal_mission_qr_step, _FORMATION_QOS,
        )

        # --- Sonraki QR hedefi (mission_fsm liderde→tüm dronlar) — MissionTarget
        # (qr_id + lat/lon). mission1 bunu /public'ten okuyup navige eder. Liderin
        # mission_fsm'inden çıkar → mesafe kaybı liderin konumuna göre (_leader_drop).
        self._mission_next_target_pub = self.create_publisher(
            MissionTarget, "/swarm/public/mission/next_target", _FORMATION_QOS
        )
        self.create_subscription(
            MissionTarget, "/swarm/internal/mission/next_target",
            self._on_internal_mission_next_target, _FORMATION_QOS,
        )

        self.get_logger().info("Network Proxy Node (ESP-NOW Simulator) Başlatıldı.")
        self.get_logger().info(
            "Yönlendirme aktif: /swarm/internal/... -> /swarm/public/..."
        )

    def _on_unreachable_set(self, msg: String):
        """Fault-injection: menzil dışı sayılacak drone listesini günceller.

        Boş string -> hepsi menzile döner (rejoin). Virgülle ayrılmış
        birden çok drone da olur: 'drone1,drone2'.
        """
        names = {n.strip() for n in msg.data.split(",") if n.strip()}
        self.unreachable_agents = names
        self.get_logger().warn(f"FAULT-INJECTION: menzil dışı = {names or '(boş)'}")

    def _schedule(self, channel_key: str, publisher, msg) -> None:
        """Bir mesajı sıralı gecikme kuyruğuna ekler.

        channel_key aynı olan mesajlar SIRASINI korur: yeni mesajın hedef
        zamanı, aynı kanaldaki bir önceki mesajınkinden erken olamaz (yoksa
        art arda gelen A,B mesajları rastgele jitter yüzünden B,A sırasında
        çıkabilirdi). Node saatini kullanır (get_clock) — sim-time uyumlu.
        """
        now = self.get_clock().now().nanoseconds / 1e9
        target = now + self.rf_model.get_jitter()
        last = self._last_scheduled.get(channel_key, 0.0)
        if target <= last:
            target = last + 1e-6
        self._last_scheduled[channel_key] = target
        heapq.heappush(
            self._pending, (target, next(self._seq_counter), publisher, msg)
        )

    def _drain_pending(self) -> None:
        """Periyodik çağrılır (2ms); hedef zamanı geçmiş mesajları yayınlar."""
        now = self.get_clock().now().nanoseconds / 1e9
        while self._pending and self._pending[0][0] <= now:
            _, _, publisher, msg = heapq.heappop(self._pending)
            publisher.publish(msg)

    def _within_budget(self, msg, label: str) -> bool:
        """Serileştirilmiş boyut ESP-NOW sınırını aşarsa False + uyarı basar.

        Havadan geçen (mesh) kanalların ortak bütçe bekçisi. Gerçek köprü
        veriyi 16 byte'lık struct'lara paketlediğinden bu ölçüm birebir
        fiziksel değildir; amacı mesaj tanımları şişip 250 byte'ı aşınca
        yakalamaktır. SwarmState için de koruyucudur: agents[] boş bırakıldığı
        sürece geçer (~192 byte), yanlışlıkla doldurulursa yakalar.
        """
        size = len(serialize_message(msg))
        if size > _ESPNOW_MTU_BYTES:
            self.get_logger().warn(
                f"PAKET REDDEDİLDİ! {label} mesajı 250 byte sınırını aştı "
                f"(Boyut: {size} byte)"
            )
            return False
        return True

    def _min_neighbor_distance_m(self, sender_pos, exclude_key=None):
        """sender_pos'a en yakın canlı komşunun mesafesi (metre). Menzil-dışı
        işaretli, konumu bilinmeyen VEYA konumu bayat (bkz. _STALE_LIMIT_S)
        alıcılar sayılmaz. Hiç aday yoksa None (fail-open — henüz karar
        verilemez).
        """
        now = self.get_clock().now().nanoseconds / 1e9
        min_dist = None
        for receiver_id in self.agent_ids:
            if receiver_id == exclude_key:
                continue
            if receiver_id in self.unreachable_agents:
                continue
            receiver_pos = self.positions.get(receiver_id)
            if receiver_pos is None:
                continue  # henüz konum bildirmedi → hesaba katma (fail-open)
            stamp = self._pos_stamp.get(receiver_id)
            if stamp is not None and now - stamp > _STALE_LIMIT_S:
                continue  # bayat konum → ölü/susmuş komşu, canlı sayma
            d = self.rf_model.distance_m(sender_pos, receiver_pos)
            min_dist = d if min_dist is None else min(min_dist, d)
        return min_dist

    def _broadcast_drop(self, sender_key: str) -> bool:
        """En yakın komşuya göre tek-zar: yayın düşecekse True.

        TÜM mesh yayınları radyo kaybına tabidir. Havadan geçen bir paket,
        kritik olsun olmasın, aynı fizikle kaybolur: ESP-NOW broadcast'te
        donanım ACK'i yoktur (mesh_config.h _mesh_gonder), dolayısıyla paket
        havaya TEK ATIŞ çıkar; kritik kanalların 3-retry'ı yalnız YEREL
        gönderim hatasını (TX kuyruğu) kurtarır, havadaki kaybı değil.
        Flooding (ATLAMA_MAKS=3) her iki sınıfta da vardır ve paket en yakın
        komşusuna ulaşabildiğinde mesh'e girip geri kalana yayılır. Bu yüzden
        karar EN YAKIN komşuya göredir (en uzak değil) — yakın bir komşu,
        uzaktaki başka bir alıcı yüzünden cezalandırılmamalı. En yakın link
        bile tek atışta düşebilir → hard-cutoff değil OLASILIK zarı (cutoff
        ötesinde zar zaten %100 verir, izolasyonu da kapsar).

        Fault-injection: gönderen menzil dışı işaretlenmişse tüm yayını
        düşürür (düğüm-seviyesi kesme; tüm kanallarda tutarlı).
        """
        if sender_key in self.unreachable_agents:
            return True
        sender_pos = self.positions.get(sender_key)
        if sender_pos is None:
            return False
        min_dist = self._min_neighbor_distance_m(sender_pos, exclude_key=sender_key)
        if min_dist is None:
            return False
        return self.rf_model.should_drop_packet(min_dist)

    def _leader_drop(self) -> bool:
        """Liderden çıkan (formation/mission fazı) kanallar için mesafe kaybı
        zarı. Bu mesajlarda gönderen kimliği yok ama fiziksel olarak liderin
        radyosundan çıkarlar; gönderen = izlenen güncel lider (_current_leader_id,
        heartbeat/election'dan). Lider henüz bilinmiyorsa fail-open (kayıpsız).
        Split-brain'de tek lider takibi yaklaşıktır (bkz. _current_leader_id).
        """
        if self._current_leader_id is None:
            return False
        return self._broadcast_drop(f"drone{self._current_leader_id}")

    def internal_status_callback(self, msg: AgentStatus, sender_id: str):
        """
        Bir İHA'dan (Gönderici) mesaj geldiğinde tetiklenir.
        """
        # 0. Fault-injection: bu drone elle menzil dışı işaretlenmişse,
        # mesafeye bile bakmadan reddet (düğüm-seviyesi kesme).
        if sender_id in self.unreachable_agents:
            return

        # 1. Göndericinin GPS konumunu güncelle. pos_x/y/z KULLANILMAZ —
        # her drone kendi yerel origin'ini kurar, aralarında ortak referans
        # yoktur. Ortak referans yalnızca GPS'tir.
        #
        # GEÇERLİLİK: yalnız 3D fix (gps_fix_type >= 3) VE (0,0) olmayan
        # koordinat saklanır. GPS kilidi yokken drone lat/lon=0.0 yayınlar;
        # ham (0,0)'ı saklarsak haversine bunu Gine Körfezi (~5500 km) sanır
        # ve gerçek GPS'li dronlara sahte "izole/çok uzak" kararı üretir.
        # Geçersizse konumu GÜNCELLEMEYİZ — son geçerli konum korunur (bayatsa
        # _min_neighbor_distance zaten atar). Hiç geçerli fix gelmediyse konum
        # None kalır → _broadcast_drop fail-open (hesaba katmaz).
        now = self.get_clock().now().nanoseconds / 1e9
        if msg.gps_fix_type >= 3 and not (
            msg.lat_deg == 0.0 and msg.lon_deg == 0.0
        ):
            self.positions[sender_id] = (msg.lat_deg, msg.lon_deg, msg.alt_amsl_m)
            self._pos_stamp[sender_id] = now

        # 2. ESP-NOW 250 byte bütçe kontrolü (gerçek serileştirme boyutu).
        if not self._within_budget(msg, sender_id):
            return  # Mesajı iptal et (Drop)

        # 3. Mesajı Sistemdeki Diğer Alıcılara (İHA'lar ve YKİ) Yönlendir
        sender_pos = self.positions[sender_id]

        # GCS de bir ağ ucudur; menzil dışına çıkarsa bağlantı kopar. Yalnız
        # gcs konumu gerçekten verildiyse VE gönderenin geçerli bir konumu
        # varsa anlamlı — aksi halde (0,0,0) her drona ~5500 km uzaktır ve
        # her mesajda sahte "koptu" uyarısı basardı.
        if self._gcs_configured and sender_pos is not None:
            gcs_dist = self.rf_model.distance_m(sender_pos, self.positions["gcs"])
            if gcs_dist > self.rf_model.cutoff_m:
                self.get_logger().warn(
                    f"BAĞLANTI KOPTU: {sender_id} GCS'ten çok uzak ({gcs_dist:.1f}m)"
                )

        # Diğer İHA'lara iletim — TEK ZAR (en yakın komşuya göre). Status mesh'te
        # non-kritik (POSE/DURUM, retry YOK) ama flooding ile aktarılır; paket
        # en yakın komşusuna ulaşınca mesh'e girer. Paylaşımlı public topic'te
        # alıcı-başına ayrı zar atmak duplicate yayına yol açardı; TEK karar,
        # TEK publish (bkz. _broadcast_drop).
        if self._broadcast_drop(sender_id):
            return  # tek-zar düştü → hiçbir alıcı almaz

        # Paket geçmeyi başardı! Sıralı kuyruğa ekle (kanal=sender_id).
        self._schedule(sender_id, self.public_pubs[sender_id], msg)

    def _on_internal_heartbeat(self, msg: LeaderHeartbeat):
        """Liderin heartbeat'ini public'e taşır (RELIABLE, mesh'te non-kritik).

        Gönderici = msg.leader_id. En yakın komşuya göre radyo kaybı zarı
        (tek-zar); geçerse jitter ile yayınlanır.
        """
        # Güncel lideri DROP'TAN ÖNCE yakala: bu heartbeat /public'e düşse bile
        # proxy gerçek lideri bilmeli (formation/mission fazı bunun konumunu
        # kullanır). Fault-injection'da bile lider odur, yalnız iletim kesilir.
        self._current_leader_id = msg.leader_id

        leader_key = f"drone{msg.leader_id}"

        # Fault-injection: lider elle menzil dışı işaretlenmişse heartbeat
        # hiç relay edilmez -> follower'lar 300ms'de timeout -> election.
        if leader_key in self.unreachable_agents:
            return

        if not self._within_budget(msg, f"{leader_key} heartbeat"):
            return

        # LEADER_HB mesh'te non-kritik (retry YOK) → en yakın komşuya göre
        # tek-zar radyo kaybı.
        if self._broadcast_drop(leader_key):
            return  # tek-zar düştü → hiçbir follower almaz

        self._schedule("heartbeat", self._hb_pub, msg)

    def _simple_relay(self, msg, publisher, channel_key: str):
        """Yalnızca jitter uygulayıp yayınlayan ortak yol.

        Kendisi hiçbir kayıp kararı vermez — mesafeye bağlı kayıp zarı, çağıran
        handler'da bu fonksiyondan ÖNCE atılır. Gönderen kimliği taşıyan kanallar
        (events, election, control, state, qr) _broadcast_drop; gönderen kimliği
        taşımayan ama LİDERDEN çıkan kanallar (formation, mission_state/qr_step/
        next_target) _leader_drop kullanır. Yalnız origin (baz istasyonu) ve qr_coords
        (GCS/operatör) bir drondan çıkmadığından mesafe uygulanamaz → yalnız jitter.
        """
        self._schedule(channel_key, publisher, msg)

    def _on_internal_state(self, msg: SwarmState):
        # SwarmState mesh'te non-kritik (TIP_SWARM_STATE, retry YOK) — lider
        # yayını, en yakın komşuya göre tek-zar (heartbeat ile aynı sınıf).
        if not self._within_budget(msg, "state"):
            return
        if self._broadcast_drop(f"drone{msg.leader_id}"):
            return
        self._simple_relay(msg, self._state_pub, "state")

    def _on_internal_event(self, msg: SystemEvent):
        if not self._within_budget(msg, "event"):
            return
        # source_agent_id==0 sistem/GCS kaynaklı demek — fiziksel bir verici
        # yok, mesafe kontrolü uygulanamaz (her zaman geçer). >0 ise gönderen
        # dronun konumuna göre mesafe kaybı zarı: havada giden event de kritik
        # olsun olmasın kaybolabilir (ACK yok), en yakın komşuya göre tek-zar.
        if msg.source_agent_id != 0:
            if self._broadcast_drop(f"drone{msg.source_agent_id}"):
                return
        self._simple_relay(msg, self._event_pub, "events")

    def _on_internal_qr(self, msg: QRMissionData):
        # Ham metin mesh'ten geçmez (firmware qr_veri_t 16 byte, çözülmüş
        # alanlar); /internal'da lokal tüketici için durur, /public'e (mesh)
        # geçerken proxy'nin kendi kopyasında temizlenir.
        msg.raw_text = ""
        msg.error_message = ""
        # QR_DATA mesh'te non-kritik (retry YOK) — algılayan dronun yayını,
        # en yakın komşuya göre tek-zar radyo kaybı.
        if not self._within_budget(msg, "qr_data"):
            return
        if self._broadcast_drop(f"drone{msg.detector_agent_id}"):
            return
        self._simple_relay(msg, self._qr_pub, "qr_data")

    def _on_internal_election(self, msg: ElectionResult):
        # Güncel lideri DROP'TAN ÖNCE yakala (heartbeat ile aynı ilke): election
        # /public'e düşse bile proxy yeni lideri bilmeli — formation/mission fazı
        # bunun konumunu kullanır.
        self._current_leader_id = msg.new_leader_id
        if not self._within_budget(msg, "election"):
            return
        # Gönderen = yeni seçilen lider (consensus_fsm'i bu mesajı yayınlar).
        # Havada giden election de kaybolabilir (ACK yok, tek atış) — gönderen
        # liderin konumuna göre en yakın komşuya tek-zar.
        if self._broadcast_drop(f"drone{msg.new_leader_id}"):
            return
        # Mesh'te election_veri_t.confirmed_ids sabit 4 slot (mesh_config.h);
        # ROS mesajı dinamik dizi olsa da gerçek paket ilk 4'ten fazlasını
        # taşıyamaz. Proxy'nin kendi kopyasında kırpılır (orijinal msg,
        # /internal tüketicileri için, dokunulmadan kalır).
        if len(msg.confirmed_by_agent_ids) > 4:
            mesh_msg = ElectionResult()
            mesh_msg.stamp = msg.stamp
            mesh_msg.sequence_num = msg.sequence_num
            mesh_msg.new_leader_id = msg.new_leader_id
            mesh_msg.election_round = msg.election_round
            mesh_msg.triggered_by_agent_id = msg.triggered_by_agent_id
            mesh_msg.reason = msg.reason
            mesh_msg.confirmed_by_agent_ids = list(msg.confirmed_by_agent_ids[:4])
            mesh_msg.message = msg.message
            msg = mesh_msg
        self._simple_relay(msg, self._election_pub, "election")

    def _on_internal_origin(self, msg: SwarmOrigin):
        if not self._within_budget(msg, "origin"):
            return
        # NOT: SwarmOrigin.leader_agent_id sabit-çapa/RTK modunda her zaman 0
        # (swarm_origin_publisher — "sabit çapa/RTK, tek seed yok"); mesajda
        # fiziksel göndereni (hangi drone/RPi'nin ESP32'sinden çıktığını)
        # tanımlayan bir alan yok. Bu yüzden menzil kontrolü burada
        # UYGULANAMAZ — uygulanırsa yanlış bir sender'a dayanıp yanlış karar
        # verirdik. Gerçek menzil davranışı için mesaja bir gönderen-drone
        # alanı eklenmesi gerekir (bilinen sınır).
        self._simple_relay(msg, self._origin_pub, "origin")

    def _on_internal_qr_coords(self, msg: QRCoordinates):
        # QR konum tablosu: statik, latched (origin sınıfı). Nadir yayınlanır,
        # yarışma öncesi bir kez girilir → mesafe zarı yok, yalnız jitter.
        # Gönderen GCS/operatör (fiziksel dron kimliği yok) → origin ile aynı
        # sebepten menzil/izolasyon kontrolü uygulanamaz. 6 QR ≈ 60 byte < 250;
        # bütçe kontrolü şişerse (çok fazla QR) yakalar.
        if not self._within_budget(msg, "qr_coords"):
            return
        self._simple_relay(msg, self._qr_coords_pub, "qr_coords")

    def _on_internal_formation(self, msg: FormationCommand):
        # Formation liderden çıkar (merkezi atama). Mesajda gönderen kimliği yok
        # ama fiziksel gönderen = güncel lider → mesafe kaybını liderin konumuna
        # göre uygula (_leader_drop; lider bilinmiyorsa kayıpsız). offset dizileri
        # dron sayısıyla büyür; 250 bütçe kontrolü taşmayı yakalar.
        if not self._within_budget(msg, "formation"):
            return
        if self._leader_drop():
            return
        self._simple_relay(msg, self._formation_pub, "formation")

    def _on_internal_mission_state(self, msg: UInt8):
        # Görev fazı UInt8; mission_fsm liderde tek yayıncı → fiziksel gönderen
        # = güncel lider, mesafe kaybını liderin konumuna göre uygula
        # (_leader_drop; lider bilinmiyorsa kayıpsız).
        if not self._within_budget(msg, "mission_state"):
            return
        if self._leader_drop():
            return
        self._simple_relay(msg, self._mission_state_pub, "mission_state")

    def _on_internal_mission_qr_step(self, msg: UInt8):
        # QR alt-adımı UInt8; formation_control gate ve mission1 manevra tetiği
        # bunu okur. mission_fsm liderde yayıncı → fiziksel gönderen = güncel
        # lider, mesafe kaybı liderin konumuna göre (_leader_drop).
        if not self._within_budget(msg, "mission_qr_step"):
            return
        if self._leader_drop():
            return
        self._simple_relay(msg, self._mission_qr_step_pub, "mission_qr_step")

    def _on_internal_mission_next_target(self, msg: MissionTarget):
        # Sonraki hedef MissionTarget; mission_fsm liderde tek yayıncı → fiziksel
        # gönderen = güncel lider, mesafe kaybı liderin konumuna göre (_leader_drop).
        if not self._within_budget(msg, "mission_next_target"):
            return
        if self._leader_drop():
            return
        self._simple_relay(
            msg, self._mission_next_target_pub, "mission_next_target"
        )

    def _on_internal_control(self, msg: SwarmControlCommand):
        """YKİ->İHA komutunu taşır. Komut da havadan (GCS→mesh) gider ve
        kaybolabilir: KOMUT kritik olsa da broadcast'te ACK yoktur, 3-retry
        yalnız yerel TX hatasını kurtarır (mesh_config.h). Bu yüzden GCS'in
        en yakın drone'una göre mesafe kaybı zarına tabidir — cutoff ötesinde
        zar %100 verir (GCS izolasyonu bu zarın içinde).

        Zar YALNIZCA gcs_lat/gcs_lon parametreyle gerçekten verildiyse
        (_gcs_configured) uygulanır; aksi halde GCS konumu (0,0,0) anlamsızdır
        ve kontrol her zaman "çok uzak" der, komutu (deadman/emergency dahil)
        sessizce keserdi — o durumda kanal zardan muaf kalır.
        """
        if not self._within_budget(msg, "control command"):
            return
        if self._gcs_configured and self._broadcast_drop("gcs"):
            return
        self._schedule("control", self._control_pub, msg)

    def destroy_node(self) -> bool:
        """Kapanışta bekleyen (henüz yayınlanmamış) mesajları iptal eder."""
        self._pending.clear()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NetworkProxyNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
