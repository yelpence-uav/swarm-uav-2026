#!/usr/bin/env python3
# =============================================================================
# CA BENZETIMI — DIKEY yol verme, sartnamenin 3-10 m aralik bandinda
#
# NEDEN VAR (23 Agustos 2026)
# Carpisma onlemenin yol verme bileseni artik DIKEY: catisan ucaklardan
# kimligi buyuk olan, kucuk olanin olculen irtifasindan KATMAN kadar uzaga
# gider. Yatay itme kapali (k_yatay=0) — formasyon geometrisi bozulmasin.
#
# GERCEK `ca_core` KOSTURULUR, taklit degil. Ustelik artik DIKEY KURAL DA
# ca_core'un icinde: onceki surumde benzetim KENDI ayri dikey kuralini
# kosuyordu, yani olculen sey ucacak sey DEGILDI. O sapma kapatildi.
#
# ---------------------------------------------------------------------------
# MESH MODELI — 23 Agustos 2026'DA OLCULDU, artik tahmin degil
#
# Onceki surum `mesh_hz=7.0` VE `mesh_kayip=0.30` diyordu: ikisi birlikte
# kaybi CIFTE sayiyor ve etkin tazelemeyi 4.9 Hz'e dusuruyordu. Gercek
# olcum (iki ucak, yerde, POSE kapisi duzeltildikten sonra):
#
#     kaynak (agent_fsm ic durum)        10.00 Hz
#     Pi->ESP yazilan (gonderim_ok)      11.9 /s  (POSE 10 + DURUM 1)
#     karsi tarafin ALDIGI               10.46 Hz / 10.89 Hz
#     en buyuk bosluk                    0.31 s / 0.20 s
#     -> HAVADAN kayip %1-5
#
# Yani model: 10 Hz gonderim, %5 kayip. Tek yerde, cifte sayilmadan.
#
# ⚠️ Bu olcum YERDE alindi. 22 Agustos'ta havadaki linkin yerdekinden IYI
# oldugu gorulmustu (yer yansimasi), yani ucusta bundan kotu beklenmiyor —
# ama ucusta teyit edilmeli.
# ---------------------------------------------------------------------------
#
# 🔴 NE OLCMEZ — sonuclari yorumlarken sart:
#   * Kinematik model: egim dinamigi, ITKI SINIRI, ruzgar YOK
#   * Ucak komut edilen hizi ANINDA uygular (gercekte PX4 araya girer)
#   * 🔴 DIKEY HIZ TAVANI VARSAYIM: v_dikey=1.5 m/s. Ucagin gercekten
#     tirmanabildigi hiz OLCULMEDI (aski gazi %66, itki payi bilinmiyor —
#     TUZAKLAR §0.3). Bu sayi yanlissa butun dikey sonuclar kayar.
#
# KULLANIM
#     python3 src/gcs/ca_benzetim.py            # 3-10 m aralik taramasi
#     python3 src/gcs/ca_benzetim.py --kip      # dikey vs yatay vs kapali
#     python3 src/gcs/ca_benzetim.py --tarama   # hangi kol ne kazandiriyor
#     python3 src/gcs/ca_benzetim.py --tohum    # tohum duyarliligi — ATLAMA
#
# 🔴 TOHUM TARAMASI ATLANMAZ. Mesh kaybi rastgele; tek tohumla alinan sayi
# yaniltir. 23 Agustos'ta olculdu: bir ayar tek tohumda "sinirda gecti"
# gorunurken 8 tohumda 3'unde esigi IHLAL ediyordu.
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
SURE = 40.0

# KABUL ESIGI — sartnamenin ajanlar arasi mesafesi hakemlerce 3-10 m
# arasindan secilir. Kabul esigi olarak MIN_AYRIM_M kullanilamaz (4.0 m),
# cunku hakem 3 m secerse formasyonun KENDISI onu ihlal eder. Olcut:
# nominal araligin yarisi, ama en az 1.5 m.
def kabul_esigi(aralik):
    return max(1.5, 0.5 * aralik)


TABAN = dict(
    d0=4.0, hard=2.5, r_min=1.5,
    katman=3.0, k_dikey=1.0, k_yatay=1.0, k_tan=0.0,
    yatay_esik=0.0,      # 0 = hard kullanilir (son care)
    v_dikey=1.5, a_dikey=1.0, kp_dikey=0.8,
    f_sat=6.0, v_max=4.0, xy_guard=0.3, slew=3.58,
    c_dead=0.2, c_ref=1.0,
    mesh_hz=10.0, mesh_kayip=0.05, seyir=3.0, aralik=5.0,
    donusumlu=True,
)


