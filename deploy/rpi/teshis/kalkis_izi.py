"""Son kalkisin ilk saniyelerini cikarir: komut (setpoint) ve gercek konum."""
import sys, math, glob, os, bisect
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message
from mavros_msgs.msg import PositionTarget
from geometry_msgs.msg import PoseStamped

D, AID = sys.argv[1], sys.argv[2]
sp_t = f'/drone_{AID}/mavros/setpoint_raw/local'
po_t = f'/drone_{AID}/mavros/local_position/pose'
sps, pos = [], []
for pf in sorted(glob.glob(os.path.join(D, '*.mcap'))):
    try:
        r = SequentialReader()
        r.open(StorageOptions(uri=pf, storage_id='mcap'), ConverterOptions('', ''))
        r.set_filter(StorageFilter(topics=[sp_t, po_t]))
    except Exception:
        continue
    try:
        while r.has_next():
            t_, data, ts = r.read_next()
            if t_ == sp_t:
                m = deserialize_message(data, PositionTarget)
                sps.append((ts*1e-9, m.position.x, m.position.y, m.position.z,
                            m.velocity.x, m.velocity.y, m.velocity.z, m.type_mask))
            else:
                m = deserialize_message(data, PoseStamped)
                pos.append((ts*1e-9, m.pose.position.x, m.pose.position.y,
                            m.pose.position.z))
    except Exception:
        pass
    del r
pos.sort(); sps.sort()

# SON kalkis: z 1 m'yi asan son gecis
kalkis = None
for i in range(len(pos)-1, 0, -1):
    if pos[i][3] > 4.0 and pos[i-1][3] <= 4.0:
        kalkis = pos[i][0]; break
if kalkis is None:
    sys.exit('kalkis bulunamadi')
print(f"son kalkis t={kalkis:.1f}")

t0 = kalkis - 3.0
pt = [p[0] for p in pos]
print(f"{'t':>6} {'sp_x':>7} {'sp_y':>7} {'sp_z':>6} | {'x':>7} {'y':>7} {'z':>6} | "
      f"{'yatay_hata':>10} {'yatay_yer_degis':>15}")
ilk = None
son_bas = 0.0
for (t, sx, sy, sz, vx, vy, vz, tm) in sps:
    if not (t0 <= t <= kalkis + 22.0):
        continue
    i = bisect.bisect_left(pt, t)
    aday = [j for j in (i-1, i) if 0 <= j < len(pos)]
    if not aday: continue
    j = min(aday, key=lambda j: abs(pos[j][0]-t))
    px, py, pz = pos[j][1], pos[j][2], pos[j][3]
    if ilk is None: ilk = (px, py)
    hata = math.hypot(sx-px, sy-py)
    yerdeg = math.hypot(px-ilk[0], py-ilk[1])
    if t - son_bas >= 0.5:
        son_bas = t
        print(f"{t-kalkis:+6.1f} {sx:7.2f} {sy:7.2f} {sz:6.2f} | "
              f"{px:7.2f} {py:7.2f} {pz:6.2f} | {hata:10.2f} {yerdeg:15.2f}")
