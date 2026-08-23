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
    komsu_id: int | None = None,
) -> tuple[NeighborObs | None, str]:
    """Ham `AgentStatus` ciftini CA'nin bekledigi `NeighborObs`a cevirir.

    komsu_id: dikey RUTBE icin kimlik. Dugum bunu ZATEN biliyor (abonelik
    anahtari); mesajin kendi `agent_id` alanina guvenmek yerine disaridan
    vermek daha saglam — bos bir alan dikey kurali SESSIZCE kapatirdi.

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
    # 🔴 23 AGUSTOS 2026'DA DUZELTILDI — eski hali IKI FARKLI REFERANSTAN
    # olculen sayiyi birbirinden cikariyordu.
    #
    # ESKI HALI:  rel_z = komsu.pos_z - ben.pos_z
    #
    #   ben.pos_z   : MAVROS odometry = EKF YEREL NED. Sifir noktasi EKF'in
    #                 acilis origin'i; esp32_bridge_node.py:1697'de olculdu:
    #                 "boot'a bagli ~10 m kayabiliyor VE ucus boyunca suruyor"
    #   komsu.pos_z : mesh POSE = -(alt_amsl - home_amsl), yani komsunun
    #                 KENDI KALKIS NOKTASINA gore irtifasi
    #                 (esp32_bridge_node.py:938, 949)
    #
    # Iki ayri datum. Farklari SABIT BIR YANLILIK tasiyor ve o yanlilik
    # 10 m mertebesinde olabiliyor.
    #
    # NEDEN SIMDIYE KADAR PATLAMADI: rel_z yalniz 3B mesafeyi (d3) biraz
    # kaydiriyordu ve `origin_synced` kapisi cogu zaman 0.0 yaziyordu.
    # DIKEY YOL VERMEDE ise rel_z DOGRUDAN KUMANDA SINYALI: 10 m'lik bir
    # yanlilik ucagin "zaten yeterince yukaridayim" sanip HIC kacmamasi
    # demek. Yatay tarafta bu tuzagin uyarisi bu dosyanin basliginda zaten
    # var; dikeyde yoktu.
    #
    # DOGRU HALI: iki tarafta da GONDERENIN KULLANDIGI FORMULU kullan.
    # Geriye kalan tek hata iki ucagin kalkis noktalari arasindaki KOT
    # FARKI — ayni sahadan kalktiklari ve ikisi de ayni RTK bazindan
    # duzeldigi icin tipik olarak yarim metrenin altinda. Yer testi G0-1
    # bunu olcuyor: iki ucak kalkis noktasindayken rel_z ~ 0 cikmali.
    dikey_gecerli = (
        ben.home_alt_amsl_m != 0.0 and ben.gps_fix_type >= 3
        and math.isfinite(ben.alt_amsl_m)
    )
    if dikey_gecerli:
        ben_h = float(ben.alt_amsl_m) - float(ben.home_alt_amsl_m)
        komsu_h = -float(komsu.pos_z)
        rel_z = ben_h - komsu_h          # NED: + ise komsu BENDEN ASAGIDA
    else:
        # Kendi dikey datum'umuzu kuramiyoruz. rel_z=0 MUHAFAZAKAR yon
        # (d3 kuculur, yatay koruma erken devreye girer) ama dikey kural
        # bu komsu icin UYGULANMAZ — asagida agent_id=0 ile kapatiliyor.
        # Uydurma bir yukseklik farkina gore tirmanmak, hic tirmanmamaktan
        # kotudur: yanlis yone gitme ihtimalini de tasir.
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
        # RUTBE kimligi. Dikey datum kurulamadiysa 0 gecilir ve ca_core
        # dikey kurali bu komsu icin UYGULAMAZ — yatay koruma calismaya
        # devam eder. "Bilmiyorsan dikeyde hareket etme" kurali.
        agent_id=(
            int(komsu_id if komsu_id is not None else komsu.agent_id)
            if dikey_gecerli else 0
        ),
    ), ''