def _params(c, aid):
    return CaParams(
        d0=c["d0"], hard=c["hard"], r_min=c["r_min"], f_sat=c["f_sat"],
        k_tan=c["k_tan"], v_max=c["v_max"], xy_guard=c["xy_guard"],
        slew_normal=c["slew"], slew_emergency=5.66,
        c_dead=c["c_dead"], c_ref=c["c_ref"], dt=DT,
        k_dikey=c["k_dikey"], k_yatay=c["k_yatay"], katman_m=c["katman"],
        yatay_esik_m=c["yatay_esik"],
        v_dikey_max=c["v_dikey"], a_dikey_max=c["a_dikey"],
        kp_dikey=c["kp_dikey"], dikey_taban_m=4.0, agent_id=aid,
        rutbe=(aid - 1) if c.get("donusumlu", True) else -1,
    )


def _geometri(aralik):
    """Uc ucak, CAPRAZ slot degisimi (formasyon degisimi en zor an)."""
    y = aralik * math.sin(math.radians(60.0))
    bas = [(-aralik, 0.0), (0.0, y), (aralik, 0.0)]
    hed = [(aralik, 0.0), (0.0, -y), (-aralik, 0.0)]
    return bas, hed


def kosu(c, tohum=20260823):
    """Tek kosu. (en_kucuk_3B_mesafe, maks_irtifa_sapmasi) doner."""
    random.seed(tohum)
    bas, hed = _geometri(c["aralik"])
    Z0 = 12.0
    U = [{"aid": i + 1, "p": [b[0], b[1], Z0], "hedef": list(h),
          "ca": CollisionAvoidanceCore(_params(c, i + 1)),
          "v": [0.0, 0.0, 0.0], "gor": {}, "son": {}, "zs": 0.0}
         for i, (b, h) in enumerate(zip(bas, hed))]

    en_kucuk, t = float("inf"), 0.0
    for _ in range(int(SURE / DT)):
        # --- mesh: sifirinci derece tutucu, olculen hiz ve kayip ----------
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
            for aid, (pp, vv) in u["gor"].items():
                rx = pp[0] - u["p"][0]
                ry = pp[1] - u["p"][1]
                # NED: z ASAGI pozitif, benzetimde p[2] irtifa (YUKARI).
                # rel_z = benim_irtifam - komsunun_irtifasi
                rz = u["p"][2] - pp[2]
                obs.append(NeighborObs(
                    rel_x=rx, rel_y=ry, rel_z=rz,
                    rel_vx=vv[0] - u["v"][0], rel_vy=vv[1] - u["v"][1],
                    rel_vz=-(vv[2] - u["v"][2]),
                    distance=math.sqrt(rx * rx + ry * ry + rz * rz),
                    agent_id=aid))
            dx = u["hedef"][0] - u["p"][0]
            dy = u["hedef"][1] - u["p"][1]
            d = math.hypot(dx, dy)
            vf = ((0.0, 0.0, 0.0) if d < 0.6 else
                  (dx * min(c["seyir"], d) / d, dy * min(c["seyir"], d) / d,
                   0.0))
            (vx, vy, vz_ned), _kacti = u["ca"].compute(
                vf, obs, h_now=u["p"][2])
            emir.append((vx, vy, -vz_ned))     # NED -> benzetim (yukari +)

        for u, (vx, vy, vz) in zip(U, emir):
            u["v"] = [vx, vy, vz]
            u["p"][0] += vx * DT
            u["p"][1] += vy * DT
            u["p"][2] += vz * DT
            u["zs"] = max(u["zs"], abs(u["p"][2] - Z0))
        for i in range(len(U)):
            for j in range(i + 1, len(U)):
                en_kucuk = min(en_kucuk, math.dist(U[i]["p"], U[j]["p"]))
        t += DT
    return en_kucuk, max(u["zs"] for u in U)


def aralik_taramasi():
    """Sartnamenin 3-10 m bandinda dikey kaciSin davranisi."""
    print("SARTNAME BANDI — ajanlar arasi mesafe hakemlerce secilir\n")
    print(f"d0={TABAN['d0']} sabit (operator karari) · "
          f"katman={TABAN['katman']} m · seyir={TABAN['seyir']} m/s")
    print(f"mesh {TABAN['mesh_hz']:.0f} Hz / %{TABAN['mesh_kayip']*100:.0f} "
          f"kayip (23 Agu olcumu)\n")
    print(f"{'aralik':>7} {'kip':<7} {'en_kucuk':>10} {'esik':>7} "
          f"{'irtifa':>8}")
    print("-" * 46)
    for aralik in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        esik = kabul_esigi(aralik)
        for kip, delta in (("DIKEY", {}), ("KAPALI", {"k_dikey": 0.0})):
            d, z = kosu(dict(TABAN, aralik=aralik, **delta))
            im = " ⚠" if d < esik else "  "
            print(f"{aralik:>5.0f} m {kip:<7} {d:>8.2f}m{im} {esik:>6.2f}m "
                  f"{z:>7.1f}m")
        print()


