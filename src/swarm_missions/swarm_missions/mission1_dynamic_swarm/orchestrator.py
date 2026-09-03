"""orchestrator.py — Görev 1 dinamik sürü orkestrasyon çekirdeği (ROS'suz)."""

from dataclasses import dataclass, field
import math

from swarm_core.formation_control.formation_geometry import rotate_offset
from swarm_core.formation_control.manual_kinematics import apply_tilt

from .formation_cmd import build_slot_assignment
from .qr_geo import QrGeoResolver

# MissionState (swarm_state_machine mission_states.py ile aynı tutulmalı).
_S_SYNCHRONIZED_TAKEOFF = 3
_S_NAVIGATE_TO_QR = 4
_S_EXECUTE_QR_TASK = 5
_S_WAIT_AT_QR = 6
_S_ROTATE_TO_NEXT = 7
_S_RETURN_HOME = 9

# QR alt-adımları (mission_fsm QrTaskStep ile aynı). FORMATION ve ALTITUDE
# adımları EVENT_FORMATION_REACHED ile ilerler; o sinyali burada üretiyoruz.
_QR_STEP_FORMATION = 1
_QR_STEP_ALTITUDE = 3

# QrTaskStep (mission_states.py ile aynı).
_STEP_FORMATION = 1
_STEP_MANEUVER = 2
_STEP_ALTITUDE = 3
_STEP_DETACH = 4
_STEP_DONE = 5

# ExecuteManeuver.action maneuver_type.
_MNV_PITCH = 1
_MNV_ROLL = 2
_MNV_YAW = 3
_MNV_PITCH_ROLL = 4

# QR OKUNAMADIĞINDA yapılan arama manevralarında (alçal/yüksel) inilebilecek en
# düşük irtifa. Bu taban YALNIZ aramaya aittir; QR'ın irtifa GÖREVİNE değil.
_SEARCH_ALT_FLOOR_M = 10.0

# QR'ın irtifa değişimi komutu için izinli bant. QR ne derse o uygulanır: komut
# jüriden gelir ve görevin puanlanan kalemidir; tabana yuvarlamak yanlış irtifada
# uçmak (ve o kalemi kaybetmek) demektir. Bant yalnız açıkça hatalı/kötü niyetli
# değerlere (0, negatif, 200) karşı emniyettir.
_ALT_CMD_MIN_M = 5.0
_ALT_CMD_MAX_M = 30.0

# FormationCommand.FORMATION_CUSTOM — jüri dizilişi snapshot'ı (dayatılan tip
# yok); formation_node sağlanan ofsetleri doğrudan kullanır.
_FRM_CUSTOM = 99


@dataclass
class OrchestratorConfig:
    """mission1 orkestratörünün ayarlanabilir parametreleri."""

    default_formation_type: int = 1  # FORMATION_OKBASI
    default_spacing_m: float = 5.0
    wing_alpha_rad: float = math.radians(45.0)
    maneuver_duration_s: float = 3.0
    # Tam sürü boyutu (yapılandırılan dron sayısı). Bir dron ayrılıp aktif
    # sayı bunun altına düşerse formasyon YENİDEN hesaplanmaz (şartname:
    # ayrılınca formasyon düzeltmesi yok). 0 = kontrol kapalı.
    full_agent_count: int = 0
    # --- GOREV 1 UCUS PROFILI (operator karari, 2 Eylul gecesi) -------------
    # Sartname baslangic formasyonunun KORUNMASINI istiyor; bu alanlar o
    # davranisi DEGISTIRMEZ, 0/None birakildiginda kod eskisi gibi calisir.
    # Operator test ucusu icin acik bir profil istedi:
    #   dagitik kalk -> CIZGI kur -> QR1'e git -> gorev -> 180 yaw
    #   -> eve don -> dikey merdiven -> herkes KENDI kalkis noktasina -> in
    # 🔴 gorev_formasyon SABIT bir deger; ileride YKI'den gelecek
    # (YAPILACAKLAR: "ilk formasyon secimi YKI'den"). QR'dan gelen `frm`
    # komutu bunu EZER — sartname yolu her zaman ustte kalir.
    gorev_formasyon: int = 0          # 0 = kapali (CUSTOM kalir), 3 = cizgi
    gorev_aralik_m: float = 7.0
    # Eve donmeden ONCE sürünün topluca dondugu aci. 0 = donme yok.
    donus_yaw_deg: float = 0.0
    # Dagilma oncesi dikey merdiven basamagi. Kuru testte 3 m KALDI (3.29 m),
    # 4 m'den itibaren GECTI; 5 m secildi (5.18 m pay).
    donus_katman_m: float = 5.0
    # 🔴 SADECE DAGILMA BACAGINDA. 180 yaw'dan sonra cizginin uc ucaklari
    # takas ediyor ve KAFA KAFAYA gecmek zorundalar. Olculdu:
    #   her biri 2.0 m/s -> kapanma 4.0 -> frenleme 2.23 m -> kalan 1.77 m
    #   (hard sinir 2.5 m IHLAL; 1 Eylul'de olculen 1.65 m tam buydu)
    #   her biri 1.0 m/s -> kapanma 2.0 -> frenleme 0.56 m -> kalan 3.44 m
    # Diger bacaklarda suru BLOK halinde gidiyor, kapanma sifir -> hiz normal.
    dagilma_hiz_mps: float = 1.0
    # 🔴 FORMASYON KURULUM HIZI — 3 Eylul, operator: "cok hizli yaptilar".
    # Dagitik dizilisten cizgiye gecerken ucaklar ROTA_MAKS_HIZ (3.0 m/s)
    # ile kosuyordu; yollar kesismese de goruntu ve yuk agir. Kurulum tek
    # atimlik bir manevra, hizli olmasinin bir degeri yok.
    # 0.0 = degistirme (dugumun kendi varsayilani).
    gorev_kurulum_hiz_mps: float = 0.0
    # QR okunamazsa okuma irtifasına inme (10m tabanı) ve tetik gecikmesi.
    qr_read_altitude_m: float = 12.0
    qr_recovery_delay_s: float = 8.0
    # QR okunamazsa İRTİFA MERDİVENİ ile tekrar tekrar dener: sürü QR'ın üstünde
    # ÇIPALI kalır (ileri/geri YOK — yatay hareket kamerayı QR'dan kaydırıp
    # okumayı bozuyordu), yalnız yükseklik değişir. Her basamakta uzun süre
    # SABİT durur ki kamera net kare alıp decode edebilsin.
    #   12 m (varsayılan) → 10 m (taban, QR en büyük) → 18 m (geniş açı) → tekrar
    qr_search_step_s: float = 18.0    # her irtifada bu kadar hareketsiz bekle
    qr_search_high_m: float = 18.0    # geniş açı basamağı
    # QR alt-görevi (FORMASYON/İRTİFA) "tamamlandı" ölçütü. Karar MESAFE DEĞİL,
    # YAKINSAMA'dır: hata artık azalmıyor (plato) + dronlar durdu. Yakınsama her
    # koşulda gerçekleştiği için sinyal daima üretilir → görev kilitlenmez. Sıkı
    # bir mesafe eşiğine bağlansaydı rüzgâr/gürültüde hiç tetiklenmeyip görevi
    # öldürebilirdi. Mesafe yalnızca KALİTE kontrolü: aşılırsa uyarı basılır,
    # görev yine de ilerler.
    formation_settle_tol_m: float = 0.5     # aşılırsa uyar (ilerlemeyi durdurma)
    settle_window_ticks: int = 6            # plato penceresi
    settle_improve_eps_m: float = 0.05      # pencerede bu kadar iyileşme yoksa plato
    settle_move_eps_m: float = 0.05         # tick başına hareket ~0 → durdu
    settle_timeout_s: float = 30.0          # yakınsama gelmezse kilitlenme koruması
    # ROTASYONA ÖZEL: dönüşün gerçekten ilerlediğini doğrulayan pay. Kalkıştan
    # hemen sonra sürü çapada kıpırdamadan asılı durur; heading komutu çıksa da
    # dronlar ilk ~1 sn hareket etmez. O anda hata SABİT (kimse kıpırdamıyor) ve
    # hareket SIFIR olduğu için plato+durdu ölçütü sağlanır ve dönüş daha
    # BAŞLAMADAN "tamamlandı" sayılırdı: sürü yarı dönük halde navigasyona geçip
    # aynı anda hem döner hem ilerler, formasyon çökerdi (ölçüldü: ilk rotasyon
    # 1 sn sürüyor, ardından açıklık 12 m'den 3.5 m'ye iniyordu; sonraki
    # rotasyonlar 12-15 sn sürüp şekli koruyor). Hatanın bu kadar DÜŞMÜŞ olmasını
    # şart koşmak sahte yakınsamayı keser; zaten yerinde olan küçük dönüşler
    # formation_settle_tol_m ile ayrıca kabul edilir.
    rotation_improve_margin_m: float = 0.5
    # NAVIGATE_TO_QR varış tespiti: okuyucu (QR'a en yakın) dron QR'a bu
    # mesafeden (m) yakınsa ve birkaç tick stabil kalırsa "vardım" sayılır;
    # mission_fsm 120s yedek timer yerine bu sinyalle EXECUTE_QR_TASK'a geçer.
    # QR 1.5 m genişlikte → eşik QR'ın İÇİNDE olmalı (gevşek eşik "vardım"
    # derken dronu QR'ın dışında bırakır). Kontrol bu eşiğe inemiyorsa eşik
    # gevşetilmez, kontrol düzeltilir.
    qr_arrival_threshold_m: float = 0.3
    # Geçerken değil, OTURMUŞ olsun: 5 tick @5Hz = 1 sn eşik altında kalmalı.
    qr_arrival_stable_ticks: int = 5


