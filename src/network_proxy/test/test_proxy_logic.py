"""test_proxy_logic.py - proxy karar mantığı testleri (rclpy, spin YOK).

Deterministik: konumlar ya aynı (0 m -> drop olasılığı 0, asla düşmez) ya da
1° uzak (~111 km -> cutoff ötesi, hep düşer). Böylece rastgeleliğe gerek yok.
Relay olup olmadığı, gecikme kuyruğuna (_pending) mesaj eklendi mi ile ölçülür.
"""

import pytest
import rclpy

from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    LeaderHeartbeat,
    MissionTarget,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from network_proxy.network_proxy_node import NetworkProxyNode

_YAKIN = (41.0, 29.0, 0.0)          # 0 m -> asla düşmez
_UZAK = (42.0, 29.0, 0.0)           # ~111 km -> cutoff ötesi, hep düşer


@pytest.fixture(scope="module")
def node():
    rclpy.init()
    n = NetworkProxyNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _reset(n):
    """Her testten önce: kuyruğu boşalt, fault temizle, herkesi yakına al.

    _pos_stamp temizlenir -> damgası olmayan konum "taze" sayılır (tazelik
    denetimi yalnız açıkça eski damga konanları atar).
    """
    n._pending.clear()
    n.unreachable_agents = set()
    n._pos_stamp.clear()
    n._current_leader_id = None
    for a in n.agent_ids:
        n.positions[a] = _YAKIN


# _within_budget (250 byte)
def test_within_budget_normal_gecer(node):
    _reset(node)
    assert node._within_budget(AgentStatus(), "test") is True


def test_within_budget_asan_dusurulur(node):
    _reset(node)
    msg = AgentStatus()
    msg.status_text = "x" * 300  # 250'yi kesin aşar
    assert node._within_budget(msg, "test") is False


# _broadcast_drop (mesafe + fault)
def test_broadcast_yakin_dusmez(node):
    _reset(node)
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_izole_duser(node):
    """Gönderen TÜM komşularından menzil dışıysa (en yakın komşu bile
    cutoff ötesi) non-kritik yayın düşer - mesh'e hiç giremez."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # gönderen komşularından izole
    assert node._broadcast_drop("drone1") is True


def test_broadcast_bir_komsu_uzak_digeri_yakin_gecer(node):
    """Bir alıcı uzak, bir alıcı yakınsa yayın GEÇER - en yakın komşu
    paketi mesh'e sokar (multi-hop). Eski 'en uzak alıcı' modeli bunu
    yanlışlıkla düşürürdü."""
    _reset(node)
    node.positions["drone3"] = _UZAK  # drone1 hâlâ drone2 ile _YAKIN
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_none_failopen(node):
    _reset(node)
    node.positions["drone1"] = None  # henüz konum bildirmedi
    assert node._broadcast_drop("drone1") is False


def test_broadcast_gonderen_unreachable_keser(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    assert node._broadcast_drop("drone1") is True


def test_broadcast_uzak_alici_unreachable_sayilmaz(node):
    _reset(node)
    node.positions["drone2"] = _UZAK
    node.unreachable_agents = {"drone2"}  # "gitmiş" alıcı komşu adayı değil
    assert node._broadcast_drop("drone1") is False


# reliability sınıfları (mesh retry hizası)
def test_control_gcs_konumsuzken_uzakta_bile_iletilir(node):
    """GCS konumu verilmediginde kontrol menzil disi olsa bile gecer.

    (gcs verilince zar uygulanir: bkz. test_control_gcs_mesafe_zari.)
    """
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_control(SwarmControlCommand())
    assert len(node._pending) == 1


def test_state_gonderen_izole_dusurulur(node):
    """SWARM_STATE non-kritik -> mesafe zarı VAR; lider komşularından
    izole ise (en yakın komşu bile cutoff ötesi) düşer."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # lider komşularından izole
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 0


def test_state_yakinda_iletilir(node):
    _reset(node)
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 1


# QR: raw_text temizleme + mesafe
def test_qr_raw_text_temizlenir(node):
    _reset(node)
    m = QRMissionData()
    m.detector_agent_id = 1
    m.raw_text = "team_id=YELPENCE; formation=V"
    m.error_message = "hata"
    node._on_internal_qr(m)
    assert len(node._pending) == 1
    _, _, _, sched = node._pending[0]
    assert sched.raw_text == ""
    assert sched.error_message == ""


def test_qr_gonderen_izole_dusurulur(node):
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # algılayan komşularından izole
    m = QRMissionData()
    m.detector_agent_id = 1
    node._on_internal_qr(m)
    assert len(node._pending) == 0


