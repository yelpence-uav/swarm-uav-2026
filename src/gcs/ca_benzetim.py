#!/usr/bin/env python3
# =============================================================================
# CA BENZETIMI — yatay teget vs DIKEY katman yol verme, ve parametre taramasi
#
# NEDEN VAR (23 Agustos 2026)
# Carpisma onlemenin "yol verme" bileseni bugun YATAY (teget). Operator
# DIKEY yol vermeyi onerdi: catisan ucaklardan biri irtifa alsin. Fikrin
# gerekcesi guclu — yatay duzlem gorev geometrisinin kendisi (formasyon
# slotlari, rota, QR konumlari), dikey eksen bos duruyor; ayrica dikeyde
# kimlik siralamasi belirsizlik birakmiyor, yatayda "saga gec" kurali n=3'te
# dongusel.
#
# Bu betik iddiayi TAHMINLE degil SAYIYLA sinar. GERCEK ca_core kosturulur
# (taklit degil), boylece sahadaki davranisin ta kendisi olculur.
#
# 🔴 NE OLCMEZ — sonuclari yorumlarken sart:
#   * Kinematik model: egim dinamigi, itki siniri, ruzgar YOK
#   * Ucak "komut edilen hizi" aninda uygular (gercekte PX4 araya girer)
#   * Tek geometri ailesi, 3 ucak
#   * Dikey kural HAM: oransal, histerezissiz
# Yani ciktilar MUTLAK degil KARSILASTIRMALI okunur: A kipi B'den iyi mi.
#
# MESH GERCEGI MODELLENIR: komsu bilgisi sifirinci derece tutucu ile
# beslenir, ~7 Hz gelir ve ~%30 duser (sahada olculen degerler).
#
# KULLANIM
#     python3 src/gcs/ca_benzetim.py            # yatay vs dikey, 3 m olcegi
#     python3 src/gcs/ca_benzetim.py --tarama   # hangi kol ne kazandiriyor
#     python3 src/gcs/ca_benzetim.py --tohum    # mesh kaybi tohum duyarliligi
#
# 🔴 TOHUM TARAMASI ATLANMAZ. Mesh kaybi rastgele; tek tohumla alinan sayi
# yaniltir. 23 Agustos'ta olculdu: bugunku ayar tek tohumda 1.54 m ("sinirda
# gecti") gorunuyordu, 8 tohumda 3'unde ESIGI IHLAL ediyordu.
# =============================================================================
import argparse
import math
import random
import statistics
import sys
from pathlib import Path

_KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_KOK / "src" / "swarm_core"))

from swarm_core.collision_avoidance.ca_core import (  # noqa: E402
    CaParams, CollisionAvoidanceCore, NeighborObs)

DT = 0.05
SURE = 30.0

# --- 3 m olcegi: aralik 6 m'den 3 m'e indirilecek (operator, 23 Agustos) ----
# Kabul esigi VARSAYIM: nominal araligin yarisi. Gercek deger karara baglanmali.
MIN_AYRIM = 1.5

TABAN = dict(
    d0=3.0, hard=2.0, r_min=1.0, f_sat=6.0,
    k_tan=0.0,          # 0 = yatay teget KAPALI (dikey kip)
    v_max=4.0, xy_guard=0.3, slew=3.58,
    c_dead=0.2, c_ref=1.0,
    v_dikey=2.0, katman=2.0, tetik=6.0,
    mesh_hz=7.0, mesh_kayip=0.30, seyir=3.0,
)

# Uc ucak, 3 m araliklar, CAPRAZ slot degisimi (formasyon degisimi).
BAS = [(-3.0, 0.0, 10.0), (0.0, 2.6, 10.0), (3.0, 0.0, 10.0)]
HED = [(3.0, 0.0, 10.0), (0.0, -2.6, 10.0), (-3.0, 0.0, 10.0)]