@dataclass
class OrchestratorInput:
    """Bir tick'te orkestratöre verilen anlık bağlam."""

    mission_state: int
    qr_step: int
    is_leader: bool
    agent_ids: list
    positions: list          # agent_ids sırasında (x, y, z); [] = bilinmiyor
    centroid: tuple          # (x, y, z) shared NED
    home: tuple              # (x, y, z) shared NED
    qr: object = None        # QRMissionData benzeri; None = QR yok
    time_in_state: float = 0.0  # mevcut MissionState'e girişten beri saniye
    # Sürünün o anki yaw'ı (derece, kuzeyden saat yönü). None = bilinmiyor.
    # YALNIZ kalkış heading'i ve snapshot referansı için; rotasyon/navigasyon
    # heading'i her zaman hedefe göre hesaplanır.
    swarm_yaw_deg: float = None


@dataclass
class FormationTargetCmd:
    """path_planner'a gidecek sürü-seviyesi formasyon hedefi (lider)."""

    formation_type: int
    center: tuple
    heading_deg: float
    spacing_m: float
    agent_ids: list
    offsets: list
    rotate_towards_target: bool = False
    use_current_centroid: bool = False
    use_current_altitude: bool = False
    # Hız tavanı (m/s); 0 = formation_node default'u (3.0). Reshape morph'unu
    # yavaşlatmak için düşük verilir → yavaş yaklaşma → CA kapanma-sönümü küçük.
    max_speed: float = 0.0


@dataclass
class ManeuverCmd:
    """Lokal maneuver_executor'a gidecek manevra (her drone)."""

    maneuver_type: int
    pitch_deg: float
    roll_deg: float
    yaw_deg: float
    hold_after_complete: bool = True
    duration_s: float = 3.0


@dataclass
class DetachCmd:
    """EVENT_MEMBER_DETACH_STARTED olarak yayınlanacak ayrılma (lider)."""

    target_agent_id: int
    detach_wait_s: float = 0.0


@dataclass
class FormationReachedCmd:
    """QR alt-görevi (FORMASYON / İRTİFA) tamamlandı sinyali."""

    max_error_m: float = 0.0
    clean: bool = True
    timed_out: bool = False


@dataclass
class RotationCompletedCmd:
    """Formasyon rotasyonu tamamlandı sinyali (ROTATE_TO_NEXT)."""

    max_error_m: float = 0.0
    clean: bool = True
    timed_out: bool = False


@dataclass
class QrReachedCmd:
    """Okuyucu dron QR'ın üstüne vardığında lider tarafından üretilen sinyal."""

    distance_m: float = 0.0


@dataclass
class _State:
    """Orkestratörün faz/QR zinciri ve eğim takibi için iç durumu."""

    heading_deg: float = 0.0
    formation_type: int = 1
    spacing_m: float = 5.0
    tilt_pitch_deg: float = 0.0
    tilt_roll_deg: float = 0.0
    handled_key: tuple = field(default=None)
    recovery_emitted: bool = False  # bu takılmada alçalma komutu verildi mi
    # Diziliş (formasyon) en az bir kez yayınlandı mı. Kalkışta konumlar
    # SwarmState'e geç düşerse snapshot orada alınamaz ve ilk formasyon komutu
    # ROTATE fazında çıkar; o komut doğrudan hedef heading taşırsa slotlar tek
    # karede döner ve kalkış dizilişi çarpılır. Bu bayrak, öyle bir durumda
    # rotasyondan ÖNCE dizilişi koruyan (heading=0) komutun yayınlanmasını
    # sağlar → heading rampası 0'dan başlar.
    formation_published: bool = False
    # ÜZERİNDE DURDUĞUMUZ QR'ın konumu (x, y). Varışta kaydedilir; QR görevleri
    # ve rotasyon boyunca formasyon merkezi buraya çıpalanır → sürü QR'ın
    # üzerinde kalır, yerinde döner. resolve_ned() bu fazlarda artık SONRAKİ
    # QR'ı gösterdiği için (varışta hedef ilerliyor) ona çıpalanamaz.
    qr_anchor: tuple = field(default=None)
    # KALKIS BASLIGI — bir kez alinir, bir daha degismez (2 Eylul saha olayi).
    # RETURN_HOME basligi bearing(centroid -> home) ile kuruluyordu; suru eve
    # yaklastikca vektor kisaliyor ve yon TANIMSIZLASIP donuyor. Olculdu:
    # merkez (4,4;0,6) -> (0,0;0,0) giderken baslik -106 -> -169 derece,
    # 5 SANIYEDE 63 DERECE. Slot ofsetleri basliga gore donduğu icin 7 m
    # yaricaptaki ucak yay cizerek supuruldu: ylp00 ylp02'nin uzerine gitti,
    # operator PosCtl'e alip elle indirdi, uçak az kalsin bahce teline
    # konuyordu. Eve donuste diziliş DONMEMELI — kalkistaki basligi tasi.
    # None = hic snapshot alinmadi (kalkis fazi hic gorulmedi) -> eski yola dus.
    kalkis_heading_deg: float = field(default=None)
    # KALKIS DIZILISI — agent_id -> (kuzey, dogu, 0), heading=0 cercevesinde.
    # frozen_offsets QR bir formasyon dayatinca SILINIYOR (satir ~958); eve
    # donuste "herkes KENDI kalkis noktasina" diyebilmek icin dizilisin ayri
    # bir kopyasi lazim. Bir kez alinir, bir daha degismez.
    kalkis_ofsetleri: dict = field(default=None)
    # Gorev formasyonu (cfg.gorev_formasyon) bir kez uygulandi mi.
    gorev_formasyon_kuruldu: bool = False
    # RETURN_HOME alt-fazi: 0=yaw, 1=eve don, 2=merdiven, 3=dagil, 4=bitti
    donus_faz: int = 0
    # Alt-fazin BASLADIGI an (time_in_state). Fazlar artik sure ile degil
    # YAKINSAMA ile ilerliyor; bu damga yalniz ZAMAN ASIMI icin.
    donus_faz_t0: float = 0.0
    # Yakinsama olceri "oturdu" dedi mi — bir sonraki tick tuketir. Olcer
    # (_maybe_formation_settled) decide() icinde _phase_key'DEN SONRA
    # kostugu icin sinyal bir tick gecikmeyle islenir (2 Hz'de 0.5 sn).
    donus_settled: bool = False
    # EVE DONUS BASLIGI — RETURN_HOME'a girerken BIR KEZ mandallanir.
    #
    # NIYE BEARING(centroid -> home) VE NIYE BIR KEZ: 2 Eylul'de baslik HER
    # TICK bearing(centroid->home) ile hesaplaniyordu; suru eve yaklastikca
    # vektor kisalip yon tanimsizlasiyor ve 5 SANIYEDE 63 DERECE donuyordu
    # (ylp00 ylp02'nin uzerine gitti). Cozum olarak kalkis basligi tasinmisti
    # ama o da olculdu: kalkis basligi bacak yonuyle alakasiz oldugu icin
    # QR1'deki "180 derece" 2.1 DERECEYE dusuyordu — manevra sessizce hic
    # yapilmiyordu. Dogrusu ikisinin ortasi: vektor EN UZUNKEN (QR1'de,
    # 31 m) bir kez olc, mandalla, bir daha hesaplama.
    donus_heading_deg: float = field(default=None)
    # Varista olculen donus miktari esigin altindaysa yaw fazi ATLANIR.
    donus_yaw_gerekli: bool = False
    # QR irtifa merdiveninde en son yayınlanan basamak (-1 = arama kapalı).
    # Basamak değişince yeni komut yayınlanır; aynı basamakta sürü SABİT durur.
    search_step: int = -1
    # QR alt-görevi yakınsama takibi: hata geçmişi (plato tespiti), önceki
    # konumlar (durdu mu), işlenen adım anahtarı ve adımın başlangıç anı.
    settle_hist: list = field(default_factory=list)
    settle_prev_pos: list = field(default=None)
    settle_key: tuple = field(default=None)
    settle_key_t0: float = 0.0
    settle_done_key: tuple = field(default=None)
    # Adımın İLK ölçülen şekil hatası. Rotasyonun gerçekten ilerleyip
    # ilerlemediğini anlamak için referans: hata bu değerden düşmediyse sürü
    # daha kıpırdamamış demektir (bkz. _settle_signal).
    settle_first_err: float = field(default=None)
    # Son tam-sürü slot ataması (agent_id → ofset). Bir dron ayrıldığında
    # kalanlar bu dondurulmuş slotlarda tutulur; formasyon yeniden dizilmez.
    frozen_offsets: dict = field(default_factory=dict)
    # NAVIGATE varış tespiti: eşik-altı ardışık tick sayacı ve varışın bir kez
    # bildirildiği faz anahtarı (her QR için tek "vardım" sinyali).
    arrival_ticks: int = 0
    arrival_done_key: tuple = field(default=None)
    # Teşhis: NAVIGATE'te en yakın dronun QR'a son ölçülen uzaklığı (m).
    # -1.0 = henüz ölçülmedi. Kontrolün gerçekte kaç metreye indiğini görmek
    # için mission1_node bunu throttle'lı loglar.
    last_qr_distance_m: float = -1.0
    # İrtifa komutunda QR'ın istediği ve sınıra sabitlendikten sonra
    # uygulanan değer (m). İkisi farklıysa sınır-altı ihlal engellenmiştir;
    # mission1_node bunu loglar.
    last_alt_request_m: float = -1.0
    last_alt_applied_m: float = -1.0


