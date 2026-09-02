from swarm_state_machine.agent_fsm.agent_context import AgentContext
from swarm_state_machine.agent_fsm.agent_states import AgentState
from swarm_state_machine.agent_fsm.agent_health_monitor import check as health_check

def c(kesme, volt, **kw):
    x=AgentContext(agent_id=1); x.set_state(AgentState.IN_SWARM)
    x.px4_link_ok=True; x.kill_switch_active=False; x.failsafe_active=False
    x.xy_valid=True; x.z_valid=True; x.v_xy_valid=True
    x.battery_critical_voltage_v=13.8; x.battery_voltage_v=volt
    x.pil_kesme_aktif=kesme
    x.estimator_ok=True; x.rc_link_ok=True; x.imu_healthy=True
    x.mag_healthy=True; x.baro_healthy=True; x.unstable_flight=False
    for k,v in kw.items(): setattr(x,k,v)
    return x

def sat(ad, ctx, bek_healthy, bek_kesme):
    r=health_check(ctx)
    ok = (ctx.healthy==bek_healthy) and (r.critical_fault==bek_kesme)
    print(f"  {'OK  ' if ok else 'HATA'} {ad:38s} healthy={str(ctx.healthy):5s} "
          f"FAILSAFE={str(bool(r.critical_fault)):5s} uyari={str(bool(r.warning)):5s} "
          f"sebep={r.reason or '-'}")
    return 0 if ok else 1

h=0
print("--- KESME ACIK (yarisma ayari) ---")
h+=sat("pil 15.3 (iyi)",          c(True, 15.3), True,  False)
h+=sat("pil 14.5 (dusuk bandi)",  c(True, 14.5), True,  False)
h+=sat("pil 13.5 (kritik)",       c(True, 13.5), False, True)
print("--- KESME KAPALI (operator talimati) ---")
h+=sat("pil 15.3 (iyi)",          c(False,15.3), True,  False)
h+=sat("pil 13.5 (kritik)",       c(False,13.5), True,  False)  # uyari beklenir
h+=sat("pil 11.0 (cok dusuk)",    c(False,11.0), True,  False)
print("--- KESME KAPALI ama BASKA ariza ---")
h+=sat("kill switch acik",        c(False,15.3,kill_switch_active=True), False, True)
h+=sat("EKF xy bozuk",            c(False,15.3,xy_valid=False),          False, False)
h+=sat("px4 link yok",            c(False,15.3,px4_link_ok=False),       False, False)
print("SONUC:", "GECTI" if h==0 else f"{h} BASARISIZ")