def kosu(c, tohum=20260823):
    """Tek benzetim kosusu. (en_kucuk_3B_mesafe, maks_irtifa_sapmasi) doner."""
    random.seed(tohum)
    p = CaParams(d0=c["d0"], hard=c["hard"], r_min=c["r_min"],
                 f_sat=c["f_sat"], k_tan=c["k_tan"], v_max=c["v_max"],
                 xy_guard=c["xy_guard"], slew_normal=c["slew"],
                 slew_emergency=5.66, c_dead=c["c_dead"], c_ref=c["c_ref"],
                 dt=DT)
    U = [{"aid": i + 1, "p": list(b), "hedef": list(h), "rutbe": i,
          "z0": b[2], "ca": CollisionAvoidanceCore(p), "v": [0.0, 0.0, 0.0],
          "gor": {}, "son": {}, "zs": 0.0}
         for i, (b, h) in enumerate(zip(BAS, HED))]

    en_kucuk, t = float("inf"), 0.0
    for _ in range(int(SURE / DT)):
        # --- mesh: sifirinci derece tutucu, ~mesh_hz, ~mesh_kayip -----------
        for u in U:
            for o in U:
                if o is u:
                    continue
                if t - u["son"].get(o["aid"], -99.0) < 1.0 / c["mesh_hz"]:
                    continue
                if random.random() < c["mesh_kayip"]:
                    continue          # paket dustu — ESKI bilgi kullanilir
                u["gor"][o["aid"]] = (list(o["p"]), list(o["v"]))
                u["son"][o["aid"]] = t

        emir = []
        for u in U:
            obs = []
            for _aid, (pp, vv) in u["gor"].items():
                rx = pp[0] - u["p"][0]
                ry = pp[1] - u["p"][1]
                rz = pp[2] - u["p"][2]
                obs.append(NeighborObs(
                    rel_x=rx, rel_y=ry, rel_z=rz,
                    rel_vx=vv[0] - u["v"][0], rel_vy=vv[1] - u["v"][1],
                    rel_vz=vv[2] - u["v"][2],
                    distance=math.sqrt(rx * rx + ry * ry + rz * rz)))
            dx = u["hedef"][0] - u["p"][0]
            dy = u["hedef"][1] - u["p"][1]
            d = math.hypot(dx, dy)
            vf = ((0.0, 0.0, 0.0) if d < 0.6 else
                  (dx * min(c["seyir"], d) / d, dy * min(c["seyir"], d) / d,
                   0.0))
            (vx, vy, _vz), _kacti = u["ca"].compute(vf, obs)
            # DIKEY YOL VERME: kimlik rutbesine gore katman; temizlenince don.
            catisma = any(o.distance < c["tetik"] for o in obs)
            hedef_z = u["z0"] + (u["rutbe"] * c["katman"] if catisma else 0.0)
            vz = max(-c["v_dikey"],
                     min(c["v_dikey"], 1.5 * (hedef_z - u["p"][2])))
            emir.append((vx, vy, vz if c["v_dikey"] > 0.0 else 0.0))

        for u, (vx, vy, vz) in zip(U, emir):
            u["v"] = [vx, vy, vz]
            u["p"][0] += vx * DT
            u["p"][1] += vy * DT
            u["p"][2] += vz * DT
            u["zs"] = max(u["zs"], abs(u["p"][2] - u["z0"]))
        for i in range(len(U)):
            for j in range(i + 1, len(U)):
                en_kucuk = min(en_kucuk, math.dist(U[i]["p"], U[j]["p"]))
        t += DT
    return en_kucuk, max(u["zs"] for u in U)


def kip_karsilastir():
    """YATAY teget ile DIKEY katmani hiz hiz karsilastirir."""
    print(f"3 m olcegi — d0={TABAN['d0']} hard={TABAN['hard']}, "
          f"kabul esigi {MIN_AYRIM} m")
    print(f"mesh: {TABAN['mesh_hz']:.0f} Hz, %{TABAN['mesh_kayip']*100:.0f} "
          f"kayip\n")
    print(f"{'seyir':>7} {'kip':<7} {'en_kucuk':>10} {'irtifa':>8}")
    print("-" * 38)
    for seyir in (1.0, 2.0, 3.0):
        for kip in ("YATAY", "DIKEY"):
            c = dict(TABAN, seyir=seyir)
            if kip == "YATAY":
                c.update(k_tan=0.9, v_dikey=0.0)
            d, z = kosu(c)
            im = " ⚠" if d < MIN_AYRIM else "  "
            print(f"{seyir:>5.1f}m/s {kip:<7} {d:>8.2f}m{im} {z:>7.1f}m")
        print()


