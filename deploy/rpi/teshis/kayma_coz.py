"""Kayittan navigasyon kaymasi cikarir (NAVIGASYON_KAYMA Adim 1).

setpoint_raw/local (nereye dedik) ile local_position/pose (nereye gitti)
farkini bacak bacak cozer. Ikisi de ENU; yatay (x,y) farki aliniyor.
"""
import sys, math
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message
from mavros_msgs.msg import PositionTarget
from geometry_msgs.msg import PoseStamped

D, AID = sys.argv[1], sys.argv[2]
sp_t = f'/drone_{AID}/mavros/setpoint_raw/local'
po_t = f'/drone_{AID}/mavros/local_position/pose'

# Bag HALA YAZILIYOR: metadata.yaml kapanmadigi icin dizin acilamiyor
# (18 Agustos'ta da yasandi). Parca .mcap dosyalari tek tek gecerli —
# hepsini ayri ayri okuyup birlestiriyoruz.
import glob, os
parcalar = sorted(glob.glob(os.path.join(D, '*.mcap')))
sps, pos = [], []
okunan_parca = 0
for pf in parcalar:
    try:
        r = SequentialReader()
        r.open(StorageOptions(uri=pf, storage_id='mcap'), ConverterOptions('', ''))
        r.set_filter(StorageFilter(topics=[sp_t, po_t]))
    except Exception:
        continue
    okunan_parca += 1
    try:
        while r.has_next():
            t_, data, ts = r.read_next()
            if t_ == sp_t:
                m = deserialize_message(data, PositionTarget)
                sps.append((ts * 1e-9, m.position.x, m.position.y,
                            m.velocity.x, m.velocity.y))
            else:
                m = deserialize_message(data, PoseStamped)
                pos.append((ts * 1e-9, m.pose.position.x, m.pose.position.y))
    except Exception:
        pass
    del r
print(f"okunan parca: {okunan_parca}/{len(parcalar)}")
print(f"okunan: setpoint={len(sps)}  pose={len(pos)}")
if not sps or not pos:
    sys.exit("veri yok")

# pose'u zamana gore esle (en yakin komsu)
pos.sort(); sps.sort()
import bisect
pt = [p[0] for p in pos]
kayit = []
for (t, sx, sy, vx, vy) in sps:
    i = bisect.bisect_left(pt, t)
    aday = [j for j in (i - 1, i) if 0 <= j < len(pos)]
    if not aday:
        continue
    j = min(aday, key=lambda j: abs(pos[j][0] - t))
    if abs(pos[j][0] - t) > 0.15:
        continue
    hata = math.hypot(sx - pos[j][1], sy - pos[j][2])
    kayit.append((t, hata, math.hypot(vx, vy)))

# hareket bacaklarini ayir: komut hizi > 0.5 m/s
bacaklar, aktif = [], None
for (t, h, v) in kayit:
    if v > 0.5 and aktif is None:
        aktif = [(t, h, v)]
    elif v > 0.5:
        aktif.append((t, h, v))
    elif aktif is not None:
        if aktif[-1][0] - aktif[0][0] > 3.0:
            bacaklar.append(aktif)
        aktif = None
if aktif and aktif[-1][0] - aktif[0][0] > 3.0:
    bacaklar.append(aktif)

print(f"bulunan hareket bacagi: {len(bacaklar)}\n")
for n, b in enumerate(bacaklar[-2:], 1):     # son ucusun iki bacagi
    t0 = b[0][0]
    sure = b[-1][0] - t0
    vmax = max(x[2] for x in b)
    seyir = [x for x in b if x[2] > 0.9 * vmax]
    if not seyir:
        continue
    yari = seyir[len(seyir) // 2:]           # seyrin ikinci yarisi = oturmus
    kalici = sum(x[1] for x in yari) / len(yari)
    tepe = max(x[1] for x in b)
    tepe_t = [x[0] for x in b if x[1] == tepe][0] - t0
    # oturma: hata kalicinin %110'unun altina ilk indigi an
    esik = kalici * 1.1 + 0.05
    otur = None
    for x in b:
        if x[0] - t0 > 1.0 and x[1] <= esik:
            otur = x[0] - t0
            break
    print(f"--- BACAK {n}  (sure {sure:.1f}s, komut tepe hiz {vmax:.2f} m/s, "
          f"ornek {len(b)}) ---")
    print(f"  KALICI KAYMA   : {kalici:.3f} m   (seyir fazi ortalamasi)")
    print(f"  TEPE HATA      : {tepe:.3f} m   (t+{tepe_t:.1f}s)")
    print(f"  OTURMA SURESI  : {otur if otur is None else round(otur,2)} s")
    print(f"  seyir ornegi   : {len(seyir)}  ({len(seyir)/len(b)*100:.0f}% bacagin)")
