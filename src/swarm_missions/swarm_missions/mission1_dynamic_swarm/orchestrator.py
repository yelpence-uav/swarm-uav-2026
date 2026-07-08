"""orchestrator.py — Görev 1 dinamik sürü orkestrasyon çekirdeği (ROS'suz).

mission_fsm hangi FAZ'da olduğumuza karar verip yayınlar (gözlemci); bu modül
o fazı okuyup DOĞRU komutu üretir (orkestratör). Kapalı döngü:

    mission_fsm faz → orchestrator komut → mevcut modül icra →
    swarm_fsm/task_reallocator event → mission_fsm adım ilerletir → tekrar

Bu çekirdek yalnızca KARARI verir; komutları ROS'a yazmak mission1_node'un
işidir. ROS bağımlılığı yoktur → birim test edilebilir.

TASARIM KURALLARI:
  - Emit-once: komut faz/adım/qr_seq değişince BİR KEZ üretilir (spam yok).
  - Lider-guard: FormationTargetCmd ve DetachCmd yalnız lider'de üretilir;
    ManeuverCmd her drone'da (her drone kendi lokal maneuver_executor'ını
    çağırır — mesh üzerinden action gitmez).
  - Model B: manevra sonrası açılı poz, sonraki FormationTargetCmd'lerin
    ofsetlerine gömülür (build_slot_assignment tilt argümanları). Yeni
    formasyon değişimi eğimi sıfırlar.
  - Durum güncellemesi lider olsun olmasın yapılır; böylece lider düşünce
    devralan drone'un orchestrator'ı tutarlı bağlama sahiptir.
"""

import math
from dataclasses import dataclass, field

from .formation_cmd import build_slot_assignment
from .qr_geo import QrGeoResolver

# MissionState (swarm_state_machine mission_states.py ile aynı tutulmalı).
_S_SYNCHRONIZED_TAKEOFF = 3
_S_NAVIGATE_TO_QR = 4
_S_EXECUTE_QR_TASK = 5
_S_ROTATE_TO_NEXT = 7
_S_RETURN_HOME = 9

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

# Şartname: QR okuma için alçalmada alt irtifa sınırı 10 m.
_ALT_FLOOR_M = 10.0


@dataclass
class OrchestratorConfig:
    """mission1 orkestratörünün ayarlanabilir parametreleri."""

    start_qr: int = 1
    default_formation_type: int = 1  # FORMATION_OKBASI
    default_spacing_m: float = 5.0
    wing_alpha_rad: float = math.radians(45.0)
    maneuver_duration_s: float = 3.0
    # QR okunamazsa okuma irtifasına inme (10m tabanı) ve tetik gecikmesi.
    qr_read_altitude_m: float = 12.0
    qr_recovery_delay_s: float = 8.0


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
    """EVENT_MEMBER_DETACH_STARTED olarak yayınlanacak ayrılma (lider).

    detach_wait_s ayrılan ajanın renkli pedde disarm bekleyeceği süredir;
    event value alanıyla ajana taşınır. Ajan bu süre dolunca KENDİ KENDİNE
    tekrar arm olup sürüye yetişir — rejoin zamanlaması dronun kendisindedir
    (şartname: bekleme süresi kadar bekler, en geç sonraki QR'da katılır).
    """

    target_agent_id: int
    detach_wait_s: float = 0.0


@dataclass
class _State:
    """Orkestratörün faz/QR zinciri ve eğim takibi için iç durumu."""

    target_qr: int = 0
    last_next_qr: int = 0
    heading_deg: float = 0.0
    formation_type: int = 1
    spacing_m: float = 5.0
    tilt_pitch_deg: float = 0.0
    tilt_roll_deg: float = 0.0
    handled_key: tuple = field(default=None)
    recovery_emitted: bool = False  # bu takılmada bir kez alçalma yapıldı mı


