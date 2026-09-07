# Copyright 2026 Yelpence
"""MANEVRA MODU — egim rampasi ve gaz entegrasyonu (6 Eylul 2026).

Iki ayri kusuru kilitliyor; ikisi de SAHADA GORULDU ve ikisi de "hata
vermeden yanlis sonuc" sinifindaydi.

BELIRTI (operator, roll manevrasi): *"ortadaki ucak sabit gorunuyordu ama
diger iki ucak biri yukari biri asagi gidip oturmasi gerekirken sanki
kumandaya DIRENIR gibi davraniyordu ve IRTIFA noktasinda sikinti
yapiyordu."*

KUSUR 1 — EGIM RAMPASI YOKTU. `target_roll_deg = roll_cmd * max_tilt_deg`
cubugu ANINDA aciya ceviriyordu. Kanat slotu icin bu tek tick'te bir konum
basamagi: aralik 6 m / cubuk %66 -> 1.05 m, 20 Hz'de turevi 20.9 m/s. Ayni
cubuk HAREKET modunda (B6 rampasi) tick basina en fazla 0.065 m/s
degistiriyor. Sartname: "Osilasyon gozlemlenmesi -10".

KUSUR 2 — GAZ CUBUGU OLUYDU. `dz_throttle` dogrudan setpoint'e ekleniyor,
`centroid_z`'ye HIC yazilmiyordu; yani birikmiyordu. 20 Hz'de tam gaz
2.0 * 0.05 = 0.10 m SABIT ofset uretiyordu, 2 m/s tirmanma degil. Cubuk
birakilinca o da gidiyordu. Sartname G4: "throttle = toplu irtifa".
"""

import math
import unittest

from swarm_core.formation_control.formation_geometry import FORMATION_V
from swarm_state_machine.mode_manager.maneuver_mode import (
    compute_agent_setpoints,
)
from swarm_state_machine.mode_manager.mode_context import ModeContext

# Nominal saha ayari: ucus_ayarlari MOD_* degerleri.
_EGIM_TAVANI_DEG = 15.0
_EGIM_HIZI_DEG_S = 8.25      # MOD_EGIM_HIZI_DEG_S (turetilmis)
_HIZ_MPS = 2.0               # MOD_HIZ_MPS
_DIKEY_IVME = 1.0            # MOD_DIKEY_IVME_MPS2
_TICK_S = 0.05               # tick_hz = 20


def _ctx(**kw):
    """Manevraya hazir baglam. Ofsetler cagiranda."""
    ctx = ModeContext(agent_ids=[1, 2, 3])
    ctx.centroid_x = 0.0
    ctx.centroid_y = 0.0
    ctx.centroid_z = -10.0
    ctx.formation_heading_deg = 0.0
    ctx.max_tilt_deg = _EGIM_TAVANI_DEG
    ctx.max_tilt_rate_deg_s = _EGIM_HIZI_DEG_S
    ctx.max_speed_mps = _HIZ_MPS
    ctx.max_accel_z_mps2 = _DIKEY_IVME
    ctx.active_formation = FORMATION_V
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


# Cizgi benzeri: lider ortada (slot 0), kanatlar +-7 m. Roll bu dizilimde
# kanatlari zit yonlere iter, lider sabit kalir (ortalama 0).
_CIZGI_7M = {1: (0.0, 0.0, 0.0), 2: (0.0, 7.0, 0.0), 3: (0.0, -7.0, 0.0)}


