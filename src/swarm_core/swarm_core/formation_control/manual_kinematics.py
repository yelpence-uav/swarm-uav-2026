"""Yarı-otonom (Görev 2) manuel komut kinematiği — saf matematik, ROS yok.

Operatörün analog joystick eksenlerini ([-1, +1] normalize) sürü-seviyesi
hareketine çevirir. İki mod:

  * SÜRÜ HAREKET MODU (MODE_SWARM_MOVEMENT):
        Formasyon ŞEKLİ korunur, kütle merkezi (centroid) ötelenir.
        pitch -> +North hız, roll -> +East hız, throttle -> tırmanış,
        yaw -> tüm formasyonun heading dönüşü.
        Bireysel İHA hızı:  v_i = v_merkez + (ψ̇ × r_i)

  * MANEVRA MODU (MODE_MANEUVER):
        Centroid SABİT; formasyon merkez etrafında döner/eğilir.
        Öteleme yok (v_merkez -> 0, a_max ile sönümlenerek),
        yaw -> centroid etrafında saf dönme (v_i = ψ̇ × r_i, teğetsel),
        pitch/roll -> formasyon düzlemi eğimi (offset_z modülasyonu),
        throttle -> ortak irtifa değişimi.

İŞARET KONVANSİYONU (SwarmControlCommand.msg ile aynı, NED frame):
    pitch_cmd    > 0 : ileri (+North, +X)
    roll_cmd     > 0 : sağ   (+East,  +Y)
    yaw_cmd      > 0 : yukarıdan bakışta saat yönü (heading artar)
    throttle_cmd > 0 : tırmanış (irtifa artar -> NED Down/Z azalır)

İVME: analog girdi anlık hız HEDEFİ üretir; gerçek centroid hızı a_max·dt
adımıyla bu hedefe doğru "slew" (eğim-limit) edilir. Böylece |a| <= a_max
garanti edilir ve çıkışta hem hız hem ivme komutu sınırlı kalır. İvme,
hızdaki bu sınırlı değişimin dt'ye bölümüdür (StepResult.a*).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class MotionLimits:
    """Sürü-seviyesi hız/ivme/açısal hız tavanları."""

    v_max_xy: float = 3.0          # m/s, yatay centroid hızı
    v_max_z: float = 1.5           # m/s, dikey centroid hızı
    a_max_xy: float = 2.0          # m/s^2, yatay ivme tavanı
    a_max_z: float = 1.0           # m/s^2, dikey ivme tavanı
    yaw_rate_max_deg_s: float = 45.0   # deg/s, heading dönüş hızı
    tilt_max_deg: float = 15.0     # deg, manevra eğim genliği


@dataclass
class CentroidState:
    """Formasyon merkezinin anlık konum/hız/yön durumu (shared NED)."""

    x: float = 0.0                 # North (m)
    y: float = 0.0                 # East (m)
    z: float = 0.0                 # Down (m)
    heading_deg: float = 0.0
    vx: float = 0.0                # m/s North
    vy: float = 0.0                # m/s East
    vz: float = 0.0                # m/s Down


@dataclass
class StepResult:
    """Bir kinematik adımının çıktısı: yeni durum + komut metrikleri."""

    state: CentroidState
    ax: float = 0.0                # m/s^2 (uygulanan centroid ivmesi)
    ay: float = 0.0
    az: float = 0.0
    yaw_rate_deg_s: float = 0.0
    tilt_pitch_deg: float = 0.0    # formasyon düzlemi eğimi (manevra)
    tilt_roll_deg: float = 0.0
    offsets: list[tuple[float, float, float]] = field(default_factory=list)


def _slew(current: float, target: float, max_delta: float) -> float:
    """current'i target'e doğru en fazla |max_delta| adımıyla yaklaştırır.

    İvme sınırlamasının çekirdeği: hız bir adımda en çok a_max·dt değişebilir.
    """
    if max_delta <= 0.0:
        return current
    diff = target - current
    if diff > max_delta:
        return current + max_delta
    if diff < -max_delta:
        return current - max_delta
    return target


def _clamp(value: float, lo: float, hi: float) -> float:
    """value'yu [lo, hi] aralığına kırpar."""
    return max(lo, min(hi, value))


