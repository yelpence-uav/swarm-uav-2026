# WORKFLOW BULGULAR — G2 öncesi çok ajanlı kod denetimi

**Son güncelleme:** 20 Ağustos 2026, 17:40

> **DONMUŞ BELGE.** 19/20 Ağustos gecesi, G2 tekrar uçuşundan önce çalıştırılan
> çok ajanlı denetimin ham çıktısı (KARAR-02 `ultracode`). **Buraya yeni madde
> yazma** — gerçek iş maddeleri `YAPILACAKLAR.md`'ye süzülerek girer.
>
> ⚠️ **Denetim doğrulama aşamasında durduruldu** (token maliyeti). 42 bulgunun
> **yalnız 7'sinin** doğrulayıcı kararı tamamlandı. **Etiketsiz her bulgu bir
> İDDİADIR** — uygulanmadan önce koddan teyit edilmeli. Bu uyarı belge boyunca
> tekrarlanmıyor; etiket görmüyorsan doğrulanmamıştır.
>
> 🔴 **TEK NOKTA ARIZASI:** 16 bulgunun mekanizma metni burada **kesik**
> (`*(tam metin journal.jsonl)*`). O dosya yalnız **Berk'in Mac'inde**
> (`~/.claude/projects/-Users-berk-Desktop-yelpence-2026-saha/.../
> wf_635b637e-bd2/journal.jsonl`) — depoda yok, yedeği yok. O makine giderse
> 16 bulgunun gerekçesi kaybolur. **Berk: o journal'ı depoya al ya da tam
> metinleri buraya yapıştır.**

## Doğrulanmış sonuçlar — bunlara güvenilebilir

| Bulgu | Karar | Nerede |
|---|---|---|
| `heartbeat_timeout_ms` tamamen ölü — `own_airborne` hiç true olmuyor | ✅ **2/2 DOĞRULANDI** | `election.py:47` |
| Bayatlık yanlış akışı ölçüyor — POSE 10 Hz tazeliyor, sağlık 1 Hz | ✅ **2/2 DOĞRULANDI** | `consensus_context.py:93` |
| Lider yalpası — 10 Hz'de sürekli lider devrilmesi | ⚠️ **1/2 BÖLÜNDÜ** | `consensus_node.py:243` |
| *"Her GOTO SetMode(OFFBOARD) üretiyor, RC failsafe RTL'i geri alınıyor"* | ❌ **ÇÜRÜTÜLDÜ** | kapı `gorev_kanit_ucus.py:2177` |

> 🔵 **Çürütülen P0, denetimin neden karşıt doğrulamayla yapıldığının kanıtı.**
> İddia *"kodda 'PX4 şu an hangi modda' diye bakan hiçbir kapı yok"* diyordu.
> Doğrulayıcı tam o kapıyı satırıyla gösterdi: `gorev_kanit_ucus.py:2177-2186`
> her tikte `flight_mode`'u okuyor ve OFFBOARD değilse (RTL = 7 ≠ 4) görevi
> **kesiyor** — goto POST'u hiç atılmıyor. İkinci bağımsız kapı da var
> (`guvenlik_ihlali` → `failsafe_active`, `:2078`). Tek kanalda kalsaydı bu
> iddia "uçuş engeli" diye yazılacaktı.

⚠️ İki DOĞRULANMIŞ bulgu birbirini büyütüyor: lider kaybı 300 ms'de
farkedilmeli, ama `own_airborne` hiç true olmadığı için o yol ölü; yedek olan
3 sn'lik bayatlık da yanlış akışı ölçtüğü için tetiklenmiyor. **Sonuç: düşmüş
bir lider süresiz olarak sürünün lideri kalabilir.** `YAPILACAKLAR.md` P0.14.

## Denetimin bağlamı

Denetlenen yeni kod (19 Ağustos gecesi yazıldı, **hiç uçmadı**):
1. `esp32_bridge` guided ARM'da yerel `EVENT_MISSION_STARTED` üretiyor (uçak-içi köprü)
2. `agent_fsm`'e `kalkis_olayla` parametresi (sahada `false`)
3. `consensus_node` lider olduğu sürece kalp atışı yayınlıyor (`own_airborne` şartı kalktı)

Uçuş düzeni: 2 uçak (ajan 1 ve 3), kalkış/rota YKİ guided yolundan, `yer_testi`
bayrakları silinmiş, RC-kayıp failsafe'i (Ch3 üst-uç → RTL) iki uçakta da kurulu.

## Özet