class TestEgimRampasi(unittest.TestCase):
    """KUSUR 1 — egim cubugu ANINDA takip etmemeli."""

    def test_tek_tickte_tavana_FIRLAMAZ(self):
        """Cubuk tam basili: ilk tick'te egim rampa hizi kadar artar."""
        ctx = _ctx(roll_cmd=1.0)
        _sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
        )
        self.assertAlmostEqual(roll_deg, _EGIM_HIZI_DEG_S * _TICK_S, places=9)
        self.assertLess(roll_deg, _EGIM_TAVANI_DEG)

    def test_rampa_tavana_ULASIR(self):
        """Yeterince tick sonra istenen egime tam oturur, asmaz."""
        ctx = _ctx(roll_cmd=1.0)
        roll_deg = 0.0
        # 15 deg / 8.25 deg/s = 1.82 s -> 20 Hz'de ~37 tick. 60 bol bol.
        for _ in range(60):
            ctx.maneuver_roll_deg = roll_deg
            _sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
        self.assertAlmostEqual(roll_deg, _EGIM_TAVANI_DEG, places=6)

    def test_kanat_dikey_hizi_PX4_TAVANININ_ALTINDA(self):
        """🔴 Rampanin VAROLUS SEBEBI: slot PX4'ten hizli kacmamali.

        Kanat slotunun dikey hizi MPC_Z_VEL_MAX_UP'i (1.2 m/s, ucaktan
        OLCULDU) asarsa PX4 ustunu SESSIZCE kirpar; slot ucagin onunden
        kacar ve formasyon manevra boyunca dagilir.
        """
        px4_dikey_tavan = 1.2
        ctx = _ctx(roll_cmd=1.0)
        roll_deg = 0.0
        onceki_z = None
        en_yuksek_hiz = 0.0
        for _ in range(60):
            ctx.maneuver_roll_deg = roll_deg
            sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            z = {s['agent_id']: s['z'] for s in sp}[2]
            if onceki_z is not None:
                en_yuksek_hiz = max(en_yuksek_hiz,
                                    abs(z - onceki_z) / _TICK_S)
            onceki_z = z
        self.assertLessEqual(en_yuksek_hiz, px4_dikey_tavan)

    def test_rampasiz_hal_PX4_TAVANINI_ASIYORDU(self):
        """Regresyon kaydi: eski davranis (rampa 0.0) tavani asiyor.

        Bu test duzeltmenin GEREKLI oldugunu kanitliyor — sayiyi
        buyuttugumuzde ya da rampa kazara kapandiginda sessiz kalmasin.
        """
        ctx = _ctx(roll_cmd=1.0, max_tilt_rate_deg_s=0.0)
        sp, _h, _p, _r, _cz = compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
        )
        z = {s['agent_id']: s['z'] for s in sp}[2]
        # Tek tick'te olusan yer degistirme / dt = fiili komut hizi.
        hiz = abs(z - (-10.0)) / _TICK_S
        self.assertGreater(hiz, 1.2)
        # 7 m'de tam egim: 7*tan(15) = 1.88 m, 0.05 s'de -> 37.5 m/s.
        self.assertAlmostEqual(
            hiz, 7.0 * math.tan(math.radians(15.0)) / _TICK_S, places=6)

    def test_rampa_KAPALI_iken_eski_davranis_BIREBIR(self):
        """0.0 = geri donus anahtari; egim aninda hedefe gider."""
        ctx = _ctx(roll_cmd=1.0, max_tilt_rate_deg_s=0.0)
        _sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
        )
        self.assertAlmostEqual(roll_deg, _EGIM_TAVANI_DEG, places=9)

    def test_cubuk_birakilinca_SIFIRA_da_rampali_doner(self):
        """Geri donus de rampali — birakinca da basamak atmamali."""
        ctx = _ctx(roll_cmd=0.0, maneuver_roll_deg=_EGIM_TAVANI_DEG)
        _sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
        )
        self.assertAlmostEqual(
            roll_deg, _EGIM_TAVANI_DEG - _EGIM_HIZI_DEG_S * _TICK_S,
            places=9)

    def test_dt_sifir_GUVENLI(self):
        """dt=0 (ayni tick iki kez) egimi kimildatmaz, coksmez."""
        ctx = _ctx(roll_cmd=1.0, maneuver_roll_deg=4.0)
        _sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
            ctx, dt=0.0, formation_offsets=_CIZGI_7M,
        )
        self.assertAlmostEqual(roll_deg, 4.0, places=9)

    def test_rampa_sirasinda_MERKEZ_SABIT(self):
        """Egim rampalanirken de sürü merkezi kaymamali (sartname G4).

        apply_tilt'in ortalama-cikarmasi rampali acida da gecerli olmali.
        """
        ctx = _ctx(roll_cmd=1.0)
        roll_deg = 0.0
        for _ in range(20):
            ctx.maneuver_roll_deg = roll_deg
            sp, _h, _p, roll_deg, _cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            ort_z = sum(s['z'] for s in sp) / len(sp)
            self.assertAlmostEqual(ort_z, -10.0, places=9)


