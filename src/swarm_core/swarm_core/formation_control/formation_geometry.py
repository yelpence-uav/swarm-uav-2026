"""Formasyon geometrisi — saf matematik, ROS yok.

Şartnamenin üç formasyon tipi için (Çizgi, Ok Başı, V) her drone'un
formasyon merkezine göre offset'ini hesaplar. Algoritma N'den bağımsız
(jenerik): 3, 5, 10, 20 drone ile aynı şekilde çalışır — sürüden birey
ayrılınca N azalır, yedek katılınca N artar, geometri otomatik tepki verir.

Notasyon:
    x_c, y_c, z_c : Formasyon merkezi (local NED, metre)
    u_b           : Drone aralığı (spacing) — QR'dan gelir
    alpha         : Ok Başı/V kanat açısı (radyan)
    theta         : Formasyon heading açısı (radyan)
    r             : Lider'den kanat boyunca sıra (1, 2, 3, ...)

Frame konvansiyonu:
    +X = North, +Y = East, +Z = Down (NED).
    Body frame'de heading=0 iken X ileri, Y sağdır.

Rank ataması:
    rank=0 daima lider/merkez (0, 0, 0).
    Ok Başı / V: rank 1 sağ kanat r=1, rank 2 sol kanat r=1,
                 rank 3 sağ kanat r=2, rank 4 sol kanat r=2, ...
    Çizgi: rank 1 sağ slot r=1, rank 2 sol slot r=1,
           rank 3 sağ slot r=2, rank 4 sol slot r=2, ...
           (Ok Başı/V ile aynı sağ-sol alternasyonu, dx=0.)
    Bu konvansiyon sayesinde drone'lar tüm formasyon tiplerinde
    tutarlı bir tarafta (sağ/sol) kalır; formasyon geçişlerinde
    lider yerinde durur, osilasyon (şartname -10 puan) azalır.

Güvenlik validasyonu:
    - alpha sınırı: 5°-85° (kanatların üst üste binmesini önler)
    - Min drone mesafesi: compute_min_drone_distance() ile hesaplanır,
      validate_formation_safety() ile doğrulanır (varsayılan 1.5m).
    - Çarpışma cezası -20×N olduğu için bu kontroller kritik.

Birey ayrılma desteği:
    Algoritma N parametresi ile çalışır. Drone ayrıldığında
    (PRECISION_LANDING → LANDED → DETACHED) sürü N-1'e düşer;
    kalan ranker'ler yeniden hesaplanır, sürü yeniden konuşlanır.
    Yedek (STANDBY) ajan katılınca N artar. Geometri kodunda hiçbir
    değişiklik gerekmez — N runtime'da güncel SwarmState'ten alınır.
"""

from __future__ import annotations

import math


# Formasyon tip kodları — FormationCommand.msg ile aynı tutulmalı.
FORMATION_UNKNOWN = 0
FORMATION_OKBASI = 1
FORMATION_V = 2
FORMATION_CIZGI = 3
FORMATION_CUSTOM = 99


# Offset tuple tipi: (dx, dy, dz), metre cinsinden.
Offset = tuple[float, float, float]


# Güvenlik sabitleri — formasyon konfigürasyonunun fiziksel olarak
# uygulanabilir olmasını sağlar.

# Drone fiziksel boyutu ~50cm (F450) + rotor downwash + GPS hatası
# + güvenlik marjı. Şartname -20×N çarpışma cezasını önler.
DEFAULT_MIN_DRONE_DISTANCE_M = 1.5

# Ok Başı / V kanat açısı sınırları:
# Çok küçükse (alpha→0): kanatlar -X/+X ekseninde üst üste biner
# Çok büyükse (alpha→90°): formasyon dejenere olur (Çizgi'ye dönüşür)
_MIN_ALPHA_RAD = math.radians(5.0)
_MAX_ALPHA_RAD = math.radians(85.0)


