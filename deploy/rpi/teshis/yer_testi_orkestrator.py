import math
from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    Mission1Orchestrator, OrchestratorConfig, OrchestratorInput)

POS=[(-3.91,-4.82,-10.0),(3.91,4.82,-10.0)]; CEN=(0.0,0.0,-10.0); HOME=(0.0,0.0,-10.0)
cfg=OrchestratorConfig(default_formation_type=1, default_spacing_m=7.0,
                       wing_alpha_rad=math.radians(45.0))
ORG=(38.6904758,39.1610188); HEDEF=(38.6910000,39.1615000)
AD={3:'SYNC_TAKEOFF',4:'NAVIGATE_TO_QR',7:'ROTATE_TO_NEXT',9:'RETURN_HOME'}

def dene(st, hedef_var):
    o=Mission1Orchestrator(cfg); o.set_origin(*ORG)
    o.set_next_target(hedef_var, HEDEF[0], HEDEF[1])
    for t in (0.5,1.0,2.0,3.0):
        inp=OrchestratorInput(mission_state=st, qr_step=0, is_leader=True,
                              agent_ids=[1,3], positions=POS, centroid=CEN,
                              home=HOME, qr=None, time_in_state=t, swarm_yaw_deg=281.0)
        c=list(o.decide(inp))
        if c: return c
    return []

hata=0
for st in (3,7,4,9):
    for hv in (False,True):
        c=dene(st,hv)
        ok = len(c)>0
        hata += (not ok)
        det=''
        if c and hasattr(c[0],'center'):
            z=c[0].center[2]
            det=f"  merkez_z={z:+.1f} kullan_centroid={c[0].use_current_centroid} kullan_irtifa={c[0].use_current_altitude}"
        print(f"  {'OK  ' if ok else 'HATA'} {AD[st]:15s} hedef={'VAR ' if hv else 'YOK '} -> "
              f"{[type(x).__name__ for x in c] if c else 'HICBIR SEY'}{det}")
print("SONUC:", "GECTI — her durumda komut uretiliyor" if hata==0 else f"{hata} BOSLUK KALDI")