| Önem | Adet | Not |
|------|------|-----|
| 🔴 P0 | 6 | 4 ayrı sorun (2'si iki avcı tarafından bağımsız bulundu) |
| 🟠 P1 | 20 | uçuşta risk / eksik emniyet katmanı |
| 🟡 P2 | 16 | sonra ele alınacak |
| **toplam** | **42** | 7'si doğrulandı ya da çürütüldü |

### 🔵 Doğrulamanın en önemli sonucu — bir P0 ÇÜRÜTÜLDÜ

*"Her GOTO çerçevesi `SetMode(OFFBOARD)` üretiyor, RC failsafe RTL'i 5 Hz'de geri
alınıyor"* iddiası **yanlış çıktı.** Doğrulayıcı, YKİ görev koşucusunda tam bu
senaryo için yazılmış kapıyı satırıyla gösterdi: `gorev_kanit_ucus.py:2177-2186`
her tikte `flight_mode`'u okuyor ve OFFBOARD değilse (RTL = 7 ≠ 4) görevi
**kesiyor** — yani goto POST'u hiç atılmıyor. İkinci bağımsız kapı da var
(`guvenlik_ihlali` → `failsafe_active`, `:2078`). **Sonuç: dün kurulan RC-kayıp
RTL'i görev sırasında geçersiz kılınmıyor.**

Bu, denetimin neden karşıt doğrulamayla yapıldığının kanıtı: tek kanalda kalsaydı
bu iddia "uçuş engeli" olarak yazılacaktı.

## 🔴 P0 — uçuş engeli iddiaları

#### land/rtl sonrasi kuyrukta kalan GOTO tekrarlari OFFBOARD'i geri acip inisi iptal ediyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:1204` · mercek: `rc-failsafe-ucus`  
_isle_goto ALINAN HER GOTO cercevesinde kosulsuz `_guided_string('offboard')` yayinliyor (esp32_bridge_node.py:1204) ve `_guided_hedef`i yeniden kuruyor (:1203). px4_bridge'de 'offboard' dali `_offboard_streaming=True` yapip `set_offboard_mode()` cagiriyor (px4_bridge.py:1349-1353 -> mavros_command_sender.py:208-233 SetMode servisi). Base tarafinda guided kuyrugu SADECE ayni tip+ayni hedef GOTO icin ayiklama yapiyor; TIP_KOMUT (land/rtl/disarm) bekleyen GOTO tekrarlarini TEMIZLEMIYOR (esp32_bridge_node.py:1689-1691). Zincir: RC 0.5 sn kesilir -> PX4 NAV_RCL_ACT=2 AUTO.RTL -> gorev kosucusu `flight_mode != 4` gorup iptal eder ve `indir()` cagirir (gorev_kanit_ucus.py:2810-2813) -> LAND cercevesi TIP_KOMUT kapisindan (~0.05 sn) once cikar, ucakta `_guided_hedef=None` + AUTO.LAND olur (esp32_bridge_node.py:1137-1139, px4_bridge.py:1329-1338). AMA iptal anindan onceki son GOTO kaydi kuyrukta hala kalan=4 ile duruyor ve TIP_GOTO kapisi 0.10 sn (esp32_bridge_node.py:158, _GUIDED_TEKRAR=4 :152); kopyalar LAND'den 0.25/0.50/0.75 sn SONRA havaya cikiyor. Ucaga ulasan ilk bayat GOTO `_guided_hedef`i yeniden kuruyor ve 'offboard' yolluyor -> AUTO.LAND iptal, ucak OFFBOARD'a doner. `_guided_hedef_tekrar` 10 Hz'de sonsuza kadar tazeledigi icin (esp32_bridge_node.py:1217-1219, timer :428) px4_bridge'in 0.5 sn bayatlama korumasi da hic tetiklenmez: ucak, RC yokken ve YKI kosucusu cikmisken bayat goto hedefinde suresiz asili kalir.

#### Her GOTO cercevesi SetMode(OFFBOARD) uretiyor: dun kurulan RC failsafe RTL'i 5 Hz'de geri aliniyor

`src/swarm_control/swarm_control/px4_interface/px4_bridge.py:1349` · mercek: `rc-failsafe-ucus`  
**❌ ÇÜRÜTÜLDÜ**

Gorev kosucusu her 0.2 sn'de her ucaga goto POST ediyor (gorev_kanit_ucus.py:2235, SETPOINT_ADIM_S=0.2 :595). Base her goto'yu 4 kopya kuyruga koyuyor (esp32_bridge_node.py:152) ve TIP_GOTO kapisi 0.10 sn (:158) -> iki ucak paylasinca ucak basina ~5 GOTO cercevesi/sn havaya cikiyor. Ucakta her cerceve `_guided_string('offboard')` (esp32_bridge_node.py:1204) -> px4_bridge `set_offboard_mode()` (px4_bridge.py:1349-1353) -> MAVLink DO_SET_MODE. Yani ucus BOYUNCA saniyede ~3-5 kez OFFBOARD mod komutu gidiyor. RC 0.5 sn kesilip PX4 RTL'e gectiginde (COM_RC_LOSS_T=0.5, NAV_RCL_ACT=2, COM_RCL_EXCEPT=0) en gec 0.2-0.3 sn icinde bir sonraki GOTO ucagi OFFBOARD'a geri cekiyor; RC hala yokken gorev devam ediyor. Kodda 'PX4 su an hangi modda' diye bakan hicbir kapi yok: px4_bridge'in `_offboard_streaming` bayragi PX4 OFFBOARD'dan CIKINCA hic dusmuyor, ve mod yeniden talebi yalniz `_sitl_mode` dalinda hiz sinirli (px4_bridge.py:667-686) — gercek donanimda sinirsiz. Sonuc: dun HAVADA dogrulanan RC failsafe'i guided komut yolu sessizce etkisizlestiriyor.

#### Lider bayragi geri alinmiyor: IDLE/disarm ucaktan sonsuz kalp atisi + takipciyi olu lidere geri ceken zipla­ma dongusu

`src/swarm_core/swarm_core/consensus/consensus_node.py:183` · mercek: `kalp-atisi-degisikligi`  
c3068c8 ile 'own_airborne' kapisi kalkti; yayin artik SADECE ctx.is_leader'a bagli (183-184). Fakat ctx.is_leader yalniz _set_leader(192)/_adopt_leader(253)/_on_election(292) icinde yazilir ve bunlarin hicbiri 'kendi uygunlugumu kaybettim' halini KENDI BASINA yakalamaz: election.py:98-99 `candidate = min(effective) if effective else 0; if candidate == 0: return None` — komsu kumesi bossa hicbir degisiklik uretilmez. Yarin somut zincir: baslat.sh:363 kalkis_olayla=false -> agent_fsm ARMED'da kalir (agent_transitions.py:146 _from_armed, TAKEOFF kapisi kapali). Guided 'land' sonrasi PX4 disarm eder -> `if not ctx.armed or not ctx.healthy: return AgentState.IDLE` (agent_transitions.py:155) -> ucak IDLE. IDLE, ELIGIBLE_STATES'te YOK (consensus_states.py:7-12). Ucus sonunda IKI ucak da IDLE oldugunda effective=bos kalir, decide_change None doner ve lider ucakta ctx.is_leader=True KALIR: disarm olmus, yerde duran ylp00 mesh'e 10 Hz LeaderHeartbeat(leader_id=1) basmaya SONSUZA KADAR devam eder (eski kodda IDLE havada sayilmadigi icin yayin aninda kesiliyordu). Ikinci ucus icin konteyner yeniden baslatilmadan ylp02 once ARM edilirse: ylp02'de elig={3}, ctx.leader_id=1, `ctx.leader_id not in effective` (election.py:112) -> kendini lider secer; <=100 ms sonra ylp00'in hayalet kalp atisi gelir, consensus_node.py:243 `msg.leader_id < ctx.leader_id` (1<3) -> _adopt_leader(1) ile liderligi disarm ucaga GERI VERIR; bir sonraki tick tekrar kendini secer. Kalici 5-10 Hz zipla­ma: _publish_election_result 5 Hz mesh'e ELECTION basar (firmware kapisi 50 ms, hepsi gecer), _pub_leader_changed 5 Hz RELIABLE olay yayar, _apply_role 10 Hz AssignRole cagirir ve ctx.election_round=(x+1)%256 ~51 sn'de uint8 tavanini sarar (sarma sonrasi _on_election'daki `msg.election_round < ctx.election_round` filtresi mesru secimleri dusurur). Bunlarin hepsi, pervaneler donerken, kalkis/goto guided komutlariyla AYNI ESP-NOW kanalinda olur. Cozum: 184'teki kapiyi `if ctx.is_leader and self._agent_id in elig:` yapmak (1 satir, geri alinabilir).

#### kalkis_olayla varsayilani True — guided ARM artik KOMUTSUZ 10 m kalkis tetikleyebilir ve operatorun 20 m takeoff'unu sessizce yutar

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:88` · mercek: `komut-etkilesimi`  
agent_fsm_node.py:88 `declare_parameter('kalkis_olayla', True)`. Bu varsayilan dun geceye kadar ATILDI cunku ucakta EVENT_MISSION_STARTED'i uretenr yoktu (G2'de olculdu: 638 sn IDLE). b469871 ile esp32_bridge_node.py:1120 guided ARM'da olayi KOSULSUZ uretiyor — yani tehlikeli varsayilan artik CANLI. Zincir: guided ARM -> olay -> agent_fsm_node.py:345 mission_start_sequence_active=True -> agent_transitions.py:160-163 `_from_armed`: armed+offboard_active+2.0 sn -> TAKEOFF -> agent_fsm_node.py:299-300 `cmd=f'takeoff:{self._target_altitude_m}'`. target_altitude_m baslat.sh'te HIC gecilmiyor (baslat.sh:360-364), yani agent_fsm_node.py:77 varsayilani 10.0. Iki sonuc: (a) kosucu drone3'u armlamayi beklerken drone1 kendiliginden 10 m'ye kalkar (arm teyidi dongusu gorev_kanit_ucus.py:2525-2537 uc-bes saniye surer, FSM 2 sn'de tetikler); (b) FSM'in 'takeoff:10.0'i once varirsa px4_bridge.py:1309-1311 tekrar-kapisi ('_target_altitude_ned is not None -> yok say') operatorun gercek `takeoff:20.0` komutunu SESSIZCE atar ve G2 (gorev_kanit_ucus.py:219, G2_IRTIFA_M=20.0) 10 m'de ucar. Sahada baslat.sh `${SURU_KALKIS_OLAYLA:-false}` geciyor, ama run_drone.sh bu env'i konteynere hic gecmiyor ve kod ile baslat.sh AYRI rsync ediliyor (dagit.sh:122 paketler, :136 baslat.sh) — bir ucakta yeni kod + eski baslat.sh kalirsa varsayilan True olur. Cozum: varsayilani False yap (1 satir) + ucus oncesi iki ucakta `ros2 param get /agent_fsm_node kalkis_olayla` dogrula.

#### LAND/iptal komutundan SONRA gelen bayat GOTO kopyalari 'offboard' yollayip inisi iptal ediyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:1204` · mercek: `komut-etkilesimi`  
_isle_goto her GOTO cercevesinde KOSULSUZ `self._guided_string('offboard')` yayinliyor (esp32_bridge_node.py:1204) ve px4_bridge.py:1349-1353 'offboard' dalinda kosulsuz `_offboard_streaming=True` + `set_offboard_mode()` yapiyor. Baz istasyonundaki guided kuyrugu TIP_GOTO ile TIP_KOMUT'u AYRI kapilardan bosaltiyor (esp32_bridge_node.py:1156-1159: GOTO 0.10 s, KOMUT 0.30 s; bosaltma 1702-1730) ve her cerceve 4 KOPYA. gorev_kanit_ucus.py:2235 `git()` dongude her 0.2 sn'de bir yeni GOTO kuyruga koyuyor; iptal/varis olunca gorev_kanit_ucus.py:2810-2814 (veya 2168-2185 guvenlik ihlali) hemen `indir()` -> gorev_kanit_ucus.py:2300 `/api/guided/{did}/land` cagiriyor. LAND ilk kopyasi ~0.05 sn'de cikar (KOMUT kapisi bostur), ama kuyrukta 3-4 GOTO kopyasi kalir ve sonraki ~0.75 sn boyunca ucaga varmaya DEVAM eder. Ucakta sira: land -> AUTO.LAND, sonra bayat goto -> 'offboard' -> PX4 AUTO.LAND'dan cikip OFFBOARD'a doner ve px4_bridge yurutucusu ucagi eski hedefe (G2'de z=-20.0 mutlak, `_takeoff_baslangic_z` land'de None'landigi icin px4_bridge.py:1332) geri surer. En kotu hali kill-switch iptalinde: operator kesmek istiyor, boru hatti ucagi hedefe geri cekiyor. Cozum: LAND/RTL/DISARM islenirken o hedefe ait bekleyen TIP_GOTO kayitlarini kuyruktan sil (_guided_gonder icindeki TIP_GOTO ayiklamasinin aynisi, ~4 satir) VE px4_bridge'de land sonrasi N saniye 'offboard'i yok sayan bir mandal ekle.

#### Kalkis kapisi yalniz baslat.sh argumanina asili — kodun kendi varsayilani TEHLIKELI olan (kalkis_olayla=True)

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:88` · mercek: `kopru-kacaklari`  
`self.declare_parameter('kalkis_olayla', True)` — guvenli deger YALNIZ deploy/rpi/baslat.sh:363'ten (`-p kalkis_olayla:=${SURU_KALKIS_OLAYLA:-false}`) geliyor. Parametre herhangi bir sebeple ulasmazsa (ucaktaki /ws/baslat.sh eski kalmis, dagitimdan sonra `docker restart` yapilmamis, agent_fsm elle ya da bir teshis betiginden baslatilmis) varsayilan True devreye girer ve zincir sudur: esp32_bridge guided ARM'da olay uretir (esp32_bridge_node.py:1120) -> _on_event `kalkis_izni = (not yer_testi) and kalkis_olayla` = True (agent_fsm_node.py:343-346) -> `mission_start_sequence_active=True` -> _from_armed offboard_active + 2.0 sn sonra TAKEOFF dondurur (agent_transitions.py:160-163) -> _dispatch_px4_command `takeoff:10.0` yayinlar (agent_fsm_node.py:299-300; `target_altitude_m` varsayilani 10.0, agent_fsm_node.py:77 ve baslat.sh bu parametreyi HIC gecmiyor). px4_bridge ilk gelen takeoff'u capalar ve sonraki guided `takeoff:20.0`'i `_target_altitude_ned is not None` diye YOK SAYAR (px4_bridge.py:1309-1311) — ucak G2'nin 20 m'sine degil 10 m'ye cikar ve kalkis otoritesi guided yolda degil FSM'de olur. Kritik olan: dunku P0.11 yer testinde bu kapi ayrica `yer_testi=true` ile de kapaliydi (DURUM.md: bayrak geri konmustu); yarin bayrak silindi, yani `kalkis_olayla` TEK BASINA ilk kez havada guvenilecek ve hic dogrulanmadi. Ucus oncesi tek satirlik kanit: iki ucakta da `ros2 param get /agent_fsm_node kalkis_olayla` -> False olmali; ayrica fsm.log'da 'gecis modu ... (kalkis_olayla=false)' satiri gorulmeli.

## 🟠 P1 — uçuşta risk

#### failsafe_active mesh'te TASINMIYOR — YKI'nin FAILSAFE emniyet kesicisi olu

`src/gcs/gorev_kanit_ucus.py:2085` · mercek: `rc-failsafe-ucus`  
`guvenlik_ihlali()` ucusu derhal kesmek icin `d.get('failsafe_active')`e bakiyor (gorev_kanit_ucus.py:2085). Bu alan backend'e `/swarm/public/drone{N}/status`tan geliyor (ros_bridge.py:254), o konuyu da baz istasyonundaki esp32_bridge dolduruyor. `_isle_durum` (esp32_bridge_node.py:929-992) 15+ alan yaziyor ama `status.failsafe_active` HIC yazilmiyor — dosyada `status.failsafe_active` sifir kez geciyor. AgentStatus varsayilani False, yani YKI bu bayragi HER ZAMAN False goruyor. Ucakta deger dogru uretiliyor (mavros_telemetry_mapper.py:112-116, MAV_STATE CRITICAL/EMERGENCY -> True) ve PX4 RC-kayip failsafe'inde MAV_STATE CRITICAL olur; yani bilgi uretiliyor ama mesh'te dusuyor. Geriye kalan tek tespit yolu `flight_mode != 4` (gorev_kanit_ucus.py:2182-2185), o da 1 Hz DURUM paketiyle (esp32_bridge_node.py:348 _durum_periyot_s=1.0) ve broadcast'te ~%30 kayipla geliyor -> iptal gecikmesi 1-3 sn. O 1-3 sn boyunca 5-15 goto (yani 5-15 SetMode OFFBOARD) gonderilmeye devam eder.

#### rc_signal_failsafe_active'i hicbir dugum uretmiyor: iki ayri emniyet kontrolu olu kod

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_health_monitor.py:315` · mercek: `rc-failsafe-ucus`  
`_check_rc_safety` havadayken `ctx.rc_signal_failsafe_active` ile kritik ariza ilan ediyor (agent_health_monitor.py:315-320) ve YKI on kontrolu de ayni alana bakiyor (gorev_kanit_ucus.py:2341). Alanin tek yazicisi agent_fsm'in telemetriden kopyalamasi (agent_fsm_node.py:536) ve telemetriyi ureten px4_bridge/mavros_telemetry_mapper icinde `rc_signal_failsafe` dizesi SIFIR kez geciyor (iki dosyada da grep 0). Yani deger dogusundan itibaren hep False; iki kontrol de hicbir zaman tetiklenmez. Bu, docs/TUZAKLAR.md 3.9'un onerdigi ('on kontrol PX4'un kendi hukmune baglanmali: ready_to_arm, kill_switch_active, rc_signal_failsafe_active, failsafe_active') cozumun iki ayagini bosa cikariyor — rc_signal_failsafe_active hic uretilmiyor, failsafe_active ise mesh'te dusuyor (bkz. diger bulgu).

#### kalkis_olayla=false yuzunden FSM ucus boyunca ARMED'da kaliyor — butun 'havada' emniyet denetimleri kapali

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_health_monitor.py:31` · mercek: `rc-failsafe-ucus`  
Sahada baslat.sh `kalkis_olayla:=false` geciyor (deploy/rpi/baslat.sh:363) -> agent_fsm_node.py:343 `kalkis_izni=False` -> ARMED->TAKEOFF kapisi (agent_transitions.py:160-163) hic acilmiyor, ajan 20 m'de ucarken state=ARMED kaliyor. `_AIRBORNE` kumesinde ARMED YOK (agent_health_monitor.py:31-40). Sonuc, tum ucus boyunca su denetimler KAPALI: RC link kaybi kritik degil sadece uyari (:300-313), EKF arizasi denetlenmiyor (:202), OFFBOARD kaybi 5 sn timeout'u denetlenmiyor (:209-217), 30 m irtifa tavani denetlenmiyor (:439-441), jeofen denetlenmiyor (:338). Ayrica consensus_node.py:161 `own_airborne = own.state in AIRBORNE_STATES` hep False oluyor; bu yuzden election.py:47'deki 'lider kalp atisi zaman asimi -> lideri kumeden cikar' dali HIC calismiyor. Yani lider RC failsafe'e girip kalp atisini kesse bile takipci bunu heartbeat uzerinden goremez; yalniz 1 Hz'lik DURUM paketine kalir.

#### Havada kill switch: FSM bunu 'yerde, disarm' uyarisi sayiyor, mesh'e IDLE gonderiyor ve kendiliginden yeniden arm yolu aciliyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_health_monitor.py:289` · mercek: `rc-failsafe-ucus`  
Pilot CH5>1500 yapinca px4_bridge `kill_switch_active=True` uretiyor (mavros_telemetry_mapper.py:304-306) ve PX4 disarm ettigi icin ayni telemetride `armed=False` geliyor (:104). `_check_rc_safety` kritik-ariza kapisi `if ctx.state in _AIRBORNE or ctx.armed:` (agent_health_monitor.py:289) — state ARMED (onceki bulgu: _AIRBORNE'da degil) ve armed artik False oldugundan kosul FALSE olup :295-298'deki 'Kill switch aktif (yerde, disarm)' UYARI dalina duşuyor. FAILSAFE'e gecis yok. Ardindan agent_transitions.py:158-159 `_from_armed` -> IDLE. Mesh'e `_STATE_DURUM_MAP[STATE_IDLE]=_DURUM_BOSTA` gidiyor (esp32_bridge_node.py:200): komsu ve YKI, motoru havada kesilmis ucagi 'BOSTA' goruyor. Ikinci etki: IDLE'a dusen ajan yeni bir EVENT_MISSION_STARTED'a acik hale geliyor; esp32_bridge her guided ARM cercevesinde (4 kopya, ~2 sn'ye yayili) bu olayi uretiyor (esp32_bridge_node.py:1120) -> pending_state=ARMING; kill birakilmissa preflight yalniz o anki kill'e baktigi icin gecer (preflight_checker.py:17) -> FSM 'arm' yollar (agent_fsm_node.py:295-296) -> px4_bridge disarm oldugu icin kabul eder (px4_bridge.py:1245-1255) ve yeniden armlar. 18 Agustos'ta olculen 'disarm kavgasi' bu zincir; kodda hala duruyor.

#### rc_link_ok / kill_switch_active icin yas (staleness) denetimi yok — RCIn susarsa son degerde donuyor

`src/swarm_control/swarm_control/px4_interface/mavros_telemetry_mapper.py:298` · mercek: `rc-failsafe-ucus`  
`map_rc_in` yalnizca RCIn mesaji GELDIGINDE yaziyor (mavros_telemetry_mapper.py:298-310) ve tek cagirani `_on_mav_rc` (px4_bridge.py:569-585). Hicbir yerde 'son RCIn ne zaman geldi' tutulmuyor. `/drone_N/mavros/rc/in` akisi durursa (FCU RC_CHANNELS yayinini kesince) hem `rc_link_ok` hem `kill_switch_active` SON degerinde donuyor: operator kill'e bassa bile mesh'e ve YKI'ye False gider, `guvenlik_ihlali`nin kill kontrolu (gorev_kanit_ucus.py:2083) tetiklenmez ve agent_fsm `_check_rc_safety` (agent_health_monitor.py:277) hic gormez. NOT (dunku 'false-lost' anomalisi icin): kod tarafinda `rc_link_ok`u False'a kilitleyebilecek bir yol YOK — :299 `len(kanallar) > 0` yalniz o mesaj icin hukum verir, dolu gelen bir sonraki mesaj aninda duzeltir. Yani 'kumanda acikken RC biti kayipta takili' anomalisinin sebebi bu kodda degil; PX4/alici tarafinda (sys_status RC_RECEIVER biti, manual_control kaynak secimi) aranmali. Kodun eksigi yon degil, YAS denetimi.

#### _adopt_leader: dusuk ID'li kalp atisini uygunluk ve secim-turu denetimi olmadan kabul ediyor

`src/swarm_core/swarm_core/consensus/consensus_node.py:243` · mercek: `kalp-atisi-degisikligi`  
`elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id: self._adopt_leader(...)` — _adopt_leader (246-261) gelen leader_id'nin YEREL GORUSTE uygun olup olmadigini (election.is_eligible) hic sormuyor, msg.election_round'u da yalniz `max()` ile yukari cekiyor, ESKI turu reddetmiyor. Yani bu dugum, ayni tick'te 'lider arizali' diye disladigi (election.py:112-113 REASON_LEADER_FAULT) ucagi, o ucagin bir sonraki kalp atisiyla geri kabul eder. Eski kodda bu tehlikeli degildi cunku uygunlugunu yitiren bir lider (FAILSAFE/RETURN_HOME/LANDING/LANDED/IDLE) AIRBORNE_STATES disinda oldugu icin (consensus_states.py:15-19) hic kalp atisi yayinlamiyordu — yani susma, dogru sinyaldi. Yayin kapisi kalkinca bu susma garantisi de kalkti ve BULGU-1'deki dongunun geri-besleme kolu tam burasi oldu. Cozum: adopt etmeden once `election.is_eligible(ctx.agents.get(msg.leader_id), now, ctx.stale_s, ctx.battery_min_v)` denetimi.

#### Asimetri: yayin own_airborne'dan kurtuldu ama 300 ms lider-kaybi zaman asimi hala ona bagli — yarin tamamen olu kod

`src/swarm_core/swarm_core/consensus/election.py:47` · mercek: `kalp-atisi-degisikligi`  
effective_set'te kalan tek own_airborne kullanimi: `if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:`. Yarinki yapilandirmada own_airborne HIC True olmuyor: baslat.sh:363 `-p kalkis_olayla:=false` -> agent_fsm_node.py:343 `kalkis_izni = (not yer_testi) and self._kalkis_olayla` = False -> mission_start_sequence_active=False -> agent_transitions.py:161 ARMED->TAKEOFF kapisi acilmaz -> ajan tum ucus boyunca ARMED'da kalir. consensus_node.py:161 `own_airborne = own.state in AIRBORNE_STATES` ve AIRBORNE_STATES={TAKEOFF,IN_SWARM,EXECUTING_TASK} (consensus_states.py:15-19) -> ARMED yok -> False. Sonuc: ctx.last_hb_time ve hb_timeout_s (heartbeat_timeout_ms=300) hicbir kararda KULLANILMIYOR. Yarin 10 Hz kalp atisi uretilecek, kayda girecek, 'calisiyor' gorunecek — ama onun var olma sebebi olan lider-kaybi tespitinin tek tuketicisi devre disi. Lider kaybi ancak agent_stale_timeout_s=3.0 sn'lik durum bayatlamasiyla, yani tasarim hedefinin 10 KATI yavaslikla farkedilir. G2'nin olcmek istedigi seyin yanlis 'gecti' vermesi riski.

#### Mesh durum eslemesi ARMED'i TAKEOFF yapiyor: yerdeki ucak komsuya 'havada' gorunuyor; leader_airborne ve swarm_fsm yanlis veriyle karar veriyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:202` · mercek: `kalp-atisi-degisikligi`  
Gidis yonu `AgentStatus.STATE_ARMED: _DURUM_KALKIS` (202), donus yonu `_DURUM_KALKIS: AgentStatus.STATE_TAKEOFF` (182). Yani mesh'ten gelen her ARMED komsu yerelde STATE_TAKEOFF olarak kaydedilir. Iki dogrudan sonucu var: (1) election.py:49-51 `leader_airborne = lrec.state in AIRBORNE_STATES` — yerde ARM'li bir lider 'havada' sayilir; kalkis_olayla=true'ya gecildigi anda (ADIM 3) gozlemci havalanir havalanmaz, YERDE duran lider 300 ms'lik hb bosluguyla (ESP-NOW broadcast'te 3 ardisik kayip) effective'den atilir ve gereksiz lider degisimi uretilir. (2) Yarin aktif olan zincir: yeni kopru guided ARM'da EVENT_MISSION_STARTED uretiyor (esp32_bridge_node.py:1151-1172, /swarm/internal/events/system) -> ic_dis_kopru.py:105 events/system'i /public'e tasiyor -> swarm_fsm_node.py:585 `ctx.mission_active = True` -> swarm_transitions.py:61-65 `count_agents_in_state(AgentState.TAKEOFF) > 0` komsunun sahte TAKEOFF'u yuzunden dogrulanir -> swarm_fsm IKI UCAK DA YERDEYKEN IDLE->FORMING'e gecer ve SwarmState'i oyle yayinlar. mission1/mode_manager kapali oldugu icin bugun eyleme donusmuyor, ama YKI'de ve kayitta yanlis suru durumu gorunur ve ADIM 3/6 acildiginda dogrudan aktuator yoluna baglanir.

#### Lider yalpası: kalp atışı 'benim' der, uygunluk kapısı 'değil' der → 10 Hz'de sürekli lider devrilmesi

`src/swarm_core/swarm_core/consensus/consensus_node.py:243` · mercek: `consensus-secim`  
**⚠️ BÖLÜNDÜ — 1/2 onay**

Girdi: ylp02 (agent 3) ylp00'dan (agent 1) ÖNCE arm edilir — ya da uçuş sırasında liderlik el değiştirir. (1) agent 3 tek uygun ajan olduğu için election.py:98-108 ile kendini lider seçer, consensus_node.py:183-184 gereği her tick (10 Hz) kalp atışı yayınlar. (2) agent 1 arm olur; kendi kaydını /swarm/internal/... üzerinden 10 Hz görür, effective={1,3} olur ve election.py:114 `candidate == ctx.agent_id and candidate < ctx.leader_id` ile liderliği devralıp leader_id=1 kalp atışı yayınlamaya başlar. (3) agent 3 bu kalp atışını alır: consensus_node.py:243 `elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id` → _adopt_leader(1) KOŞULSUZ çalışır; iddia sahibinin uygunluğu HİÇ kontrol edilmez. (4) Ama agent 3'ün agent 1 için tuttuğu AgentStatus hâlâ IDLE'dır: komşunun state/healthy/estimator_ok alanları yalnız TIP_DURUM ile taşınır ve o 1 Hz'dir (esp32_bridge_node.py:348 `_durum_periyot_s = 1.0`, gönderim 1516), tekrarı da yoktur. (5) Bir sonraki tick'te (100 ms) election.py:112 `ctx.leader_id not in effective` → agent 3 REASON_LEADER_FAULT ile kendini yeniden seçer, ElectionResult + kalp atışı yayınlar. (6) 100 ms sonra agent 1'in kalp atışı yine gelir → (3)'e döner. Sonuç: agent 1'in ARMED DURUM paketi ulaşana kadar (≥1 sn; paket kaybında her kayıp +1 sn) saniyede ~10 lider değişimi. Her çevrimde election_round +1 (satır 190), mesh'e TIP_ELECTION, /swarm/internal/events/system'e EVENT_LEADER_CHANGED, agent_fsm'e AssignRole LEADER↔FOLLOWER (agent_fsm_node.py:511 bunu kısıtsız loglar). Bu yol 19 Ağustos'ta c3068c8 ile AÇILDI: kalp atışı önceden `ctx.is_leader and own_airborne` şartına bağlıydı, yani yerdeki/ARMED lider hiç kalp atışı yayınlamıyordu ve adım (3) hiç oluşmuyordu. Kod hiç uçmadı. Kalıcı hâli de var: agent 1'in estimator_ok'u düşerse (election.py:26-27) agent 3 onu HİÇ uygun görmez ve yalpa uçuş boyunca sürer.

#### heartbeat_timeout_ms bu uçuşta tamamen ölü — own_airborne hiçbir zaman true olmayacak

`src/swarm_core/swarm_core/consensus/election.py:47` · mercek: `consensus-secim`  
**✅ DOĞRULANDI — 2/2 bağımsız doğrulayıcı**

election.py:47 `if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:` — lider kalp atışı zaman aşımı (300 ms) yolu tamamen `own_airborne` şartına bağlı. consensus_node.py:161 bunu `own.state in AIRBORNE_STATES` ile hesaplıyor ve consensus_states.py:15-19 AIRBORNE_STATES = {TAKEOFF, IN_SWARM, EXECUTING_TASK}. Yarınki yapılandırmada baslat.sh:363 `kalkis_olayla=false` geçiyor; agent_fsm_node.py:343-345 `mission_start_sequence_active`'i False bırakıyor; agent_transitions.py:160-163 ARMED→TAKEOFF geçişini tam bu bayrağa bağlıyor. Kalkış guided yoldan yapıldığı için FSM uçuş boyunca ARMED'da kalır → own_airborne HEP False → effective_set gelen kümeyi olduğu gibi döndürür → 300 ms'lik lider kaybı tespiti hiç çalışmaz. Somut sonuç: liderin consensus_node'u çöker ama agent_fsm + esp32_bridge çalışmaya devam ederse (status akmaya devam eder, ajan hâlâ 'uygun' görünür) takipçi lider kaybını ASLA fark etmez — sürünün lideri yoktur ama kimse seçim yapmaz. Tek yedek yol election.py:19'daki 3 sn'lik bayatlık ve o da bir sonraki bulgu yüzünden tetiklenemiyor.

#### Bayatlık yanlış akışı ölçüyor: POSE 10 Hz kaydı tazeliyor, sağlık/durum yalnız 1 Hz DURUM'dan geliyor

`src/swarm_core/swarm_core/consensus/consensus_context.py:93` · mercek: `consensus-secim`  
**✅ DOĞRULANDI — 2/2 bağımsız doğrulayıcı**

consensus_context.py:88-93 `update_status` her AgentStatus mesajında hem state/healthy/estimator_ok'u hem `last_update`'i yazıyor. Komşu tarafında bu mesajın iki ayrı mesh kaynağı var: esp32_bridge_node.py:876 TIP_POSE her geldiğinde (10 Hz, `_pose_periyot_s = 0.1`, satır 345) ÖNBELLEKTEKİ TÜM AgentStatus'u yeniden yayınlıyor — ama POSE yalnız konum/hız taşıyor. state/healthy/estimator_ok yalnız TIP_DURUM ile güncelleniyor (esp32_bridge_node.py:928-978, 1 Hz, satır 348) ve o paketin tekrarı yok (guided komutlar tam bu kayıp yüzünden 4 kopya gönderiliyor). Dolayısıyla election.py:19'daki `rec.is_stale(now, 3.0)` yalnız POSE akışının tazeliğini ölçüyor, koruduğu alanlarınkini değil. Girdi: liderin DURUM paketleri mesh'te düşer, POSE geçmeye devam eder. Sonuç: lider FAILSAFE'e düşse, disarm olsa, IDLE'a dönse bile takipçiler onu süresiz 'taze + ARMED + healthy' görür; election.py:112'deki lider-arıza yolu hiç tetiklenmez ve düşmüş lider sürünün lideri olarak kalır. Aynı gecikme ters yönde de çalışıyor ve 1. bulgudaki yalpanın doğrudan sebebi.

#### bootstrap_grace_s saati sıfırlanmıyor — 1.5 sn'lik bekleme daha başlamadan bitmiş olabilir

`src/swarm_core/swarm_core/consensus/consensus_node.py:166` · mercek: `consensus-secim`  
consensus_node.py:166-167 `bootstrap_since`'i `effective` ilk kez boş olmadığında kuruyor. Sıfırlayan TEK yer consensus_node.py:194 (_set_leader). Yani lider seçilemediği sürece saat bir daha sıfırlanmaz; effective yeniden boşalsa bile eski damga durur. agent_count=3 ama iki uçak uçtuğu için election.py:102 `full_field = len(effective) >= ctx.agent_count` HİÇ sağlanamaz — leader_id==0'dan çıkışın tek yolu grace saatidir. Girdi: uçuş öncesi bir arm denemesi başarısız olur (agent_transitions.py:158 `not ctx.armed or not ctx.healthy` → ARMED'dan IDLE'a döner) veya ajan yer testinde bir süre ARMED kalır. O anda bootstrap_since kurulur ve dakikalarca öyle kalır. Gerçek kalkışta effective ilk kez dolduğu tick'te election.py:104-106 `grace_done` ANINDA true olur ve ajan tek kişilik kadroyla, komşusunun DURUM'unu beklemeden kendini lider ilan eder. İki uçak bunu aynı pencerede yaparsa ikisi de kendini seçer (split-brain) ve doğrudan 1. bulgudaki yalpaya girilir. 1.5 sn'lik bekleme tam olarak bunu önlemek için konmuştu.

#### DISARM'dan sonra kuyrukta kalan ARM kopyasi ucagi yeniden armliyor — dun olculen 'disarm kavgasi'nin kok nedeni

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:1689` · mercek: `komut-etkilesimi`  
_guided_gonder'de ayiklama YALNIZ TIP_GOTO icin var (esp32_bridge_node.py:1689-1691); TIP_KOMUT icin bilerek yok ('arm/takeoff/land birbirinin yerine gecmez'). Bosaltici gonderdigi kaydi kuyrugun SONUNA atiyor (1726-1730), yani ARM ve DISARM ic ice geciyor: arm#2, disarm#1, arm#3, disarm#2, arm#4... Ucakta px4_bridge'in disarm dali (px4_bridge.py:1266-1283) `_offboard_streaming=False` + `disarm()` yapiyor; hemen ardindan gelen bayat ARM cercevesi arm dalina giriyor ve TEK koruma px4_bridge.py:1245 `if self._status.armed: return`. Bu bayrak /mavros/state'ten geliyor ve HEARTBEAT hizi hic istenmiyor (deploy/rpi/mesaj_hizlari.py:12-13 sadece 24/1/147/31/331/33 istiyor), yani PX4 varsayilani ~1 Hz — disarm'dan sonraki 1 saniye boyunca `armed` HALA True veya tam tersi bayat okunur. Bayat ARM gecerse px4_bridge.py:1252-1255 `_offboard_streaming=True`, `set_offboard_mode()`, `_arm_bekliyor=True` -> `_offboard_tick` (px4_bridge.py:623-627) OFFBOARD aktif gorunce `arm()` yolluyor: ucak yeniden armlanir. Ucus SONUNDA (land -> PX4 kendi disarm eder) bu tetiklenmez, cunku o an kuyrukta ARM yok ve agent_fsm ARMED->IDLE gecisinde HICBIR komut yayinlamiyor (agent_fsm_node.py:309-310 'else: return'). Risk penceresi: ARM'dan sonraki ~2.5 sn icinde operator DISARM'a basarsa (iki ucakta 8 KOMUT cercevesi ~2.4 sn suruyor). Cozum: LAND/DISARM geldiginde ayni hedefe ait bekleyen ARM/TAKEOFF TIP_KOMUT kayitlarini kuyruktan dusur.

#### /swarm/agent/droneN/commands artik IKI uretici tasiyor; arm gecisinde DO_SET_MODE selini kanitlanmis 2 Hz sinirinin ustune cikariyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:296` · mercek: `komut-etkilesimi`  
Ayni konuya iki yayinci: esp32_bridge_node.py:419-421 (_guided_cmd_pub) ve agent_fsm_node.py:123-127 (_command_pub). b469871'e kadar FSM IDLE'da takiliydi ve hic yayin yapmiyordu; artik ARMING girisinde 'arm' (agent_fsm_node.py:296) ve ARMED girisinde 'offboard' (agent_fsm_node.py:298) yayinliyor. px4_bridge'de ikisi de `set_offboard_mode()` cagiriyor (px4_bridge.py:1253 ve 1353). Arm penceresinde toplanan DO_SET_MODE sayisi: guided ARM 4 kopya (her biri :1253) + FSM 'arm' (:1253) + FSM 'offboard' (:1353) + guided takeoff'un her kopyasinin basindaki 'offboard' (esp32_bridge_node.py:1135) -> ~1-2 saniyede 6-10 mod komutu, yani ~5 Hz. px4_bridge.py:669-673'teki kendi yorumu bunu birebir yasakliyor: '10Hz denendi ama DO_SET_MODE flood'lamak arm gecisinde cakisma yaratip bir drone'un disarm olmasina yol acti. 2Hz kanitlanmis guvenli deger.' Ayrica arm dali her seferinde `_arm_z` ve `_kalkis_kilidi_acildi`'yi sifirliyor (px4_bridge.py:1260-1261); /mavros/state 1 Hz oldugu icin bayat `armed=False` ile bu dal armli ucakta da calisabiliyor. Cozum: agent_fsm dispatch'ine 'guided modda arm/offboard yollama' kapisi (kalkis_olayla=false iken ARMING/ARMED komutlarini bastir) — 3 satir; veya px4_bridge'de set_offboard_mode cagrisina 0.5 sn'lik hiz limiti.

#### FSM tum ucus boyunca ARMED'da park ediyor: irtifa tavani, jeofen, EKF ve OFFBOARD-kaybi denetimlerinin HEPSI olu

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_health_monitor.py:31` · mercek: `komut-etkilesimi`  
kalkis_olayla=false iken mission_start_sequence_active hep False (agent_fsm_node.py:343-348), dolayisiyla agent_transitions.py:160-163 hicbir zaman TAKEOFF'a gecmiyor: ajan ARM'dan inise kadar ARMED'da kaliyor. Ama butun hava emniyet denetimleri `_AIRBORNE` kumesine bagli ve ARMED o kumede YOK (agent_health_monitor.py:31-40): 30 m irtifa tavani agent_health_monitor.py:439-440'ta `if ctx.state not in _AIRBORNE: return` ile atlaniyor; jeofen :338; EKF arizasi :202; 5 sn'lik OFFBOARD kaybi :209-212; RC link kaybi havada-kritik dali :303. Ustelik ARMED, agent_transitions.py:16-25 `_FAILSAFE_EXEMPT` icinde, yani `not ctx.healthy` FAILSAFE'e bile dusuremiyor — sadece agent_transitions.py:158 ile sessizce IDLE'a duser. Sonuc: yeni kopru ajani 'ucusun icine' soktu gibi gorunuyor (mesh'te STATE_ARMED->_DURUM_KALKIS gidiyor, consensus lider seciyor) ama ajanin ucus sirasinda uygulayacagi TEK koruma kill-switch (agent_health_monitor.py:289) ve px4_link. Yaninca yaniltici: kayitta 'FSM ayakta' gorunur, gercekte 20 m ucusta 30 m tavani hic denetlenmez. Cozum: ARMED'i `_AIRBORNE`e degil ama `armed and -pos_z > 1.5` gibi bir 'havada' turevine bagla, ya da gecis doneminde TAKEOFF'a kendiliginden gecir (kalkis komutu yayinlamadan).

#### Lider kalp atisi 10 Hz'de mesh'e hiz siniri olmadan yaziliyor ve inisten sonra da HIC durmuyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:2104` · mercek: `komut-etkilesimi`  
c3068c8 ile consensus_node.py:183-184'teki `own_airborne` sarti kaldirildi: `if ctx.is_leader: self._publish_heartbeat(...)` her tick, tick_hz=10. esp32_bridge'in aktarimi (esp32_bridge_node.py:2095-2104) HIC hiz siniri uygulamiyor — kiyas: POSE 10 Hz (:1489), DURUM 1 Hz (:1516) throttle'li. Firmware kapisi tip basina 50 ms ('TX DRONE/src/main.cpp':261,370 MESH_GONDERIM_MIN_MS 50) oldugu icin 10 Hz'in tamami geciyor. Yani lider ucagin mesh TX'i 11 -> 21 paket/sn'ye ciktiyor; ayni ESP-NOW broadcast linki GOTO ve LAND cercevelerini tasiyor ve OTA ACK yok (gorev_kanit_ucus.py:2218-2219'da olculen kayip ~%30). Ikinci sorun: election.py:98-99 `candidate = min(effective) if effective else 0` ve :99 `if candidate == 0: return None` — iki ucak da inip ELIGIBLE_STATES disina cikinca effective bosalir, `decide_change` None doner ve `ctx.is_leader` HIC False olmaz; yerde, disarm, gorev bittikten sonra bile 10 Hz kalp atisi mesh'e akmaya devam eder. Cozum: _on_leader_hb_out'a 2-5 Hz throttle (POSE ile ayni desen, ~4 satir) ve consensus'ta 'own ELIGIBLE degilse is_leader=False' birak.

#### Guided ARM mesh'te 4 kopya geliyor ve HER kopya yeni bir EVENT_MISSION_STARTED uretiyor — dun olculen 'disarm kavgasi' artik otomatik

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:1120` · mercek: `kopru-kacaklari`  
`_guided_discrete_uygula` ARM dalinda kosulsuz `_gorev_basladi_olayi_yayinla()` cagiriyor; guided komutta HICBIR dedup yok (`_isle_komut` guided dali sadece hedef suzuyor, esp32_bridge_node.py:1050-1059; `_komut_rx_seq` sayaci yalniz joystick dalinda). Kuyruk her komutu `_GUIDED_TEKRAR=4` kez, TIP_KOMUT icin en az 0.30 sn arayla gonderiyor (esp32_bridge_node.py:152-159, 1697-1730) ve iki ucak ayni kapiyi paylastigi icin dizi ~1.2-2.4 sn'ye yayiliyor. Sonuc: tek bir ARM butonu ucakta 4 ayri MISSION_STARTED uretir. O pencerede PX4 disarm olursa (elle, ya da PX4'un yerde-armli oto-disarm'i) _from_armed `not ctx.armed` ile IDLE dondurur (agent_transitions.py:158-159), ardindan gelen 2./3./4. kopya IDLE'da `pending_state=ARMING` yazar (agent_fsm_node.py:344-346), _from_idle preflight'i gecince ARMING'e girilir ve _dispatch_px4_command px4_bridge'e **'arm'** yollar (agent_fsm_node.py:295-296, 314). px4_bridge armli degilse bu dali aynen uygular: `_offboard_streaming=True`, `set_offboard_mode()`, `_arm_bekliyor=True` (px4_bridge.py:1245-1265) ve OFFBOARD aktiflesince gercekten ARM eder (px4_bridge.py:623-627). Yani operatorun disarm'i sessizce geri alinir. Dun tam bu olculdu ama tam_kalkis.sh testinde, elle enjekte edilen olayla; artik uretim yolunda kendiliginden olusuyor.

#### agent_fsm, px4_bridge komut konusunun IKINCI ureticisi oldu; RETURN_HOME/ARMED girisinde 'offboard' yayinlayip guided land/rtl'i iptal edebiliyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:303` · mercek: `kopru-kacaklari`  
agent_fsm `/swarm/agent/drone{aid}/commands`'a yayin yapiyor (agent_fsm_node.py:123-127) — esp32_bridge guided yolunun yazdigi KONUNUN AYNISI (esp32_bridge_node.py:419-421), px4_bridge tek abone (px4_bridge.py:311). CLAUDE.md bolum-4 kurali burada ihlal: bir konuya iki uretici. Kopru oncesi ajan IDLE'da kaldigi icin hicbir sey yayinlamiyordu; artik canli durumlarda. Zararli dal `offboard`: px4_bridge'in 'offboard' dali KORUMASIZ — `_offboard_streaming=True` + `set_offboard_mode()` (px4_bridge.py:1349-1353), oysa 'land' ve 'rtl' dallari tam tersini yapiyor (`_offboard_streaming=False` + land()/return_home(), px4_bridge.py:1329-1348). Somut zincir: ESP firmware mesh kopmasinda TIP_FAILSAFE(RTL) yolluyor (firmware/esp32_mesh/common/mesh_shared/fail_safe.h:91,103) -> esp32_bridge `_isle_failsafe` EVENT_RTL_TRIGGERED uretiyor, target=kendi id (esp32_bridge_node.py:1347-1367) -> agent_fsm `pending_state=RETURN_HOME` (agent_fsm_node.py:360-361). Ajan o an FAILSAFE'te ise (`_check_critical_faults` px4_link kopmasi, agent_health_monitor.py:194-199; ya da kill anahtari + `ctx.armed`, agent_health_monitor.py:289-294) `_from_failsafe` RETURN_HOME dondurur (agent_transitions.py:385-386) ve _dispatch_px4_command **'offboard'** yayinlar (agent_fsm_node.py:303-308): PX4 AUTO.RTL/AUTO.LAND'den cekilip OFFBOARD'a alinir, taze setpoint olmadigi icin px4_bridge 'anlik konumda bekle' setpoint'i yayinlar (px4_bridge.py:746-751) — yani inis/donus IPTAL olur ve ucak oldugu yerde asili kalir. Ayni sekilde EVENT_EMERGENCY_LAND (esp32_bridge_node.py:1355 veya swarm_fsm_node.py:392-396) FAILSAFE'te 'land' yayinlatir (agent_transitions.py:387-388 -> agent_fsm_node.py:301-302), bu sefer ucak nerede ise oraya iner.

#### MISSION_STARTED olayi IDLE/ARMED disindaki durumlarda SESSIZCE dusuyor, ustelik log 'kabul edildi' diyor — ajan tum ucus boyunca IDLE'da kalabilir

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:349` · mercek: `kopru-kacaklari`  
`_on_event` MISSION_STARTED dalinda durum kapisi yalniz IDLE ve ARMED (agent_fsm_node.py:344-348). Ajan o anda UNKNOWN'da (ilk telemetri gelmemis — `_from_unknown` telemetri_alindi bekliyor, agent_transitions.py:102-104), ARMING'de veya FAILSAFE'te ise olay hicbir sey yapmadan dusuyor ve HIC LOG BIRAKMIYOR. Buna karsilik 349-353'teki info logu durum kapisinin DISINDA: olay reddedilse bile 'gecis modu: ARMED e kadar gidilecek, kalkis guided yoldan' basiliyor; ayni sey yer_testi uyarisi icin de gecerli (satir 354-358). Yani operator/log 'olay isledi' diyor, ajan IDLE'da duruyor. Olayin TEK uretici yolu guided ARM oldugu icin (esp32_bridge_node.py:1109-1121) ve gorev kosucusu ARM'i bir kez gonderip teyide bakiyor (src/gcs/gorev_kanit_ucus.py:2525-2537, sonrasinda yalniz takeoff tekrarlaniyor), 4 mesh kopyasi da bu ~1-2 sn'lik pencerede kacirilirsa ajan UCUS BOYUNCA IDLE'da kalir: mesh'e STATE_IDLE gider, consensus ELIGIBLE_STATES'e giremez, lider secilmez, kalp atisi yayinlanmaz — P0.11'in tum kazanimi sessizce kaybolur. Ayni sinif hata icin 15 Agustos'ta `_tick`'e 'ARMING REDDEDILDI' teshisi eklenmisti (agent_fsm_node.py:230-238); bu kapida karsiligi yok.

#### ARMED durumu mesh'te KALKIS olarak tasiniyor, komsuda STATE_TAKEOFF'a cozuluyor — swarm_fsm yerdeyken FORMING'e geciyor ve suru-geneli acil inis dallarini aciyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:202` · mercek: `kopru-kacaklari`  
`_STATE_DURUM_MAP` ARMING ve ARMED'i `_DURUM_KALKIS`(2)'e esliyor (esp32_bridge_node.py:200-203), ters yonde `_DURUM_STATE_MAP` bunu `AgentStatus.STATE_TAKEOFF`(4) yapiyor (esp32_bridge_node.py:182). Enum degerleri birebir ayni (agent_states.py:14 TAKEOFF=4, AgentStatus.msg:22 STATE_TAKEOFF=4). Kopru oncesi ajan IDLE'da kaldigi icin mesh'e `_DURUM_BOSTA` gidiyordu ve bu esleme hic tetiklenmiyordu; artik guided ARM ile ajan ARMED'a cikinca komsu onu TAKEOFF sanir. Zincir: yeni olay ic_dis_kopru ile public'e kopyalanir (ic_dis_kopru.py:105,137-139) -> swarm_fsm `_on_event` `ctx.mission_active=True` yapar (swarm_fsm_node.py:585-587) -> `_from_idle` `mission_active` VE `count_agents_in_state(TAKEOFF)>0` gorup FORMING dondurur (swarm_transitions.py:56-66; sayim swarm_context.py:173-178). Yani iki ucak da HENUZ YERDEYKEN swarm_fsm FORMING'e gecer. FORMING, AIRBORNE_SWARM_STATES icinde (swarm_states.py:32-37) oldugu icin `_check_agent_health`'in iki tehlikeli dali acilir: (a) `healthy/expected_agent_count < 0.5` -> SWARM FAILSAFE + EVENT_EMERGENCY_LAND (swarm_fsm_node.py:399-418), (b) herhangi bir ajanda kill biti -> EVENT_KILL_SWITCH_ACTIVATED (swarm_fsm_node.py:420-439). Ikisi de `_pub_event` ile target_agent_id=0 (yayin) gider (swarm_fsm_node.py:750-764) ve agent_fsm bunlari `is_mine` sayar (agent_fsm_node.py:325): EMERGENCY_LAND -> `pending_state=LANDING` (agent_fsm_node.py:363-364), KILL -> `ctx.kill_switch_active=True` (agent_fsm_node.py:434-435, temizleyicisi yok, yalniz 10 Hz telemetri geri yaziyor -> `_check_rc_safety` ile yaris). Iki ucakli kadroda (a) dali 1/2=0.5 sinirinda kaliyor, yani bugun tetiklenmiyor — ama yalniz esitlik korumasi sayesinde; ucuncu ucak katildiginda ya da kendi ajanimiz saglıksiz gorundugunde aciliyor.

## 🟡 P2 — sonra

#### PX4-ici RTL sirasinda kacinma tamamen devre disi ve G2'de iki ucak AYNI irtifada — yedek dikey ayrim yok

`src/swarm_control/swarm_control/kacinma/basit_kacinma_node.py:320` · mercek: `rc-failsafe-ucus`  
basit_kacinma cikisini `/drone_N/control/setpoint`e yaziyor (basit_kacinma_node.py:198-199) ve oradan px4_bridge `setpoint_raw/local`a gidiyor (mavros_command_sender.py:298-315). AUTO.RTL PX4-ici moddur ve bu setpoint akisini yok sayar; dugumde 'ben veya komsum OFFBOARD'dan cikti mi' diye bir denetim yok (dosyada `flight_mode` hic okunmuyor). Yani RTL'e kalkan ucak kacinmaya HIC tepki vermez, kacinma tek tarafli … *(tam metin journal.jsonl)*

#### Komsunun healthy turetimi PX4 failsafe'ini gormuyor; POSE 10 Hz kaydi tazeledigi icin bayatlama emniyeti hic tetiklenmiyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:974` · mercek: `rc-failsafe-ucus`  
Komsu `healthy`si mesh'te bit olarak gelmiyor, `ekf_ok && !kill_switch && state != STATE_FAILSAFE` diye turetiliyor (esp32_bridge_node.py:974-978). PX4 RC-kayip failsafe'inde ucagin FSM state'i FAILSAFE olmuyor — `failsafe_active` uzerinden healthy dusup `_from_armed` ARMED->IDLE yapiyor (agent_transitions.py:158-159), mesh'e _DURUM_BOSTA gidiyor — dolayisiyla komsu `healthy=True` goruyor: yerel gercek ile uzak … *(tam metin journal.jsonl)*

#### _on_leader_hb_out: esp32_bridge'in hiz siniri OLMAYAN tek mesh ureticisi — consensus tick_hz'i 1:1 mesh'e basiyor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:2095` · mercek: `kalp-atisi-degisikligi`  
Ayni dosyadaki butun diger mesh ureticilerinin acik kapisi var: POSE 10 Hz (`if now - self._son_pose_gonderim_ts >= self._pose_periyot_s`, 1489), DURUM 1 Hz (1516), guided komutlar tip basina 0.30/0.10 sn (156-160), formasyon lider kapisiyla. _on_leader_hb_out (2095-2104) ise gelen HER LeaderHeartbeat'i dogrudan _uart_yaz'a veriyor; tek fren consensus'un tick_hz=10 degeri. Ust akista bir parametre degisirse (veya … *(tam metin journal.jsonl)*

#### RX BASE 10 Hz LEADER_HB'yi YKI hattina iletiyor — YKI'de bu mesajin HICBIR tuketicisi yok

`firmware/esp32_mesh/RX BASE/src/main.cpp:229` · mercek: `kalp-atisi-degisikligi`  
`else if (p->tip == TIP_LEADER_HB) msg.uzunluk = sizeof(leader_hb_veri_t);` — cerceve uart_kuyruk'a girip YKI'ye iletiliyor. Ayni fonksiyonun 243-249. satirlari TIP_FORMASYON'u tam ters gerekceyle DISARIDA birakiyor: 'base UART'in YKI yonu ~35 cerceve/sn ile sinirli ... karsiliginda YKI tarafinda henuz TUKETICI YOK'. Olcum: depoda src/gcs/ altinda LeaderHeartbeat aboneligi YOK (ros_bridge.py:38-46 import listesi … *(tam metin journal.jsonl)*

#### task_reallocator._on_heartbeat tur/sekans denetimsiz rol dagitimi tetikliyor; degisikligin commit gerekcesindeki 'sahte lider kayip' kodda karsiligi yok

`src/swarm_core/swarm_core/task_reallocator/task_reallocator_node.py:193` · mercek: `kalp-atisi-degisikligi`  
Iki ayri kusur. (a) _on_election (176-191) bayat mesaj filtresi uyguluyor (`rnd < last_round or (rnd == last_round and seq <= last_seq)`), ama _on_heartbeat (193-201) HICBIR tazelik denetimi yapmadan `self._consensus_leader = leader` deyip _core.apply_leader + _apply ile AssignRole servis cagrilari uretiyor. Yani kalp atisi, kendisinden YENI bir ElectionResult'i ezebiliyor; BULGU-1'deki 5-10 Hz zipla­mada bu dugum … *(tam metin journal.jsonl)*

#### swarm_fsm._on_heartbeat ctx.leader_id'yi kosulsuz eziyor: self-filtre, tur ve tazelik denetimi yok

`src/swarm_state_machine/swarm_state_machine/swarm_fsm/swarm_fsm_node.py:632` · mercek: `kalp-atisi-degisikligi`  
`ctx.leader_id = msg.leader_id` — kaynak, election_round veya kendi kimligi denetlenmeden yaziliyor (629-636); ayni dosyadaki _on_election (638-675) ise seq_kabul ile korunuyor, yani iki yol tutarsiz. Yeni durumda bu konuya AYNI ANDA iki ureticiden veri geliyor: (1) ic_dis_kopru.py:107 kendi consensus'umuzun /swarm/internal/leader/heartbeat'ini 10 Hz /swarm/public/leader/heartbeat'e kopyaliyor, (2) … *(tam metin journal.jsonl)*

#### Takipçi rolü hiç uygulanmıyor: _apply_role yalnız kenar tetiklemeli, _tick'ten yeniden denenmiyor

`src/swarm_core/swarm_core/consensus/consensus_node.py:210` · mercek: `consensus-secim`  
`_apply_role` yalnız consensus_node.py:204 (_set_leader), 261 (_adopt_leader) ve 294 (_on_election) üzerinden çağrılıyor; `_tick` içinde yeniden deneme YOK. Satır 210-211 kendi durumu ELIGIBLE_STATES'te değilse sessizce dönüyor, satır 219 servis hazır değilse yine sessizce dönüyor. Girdi: ylp00 önce arm edilip lider olur; ylp02 hâlâ IDLE iken kalp atışını alır → satır 244 `_adopt_leader(1)` → `_apply_role` satır … *(tam metin journal.jsonl)*

#### consensus kendi ElectionResult'ını ic_dis_kopru üzerinden geri alıyor; kendi kaynağını filtrelemiyor

`src/swarm_core/swarm_core/consensus/consensus_node.py:263` · mercek: `consensus-secim`  
consensus_node.py:125-128 sonucu /swarm/internal/election/result'a yazıyor; ic_dis_kopru.py:106 + 132-139 aynı uçakta bunu /swarm/public/election/result'a kopyalıyor; consensus_node.py:147-150 o konuya abone ve `_on_election` (satır 263) `triggered_by_agent_id == kendi id` kontrolü YAPMIYOR. (a) Yalpa sırasında: agent 3 kendini seçip sonucu yayınlar, milisaniyeler sonra agent 1'in kalp atışıyla liderliği bırakır, … *(tam metin journal.jsonl)*

#### election_round düğüm başına sayaç, uint8 ve '<' ile eleniyor — ayrışınca komşunun bütün seçimleri sessizce düşer

`src/swarm_core/swarm_core/consensus/consensus_node.py:287` · mercek: `consensus-secim`  
consensus_node.py:190 her YEREL karar için round'u `(x + 1) % 256` ile artırıyor, satır 254 komşununkini `max()` ile içeri alıyor. Bu sayaç Raft'taki ortak 'term' değil, düğüm başına yerel bir sayaç. 1. bulgudaki yalpada agent 3 saniyede ~10 artırırken agent 1 sabit kalır. Ardından satır 287 `if msg.election_round < ctx.election_round: return` agent 1'in BÜTÜN ElectionResult'larını sessizce düşürür — seq/incarnation … *(tam metin journal.jsonl)*

#### battery_min_v mayını: pil izleme açılır açılmaz hiçbir ajan lider adayı olamaz

`src/swarm_core/swarm_core/consensus/election.py:29` · mercek: `consensus-secim`  
election.py:29 `if rec.battery_v > 0.0 and rec.battery_v < battery_min_v: return False`. baslat.sh:664 `battery_min_v`'yi BATARYA_KRITIK_V'den alıyor; bugün 0.0 olduğu için kapı kapalı ve yarın sorun çıkarmaz. Ama uçaklar regülatörden besleniyor ve battery_voltage_v sabit 12.6 V okunuyor; bu değer mesh'te de birebir taşınıyor (packet_parser.py:564 volt_x10, esp32_bridge_node.py:935 `status.battery_voltage_v = … *(tam metin journal.jsonl)*

#### ARMED'da mesh failsafe (RTL / acil inis) olaylari sessizce dusuyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_transitions.py:158` · mercek: `komut-etkilesimi`  
esp32_bridge_node.py:1347-1367 mesh 0xFA failsafe paketini EVENT_RTL_TRIGGERED / EVENT_EMERGENCY_LAND'e ceviriyor; agent_fsm_node.py:360-364 bunlari `ctx.pending_state = RETURN_HOME / LANDING` olarak yaziyor. Ama `_from_armed` (agent_transitions.py:146-164) pending_state'e HIC bakmiyor — sadece armed/healthy ve mission_start'a bakiyor — ve agent_fsm_node.py:257 her tick sonunda `ctx.pending_state = None` yapiyor. … *(tam metin journal.jsonl)*

#### failsafe_active ve rc_signal_failsafe_active mesh'te hic tasinmiyor — gorev kosucusunun FAILSAFE kesicisi kalici olarak kor

`src/swarm_control/swarm_control/esp32_bridge/esp32_bridge_node.py:907` · mercek: `komut-etkilesimi`  
YKI telemetrisi `/swarm/public/drone{id}/status` konusundan geliyor (ros_bridge.py:620), onu da baz esp32_bridge'in _isle_durum'u dolduruyor (esp32_bridge_node.py:907-993). O blok state/armed/gps/batarya/ekf/kill/rc_link/ready_to_arm/origin_synced/healthy yaziyor ama `failsafe_active`'i HIC yazmiyor, dolayisiyla AgentStatus varsayilani False kaliyor. ros_bridge.py:254 bu alani oldugu gibi tasiyor ve … *(tam metin journal.jsonl)*

#### EVENT_MISSION_STARTED, agent_fsm'de hedef suzgeci (is_mine) olmayan TEK olay dali

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:327` · mercek: `kopru-kacaklari`  
`_on_event` icinde `is_mine = tgt == 0 or tgt == aid` hesaplaniyor (satir 325) ve RTL, EMERGENCY_LAND, SAFETY_HOLD, DETACH, REJOIN, MANEUVER, JOIN_REQUEST dallarinin hepsinde kullaniliyor; MISSION_STARTED dalinda (satir 327) KULLANILMIYOR. Kopru olayi `target_agent_id = self._agent_id` ile uretiyor (esp32_bridge_node.py:1166) ama bu deger hicbir yerde denetlenmiyor: ayni ROS alaninda uretilen HERHANGI bir … *(tam metin journal.jsonl)*

#### ic_dis_kopru her yerel olayi public'e kopyaliyor, agent_fsm iki konuya birden abone — her olay IKI KEZ isleniyor ve dugum kendi olayini geri yiyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:147` · mercek: `kopru-kacaklari`  
agent_fsm hem `/swarm/public/events/system` hem `/swarm/internal/events/system` konusuna abone (agent_fsm_node.py:139-150), ic_dis_kopru ise internal'i public'e aynen kopyaliyor (ic_dis_kopru.py:105 tablosu + 137-139/149-154). Sonuc: yerel uretilen her olay `_on_event`'e iki kez ulasiyor — guided ARM'in 4 kopyasi 8 isleme donusuyor, esp32_bridge'in 1 Hz mesh_diag olayi (esp32_bridge_node.py:624) 2 Hz'e cikiyor. … *(tam metin journal.jsonl)*

#### _ARMING_TIMEOUT_S ve _ARMED_STABILIZE_S iki kez tanimli — okunan deger yaziani degil

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_transitions.py:9` · mercek: `kopru-kacaklari`  
Dosya basinda `_ARMING_TIMEOUT_S = 30.0` (satir 7) ve hemen ardindan `_ARMING_TIMEOUT_S = 15.0` (satir 9); ayni sekilde `_ARMED_STABILIZE_S` satir 8 ve 10'da. Python ikincisini alir, yani gercek arming zaman asimi 15 sn. Kodu okuyan 30 sn sanir. Pratik sonucu bulgu 4 ile birlesiyor: guided ARM sonrasi PX4 15 sn icinde arm etmezse (px4_bridge once OFFBOARD'in aktiflesmesini bekliyor, px4_bridge.py:623-638) … *(tam metin journal.jsonl)*

#### _transition icindeki WAITING_REJOIN -> ARMING dali OLU KOD; yeni kalkis_olayla duzeltmesi orada hic calismiyor

`src/swarm_state_machine/swarm_state_machine/agent_fsm/agent_fsm_node.py:272` · mercek: `kopru-kacaklari`  
Dunku commit `if old == AgentState.WAITING_REJOIN and new_state == AgentState.ARMING: self._ctx.mission_start_sequence_active = self._kalkis_olayla` satirini duzeltti (agent_fsm_node.py:272-273), ama gecis tablosunda WAITING_REJOIN'den ARMING'e giden HICBIR yol yok: `_from_waiting_rejoin` yalniz REJOINING veya FAILSAFE donduruyor (agent_transitions.py:264-280) ve `_on_event` WAITING_REJOIN'de ARMING pending'i … *(tam metin journal.jsonl)*

---

## Doğrulayıcı kararları (tamamlananlar)

- **ÇÜRÜTÜLDÜ** — Her GOTO cercevesi SetMode(OFFBOARD) uretiyor: dun kurulan RC failsafe RTL'i 5 Hz'de geri 
  - Bulgunun cekirdek iddiasi — "Kodda 'PX4 su an hangi modda' diye bakan hicbir kapi yok" ve "RC hala yokken gorev devam ediyor" — koda bakinca yanlis. Tam o kapi var, tam bu senaryo icin yazilmis ve GOTO gonderiminden ONCE calisiyor.

1) MOD KAPISI VAR VE GOTO'DAN ONCE KOSUYOR.
src/gcs/gorev_kanit_ucus.py `git_ve_bekle` dongusunun tik sirasi:
  :2151  time.sleep(SETPOINT_ADIM_S)   # 0.2 sn
  :2153 …

- **GERÇEK** — heartbeat_timeout_ms bu uçuşta tamamen ölü — own_airborne hiçbir zaman true olmayacak\nDos
  - ÇÜRÜTÜLEMEDİ — zincirin her halkası kodda birebir doğrulandı, üç ayrı çürütme denemesi de düştü.

DOĞRULANAN ZİNCİR (hepsi mevcut HEAD, `git status` bu dosyalarda değişiklik göstermiyor — yalnız docs/ kirli):
1. src/swarm_core/swarm_core/consensus/election.py:47 — `if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:` Kapı aynen iddia edildiği gibi. …

- **GERÇEK** — Bayatlık yanlış akışı ölçüyor: POSE 10 Hz kaydı tazeliyor, sağlık/durum yalnız 1 Hz DURUM'
  - DOGRULANDI — zincirin her halkasi kodda birebir var, cürütecek koruma yok.

1) Tek zaman damgasi, yanlis akisla tazeleniyor:
- consensus_context.py:9-12 `AgentRec.__slots__` icinde SADECE bir zaman alani var (`last_update`); state/healthy/estimator_ok icin ayri tazelik olcusu YOK.
- consensus_context.py:88-93 `update_status` her AgentStatus'ta hem alanlari hem `rec.last_update = now` yaziyor (sati …

- **GERÇEK** — Bayatlık yanlış akışı ölçüyor: POSE 10 Hz kaydı tazeliyor, sağlık/durum yalnız 1 Hz DURUM'
  - ÇÜRÜTEMEDİM — zincirin her halkası kodda birebir doğrulandı; üstelik akla gelen tek mevcut koruma bu senaryoyu kapatmıyor.

DOĞRULANAN ZİNCİR (satır satır):
1. consensus_context.py:88-93 — `update_status` her AgentStatus mesajında state/role/healthy/estimator_ok/battery ile BİRLİKTE `rec.last_update = now` yazıyor. İçerik denetimi yok.
2. esp32_bridge_node.py:815-876 — `_isle_pose` yalnız lat/lon/ …

- **GERÇEK** — heartbeat_timeout_ms bu uçuşta tamamen ölü — own_airborne hiçbir zaman true olmayacak\nDos
  - DOGRULANDI — bulgunun ana iddiasi koddan bire bir izlenebiliyor; curutemedim.

1) Kapi gercekten own_airborne'a bagli: election.py:47 `if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:` ve hb yasi karsilastirmasi yalniz bu blogun icinde (election.py:52-56). `hb_timeout_s`in repo genelinde BASKA tuketicisi yok: grep ile tek kullanim election.py:55 (tanim consensus_node.py:98/106-107, ta …

- **GERÇEK** — Lider yalpası: kalp atışı 'benim' der, uygunluk kapısı 'değil' der → 10 Hz'de sürekli lide
  - ÇÜRÜTEMEDİM — zincirin her halkası kodda doğrulandı, engelleyen bir koruma yok.

1) Kalp atışı kapısı gerçekten kalktı: `consensus_node.py:183-184` `if ctx.is_leader: self._publish_heartbeat(...)` — `own_airborne` şartı yok, üstündeki yorum (173-182) değişikliği açıkça anlatıyor. Tick 10 Hz (`_tick_hz` varsayılan 10.0, `consensus_node.py:96`).

2) Kabul kapısı koşulsuz: `consensus_node.py:241-244` …

- **ÇÜRÜTÜLDÜ** — Lider yalpası: kalp atışı 'benim' der, uygunluk kapısı 'değil' der → 10 Hz'de sürekli lide
  - Kod kancasi gercek, ama bulgunun tetikleyicisi, "dun acildi" iddiasi ve "kalici hal" ayagi kodda cürütülüyor; yarinki ucus icin P1 degil.

DOGRULANAN TEK SEY (kancanin kendisi):
- src/swarm_core/swarm_core/consensus/consensus_node.py:243-244 gercekten kosulsuz: `elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id: self._adopt_leader(...)` — iddia sahibin …

---

## Denetimi tamamlamak isteyen için

Doğrulama aşaması yarım kaldı. Kalan bulguları doğrulatmak yerine **elle koddan
teyit etmek** daha ucuz: her bulgunun `dosya:satir`'ı verilmiş, mekanizma metni
zinciri adım adım anlatıyor. Bir bulguyu uygulamadan önce şunu sor: *"bu zincirin
her halkası bugünkü kodda gerçekten var mı, ve bunu engelleyen mevcut bir koruma
var mı?"* — çürütülen P0'ın hatası tam buydu.