class TestManevraGazCubugu(unittest.TestCase):
    """KUSUR 2 — gaz cubugu centroid_z'ye ENTEGRE edilmeli."""

    def test_gaz_centroid_z_yi_BIRIKTIRIR(self):
        """Her tick birikiyor mu — eski kodda sabit 0.10 m kaliyordu."""
        ctx = _ctx(throttle_cmd=1.0)
        cz = ctx.centroid_z
        for _ in range(10):
            _sp, _h, _p, _r, cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            ctx.centroid_z = cz
        # Dikey ivme 1.0 m/s2 ile 10 tick (0.5 s) sonunda hiz 0.5 m/s,
        # yol = ort(0..0.5)*0.5 mertebesinde — ama KESIN olcut: eski
        # davranisin tek-tick ofsetinden (0.10 m) buyuk ve tirmaniyor.
        self.assertLess(cz, -10.10)

    def test_gaz_dikey_IVME_ile_rampali(self):
        """Ilk tick'te hiz max_accel_z * dt kadar — aninda tavana degil."""
        ctx = _ctx(throttle_cmd=1.0)
        _sp, _h, _p, _r, cz = compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
        )
        beklenen_v = _DIKEY_IVME * _TICK_S          # 0.05 m/s
        self.assertAlmostEqual(ctx.v_yukari, beklenen_v, places=9)
        # NED: yukari = z azalir.
        self.assertAlmostEqual(cz, -10.0 - beklenen_v * _TICK_S, places=9)

    def test_gaz_tavana_DOYAR(self):
        """Yeterince tick sonra dikey hiz max_speed_mps'e oturur."""
        ctx = _ctx(throttle_cmd=1.0)
        for _ in range(200):
            _sp, _h, _p, _r, cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            ctx.centroid_z = cz
        self.assertAlmostEqual(ctx.v_yukari, _HIZ_MPS, places=9)

    def test_gaz_merkezdeyken_irtifa_KIMILDAMAZ(self):
        """Cubuk merkezde: rampa 0'da durur, centroid_z sabit."""
        ctx = _ctx(throttle_cmd=0.0)
        for _ in range(50):
            _sp, _h, _p, _r, cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            ctx.centroid_z = cz
        self.assertAlmostEqual(ctx.centroid_z, -10.0, places=9)

    def test_gaz_ile_egim_BIRLIKTE_calisir(self):
        """Toplu irtifa + egim ayni anda: merkez tirmanir, egim korunur.

        Sartname G4 ikisini AYNI ANDA istiyor (throttle = toplu irtifa,
        pitch/roll = duzlem egimi). Kanatlarin ortalamasi merkezi verir.
        """
        ctx = _ctx(throttle_cmd=1.0, roll_cmd=1.0)
        roll_deg = 0.0
        cz = ctx.centroid_z
        for _ in range(20):
            ctx.maneuver_roll_deg = roll_deg
            sp, _h, _p, roll_deg, cz = compute_agent_setpoints(
                ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M,
            )
            ctx.centroid_z = cz
        z = {s['agent_id']: s['z'] for s in sp}
        # Merkez yukselmis (NED z azalmis)
        self.assertLess(cz, -10.0)
        # Kanatlar zit yonlerde ve ortalamalari merkezde
        self.assertAlmostEqual(sum(z.values()) / 3.0, cz, places=9)
        self.assertGreater(z[2], z[3])
        self.assertGreater(roll_deg, 0.0)


class TestDikeyRampaTekKaynak(unittest.TestCase):
    """HAREKET ve MANEVRA ayni dikey rampayi paylasmali."""

    def test_hareket_ve_manevra_AYNI_fonksiyonu_kullanir(self):
        """compute_centroid_delta'nin dz'si compute_centroid_dz ile ayni.

        Iki kopya olsaydi biri gun gelip otekinden kayardi — bu depoda
        "ayni sabiti iki yere yazma" kurali (CLAUDE.md §9).
        """
        a = _ctx(throttle_cmd=0.7)
        b = _ctx(throttle_cmd=0.7)
        _dx, _dy, dz_hareket = a.compute_centroid_delta(
            0.0, 0.0, 0.7, _TICK_S)
        dz_manevra = b.compute_centroid_dz(0.7, _TICK_S)
        self.assertAlmostEqual(dz_hareket, dz_manevra, places=12)
        self.assertAlmostEqual(a.v_yukari, b.v_yukari, places=12)

    def test_moddan_moda_gecerken_dikey_hiz_SICRAMAZ(self):
        """v_yukari tek durumda: HAREKET'ten MANEVRA'ya gecis surekli."""
        ctx = _ctx(throttle_cmd=1.0)
        for _ in range(10):
            ctx.compute_centroid_delta(0.0, 0.0, 1.0, _TICK_S)
        v_gecis = ctx.v_yukari
        ctx.throttle_cmd = 1.0
        compute_agent_setpoints(
            ctx, dt=_TICK_S, formation_offsets=_CIZGI_7M)
        # Rampa kaldigi yerden devam etti, sifirdan baslamadi.
        self.assertGreater(ctx.v_yukari, v_gecis)
        self.assertAlmostEqual(
            ctx.v_yukari, v_gecis + _DIKEY_IVME * _TICK_S, places=9)


if __name__ == '__main__':
    unittest.main()
