import math
from swarm_core.formation_control.formation_geometry import compute_slot_offsets, rotate_offset
from swarm_missions.mission1_dynamic_swarm.formation_cmd import build_slot_assignment

R = 6378137.0
def ned(p, ref):
    return ((p[0]-ref[0])*math.pi/180*R,
            (p[1]-ref[1])*math.pi/180*R*math.cos(ref[0]*math.pi/180))

A = (38.6904743, 39.1609639)   # ylp00  agent 1
B = (38.6905446, 39.1610749)   # ylp02  agent 3
C = ((A[0]+B[0])/2, (A[1]+B[1])/2)

pa, pb = ned(A, C), ned(B, C)
print(f"merkeze gore konumlar (kuzey, dogu):")
print(f"  ylp00 (agent 1): ({pa[0]:+.2f}, {pa[1]:+.2f})")
print(f"  ylp02 (agent 3): ({pb[0]:+.2f}, {pb[1]:+.2f})")
print(f"  aralarindaki mesafe: {math.hypot(pb[0]-pa[0], pb[1]-pa[1]):.2f} m\n")

SPACING, ALPHA = 7.0, math.radians(45.0)
slots = compute_slot_offsets(1, 2, SPACING, ALPHA)   # 1 = OKBASI
print(f"OKBASI slotlari (aralik 7.0 m, kanat 45 deg), govde cercevesi:")
for i, s in enumerate(slots):
    print(f"  slot{i}: ileri={s[0]:+.2f} m  sag={s[1]:+.2f} m")
print()

for h_deg in (0.0, 90.0, 180.0, 270.0):
    off = build_slot_assignment(1, [1, 3], [(pa[0],pa[1],0.0),(pb[0],pb[1],0.0)], (0.0, 0.0),
                                SPACING, ALPHA, math.radians(h_deg))
    yon = {}
    for aid, o in zip([1, 3], off):
        wx, wy = rotate_offset(o[0], o[1], math.radians(h_deg))
        yon[aid] = (wx, wy, o)
    # slot0 (0,0) = uc; digeri kanat
    uc = 1 if abs(off[0][0]) + abs(off[0][1]) < 0.01 else 3
    kanat = 3 if uc == 1 else 1
    ad = {1: 'ylp00', 3: 'ylp02'}
    ox, oy, _ = yon[kanat][2], 0, 0
    o = yon[kanat][2]
    taraf = 'SAG' if o[1] > 0 else 'SOL'
    wx, wy = yon[kanat][0], yon[kanat][1]
    print(f"heading {h_deg:5.0f} deg -> UC: {ad[uc]}   KANAT: {ad[kanat]} "
          f"({taraf}, govde: ileri {o[0]:+.2f} sag {o[1]:+.2f}) "
          f"| dunya: kuzey {wx:+.2f} dogu {wy:+.2f}")
