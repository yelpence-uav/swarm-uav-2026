# ElectionResult.msg
# Distributed leader election sonucu — Heartbeat Bully algoritması çıktısı.
#
# NEDEN AssignRole.srv YETERSİZ:
# ROS2 servis çağrısı senkron istek-cevap döngüsüdür. Lider düştüğünde
# WiFi üzerinden servis timeout'a uğrar (varsayılan 5s) → election bloklanır.
# Election milisaniyeler içinde tamamlanmalıdır → topic zorunludur.
#
# NOT: AssignRole.srv KALIR — sadece kullanım alanı ayrışır:
#   AssignRole.srv  → GCS kaynaklı manuel rol ataması / pre-flight konfigürasyon
#   ElectionResult  → consensus_fsm kaynaklı otomatik election sonucu
#
# Topic : /swarm/election/result
# QoS   : RELIABLE + TRANSIENT_LOCAL, depth=10
# Kim   : yeni lider olarak seçilen agent'ın consensus_fsm'i
# Ne zaman: election tamamlandığında (tek seferlik, her election için)
#
# STALE MESAJ KORUMASI:
# Alıcılar: AYNI (triggered_by_agent_id, incarnation) çifti içinde
# sequence_num gördükleri en yüksek değerden küçük/eşitse mesajı yok say.
# election_round mevcut round'dan küçükse mesajı yok say.
#
# incarnation NEDEN VAR (30 Temmuz, ölçülerek bulundu):
# sequence_num yayıncı düğümün ömrü boyunca monoton artar ama düğüm yeniden
# başlayınca 0'dan başlar. Alıcı max_seen_seq'i koruduğu için yeniden başlayan
# liderin BÜTÜN yeni seçim sonuçları sessizce düşerdi — log yok, uyarı yok.
# Aynı şey lider el değiştirdiğinde de olurdu: yeni lider seq=1'den başlar,
# alıcıların sayacı yüksek kalır.
# incarnation, yayıncının o açılışına özgü rastgele bir kimlik (0 = bilinmiyor,
# eski gönderici). Değiştiğini gören alıcı o kaynağın seq sayacını sıfırlar.
# Bu yüzden sayaç KAYNAK BAŞINA tutulmalıdır, global değil.

builtin_interfaces/Time stamp

uint32 sequence_num            # yayıncı ömrü boyunca monoton artar
uint16 incarnation             # yayıncının açılış kimliği; 0 = bilinmiyor

# Election tetikleyici sebebi
uint8 REASON_UNKNOWN=0
uint8 REASON_LEADER_TIMEOUT=1   # heartbeat 300ms gelmedi
uint8 REASON_LEADER_FAULT=2     # AgentStatus.state == STATE_FAILSAFE / STATE_LANDED
uint8 REASON_MANUAL=3           # GCS / operatör tetikledi

uint8 new_leader_id
uint8 election_round            # hangi election turu; her yeni election +1
uint8 triggered_by_agent_id     # election'ı başlatan agent; 0 = sistem/GCS
uint8 reason                    # REASON_* enum

# Hangi agent'lar bu sonucu onayladı (consensus doğrulama)
# Boş ise tek agent kaldı veya bölünmüş ağ — GCS uyarı göstermeli
uint8[] confirmed_by_agent_ids

string message                  # insan okunabilir açıklama (log/GCS için)
