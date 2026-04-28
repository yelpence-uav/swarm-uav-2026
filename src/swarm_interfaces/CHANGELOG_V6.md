# swarm_interfaces v6 değişiklikleri

Bu sürüm, v5 üzerine gelen görev akışı geri bildirimlerine göre hazırlanmıştır.

## Eklenen arayüzler

- `action/ExecuteManeuver.action`
  - QR veya joystick kaynaklı pitch/roll/yaw manevralarını `mission_fsm -> maneuver_executor -> AgentSetpoint` zincirine bağlar.
  - Feedback/result alanları sayesinde `mission_fsm` manevranın tamamlanmasını takip edebilir.

- `action/ManageSwarmMember.action`
  - QR kaynaklı ajan çıkarma/yeniden katma/standby replacement akışını uzun süreli action olarak takip eder.
  - detach, colored zone landing, disarm wait, rearm ve rejoin fazlarını feedback olarak verir.

- `srv/ManageSwarmMember.srv`
  - Hızlı başlatma/debug/GCS isteği için hafif servis arayüzüdür.
  - Uzun süreli tamamlanma takibi için `ManageSwarmMember.action` tercih edilmelidir.

## Güncellenen arayüzler

- `msg/SystemEvent.msg`
  - `EVENT_ROTATION_STARTED`, `EVENT_ROTATION_COMPLETED`
  - `EVENT_MANEUVER_STARTED`, `EVENT_MANEUVER_COMPLETED`, `EVENT_MANEUVER_FAILED`
  - `EVENT_MEMBER_DETACH_STARTED`, `EVENT_MEMBER_REJOIN_STARTED`, `EVENT_MEMBER_MANAGEMENT_FAILED`

## Güncellenen dosyalar

- `CMakeLists.txt`
  - Yeni action ve service dosyaları `rosidl_generate_interfaces()` listesine eklendi.
- `package.xml`
  - Sürüm `0.3.0` yapıldı.
- `INTERFACE_CONTRACT.md`
  - Paket sayısı v6 olarak güncellendi.
  - Topic/action/service tablosu güncellendi.
  - Manevra akışı, birey çıkarma/katma akışı ve `SWARM_ROTATING` state geçişi eklendi.

## V6.1 Patch

- `SwarmState.msg` event constants bloğu, `SystemEvent.msg` ile hizalandı.
- `EVENT_ROTATION_*`, `EVENT_MANEUVER_*` ve `EVENT_MEMBER_*` sabitleri `SwarmState.msg` içine de eklendi.
- Böylece `SwarmState.last_event_type` alanı 30-37 arası eventlerde cross-reference gerektirmeden okunabilir hale geldi.

---

## V6.2 Contract Patch

- Interface mesaj/action/srv sayısı değiştirilmedi.
- `INTERFACE_CONTRACT.md` topic/action tablosundaki fonksiyonel rol adları mevcut `src/` mimarisine sıkıştırıldı:
  - `maneuver_executor` → `swarm_core/formation_control/maneuver_executor_node.py`
  - `member_manager` → `swarm_missions/mission1_dynamic_swarm/member_manager_node.py`
  - `precision_landing` → `swarm_missions/mission1_dynamic_swarm/precision_landing_node.py`
  - `joystick_interpreter` → `swarm_state_machine/mode_manager/joystick_interpreter_node.py`
  - `inter_drone_comm` → `swarm_core/consensus/neighbor_monitor_node.py`
- Yeni ana klasör önerisi yapılmadı; mevcut mimariye sadık kalındı.


---

## V6.3 Interface Patch

- Yeni `.msg`, `.srv` veya `.action` dosyası eklenmedi.
- `FormationCommand.msg` içine `use_current_altitude` alanı geri eklendi.
  - QR yalnızca formasyon değiştiriyor ve irtifa komutu vermiyorsa mevcut sürü irtifası/NED Z korunur.
- `ExecuteFormation.action` goal kısmına `participating_agent_ids[]` alanı eklendi.
  - Formation action server detach/rejoin veya standby replacement sonrası hangi ajanları bekleyeceğini net bilir.
- `INTERFACE_CONTRACT.md` v6.3 olarak güncellendi ve bu iki alanın kullanım kuralları eklendi.
- `package.xml` sürümü `0.3.2` yapıldı.

---

## V6.4 Safety & Quality Patch

- Yeni `.msg`, `.srv` veya `.action` dosyası eklenmedi.

## Güncellenen arayüzler

- `msg/AgentStatus.msg`
  - `rc_link_ok`, `kill_switch_active`, `rc_signal_failsafe_active` eklendi
  - `oscillation_detected`, `unstable_flight` eklendi

- `msg/SystemEvent.msg`
  - `EVENT_OSCILLATION_DETECTED=54` – `EVENT_KILL_SWITCH_ACTIVATED=59` arası 6 yeni event eklendi

- `msg/SwarmState.msg`
  - Yukarıdaki 6 event mirror edildi

- `msg/LeaderHeartbeat.msg`
  - Bully variant yorumu düzeltildi: en küçük active agent_id lider olur; STANDBY/DETACHED election dışı

## Güncellenen dosyalar

- `srv/AssignRole.srv`
  - Topic adı notu eklendi: `/swarm/agent/{id}/assign_role`
- `INTERFACE_CONTRACT.md`
  - `AssignRole.srv` topic adresi düzeltildi: `/swarm/assign_role` → `/swarm/agent/{id}/assign_role`
  - RC/kill switch ve uçuş kalitesi alanları belgelendi (bölüm 3.2)
  - Preflight checklist güncellendi
  - EVENT enum tablosu ve kurallar 25–31 güncellendi
- `package.xml`
  - Sürüm `0.4.0` yapıldı