def _wrap_heading(deg: float) -> float:
    """Heading'i (-180, 180] aralığına sarar."""
    wrapped = (deg + 180.0) % 360.0 - 180.0
    # %, -180 için +180 üretebilir; tek noktayı normalize et.
    return 180.0 if wrapped == -180.0 else wrapped


def swarm_movement_step(
    state: CentroidState,
    pitch: float,
    roll: float,
    yaw: float,
    throttle: float,
    dt: float,
    limits: MotionLimits,
) -> StepResult:
    """SÜRÜ HAREKET MODU: centroid'i öteler, şekil korunur.

    Analog girdiler hız HEDEFİ üretir; gerçek hız a_max·dt ile slew edilir
    (ivme sınırı). Konum yeni hızla integre edilir, heading yaw ile döner.

    Args:
        state: Mevcut centroid durumu.
        pitch, roll, yaw, throttle: [-1, +1] normalize analog eksenler.
        dt: Adım süresi (s). <= 0 ise durum değişmeden döner.
        limits: Hız/ivme/açısal hız tavanları.

    Returns:
        StepResult: yeni durum + uygulanan ivme ve yaw hızı.
    """
    if dt <= 0.0:
        return StepResult(state=replace(state))

    pitch = _clamp(pitch, -1.0, 1.0)
    roll = _clamp(roll, -1.0, 1.0)
    yaw = _clamp(yaw, -1.0, 1.0)
    throttle = _clamp(throttle, -1.0, 1.0)

    # Analog -> hız hedefi (NED). throttle>0 tırmanış => Down hızı negatif.
    vx_des = pitch * limits.v_max_xy
    vy_des = roll * limits.v_max_xy
    vz_des = -throttle * limits.v_max_z

    # İvme-sınırlı slew (|Δv| <= a_max·dt).
    da_xy = limits.a_max_xy * dt
    da_z = limits.a_max_z * dt
    new_vx = _slew(state.vx, vx_des, da_xy)
    new_vy = _slew(state.vy, vy_des, da_xy)
    new_vz = _slew(state.vz, vz_des, da_z)

    ax = (new_vx - state.vx) / dt
    ay = (new_vy - state.vy) / dt
    az = (new_vz - state.vz) / dt

    # Konum integrasyonu.
    new_x = state.x + new_vx * dt
    new_y = state.y + new_vy * dt
    new_z = state.z + new_vz * dt

    # Heading dönüşü.
    yaw_rate = yaw * limits.yaw_rate_max_deg_s
    new_heading = _wrap_heading(state.heading_deg + yaw_rate * dt)

    new_state = CentroidState(
        x=new_x, y=new_y, z=new_z, heading_deg=new_heading,
        vx=new_vx, vy=new_vy, vz=new_vz,
    )
    return StepResult(
        state=new_state, ax=ax, ay=ay, az=az, yaw_rate_deg_s=yaw_rate,
    )


