"""AgentStatus -> NeighborObs adaptoru (KARAR-01, Secenek C).

NEDEN VAR
`collision_avoidance` ozgun tasariminda komsu verisini `NeighborInfo`'dan
aliyor; onu `kinematic_fusion` uretiyor. KARAR-01 (15 Agustos) fusion'i
DEVRE DISI biraktI: EMA yumusatmasi (alpha_pos=0.3) ~2.33 ornek gecikme
ekliyor, mesh ~5-7 Hz'de bu 0.35-0.47 s demek. 3 m/s'te komsunun 1.2 m
ONCEKI yerine bakmak — kacinmada odenecek bir bedel degil.

Atlanabilir olmasinin sebebi: `AgentStatus`ta `vel_x/vel_y/vel_z` ZATEN var,
yani `NeighborInfo`nun tasidigi bilgi ham veride mevcut. Fusion'in tek
kattigi yumusatma, o da gecikme.

============================================================================
ISARET YONU — TERS YAZILIRSA UCAK KOMSUSUNUN USTUNE GIDER
============================================================================
    rel = KOMSU - BEN
Uc yerden dogrulandi (15 Agustos, olculdu):
    kinematic_fusion_node.py:436   rel_x = n_n - s_n
    ca_core.py:98                  away_x = -n.rel_x      (itme komsudan uzaga)
    ca_core.py:117                 c = -(rel . rel_v)/d3  (kapanma hizi > 0)

============================================================================
CERCEVE — pos_x/pos_y GUVENILIR DEGIL, lat/lon GUVENILIR
============================================================================
`AgentStatus.msg:77`: "WARNING — GERCEK DONANIM: Bu alanlar local NED
frame'dedir. Her drone KENDI GPS origin'inden NED kurar."

Iki ucagin origin'i ayrisirsa `pos_x` farki SABIT BIR SAPMA tasir ve kacinma
yanlis yone iter. 15 Agustos'ta iki origin arasinda 18.2 m fark olustugu
gorulmustu — o gun bu kod kossaydi itme yonu tamamen yanlis olurdu.

lat/lon yolunda bu sorun YOK: referans noktasi cikarmada goturulur. Referans
olarak KENDI konumumu verirsem sonuc DOGRUDAN goreli vektordur ve origin
denklemden tamamen duser — `origin_synced` beklemeye bile gerek kalmaz.

Bu yuzden: **lat/lon BIRINCIL**, `pos_x/pos_y` yalniz ikisi de origin_synced
iken YEDEK. Ikisi de yoksa komsu ATLANIR (sessizce yanlis yone itmektense
hic itmemek dogru; kacinma tek koruma katmani degil, irtifa ayrimi da var).

Hiz farki cerceveden BAGIMSIZ — sabit origin offset'i turevde kaybolur —
o yuzden hizda cerceve kapisi yok.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .ca_core import NeighborObs
from ..formation_control.formation_geometry import latlon_to_ned

# AgentStatus YALNIZ tip aciklamasi icin gerekli. Calisma zamaninda import
# EDILMIYOR ki bu modul ROS olmadan da yuklenebilsin — boylece KARAR-01
# Test 1 (isaret yonu dogrulamasi) dizustunde, ucaga dagitmadan kosuyor.
# Kacinmanin yonunu ancak ucakta test edebilmek kabul edilebilir bir bedel
# degil: ters isaret ucagi komsusunun ustune gonderir.
if TYPE_CHECKING:  # pragma: no cover
    from swarm_interfaces.msg import AgentStatus

# Adaptorun komsuyu neden atladigini sayan tanilar. Node bunlari 5 sn'de bir
# basiyor; "kacinma neden tetiklenmedi" sorusu olcumle cevaplanabilsin diye.
ATLAMA_GECERSIZ = 'gecersiz'      # xy_valid/z_valid false
ATLAMA_CERCEVE = 'cerceve'        # ne lat/lon ne de ortak origin var
ATLAMA_SAYISAL = 'sayisal'        # NaN/inf


def agent_status_to_obs(
    komsu: AgentStatus,
    ben: AgentStatus,
) -> tuple[NeighborObs | None, str]:
    """Ham `AgentStatus` ciftini CA'nin bekledigi `NeighborObs`a cevirir.

    Doner: (gozlem, atlama_nedeni). Gozlem None ise neden dolu.
    """
    if not (komsu.xy_valid and komsu.z_valid):
        return None, ATLAMA_GECERSIZ

    # --- YATAY: lat/lon birincil -------------------------------------------
    # Referans = KENDI konumum, yani donen deger dogrudan goreli vektor.
    if (komsu.lat_deg != 0.0 and komsu.lon_deg != 0.0
            and ben.lat_deg != 0.0 and ben.lon_deg != 0.0):
        rel_x, rel_y = latlon_to_ned(
            float(komsu.lat_deg), float(komsu.lon_deg),
            float(ben.lat_deg), float(ben.lon_deg),
        )
    elif komsu.origin_synced and ben.origin_synced:
        # YEDEK: ikisi de ayni paylasilan origin'i uygulamis; pos farki
        # ancak o zaman anlamli.
        rel_x = float(komsu.pos_x) - float(ben.pos_x)
        rel_y = float(komsu.pos_y) - float(ben.pos_y)
    else:
        return None, ATLAMA_CERCEVE

    # --- DIKEY --------------------------------------------------------------
    # pos_z de local NED. Ortak origin yoksa 0.0 aliyoruz; bu MUHAFAZAKAR
    # yon: d3 kuculur, yani kacinma DAHA ERKEN devreye girer. Yanlis bir
    # yukseklik farkina guvenip gec kalmaktansa erken itmek dogru takas.
    if komsu.origin_synced and ben.origin_synced:
        rel_z = float(komsu.pos_z) - float(ben.pos_z)
    else:
        rel_z = 0.0

    # --- HIZ ----------------------------------------------------------------
    # v_xy_valid dusukse hizi 0 aliyoruz: kapanma hizi kapisi (c) devre disi
    # kalir ama `d3 <= hard` tam-itme yolu HALA calisir. Yani ongoru kaybolur,
    # sert kabuk durur. Uydurma hizla erken itmekten iyi.
    if komsu.v_xy_valid and ben.v_xy_valid:
        rel_vx = float(komsu.vel_x) - float(ben.vel_x)
        rel_vy = float(komsu.vel_y) - float(ben.vel_y)
        rel_vz = float(komsu.vel_z) - float(ben.vel_z)
    else:
        rel_vx = rel_vy = rel_vz = 0.0

    mesafe = math.sqrt(rel_x * rel_x + rel_y * rel_y + rel_z * rel_z)

    degerler = (rel_x, rel_y, rel_z, rel_vx, rel_vy, rel_vz, mesafe)
    if not all(math.isfinite(d) for d in degerler):
        return None, ATLAMA_SAYISAL

    return NeighborObs(
        rel_x=rel_x,
        rel_y=rel_y,
        rel_z=rel_z,
        rel_vx=rel_vx,
        rel_vy=rel_vy,
        rel_vz=rel_vz,
        distance=mesafe,
    ), ''
