# Copyright 2026 Yelpence
"""Formasyon tarifinin TEK yayincisi kurali — 3 Eylul 2026 saha olayi.

OLAY: ylp00+ylp02'de env artigi SURU_KADRO="1 3" vardi (ylp01 dogru).
SwC ile formasyon degisince UC mode_manager birden tarif basti; ikisi
[1,3]'lu, biri [1,2,3]'lu, merkezleri de farkli. formation_node'lar
celiskili tariflerle beslendi ve uc ucak havada ~1 m'lik kumeye
toplandi — carpismamalari sans. Kadro duzeltildi AMA mimari acik kaldi:
her ucak tarif basabildigi surece HER gorus ayriligi celiskili tarife
donusur (kadro yalnizca o gunku tetikti).

KURAL: FormationCommand'i yalniz LIDER basar. Digerlerinin
formation_node'u tarifi mesh'ten (liderinkini) alir — yol zaten kanitli.
Yan fayda: MOVEMENT'ta tarif trafigi ucte bire iner.

Lider kaynagi consensus'un ElectionResult'i (internal + mesh/public).
Election HIC gelmemisse deterministik yedek: kadronun EN KUCUK agent_id'si
(ucu de ayni sonuca varir, celiski uretmez). Yedek olmasaydi election'siz
ortamda yayin tamamen susar ve formasyon degisimi SESSIZCE olurdu —
B15/30 Agustos "sessiz kapi" dersinin tekrarina izin yok.
"""


def tarif_yayinlanir_mi(agent_id, lider_id, agent_ids) -> bool:
    """Bu ucak FormationCommand yayinlayabilir mi?"""
    if lider_id is not None:
        return int(agent_id) == int(lider_id)
    if not agent_ids:
        return False
    return int(agent_id) == min(int(a) for a in agent_ids)


def degisim_islenir_mi(req_tip, aktif_tip, yeni_aralik, eski_aralik,
                       tolerans: float = 0.01) -> bool:
    """Formasyon degisim talebi GERCEK bir degisim mi?

    1 Eylul ucusunda ayni degisim 50 ms'de bir yeniden islendi (mesh
    komutlari degisim bayragini surekli tasiyor): morf kilidi surekli
    tazelendi, log boguldu, tarif gereksiz yeniden basildi. Ayni tip +
    ayni aralik = tekrar; islenmez. Ayni tipte ARALIK degisimi (daraltma)
    gercek degisimdir.
    """
    if int(req_tip) != int(aktif_tip):
        return True
    return abs(float(yeni_aralik) - float(eski_aralik)) > tolerans
