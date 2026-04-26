# Sürü İHA — Interface Contract
# TEKNOFEST 2026 Sürü İHA Yarışması
# v6.2-teknofest2026: 12 msg + 3 srv + 3 action

Bu dosya `swarm_interfaces` paketinin takım içi sözleşmesidir. Bu paketteki `.msg`, `.srv`, `.action`, topic adı, enum veya frame kuralı değişirse 3 geliştirici de haberdar edilmelidir.

---

## 1. Paket Yapısı

```text
swarm_interfaces/
├── msg/
│   ├── AgentStatus.msg           # Tek İHA/ajan durumu (donanım alanları eklendi)
│   ├── SwarmState.msg            # Sürü özeti + son olay özeti
│   ├── SwarmOrigin.msg           # [YENİ] Paylaşılan NED origin broadcast
│   ├── FormationCommand.msg      # Sürü seviyesinde formasyon hedefi
│   ├── AgentSetpoint.msg         # Her İHA için ayrı setpoint
│   ├── QRMissionData.msg         # QR algılama + parse edilmiş görev verisi
│   ├── NeighborInfo.msg          # Komşu İHA bilgisi (ORCA/APF girişi)
│   ├── SwarmControlCommand.msg   # Görev 2 joystick/kumanda sürü komutu
│   ├── SystemEvent.msg           # Event bus / olay bildirimi
│   ├── LandingZoneDetection.msg  # landing_zone_detector çıktısı
│   ├── LeaderHeartbeat.msg       # Aktif liderin consensus heartbeat mesajı
│   └── ElectionResult.msg        # Lider seçimi sonucunu duyuran topic mesajı
├── srv/
│   ├── AssignRole.srv            # Rol atama/güncelleme
│   ├── TriggerMission.srv        # GCS üzerinden görev başlatma/güvenlik komutu
│   └── ManageSwarmMember.srv     # Birey çıkarma/katma akışını başlatma isteği
└── action/
    ├── ExecuteFormation.action   # Formasyon icrası action arayüzü
    ├── ExecuteManeuver.action    # Pitch/roll/yaw manevra icrası action arayüzü
    └── ManageSwarmMember.action  # Birey çıkarma/katma uzun süreli action arayüzü
```

---

## 2. Frame ve Birim Kuralı

Ana kontrol ve PX4 tarafında **local NED frame** kullanılır.

```text
x: North / ileri yön bileşeni, metre
y: East / sağ yön bileşeni, metre
z: Down / aşağı yön bileşeni, metre
```

NED içinde yukarı çıkmak için `z` değeri azalır. Örneğin yerden 20 m yukarı hedef `z = -20.0`'dır.

### 2.1 ⚠️ GERÇEK DONANIM — Paylaşılan NED Origin Problemi

**SITL'de sorun olmaz. Sahada kritik hatadır.**

SITL'de tüm simüle drone'lar aynı simülatör origin'inden local NED kurar — frame'ler örtüşür.