def maneuver_step(
    state: CentroidState,
    pitch: float,
    roll: float,
    yaw: float,
    throttle: float,
    dt: float,
    limits: MotionLimits,
) -> StepResult:
    """MANEVRA MODU: centroid sabit; formasyon döner/eğilir.

    Yatay öteleme yasak -> v_merkez a_max ile 0'a sönümlenir (artık atalet
    güvenli durur). yaw centroid etrafında saf dönme verir (formation_node
    R(heading)·offset uygular). pitch/roll formasyon düzlemini eğer
    (tilt_* dereceleri; offset_z modülasyonu çağıran tarafça uygulanır).
    throttle ortak irtifa değişimine izin verir.

    Returns:
        StepResult: yeni durum (x,y sabit) + tilt_pitch/roll dereceleri.
    """
    if dt <= 0.0:
        return StepResult(state=replace(state))

    pitch = _clamp(pitch, -1.0, 1.0)
    roll = _clamp(roll, -1.0, 1.0)
    yaw = _clamp(yaw, -1.0, 1.0)
    throttle = _clamp(throttle, -1.0, 1.0)

    # Yatay hızı güvenle 0'a çek (centroid sabit kalmalı).
    da_xy = limits.a_max_xy * dt
    da_z = limits.a_max_z * dt
    new_vx = _slew(state.vx, 0.0, da_xy)
    new_vy = _slew(state.vy, 0.0, da_xy)

    # Ortak irtifa hâlâ serbest.
    vz_des = -throttle * limits.v_max_z
    new_vz = _slew(state.vz, vz_des, da_z)

    ax = (new_vx - state.vx) / dt
    ay = (new_vy - state.vy) / dt
    az = (new_vz - state.vz) / dt

    # x, y SABİT (öteleme yok); sadece artık hız sönümlenir, konum kaymaz.
    new_z = state.z + new_vz * dt

    yaw_rate = yaw * limits.yaw_rate_max_deg_s
    new_heading = _wrap_heading(state.heading_deg + yaw_rate * dt)

    tilt_pitch = pitch * limits.tilt_max_deg
    tilt_roll = roll * limits.tilt_max_deg

    new_state = CentroidState(
        x=state.x, y=state.y, z=new_z, heading_deg=new_heading,
        vx=new_vx, vy=new_vy, vz=new_vz,
    )
    return StepResult(
        state=new_state, ax=ax, ay=ay, az=az,
        yaw_rate_deg_s=yaw_rate,
        tilt_pitch_deg=tilt_pitch, tilt_roll_deg=tilt_roll,
    )


def apply_tilt(
    offsets: list[tuple[float, float, float]],
    tilt_pitch_deg: float,
    tilt_roll_deg: float,
) -> list[tuple[float, float, float]]:
    """Formasyon düzlemini eğerek slot offset_z'lerini modüle eder (manevra).

    Eğim, body frame'de bir düzlem dönüşüdür (heading uygulanmadan ÖNCE,
    çünkü offset'ler body frame'dedir; formation_node sonra R(heading)
    uygular). NED Z aşağı pozitif olduğundan:

        pitch>0 (burun yukarı): ÖN slotlar (+x) YÜKSELİR -> dz azalır.
        roll>0  (sağ kanat aşağı): SAĞ slotlar (+y) ALÇALIR -> dz artar.

    dz_yeni = dz - x·tan(pitch) + y·tan(roll)

    Args:
        offsets: body frame (dx, dy, dz) listesi.
        tilt_pitch_deg, tilt_roll_deg: eğim açıları (derece).

    Returns:
        offset_z'si modüle edilmiş yeni (dx, dy, dz) listesi.
    """
    tp = math.tan(math.radians(tilt_pitch_deg))
    tr = math.tan(math.radians(tilt_roll_deg))
    if not offsets:
        return offsets

    # Ham z değişimi: eğim düzlemine göre her slotun yükselip alçalması.
    dz_delta = [-dx * tp + dy * tr for (dx, dy, _dz) in offsets]

    # MERKEZ SABİT KALMALI (şartname 5.1.2: "sürü merkezinin konumunu SABİT
    # tutarak eğilme"). Ham değişimin ortalaması genelde SIFIR DEĞİLDİR:
    # örn. okbaşında iki kanat geride (dx<0), pitch>0 ikisini de aşağı iter,
    # ortalama ≈ +1.44 m → tüm sürü aşağı KAYAR (ölçüldü: irtifa 14→10.5 m).
    # Çizgi formasyonunda simetri yüzünden ortalama 0 olduğu için fark
    # edilmiyordu; okbaşı/V gibi asimetrik formasyonlarda kayma çıkıyor.
    # Ortalamayı çıkarınca eğim korunur ama merkez sabitlenir: bazı slot
    # yukarı, bazı aşağı, net kayma 0.
    ort = sum(dz_delta) / len(dz_delta)

    out: list[tuple[float, float, float]] = []
    for (dx, dy, dz), delta in zip(offsets, dz_delta):
        out.append((dx, dy, dz + delta - ort))
    return out
