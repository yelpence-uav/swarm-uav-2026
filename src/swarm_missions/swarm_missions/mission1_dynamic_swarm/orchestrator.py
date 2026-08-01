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
    # QR'a VARIŞTA donan yön (derece). resolve_ned() varışta sonraki QR'a
    # ilerlediği için heading oraya kayıp sürü GÖREV sırasında (roll/wait)
    # dönmeye başlıyordu. Bu alan varış yönünü tutar; EXEC+WAIT boyunca heading
    # buna kilitlenir → "önce görev, sonra dön". ROT'ta çözülür (None).
    hold_heading: float = field(default=None)
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
        # Başlangıç formasyonu = jüri dizilişi (CUSTOM). OKBAŞI/V/CIZGI yalnız
        # QR 'frm' komutuyla kurulur; kalkışta hiçbir tip DAYATILMAZ.
        self._st = _State(
            formation_type=_FRM_CUSTOM,
            spacing_m=self._cfg.default_spacing_m,
        )

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
            # Varış yönünü DONDUR: görev (roll/wait) boyunca heading buna
            # kilitlenir, sürü yerinde dönmez. ROT'ta çözülür.
            if inp.swarm_yaw_deg is not None:
                self._st.hold_heading = float(inp.swarm_yaw_deg)
            else:
                self._st.hold_heading = self._st.heading_deg
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
        """Emit-once için (state, step, qr_seq) anahtarı."""
        qr_seq = int(getattr(inp.qr, 'qr_seq', 0)) if inp.qr else 0
        return (inp.mission_state, inp.qr_step, qr_seq)

    def _handle(self, inp: OrchestratorInput):
        """Faza göre ilgili işleyiciye yönlendirir."""
        s = inp.mission_state
        # GÖREV/BEKLEME'de yönü DONDUR (varışta kaydedilen hold_heading).
        # Böylece heading sonraki QR'a kaymaz, sürü roll/wait sırasında
        # dönmez → "önce görev, sonra dön" (dönüş ROT'ta olur).
        if s in (_S_EXECUTE_QR_TASK, _S_WAIT_AT_QR) \
                and self._st.hold_heading is not None:
            self._st.heading_deg = self._st.hold_heading
        if s == _S_SYNCHRONIZED_TAKEOFF:
            return self._on_takeoff(inp)
        if s == _S_ROTATE_TO_NEXT:
            return self._on_rotate(inp)
        if s == _S_NAVIGATE_TO_QR:
            return self._on_navigate(inp)
        if s == _S_EXECUTE_QR_TASK:
            return self._on_execute(inp)
        if s == _S_WAIT_AT_QR:
            # BEKLEME'de formasyon EĞİK komutu GÖNDERME. Artık manevra
            # hold_after_complete=True ile eğimi KENDİ tutuyor (yayını
            # kesmiyor) → dron eğik kalır, gap yok. Buradan eğik formasyon
            # yollarsak maneuver_executor o eğik offset'e euler'i bir daha
            # uygular → DOUBLE-TILT (ölçüldü: eğim 2 katına çıkıp sıçradı).
            # O yüzden boş dön; eğimi manevra tutar, ROT'ta roll=0 ile bırakılır.
            return []
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

    def _on_rotate(self, inp: OrchestratorInput):
        """ROTATE_TO_NEXT: formasyonu bir sonraki QR'a döndürür (merkez sabit)."""
        # Görev bitti, artık dönebiliriz → yön kilidini ÇÖZ.
        self._st.hold_heading = None
        # Manevra eğimini BIRAK: hold=True ile TUTULAN eğimi roll=0 gönderip
        # rampalı indir (start_r→0 maneuver_executor'da), formasyon DÜZ
        # devralır. Eğim varken bir kez üret; tilt sıfırlandığından sonraki
        # tick'lerde tekrar üretmez. Formasyon düz (tilt=0) → double-tilt yok.
        release = []
        if self._st.tilt_roll_deg != 0.0 or self._st.tilt_pitch_deg != 0.0:
            release = [ManeuverCmd(
                maneuver_type=_MNV_ROLL,
                pitch_deg=0.0, roll_deg=0.0, yaw_deg=0.0,
                hold_after_complete=False,
                duration_s=self._cfg.maneuver_duration_s,
            )]
            self._st.tilt_roll_deg = 0.0
            self._st.tilt_pitch_deg = 0.0
        ned = self._qr_geo.resolve_ned()
        if ned is None:
            return release or None
        heading = self._bearing_deg(inp.centroid, ned)

        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            heading, inp,
        )
        if offsets is None:
            return release or None

        cmds = list(release)
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
            rotate_towards_target=True,
            use_current_centroid=True,
            use_current_altitude=True,
        ))
        return cmds

    def _on_navigate(self, inp: OrchestratorInput):
        """NAVIGATE_TO_QR: OKUYUCU dronu QR'ın üstüne çıpalar (irtifayı korur)."""
        ned = self._qr_geo.resolve_ned()
        if ned is None:
            return None
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
        """Formasyon değişimi: yeni tip HEMEN kurulur, eğim RAMPALI iner."""
        # Yeni tipi HEMEN ayarla — yoksa settle erken tetikler, yeni formasyon
        # (örn. kolon) HİÇ oluşmaz + tilt yarıda takılı kalır (ölçüldü: kolon
        # atlandı, dronlar eğik uçtu). Roll/pitch eğimini ANINDA sıfırlama;
        # her tick 2° indir → reshape+düzleşme yumuşak. 5Hz'de 15°->0 ~1.5sn.
        new_type = int(getattr(qr, 'formation_type', 0)) \
            or self._st.formation_type
        if new_type != self._st.formation_type:
            self._st.formation_type = new_type
            # Yeni şekli build_slot_assignment ile yeniden kur ve dondur.
            self._st.frozen_offsets = {}
        spacing = float(getattr(qr, 'spacing_m', 0.0))
        if spacing > 0.0:
            self._st.spacing_m = spacing
        step = 2.0
        r = self._st.tilt_roll_deg
        p = self._st.tilt_pitch_deg
        self._st.tilt_roll_deg = (
            max(0.0, r - step) if r > 0.0 else min(0.0, r + step))
        self._st.tilt_pitch_deg = (
            max(0.0, p - step) if p > 0.0 else min(0.0, p + step))
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
        # hold_after_complete=True: manevra bitince eğimi TUTAR (yayını
        # durdurmaz) → eğik setpoint kesilmez → manevra→formasyon devir
        # boşluğu (düze düşme) KALKAR, ~0.6m sıçrama biter. Eğimi ROT'ta
        # roll=0 ile bırakırız (_on_rotate). Formasyon tarafı bu sürede
        # eğim uygulamamalı (WAIT boş döner) → double-tilt önlenir.
        return [ManeuverCmd(
            maneuver_type=mtype,
            pitch_deg=pitch,
            roll_deg=roll,
            yaw_deg=yaw,
            hold_after_complete=True,
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

    def _on_return_home(self, inp: OrchestratorInput):
        """RETURN_HOME: eve doğru düz formasyonla ilerler (eğim sıfırlanır)."""
        self._st.tilt_pitch_deg = 0.0
        self._st.tilt_roll_deg = 0.0
        heading = self._bearing_deg(inp.centroid, inp.home)
        self._st.heading_deg = heading
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.home, heading,
            inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=inp.home,
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=False,
            use_current_altitude=False,
        )]


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