Gerçek sahada PX4, her drone'un kendi GPS konumunu local NED origin'i olarak atar. 10 metre arayla konuşlanan iki drone'da:
- Drone 1: `x=0, y=0` → kendi fiziksel yeri
- Drone 2: `x=0, y=0` → kendi fiziksel yeri (Drone 1'den farklı!)

`formation_control` "Drone 2'yi x=5'e git" dediğinde her drone farklı bir yere gider.

**Çözüm: `SwarmOrigin.msg`**

Leader arming öncesinde GPS kilidini aldıktan sonra `/swarm/origin` topic'ine yayın yapar.
Diğer drone'ların `px4_interface`'leri bu origin'i MAVLink `SET_GPS_GLOBAL_ORIGIN` komutuyla PX4'e gönderir.
Tüm local NED frame'ler aynı GPS noktasına kilitlenir.

`formation_control`, `AgentStatus.origin_synced = false` olan hiçbir drone'a setpoint gönderMEZ.

### 2.2 GPS Koordinatı Kullanımı

`AgentStatus.lat_deg / lon_deg / alt_amsl_m` alanları gerçek GPS konumunu taşır.
Bu alanlar `SwarmOrigin` senkronizasyonu doğrulama ve GCS harita görüntüleme için kullanılır.
Formation hesapları yalnızca origin sync sonrasında local NED üzerinden yapılır.

### 2.3 Diğer Frame Kuralları

`QRMissionData.altitude_agl_m` pozitif yukarıdır. NED `z` dönüşümü kontrol katmanında yapılır.
`LandingZoneDetection.zone_x/y/z` algılayan drone'a göreli NED'dir.
GCS/RViz ENU kullanan taraflarda dönüşüm açıkça yapılmalıdır.

---

## 3. Topic Tablosu

| Arayüz | Topic | Yayıncı | Dinleyici | QoS |
|---|---|---|---|---|
| `AgentStatus.msg` | `/swarm/agent/{id}/status` | `agent_fsm_node` | `mission_fsm`, `swarm_fsm`, `GCS`, `diagnostics` | BEST_EFFORT, 5-20 Hz |
| `SwarmState.msg` | `/swarm/state` | `swarm_fsm` | `GCS`, `mission_fsm`, `logger` | RELIABLE, 1-10 Hz |
| `SwarmOrigin.msg` | `/swarm/origin` | leader `px4_interface` | tüm follower `px4_interface`'leri | RELIABLE + TRANSIENT_LOCAL, 0.2-1 Hz |
| `FormationCommand.msg` | `/swarm/formation/target` | `mission_fsm` | `formation_control` | RELIABLE, event |
| `AgentSetpoint.msg` | `/drone_{id}/control/setpoint` | `swarm_core/formation_control`, `swarm_core/formation_control/maneuver_executor_node.py`, `failsafe_fsm/failsafe_handler.py` | ilgili drone `px4_interface` | BEST_EFFORT/RELIABLE, 10-50 Hz |
| `QRMissionData.msg` | `/swarm/perception/qr_data` | `qr_detector` / `qr_mission_parser` | `mission_fsm`, `consensus_fsm` | RELIABLE, event |
| `LandingZoneDetection.msg` | `/drone_{id}/perception/landing_zone` | `landing_zone_detector` (lokal) | `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py` (lokal), `GCS bridge` | BEST_EFFORT, 20-50 Hz |
| `NeighborInfo.msg` | `/swarm/agent/{self_id}/neighbor/{neighbor_id}` | `swarm_core/consensus/neighbor_monitor_node.py` | `collision_avoidance`, `consensus` | BEST_EFFORT, 5-20 Hz |
| `SwarmControlCommand.msg` | `/swarm/control/command` | `swarm_state_machine/mode_manager/joystick_interpreter_node.py` | `mode_manager/movement_mode.py`, `mode_manager/maneuver_mode.py`, `swarm_core/formation_control` | BEST_EFFORT, 20-50 Hz |
| `SystemEvent.msg` | `/swarm/events/system` | `event_bus`, `failsafe_manager`, `mission_fsm`, `perception` | `GCS`, `logger`, `diagnostics`, `swarm_fsm` | RELIABLE, event |
| `LeaderHeartbeat.msg` | `/swarm/leader/heartbeat` | aktif lider `consensus_fsm` | follower `consensus_fsm`, `swarm_fsm`, `failsafe_manager` | RELIABLE + VOLATILE, depth=5, 10 Hz |
| `ElectionResult.msg` | `/swarm/election/result` | yeni lider `consensus_fsm` | `consensus_fsm`, `swarm_fsm`, `mission_fsm`, `GCS bridge` | RELIABLE + TRANSIENT_LOCAL, depth=10, event |
| `ExecuteFormation.action` | `/swarm/formation/execute` | `formation_control` action server | `mission_fsm` / `mission_orchestrator` | — |
| `ExecuteManeuver.action` | `/swarm/maneuver/execute` | `swarm_core/formation_control/maneuver_executor_node.py` action server | `mission_fsm`, `mode_manager` | — |
| `ManageSwarmMember.action` | `/swarm/member/manage` | `swarm_missions/mission1_dynamic_swarm/member_manager_node.py` / target `agent_fsm` action server | `mission_fsm`/`mission_orchestrator` | — |
| `AssignRole.srv` | `/swarm/assign_role` | `agent_fsm_node` | `consensus_fsm`, `mission_orchestrator` | — |
| `TriggerMission.srv` | `/swarm/mission/trigger` | `mission_fsm` | `GCS backend` | — |
| `ManageSwarmMember.srv` | `/swarm/member/manage_request` | `swarm_missions/mission1_dynamic_swarm/member_manager_node.py` / `mission_fsm` | `GCS backend`, debug/test tools | — |

### 3.1 Topic Adı Netleştirmesi

`/swarm/agent/{self_id}/neighbor/{neighbor_id}`: `{self_id}` yayıncı drone, `{neighbor_id}` gözlemlenen drone.
`/drone_{id}/perception/landing_zone`: `{id}` kamerayı çalıştıran drone. Lokal onboard topic'tir.
`/swarm/origin`: RELIABLE + TRANSIENT_LOCAL durability kullanılmalıdır; yeni başlayan follower drone son değeri otomatik alır.
`/drone_{id}/control/setpoint`: `{id}` hedef setpoint alacak drone. Yüksek frekanslı onboard/local kontrol topic’idir.
`/swarm/leader/heartbeat`: yalnızca aktif lider yayınlar; follower’lar timeout ile election başlatır.
`/swarm/election/result`: yeni lider seçimi sonucunu duyurur; servis değil topic tabanlıdır.
`/swarm/maneuver/execute`: QR veya joystick kaynaklı pitch/roll/yaw manevralarını uzun süreli action olarak yürütür.
`/swarm/member/manage`: QR kaynaklı detach/rejoin/standby replacement akışını uzun süreli action olarak yürütür.
`/swarm/member/manage_request`: yalnızca hızlı başlatma/debug içindir; tamamlanma takibi için action tercih edilir.

### 3.2 AgentStatus Gerçek Donanım Kullanım Notu

`AgentStatus.flight_mode`, `offboard_active` ve `pilot_override_active` gerçek uçuşta zorunlu izleme alanlarıdır. `mode_manager` ve `failsafe_fsm`, PX4'ün MANUAL/POSCTL/OFFBOARD/RTL/LAND gibi modlarını bu alanlardan okumalıdır. Pilot override aktifse otomatik setpoint zinciri HOLD/SAFE durumuna alınmalıdır.

EKF2/estimator alanları gerçek donanımda pre-flight ve in-flight güvenlik için zorunlu kabul edilir. `estimator_ok=false`, `xy_valid=false`, `z_valid=false` veya `v_xy_valid=false` olan drone'a normal formation setpoint gönderilmemeli; ilgili drone HOLD/FAILSAFE akışına alınmalıdır. Sensör health alanları true olsa bile EKF2 diverge edebileceği için bu dört alan ayrı kontrol edilir.

### 3.3 AgentSetpoint Gerçek Donanım Kullanım Notu

`AgentSetpoint` yüksek frekanslı uçuş hedefidir. Gerçek uçuşta bu akışın `swarm_core/formation_control` / `swarm_core/formation_control/maneuver_executor_node.py` ile `px4_interface` arasında onboard/local çalışması önerilir. GCS veya merkezi WiFi üzerinden sürekli yüksek frekanslı setpoint gönderimi gecikme, paket kaybı ve failsafe riski oluşturabilir. GCS yalnızca görev başlatma, izleme ve güvenlik komutları için kullanılmalıdır.

### 3.4 Mevcut Mimariye Yerleştirme Kuralı

Bu contract içinde geçen bazı fonksiyonel adlar yeni ana klasör açmak anlamına gelmez. Takımın mevcut `src/` mimarisine sadık kalınacak ve ek action/service rollerinin karşılığı mevcut klasörlerin içinde node dosyası olarak tutulacaktır.

| Fonksiyonel rol | Mevcut mimarideki karşılık | Not |
|---|---|---|
| `maneuver_executor` | `swarm_core/formation_control/maneuver_executor_node.py` | `ExecuteManeuver.action` server; pitch/roll/yaw manevrası için |
| `member_manager` | `swarm_missions/mission1_dynamic_swarm/member_manager_node.py` | `ManageSwarmMember.action/srv` server |
| `precision_landing` | `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py` | `LandingZoneDetection` tüketicisi; agent iniş akışı |
| `joystick_interpreter` | `swarm_state_machine/mode_manager/joystick_interpreter_node.py` | `SwarmControlCommand` publisher; Görev 2 komut yorumlayıcı |
| `inter_drone_comm` | `swarm_core/consensus/neighbor_monitor_node.py` | `NeighborInfo` publisher; komşu/liderlik izleme |

Bu nedenle yeni ana klasör açmak yerine yukarıdaki dosya yolları kullanılacaktır.

---

## 4. Ana Veri Akışları

### 4.0 Uçuş Öncesi — Origin Senkronizasyonu (GERÇEK DONANIM)

```text
1. Leader GPS kilidi alır (gps_fix_type >= 3, hdop < 1.5)
2. Leader /swarm/origin [SwarmOrigin.msg] yayınlar  ← RELIABLE + TRANSIENT_LOCAL
3. Follower px4_interface'leri mesajı alır
4. Her follower MAVLink SET_GPS_GLOBAL_ORIGIN gönderir → PX4 local frame'ini sıfırlar
5. Follower AgentStatus.origin_synced = true ayarlar
6. formation_control tüm drone'ların origin_synced=true olmasını bekler
7. Ancak bundan sonra arming + takeoff izni
```

### 4.1 Görev 1: Dinamik Sürü Kabiliyeti

```text
GCS → /swarm/mission/trigger [TriggerMission.srv]
  → mission_fsm
  → /swarm/formation/target [FormationCommand.msg]
  → formation_control
  → /drone_{id}/control/setpoint [AgentSetpoint.msg]  ← max_speed_mps burada taşınır
  → px4_interface → PX4 TrajectorySetpoint
```

QR akışı:
```text
qr_detector → /swarm/perception/qr_data [QRMissionData.msg]
  → mission_fsm
  → formation_active ise FormationCommand / ExecuteFormation.action
  → maneuver_active ise ExecuteManeuver.action
  → altitude_active ise FormationCommand.center_z veya AgentSetpoint hedef irtifa akışı
  → detach_active ise ManageSwarmMember.action
```

Manevra akışı:
```text
QRMissionData.pitch_deg/roll_deg/yaw_deg
  → mission_fsm
  → /swarm/maneuver/execute [ExecuteManeuver.action]
  → `swarm_core/formation_control/maneuver_executor_node.py`
  → /drone_{id}/control/setpoint [AgentSetpoint.msg, source=MANEUVER_EXECUTOR]
  → px4_interface → PX4
```

Birey çıkarma/katma akışı:
```text
QRMissionData.detach_active + detach_agent_id + detach_target_color + wait_s
  → mission_fsm
  → /swarm/member/manage [ManageSwarmMember.action]
  → `swarm_missions/mission1_dynamic_swarm/member_manager_node.py` / target `agent_fsm`
  → `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py` + disarm wait + rearm + rejoin
  → SystemEvent: AGENT_DETACHED, PRECISION_LANDING_COMPLETED, AGENT_REJOINED
```

Precision landing akışı:
```text
landing_zone_detector → /drone_{id}/perception/landing_zone [LandingZoneDetection.msg]  20-50 Hz
  → `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py` → AgentSetpoint → px4_interface → PX4
```

### 4.2 Görev 2: Yarı Otonom Sürü Kontrolü

```text
`swarm_state_machine/mode_manager/joystick_interpreter_node.py` → /swarm/control/command [SwarmControlCommand.msg]
  → `mode_manager/movement_mode.py` / `mode_manager/maneuver_mode.py`
  → `swarm_core/formation_control` / `swarm_core/formation_control/maneuver_executor_node.py`
  → AgentSetpoint (max_speed_mps, max_tilt_deg kopyalanır)
  → px4_interface
```

### 4.3 SWARM_ROTATING Akışı

QR noktaları arasında geçişte formasyonun hedef QR doğrultusuna döndürülmesi açık bir swarm state geçişi olarak izlenmelidir.

```text
mission_fsm next_qr hedefini belirler
  → FormationCommand.rotate_towards_target=true yayınlar
  → SystemEvent.EVENT_ROTATION_STARTED yayınlanır
  → swarm_fsm swarm_state=SWARM_ROTATING yapar
  → `swarm_core/formation_control` veya `swarm_core/formation_control/maneuver_executor_node.py` heading/rotasyon hedefini uygular
  → rotasyon tolerans içine girince SystemEvent.EVENT_ROTATION_COMPLETED yayınlanır
  → swarm_fsm swarm_state=SWARM_NAVIGATING yapar
```

`SWARM_ROTATING`, normal formasyon değişimiyle karıştırılmamalıdır. Bu state, sürünün mevcut formasyonunu koruyarak sadece hedef doğrultuya hizalanmasını temsil eder.

---

## 5. Ortak Enum Sözleşmeleri

### ROLE Enum
```
0=UNKNOWN  1=LEADER  2=FOLLOWER  3=STANDBY  4=DETACHED
```

### AGENT STATE Enum
`AgentStatus.msg` ↔ `agent_states.py` ↔ `NeighborInfo.neighbor_state` — hepsi aynı değerleri kullanır.
```
0=UNKNOWN  1=IDLE  2=ARMING  3=ARMED  4=TAKEOFF  5=IN_SWARM
6=EXECUTING_TASK  7=DETACHED  8=PRECISION_LANDING  9=WAITING_REJOIN
10=REJOINING  11=RETURN_HOME  12=LANDING  13=LANDED  14=FAILSAFE  15=STANDBY
```
ORCA/APF: komşu state `7,8,13,14` ise avoidance hesabına dahil etme.

### SWARM STATE Enum
`SwarmState.msg` ↔ `swarm_states.py`
```
0=UNKNOWN  1=IDLE  2=FORMING  3=NAVIGATING  4=EXECUTING_TASK
5=ROTATING  6=LANDING  7=RTL  8=FAILSAFE  9=MISSION_COMPLETE
```

### FORMATION Enum
`FormationCommand`, `ExecuteFormation.action`, `QRMissionData`, `SwarmState`, `SwarmControlCommand`
```
0=UNKNOWN  1=OKBASI  2=V  3=CIZGI  99=CUSTOM
```

### COLOR Enum
`QRMissionData` ve `LandingZoneDetection`
```
0=UNKNOWN  1=RED  2=BLUE
```

### MANEUVER Enum
`ExecuteManeuver.action`
```
0=UNKNOWN  1=PITCH  2=ROLL  3=YAW  4=PITCH_ROLL  99=CUSTOM
```

### MEMBER OPERATION Enum
`ManageSwarmMember.action` ve `ManageSwarmMember.srv`
```
0=UNKNOWN  1=DETACH  2=REJOIN  3=REPLACE_WITH_STANDBY
```

### GPS FIX TYPE Enum
`AgentStatus.gps_fix_type` ve `SwarmOrigin.gps_fix_type`
```
0=NO_FIX  1=NO_FIX_2  2=2D_FIX  3=3D_FIX  4=DGPS  5=RTK_FLOAT  6=RTK_FIXED
```
Arming için minimum: `3D_FIX (3)`. HDOP < 1.5 beklenmeli.

### EVENT Enum
`SwarmState.msg` ↔ `SystemEvent.msg`

**Ajan (1-19):** `1=AGENT_READY  2=AGENT_REACHED_POS  3=AGENT_DETACHED  4=AGENT_LANDED  5=AGENT_REJOINED  6=AGENT_FAULT  7=AGENT_JOIN_REQUEST  8=AGENT_PILOT_OVERRIDE`

**Algı/Görev (20-39):** `20=QR_DETECTED  21=QR_PARSED  22=FORMATION_REACHED  23=FORMATION_FAILED  24=MISSION_STARTED  25=MISSION_COMPLETED  26=COLOR_ZONE_DETECTED  27=QR_SEQUENCE_REJECTED  28=PRECISION_LANDING_STARTED  29=PRECISION_LANDING_COMPLETED  30=ROTATION_STARTED  31=ROTATION_COMPLETED  32=MANEUVER_STARTED  33=MANEUVER_COMPLETED  34=MANEUVER_FAILED  35=MEMBER_DETACH_STARTED  36=MEMBER_REJOIN_STARTED  37=MEMBER_MANAGEMENT_FAILED`

**Sistem/Güvenlik (40-59):** `40=GCS_LINK_LOST  41=GCS_LINK_RESTORED  42=BATTERY_LOW  43=COLLISION_RISK  44=OFFBOARD_LOST  45=RTL_TRIGGERED  46=EMERGENCY_LAND  47=PX4_LINK_LOST  48=LEADER_CHANGED  49=SAFETY_HOLD  50=FAILSAFE_CLEARED  51=ORIGIN_READY  52=ORIGIN_SYNCED  53=ORIGIN_FAILED`

### EVENT SEVERITY Enum
```
0=INFO  1=WARNING  2=CRITICAL  3=EMERGENCY
```

---

## 6. Kritik Kurallar

1. `QRMissionData.qr_seq` monoton artar. Stale/sıra dışı mesajlar `mission_fsm` tarafından düşürülür.
2. `QRMissionData.altitude_agl_m` pozitif yukarıdır. NED `z` dönüşümü kontrol katmanında yapılır.
3. `*_active` flag'leri `command_type`'tan önce gelir — bir QR birden fazla komut içerebilir.
4. `FormationCommand` sürü seviyesidir, doğrudan PX4'e gitmez.
5. `AgentSetpoint` ajan başınadır. `px4_interface` PX4 TrajectorySetpoint'e çevirir.
   **Gerçek donanım notu:** PX4’e giden yüksek frekanslı setpoint akışı onboard/local çalışmalıdır; GCS veya merkezi WiFi üzerinden sürekli setpoint gönderimi gerçek uçuşta önerilmez.

`AgentSetpoint.priority` px4_interface için arbitration alanıdır. Aynı anda birden fazla kaynak setpoint üretirse öncelik sırası şu olmalıdır: `FAILSAFE > COLLISION_AVOIDANCE > MANEUVER > POSITION > FORMATION`. `yaw_rate_deg_s` smooth formasyon rotasyonu ve Görev 2 yaw manevrası için korunmalıdır.
6. GCS yalnızca `TriggerMission.srv` üzerinden komut gönderir (START / ABORT / RTL / LAND / PAUSE / RESUME).
7. **`AgentSetpoint.max_speed_mps` / `max_acc_mps2`**: `SwarmControlCommand`'dan `swarm_core/formation_control`/`swarm_core/formation_control/maneuver_executor_node.py` tarafından buraya kopyalanır. `0.0` = varsayılan kullan.
8. **`NeighborInfo.neighbor_state`**: ORCA/APF state `7,8,13,14` komşuları için avoidance yapmaz.
9. **`NeighborInfo.data_age_ms > 500`**: Bu komşuyu avoidance hesabından çıkar; position ve velocity verisi çok eski.
10. **`LandingZoneDetection`**: `QRMissionData.zone_*` yalnızca QR parse snapshot'ıdır; `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py` sürekli takip için bu ayrı topic'i kullanır.
11. **`AgentStatus.battery_voltage_v`**: Yüzde değil gerilim izlenir. PX4 failsafe voltage-based tetiklenir.
12. **`AgentStatus.origin_synced`**: `formation_control`, `origin_synced=false` drone'lara setpoint göndermez.
13. **`AgentStatus.home_set`**: GCS arming öncesi `home_set=false` olan drone'u işaretler; bu drone RTL komutunu reddetmeli.
14. **`SwarmOrigin.msg`**: Leader arming öncesi GPS kilidi doğrulandıktan sonra yayınlar. Follower'lar `SET_GPS_GLOBAL_ORIGIN` gönderince `origin_synced=true` ayarlar.
15. **`LeaderHeartbeat`**: Sadece aktif lider `consensus_fsm` tarafından 10 Hz yayınlanır. Follower tarafında timeout değeri config ile 300–500 ms aralığında tutulur.
16. **`ElectionResult`**: Lider seçimi sonucu `AssignRole.srv` ile değil `/swarm/election/result` topic’i ile duyurulur. `sequence_num` ve `election_round` eski mesajları reddetmek için kullanılmalıdır.
17. **`AssignRole.srv`**: Gerçek zamanlı leader election için kullanılmaz; yalnızca pre-flight, manuel/debug rol atama için kullanılır.
18. **`ExecuteManeuver.action`**: QR'dan gelen `pitch_deg`/`roll_deg`/`yaw_deg` değerleri `FormationCommand` içine gömülmez; `mission_fsm` bu action üzerinden `swarm_core/formation_control/maneuver_executor_node.py`'a gönderir. `mission_fsm`, action result success olmadan sonraki QR adımına geçmez.
19. **`ManageSwarmMember.action`**: QR kaynaklı birey çıkarma/katma uzun süren bir akıştır. `mission_fsm`, detach/rejoin tamamlanmadan sonraki görev adımına geçmez.
20. **`ManageSwarmMember.srv`**: Sadece hızlı başlatma, debug veya GCS isteği için kullanılmalıdır. Uzun süreli tamamlanma takibi gerekiyorsa action kullanılmalıdır.
21. **`SWARM_ROTATING`**: `FormationCommand.rotate_towards_target=true` geldiğinde `swarm_fsm` `SWARM_ROTATING` state'ini açıkça kullanmalı; `EVENT_ROTATION_COMPLETED` sonrası `SWARM_NAVIGATING` durumuna dönmelidir.
22. Interface değişikliğinde `CMakeLists.txt`, bu dosya ve ilgili node kodları birlikte güncellenir.

---

## 7. Gerçek Donanım Pre-flight Checklist (GCS Otomasyonu)

GCS backend, `START` komutuna izin vermeden önce her drone için şunları doğrulamalıdır:

```
✓ AgentStatus.gps_fix_type >= 3  (3D GPS kilidi)
✓ AgentStatus.gps_hdop < 1.5    (yeterli GPS kalitesi)
✓ AgentStatus.home_set = true   (RTL hedefi set edildi)
✓ AgentStatus.origin_synced = true  (NED frame senkron)
✓ AgentStatus.battery_voltage_v > THRESHOLD  (uçuş için yeterli gerilim)
✓ AgentStatus.imu_healthy = true
✓ AgentStatus.mag_healthy = true
✓ AgentStatus.baro_healthy = true
✓ AgentStatus.estimator_ok = true
✓ AgentStatus.xy_valid = true
✓ AgentStatus.z_valid = true
✓ AgentStatus.v_xy_valid = true
✓ AgentStatus.px4_link_ok = true
✓ AgentStatus.gcs_link_ok = true
```

---

## 8. Build ve Kontrol

```bash
colcon build --packages-select swarm_interfaces
source install/setup.bash

ros2 interface list | grep swarm_interfaces
ros2 interface show swarm_interfaces/msg/AgentStatus
ros2 interface show swarm_interfaces/msg/SwarmOrigin
ros2 interface show swarm_interfaces/msg/FormationCommand
ros2 interface show swarm_interfaces/msg/AgentSetpoint
ros2 interface show swarm_interfaces/msg/QRMissionData
ros2 interface show swarm_interfaces/msg/NeighborInfo
ros2 interface show swarm_interfaces/msg/SwarmControlCommand
ros2 interface show swarm_interfaces/msg/SystemEvent
ros2 interface show swarm_interfaces/msg/LandingZoneDetection
ros2 interface show swarm_interfaces/msg/LeaderHeartbeat
ros2 interface show swarm_interfaces/msg/ElectionResult
ros2 interface show swarm_interfaces/srv/TriggerMission
ros2 interface show swarm_interfaces/srv/ManageSwarmMember
ros2 interface show swarm_interfaces/action/ExecuteFormation
ros2 interface show swarm_interfaces/action/ExecuteManeuver
ros2 interface show swarm_interfaces/action/ManageSwarmMember
```
