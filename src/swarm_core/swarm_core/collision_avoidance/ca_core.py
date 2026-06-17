"""ca_core.py — Hız-tabanlı çarpışma önleme çekirdeği (saf matematik, ROS yok).

Bu modül kasıtlı olarak ROS2'den bağımsızdır: tüm fonksiyonlar saf Python
alır/döner, böylece birim test ROS runtime'ı olmadan koşar (bkz.
test/test_ca_core.py). Node katmanı (collision_avoidance_node.py) yalnızca
mesajları bu çekirdeğe besler.

═══════════════════════════════════════════════════════════════════════════
MİMARİ: CA = SAF HIZ FİLTRESİ (son emniyet katmanı)
═══════════════════════════════════════════════════════════════════════════
Sistem HIZ-TABANLIDIR: pozisyon kontrolünü tek bir yer yapar (formation
node'daki SVT, hız uzayında). PX4 pozisyon kontrolü YAPMAZ. CA bu yüzden
pozisyon ÜRETMEZ; formasyon hızına bir hız terimi ekler:

    v_cmd_xy = v_form_xy + Σ_j ( F_rep,j + F_tan,j )
    v_cmd_z  = v_form_z                      (CA Z'ye dokunmaz — irtifa formasyonun)

Girdi konum/mesafe OLABİLİR (komşunun nerede olduğunu ölçmek zorunludur);
ama ÇIKTI daima hızdır. position_valid bu çekirdekte hiç geçmez.

═══════════════════════════════════════════════════════════════════════════
İTME MODELİ: KAPANMA-HIZI KAPILI İTİCİ ALAN (Model B)
═══════════════════════════════════════════════════════════════════════════
Klasik Khatib (1986) itici potansiyeli yalnızca MESAFEYE bakar:

    F_rep = k_rep · (1/d − 1/d0) · (1/d²) · û_away          (d ≤ d0)

İki sorunu var:
  (1) Yöne/hıza kör → komşudan UZAKLAŞIRKEN bile iter → SVT (içeri çeker) ile
      sonsuz itişme → limit cycle / osilasyon (şartname −10 ceza kalemi).
  (2) hard=2 m drone boyutundan çok büyük olduğundan 1/d formu bu yarıçaplarda
      DÜZ kalır (zayıf), doygunluk hard'da UÇURUM yapar → tekme → savrulma.

Çözüm iki katmanlı:
  (1) MESAFE alanını smoothstep ile şekillendir (bkz. _repulsion_magnitude):
      d0'da 0 → hard'da f_sat, tüm bantta anlamlı + C¹ sürekli (uçurum yok).
  (2) Alanı KAPANMA HIZINA göre kapıla (RVO/ORCA esinli):

Çözüm: itkiyi KAPANMA HIZINA göre kapıla (RVO/ORCA esinli):

    c_j = −(rel · rel_v) / d        (pozitif = mesafe azalıyor, "üstüme geliyor")
    g(c) = smoothstep(c / c_ref)    (yaklaşırken 1, uzaklaşırken 0)
    F_rep ← F_rep · g(c)

→ Denge mesafesinde c→0 → itki→0 → drone DURUR. "It↔SVT çek" döngüsü
yapısal olarak imkânsız. Emniyet için hard yarıçap altında kapı zorla açık
tutulur (g=1): acil bölgede yaklaşma olmasa bile aktif ayrışma.

═══════════════════════════════════════════════════════════════════════════
KATMANLI EMNİYET YARIÇAPLARI (merkez-merkez, yatay)
═══════════════════════════════════════════════════════════════════════════
    r_min = 1.5 m  → hard floor: kapanma hızı projeksiyonla SIFIRLANIR (garanti)
    hard  = 2.0 m  → itki doygunluğu (f_sat); kapı zorla açık
    d0    = 3.5 m  → itki başlar (smoothstep zarfıyla C¹ sürekli)
    aralık= 5.0 m  → nominal: d0 < aralık → seyirde CA UYUR (formasyon bozulmaz)

LİTERATÜR / TASARIM:
- Khatib (1986): çekici/itici potansiyel alan; etki yarıçapı d0 dışında F=0.
- RVO/ORCA (van den Berg): yalnızca çarpışma rotasındaki komşuya tepki →
  kapanma-hızı kapısı bu fikrin APF'e taşınmış halidir.
- Sağ-el teğet: deterministik, simetrik, haberleşmesiz ayrışma (dağıtık).
- r_min projeksiyonu: "asla çarpışma" garantisini hız uzayında verir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class NeighborObs:
    """Tek komşunun CA girdisi (self-merkezli, NED).

    NeighborInfo'dan doldurulur:
        rel_*  = relative_*   (komşu − self)  → self'ten komşuya doğru vektör
        rel_v* = relative_v*  (komşu_hız − self_hız)  → göreli hız
        distance = distance_m (3D merkez-merkez, referans)
    """

    rel_x: float
    rel_y: float
    rel_z: float
    rel_vx: float
    rel_vy: float
    rel_vz: float
    distance: float


@dataclass
class CaParams:
    """CA ayar kümesi. Varsayılanlar: 5 m formasyon aralığı, X500/F550
    (~0.5–0.55 m çerçeve), heterojen sürü için seçilmiştir."""

    d0: float = 4.5            # influence yarıçapı (m): itki başlar
    hard: float = 2.0          # acil yarıçap (m): doygunluk + kapı zorla açık
    r_min: float = 1.5         # hard floor (m): kapanma hızı projeksiyonla sıfırlanır
    f_sat: float = 6.0         # itici doygunluk büyüklüğü (m/s): hard'da bu değere ulaşır
    c_dead: float = 0.2        # kapanma-hızı deadband: gürültü-altı kapıyı açmaz (mikro-osc)
    c_ref: float = 1.0         # kapanma-hızı kapı bandı (m/s): c_dead+c_ref'te g=1
    c_damp: float = 0.7        # radyal sönüm: yaklaşmayı frenler, standoff overshoot söner
    damp_band: float = 0.5     # içeri-fren yalnızca hard..hard+band (ayrılanı kovalamaz)
    k_tan: float = 0.9         # teğet kaçış kazancı
    v_max: float = 4.0         # v_cmd XY büyüklük tavanı (m/s)
    xy_guard: float = 0.3      # dejenere yığılma ε-guard (m): altında CA çözemez
    slew_normal: float = 4.0       # normal ivme sınırı (m/s²)
    slew_emergency: float = 30.0   # acil ivme sınırı (m/s²)
    hyst_band: float = 0.2         # slew Schmitt trigger histerezis bandı (m)
    dt: float = 0.05               # kontrol adımı (s) — 20 Hz varsayılan


def _finite(*vals: float) -> bool:
    """Hiçbiri NaN/Inf değilse True."""
    for v in vals:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _smoothstep(t: float) -> float:
    """C¹ sürekli smoothstep: t²(3−2t), t∈[0,1]→[0,1] (sınır dışı clamp)."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def clamp_speed_xy(vx: float, vy: float, max_speed: float) -> tuple[float, float]:
    """XY hız vektörünü max_speed büyüklüğüne kırpar (yön korunur)."""
    speed = math.sqrt(vx * vx + vy * vy)
    if speed > max_speed and speed > 1e-9:
        s = max_speed / speed
        return vx * s, vy * s
    return vx, vy


