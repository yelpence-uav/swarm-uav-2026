# Copyright 2026 Yelpence
"""Consensus icin durum kumeleri ve sabitler."""

from swarm_interfaces.msg import AgentStatus

# Lider adayi olabilmek icin ajanin bulunmasi gereken durumlar.
#
# 🔴 STATE_RETURN_HOME BURADA OLMAK ZORUNDA — 3 Eylul 2026 saha olayi.
#
# Eskiden yoktu. Sonucu olculdu: lider (agent 1) RETURN_HOME'a gectigi
# ANDA aday olmaktan cikti, `decide_change` LEADER_FAULT gordu ve
# liderlik 0.4 saniye icinde agent 2'ye gecti (385187.56 -> 385187.9).
#
# Neden oldurucu: formasyon tarifini YALNIZ LIDER mesh'e basiyor
# (KARAR 11). Eski lider eve donus icin 180 derecelik yaw rampasini
# uretti (18 komut, heading -50 -> +127) ama artik lider olmadigi icin
# HICBIRI MESH'E CIKMADI. Takipciler son aldiklari komutta (heading -50)
# donup kaldi: ortadaki ucak kendi planini uygulayip yerinde donerken
# digerleri hic kimildamadi. SURU IKIYE BOLUNDU.
#
# Eve donus ucusun EN KRITIK fazi (herkes inis noktasina gidiyor) ve
# tam orada liderin degismesi mumkun olmamali. LANDING bilerek DISARDA:
# inen ucak liderligi birakmali.
ELIGIBLE_STATES = frozenset({
    AgentStatus.STATE_ARMED,
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
    AgentStatus.STATE_RETURN_HOME,
})

# Havada sayilan durumlar.
# RETURN_HOME de havada; karar yollari ELIGIBLE_STATES'e tasindigi icin
# (P0.14, 20 Agustos) bu kume artik hicbir kararda kullanilmiyor, ama
# tutarli kalsin diye eklendi — ileride biri buna bakarsa yanilmasin.
AIRBORNE_STATES = frozenset({
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
    AgentStatus.STATE_RETURN_HOME,
})

# Secim disi roller.
INELIGIBLE_ROLES = frozenset({
    AgentStatus.ROLE_STANDBY,
    AgentStatus.ROLE_DETACHED,
})
