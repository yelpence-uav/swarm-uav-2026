"""scenarios.py — APF çarpışma önleme test senaryoları kataloğu.

Bu dosya ROS'suz saf VERİ'dir: her senaryo, drone'ların NED başlangıç ve
hedef konumlarını tanımlar. Tek kaynak (single source of truth) olarak hem
kinematik simülatör (apf_sim.py) hem de ileride SITL koşucusu tarafından
okunur.

KOORDİNAT: NED (+X=Kuzey, +Y=Doğu, +Z=Aşağı, yukarı = negatif z).
Saha ~10 m × 10 m yatay; senaryolar ±8 m içinde tutulur.

EMNİYET KATMANLARI (jüri için kritik ayrım — emniyet-mesafesi-tasarimi):
    influence_radius (3.5 m)  → APF kaçmaya başlar
    hard_radius      (2.0 m)  → APF maksimum itki (acil)
    safety (emniyet) (1.5 m)  → İHLAL EŞİĞİ — min merkez-merkez mesafe,
                                asla ihlal edilmemeli (jüriye kırmızı çizgi)
    physical         (~0.7 m) → pervane teması (gerçek çarpışma)

Emniyet 1.5 m: RTK ±3 cm ölçümle, drone fiziksel açıklığı + aerodinamik
downwash payıyla belirlenir (konum gürültüsüyle değil). Konservatif tercih
(çarpışma cezası −20×N en ağır).

`expect_avoid=True`  → kaçınma beklenir; min mesafe emniyeti korumalı.
`expect_avoid=False` → çatışma yok (örn. farklı irtifa); aşırı tepki olmamalı
                       ama min mesafe yine emniyet üstünde kalmalı.

SENARYO SAYISI: 18 geometrik senaryo, 6 kategoride.
Bozulmuş-veri (stale/excluded-state/NaN) testleri geometrik değildir;
onlar birim testlerde (test_apf.py) elle kurulmuş NeighborInfo ile sınanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Formasyon slotları GERÇEK geometri fonksiyonundan üretilir (tek kaynak):
# elle koordinat yazmak yerine formation_node'un kullandığı aynı hesabı
# çağırırız → formation_geometry değişirse senaryolar otomatik takip eder.
from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_slot_offsets,
)


@dataclass(frozen=True)
class DroneInit:
    """Bir drone'un senaryo başlangıcı: kimlik, NED başlangıç ve hedef.

    excluded=True → bu drone DİĞERLERİNİN avoidance hesabından çıkarılır
    (kontrat m.8: DETACHED/PRECISION_LANDING/LANDED/FAILSAFE). Yani diğerleri
    onu engel saymaz (hassas inişini bozmasınlar). Kendisi yine de
    çevresindekilerden kaçınmaya devam eder.

    Formasyon-farkında simde (apf_sim) `goal` aynı zamanda drone'un FORMASYON
    SLOT'udur: SVT bu slota çeker. goal==start ise drone slotta hover eder
    (formasyon koruma testleri için); farklıysa slot hedefe ramp'lenir
    (seyahat/çatışma testleri).
    """

    agent_id: int
    start: tuple[float, float, float]
    goal: tuple[float, float, float]
    excluded: bool = False


@dataclass(frozen=True)
class Perturbation:
    """Bir drone'a dış kuvvet (rüzgar/itme/çarpma) enjekte eder.

    Formasyon koruma testlerinin çekirdeği: drone slotunda dururken [t0, t1]
    aralığında sabit hızla itilir → APF çarpışmayı önlemeli, slot_dev tavanı
    tutmalı, itme bitince SVT slota geri toplamalı. "Drone'un başına ne
    geleceği belli değil" senaryosunun (rüzgar/arıza) deterministik testi.

    vel: NED hız (m/s) olarak dış itme; drone'un kontrol hızının ÜSTÜNE eklenir.
    """

    agent_id: int
    t_start: float
    t_end: float
    vel: tuple[float, float, float]


@dataclass(frozen=True)
class Phase:
    """Görev fazı: t_start anında sürünün slot geometrisi (ve excluded
    durumu) değişir. Çok-fazlı 'dinamik görev icrası' senaryoları bununla
    kurulur (formasyon değişimi → birey çıkar → birey ekle → topla).

    ca_sim bu fazları zaman içinde uygular: faz gelince goal[i] güncellenir,
    slot yeni hedefe ramp'lenir → tek sürekli (kesintisiz) görev zaman
    çizelgesi. Şartname §5.1 görev akışına sadık.

    goals: her drone için yeni NED slot hedefi (agent_id sırası, 1..n).
    excluded: opsiyonel; her drone için yeni excluded bayrağı (birey
              çıkar/ekle). None ise mevcut excluded korunur.
    label: grafikte faz işaretlemek için (örn 'Formasyon değişimi').
    """

    t_start: float
    goals: tuple[tuple[float, float, float], ...]
    excluded: tuple[bool, ...] | None = None
    label: str = ''


@dataclass(frozen=True)
class Scenario:
    """Tek bir test senaryosu (saf geometri/kinematik)."""

    name: str
    category: str
    description: str
    drones: tuple[DroneInit, ...]
    safety_radius_m: float = 1.5  # emniyet eşiği (merkez-merkez), bkz dosya başı
    expect_avoid: bool = True
    max_speed_mps: float = 2.0
    notes: str = ""
    # ca_solvable=False → çarpışma önleme TEK BAŞINA çözemez; görev katmanı
    # sıralaması/uzamsal ayrım gerekir (örn. aynı kolonda dik kafa-kafaya).
    ca_solvable: bool = True
    # Formasyon-farkında alanlar (apf_sim node-sadık koşum için):
    perturbations: tuple[Perturbation, ...] = ()  # dış itme/rüzgar olayları
    # slot_dev_max: carrot'un slottan max yatay sapma TAVANI (node ile aynı).
    # Sıkılığı SVT sağlar; bu yalnızca tavan → normal formasyonda drone değmez,
    # 2.5 sadece çarpışma kaçışına alan verir (1.5 sandwich'te çarpışmaya yol
    # açıyordu; 2.5 → 22/23 senaryo emniyet korur).
    slot_dev_max_m: float = 2.5
    # check_slot_dev=True → max_slot_dev ≤ slot_dev_max_m ihlal sayılır
    # (formasyon koruma + sınır testleri). Uzun seyahatte False.
    check_slot_dev: bool = False
    # recover_threshold_m: pertürbasyon sonrası formation_rms bu eşiğin altına
    # inince "toparlandı" sayılır (recovery_time ölçümü).
    recover_threshold_m: float = 0.5
    # Çok-fazlı görev: zamanı gelince slot geometrisini değiştiren fazlar
    # (formasyon değişimi, birey ekle/çıkar). Boşsa tek-bacaklı senaryo.
    phases: tuple[Phase, ...] = ()
    # duration_s: çok-fazlı görevin tam süresi (saniye). None ise sim default.
    duration_s: float | None = None


def _ring(n: int, r: float, z: float, antipodal: bool = True,
          phase_deg: float = 0.0) -> tuple[DroneInit, ...]:
    """Yarıçap r çemberine n drone yerleştirir; hedef = karşı nokta.

    Antipodal (karşıt) hedef → hepsi merkezde buluşmaya çalışır: en zorlu
    simetrik çatışma. agent_id 1..n.
    """
    drones = []
    for i in range(n):
        ang = math.radians(phase_deg + i * 360.0 / n)
        sx = r * math.cos(ang)
        sy = r * math.sin(ang)
        if antipodal:
            gx, gy = -sx, -sy
        else:
            gx, gy = sx, sy
        drones.append(DroneInit(
            agent_id=i + 1,
            start=(round(sx, 3), round(sy, 3), z),
            goal=(round(gx, 3), round(gy, 3), z),
        ))
    return tuple(drones)


_Z = -10.0  # standart çalışma irtifası (10 m yukarı)


# =====================================================================
# KATEGORİ A — İKİLİ GEOMETRİK KARŞILAŞMALAR (pairwise)
# =====================================================================
_PAIRWISE = [
    Scenario(
        name='head_on',
        category='ikili',
        description='Kafa kafaya: iki drone aynı hat üzerinde zıt yönde.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (6.0, 0.0, _Z), (-6.0, 0.0, _Z)),
        ),
        notes='En kritik ikili durum; teğet kaçış (sağdan geç) devreye girer.',
    ),
    Scenario(
        name='head_on_offset',
        category='ikili',
        description='Hafif yanal kaçık kafa kafaya (gerçekçi GPS gürültüsü).',
        drones=(
            DroneInit(1, (-6.0, 0.3, _Z), (6.0, 0.3, _Z)),
            DroneInit(2, (6.0, -0.3, _Z), (-6.0, -0.3, _Z)),
        ),
        notes='Simetri kırık → itici kuvvet tek başına çözebilmeli.',
    ),
    Scenario(
        name='crossing_90',
        category='ikili',
        description='Dik kesişme: yollar merkezde 90° çakışır.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (0.0, -6.0, _Z), (0.0, 6.0, _Z)),
        ),
    ),
    Scenario(
        name='crossing_45',
        category='ikili',
        description='Eğik kesişme: biri kuzeye, biri 45° çaprazdan geçer.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (-6.0, -6.0, _Z), (6.0, 6.0, _Z)),
        ),
    ),
    Scenario(
        name='crossing_wide',
        category='ikili',
        description='Geniş açılı (~135°) yarı-kafa-kafaya kesişme.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (6.0, -3.0, _Z), (-6.0, 3.0, _Z)),
        ),
    ),
    Scenario(
        name='overtaking',
        category='ikili',
        description='Sollama: arkadaki drone öndekini aynı hatta yakalar.',
        drones=(
            DroneInit(1, (0.0, 0.0, _Z), (8.0, 0.0, _Z)),
            DroneInit(2, (-3.0, 0.0, _Z), (10.0, 0.0, _Z)),
        ),
        notes='Arkadan yaklaşma; kapanış hızı modülasyonu (RVO) sınanır.',
    ),
    Scenario(
        name='converging_point',
        category='ikili',
        description='İki drone aynı noktaya yakınsar (paylaşılan hedef).',
        drones=(
            DroneInit(1, (-5.0, 0.0, _Z), (0.0, 0.0, _Z)),
            DroneInit(2, (5.0, 0.0, _Z), (0.0, 0.0, _Z)),
        ),
        notes='Ortak hedefte bile min ayrım korunmalı; kalıcı itki gerekir.',
    ),
    Scenario(
        name='static_obstacle',
        category='ikili',
        description='Sabit (hover) drone; diğeri üstünden geçmeye çalışır.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (0.0, 0.0, _Z), (0.0, 0.0, _Z)),
        ),
        notes='Engel hareketsiz; saf konum-bazlı itki + teğet kaçış.',
    ),
    Scenario(
        name='parallel_merge',
        category='ikili',
        description='Paralel iki şerit daralarak tek hedefe birleşir.',
        drones=(
            DroneInit(1, (-6.0, 1.0, _Z), (6.0, 0.2, _Z)),
            DroneInit(2, (-6.0, -1.0, _Z), (6.0, -0.2, _Z)),
        ),
    ),
]


# =====================================================================
# KATEGORİ B — DİKEY (Z EKSENİ)
# =====================================================================
_VERTICAL = [
    Scenario(
        name='crossing_diff_alt',
        category='dikey',
        description='XY\'de kesişen ama 2 m irtifa farklı iki drone.',
        drones=(
            DroneInit(1, (-6.0, 0.0, -10.0), (6.0, 0.0, -10.0)),
            DroneInit(2, (0.0, -6.0, -12.0), (0.0, 6.0, -12.0)),
        ),
        expect_avoid=False,
        notes='Dikey ayrım yeterli → aşırı tepki olmamalı, ihlal de olmamalı.',
    ),
    Scenario(
        name='vertical_converge',
        category='dikey',
        description='Biri tırmanırken diğerinin irtifasına girer.',
        drones=(
            DroneInit(1, (0.0, 0.0, -10.0), (0.0, 0.0, -10.0)),
            DroneInit(2, (0.0, 0.0, -13.0), (0.0, 0.0, -9.0)),
        ),
        notes='Z itkisi z_weight ile kısık; yine de ayrım korunmalı.',
    ),
]


# =====================================================================
# KATEGORİ C — ÇOKLU DRONE (3+)
# =====================================================================
_MULTI = [
    Scenario(
        name='sandwich_crossthrough',
        category='coklu',
        description='Merkezdeki hover drone iki yandan zıt geçişle sıkışır.',
        drones=(
            DroneInit(1, (-4.0, 0.0, _Z), (4.0, 0.0, _Z)),
            DroneInit(2, (4.0, 0.0, _Z), (-4.0, 0.0, _Z)),
            DroneInit(3, (0.0, 0.0, _Z), (0.0, 0.0, _Z)),
        ),
        notes='İtici vektör iptali (false-negative) düzeltmesini sınar.',
    ),
    Scenario(
        name='three_way_symmetric',
        category='coklu',
        description='3 drone 120° simetrik, hepsi merkezden karşıya geçer.',
        drones=_ring(3, 5.0, _Z, phase_deg=90.0),
        notes='Simetrik deadlock; teğet kaçış olmadan donar.',
    ),
    Scenario(
        name='four_corner_cross',
        category='coklu',
        description='4 drone köşelerden çapraz karşı köşeye geçer.',
        drones=(
            DroneInit(1, (5.0, 5.0, _Z), (-5.0, -5.0, _Z)),
            DroneInit(2, (5.0, -5.0, _Z), (-5.0, 5.0, _Z)),
            DroneInit(3, (-5.0, 5.0, _Z), (5.0, -5.0, _Z)),
            DroneInit(4, (-5.0, -5.0, _Z), (5.0, 5.0, _Z)),
        ),
    ),
    Scenario(
        name='antipodal_swap_6',
        category='coklu',
        description='6 drone çemberde, herkes karşı noktaya — yoğun çatışma.',
        drones=_ring(6, 5.0, _Z),
        notes='Klasik en zor test; merkezde 6 yol kesişir.',
    ),
]


# =====================================================================
# KATEGORİ D — DEADLOCK / KENAR DURUMLAR
# =====================================================================
_DEADLOCK = [
    Scenario(
        name='perfect_symmetric_headon',
        category='deadlock',
        description='Tam simetrik kafa kafaya (sıfır kaçık) — donma riski.',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (6.0, 0.0, _Z), (-6.0, 0.0, _Z)),
        ),
        notes='Teğet kaçış tetiklenmezse drone donar; en saf deadlock testi.',
    ),
    Scenario(
        name='local_minimum',
        category='deadlock',
        description='Engel, drone ile hedefi tam arasında (yerel minimum).',
        drones=(
            DroneInit(1, (-6.0, 0.0, _Z), (6.0, 0.0, _Z)),
            DroneInit(2, (0.0, 0.0, _Z), (0.0, 0.0, _Z)),
        ),
        notes='Çekici+itici zıt; teğet kuvvet olmadan klasik APF tuzağı.',
    ),
]


# =====================================================================
# KATEGORİ E — YÜKSEK HIZ (RVO modülasyonu)
# =====================================================================
_HIGH_SPEED = [
    Scenario(
        name='high_closing_speed',
        category='yuksek_hiz',
        description='Yüksek hızla kafa kafaya — geç tepki/aşım riski.',
        drones=(
            DroneInit(1, (-7.0, 0.0, _Z), (7.0, 0.0, _Z)),
            DroneInit(2, (7.0, 0.0, _Z), (-7.0, 0.0, _Z)),
        ),
        max_speed_mps=4.0,
        notes='Kapanış hızı modülasyonu erken/güçlü itki üretmeli.',
    ),
]


# =====================================================================
# KATEGORİ F — BİREY EKLE/ÇIKAR (görev akışı)
# =====================================================================
_MEMBER = [
    Scenario(
        name='member_detach_rejoin',
        category='birey',
        description='Bir drone ayrılıp iner (excluded); yedek tırmanıp girer.',
        drones=(
            DroneInit(1, (0.0, -3.0, _Z), (0.0, -3.0, _Z)),   # tut
            DroneInit(2, (0.0, 0.0, _Z), (0.0, 0.0, 0.0),     # ayrıl: dik in
                      excluded=True),
            DroneInit(3, (0.0, 3.0, _Z), (0.0, 3.0, _Z)),     # tut
            DroneInit(4, (-4.0, 0.0, -0.3), (0.0, 0.0, _Z)),  # katıl: tırman
        ),
        notes='Ayrılan excluded → diğerleri itmez (iniş bozulmasın); '
              'katılan REJOINING gibi normal kaçınma yapar.',
    ),
    Scenario(
        name='member_same_column',
        category='birey',
        description='Ayrılan dik iner, yedek AYNI kolondan tırmanır (zor).',
        drones=(
            DroneInit(1, (0.0, 0.0, _Z), (0.0, 0.0, 0.0),     # dik in
                      excluded=True),
            DroneInit(2, (0.0, 0.0, -0.3), (0.0, 0.0, _Z)),   # aynı kolon
        ),
        notes='Aynı dikey kolonda kafa kafaya; excluded yüzünden yatay '
              'kaçış yok → görev katmanının sıralaması gerektiğini sınar.',
        ca_solvable=False,
    ),
]


# =====================================================================
# KATEGORİ G — FORMASYON KORUMA (pertürbasyon → toparlanma)
# =====================================================================
def _okbasi_slots(
    n: int = 3, spacing: float = 5.0, alpha_deg: float = 30.0,
    center: tuple[float, float, float] = (0.0, 0.0, -15.0),
) -> list[tuple[float, float, float]]:
    """OKBAŞI formasyon slotlarını GERÇEK geometriyle üretir (shared NED).

    formation_node ile TEK kaynak: compute_slot_offsets aynı fonksiyon.
    heading=0 varsayımıyla offsetler merkeze eklenir. Index = rank = agent_id−1.
    """
    offs = compute_slot_offsets(
        FORMATION_OKBASI, n, spacing, math.radians(alpha_deg),
    )
    return [
        (center[0] + dx, center[1] + dy, center[2] + dz)
        for dx, dy, dz in offs
    ]


# spacing 5 m, alpha 30° → tüm ikili mesafeler 5 m (influence 3.5 dışında →
# normalde APF kapalı, formasyon bozulmaz). Pertürbasyon bir drone'u iter.
_OK = _okbasi_slots()
_OK_C, _OK_R, _OK_L = _OK[0], _OK[1], _OK[2]

_FORMATION = [
    Scenario(
        name='push_recover',
        category='formasyon',
        description='OKBASI hover; agent2 merkeze dogru itilir -> toparlanma.',
        drones=(
            DroneInit(1, _OK_C, _OK_C),   # merkez, slotta hover
            DroneInit(2, _OK_R, _OK_R),   # sağ kanat, slotta hover
            DroneInit(3, _OK_L, _OK_L),   # sol kanat, slotta hover
        ),
        # agent2'yi merkeze (agent1'e) doğru it: yön (+0.866,−0.5), 2.5 m/s, 1 s.
        perturbations=(
            Perturbation(2, 3.0, 4.0, (2.16, -1.25, 0.0)),
        ),
        check_slot_dev=True,
        notes='Dis itme agent2-agent1 mesafesini ~2m ye dusurur; APF '
              'carpismayi onlemeli, itme bitince SVT+goreli slota toplamali.',
    ),
    Scenario(
        name='push_recover_strong',
        category='formasyon',
        description='Sert ama gercekci itme (ruzgar darbesi): agent3 iceri.',
        drones=(
            DroneInit(1, _OK_C, _OK_C),
            DroneInit(2, _OK_R, _OK_R),
            DroneInit(3, _OK_L, _OK_L),
        ),
        # İtme 1.8 m/s — max_speed(2.0) ALTINDA. Daha güçlüsü (>max_speed)
        # drone'u "savuran fırtına" olur, fizik gereği kontrol tutamaz; bu
        # gerçekçi rüzgar darbesi, kontrol karşı koyabilir → slot_dev korunur.
        perturbations=(
            Perturbation(3, 3.0, 4.5, (1.5, 1.0, 0.0)),  # merkeze çapraz, 1.8 m/s
        ),
        check_slot_dev=True,
        notes='Uzun (1.5s) gercekci itme; tegset kacis + slot_dev clamp + '
              'SVT toparlama birlikte sinanir.',
    ),
    Scenario(
        name='slot_swap',
        category='formasyon',
        description='Iki kanat drone slotlarini degistirir (formasyon degisimi).',
        drones=(
            DroneInit(1, _OK_C, _OK_C),       # merkez sabit
            DroneInit(2, _OK_R, _OK_L),       # sağ → sol slota geç
            DroneInit(3, _OK_L, _OK_R),       # sol → sağ slota geç
        ),
        notes='Slot atamasi degisti; iki drone karsilikli gecerken carpismamali '
              '(formasyon degisimi / Macar yeniden atama senaryosu).',
    ),
]


# =====================================================================
# KATEGORİ H — SINIR STRESİ (clamp doğrulama)
# =====================================================================
_BOUNDARY = [
    Scenario(
        name='lateral_clamp_stress',
        category='sinir',
        description='Komsuya dogru surekli itme -> slot_dev clamp tavani tutar.',
        drones=(
            DroneInit(1, (0.0, 0.0, -15.0), (0.0, 0.0, -15.0)),    # sabit slot
            DroneInit(2, (0.0, 4.0, -15.0), (0.0, 4.0, -15.0)),    # 4 m doğuda
        ),
        # agent2'yi agent1'e doğru (−y, batı) SÜREKLİ it: clamp+APF dayanmalı.
        perturbations=(
            Perturbation(2, 2.0, 12.0, (0.0, -1.2, 0.0)),
        ),
        check_slot_dev=True,
        max_speed_mps=2.0,
        notes='Uzun sureli dis itme altinda APF carpismayi onler; slot_dev '
              'clamp drone u slot+tavan icinde tutmaya calisir (SVT geri ceker).',
    ),
    Scenario(
        name='vertical_squeeze',
        category='sinir',
        description='Ustteki drone alttan yukari itilir -> irtifa 30m yi asmaz.',
        drones=(
            DroneInit(1, (0.0, 0.0, -28.0), (0.0, 0.0, -28.0)),   # 28 m hover
            DroneInit(2, (0.0, 0.0, -24.0), (0.0, 0.0, -29.0)),   # alttan tirman
        ),
        expect_avoid=True,
        ca_solvable=False,  # dikey kafa-kafaya; CA tek başına çözmez, clamp testi
        notes='alt_max(30m) clamp dogrulamasi: agent1 yukari itilse de irtifasi '
              '30m yi asmamali (sartname s.13).',
    ),
]


# =====================================================================
# KATEGORİ I — DİNAMİK GÖREV İCRASI (TEKNOFEST §5.1, çok-fazlı)
# =====================================================================
# Jüri isteri: "dinamik görev icrası sırasında min mesafe-zaman grafiği".
# Görev çoğu zaman ~5 m aralıklı formasyonda (influence 3.5 dışı → CA kapalı);
# CA yalnızca YENİDEN YAPILANMA anlarında zorlanır: (1) formasyon değişimi
# (slot yeniden atama → kesişme), (2) birey ekle/çıkar. Bu senaryo bu iki
# CA-kritik fazı tek sürekli görev zaman çizelgesinde birleştirir.
# z=-15 m görev irtifası; başlangıç stabilize (kalkış offline'da yok).
_GZ = -15.0

# Okbaşı başlangıç (~5 m aralık, tüm ikililer influence 3.5 dışı → CA kapalı)
_OKB = (
    (3.0, 0.0, _GZ),     # d1 lider (ön/kuzey)
    (-1.5, 3.0, _GZ),    # d2 sağ kanat
    (-1.5, -3.0, _GZ),   # d3 sol kanat
)
# Çizgi (doğu ekseni): kanatlar yer değiştirir → kesişme (DİP 1)
_LINE = (
    (0.0, 0.0, _GZ),     # d1 merkez
    (0.0, -3.0, _GZ),    # d2 (sağdan sola geçer → d3 ile kesişir)
    (0.0, 3.0, _GZ),     # d3 (soldan sağa geçer)
)
# Birey çıkar: d2 görev alanındaki renkli bölgeye iner (irtifa düşer),
# diğerlerinin avoidance hesabından çıkar (excluded). d1/d3 boşluğu kapatır.
_DETACH = (
    (0.0, 1.5, _GZ),     # d1 boşluğa kayar (yeniden dağılım)
    (0.0, -3.0, -4.0),   # d2 alçalır (iniş)
    (0.0, -1.5, _GZ),    # d3 boşluğa kayar → d1'e yaklaşır (DİP 2)
)
# Birey ekle: d2 tekrar tırmanıp çizgi slotuna girer; d1/d3 yer açar.
_REJOIN = _LINE

def _form_slots(ftype: int, n: int = 3, spacing: float = 5.0,
                alpha_deg: float = 30.0,
                center: tuple = (0.0, 0.0, _GZ)) -> tuple:
    """Gerçek formation_geometry ile bir formasyon tipinin NED slotları.

    SITL formation_test_publisher ile TEK kaynak (compute_slot_offsets) →
    offline graf = SITL grafiği aynı geometri. Index = rank = agent_id-1.
    """
    offs = compute_slot_offsets(ftype, n, spacing, math.radians(alpha_deg))
    return tuple(
        (center[0] + dx, center[1] + dy, center[2] + dz)
        for dx, dy, dz in offs
    )


# SITL formation_change_test.sh ile birebir aynı sekans (çizgi→V→okbaşı→çizgi),
# gerçek slot geometrisiyle. Drone i daima rank i (tutarlı atama, doğal geçiş).
_F_CIZGI = _form_slots(FORMATION_CIZGI)
_F_V = _form_slots(FORMATION_V)
_F_OKB = _form_slots(FORMATION_OKBASI)


_GOREV = [
    Scenario(
        name='gorev_formasyon',
        category='gorev',
        description='TEKNOFEST §5.1 formasyon değişimi (SITL ile ayni sekans): '
                    'cizgi -> V -> okbasi -> cizgi, gercek slot geometrisi.',
        drones=(
            DroneInit(1, _F_CIZGI[0], _F_CIZGI[0]),
            DroneInit(2, _F_CIZGI[1], _F_CIZGI[1]),
            DroneInit(3, _F_CIZGI[2], _F_CIZGI[2]),
        ),
        phases=(
            Phase(4.0, _F_V, label='→ V'),
            Phase(16.0, _F_OKB, label='→ Okbaşı'),
            Phase(28.0, _F_CIZGI, label='→ Çizgi'),
        ),
        duration_s=40.0,
        notes='SITL-uçurulabilir tek faz: formasyon değişimi. Slot yeniden '
              'atama → yollar geçici yaklaşır; CA emniyeti korur. Birey '
              'ekle/çıkar SEPARATE (gorev_dinamik, offline-only).',
    ),
    Scenario(
        name='gorev_dinamik',
        category='gorev',
        description='TEKNOFEST §5.1 dinamik görev: formasyon degisimi + '
                    'birey ekle/cikar, tek surekli zaman cizelgesi.',
        drones=(
            DroneInit(1, _OKB[0], _OKB[0]),
            DroneInit(2, _OKB[1], _OKB[1]),
            DroneInit(3, _OKB[2], _OKB[2]),
        ),
        phases=(
            Phase(4.0, _LINE,
                  label='Formasyon değişimi (Okbaşı→Çizgi)'),
            Phase(18.0, _DETACH, excluded=(False, True, False),
                  label='Birey çıkar (iniş)'),
            Phase(30.0, _REJOIN, excluded=(False, False, False),
                  label='Birey ekle (katılım)'),
        ),
        duration_s=44.0,
        notes='CA-kritik fazlar: slot yeniden atama (kesisme) ve birey '
              'degisimi. Seyir/rotasyon fazlari rijit → CA tetiklenmez.',
    ),
]


SCENARIOS: tuple[Scenario, ...] = tuple(
    _PAIRWISE + _VERTICAL + _MULTI + _DEADLOCK + _HIGH_SPEED + _MEMBER
    + _FORMATION + _BOUNDARY + _GOREV
)

CATEGORIES = (
    'ikili', 'dikey', 'coklu', 'deadlock', 'yuksek_hiz', 'birey',
    'formasyon', 'sinir', 'gorev',
)


def get(name: str) -> Scenario:
    """İsme göre senaryo döndürür."""
    for s in SCENARIOS:
        if s.name == name:
            return s
    raise KeyError(f'Senaryo bulunamadı: {name}')


def by_category(category: str) -> list[Scenario]:
    """Bir kategorideki senaryoları döndürür."""
    return [s for s in SCENARIOS if s.category == category]


def summary() -> str:
    """Katalog özeti (kategori başına sayı)."""
    lines = [f'Toplam {len(SCENARIOS)} senaryo, {len(CATEGORIES)} kategori:']
    for cat in CATEGORIES:
        names = [s.name for s in by_category(cat)]
        lines.append(f'  {cat:12s} ({len(names)}): {", ".join(names)}')
    return '\n'.join(lines)


if __name__ == '__main__':
    print(summary())
