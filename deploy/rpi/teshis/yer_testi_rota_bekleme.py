from swarm_state_machine.mission_fsm.mission_context import MissionContext
from swarm_state_machine.mission_fsm.mission_states import MissionState
from swarm_state_machine.mission_fsm.mission_transitions import evaluate_transitions
import time

def c(grace, gecen):
    x=MissionContext(agent_ids=[1,3])
    x.set_state(MissionState.NAVIGATE_TO_QR)
    x.state_entry_time = time.monotonic() - gecen
    x.route_unknown=True; x.rota_bilinmeyen_s=grace; x.navigate_timeout_s=30.0
    return x

t=[("grace=10, 5 sn gecti  -> beklesin", c(10.0,5),  None),
   ("grace=10, 11 sn gecti -> EVE DON",  c(10.0,11), MissionState.RETURN_HOME),
   ("grace=0 (kod vars.30), 11 sn",      c(0.0,11),  None),
   ("grace=0 (kod vars.30), 31 sn",      c(0.0,31),  MissionState.RETURN_HOME)]
h=0
for ad,ctx,bek in t:
    r=evaluate_transitions(ctx); ok=(r==bek); h+=(not ok)
    print(f"  {'OK  ' if ok else 'HATA'} {ad:36s} -> {r.name if r else None}")
print("SONUC:", "GECTI" if h==0 else f"{h} BASARISIZ")