def tarama():
    """Tek tek kol degistirip hangisinin ne kazandirdigini olcer."""
    taban_d, _ = kosu(TABAN)
    print(f"TABAN (3 m/s, gercek mesh, dikey): {taban_d:.2f} m "
          f"(esik {MIN_AYRIM} m)\n")
    kollar = [
        ("dikey hiz 2 -> 3 m/s",       {"v_dikey": 3.0}),
        ("dikey hiz 2 -> 4 m/s",       {"v_dikey": 4.0}),
        ("katman 2 -> 3 m",            {"katman": 3.0}),
        ("egim tavani 3.58 -> 5.66",   {"slew": 5.66}),
        ("kacis tavani 4 -> 6 m/s",    {"v_max": 6.0}),
        ("mesh 7 -> 14 Hz",            {"mesh_hz": 14.0}),
        ("mesh kayip %30 -> %5",       {"mesh_kayip": 0.05}),
        ("yavas-yaklasma kapisi ac",   {"c_dead": 0.0, "c_ref": 0.3}),
        ("d0 3.0 -> 4.0 m",            {"d0": 4.0}),
        ("hard 2.0 -> 2.5 m",          {"hard": 2.5}),
        ("yatay teget de acik",        {"k_tan": 0.9}),
        ("seyir 3 -> 2 m/s",           {"seyir": 2.0}),
    ]
    print(f"{'kol':<30} {'en_kucuk':>10} {'fark':>8} {'irtifa':>8}")
    print("-" * 60)
    for ad, delta in kollar:
        d, z = kosu(dict(TABAN, **delta))
        im = " ⚠" if d < MIN_AYRIM else "  "
        print(f"{ad:<30} {d:>8.2f}m{im} {d-taban_d:>+7.2f} {z:>7.1f}m")


def tohum_taramasi():
    """Mesh kaybi rastgele — tek tohumla alinan sayi YANILTIR."""
    yapi = {
        "TABAN (bugunku)":          {},
        "ONERI (dikey3+hard2.5)":   {"v_dikey": 3.0, "hard": 2.5},
        "ONERI + egim 5.66":        {"v_dikey": 3.0, "hard": 2.5,
                                     "slew": 5.66},
        "ONERI, seyir 2 m/s":       {"v_dikey": 3.0, "hard": 2.5,
                                     "seyir": 2.0},
    }
    tohumlar = [1, 7, 13, 42, 101, 777, 20260823, 31337]
    print(f"{'yapilandirma':<26} {'ortanca':>9} {'en_kotu':>9} "
          f"{'en_iyi':>8} {'ihlal':>8}")
    print("-" * 64)
    for ad, delta in yapi.items():
        ms = [kosu(dict(TABAN, **delta), tohum=s)[0] for s in tohumlar]
        ihlal = sum(1 for m in ms if m < MIN_AYRIM)
        print(f"{ad:<26} {statistics.median(ms):>7.2f}m {min(ms):>7.2f}m "
              f"{max(ms):>6.2f}m {ihlal:>5}/{len(ms)}")
    print(f"\nesik {MIN_AYRIM:.2f} m · {len(tohumlar)} farkli mesh tohumu")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarama", action="store_true",
                    help="hangi kol ne kazandiriyor")
    ap.add_argument("--tohum", action="store_true",
                    help="mesh kaybi tohum duyarliligi (ATLAMA)")
    a = ap.parse_args()
    if a.tarama:
        tarama()
    elif a.tohum:
        tohum_taramasi()
    else:
        kip_karsilastir()
