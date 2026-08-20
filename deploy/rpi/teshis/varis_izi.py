"""Son bacagin VARIS fazi: asim var mi, ne kadar, kac saniyede duzeliyor."""
import sys, math, glob, os, bisect
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions, StorageFilter
from rclpy.serialization import deserialize_message
from mavros_msgs.msg import PositionTarget
from geometry_msgs.msg import PoseStamped
D, AID = sys.argv[1], sys.argv[2]
sp_t=f'/drone_{AID}/mavros/setpoint_raw/local'; po_t=f'/drone_{AID}/mavros/local_position/pose'
sps=[]; pos=[]
for pf in sorted(glob.glob(os.path.join(D,'*.mcap'))):
    try:
        r=SequentialReader(); r.open(StorageOptions(uri=pf,storage_id='mcap'),ConverterOptions('',''))
        r.set_filter(StorageFilter(topics=[sp_t,po_t]))
    except Exception: continue
    try:
        while r.has_next():
            t_,data,ts=r.read_next()
            if t_==sp_t:
                m=deserialize_message(data,PositionTarget)
                sps.append((ts*1e-9,m.position.x,m.position.y,m.velocity.x,m.velocity.y))
            else:
                m=deserialize_message(data,PoseStamped)
                pos.append((ts*1e-9,m.pose.position.x,m.pose.position.y,m.pose.position.z))
    except Exception: pass
    del r
pos.sort(); sps.sort()
# son hareket bacaginin bitisi: komut hizi 0.5'in altina son dusus
son_hareket=None
for i in range(len(sps)-1,0,-1):
    v=math.hypot(sps[i][3],sps[i][4]); vp=math.hypot(sps[i-1][3],sps[i-1][4])
    if v<0.5<=vp:
        son_hareket=sps[i][0]; break
if son_hareket is None: sys.exit('bacak bitisi bulunamadi')
print(f"son bacak bitisi t={son_hareket:.1f}\n")
pt=[p[0] for p in pos]
# hedef: bacak bitisindeki setpoint konumu
hedef=None
for (t,sx,sy,vx,vy) in sps:
    if t>=son_hareket: hedef=(sx,sy); break
print(f"hedef (ENU): ({hedef[0]:.2f}, {hedef[1]:.2f})")
print(f"{'t':>6} {'sp_x':>7} {'sp_y':>7} | {'x':>7} {'y':>7} {'z':>6} | {'hedefe':>7} {'komut_hiz':>9}")
son_bas=0.0
for (t,sx,sy,vx,vy) in sps:
    if not (son_hareket-4.0 <= t <= son_hareket+14.0): continue
    i=bisect.bisect_left(pt,t); aday=[j for j in (i-1,i) if 0<=j<len(pos)]
    if not aday: continue
    j=min(aday,key=lambda j: abs(pos[j][0]-t))
    px,py,pz=pos[j][1],pos[j][2],pos[j][3]
    d=math.hypot(px-hedef[0],py-hedef[1])
    if t-son_bas>=0.4:
        son_bas=t
        print(f"{t-son_hareket:+6.1f} {sx:7.2f} {sy:7.2f} | {px:7.2f} {py:7.2f} {pz:6.2f} | "
              f"{d:7.2f} {math.hypot(vx,vy):9.2f}")