class Mission1Orchestrator:
    """Faz+adım+QR → komut çeviricisi (saf mantık)."""

    def __init__(self, config: OrchestratorConfig = None) -> None:
        """Konfig ve boş QR çözücü ile başlatır."""
        self._cfg = config or OrchestratorConfig()
        self._qr_geo = QrGeoResolver()
        self._st = _State(
            formation_type=self._cfg.default_formation_type,
            spacing_m=self._cfg.default_spacing_m,
        )

    # --- Dışarıdan besleme (node topic callback'lerinden) --------------------

    def set_qr_table(self, qr_ids, lat_deg, lon_deg, alt_m) -> None:
        """QR konum tablosunu (YKİ'den gelen QRCoordinates) yükler."""
        self._qr_geo.set_table(qr_ids, lat_deg, lon_deg, alt_m)

    def set_origin(self, lat_deg, lon_deg) -> None:
        """Paylaşılan NED origin'ini (SwarmOrigin) günceller."""
        self._qr_geo.set_origin(lat_deg, lon_deg)

    @property
    def qr_ready(self) -> bool:
        """QR konumları NED'e çözülebilir durumdaysa True."""
        return self._qr_geo.ready

    # --- Ana karar -----------------------------------------------------------

    def decide(self, inp: OrchestratorInput) -> list:
        """Bu tick'te icra edilecek komut listesini döner (çoğu tick boş).

        Args:
            inp: Anlık faz/QR/konum bağlamı.

        Returns:
            FormationTargetCmd / ManeuverCmd / DetachCmd örnekleri listesi.
            Lider değilse yalnız ManeuverCmd taşınır.
        """
        # Geçerli QR'dan next_qr'ı yakala (navigasyon hedefi için; NAVIGATE
        # fazında mission_fsm current_qr'ı sıfırladığı için burada saklanır).
        if inp.qr is not None and getattr(inp.qr, 'valid', False):
            self._st.last_next_qr = int(getattr(inp.qr, 'next_qr', 0))

        cmds = []

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

        if not inp.is_leader:
            return [c for c in cmds if isinstance(c, ManeuverCmd)]
        return cmds

    def _maybe_qr_recovery(self, inp: OrchestratorInput):
        """QR çözülemiyorsa okuma irtifasına bir kez alçalır (10m tabanı).

        EXECUTE_QR_TASK'ta qr_step hâlâ NONE (QR okunmadı) ve süre eşiği
        aşıldıysa sürüyü okuma irtifasına indirir. Yetmezse mission_fsm
        timeout ile RETURN_HOME'a düşer (şartname: eve dönüp yeniden başla).
        """
        stuck = (
            inp.mission_state == _S_EXECUTE_QR_TASK and inp.qr_step == 0
        )
        if not stuck:
            self._st.recovery_emitted = False
            return None
        if self._st.recovery_emitted:
            return None
        if inp.time_in_state < self._cfg.qr_recovery_delay_s:
            return None
        self._st.recovery_emitted = True
        read_alt = max(self._cfg.qr_read_altitude_m, _ALT_FLOOR_M)
        center = (inp.centroid[0], inp.centroid[1], -read_alt)
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, center,
            self._st.heading_deg, inp,
        )
        return FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=center,
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
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
        if s == _S_ROTATE_TO_NEXT:
            return self._on_rotate(inp)
        if s == _S_NAVIGATE_TO_QR:
            return self._on_navigate(inp)
        if s == _S_EXECUTE_QR_TASK:
            return self._on_execute(inp)
        if s == _S_RETURN_HOME:
            return self._on_return_home(inp)
        return []

    def _resolve_target(self):
        """Mevcut hedef QR'ı belirler ve NED konumunu çözer.

        Returns:
            (target_qr, (north, east, alt_agl)) veya çözülemezse None.
        """
        target_qr = (
            self._st.last_next_qr
            if self._st.last_next_qr > 0
            else self._cfg.start_qr
        )
        ned = self._qr_geo.resolve_ned(target_qr)
        if ned is None:
            return None
        return target_qr, ned

    def _bearing_deg(self, frm, to) -> float:
        """frm'den to'ya yön açısı (kuzeyden saat yönüne, derece)."""
        dn = to[0] - frm[0]
        de = to[1] - frm[1]
        return math.degrees(math.atan2(de, dn))

    def _assign(self, formation_type, spacing, center, heading_deg,
                inp: OrchestratorInput):
        """Mevcut eğimi koruyarak slot ofsetlerini üretir (model B)."""
        return build_slot_assignment(
            formation_type,
            inp.agent_ids,
            inp.positions,
            center,
            spacing,
            self._cfg.wing_alpha_rad,
            heading_rad=math.radians(heading_deg),
            tilt_pitch_deg=self._st.tilt_pitch_deg,
            tilt_roll_deg=self._st.tilt_roll_deg,
        )

    # --- Faz işleyicileri ----------------------------------------------------

    def _on_rotate(self, inp: OrchestratorInput):
        """ROTATE_TO_NEXT: formasyonu bir sonraki QR'a döndürür (merkez sabit)."""
        resolved = self._resolve_target()
        if resolved is None:
            return None
        target_qr, ned = resolved
        self._st.target_qr = target_qr
        heading = self._bearing_deg(inp.centroid, ned)
        self._st.heading_deg = heading
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            heading, inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=inp.centroid,
            heading_deg=heading,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=True,
            use_current_centroid=True,
            use_current_altitude=True,
        )]

    def _on_navigate(self, inp: OrchestratorInput):
        """NAVIGATE_TO_QR: hedef QR'a yatayda ilerler (irtifayı korur)."""
        ned = self._qr_geo.resolve_ned(self._st.target_qr)
        if ned is None:
            return None
        center = (ned[0], ned[1], inp.centroid[2])
        heading = self._bearing_deg(inp.centroid, ned)
        self._st.heading_deg = heading
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, center, heading, inp,
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
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=inp.centroid,
            heading_deg=self._st.heading_deg,
            spacing_m=self._st.spacing_m,
            agent_ids=list(inp.agent_ids),
            offsets=offsets,
            rotate_towards_target=False,
            use_current_centroid=True,
            use_current_altitude=True,
        )]

    def _exec_maneuver(self, inp, qr):
        """Pitch/roll/yaw manevrası: geçici eğilme, sonra formasyon devralır.

        maneuver_executor yalnızca geçici eğilme hareketini yapar
        (hold_after_complete=False → bitince bırakır, drone eğik pozda kalır;
        px4_interface pozisyonu tutar). Eğik pozu SONRAKI adımlarda ve DONE'da
        formation_control eğik ofsetlerle korur (model B). Böylece /raw'a hep
        tek yazıcı olur; iki yazıcı çakışması olmaz.
        """
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
        """Adımlar bitince eğik pozu formasyon ofsetiyle korur (model B).

        Eğim yoksa komut üretmez. Eğim varsa mevcut centroid'de eğik
        formasyonu yayınlar → manevra bıraktıktan sonra formation_control
        pozu tutar (DONE/wait sırasında düzleşmez).
        """
        if (self._st.tilt_pitch_deg == 0.0
                and self._st.tilt_roll_deg == 0.0):
            return []
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, inp.centroid,
            self._st.heading_deg, inp,
        )
        return [FormationTargetCmd(
            formation_type=self._st.formation_type,
            center=inp.centroid,
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
        alt_agl = float(getattr(qr, 'altitude_agl_m', 0.0))
        center = (inp.centroid[0], inp.centroid[1], -alt_agl)
        offsets = self._assign(
            self._st.formation_type, self._st.spacing_m, center,
            self._st.heading_deg, inp,
        )
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
        """Sürüden birey ayırma: hedef ID + bekleme süresiyle DetachCmd.

        Rejoin zamanlaması ayrılan dronun kendisindedir; burada yalnız
        detach_wait_s taşınır (event value ile ajana gider).
        """
        target = int(getattr(qr, 'target_agent_id', 0))
        if target <= 0:
            return []
        wait_s = float(getattr(qr, 'detach_wait_s', 0.0))
        return [DetachCmd(target_agent_id=target, detach_wait_s=wait_s)]

    def _on_return_home(self, inp: OrchestratorInput):
        """RETURN_HOME: eve doğru düz formasyonla ilerler (eğim sıfırlanır).

        QR zinciri de sıfırlanır: madde 17 restart'ında sürü eve varınca rota
        yeniden başlarsa (mission_fsm ROTATE_TO_NEXT), hedef tekrar QR1 olur.
        """
        self._st.tilt_pitch_deg = 0.0
        self._st.tilt_roll_deg = 0.0
        self._st.last_next_qr = 0
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
