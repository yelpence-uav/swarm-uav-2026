# Copyright 2026 Yelpence
"""EN YAKIN SLOT atamasi — lider slot 0'a SABIT. Saf mantik, ROS yok.

NEDEN VAR (operator istegi 4 Eylul, gerekcesi 5 Eylul'de OLCULDU)

Atama bugune kadar KIMLIK SIRASIYDI (Macar YOK, KARAR-11 notu): slot i
<-> agent_ids[i]. Bu, ucaklarin YERE hangi sirayla dizildigine bagli bir
varsayimdi ve tutmadigi anda ucaklar BIRBIRININ USTUNDEN geciyordu.

5 Eylul olcumu (ylp00 8.79,4.32 · ylp01 3.95,-3.79 · aralik 9.44 m):
kimlik sirasiyla cizgi secilseydi ylp01'in slotu ylp00'in OTE TARAFINA
dusuyordu ve ylp01 11,72 m yol yapip ylp00'in uzerinden gececekti — hem
de kacinmanin KAPALI oldugu 2-3 m'de (altitude_gate_m = 3,0).
4 Eylul'de ayni sinif olay yasandi: kuru test 1,94 m ile KALDI ve sorun
ucaklari FIZIKSEL OLARAK takas ederek cozuldu.

KURAL

  1. LIDER her zaman SLOT 0. Slot 0 uc formasyonun da tepe/merkezi ve
     merkez zaten liderin konumu (mode_context.konumdan_tohumla), yani
     lider HIC KIMILDAMAZ. Operatorun dizilisi bozulmaz.
  2. Kalan ucaklar kalan slotlara EN YAKIN olacak sekilde atanir
     (Macar/hungarian, toplam yolu enazlar).

Sonuc: dizilis hangi sirayla olursa olsun kimse karsiya gecmez. Finalde
dizilisi biz secemezsek bu kural SART.

⚠️ KAPSAM: yalniz GOREV 2 (mode_manager). Gorev 1'in atamasini mission1
yapiyor (formation_cmd.build_slot_assignment, zaten Macar) ve o zincir
4 Eylul aksami uctan uca uctu — DOKUNULMADI.
"""

import math

from swarm_core.formation_control.formation_geometry import (
    hungarian_assignment,
    rotate_offset,
)


def slot_dunya_konumlari(slotlar, merkez_x, merkez_y, heading_deg):
    """Govde cercevesindeki slot ofsetlerini DUNYA (NED) konumuna cevirir.

    formation_node ile AYNI donusum (rotate_offset) bilerek kullaniliyor:
    iki ayri kopya isaret ya da eksen sirasinda sessizce kayabilir.
    """
    h = math.radians(heading_deg)
    out = []
    for (ox, oy) in [(s[0], s[1]) for s in slotlar]:
        rx, ry = rotate_offset(ox, oy, h)
        out.append((merkez_x + rx, merkez_y + ry))
    return out


def slot_sirasi(lider_id, agent_ids, konumlar, slot_xy):
    """Slot sirasindaki ajan listesini doner (index i = i. slot).

    Args:
        lider_id: Slot 0'a sabitlenecek kimlik. Kadroda yoksa ya da 0 ise
            atama TAMAMEN en-yakina birakilir (lider capasi olmadan).
        agent_ids: Kadro.
        konumlar: {agent_id: (x, y)} — olculen NED konumlari.
        slot_xy: [(x, y)] — slot dunya konumlari, slot sirasinda.

    Returns:
        list[int]: index i, i. slottaki ajan. Konumu eksik ajan varsa
        KIMLIK SIRASINA dusulur — eksik veriyle "en yakin" hesaplamak
        sessizce yanlis atama uretirdi.
    """
    ids = [int(a) for a in agent_ids]
    if not ids or len(slot_xy) < len(ids):
        return sorted(ids)
    if any(a not in konumlar for a in ids):
        return sorted(ids)

    lider = int(lider_id) if lider_id else 0
    if lider in ids:
        kalan = [a for a in ids if a != lider]
        kalan_slot = list(range(1, len(slot_xy)))
        sonuc = {0: lider}
    else:
        kalan = list(ids)
        kalan_slot = list(range(len(slot_xy)))
        sonuc = {}

    if kalan:
        maliyet = [
            [math.dist(konumlar[a], slot_xy[si]) for si in kalan_slot]
            for a in kalan
        ]
        atama = hungarian_assignment(maliyet)
        for i, a in enumerate(kalan):
            sonuc[kalan_slot[atama[i]]] = a

    return [sonuc[i] for i in sorted(sonuc)]
