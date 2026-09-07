# Copyright 2026 Yelpence
"""Sürü manevra modu hesaplama modülü (Görev 2, MANEVRA).

EĞİM MATEMATİĞİ TEK KAYNAKTAN: `manual_kinematics.apply_tilt`. Bu modülün
ilk yazımı kendi kopyasını taşıyordu ve o kopyada Görev 1 tarafında
ÖLÇÜLEREK düzeltilen hata aynen duruyordu (apply_tilt docstring'i:
asimetrik formasyonda — okbaşı/V — ham dz'nin ortalaması sıfır olmadığı
için bütün sürü kayıyordu, 14→10,5 m ölçüldü). Ayrıca roll işareti
Görev 1 sözleşmesinin TERSİYDİ (-oy·sin yerine +dy·tan olmalı: roll>0 =
sağa yatış = sağdaki slot AŞAĞI). Şartname 5.2.2 "sürü merkezi sabit
tutularak" diyor; ortalama-çıkarma o şartın kendisi.

Kumanda-yön eşlemesinin (çubuk ileri = hangi işaret) son sözü yerde
ölçülür — G0 işaret-yönü testi (komsu_adaptoru geleneği).
"""

import math

from swarm_core.formation_control.formation_geometry import (
    FORMATION_OKBASI,
    FORMATION_V,
)
from swarm_core.formation_control.manual_kinematics import apply_tilt, slew


def stick_maskesi(
    formation_type: int,
    pitch_cmd: float,
    roll_cmd: float,
) -> tuple[float, float]:
    """Manevrada formasyon tipine göre hangi stick etkili (3 Eylül, operatör).

    Manevra modu formasyonu DEĞİŞTİRMEZ — yalnız stick'lerin anlamı eğime
    döner. Hangi eğimin anlamlı olduğu diziliş geometrisine bağlı:

    - **Çizgi** (uçaklar y-ekseninde dizili, dx=0): yalnız **ROLL**. Pitch
      apply_tilt'te zaten dz üretmez (dz = -dx·tan(pitch), dx=0) ama uçaklar
      tam hizada değilse ufak dx istenmeyen dz verebilir — o yüzden pitch
      EXPLICIT sıfırlanır.
    - **V / ters okbaşı** (hem x hem y yayılım): **ROLL + PITCH** ikisi de.
    - **Formasyonsuz/UNKNOWN**: güvenli taraf — yalnız roll (çizgi gibi).

    Yaw bu maskeye GİRMİYOR — ayrı ele alınacak (operatör: "sonra yaw'a
    bakacağız"). Çağıran ctx.yaw_cmd'yi olduğu gibi kullanmaya devam eder.
    """
    if formation_type in (FORMATION_V, FORMATION_OKBASI):
        return pitch_cmd, roll_cmd
    return 0.0, roll_cmd


def _egik_ofsetler(
    formation_offsets: dict[int, tuple[float, float, float]],
    pitch_deg: float,
    roll_deg: float,
) -> dict[int, tuple[float, float, float]]:
    """Ofsetleri apply_tilt'ten geçirip kimliğe geri eşler.

    Sıralama kimliğe göre SABİT: apply_tilt liste alır, ortalamayı
    listeden çıkarır — çağrılar arasında sıra değişirse sonuç değişmez
    ama okunabilirlik için deterministik tutuluyor.
    """
    sirali = sorted(formation_offsets.items())
    egik = apply_tilt([ofs for _aid, ofs in sirali], pitch_deg, roll_deg)
    return {aid: egik[i] for i, (aid, _ofs) in enumerate(sirali)}


