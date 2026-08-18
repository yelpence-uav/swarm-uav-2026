#!/bin/bash
# Konteyner icinde ylp00'da kosar. $1 = agent_id (1)
#
# DENEY: consensus_node._on_election'daki eskimis-mesaj filtresi
#     if msg.sequence_num <= ctx.max_seen_seq: return
# gercekten yeni secimleri dusuruyor mu?
#
# NEDEN ONEMLI: _publish_election_result ctx.out_seq'i 0'dan baslatiyor. Lider
# dronun consensus_node'u yeniden baslarsa (cokme, konteyner restart) out_seq
# 1'e doner; takipcilerin max_seen_seq'i ise yuksek kalir. O durumda liderin
# TUM yeni secim sonuclari SESSIZCE dusurulur. election_round kontrolu
# kurtarmiyor cunku seq kontrolu ONCE geliyor ve return ediyor.
#
# GOZLEM YOLU: _on_election hicbir sey LOGLAMIYOR (ctx.leader_id'yi dogrudan
# yaziyor, _set_leader'i cagirmiyor). Bu yuzden dogrudan gozlenemez. Dolayli
# yol: yanlis bir lider (3) enjekte edilirse ve effective={1} ise bir sonraki
# tick'te decide_change "lider effective'de yok" deyip REASON_LEADER_FAULT ile
# liderligi geri alir - ve _set_leader LOGLAR. Yani:
#     log satiri ciktiysa -> enjekte edilen mesaj KABUL edildi
#     log satiri cikmadiysa -> mesaj REDDEDILDI
#
# DENEY HIJYENI: B kolunda election_round KASTEN yuksek (9) tutuluyor, boylece
# mesaji reddeden tek sey seq olabilir; round kontrolu degiskeni kirletmez.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

secim_yayinla() {  # $1=seq $2=lider $3=round
    timeout -s INT 3 ros2 topic pub -r 5 \
        --qos-reliability reliable --qos-durability transient_local \
        /swarm/public/election/result swarm_interfaces/msg/ElectionResult \
        "{sequence_num: $1, new_leader_id: $2, election_round: $3, triggered_by_agent_id: 3, reason: 3, confirmed_by_agent_ids: [], message: seq_deneyi}" \
        >/dev/null 2>&1
}
say() { grep -c "CONSENSUS. Lider" "$LOG" 2>/dev/null || echo 0; }

# effective={1} olmasi icin ARMED durumunu arka planda surekli besle.
setsid bash /ws/durum_enjekte.sh "$AID" 40 >/dev/null 2>&1 &
BESLE=$!
sleep 4

N0=$(say); echo "   baslangic secim log satiri: $N0"

echo "   --- A KOLU: seq=100 (YUKSEK), lider=3, round=5 ---"
secim_yayinla 100 3 5
sleep 4
NA=$(say); echo "      log satiri: $NA  (artis: $((NA-N0)))"
grep "CONSENSUS. Lider" "$LOG" 2>/dev/null | tail -2 | sed 's/^/         /'

echo "   --- B KOLU: seq=5 (DUSUK), lider=3, round=9 (round YUKSEK, tek engel seq) ---"
secim_yayinla 5 3 9
sleep 4
NB=$(say); echo "      log satiri: $NB  (artis: $((NB-NA)))"
grep "CONSENSUS. Lider" "$LOG" 2>/dev/null | tail -2 | sed 's/^/         /'

kill "$BESLE" 2>/dev/null
echo
echo "   BEKLENEN: A kolunda artis VAR (mesaj kabul), B kolunda artis YOK (seq filtresi dusurdu)"