def compute_slot_offsets(
    formation_type: int,
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """
    N drone için heading=0 varsayımıyla slot offsetlerini döndürür.

    Args:
        formation_type (int): FORMATION_* sabitlerinden biri.
        total (int): Aktif drone sayısı (>=1).
        spacing (float): Drone aralığı u_b, metre.
        alpha_rad (float): Kanat açısı, radyan. Sadece OKBASI ve V
            için kullanılır; CIZGI için yok sayılır.

    Returns:
        list: Uzunluğu `total` olan (dx, dy, dz) offset listesi.
            Index = rank. rank=0 daima (0, 0, 0).

    Raises:
        ValueError: total<=0, spacing<=0 veya bilinmeyen
            formation_type için.
    """
    if total <= 0:
        raise ValueError(f'total >= 1 olmali, geldi: {total}')
    if spacing <= 0.0:
        raise ValueError(f'spacing > 0 olmali, geldi: {spacing}')

    # Ok Basi / V kanat acisi gecerli araligin disinda olamaz.
    # Cok kucuk -> kanatlar ust uste biner (carpisma).
    # Cok buyuk -> formasyon dejenere olur.
    if formation_type in (FORMATION_OKBASI, FORMATION_V):
        if alpha_rad < _MIN_ALPHA_RAD or alpha_rad > _MAX_ALPHA_RAD:
            raise ValueError(
                f'alpha {math.degrees(alpha_rad):.1f}° araligin disinda '
                f'({math.degrees(_MIN_ALPHA_RAD):.0f}°-'
                f'{math.degrees(_MAX_ALPHA_RAD):.0f}°). '
                'Ok Basi/V kanat acisi bu sinirlar icinde olmali.'
            )

    if formation_type == FORMATION_CIZGI:
        return _slots_cizgi(total, spacing)
    if formation_type == FORMATION_OKBASI:
        return _slots_okbasi(total, spacing, alpha_rad)
    if formation_type == FORMATION_V:
        return _slots_v(total, spacing, alpha_rad)

    raise ValueError(
        f'Desteklenmeyen formation_type: {formation_type}'
    )


def compute_min_drone_distance(
    formation_type: int,
    spacing: float,
    alpha_rad: float,
) -> float:
    """
    Formasyondaki en yakin iki drone arasindaki mesafeyi doner.

    Carpisma riski analizi icin kullanilir. Sonuc
    DEFAULT_MIN_DRONE_DISTANCE_M altinda ise formasyon
    konfigurasyonu guvensizdir.

    Cizgi: spacing (Y ekseninde komsu drone'lar)
    Ok Basi/V:
        - Lider-kanat mesafesi = spacing
        - Sag-sol kanat (ayni r) = 2*spacing*sin(alpha)
        - En kucugu doner

    Args:
        formation_type: FORMATION_* sabiti.
        spacing: Drone arali u_b, metre.
        alpha_rad: Kanat acisi, radyan (CIZGI icin yok sayilir).

    Returns:
        En kucuk drone-arasi mesafe, metre. Bilinmeyen
        formation_type icin spacing doner.
    """
    if formation_type == FORMATION_CIZGI:
        return float(spacing)
    if formation_type in (FORMATION_OKBASI, FORMATION_V):
        wing_pair = 2.0 * spacing * math.sin(alpha_rad)
        return float(min(spacing, wing_pair))
    return float(spacing)


def validate_formation_safety(
    formation_type: int,
    spacing: float,
    alpha_rad: float,
    min_distance_m: float = DEFAULT_MIN_DRONE_DISTANCE_M,
) -> None:
    """
    Formasyon konfigurasyonunun fiziksel olarak guvenli oldugunu dogrular.

    En yakin iki drone arasi mesafenin min_distance_m'den buyuk
    oldugunu kontrol eder. Aksi halde ValueError firlatir.

    Bu kontrol mission_fsm/orkestrator tarafindan QR'dan gelen
    parametreler uygulanmadan once cagrilmalidir.

    Args:
        formation_type: FORMATION_* sabiti.
        spacing: Drone arali, metre.
        alpha_rad: Kanat acisi, radyan.
        min_distance_m: Minimum guvenli mesafe (varsayilan 1.5m).

    Raises:
        ValueError: Drone'lar arasi mesafe esikten kucukse.
    """
    actual = compute_min_drone_distance(
        formation_type, spacing, alpha_rad
    )
    if actual < min_distance_m:
        raise ValueError(
            f'Guvensiz formasyon: en yakin drone arasi mesafe '
            f'{actual:.2f}m, minimum {min_distance_m:.2f}m olmali. '
            f'spacing veya alpha artirilmali.'
        )


def _slots_cizgi(total: int, spacing: float) -> list[Offset]:
    """
    Çizgi formasyonu için slot offsetleri.

    Drone'lar heading'e dik eksende (body Y) eşit aralıkta dizilir.
    Lider (rank 0) merkezde; kalan drone'lar sağ-sol simetrik açılır
    (Ok Başı/V ile aynı atama mantığı, dx=0). Bu sayede formasyon
    geçişlerinde lider yerinde kalır, osilasyon azalır.

    Args:
        total (int): Drone sayısı.
        spacing (float): Aralık, metre.

    Returns:
        list: (dx, dy, dz) offset listesi.
    """
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        offsets.append((0.0, side * r * spacing, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def _slots_okbasi(
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """
    Ok Başı formasyonu için slot offsetleri.

    Lider merkezde (0,0,0); kanatlar arka tarafa (-X) açılır.

    Args:
        total (int): Drone sayısı.
        spacing (float): Aralık, metre.
        alpha_rad (float): Kanat açısı, radyan.

    Returns:
        list: (dx, dy, dz) offset listesi.
    """
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        dx = -r * spacing * math.cos(alpha_rad)
        dy = side * r * spacing * math.sin(alpha_rad)
        offsets.append((dx, dy, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def _slots_v(
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """
    V formasyonu için slot offsetleri.

    Lider merkezde (0,0,0); kanatlar ön tarafa (+X) açılır.

    Args:
        total (int): Drone sayısı.
        spacing (float): Aralık, metre.
        alpha_rad (float): Kanat açısı, radyan.

    Returns:
        list: (dx, dy, dz) offset listesi.
    """
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        dx = +r * spacing * math.cos(alpha_rad)
        dy = side * r * spacing * math.sin(alpha_rad)
        offsets.append((dx, dy, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def rotate_offset(
    dx: float,
    dy: float,
    heading_rad: float,
) -> tuple[float, float]:
    """
    Body frame offsetini formasyon heading'i kadar Z ekseninde döndürür.

    NED konvansiyonu (saat yönü pozitif yaw) için:
        rx = dx * cos(h) - dy * sin(h)
        ry = dx * sin(h) + dy * cos(h)

    Args:
        dx (float): Body frame X offset, metre.
        dy (float): Body frame Y offset, metre.
        heading_rad (float): Formasyon heading açısı, radyan.

    Returns:
        tuple: (rx, ry) NED frame'de döndürülmüş offset.
    """
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)
    rx = dx * cos_h - dy * sin_h
    ry = dx * sin_h + dy * cos_h
    return rx, ry


def compute_setpoint(
    center_x: float,
    center_y: float,
    center_z: float,
    formation_type: int,
    rank: int,
    total: int,
    spacing: float,
    alpha_rad: float,
    heading_rad: float,
) -> tuple[float, float, float]:
    """
    Tek bir drone'un formasyon setpoint'ini NED frame'de hesaplar.

    Args:
        center_x (float): Formasyon merkezi X (NED kuzey), metre.
        center_y (float): Formasyon merkezi Y (NED doğu), metre.
        center_z (float): Formasyon merkezi Z (NED aşağı), metre.
        formation_type (int): FORMATION_* sabiti.
        rank (int): Drone'un sıra numarası (0..total-1).
        total (int): Toplam aktif drone sayısı.
        spacing (float): Drone aralığı u_b, metre.
        alpha_rad (float): Kanat açısı, radyan.
        heading_rad (float): Formasyon heading, radyan.

    Returns:
        tuple: (target_x, target_y, target_z) NED hedef koordinatı.

    Raises:
        ValueError: rank aralık dışındaysa veya parametreler geçersizse.
    """
    if rank < 0 or rank >= total:
        raise ValueError(
            f'rank {rank} aralik disi (0..{total - 1})'
        )

    offsets = compute_slot_offsets(
        formation_type, total, spacing, alpha_rad
    )
    dx, dy, dz = offsets[rank]
    rx, ry = rotate_offset(dx, dy, heading_rad)
    return center_x + rx, center_y + ry, center_z + dz