class CollisionAvoidanceCore:
    """Hız-tabanlı çarpışma önleme çekirdeği (Model B).

    Kullanım:
        core = CollisionAvoidanceCore(CaParams(dt=0.05))
        v_cmd, risk = core.compute(v_form, neighbors)
        # passthrough/relay yapılan her durumda:
        core.reset(cur_vel)   # slew başlangıcını gerçek hıza eşitle
    """

    def __init__(self, params: CaParams | None = None) -> None:
        self.p = params or CaParams()
        # Slew durumu — bir önceki komut edilen XY hızı.
        self._prev_vx: float = 0.0
        self._prev_vy: float = 0.0
        self._emergency: bool = False   # slew Schmitt trigger durumu

    # ------------------------------------------------------------------ #
    #  Ana giriş noktası                                                  #
    # ------------------------------------------------------------------ #
    def compute(
        self,
        v_form: tuple[float, float, float],
        neighbors: list[NeighborObs],
    ) -> tuple[tuple[float, float, float], bool]:
        """CA filtresi ana giriş noktası.

        Args:
            v_form: Formation node hedef hızı (NED m/s) — SVT+damp+rel+vff paketi.
            neighbors: Geçerli komşular (self-merkezli NED).

        Returns:
            (v_cmd, risk):
              v_cmd : CA çıkış hızı (NED m/s), slew uygulanmış.
              risk  : CA müdahale ettiyse True. Müdahale = (a) bir komşu itki/
                      teğet üretti (kapı açık), VEYA (b) bir komşu r_min altında
                      (emniyet projeksiyonu devrede). Kapı kapalı + r_min dışı →
                      müdahale yok → False (node ham hızı geçirir, anti-osilasyon).
        """
        p = self.p
        vfx, vfy, vfz = float(v_form[0]), float(v_form[1]), float(v_form[2])

        # --- Aktif komşuları süz: 3D mesafeyle karar, YATAYDA kaçış yönü ---
        # active öğesi: (ux_away, uy_away, mag_rep, damp)  — yön + itki + radyal sönüm
        active: list[tuple[float, float, float, float]] = []
        min_d3 = float('inf')
        any_within_rmin = False   # itki olmasa bile projeksiyon için izlenir

        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z,
                           n.rel_vx, n.rel_vy, n.rel_vz):
                continue
            # Kaçış yönü: komşudan uzağa, YATAYDA (rel = komşu−self → self−komşu).
            away_x = -n.rel_x
            away_y = -n.rel_y
            d_xy = math.sqrt(away_x * away_x + away_y * away_y)
            # Mesafe/kapı/projeksiyon kararları 3D mesafeyle: dikey ayrımı GÖR.
            # 5 m yukarıdaki komşu yatayda yakın olsa bile çatışma değildir →
            # gereksiz yatay itki yok (formasyon bozulmaz).
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)

            if d_xy < p.xy_guard:
                continue   # tam üst/alt: yatayda itemeyiz (irtifa/görev katmanı)
            if d3 >= p.d0:
                continue   # 3D etki dışı (dikey ayrım dahil)

            if d3 <= p.r_min:
                any_within_rmin = True   # kapı kapalı olsa bile projeksiyon şart
            if d3 < min_d3:
                min_d3 = d3

            ux = away_x / d_xy   # komşudan UZAĞA YATAY birim vektör (Z=0)
            uy = away_y / d_xy

            # --- Kapanma hızı (3D): pozitif = mesafe azalıyor ("üstüme geliyor") ---
            # c = −d(d3)/dt = −(rel · rel_v)/d3
            c = -(n.rel_x * n.rel_vx + n.rel_y * n.rel_vy
                  + n.rel_z * n.rel_vz) / d3

            # --- KAPI g(c): yaklaşırken 1, uzaklaşırken/gürültüde 0 (anti-osilasyon) ---
            # Hard yarıçap altında kapı ZORLA AÇIK (g=1): acil ayrışma, yaklaşma
            # olmasa bile it. Üstünde kapanma-hızı kapısı + deadband: yalnızca
            # c > c_dead (anlamlı yaklaşma) kapıyı açar; slottaki minik jitter
            # (c ≈ 0) kapıyı açmaz → limit cycle / mikro-osilasyon yok.
            if d3 <= p.hard:
                gate = 1.0
            elif p.c_ref > 1e-6:
                gate = _smoothstep((c - p.c_dead) / p.c_ref)
            else:
                gate = 1.0

            # --- İtici büyüklük (3D mesafe) × kapı; YATAY yönde uygulanır ---
            mag = self._repulsion_magnitude(d3) * gate
            # Gerçek viskoz radyal sönüm: F_damp = c_damp·c·û_away.
            #   yaklaşma (c>0) → dışarı fren: dalışı yavaşlatır.
            #   ayrılma  (c<0) → içeri fren: SAVRULMA (overshoot) söner.
            # İki yön de aynı dist_scale zarfıyla: d0'da 0 → hard'da tam. d0'da
            # sıfırladığı için sınırdaki komşu kovalanmaz (chase yok); sönüm c
            # ile orantılı olduğundan yavaş ayrılan formasyon komşusu da çekilmez.
            dist_scale = (_smoothstep((p.d0 - d3) / (p.d0 - p.hard))
                          if p.d0 > p.hard + 1e-6 else 1.0)
            damp = p.c_damp * c * dist_scale
            # --- Teğet (yanal kaçış) KENDİ mesafe zarfı ile ---
            # KÖK NEDEN: radyal smoothstep d0'da ~0 olduğundan teğet de menzilde
            # aç kalıyordu (3.09m'de yalnız ~0.5 m/s yanal). Dronlar yana
            # açılamadan kafa-kafaya dalıp NORTH ekseninde sekiyordu. Çözüm:
            # teğete d0'da GÜÇLÜ başlayan ayrı zarf — orta nokta (d0+hard)/2'de
            # tam güce ulaşır (radyal hâlâ hard'da). Böylece dron daha uzaktayken
            # yana açılır → pürüzsüz sidestep, radyal sekme yok.
            tan_env = (_smoothstep((p.d0 - d3) / (0.5 * (p.d0 - p.hard)))
                       if p.d0 > p.hard + 1e-6 else 1.0)
            mag_tan = p.f_sat * gate * tan_env
            if mag > 1e-9 or abs(damp) > 1e-9 or mag_tan > 1e-9:
                active.append((ux, uy, mag, damp, mag_tan))

        # --- Müdahale yok: tam pass-through (slew başlangıcını eşitle) ---
        # Kapı kapalı (uzaklaşan/duran komşu) ve hiçbiri r_min altında değil →
        # formasyon hızı dokunulmadan geçer (osilasyon beslemesi yok).
        if not active and not any_within_rmin:
            self.reset((vfx, vfy, vfz))
            return (vfx, vfy, vfz), False

        # --- Kuvvetleri topla: F_rep (itici) + F_damp (radyal sönüm) + F_tan (teğet) ---
        vx, vy = vfx, vfy
        for ux, uy, mag, damp, mag_tan in active:
            # İtici + radyal sönüm: ikisi de u_away yönünde (damp işaretli).
            f_radial = mag + damp
            vx += f_radial * ux
            vy += f_radial * uy
            # Teğet: sağ-el kuralı (deadlock/kafa-kafaya kırıcı). Erken-başlayan
            # yanal zarf (mag_tan) ile → sidestep menzilde başlar.
            tx, ty = self._tangent(vfx, vfy, ux, uy, mag_tan)
            vx += tx
            vy += ty

        # --- XY büyüklük tavanı (Z'ye dokunulmaz) ---
        vx, vy = clamp_speed_xy(vx, vy, p.v_max)

        # --- Son savunma: r_min altında kapanma hızı bileşenini sıfırla ---
        # (itki üretilmemiş olsa bile — garanti katmanı).
        vx, vy = self._safety_projection(vx, vy, neighbors)

        # --- Slew limit (Schmitt trigger histerezis ile, 3D mesafeye göre) ---
        vx, vy = self._apply_slew(vx, vy, min_d3)

        # NaN/Inf koruyucu: hesap patlarsa önceki hıza dön.
        if not _finite(vx, vy):
            vx, vy = self._prev_vx, self._prev_vy

        self._prev_vx, self._prev_vy = vx, vy
        return (vx, vy, vfz), True

    def reset(self, v_current: tuple[float, float, float]) -> None:
        """Slew başlangıcını mevcut hıza eşitle.

        Node relay/passthrough yaptığı her durumda çağırmalı; aksi hâlde CA
        devreye girince slew gerçek drone hızından değil eski değerden başlar →
        geçişte sıçrama olur.
        """
        self._prev_vx = float(v_current[0])
        self._prev_vy = float(v_current[1])
        self._emergency = False

    # ------------------------------------------------------------------ #
    #  Yardımcı metodlar                                                  #
    # ------------------------------------------------------------------ #
    def _repulsion_magnitude(self, d: float) -> float:
        """İtici büyüklük: d0'da 0, hard'da f_sat — C¹ sürekli smoothstep alan.

        d ≥ d0    → 0      (etki dışı).
        d ≤ hard  → f_sat  (doymuş, acil itki).
        Arada:    f_sat · smoothstep((d0−d)/(d0−hard)).

        NEDEN KHATIB DEĞİL: klasik Khatib k(1/d−1/d0)/d² formu, hard=2 m drone
        boyutundan çok büyük olduğu için bu yarıçaplarda DÜZ kalıyor (2–3.5 m
        bandında itki ~0.01–0.2 m/s) ve doygunluk hard'da bir UÇURUM yapıyor
        (0.2 → 6.0 ani sıçrama → tekme/savrulma → osilasyon). smoothstep alan
        tüm bantta anlamlı VE pürüzsüz: 3.0 m'de erken fren (~1.5 m/s), hard'a
        doğru kademeli doygunluk, sınırlarda süreksizlik yok. Khatib teorik
        referanstır; pratikte iyi koşullanmış alan budur.
        """
        p = self.p
        if d >= p.d0:
            return 0.0
        if d <= p.hard:
            return p.f_sat
        t = (p.d0 - d) / (p.d0 - p.hard)
        return p.f_sat * _smoothstep(t)

    def _tangent(
        self, vfx: float, vfy: float, ux: float, uy: float, mag_rep: float,
    ) -> tuple[float, float]:
        """Sağ-el kuralı XY teğet kaçış (deadlock / kafa-kafaya kırıcı).

        t_hat = cross(u_away, ẑ) = (u_y, −u_x). NED'de kuzeye koşarken sağ =
        doğu. İki drone da kendi sağına sapınca simetrik ayrışır (trafik kuralı,
        haberleşmesiz → dağıtık).

        Ağırlık w = max(0, −cos α): formasyon hızı engele doğruyken (kafa-kafaya)
        w→1, dik/uzaklaşırken w→0. Kademeli rampa (if-gate yok). Büyüklük gated
        itici (mag_rep) ile ölçeklenir → kapı kapalıysa teğet de yok.
        """
        vf_h = math.sqrt(vfx * vfx + vfy * vfy)
        if vf_h < 1e-3 or mag_rep < 1e-9:
            return 0.0, 0.0
        cos_a = (vfx * ux + vfy * uy) / vf_h
        w = max(0.0, -cos_a)
        if w < 1e-4:
            return 0.0, 0.0
        tx = uy      # cross(u_away, ẑ) XY bileşeni
        ty = -ux
        f = self.p.k_tan * w * mag_rep
        return f * tx, f * ty

    def _safety_projection(
        self, vx: float, vy: float, neighbors: list[NeighborObs],
    ) -> tuple[float, float]:
        """Son savunma: r_min altında kalan komşuya doğru kapanma hızını sıfırla.

        Tüm kuvvetler uygulandıktan SONRA bile drone hâlâ komşuya gidiyorsa
        (v_close > 0), o bileşeni projeksiyonla kaldır → "r_min altına asla
        düşme" garantisi hız uzayında verilir. XY işlem, Z dokunulmaz.
        """
        p = self.p
        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z):
                continue
            # 3D mesafe r_min kontrolü (dikey ayrım dahil); yatay projeksiyon.
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)
            if d3 > p.r_min:
                continue
            d_xy = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y)
            if d_xy < 1e-3:
                continue   # tam üst/alt: yatay projeksiyon anlamsız (Z formasyonun)
            # Komşuya DOĞRU YATAY birim vektör (self→komşu).
            tx = n.rel_x / d_xy
            ty = n.rel_y / d_xy
            v_close = vx * tx + vy * ty   # pozitif = hâlâ yatayda yaklaşıyor
            if v_close > 0.0:
                vx -= v_close * tx
                vy -= v_close * ty
        return vx, vy

    def _apply_slew(
        self, vx: float, vy: float, min_d3: float,
    ) -> tuple[float, float]:
        """XY ivme sınırı — Schmitt trigger histerezis (±hyst_band @ hard).

        d < hard             → acil mod (slew_emergency): hızlı kaçış.
        d > hard + hyst_band → normal mod (slew_normal): titremesiz.
        Bant içinde geçiş yok → chattering engellenir. Z slew'lenmez (formasyon).
        min_d3: en yakın komşunun 3D mesafesi.
        """
        p = self.p
        if not self._emergency and min_d3 < p.hard:
            self._emergency = True
        elif self._emergency and min_d3 > p.hard + p.hyst_band:
            self._emergency = False

        max_delta = (p.slew_emergency if self._emergency
                     else p.slew_normal) * p.dt
        dvx = vx - self._prev_vx
        dvy = vy - self._prev_vy
        d = math.sqrt(dvx * dvx + dvy * dvy)
        if d > max_delta and d > 1e-9:
            s = max_delta / d
            return self._prev_vx + dvx * s, self._prev_vy + dvy * s
        return vx, vy
