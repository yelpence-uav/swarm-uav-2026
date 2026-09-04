# Copyright 2026 Yelpence
"""mode_manager calisma zamani durum kabi."""

import math
import time
from dataclasses import dataclass, field

from swarm_core.formation_control.manual_kinematics import (
    dairesel_ortalama_deg,
    slew,
)

from .mode_states import ControlMode, ModeState

_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDED = 13

_MISSION_STATE_SEMI_AUTONOMOUS = 8

# Kalkis "ulasildi" olcutu: hedef irtifanin bu orani gecilince TAKEOFF biter.
# 0.8 UYDURULMADI — formasyon_sekans ayni olcutu ayni oranla kuruyor
# (ucus_ayarlari.SEKANS_KALKIS_ESIK_ORANI, "EKF z / origin farki ~1 m
# olculdu, 26 Agu"). Tam irtifa beklemek yanlis olurdu: PX4 hedefe
# asimptotik yaklasir ve son 20 cm dakikalar surebilir.
_KALKIS_ULASMA_ORANI = 0.8


@dataclass
class ModeContext:
    """mode_manager FSM calisma zamani durumu."""

    agent_ids: list

    sitl_mode: bool = False

    state: ModeState = ModeState.IDLE
    state_entry_time: float = field(default_factory=time.monotonic)

    mission_state: int = 0

    command_valid: bool = False
    deadman_pressed: bool = False
    deadman_timeout_s: float = 0.5
    control_mode: ControlMode = ControlMode.UNKNOWN

    pitch_cmd: float = 0.0
    roll_cmd: float = 0.0
    yaw_cmd: float = 0.0
    throttle_cmd: float = 0.0

    takeoff_requested: bool = False
    land_requested: bool = False
    rtl_requested: bool = False
    emergency_stop_requested: bool = False

    formation_change_requested: bool = False
    requested_formation: int = 0
    requested_spacing_m: float = 5.0

    max_speed_mps: float = 2.0
    max_yaw_rate_deg_s: float = 30.0
    max_tilt_deg: float = 15.0
    # B6 ivme rampasi — gerekce compute_centroid_delta docstring'inde.
    max_accel_mps2: float = 1.3
    max_accel_z_mps2: float = 1.0
    # Govde cercevesindeki ANLIK centroid hizi (rampanin durumu).
    v_ileri: float = 0.0
    v_sag: float = 0.0
    v_yukari: float = 0.0

    last_valid_command_time: float = 0.0
    command_sequence_num: int = 0

    centroid_x: float = 0.0
    centroid_y: float = 0.0
    centroid_z: float = 0.0
    formation_heading_deg: float = 0.0
    active_formation: int = 0
    formation_reached: bool = False
    formation_stable: bool = False

    maneuver_pitch_deg: float = 0.0
    maneuver_roll_deg: float = 0.0

    # --- B15 KALKIS KAPISI + B3 test atlatmasi (30 Agustos 2026) ---------
    # kalkis_tamam bir MANDAL: bir kez acilir, geri KAPANMAZ.
    kalkis_esik_m: float = 2.0
    kalkis_tamam: bool = False
    test_hazir_atla: bool = False
    # Kapi acilirken olculen heading'in tutarliligi (0..1). Dugum bunu
    # loglar; dusukse ucaklar ayni yone bakmiyor demektir (B17).
    kalkis_heading_tutarlilik: float = 0.0

    # --- B2 KUMANDADAN KALKIS (madde 25, 30 Agustos 2026) ----------------
    # Sartname §5.2.2: "Takeoff ve land komutlari da kumanda uzerinden
    # yapilir". kalkis_irtifa_m TEST irtifasindan (MOD_TEST_IRTIFA_M) AYRI
    # bir parametre: hakem "15 m" derse gorev oncesi bu degisir, manevra
    # testinin genligi degismez.
    kalkis_irtifa_m: float = 8.0
    # Kalkis komutunu BIZ mi verdik? TAKEOFF'un bitis olcutunu belirler
    # (bkz. mode_transitions._from_takeoff).
    kalkis_komutu_verildi: bool = False
    # Komut anindaki ZEMIN z'leri (agent_id -> pos_z). Yukseklik BUNA gore
    # olculur, origin'e gore DEGIL: acik alanda ucaklar origin'den
    # -0,1 .. +1,7 m sapmayla duruyordu (§7.5 olcumu) ve mutlak esik o
    # sapmayi hedefe ekler/cikarirdi.
    kalkis_zemin_z: dict = field(default_factory=dict)

    agent_statuses: dict = field(default_factory=dict)

    pending_abort: bool = False

    def set_state(self, new_state: ModeState) -> None:
        """Durumu degistirir ve zamanlayiciyi sifirlar."""
        self.state = new_state
        self.state_entry_time = time.monotonic()

        self.takeoff_requested = False
        self.land_requested = False
        self.rtl_requested = False
        self.emergency_stop_requested = False
        self.formation_change_requested = False

    def time_in_state(self) -> float:
        """Bu state'te gecen sure."""
        return time.monotonic() - self.state_entry_time

    def deadman_timed_out(self) -> bool:
        """Deadman timeout asildi mi?."""
        if self.last_valid_command_time <= 0.0:
            return True
        elapsed = time.monotonic() - self.last_valid_command_time
        return elapsed > self.deadman_timeout_s

    @property
    def command_active(self) -> bool:
        """Gecerli bir joystick komutu aktif mi?."""
        return (
            self.command_valid
            and self.deadman_pressed
            and not self.deadman_timed_out()
        )

    def has_nonzero_input(self) -> bool:
        """Joystick'te sifir olmayan girdi var mi?."""
        threshold = 0.05
        return (
            abs(self.pitch_cmd) > threshold
            or abs(self.roll_cmd) > threshold
            or abs(self.yaw_cmd) > threshold
            or abs(self.throttle_cmd) > threshold
        )

    def all_agents_seen(self) -> bool:
        """Her ajan icin en az bir durum mesaji alindiysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_swarm(self) -> bool:
        """Tum ajanlar STATE_IN_SWARM ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == _AGENT_STATE_IN_SWARM
            for s in self.agent_statuses.values()
        )

    def all_agents_landed(self) -> bool:
        """Tum ajanlar STATE_LANDED ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == _AGENT_STATE_LANDED
            for s in self.agent_statuses.values()
        )

    def all_agents_disarmed(self) -> bool:
        """Her ajanin durumu geldi ve HICBIRI armli degilse True.

        B19 cikis kosulu. `armed` mesh'ten geciyor (durum_paketle:581 ->
        esp32_bridge:1348) ve KALKIS KAPISINDA da guvendigimiz alan bu:
        disarm bir ucak havada olamaz, irtifa referansindan bagimsizdir.

        ⚠️ BAYAT DURUM: bir komsunun mesajlari kesilmisse elimizde son
        bilinen kayit kalir. LANDING 90 sn'de zaman asimina ugrayip
        COMPLETED'a gecmisse ve o ucak GERCEKTE hala armliysa burasi
        yanlislikla True donebilir. Kabul edildi: alternatifi (irtifa)
        DAHA guvenilmez (§7.5 — yerde +1,7 m okundu) ve sonuc IDLE'a
        donmekten ibaret; IDLE tek basina hicbir komut uretmiyor.
        """
        if not self.all_agents_seen():
            return False
        return not any(
            bool(getattr(self.agent_statuses[aid], 'armed', False))
            for aid in self.agent_ids
        )

    def all_agents_healthy(self) -> bool:
        """Her ajan healthy=True bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def is_mission_semi_autonomous(self) -> bool:
        """mission_fsm SEMI_AUTONOMOUS state'inde mi?."""
        return self.mission_state == _MISSION_STATE_SEMI_AUTONOMOUS

    def ucus_durumunu_sifirla(self) -> None:
        """B19 — COMPLETED'dan IDLE'a donerken ucus defterini temizler.

        🔴 SIFIRLANMAYAN HER ALAN IKINCI DENEMEDE YANLIS DAVRANIR:

        * `kalkis_tamam` bir MANDAL ve geri kapanmiyor. Temizlenmezse
          ikinci denemede yayin kapisi UCAKLAR YERDEYKEN acik sayilir —
          B15'in kapatmak icin var oldugu seyin ta kendisi.
        * `kalkis_zemin_z` ONCEKI ucusun zeminini tutar; ucak birinci
          inisde 3 m yana kaymissa ikinci kalkisin "irtifaya ulasildi"
          olcutu yanlis referanstan olculur.
        * `maneuver_*` sifir degilse HOLD egik poz yayinlar ve
          formation_node susturulur — ikinci ucusa egik baslamak demek.

        Gorev basina UC HAKKIMIZ var; bu yol saha gununde kullanilacak.
        """
        self.kalkis_tamam = False
        self.kalkis_komutu_verildi = False
        self.kalkis_zemin_z = {}
        self.kalkis_heading_tutarlilik = 0.0
        self.maneuver_pitch_deg = 0.0
        self.maneuver_roll_deg = 0.0
        # 🔴 IVME RAMPASI DA SILINIR (B6, 31 Agustos). Birinci ucus tam
        # hizda biterse hiz durumu 2 m/s'te kalir; ikinci denemede ilk
        # MOVEMENT tick'i cubuk merkezdeyken bile o hizdan devam eder ve
        # suru SICRAR. Testle kilitli: test_ivme_rampasi.
        self.hiz_rampasini_sifirla()

    def kalkis_kapisi_degerlendir(self) -> bool:
        """B15 — KALKIS KAPISI. Bir kez acilir, geri KAPANMAZ.

        NEDEN VAR (30 Agustos 2026): mode_manager READY durumunda
        _dispatch_hold() cagiriyor ve o da FormationCommand YAYINLIYOR.
        Centroid ise swarm_fsm'den geliyor; swarm_context.compute_centroid()
        AKTIF AJAN YOKSA HICBIR SEY YAZMADAN DONUYOR, yani acilistaki
        (0,0,0) oldugu gibi kaliyor. Zincir:

            test_hazir_atla -> FSM yerde READY'ye atlar
              -> _dispatch_hold() -> center=(0,0,0) tarifi yayinlanir
              -> formation_node bunu ucurur
              -> ARM + OFFBOARD ise ucak NED ORIGIN'E GIDER

        formasyon_sekans_node ayni isi DOGRU yapiyor: guided ARM olayini
        bekler, sonra ucak 0.8 x irtifa'ya cikana kadar SUSAR
        (formasyon_sekans_node.py:331, :379). Ayni kapi buraya tasindi.

        GERI KAPANMAZ, cunku bu bir KALKIS kapisi — surekli saglik denetimi
        DEGIL. Havadayken bir ucagin durumu bayatlayinca yayini kesmek
        formasyonu sahipsiz birakir. Baslamamak guvenli, ortada birakmak
        degil.

        Returns:
            bool: mode_manager yayin yapabilir mi.
        """
        if self.kalkis_tamam:
            return True
        if not self.all_agents_seen():
            return False

        # 🔴 ARM SARTI — 30 Agustos, ACIK ALAN OLCUMU ekledi.
        #
        # Esik ORIGIN'e goreli, YERE goreli DEGIL (AgentStatus.pos_z paylasilan
        # NED origin'inden olculur). Sahada olculdu: ucaklar YERDE dururken
        #     ylp00 +1,7 m · ylp01 -0,1 m · ylp02 0,0 m
        # yani ylp00 sirf YERLESIM yuzunden 2,0 m esigin %85'ini tuketmisti.
        # Bir ucak origin'in 2,5 m ustune konsaydi — ya da origin daha alcak
        # ayarlansaydi — KAPI YERDEYKEN ACIK OLURDU. Tam da engellemek icin
        # yazildigi sey.
        #
        # DISARM BIR UCAK HAVADA OLAMAZ. Bu sart irtifa referansindan
        # bagimsiz oldugu icin deligi kapatiyor. `armed` mesh'ten geciyor
        # (durum_paketle:581 -> esp32_bridge:1348), yani komsular icin de
        # guvenilir.
        disarm = [
            aid for aid in self.agent_ids
            if not bool(getattr(self.agent_statuses[aid], 'armed', False))
        ]
        if disarm:
            return False

        yukseklikler = []
        for aid in self.agent_ids:
            st = self.agent_statuses.get(aid)
            if st is None:
                return False
            # NED: pos_z asagi POZITIF -> yukseklik = -pos_z
            yukseklikler.append(-float(st.pos_z))

        if min(yukseklikler) < self.kalkis_esik_m:
            return False

        # KAPI ACILIYOR — centroid ve heading ucaklarin KENDI konumundan.
        self.konumdan_tohumla()
        self.kalkis_tamam = True
        return True

    def konumdan_tohumla(self) -> bool:
        """Centroid'i ve heading'i ucaklarin OLCULEN konumundan kurar.

        SwarmState'e BILEREK guvenilmiyor: swarm_fsm kapaliysa (B16) ya da
        compute_centroid hic kosmadiysa oradan (0,0,0) gelir. Ucaklarin
        kendi pos_x/y/z ortalamasi zaten centroid'in TANIMI, yani bu
        tohumlama hem dogru hem de B16'nin ayni tuzagini kapatiyor.

        🔴 B17 — HEADING DE TOHUMLANIR (30 Agustos 2026).
        SwarmState.formation_heading_deg swarm_fsm tarafindan HIC
        hesaplanmiyordu ve kalici olarak 0.0 idi (swarm_context.py:73
        tanimli, atama yoktu). Sonucu: mode_manager heading'i 0 = KUZEY
        saniyor; pilot SwC ile gercek bir formasyon secmisse ilk
        FormationCommand slotlari kuzeye dizer ve suru KIMSENIN KOMUT
        VERMEDIGI bir donus yapar — tam kontrolun pilota gectigi anda.
        7 m aralikta kanatlar ~10 m yer degistiriyordu.

        Neden GEOMETRIDEN degil OLCULEN YAW'dan: cizgi formasyonunun
        geometrisi IKI YONLU BELIRSIZ (hangi uc on?), olculen yaw degil.
        Dairesel ortalama sart — 359/0/1 okunan bir suruda aritmetik
        ortalama guneyi gosterirdi.

        IKI YERDEN CAGRILIR: kalkis kapisi acilirken ve KONTROL PILOTA
        GECERKEN (READY girisi, madde 25). Ikincisi olmazsa suru READY'de
        kapinin acildigi 2 m'ye GERI DALAR — ayrinti mode_manager_node
        _on_state_entry(READY).

        Returns:
            bool: tohumlandi mi (eksik ajan varsa False).
        """
        n = len(self.agent_ids)
        if n == 0 or not self.all_agents_seen():
            return False

        self.centroid_x = sum(
            float(self.agent_statuses[a].pos_x) for a in self.agent_ids
        ) / n
        self.centroid_y = sum(
            float(self.agent_statuses[a].pos_y) for a in self.agent_ids
        ) / n
        self.centroid_z = sum(
            float(self.agent_statuses[a].pos_z) for a in self.agent_ids
        ) / n

        self.formation_heading_deg, self.kalkis_heading_tutarlilik = \
            dairesel_ortalama_deg([
                float(self.agent_statuses[a].heading_deg)
                for a in self.agent_ids
            ])
        return True

    def kalkis_yetkisi_var(self) -> bool:
        """G2-K10 — ARM+kalkis komutu uretilebilir mi?.

        🔴 30 Agustos saha olayinin KOKU arm'in ORTUK gerceklesmesiydi:
        SwD'ye dokunmak EVENT_MISSION_STARTED yayinliyordu, agent_fsm onu
        ARM'a ceviriyordu ve UC UCAK birden armlandi (§7.6). Ders "arm'i
        gizle" degil, "arm'i ACIKCA TASARLA" idi.

        G2-K10 (operator, 30 Agustos 2026) — secenek (a): SwD tek harekette
        `arm` + `takeoff:H`, UC KAPIYLA:

            1. SwA acik        -> deadman_pressed
            2. gaz merkezde    -> command_valid (B18 kapisi)
            3. gorev YKI'den baslatilmis  <- BURASI

        Ilk ikisi joystick_interpreter'da; ucu birden ctx.takeoff_requested'i
        kuran daldan geciyor (mode_manager_node._on_control_command: takeoff
        YALNIZ hem deadman_pressed hem command_valid dogruyken set edilir —
        "gecersiz pakette kalkis istenmez" kurali).

        Ucuncu kapi BURASI ve YALNIZ gercek gorev durumuna bakar;
        test_hazir_atla BILEREK KABUL EDILMIYOR. O bayrak (B3) FSM'i
        mission_fsm olmadan READY'ye ulastirmak icin var; ARM yetkisi de
        verseydi 30 Agustos'un aynisini "test" adi altinda tekrar ederdik.
        Yani madde 27 (mission_fsm) + madde 28 (YKI BASLAT) bitene kadar
        SwD SURUYU ARMLAYAMAZ — kritik yolun sirasi tam bu yuzden
        24 -> 25 -> 27 -> 28.

        Yer testinde kapi elle acilabilir (mesh'e dokunmaz, YEREL konu):
            ros2 topic pub -1 /swarm/internal/mission/state \
                std_msgs/msg/UInt8 "{data: 8}"

        Returns:
            bool: kalkis komutu uretilebilir mi.
        """
        return self.is_mission_semi_autonomous()

    def kalkis_zeminini_tohumla(self) -> None:
        """Kalkis komutu anindaki zemin z'lerini kaydeder.

        Yukseklik ORIGIN'e gore olculemez: §7.5'te ucaklar YERDE dururken
        ylp00 +1,7 m · ylp01 -0,1 m · ylp02 0,0 m okundu. Mutlak bir
        "irtifaya ulasildi" esigi bu sapmayi hedefe eklerdi — ylp00 hedefe
        1,7 m ERKEN, baskasi gec ulasmis sayilirdi. px4_bridge de ayni
        secimi yapiyor: `_target_altitude_ned = _cached_pos_z - altitude`
        (px4_bridge.py:1384), yani hedef HER UCAGIN KENDI zeminine goreli.
        Olcut ile komut ayni referansta olmak zorunda.
        """
        self.kalkis_zemin_z = {
            aid: float(st.pos_z)
            for aid, st in self.agent_statuses.items()
            if aid in self.agent_ids
        }

    def kalkis_irtifasina_ulasildi(self) -> bool:
        """TUM ucaklar hedef irtifanin %80'ini gecti mi?.

        🔴 NEDEN "2 m kapisi" YETMEZ: B15 kapisi (kalkis_esik_m = 2 m)
        mode_manager'in YAYIN iznidir, kalkisin bitisi DEGIL. Ikisi
        karistirilirsa suru 2 m'de READY olur ve _dispatch_hold() tarif
        yayinlamaya baslar. Tarifin center_z'si kapinin acildigi anda
        ucaklardan tohumlanan centroid_z'dir — yani 2 m. formation_node o
        irtifayi hedef sanip tutar ve TIRMANIS 2 m'DE DURUR, hedef 8 m
        iken. Ustelik hicbir yerde hata gorunmez.
        """
        if not self.kalkis_zemin_z:
            return False
        gereken = self.kalkis_irtifa_m * _KALKIS_ULASMA_ORANI
        for aid in self.agent_ids:
            st = self.agent_statuses.get(aid)
            zemin = self.kalkis_zemin_z.get(aid)
            if st is None or zemin is None:
                return False
            # NED: pos_z asagi POZITIF -> kazanilan yukseklik = zemin - z
            if (zemin - float(st.pos_z)) < gereken:
                return False
        return True

    def olculen_ofsetler(self) -> dict:
        """Ucaklarin OLCULEN konumlarindan centroid'e goreli ofset uretir.

        NEDEN VAR: kalkis kapisi acildigi anda mode_manager'in elindeki
        _formation_offsets hala _init_default_offsets()'in GOMULU ucgeni
        olabilir. Pilot ilk is MANEVRA'ya gecerse (MOVEMENT/HOLD'dan hic
        gecmeden) o gomulu ofsetler egilir ve ucaklar bulunduklari yerden
        gomulu ucgene ISINLANMAYA kalkar — B7'nin ayni tuzagi, baska kapi.
        Kapi acilirken olculen geometriyle tohumlayinca boyle bir sicrama
        kalmiyor; sonraki her MOVEMENT/HOLD tick'i zaten gercek slot
        geometrisiyle tazeliyor.

        oz BILEREK 0.0: egim (apply_tilt) yalniz z'yi module ediyor ve
        _publish_formation_command'in FORMATION_UNKNOWN dali da ayni
        sozlesmeyi kullaniyor.

        🔴 GOVDE CERCEVESI ZORUNLU (4 Eylul, olculen bug). pos-centroid HAM
        NED verir, ama tuketici compute_agent_setpoints/compute_slot_offsets
        ofseti GOVDE cercevesi sanip heading ile NED'e DONDURUR
        (rx=ox*cos-oy*sin). Ham NED'i tekrar dondurmek ucaklari heading
        kadar donmus dizilime surer — SAHADA olculdu: manevraya gecince
        diziliş 287°'de donup "cizgi" gibi goründü, gercek pozisyondan
        3.6-7.2 m sapti. Cozum: NED ofseti heading ile TERS dondurup govde
        cercevesine al; tuketici geri dondurunce gercek pozisyona oturur
        (ters+duz = birim, sapma 0). Test: test_olculen_govde_cercevesi.
        """
        h = math.radians(self.formation_heading_deg)
        cos_h = math.cos(h)
        sin_h = math.sin(h)
        out = {}
        for aid, st in self.agent_statuses.items():
            if aid not in self.agent_ids:
                continue
            dx = float(st.pos_x) - self.centroid_x   # NED
            dy = float(st.pos_y) - self.centroid_y
            out[aid] = (
                dx * cos_h + dy * sin_h,             # NED -> GOVDE (ters)
                -dx * sin_h + dy * cos_h,
                0.0,
            )
        return out

    def compute_heading_rotation(
        self, yaw_cmd: float, dt: float
    ) -> float:
        """Yaw komutuna gore yeni heading hesaplar."""
        delta = yaw_cmd * self.max_yaw_rate_deg_s * dt
        new_heading = (self.formation_heading_deg + delta) % 360.0
        return new_heading

    def hiz_rampasini_sifirla(self) -> None:
        """Rampa durumunu sifirlar.

        HOLD'a, INIS'e ya da IDLE'a gecerken cagrilir: yoksa bir sonraki
        HAREKET tick'i ONCEKI hizdan devam eder ve cubuk merkezdeyken bile
        suru kayar.
        """
        self.v_ileri = 0.0
        self.v_sag = 0.0
        self.v_yukari = 0.0

    def compute_centroid_delta(
        self, pitch_cmd: float, roll_cmd: float,
        throttle_cmd: float, dt: float,
    ) -> tuple[float, float, float]:
        """Joystick girdisine gore centroid delta hesaplar (NED).

        🔴 IVME RAMPALI — B6, 31 Agustos 2026.

        ONCEDEN cubuk hiza ANINDA ceviriliyordu: tam basildiginda komut bir
        tick'te 0 -> 2 m/s. Sartname osilasyonu -10 ile cezalandiriyor ve
        cok rotorlu ucak o basamagi ancak sertce egilerek takip edebilir.

        Rampa `manual_kinematics.slew` ile — AYNI fonksiyon
        `swarm_movement_step` icinde de kullaniliyor, ikinci bir kopya YOK.

        ⚠️ `swarm_movement_step` OLDUGU GIBI KULLANILAMADI: o fonksiyon
        heading ile DONDURMUYOR, pitch'i dogrudan KUZEY sayiyor. Burasi
        govde cercevesinde calisiyor (cubuk ileri = surunun BAKTIGI yon) ve
        pilot icin dogru olan bu. Korlemesine degistirmek "ileri"nin anlamini
        kuzeye cevirirdi — sessiz ve tehlikeli bir davranis degisikligi.

        Rampa GOVDE cercevesinde uygulaniyor, dunya cercevesinde degil:
        suru donerken komut edilen yon burnu takip etsin diye. Dunyada
        rampalansaydi yaw sirasinda gecikme hissedilirdi.
        """
        v_ileri_hedef = pitch_cmd * self.max_speed_mps
        v_sag_hedef = roll_cmd * self.max_speed_mps
        v_yukari_hedef = throttle_cmd * self.max_speed_mps

        da_xy = self.max_accel_mps2 * max(0.0, dt)
        da_z = self.max_accel_z_mps2 * max(0.0, dt)
        self.v_ileri = slew(self.v_ileri, v_ileri_hedef, da_xy)
        self.v_sag = slew(self.v_sag, v_sag_hedef, da_xy)
        self.v_yukari = slew(self.v_yukari, v_yukari_hedef, da_z)

        v_forward = self.v_ileri
        v_right = self.v_sag
        v_up = self.v_yukari

        heading_rad = math.radians(self.formation_heading_deg)
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)

        dx = (v_forward * cos_h - v_right * sin_h) * dt
        dy = (v_forward * sin_h + v_right * cos_h) * dt
        dz = -v_up * dt

        return dx, dy, dz