def compute_agent_setpoints(
    ctx,
    dt: float,
    formation_offsets: dict[int, tuple[float, float, float]],
) -> tuple[list[dict], float, float, float, float]:
    """Her İHA için manevra konum setpoint'lerini hesaplar.

    🔴 EĞİM RAMPALI — 6 Eylül 2026, SAHADA GÖRÜLDÜ.

    BELİRTİ (operatör): *"roll manevrası iyi oturmadı; ortadaki uçak sabit
    görünüyordu ama diğer ikisi biri yukarı biri aşağı gidip oturması
    gerekirken kumandaya DİRENİR gibi davrandı ve irtifa noktasında sıkıntı
    yaptı."*

    KÖK NEDEN: burada rampa YOKTU. Hareket modu B6'da rampalandı
    (`mode_context.compute_centroid_delta`, `slew`, `MOD_IVME`) ama manevra
    çubuğu ANINDA açıya çeviriyordu. Kanat slotu için bu, tek bir tick'te
    bir KONUM BASAMAĞI demek — ölçülen geometriyle:

        aralık 6 m, çubuk %66 -> eğim 9.9° -> kanat dz 1.05 m
        20 Hz'de tek tick = 0.05 s  ->  basamağın türevi 20.9 m/s

    Aynı çubuk hareket modunda tick başına en fazla 0.065 m/s değiştiriyor;
    yani manevra ~300 kat sert bir komut basıyordu. Bu, 5 Eylül'de kapatılan
    yalpanın aynı sınıfı (basamak atan hedef -> aşağıda türev alınınca
    darbe) ve şartname bunu ayrıca cezalandırıyor: "Osilasyon gözlemlenmesi
    -10" (Kriter 5).

    Rampa `slew` ile — `mode_context`'in kullandığı AYNI fonksiyon, ikinci
    kopya yok. Hız tavanı `ctx.max_tilt_rate_deg_s`; türetmesi (PX4'ün
    MPC_Z_VEL_MAX_UP'ından) `ucus_ayarlari.MOD_EGIM_HIZI_DEG_S`'te.
    **0.0 = rampa KAPALI**, eski davranış birebir döner (geri dönüş
    anahtarı; `vff_pencere_s=0.0` ile aynı gelenek).

    RAMPANIN DURUMU `ctx.maneuver_pitch_deg` / `maneuver_roll_deg`: ayrı bir
    alan AÇILMADI çünkü çağıran (`_dispatch_maneuver`) bu ikisini zaten geri
    yazıyor ve `compute_hold_setpoints` ile susturma kapısı da onları
    okuyor. Ayrı durum tutmak üçüncü bir kopya olurdu.

    Args:
        ctx (ModeContext): Sürü modu çalışma zamanı bağlamı.
        dt (float): Zaman adımı farkı (saniye).
        formation_offsets (dict): İHA ID bazlı (ox, oy, oz) ofsetleri.

    Returns:
        tuple[list[dict], float, float, float, float]: İHA setpoint listesi,
            yeni heading (derece), UYGULANAN pitch (derece), UYGULANAN roll
            (derece), yeni centroid_z (NED). Son üçü çağıran tarafından
            ctx'e geri yazılır — rampanın ve gazın durumu orada yaşıyor.
    """
    new_heading = ctx.compute_heading_rotation(ctx.yaw_cmd, dt)

    # 🔴 GAZ ÇUBUĞU centroid_z'ye ENTEGRE EDİLİR (6 Eylül). Önceden delta
    # doğrudan setpoint'e ekleniyor, centroid'e hiç yazılmıyordu — yani
    # birikmiyordu ve çubuk pratikte ÖLÜYDÜ. Gerekçe ve ölçüm:
    # mode_context.compute_centroid_dz docstring'i. Şartname G4:
    # "throttle = toplu irtifa".
    new_cz = ctx.centroid_z + ctx.compute_centroid_dz(ctx.throttle_cmd, dt)

    # Formasyon tipine göre stick maskesi: çizgide yalnız roll, V/okbaşında
    # roll+pitch (3 Eylül operatör kararı). Yaw maskeye girmez.
    pitch_cmd, roll_cmd = stick_maskesi(
        int(getattr(ctx, 'active_formation', 0)),
        ctx.pitch_cmd,
        ctx.roll_cmd,
    )
    hedef_pitch_deg = pitch_cmd * ctx.max_tilt_deg
    hedef_roll_deg = roll_cmd * ctx.max_tilt_deg

    hiz = float(getattr(ctx, 'max_tilt_rate_deg_s', 0.0))
    if hiz > 0.0:
        da = hiz * max(0.0, dt)
        target_pitch_deg = slew(ctx.maneuver_pitch_deg, hedef_pitch_deg, da)
        target_roll_deg = slew(ctx.maneuver_roll_deg, hedef_roll_deg, da)
    else:
        target_pitch_deg = hedef_pitch_deg
        target_roll_deg = hedef_roll_deg

    egik = _egik_ofsetler(
        formation_offsets, target_pitch_deg, target_roll_deg
    )

    heading_rad = math.radians(new_heading)
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []
    for agent_id, (ox, oy, _oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h
        # Eğim yalnız z'yi modüle eder (apply_tilt xy'ye dokunmaz);
        # merkez sabitliği apply_tilt'in ortalama-çıkarmasıyla garanti.
        ez = egik[agent_id][2]

        setpoints.append({
            'agent_id': agent_id,
            'x': ctx.centroid_x + rx,
            'y': ctx.centroid_y + ry,
            'z': new_cz + ez,
            'heading_deg': new_heading,
        })

    return (setpoints, new_heading, target_pitch_deg, target_roll_deg,
            new_cz)


def compute_hold_setpoints(
    ctx,
    formation_offsets: dict[int, tuple[float, float, float]],
) -> list[dict]:
    """HOLD durumunda her İHA'nın mevcut eğimli konumunu korur.

    Args:
        ctx (ModeContext): Sürü modu çalışma zamanı bağlamı.
        formation_offsets (dict): İHA ID bazlı (ox, oy, oz) ofsetleri.

    Returns:
        list[dict]: Sabit konum İHA setpoint listesi.
    """
    egik = _egik_ofsetler(
        formation_offsets, ctx.maneuver_pitch_deg, ctx.maneuver_roll_deg
    )

    heading_rad = math.radians(ctx.formation_heading_deg)
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)

    setpoints = []
    for agent_id, (ox, oy, _oz) in formation_offsets.items():
        rx = ox * cos_h - oy * sin_h
        ry = ox * sin_h + oy * cos_h
        ez = egik[agent_id][2]

        setpoints.append({
            'agent_id': agent_id,
            'x': ctx.centroid_x + rx,
            'y': ctx.centroid_y + ry,
            'z': ctx.centroid_z + ez,
            'heading_deg': ctx.formation_heading_deg,
        })

    return setpoints
