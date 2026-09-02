from swarm_state_machine.agent_fsm.agent_context import AgentContext
from swarm_state_machine.agent_fsm.agent_states import AgentState
from swarm_state_machine.agent_fsm.agent_transitions import evaluate_transitions

def c_takeoff(**kw):
    c = AgentContext(agent_id=1)
    c.set_state(AgentState.TAKEOFF)
    c.px4_link_ok = True; c.kill_switch_active = False; c.failsafe_active = False
    c.xy_valid = True; c.z_valid = True; c.v_xy_valid = True
    c.battery_voltage_v = 15.0; c.battery_critical_voltage_v = 13.8
    c.offboard_active = True; c.origin_synced = True
    c.attitude_stable = True; c.altitude_stable = True; c.vertical_speed_ok = True
    c.target_altitude_reached = False   # SAHADAKI GERCEK: NED cercevesi yuzunden HIC true olmuyor
    for k, v in kw.items(): setattr(c, k, v)
    return c

t = [("gorev node sinyali",        c_takeoff(pending_state=AgentState.IN_SWARM), AgentState.IN_SWARM),
     ("sinyal yok -> beklesin",    c_takeoff(),                                  None),
     ("kendi kapisi (SITL yolu)",  c_takeoff(target_altitude_reached=True),      AgentState.IN_SWARM),
     ("pil kritik + sinyal",       c_takeoff(pending_state=AgentState.IN_SWARM,
                                             battery_voltage_v=13.0),            AgentState.FAILSAFE),
     ("EKF xy bozuk + sinyal",     c_takeoff(pending_state=AgentState.IN_SWARM,
                                             xy_valid=False),                    AgentState.FAILSAFE)]
hata = 0
for ad, c, bek in t:
    r = evaluate_transitions(c); ok = (r == bek); hata += (not ok)
    print(f"  {'OK  ' if ok else 'HATA'} {ad:26s} -> {r.name if r else None}")
print("SONUC:", "GECTI" if hata == 0 else f"{hata} BASARISIZ")
