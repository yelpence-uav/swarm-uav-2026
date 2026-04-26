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