class Mission1Orchestrator:
    """Faz+adım+QR → komut çeviricisi (saf mantık)."""

    def __init__(self, config: OrchestratorConfig = None) -> None:
        """Konfig ve boş QR çözücü ile başlatır."""
        self._cfg = config or OrchestratorConfig()
        self._qr_geo = QrGeoResolver()
        # Eve donus faz gecisi notu — node okuyup loglar ve temizler.
        # Ucus kaydinda "faz neden ilerledi" sorusunun tek cevabi bu satir:
        # yakinsama mi, zaman asimi mi. Ikisi cok farkli seyler.
        self._donus_ilerleme_notu = None
        # Başlangıç formasyonu = jüri dizilişi (CUSTOM). OKBAŞI/V/CIZGI yalnız
        # QR 'frm' komutuyla kurulur; kalkışta hiçbir tip DAYATILMAZ.
        self._st = _State(
            formation_type=_FRM_CUSTOM,
            spacing_m=self._cfg.default_spacing_m,
        )

    @property
    def donus_notu(self):
        """Son eve-donus faz gecisi notu; okununca TEMIZLENIR (bir kez loglanir)."""
        not_ = self._donus_ilerleme_notu
        self._donus_ilerleme_notu = None
        return not_

    # --- Dışarıdan besleme (node topic callback'lerinden) --------------------

    def set_next_target(self, valid, lat_deg, lon_deg) -> None:
        """mission_fsm'in çözdüğü sıradaki hedefin konumunu yükler."""
        self._qr_geo.set_target(valid, lat_deg, lon_deg)

    def set_origin(self, lat_deg, lon_deg) -> None:
        """Paylaşılan NED origin'ini (SwarmOrigin) günceller."""
        self._qr_geo.set_origin(lat_deg, lon_deg)

    @property
    def qr_ready(self) -> bool:
        """QR konumları NED'e çözülebilir durumdaysa True."""
        return self._qr_geo.ready

    @property
    def qr_distance_m(self) -> float:
        """Navigasyonda en yakın dronun QR'a son uzaklığı (-1 = yok)."""
        return self._st.last_qr_distance_m

    @property
    def altitude_clamped(self) -> tuple | None:
        """QR'ın istediği irtifa banda sığdırıldıysa (istenen, uygulanan)."""
        req = self._st.last_alt_request_m
        app = self._st.last_alt_applied_m
        if req >= 0.0 and abs(app - req) > 1e-6:
            return (req, app)
        return None

    # --- Ana karar -----------------------------------------------------------

    def decide(self, inp: OrchestratorInput) -> list:
        """Bu tick'te icra edilecek komut listesini döner (çoğu tick boş)."""
        cmds = []

        # Sürü durumu henüz gelmediyse (aktif ajan listesi boş) komut üretme.
        # Boş agent_ids ile formasyon slot ataması compute_slot_offsets'te
        # total=0 -> ValueError veriyordu (SwarmState geç/boş geldiğinde çökme).
        if not inp.agent_ids:
            return cmds

        # EVE DONUS ALT-FAZI — tick basina BIR KEZ ilerletilir ve
        # _phase_key'DEN ONCE calisir ki yeni faz ayni tick'te yayinlansin.
        if inp.mission_state == _S_RETURN_HOME:
            self._donus_ilerlet(inp)
        elif self._st.donus_heading_deg is not None:
            self._donus_sifirla()

        # QR çözülemiyorsa: okumayı kolaylaştırmak için bir kez alçal.
        recovery = self._maybe_qr_recovery(inp)
        if recovery is not None:
            cmds.append(recovery)

        # Faz komutu (emit-once). Faz işlenemiyorsa (origin/tablo yok) atlar.
        key = self._phase_key(inp)
        if key != self._st.handled_key:
            result = self._handle(inp)
            if result is not None:
                self._st.handled_key = key
                cmds.extend(result)
                if any(isinstance(c, FormationTargetCmd) for c in result):
                    self._st.formation_published = True

        # Teşhis: QR'a mesafe HER FAZDA güncellenir. Eskiden yalnız NAVIGATE'te
        # yazılıyordu; diğer fazlarda son değer DONUP kalıyor ve "sürü QR'ın
        # üstünde" gibi yanıltıcı bir sabit gösteriyordu (görev/rotasyonda sürü
        # QR'dan kaysa bile fark edilmiyordu).
        self._update_qr_distance(inp)

        # Varış tespiti (her tick): okuyucu dron QR'ın üstüne gelince bir kez
        # "vardım" sinyali; mission_fsm bunu NAVIGATE'ten çıkmak için kullanır.
        arrival = self._maybe_qr_arrival(inp)
        if arrival is not None:
            cmds.append(arrival)

        # QR alt-görevi (formasyon/irtifa) yakınsadı mı → "kuruldu" sinyali.
        # Bu sinyal olmadan mission_fsm qr_step'i ilerletmez (manevra başlamaz).
        settled = self._maybe_formation_settled(inp)
        if settled is not None:
            cmds.append(settled)

        if not inp.is_leader:
            return [c for c in cmds if isinstance(c, ManeuverCmd)]
        return cmds

    def _update_qr_distance(self, inp: OrchestratorInput) -> None:
        """En yakın dronun ilgili QR'a mesafesini her tick günceller (teşhis)."""
        if not inp.positions:
            return
        if inp.mission_state == _S_NAVIGATE_TO_QR:
            ref = self._qr_geo.resolve_ned()
            ref = None if ref is None else (ref[0], ref[1])
        else:
            ref = self._st.qr_anchor
        if ref is None:
            return
        self._st.last_qr_distance_m = min(
            math.hypot(p[0] - ref[0], p[1] - ref[1]) for p in inp.positions
        )

    def _maybe_qr_arrival(self, inp: OrchestratorInput):
        """Navigasyonda okuyucu dron QR'a varınca QrReachedCmd üretir."""
        # NAVIGATE dışındayken varış defteri SIFIRLANIR: her yeni navigasyon
        # bacağı temiz sayfayla başlar. Böylece kaç QR olursa olsun (ve aynı
        # QR'a tekrar gelinse bile) her varış yeniden bildirilebilir.
        if inp.mission_state != _S_NAVIGATE_TO_QR:
            self._st.arrival_ticks = 0
            self._st.arrival_done_key = None
            return None
        if not inp.is_leader:
            self._st.arrival_ticks = 0
            return None
        ned = self._qr_geo.resolve_ned()
        if ned is None or not inp.positions:
            return None
        # Emit-once anahtarı HEDEF QR'ın konumudur, faz değil. Faz anahtarı
        # (state, qr_step, qr_seq) iki ayrı QR'a gidişte AYNI çıkabiliyordu
        # (ikisinde de NAVIGATE + QR henüz okunmamış) → ikinci QR'a varış
        # "zaten bildirildi" sanılıp bastırılıyor, sürü QR'ın üstünde EXECUTE'a
        # geçemeden timeout'a düşüyordu (yaşanan bug: yalnız ilk QR okunabildi).
        key = (round(ned[0], 1), round(ned[1], 1))
        if self._st.arrival_done_key == key:
            return None
        d = min(
            math.hypot(p[0] - ned[0], p[1] - ned[1])
            for p in inp.positions
        )
        self._st.last_qr_distance_m = d
        if d <= self._cfg.qr_arrival_threshold_m:
            self._st.arrival_ticks += 1
        else:
            self._st.arrival_ticks = 0
        if self._st.arrival_ticks >= self._cfg.qr_arrival_stable_ticks:
            self._st.arrival_done_key = key
            # Üzerinde durduğumuz QR: görevler ve rotasyon boyunca formasyon
            # merkezi buraya çıpalanacak (sürü QR'dan kaymasın, yerinde dönsün).
            self._st.qr_anchor = (float(ned[0]), float(ned[1]))
            return QrReachedCmd(distance_m=d)
        return None

    def _maybe_formation_settled(self, inp: OrchestratorInput):
        """QR alt-görevi (FORMASYON/İRTİFA) tamamlanınca bir kez sinyal üretir."""
        step = int(inp.qr_step)
        # Aynı yakınsama ölçütü İKİ fazda kullanılır — ikisinde de soru aynı:
        # "dronlar komut edilen heading'deki slotlarına gitmeyi bitirdi mi?"
        #
        #   ROTATE_TO_NEXT  → dönüş tamamlandı mı → EVENT_ROTATION_COMPLETED
        #   EXECUTE_QR_TASK → formasyon/irtifa oturdu mu → EVENT_FORMATION_REACHED
        #
        # Rotasyon sinyalini de üreten kimse yoktu: mission_fsm hiçbir ölçüm
        # yapmaz, yalnız event dinler. Sinyal gelmeyince dönüşün BİTİP bitmediğine
        # bakmadan 30 sn'lik timeout'la ilerliyordu → dönüş herhangi bir sebeple
        # tamamlanmazsa sürü YARI DÖNÜK halde QR'a uçuyor, kimse fark etmiyordu
        # (şartname rotasyonu puanlıyor). Artık sistem kendi işini doğruluyor.
        rotating = inp.mission_state == _S_ROTATE_TO_NEXT
        qr_task = (
            inp.mission_state == _S_EXECUTE_QR_TASK
            and step in (_QR_STEP_FORMATION, _QR_STEP_ALTITUDE)
        )
        # RETURN_HOME'da da yakınsama izlenir: sürü home'da oturunca
        # FormationReachedCmd üretilir → mission_fsm EVENT_FORMATION_REACHED alıp
        # "eve vardı" der ve İNER. Bu sinyal üretilmezse sürü rastgele yere iner
        # (erken landing) ya da sert zaman aşımına kadar boşuna asılı kalır.
        returning = inp.mission_state == _S_RETURN_HOME
        if not (rotating or qr_task or returning):
            self._st.settle_key = None
            self._st.settle_hist = []
            self._st.settle_prev_pos = None
            self._st.settle_first_err = None
            return None

        key = self._phase_key(inp)
        if self._st.settle_done_key == key:
            return None
        if not inp.positions or len(inp.positions) != len(inp.agent_ids):
            return None

        # Adım değişti → yakınsama takibini sıfırla (önceki adımın geçmişi
        # yeni adımı anında "yakınsamış" göstermesin).
        if self._st.settle_key != key:
            self._st.settle_key = key
            self._st.settle_key_t0 = inp.time_in_state
            self._st.settle_hist = []
            self._st.settle_prev_pos = None
            self._st.settle_first_err = None

        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        if offsets is None:
            return None

        # Şekil hatası: dronun centroid'e göre GERÇEK göreli konumu ile atanan
        # slot ofseti (heading ile döndürülmüş) arasındaki fark.
        #
        # ÖNEMLİ: slot ofsetleri formasyon MERKEZİNE göre tanımlıdır, ama
        # ofsetlerin kendi ortalaması merkezle çakışmaz (Ok Başı'nda uç öndedir
        # → ofset ortalaması ≈ 2.8 m geride). Ham ofsetle centroid-göreli konumu
        # karşılaştırmak bu farkı SABİT bir yapay hata olarak üretir (formasyon
        # kusursuzken bile). Bu yüzden ofsetler kendi ortalamalarına indirgenir
        # → centroid-to-centroid karşılaştırma, gerçek şekil hatası ölçülür.
        heading_rad = math.radians(self._st.heading_deg)
        cx, cy = inp.centroid[0], inp.centroid[1]
        n_off = len(offsets)
        mx = sum(o[0] for o in offsets) / n_off
        my = sum(o[1] for o in offsets) / n_off
        max_err = 0.0
        for (px, py, _pz), off in zip(inp.positions, offsets):
            dx, dy = rotate_offset(off[0] - mx, off[1] - my, heading_rad)
            err = math.hypot((px - cx) - dx, (py - cy) - dy)
            max_err = max(max_err, err)

        # Durdu mu: tick başına konum değişimi (~0 ise hareket bitti).
        prev = self._st.settle_prev_pos
        if prev is not None and len(prev) == len(inp.positions):
            max_move = max(
                math.hypot(p[0] - q[0], p[1] - q[1])
                for p, q in zip(inp.positions, prev)
            )
        else:
            max_move = float('inf')
        self._st.settle_prev_pos = [
            (float(p[0]), float(p[1])) for p in inp.positions
        ]

        if self._st.settle_first_err is None:
            self._st.settle_first_err = max_err

        hist = self._st.settle_hist
        hist.append(max_err)
        win = max(2, int(self._cfg.settle_window_ticks))
        if len(hist) > win:
            del hist[:-win]

        plateau = (
            len(hist) >= win
            and (max(hist) - min(hist)) <= self._cfg.settle_improve_eps_m
        )
        stopped = max_move <= self._cfg.settle_move_eps_m
        elapsed = inp.time_in_state - self._st.settle_key_t0
        timed_out = elapsed >= self._cfg.settle_timeout_s

        # ROTASYONDA EK ŞART: dönüşün gerçekten ilerlemiş olması.
        # plato+durdu tek başına, sürü henüz KIPIRDAMADIĞI için de sağlanır
        # (kalkış çapasında asılı dururken hata sabittir) → dönüş başlamadan
        # "tamamlandı" denirdi. Hatanın düşmüş olmasını ya da zaten tolerans
        # içinde olmasını (dönecek bir şey yoktu) şart koşuyoruz. Diğer fazlar
        # (QR görevi, eve dönüş) bu ek şarttan etkilenmez.
        progressed = True
        if rotating:
            first_err = self._st.settle_first_err
            improved = (
                first_err is not None
                and max_err <= first_err - self._cfg.rotation_improve_margin_m
            )
            already_good = max_err <= self._cfg.formation_settle_tol_m
            progressed = improved or already_good

        if not ((plateau and stopped and progressed) or timed_out):
            return None

        self._st.settle_done_key = key
        self._st.settle_hist = []
        self._st.settle_prev_pos = None
        self._st.settle_first_err = None
        if rotating:
            return RotationCompletedCmd(
                max_error_m=max_err,
                clean=max_err <= self._cfg.formation_settle_tol_m,
                timed_out=timed_out,
            )
        if returning:
            # 🔴 EVE DONUSTE BU SINYAL ALT-FAZI ILERLETIR, "EVE VARDIK"
            # DEMEZ. mission_fsm `event_formation_reached` gorunce DOGRUDAN
            # LANDING'e geciyor (_from_return_home). Sinyal her alt-fazda
            # uretilseydi suru yaw fazi oturur oturmaz -- yani HALA QR1'in
            # ustunde, evden 31 m uzakta -- inise gecerdi.
            self._st.donus_settled = True
            son_faz = (int(self._st.donus_faz) >= 4
                       or self._st.kalkis_ofsetleri is None)
            if not son_faz:
                return None
        return FormationReachedCmd(
            max_error_m=max_err,
            clean=max_err <= self._cfg.formation_settle_tol_m,
            timed_out=timed_out,
        )

    def _maybe_qr_recovery(self, inp: OrchestratorInput):
        """QR çözülemiyorsa İRTİFA MERDİVENİ ile tekrar tekrar dener."""
        stuck = (
            inp.mission_state == _S_EXECUTE_QR_TASK and inp.qr_step == 0
        )
        if not stuck:
            self._st.search_step = -1
            self._st.recovery_emitted = False
            return None

        elapsed = inp.time_in_state - self._cfg.qr_recovery_delay_s
        if elapsed < 0.0:
            return None
        step_s = max(1.0, self._cfg.qr_search_step_s)
        step = int(elapsed / step_s) % 3
        if step == self._st.search_step:
            return None  # aynı basamak sürüyor → sürü SABİT, yeni komut yok

        read_alt = max(self._cfg.qr_read_altitude_m, _SEARCH_ALT_FLOOR_M)
        ladder = (
            read_alt,
            _SEARCH_ALT_FLOOR_M,
            max(self._cfg.qr_search_high_m, _SEARCH_ALT_FLOOR_M),
        )
        alt = ladder[step]

        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        if offsets is None:
            return None

        # QR ÇIPASI: ÜZERİNDE DURDUĞUMUZ QR (qr_anchor) — hedef QR değil!
        # resolve_ned() burada SONRAKİ QR'ı gösterir: varış anında hedef zaten
        # ilerlemiştir. Ona çıpalanınca kurtarma, okunamayan QR'ı bırakıp sürüyü
        # bir sonraki QR'a UÇURUYORDU (yaşanan bug: QR1 okunamadı → sürü 40 m
        # ötedeki QR3'e gidip onu okudu → QR1'in görevi hiç yapılmadı).
        # Kurtarmanın amacı, üzerinde durduğumuz QR'ı okuyabilmek için orada
        # irtifa denemektir; sürü o QR'dan AYRILMAMALIDIR.
        ned = self._st.qr_anchor
        if ned is not None:
            ax, ay, _az = self._anchor_nearest_to_qr(
                inp, ned, offsets, math.radians(self._st.heading_deg)
            )
            center = (ax, ay, -alt)
            use_cur_centroid = False
        else:
            center = (inp.centroid[0], inp.centroid[1], -alt)
            use_cur_centroid = True

        self._st.search_step = step
        self._st.recovery_emitted = True
        return FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=center,
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=use_cur_centroid,
            use_current_altitude=False,
        )

    # --- Yardımcılar ---------------------------------------------------------

    def _phase_key(self, inp: OrchestratorInput) -> tuple:
        """Emit-once için (state, step, qr_seq, donus_faz) anahtarı.

        🔴 donus_faz ANAHTARA GIRMEK ZORUNDA. RETURN_HOME tek bir
        mission_state; alt fazlar (yaw -> ev -> merdiven -> dagilma)
        anahtarda gorunmezse emit-once ilkinden sonrasini BASTIRIR ve
        suru ilk fazda asili kalir — hicbir yerde hata gorunmeden.
        """
        qr_seq = int(getattr(inp.qr, 'qr_seq', 0)) if inp.qr else 0
        faz = (self._donus_fazi(inp)
               if inp.mission_state == _S_RETURN_HOME else 0)
        return (inp.mission_state, inp.qr_step, qr_seq, faz)

    def _handle(self, inp: OrchestratorInput):
        """Faza göre ilgili işleyiciye yönlendirir."""
        s = inp.mission_state
        if s == _S_SYNCHRONIZED_TAKEOFF:
            return self._on_takeoff(inp)
        if s == _S_ROTATE_TO_NEXT:
            return self._on_rotate(inp)
        if s == _S_NAVIGATE_TO_QR:
            return self._on_navigate(inp)
        if s == _S_EXECUTE_QR_TASK:
            return self._on_execute(inp)
        if s == _S_WAIT_AT_QR:
            # BEKLEME sırasında EĞİK POZU KORU. Şartname md.8: manevradan
            # sonra yeni formasyon/manevra gelene dek eğik poz korunmalı.
            # Bu faz eskiden hiç işlenmiyordu (return []): manevra QR'ında
            # wait_s > 0 ise EXECUTE'tan WAIT_AT_QR'a geçiliyor ve orchestrator
            # burada komut ÜRETMİYORDU. Sonuç: maneuver_executor hareketi
            # bırakır (hold_after_complete=False), formation eğik pozu ise bu
            # fazda gelmediği için dron BEKLEME BOYUNCA DÜZLEŞİYORDU; eğik poz
            # ancak bekleme bitip ROTATE'e geçince geri geliyordu (ölçüldü:
            # manevra sonrası ~20 sn düz kalıp sonra tekrar eğiliyordu —
            # "pitch → düz → pitch"). _exec_hold_tilt eğik ofsetli formasyon
            # komutu üretir; eğim yoksa zaten [] döner, manevrasız QR'da etkisi
            # olmaz. Emit-once mimarisi komutu bir kez üretir (spam yok).
            return self._exec_hold_tilt(inp)
        if s == _S_RETURN_HOME:
            return self._on_return_home(inp)
        return []

    def _kalkis_heading(self, inp: OrchestratorInput) -> float:
        """Sürünün o anki yaw'ı (derece); bilinmiyorsa 0 (eski davranış)."""
        if inp.swarm_yaw_deg is None:
            return 0.0
        return float(inp.swarm_yaw_deg)

    @staticmethod
    def _ters_dondur(offsets, heading_deg: float):
        """Ofsetleri -heading kadar döndürür (heading uygulanınca sadeleşir)."""
        if not heading_deg:
            return offsets
        th = math.radians(-heading_deg)
        return [
            (*rotate_offset(o[0], o[1], th), o[2]) for o in offsets
        ]

    def _bearing_deg(self, frm, to) -> float:
        """İki nokta arası yön açısı (kuzeyden saat yönüne, derece)."""
        dn = to[0] - frm[0]
        de = to[1] - frm[1]
        return math.degrees(math.atan2(de, dn))

    def _anchor_nearest_to_qr(self, inp, ned, offsets, heading_rad):
        """Formasyonu, QR'a en yakın dron QR'ın üstüne gelecek şekilde kaydırır."""
        if not inp.positions or not offsets:
            return (ned[0], ned[1], inp.centroid[2])
        ridx = min(
            range(len(inp.positions)),
            key=lambda i: math.hypot(
                inp.positions[i][0] - ned[0], inp.positions[i][1] - ned[1]
            ),
        )
        rox, roy = rotate_offset(offsets[ridx][0], offsets[ridx][1], heading_rad)
        return (ned[0] - rox, ned[1] - roy, inp.centroid[2])

    def _assign(self, formation_type, spacing, center, heading_deg,
                inp: OrchestratorInput):
        """Slot ofsetlerini üretir; ATAMA rijit, EĞİM üstüne uygulanır."""
        if self._st.frozen_offsets:
            flat = [
                self._st.frozen_offsets.get(int(a), (0.0, 0.0, 0.0))
                for a in inp.agent_ids
            ]
            return self._tilted(flat)
        if int(formation_type) == _FRM_CUSTOM:
            # Henüz QR 'frm' gelmedi → jüri dizilişini snapshot'la, tip DAYATMA.
            flat = self._snapshot_offsets(inp)
            if flat is None:
                return None
            # SNAPSHOT REFERANSI: kuzey değil, sürünün KENDİ yönü.
            # _snapshot_offsets ofsetleri dünya çerçevesinde verir. Bunlar
            # heading=0 (kuzey) referansı sayılarak saklanırsa, ilk rotasyonda
            # heading hedefe (örn. 87°) çevrildiğinde diziliş SIFIRDAN o açıya
            # döner — ölçüldü: yerde kuzey-güney duran çizgi (eksen 1.1°)
            # kalkışta 87°'ye dönüp dikleşiyordu. Oysa sürü zaten 79°'ye
            # bakıyordu; dönmesi gereken yalnızca aradaki 8°.
            # Ofsetler -yaw döndürülüp saklanınca referans sürünün kendi yönü
            # olur: kalkışta heading=yaw verilir (iki döndürme sadeleşir,
            # diziliş aynen korunur), rotasyonda ise yalnız hedefle arasındaki
            # FARK kadar döner. Diziliş rastgele olsa da çalışır — hiçbir
            # sabit yön/konum varsayımı yok, yaw telemetriden okunur.
            flat = self._ters_dondur(flat, self._kalkis_heading(inp))
        else:
            # Taban DÜZ üretilir (tilt=0); eğim aşağıda uygulanır. Atama maliyeti
            # de düz slotlarla hesaplanır — eğim dronların hangi slota gideceğini
            # değiştirmemeli, yalnız o slotun yüksekliğini.
            flat = build_slot_assignment(
                formation_type,
                inp.agent_ids,
                inp.positions,
                center,
                spacing,
                self._cfg.wing_alpha_rad,
                heading_rad=math.radians(heading_deg),
            )
        self._st.frozen_offsets = {
            int(a): off for a, off in zip(inp.agent_ids, flat)
        }
        return self._tilted(flat)

    def _tilted(self, flat_offsets):
        """Düz ofsetlere mevcut eğimi (pitch/roll) uygular."""
        pitch = self._st.tilt_pitch_deg
        roll = self._st.tilt_roll_deg
        if pitch == 0.0 and roll == 0.0:
            return flat_offsets
        return apply_tilt(flat_offsets, pitch, roll)

    def _hold_center(self, inp: OrchestratorInput, offsets, heading_deg):
        """Sürüyü yerinde tutan formasyon merkezini döndürür."""
        if self._st.qr_anchor is not None and inp.positions and offsets:
            ned = (self._st.qr_anchor[0], self._st.qr_anchor[1])
            return self._anchor_nearest_to_qr(
                inp, ned, offsets, math.radians(heading_deg)
            )
        return self._hold_centroid(inp, offsets, heading_deg)

    def _hold_centroid(self, inp: OrchestratorInput, offsets, heading_deg):
        """Sürünün CENTROID'i yerinde kalacak formasyon merkezini döndürür."""
        if not offsets:
            return inp.centroid
        n = len(offsets)
        mx = sum(o[0] for o in offsets) / n
        my = sum(o[1] for o in offsets) / n
        dx, dy = rotate_offset(mx, my, math.radians(heading_deg))
        return (inp.centroid[0] - dx, inp.centroid[1] - dy, inp.centroid[2])

    def _snapshot_offsets(self, inp: OrchestratorInput):
        """Mevcut dizilişi baz ofset olarak alır (heading=0 çerçevesi)."""
        n_full = self._cfg.full_agent_count or len(inp.agent_ids)
        if (not inp.positions
                or len(inp.positions) != len(inp.agent_ids)
                or len(inp.agent_ids) < n_full):
            return None
        cx, cy, _cz = inp.centroid
        return [
            (float(p[0]) - cx, float(p[1]) - cy, 0.0)
            for p in inp.positions
        ]

    # --- Faz işleyicileri ----------------------------------------------------

    def _hedefsiz_tut(self, inp: OrchestratorInput):
        """Hedef bilinmiyorken "OLDUGUN YERDE KAL" komutu uretir.

        🔴 SESSIZ SETPOINT BOSLUGU — 2 Eylul 2026, sahada olculdu.

        _on_rotate ve _on_navigate, QR konumu cozulemeyince `return None`
        diyordu. Sonuc bir "bekleme" degil, KOMUT URETEN KIMSENIN OLMAMASIYDI:
            mission_fsm: "Ilk hedef QR1 konum tabloda yok"  -> route_unknown
            -> orkestrator hicbir sey uretmez
            -> formation_node'un yayinlayacagi komut yok
            -> collision_avoidance tanisi: passthrough=0 (ucus boyunca)
            -> px4_bridge'e setpoint gitmez -> PX4 OFFBOARD'i birakir
            -> agent_fsm: "FAILSAFE SEBEBI: ... offboard=False"
        2 Eylul gecesi dort ucusun ucu boyle bitti. Operator "kalktilar ve
        asili kaldilar, bir sey yapmadilar" diye bildirdi — gordugu sey
        tam olarak buydu; failsafe de ayni kokten geliyordu, pilden DEGIL
        (log: healthy=True pil=15.33V/13.80V).

        Cozum bir gorev degil bir GUVENLIK TABANI: hedef yoksa suru mevcut
        merkezinde ve mevcut irtifasinda formasyonu KORUR. Setpoint akisi
        kesilmez, OFFBOARD yasar, ucak kontrol altinda asili kalir ve
        NAVIGATE zaman asimi RETURN_HOME'a goturur. Yani "hicbir sey
        yapmamak" yerine "bilerek beklemek".

        _on_takeoff ile ayni sablon: snapshot cercevesi, mevcut centroid,
        mevcut irtifa, hedefe donme YOK.
        """
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            0.0, inp,
        )
        if offsets is None:
            return None
        heading = self._kalkis_heading(inp)
        self._st.heading_deg = heading
        if self._st.kalkis_heading_deg is None:
            # Kalkis fazi kacirildiysa (gorev NAVIGATE'te devralindi) ilk
            # hedefsiz bekleme anini referans al — donmeyen bir baslik,
            # hic olmamasindan iyi.
            self._st.kalkis_heading_deg = heading
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=self._hold_center(inp, offsets, heading),
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=True,
        )]

    def _on_takeoff(self, inp: OrchestratorInput):
        """SYNCHRONIZED_TAKEOFF: yerdeki dizilişi snapshot'lar (jüri koyduğu gibi)."""
        # _assign, tip CUSTOM olduğu için jüri dizilişini snapshot'lar.
        # Tam sürü/konum yoksa None → emit-once tetiklenmez, sonraki tick
        # tekrar denenir (eksik listeyle dondurmak dizilişi çökertirdi).
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            0.0, inp,
        )
        if offsets is None:
            return None
        # Ofsetler _assign'da sürünün yaw'ına göre saklandı; komutun heading'i
        # de aynı olmalı ki iki döndürme sadeleşsin ve diziliş korunsun.
        heading = self._kalkis_heading(inp)
        self._st.heading_deg = heading
        if self._st.kalkis_heading_deg is None:
            self._st.kalkis_heading_deg = heading   # eve donuste kullanilacak
        if self._st.kalkis_ofsetleri is None and self._st.frozen_offsets:
            # _assign az once frozen_offsets'i doldurdu. QR bir formasyon
            # dayatinca o silinecek; kalkis dizilisinin AYRI kopyasi burada
            # kaliyor ki eve donuste herkes KENDI noktasina inebilsin.
            self._st.kalkis_ofsetleri = dict(self._st.frozen_offsets)
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=self._hold_center(inp, offsets, heading),
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=True,
        )]

    def _gorev_formasyonunu_uygula(self):
        """Kalkistan sonra gorev formasyonunu bir kez kurar (cfg ile acilir).

        Sartname baslangic formasyonunun korunmasini istiyor; bu yol
        VARSAYILAN OLARAK KAPALI (gorev_formasyon=0 -> CUSTOM kalir).
        Operator test ucusu icin acikca istedi. QR'dan `frm` gelirse o
        EZER — sartname yolu her zaman ustte.
        """
        if self._st.gorev_formasyon_kuruldu:
            return
        tip = int(self._cfg.gorev_formasyon or 0)
        if tip <= 0:
            self._st.gorev_formasyon_kuruldu = True   # bir daha bakma
            return
        self._st.formation_type = tip
        self._st.spacing_m = float(self._cfg.gorev_aralik_m)
        # frozen_offsets SILINMELI: dolu kalirsa _assign kalkis dizilisini
        # geri verir ve formasyon HIC kurulmaz (sessiz).
        self._st.frozen_offsets = {}
        self._st.gorev_formasyon_kuruldu = True

    def _on_rotate(self, inp: OrchestratorInput):
        """ROTATE_TO_NEXT: formasyonu bir sonraki QR'a döndürür (merkez sabit)."""
        self._gorev_formasyonunu_uygula()
        ned = self._qr_geo.resolve_ned()
        if ned is None:
            return self._hedefsiz_tut(inp)   # bkz. _hedefsiz_tut
        heading = self._bearing_deg(inp.centroid, ned)

        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            heading, inp,
        )
        if offsets is None:
            return None

        cmds = []
        if not self._st.formation_published:
            # Snapshot çerçevesi: referans sürünün yaw'ı (bkz. _assign).
            ilk_h = self._kalkis_heading(inp)
            cmds.append(FormationTargetCmd(
                formation_type=self._st.formation_type,
                center=self._hold_center(inp, offsets, ilk_h),
                heading_deg=ilk_h,        # snapshot çerçevesi → diziliş korunur
                spacing_m=self._st.spacing_m,
                agent_ids=list(inp.agent_ids),
                offsets=offsets,
                rotate_towards_target=False,
                use_current_centroid=True,
                use_current_altitude=True,
                max_speed=float(self._cfg.gorev_kurulum_hiz_mps),
            ))

        self._st.heading_deg = heading
        # ROTASYONDA SABİT MERKEZ: _hold_center (QR çıpası) yerine _hold_centroid.
        # _anchor_nearest_to_qr merkezi "QR - döndür(okuyucu_ofset, heading)"
        # ile kurar; heading slew'lenirken bu vektör döndüğü için merkez QR
        # etrafında YAY çizer (ölçüldü: 159° dönüşte centroid 8.6 m KAYDI —
        # şartname sabit-merkez rotasyon ister). _hold_centroid merkezi mevcut
        # centroid'e göre tutar → centroid sabit kalır, sürü yerinde döner.
        # Geçiş lurch'suz: centroid mevcut konumlardan hesaplandığından ilk
        # tick hedefleri dronların bulunduğu yere birebir denk gelir.
        # QR görevlerinde (formasyon/irtifa) _hold_center AYNEN kalır — orada
        # sürünün QR'ın üstünde durması gerekir; yalnız rotasyon değişti.
        cmds.append(FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=self._hold_centroid(inp, offsets, heading),
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            max_speed=float(self._cfg.gorev_kurulum_hiz_mps),
            rotate_towards_target=True,
            use_current_centroid=True,
            use_current_altitude=True,
        ))
        return cmds

    def _on_navigate(self, inp: OrchestratorInput):
        """NAVIGATE_TO_QR: OKUYUCU dronu QR'ın üstüne çıpalar (irtifayı korur)."""
        ned = self._qr_geo.resolve_ned()
        if ned is None:
            return self._hedefsiz_tut(inp)   # bkz. _hedefsiz_tut
        heading = self._bearing_deg(inp.centroid, ned)
        self._st.heading_deg = heading
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            heading, inp,
        )
        if offsets is None:
            return None
        center = self._anchor_nearest_to_qr(
            inp, ned, offsets, math.radians(heading)
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=center,
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=False,
            use_current_altitude=False,
        )]

    def _on_execute(self, inp: OrchestratorInput):
        """EXECUTE_QR_TASK: aktif QR alt-adımına göre komut üretir."""
        step = inp.qr_step
        # Adımlar bittiğinde (DONE) eğik poz varsa onu koru — manevradan
        # sonra irtifa/detach adımı yoksa ya da wait sürerken düzleşmesin.
        if step == _STEP_DONE:
            return self._exec_hold_tilt(inp)
        qr = inp.qr
        if qr is None:
            return []
        if step == _STEP_FORMATION:
            return self._exec_formation(inp, qr)
        if step == _STEP_MANEUVER:
            return self._exec_maneuver(inp, qr)
        if step == _STEP_ALTITUDE:
            return self._exec_altitude(inp, qr)
        if step == _STEP_DETACH:
            return self._exec_detach(qr)
        return []

    def _exec_formation(self, inp, qr):
        """Formasyon değişimi: yeni tip/aralık, eğim sıfırlanır."""
        self._st.tilt_pitch_deg = 0.0
        self._st.tilt_roll_deg = 0.0
        self._st.formation_type = int(getattr(qr, 'formation_type', 0)) \
            or self._st.formation_type
        spacing = float(getattr(qr, 'spacing_m', 0.0))
        if spacing > 0.0:
            self._st.spacing_m = spacing
        # Yeni formasyon → jüri-diziliş snapshot'ını bırak; yeni şekli
        # (OKBAŞI/V/CIZGI) build_slot_assignment ile yeniden kur ve dondur.
        self._st.frozen_offsets = {}
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=self._hold_center(inp, offsets, self._st.heading_deg),
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=True,
            # Reshape morph'unu yavaşlat: dronlar yeni slota YAVAŞ gitsin →
            # düşük kapanma hızı → CA sönüm terimi (c_damp·c) küçük → savrulma az.
            # DENENDİ, GERİ ALINDI: seyir hızına (2.0) çıkarmak geçişin ilk
            # 5 saniyesini iki katı kötüleştirdi (slot hatası 2.42 → 10.19 m).
            # Dronlar slota fırlayıp savruluyor; bu 1.0 değeri bilinçli.
            max_speed=1.0,
        )]

    def _exec_maneuver(self, inp, qr):
        """Pitch/roll/yaw manevrası: geçici eğilme, sonra formasyon devralır."""
        pitch = float(getattr(qr, 'pitch_deg', 0.0))
        roll = float(getattr(qr, 'roll_deg', 0.0))
        yaw = float(getattr(qr, 'yaw_deg', 0.0))
        self._st.tilt_pitch_deg = pitch
        self._st.tilt_roll_deg = roll
        mtype = _maneuver_type(pitch, roll, yaw)
        return [ManeuverCmd(
            maneuver_type=mtype,
            pitch_deg=pitch,
            roll_deg=roll,
            yaw_deg=yaw,
            hold_after_complete=False,
            duration_s=self._cfg.maneuver_duration_s,
        )]

    def _exec_hold_tilt(self, inp: OrchestratorInput):
        """Adımlar bitince eğik pozu formasyon ofsetiyle korur (model B)."""
        if (self._st.tilt_pitch_deg == 0.0
                and self._st.tilt_roll_deg == 0.0):
            return []
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=self._hold_center(inp, offsets, self._st.heading_deg),
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=True,
        )]

    def _exec_altitude(self, inp, qr):
        """İrtifa değişimi: XY korunur, Z hedefe (eğik poz korunur)."""
        requested_alt = float(getattr(qr, 'altitude_agl_m', 0.0))
        alt_agl = min(max(requested_alt, _ALT_CMD_MIN_M), _ALT_CMD_MAX_M)
        self._st.last_alt_request_m = requested_alt
        self._st.last_alt_applied_m = alt_agl
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m,
            (inp.centroid[0], inp.centroid[1], -alt_agl),
            self._st.heading_deg, inp,
        )
        hold = self._hold_center(inp, offsets, self._st.heading_deg)
        center = (hold[0], hold[1], -alt_agl)
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=center,
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=False,
        )]

    def _exec_detach(self, qr):
        """Sürüden birey ayırma: hedef ID + bekleme süresiyle DetachCmd."""
        target = int(getattr(qr, 'target_agent_id', 0))
        if target <= 0:
            return []
        wait_s = float(getattr(qr, 'detach_wait_s', 0.0))
        return [DetachCmd(target_agent_id=target, detach_wait_s=wait_s)]

    # --- RETURN_HOME alt fazlari (operator profili, 2 Eylul gecesi) --------
    # Fazlar SURE ile ilerliyor, varis tespitiyle degil. Gerekce: varis
    # tespiti (yakinsama) QR alt-gorevleri icin yazilmis ve mission_fsm'e
    # sinyal uretiyor; buraya baglamak o zincire ikinci bir anlam yuklerdi.
    # Sureler CIMRI degil COMERT secildi — erken gecis yarim kalmis bir
    # manevranin ustune yenisini bindirir, gec gecis yalnizca bekletir.
    # 🔴 Her faz sinirinin gerekcesi asagida; degistiren OLCEREK degistirsin.
    # 🔴 BUNLAR FAZ SURESI DEGIL, ZAMAN ASIMI. Fazlar YAKINSAMAYLA ilerler
    # (_donus_ilerlet); bu sayilar yalnizca "yakinsama hic gelmezse takilip
    # kalma" korumasidir. Eskiden faz suresiydi ve olculdu: yaw fazina 12 sn
    # ayrilmisti, oysa 180 derece donus 16.7 sn suruyor (yorumdaki 25 deg/s
    # varsayimi YANLIS -- kanat teget hizi tavani 1.5 m/s once bagliyor ve
    # 7 m yaricapta acisal hiz 12.28 deg/s'de kaliyor). Suru 135 derecede
    # kesilip eve gitmeye basliyordu.
    _DONUS_ZA_S = (
        30.0,   # 0 yaw       : 16.7 s (180 deg @ 12.28 deg/s) + pay
        45.0,   # 1 eve don   : ~31 m / 2 m/s = 15.5 s + ruzgar/takip payi
        20.0,   # 2 merdiven  : 5 m / 1.2 m/s (KACINMA_DIKEY_HIZ) = 4.2 s + pay
        45.0,   # 3 dagilma   : ~20 m / 1.0 m/s = 20 s + pay
    )
    # Bu esigin altinda donulecek aci varsa yaw fazi hic acilmaz (bosuna
    # bekleme). 5 derece, takip hatasi bandinin ustunde secildi.
    _DONUS_YAW_MIN_DEG = 5.0
    # Ev vektoru bundan kisaysa yonu ondan TURETME (63 deg/5 sn tuzagi).
    _DONUS_EV_MIN_M = 3.0

    def _donus_fazi(self, inp: OrchestratorInput) -> int:
        """Gecerli RETURN_HOME alt fazi. SAF — durumu DEGISTIRMEZ.

        Ilerletme `_donus_ilerlet` icinde, tick basina BIR KEZ yapilir.
        Burasi saf olmak zorunda: `_phase_key` tick basina IKI KEZ cagriliyor
        (decide + _maybe_formation_settled) ve burada faz ilerletilseydi tek
        tick'te iki faz atlanirdi.
        """
        return int(self._st.donus_faz)

    def _donus_baslat(self, inp: OrchestratorInput) -> None:
        """RETURN_HOME'a girerken donus basligini BIR KEZ mandallar."""
        st = self._st
        st.donus_faz = 0
        st.donus_faz_t0 = float(inp.time_in_state)
        st.donus_settled = False

        # Temel baslik: EV YONU, vektor en uzunken bir kez olculur.
        temel = None
        if inp.home is not None and inp.centroid is not None:
            uzaklik = math.hypot(inp.home[0] - inp.centroid[0],
                                 inp.home[1] - inp.centroid[1])
            if uzaklik >= self._DONUS_EV_MIN_M:
                temel = self._bearing_deg(inp.centroid, inp.home)
        if temel is None:
            # Ev cok yakin ya da bilinmiyor -> yon turetilemez. Eski yola dus.
            temel = (float(st.kalkis_heading_deg)
                     if st.kalkis_heading_deg is not None
                     else float(st.heading_deg))
        # donus_yaw_deg artik EK OFSET (varsayilan 0). Donus miktari ev
        # yonunden kendiliginden cikiyor: ev arkadaysa 180, 90 saginda ise 90.
        st.donus_heading_deg = (
            temel + float(self._cfg.donus_yaw_deg or 0.0)) % 360.0

        varis = float(st.heading_deg)
        delta = abs(self._shortest_delta_deg(varis, st.donus_heading_deg))
        st.donus_yaw_gerekli = delta >= self._DONUS_YAW_MIN_DEG
        if not st.donus_yaw_gerekli:
            st.donus_faz = 1              # donecek bir sey yok, yaw'i atla

    def _donus_sifirla(self) -> None:
        """RETURN_HOME disina cikinca donus durumunu temizler."""
        st = self._st
        st.donus_faz = 0
        st.donus_faz_t0 = 0.0
        st.donus_settled = False
        st.donus_heading_deg = None
        st.donus_yaw_gerekli = False

    @staticmethod
    def _shortest_delta_deg(current: float, target: float) -> float:
        """Iki aci arasindaki en kisa yonlu fark (-180, 180]."""
        return (target - current + 180.0) % 360.0 - 180.0

    def _donus_ilerlet(self, inp: OrchestratorInput) -> None:
        """Alt fazi YAKINSAMA ile ilerletir; sure yalniz zaman asimi.

        NIYE SURE DEGIL: yaw fazina 12 sn ayrilmisti ama 180 derece donus
        16.7 sn suruyor -> suru 135 derecede kesilip eve gitmeye basliyordu.
        Ters yonu de var: donus erken biterse bosuna asili kalinip pil
        yakiliyordu. Yakinsama olceri (`_maybe_formation_settled`) sekil
        hatasinin PLATO yapmasina + hareketin DURMASINA bakiyor ve zaten bu
        durumda kosuyor; tek eksik, ciktisinin fazi ilerletmek icin
        kullanilmamasiydi.
        """
        st = self._st
        if st.donus_heading_deg is None:
            self._donus_baslat(inp)
            return

        faz = int(st.donus_faz)
        if faz >= 4:
            return
        # Dagilma icin kalkis dizilisi sart; yoksa formasyonda kal (eski yol).
        if faz >= 1 and st.kalkis_ofsetleri is None:
            return

        gecen = float(inp.time_in_state) - float(st.donus_faz_t0)
        za = self._DONUS_ZA_S[faz]
        oturdu = bool(st.donus_settled)
        if not (oturdu or gecen >= za):
            return

        st.donus_settled = False
        st.donus_faz = faz + 1
        st.donus_faz_t0 = float(inp.time_in_state)
        self._donus_ilerleme_notu = (
            f'donus faz {faz} -> {faz + 1} '
            f'({"yakinsadi" if oturdu else f"zaman asimi {za:.0f}s"}, '
            f'{gecen:.1f} sn surdu)'
        )

    def _merdiven_irtifasi(self, agent_id: int, taban_z: float) -> float:
        """Dikey merdiven basamagi — kimlik sirasina gore, DETERMINISTIK.

        180 yaw'dan sonra cizginin uc ucaklari takas ediyor ve kendi kalkis
        noktalarina giderken KAFA KAFAYA geciyorlar. Kacinma bunu cozebilir
        (rutbe 1 yukari, rutbe 2 asagi) ama olculdu: 2 m/s'de frenleme
        2.23 m ve arada 1.77 m kaliyor — hard sinir 2.5 m'nin ALTINDA.
        Merdiven ayrimi ONCEDEN kuruyor; kacinma boylece TEK DAYANAK degil
        YEDEK oluyor. NED'de z asagi pozitif, yukari cikmak z'yi KUCULTUR.
        """
        sira = sorted(int(a) for a in (self._st.kalkis_ofsetleri or {}))
        i = sira.index(int(agent_id)) if int(agent_id) in sira else 0
        return taban_z - i * float(self._cfg.donus_katman_m)

    def _kalkis_hedefleri(self, inp: OrchestratorInput, katmanli: bool):
        """Her ucagin KENDI kalkis noktasi (home + kalkis ofseti)."""
        # 🔴 DONDURME YOK. kalkis_ofsetleri, _assign'in `_ters_dondur` ile
        # urettigi HEADING=0 cercevesinde duruyor; asagi akista
        # formation_node komutun heading'ini zaten uyguluyor. Burada bir kez
        # daha dondurursek CIFT DONUS olur ve ucaklar yanlis noktalara
        # gider — birim test bunu yakaladi (agent 1 icin 1.04 m sapma).
        ofs = self._st.kalkis_ofsetleri or {}
        cikan = []
        for a in inp.agent_ids:
            ox, oy, _oz = ofs.get(int(a), (0.0, 0.0, 0.0))
            z = (self._merdiven_irtifasi(a, inp.centroid[2])
                 if katmanli else inp.centroid[2])
            cikan.append((ox, oy, z - inp.centroid[2]))
        return cikan

    def _on_return_home(self, inp: OrchestratorInput):
        """RETURN_HOME: yaw -> eve don -> dikey merdiven -> herkes kendi yerine.

        Operator profili (2 Eylul gecesi). donus_yaw_deg=0 ve
        kalkis_ofsetleri yoksa davranis ESKISI GIBI: formasyonu koruyarak
        eve don, bitir.
        """
        self._st.tilt_pitch_deg = 0.0
        self._st.tilt_roll_deg = 0.0
        faz = self._donus_fazi(inp)
        self._st.donus_faz = faz

        # Baslik RETURN_HOME'a girerken BIR KEZ mandallandi (_donus_baslat):
        # ev yonu, vektor en uzunken olculdu. Burada yalnizca OKUNUR — her
        # tick yeniden hesaplamak 63 derece/5 sn sapmayi geri getirirdi.
        if self._st.donus_heading_deg is not None:
            yawli = float(self._st.donus_heading_deg)
        elif self._st.kalkis_heading_deg is not None:
            yawli = (float(self._st.kalkis_heading_deg)
                     + float(self._cfg.donus_yaw_deg or 0.0)) % 360.0
        else:
            yawli = (self._bearing_deg(inp.centroid, inp.home)
                     + float(self._cfg.donus_yaw_deg or 0.0)) % 360.0

        if faz == 0:                       # YAW — merkez SABIT, sadece don
            heading = yawli
            offsets = self._assign(self._st.formation_type,
                                   self._st.spacing_m, inp.centroid,
                                   heading, inp)
            if offsets is None:
                return None
            self._st.heading_deg = heading
            return [FormationTargetCmd(
                formation_type=self._st.formation_type,
                center=self._hold_centroid(inp, offsets, heading),
                heading_deg=heading, spacing_m=self._st.spacing_m,
                agent_ids=list(inp.agent_ids), offsets=offsets,
                rotate_towards_target=False, use_current_centroid=True,
                use_current_altitude=True)]

        if faz == 1:                       # EVE DON — formasyon korunur
            heading = yawli
            offsets = self._assign(self._st.formation_type,
                                   self._st.spacing_m, inp.home, heading, inp)
            if offsets is None:
                return None
            self._st.heading_deg = heading
            return [FormationTargetCmd(
                formation_type=self._st.formation_type,
                center=inp.home, heading_deg=heading,
                spacing_m=self._st.spacing_m,
                agent_ids=list(inp.agent_ids), offsets=offsets,
                rotate_towards_target=False, use_current_centroid=False,
                use_current_altitude=False)]

        if faz == 2:                       # DIKEY MERDIVEN — yatayda kimildama
            heading = yawli
            offsets = self._assign(self._st.formation_type,
                                   self._st.spacing_m, inp.home, heading, inp)
            if offsets is None:
                return None
            katmanli = [
                (o[0], o[1],
                 self._merdiven_irtifasi(a, inp.centroid[2]) - inp.centroid[2])
                for a, o in zip(inp.agent_ids, offsets)
            ]
            return [FormationTargetCmd(
                formation_type=self._st.formation_type,
                center=inp.home, heading_deg=heading,
                spacing_m=self._st.spacing_m,
                agent_ids=list(inp.agent_ids), offsets=katmanli,
                rotate_towards_target=False, use_current_centroid=False,
                use_current_altitude=True)]

        # faz 3/4 — HERKES KENDI KALKIS NOKTASINA. Tip CUSTOM: kalkis
        # dizilisi geri geliyor. faz 3 katmanli ve YAVAS (kafa kafaya gecis),
        # faz 4 irtifayi esitler -> mission_fsm inise gecer.
        #
        # 🔴 BURADA BASLIK `yawli` DEGIL, KALKIS BASLIGI. kalkis_ofsetleri
        # kalkis anindaki GERCEK dizilisi, KALKIS BASLIGININ cercevesinde
        # tutuyor (_snapshot_offsets + _ters_dondur). Asagi akista
        # formation_node ofseti komutun heading'iyle donduruyor; buraya donus
        # basligini verirsek diziliş aradaki fark kadar DONER ve herkes
        # kendi noktasindan kayar. 180 derece donuste bu, iki kanadin
        # birbirinin kalkis noktasina inmesi demektir.
        katmanli = (faz == 3)
        offsets = self._kalkis_hedefleri(inp, katmanli)
        kalkis_h = (float(self._st.kalkis_heading_deg)
                    if self._st.kalkis_heading_deg is not None else yawli)
        self._st.heading_deg = kalkis_h
        return [FormationTargetCmd(
            formation_type=_FRM_CUSTOM,
            center=inp.home, heading_deg=kalkis_h,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids), offsets=offsets,
            max_speed=(float(self._cfg.dagilma_hiz_mps) if katmanli else 0.0),
            rotate_towards_target=False, use_current_centroid=False,
            use_current_altitude=True)]


def _maneuver_type(pitch, roll, yaw) -> int:
    """Sıfır olmayan açılara göre ExecuteManeuver maneuver_type seçer."""
    has_p = abs(pitch) > 1e-6
    has_r = abs(roll) > 1e-6
    has_y = abs(yaw) > 1e-6
    if has_p and has_r:
        return _MNV_PITCH_ROLL
    if has_r:
        return _MNV_ROLL
    if has_y and not has_p:
        return _MNV_YAW
    return _MNV_PITCH