def kip_karsilastir():
    """DIKEY / YATAY / KAPALI — ayni geometride."""
    print(f"aralik {TABAN['aralik']:.0f} m · esik "
          f"{kabul_esigi(TABAN['aralik']):.2f} m\n")
    print(f"{'seyir':>7} {'kip':<8} {'en_kucuk':>10} {'irtifa':>8}")
    print("-" * 38)
    kipler = (
        ("DIKEY", {}),
        ("YATAY", {"k_dikey": 0.0, "k_yatay": 1.0, "k_tan": 0.9}),
        ("KAPALI", {"k_dikey": 0.0, "k_yatay": 0.0}),
    )
    esik = kabul_esigi(TABAN["aralik"])
    for seyir in (1.0, 2.0, 3.0):
        for ad, delta in kipler:
            d, z = kosu(dict(TABAN, seyir=seyir, **delta))
            im = " ⚠" if d < esik else "  "
            print(f"{seyir:>5.1f}m/s {ad:<8} {d:>8.2f}m{im} {z:>7.1f}m")
        print()


def tarama():
    """Tek tek kol degistirip hangisinin ne kazandirdigini olcer."""
    taban_d, _ = kosu(TABAN)
    esik = kabul_esigi(TABAN["aralik"])
    print(f"TABAN (aralik {TABAN['aralik']:.0f} m, seyir "
          f"{TABAN['seyir']:.0f} m/s, dikey): {taban_d:.2f} m "
          f"(esik {esik:.2f} m)\n")
    kollar = [
        ("katman 3 -> 4 m",            {"katman": 4.0}),
        ("katman 3 -> 2 m",            {"katman": 2.0}),
        ("dikey hiz 1.5 -> 3.0 m/s",   {"v_dikey": 3.0}),
        ("dikey hiz 1.5 -> 1.0 m/s",   {"v_dikey": 1.0}),
        ("dikey ivme 1.0 -> 2.0",      {"a_dikey": 2.0}),
        ("kp_dikey 0.8 -> 1.5",        {"kp_dikey": 1.5}),
        ("d0 4 -> 5 m",                {"d0": 5.0}),
        ("d0 4 -> 3 m",                {"d0": 3.0}),
        ("mesh 10 -> 5 Hz",            {"mesh_hz": 5.0}),
        ("mesh kayip %5 -> %30",       {"mesh_kayip": 0.30}),
        ("yatay itme de acik",         {"k_yatay": 1.0}),
        ("seyir 3 -> 2 m/s",           {"seyir": 2.0}),
    ]
    print(f"{'kol':<30} {'en_kucuk':>10} {'fark':>8} {'irtifa':>8}")
    print("-" * 60)
    for ad, delta in kollar:
        d, z = kosu(dict(TABAN, **delta))
        im = " ⚠" if d < esik else "  "
        print(f"{ad:<30} {d:>8.2f}m{im} {d-taban_d:>+7.2f} {z:>7.1f}m")


def tohum_taramasi():
    """Mesh kaybi rastgele — tek tohumla alinan sayi YANILTIR."""
    yapi = {
        "DIKEY (onerilen)":         {},
        "DIKEY, katman 4 m":        {"katman": 4.0},
        "DIKEY, seyir 2 m/s":       {"seyir": 2.0},
        "YATAY (eski kip)":         {"k_dikey": 0.0, "k_yatay": 1.0,
                                     "k_tan": 0.9},
        "KACINMA KAPALI":           {"k_dikey": 0.0, "k_yatay": 0.0},
    }
    tohumlar = [1, 7, 13, 42, 101, 777, 20260823, 31337]
    esik = kabul_esigi(TABAN["aralik"])
    print(f"aralik {TABAN['aralik']:.0f} m · esik {esik:.2f} m · "
          f"{len(tohumlar)} mesh tohumu\n")
    print(f"{'yapilandirma':<26} {'ortanca':>9} {'en_kotu':>9} "
          f"{'en_iyi':>8} {'ihlal':>8}")
    print("-" * 64)
    for ad, delta in yapi.items():
        ms = [kosu(dict(TABAN, **delta), tohum=s)[0] for s in tohumlar]
        ihlal = sum(1 for m in ms if m < esik)
        print(f"{ad:<26} {statistics.median(ms):>7.2f}m {min(ms):>7.2f}m "
              f"{max(ms):>6.2f}m {ihlal:>5}/{len(ms)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kip", action="store_true", help="dikey/yatay/kapali")
    ap.add_argument("--tarama", action="store_true",
                    help="hangi kol ne kazandiriyor")
    ap.add_argument("--tohum", action="store_true",
                    help="mesh kaybi tohum duyarliligi (ATLAMA)")
    a = ap.parse_args()
    if a.tarama:
        tarama()
    elif a.tohum:
        tohum_taramasi()
    elif a.kip:
        kip_karsilastir()
    else:
        aralik_taramasi()