# fault-injection tutarlılığı
def test_faultinjection_status_kesilir(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    msg = AgentStatus()
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = _YAKIN
    node.internal_status_callback(msg, "drone1")
    assert len(node._pending) == 0


def test_faultinjection_state_de_kesilir(node):
    """Lider menzil dışı -> SwarmState de kesilmeli (tutarlılık düzeltmesi)."""
    _reset(node)
    node.unreachable_agents = {"drone1"}
    m = SwarmState()
    m.leader_id = 1
    node._on_internal_state(m)
    assert len(node._pending) == 0


def test_status_yakinda_iletilir(node):
    _reset(node)
    msg = AgentStatus()
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = _YAKIN
    node.internal_status_callback(msg, "drone1")
    assert len(node._pending) == 1


# Kritik kanallarda fiziksel menzil denetimi
# (esp_now_send başarısızlığı hariç kapsama dışındaki sinyali kurtarmaz)
def test_election_yakinda_iletilir(node):
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 1


def test_election_confirmed_ids_dorde_kirpilir(node):
    """Mesh'te election_veri_t.confirmed_ids sabit 4 slot (mesh_config.h);
    5+ onaylayan ID gelirse proxy ilk 4'e kırpar (gerçek paket kapasitesi)."""
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    m.confirmed_by_agent_ids = [1, 2, 3, 4, 5]
    node._on_internal_election(m)
    assert len(node._pending) == 1
    _, _, _, sched = node._pending[0]
    assert list(sched.confirmed_by_agent_ids) == [1, 2, 3, 4]


def test_election_confirmed_ids_dortten_azsa_dokunulmaz(node):
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 1
    m.confirmed_by_agent_ids = [1, 2]
    node._on_internal_election(m)
    _, _, _, sched = node._pending[0]
    assert list(sched.confirmed_by_agent_ids) == [1, 2]


def test_election_gonderen_izole_dusurulur(node):
    """Yeni lider (new_leader_id) TÜM komşularından menzil dışıysa (izole)
    election düşer - mesh'e paketi sokacak komşu yok. Gönderen uzakta,
    komşular birbirine yakın (başka bir kümede)."""
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # gönderen komşularından ~111 km uzak
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 0


def test_election_bir_komsuya_yakinsa_iletilir(node):
    """Multi-hop: lider bir komşuyla menzilde, diğeri uzak olsa bile
    election iletilir - yakın komşu paketi mesh'e sokup geri kalana yayar.
    (Eski 'en uzak alıcı' modeli bunu yanlışlıkla düşürürdü.)"""
    _reset(node)
    # drone1 (gönderen/lider) drone2 ile _YAKIN, drone3 uzak
    node.positions["drone3"] = _UZAK
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 1


def test_election_gonderen_unreachable_keser(node):
    _reset(node)
    node.unreachable_agents = {"drone1"}
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert len(node._pending) == 0


def test_event_kaynaksiz_menzil_kontrolsuz_iletilir(node):
    """source_agent_id==0 (sistem/GCS) -> fiziksel verici yok, menzil
    kontrolü uygulanmaz, her zaman geçer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    m = SystemEvent()
    m.source_agent_id = 0
    node._on_internal_event(m)
    assert len(node._pending) == 1


def test_event_kaynak_izole_dusurulur(node):
    _reset(node)  # drone2, drone3 _YAKIN kalır
    node.positions["drone1"] = _UZAK  # kaynak komşularından izole
    m = SystemEvent()
    m.source_agent_id = 1
    node._on_internal_event(m)
    assert len(node._pending) == 0


# QRCoordinates (latched, origin sınıfı)
def test_qr_coords_uzakta_bile_iletilir(node):
    """QR tablosu latched/statik -> mesafe zari yok, hep gecer."""
    _reset(node)
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    m = QRCoordinates()
    m.qr_ids = [1, 2, 3, 4, 5, 6]
    m.lat_deg = [41.0] * 6
    m.lon_deg = [29.0] * 6
    node._on_internal_qr_coords(m)
    assert len(node._pending) == 1


def test_qr_coords_asiri_buyuk_dusurulur(node):
    """Çok fazla QR (250 byte'ı aşan tablo) bütçe kontrolünde düşer."""
    _reset(node)
    m = QRCoordinates()
    n = 300  # 300 QR -> 250 byte'ı kesin aşar
    m.qr_ids = [1] * n
    m.lat_deg = [41.0] * n
    m.lon_deg = [29.0] * n
    node._on_internal_qr_coords(m)
    assert len(node._pending) == 0


def test_control_gcs_konumsuzken_muaf(node):
    """GCS konumu verilmediyse control menzilden muaf kalir.

    Mevcut davranis korunur.
    """
    _reset(node)
    assert node._gcs_configured is False
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_control(SwarmControlCommand())
    assert len(node._pending) == 1


def test_control_gcs_mesafe_zari(node):
    """gcs konumu elle verilince control kanalı _broadcast_drop('gcs') ile
    mesafe kaybına tabi: GCS bir drone'a yakınsa geçer, TÜM droneler cutoff
    ötesindeyse (izolasyon) eğrinin ucu %100 verip düşürür. GCS'i doğrudan
    veriyoruz çünkü test node'da gcs_lat/lon parametreyle verilmedi."""
    _reset(node)
    node.positions["gcs"] = _YAKIN
    assert node._broadcast_drop("gcs") is False  # en az bir drone menzilde
    # GCS bir drone'a ulaşabildiği sürece geçer (en yakın komşu mesh'e sokar)
    node.positions["drone1"] = _UZAK
    assert node._broadcast_drop("gcs") is False
    # Ancak TÜM droneler cutoff ötesindeyse -> eğri %100 -> düşer
    node.positions["drone2"] = _UZAK
    node.positions["drone3"] = _UZAK
    assert node._broadcast_drop("gcs") is True


# A: GPS geçerlilik denetimi (çöp konum sokulmaz)
def test_gps_gecersiz_fix_saklanmaz(node):
    """gps_fix_type < 3 (kilit yok) -> konum güncellenmez; ham koordinat
    mesafe matematiğine sokulmaz."""
    _reset(node)
    node.positions["drone1"] = None
    msg = AgentStatus()
    msg.gps_fix_type = 0
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = _YAKIN
    node.internal_status_callback(msg, "drone1")
    assert node.positions["drone1"] is None
    assert "drone1" not in node._pos_stamp


def test_gps_sifir_koordinat_saklanmaz(node):
    """3D fix olsa bile (0,0) koordinat saklanmaz - Gine Körfezi sahte
    mesafesini önler."""
    _reset(node)
    node.positions["drone1"] = None
    msg = AgentStatus()
    msg.gps_fix_type = 3
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = 0.0, 0.0, 0.0
    node.internal_status_callback(msg, "drone1")
    assert node.positions["drone1"] is None


def test_gps_gecerli_saklanir(node):
    """3D fix + geçerli koordinat -> konum ve zaman damgası güncellenir."""
    _reset(node)
    node.positions["drone1"] = None
    msg = AgentStatus()
    msg.gps_fix_type = 3
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = 41.0, 29.0, 5.0
    node.internal_status_callback(msg, "drone1")
    assert node.positions["drone1"] == (41.0, 29.0, 5.0)
    assert "drone1" in node._pos_stamp


def test_gps_gecersizde_son_gecerli_korunur(node):
    """Kilit kaybolunca son konum korunur."""
    _reset(node)
    node.positions["drone1"] = (41.0, 29.0, 5.0)
    node._pos_stamp["drone1"] = node.get_clock().now().nanoseconds / 1e9
    msg = AgentStatus()
    msg.gps_fix_type = 0
    msg.lat_deg, msg.lon_deg, msg.alt_amsl_m = 0.0, 0.0, 0.0
    node.internal_status_callback(msg, "drone1")
    assert node.positions["drone1"] == (41.0, 29.0, 5.0)


# B: bayat konum denetimi (ölü komşu sayılmaz)
def test_bayat_komsu_atlanir(node):
    """Konumu _STALE_LIMIT_S'ten eski komşu ölü sayılır: yakın ama bayat
    drone2 sayılmazsa, gönderenin tek canlı komşusu uzak drone3 kalır ->
    gönderen izole -> düşer. (Bayat atlanmasaydı drone2 yakın olduğu için
    geçerdi.)"""
    _reset(node)
    now = node.get_clock().now().nanoseconds / 1e9
    node.positions["drone2"] = _YAKIN
    node._pos_stamp["drone2"] = now - 20.0  # 20 s eski -> bayat (>12 s)
    node.positions["drone3"] = _UZAK
    assert node._broadcast_drop("drone1") is True


def test_taze_komsu_sayilir(node):
    """Aynı kurulum ama drone2 damgası TAZE -> yakın komşu geçerli, geçer."""
    _reset(node)
    now = node.get_clock().now().nanoseconds / 1e9
    node.positions["drone2"] = _YAKIN
    node._pos_stamp["drone2"] = now - 1.0  # 1 s -> taze
    node.positions["drone3"] = _UZAK
    assert node._broadcast_drop("drone1") is False


# C: kritik kanal artık kademeli mesafe zarına giriyor --
def test_kritik_election_mesafe_zarina_girer(node, monkeypatch):
    """C düzeltmesinin çekirdeği: election (kritik) artık should_drop_packet'i
    çağırıyor - eski ikili model bu olasılık eğrisine HİÇ girmezdi."""
    _reset(node)
    cagrildi = {}

    def sahte_drop(dist):
        cagrildi["dist"] = dist
        return True

    monkeypatch.setattr(node.rf_model, "should_drop_packet", sahte_drop)
    m = ElectionResult()
    m.new_leader_id = 1
    node._on_internal_election(m)
    assert "dist" in cagrildi          # mesafe zarı gerçekten atıldı
    assert len(node._pending) == 0     # zar düşür dedi -> düşürüldü


def test_kritik_event_mesafe_zarina_girer(node, monkeypatch):
    """events (kritik, source_agent_id>0) da artık mesafe zarına tabi."""
    _reset(node)
    cagrildi = {}

    def sahte_drop(dist):
        cagrildi["dist"] = dist
        return True

    monkeypatch.setattr(node.rf_model, "should_drop_packet", sahte_drop)
    m = SystemEvent()
    m.source_agent_id = 1
    node._on_internal_event(m)
    assert "dist" in cagrildi
    assert len(node._pending) == 0


# Lider takibi (drop'tan ÖNCE yakala)
def test_lider_heartbeat_ile_yakalanir(node):
    """Heartbeat işlenince güncel lider ID'si güncellenir."""
    _reset(node)
    m = LeaderHeartbeat()
    m.leader_id = 2
    node._on_internal_heartbeat(m)
    assert node._current_leader_id == 2


def test_lider_heartbeat_dusse_bile_yakalanir(node):
    """Lider heartbeat public'e dusse bile yakalanir."""
    _reset(node)
    node.positions["drone2"] = _UZAK  # lider drone2 komşularından izole
    m = LeaderHeartbeat()
    m.leader_id = 2
    node._on_internal_heartbeat(m)
    assert node._current_leader_id == 2   # düşse de lider yakalandı
    assert len(node._pending) == 0        # heartbeat gerçekten düştü


def test_lider_election_ile_yakalanir(node):
    """Election işlenince yeni lider ID'si güncellenir."""
    _reset(node)
    m = ElectionResult()
    m.new_leader_id = 3
    node._on_internal_election(m)
    assert node._current_leader_id == 3


# Formasyon/görev fazı: liderden çıkar -> mesafe kaybı ---
def test_formation_lider_yakinken_iletilir(node):
    _reset(node)
    node._current_leader_id = 1
    node._on_internal_formation(FormationCommand())
    assert len(node._pending) == 1


def test_formation_lider_izole_dusurulur(node):
    """Lider izole ise formasyon duser."""
    _reset(node)
    node._current_leader_id = 1
    node.positions["drone1"] = _UZAK  # lider komşularından ~111 km
    node._on_internal_formation(FormationCommand())
    assert len(node._pending) == 0


def test_formation_lider_bilinmiyorsa_iletilir(node):
    """Lider henuz bilinmiyorsa fail-open ile iletilir."""
    _reset(node)
    node._current_leader_id = None
    for a in node.agent_ids:
        node.positions[a] = _UZAK
    node._on_internal_formation(FormationCommand())
    assert len(node._pending) == 1


def test_formation_mesafe_zarina_girer(node, monkeypatch):
    """Formasyon artık should_drop_packet'e (liderin konumuyla) giriyor."""
    _reset(node)
    node._current_leader_id = 1
    cagrildi = {}

    def sahte_drop(dist):
        cagrildi["dist"] = dist
        return True

    monkeypatch.setattr(node.rf_model, "should_drop_packet", sahte_drop)
    node._on_internal_formation(FormationCommand())
    assert "dist" in cagrildi
    assert len(node._pending) == 0


def test_mission_state_lider_izole_dusurulur(node):
    _reset(node)
    node._current_leader_id = 1
    node.positions["drone1"] = _UZAK
    node._on_internal_mission_state(UInt8())
    assert len(node._pending) == 0


def test_mission_qr_step_lider_yakinken_iletilir(node):
    _reset(node)
    node._current_leader_id = 1
    node._on_internal_mission_qr_step(UInt8())
    assert len(node._pending) == 1


def test_next_target_lider_yakinken_iletilir(node):
    _reset(node)
    node._current_leader_id = 1
    node._on_internal_mission_next_target(MissionTarget())
    assert len(node._pending) == 1


def test_next_target_lider_izole_dusurulur(node):
    _reset(node)
    node._current_leader_id = 1
    node.positions["drone1"] = _UZAK
    node._on_internal_mission_next_target(MissionTarget())
    assert len(node._pending) == 0
