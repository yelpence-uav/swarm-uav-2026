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


def lider_onde(lider_id, agent_ids) -> list:
    """Tarifteki slot sirasini uretir: LIDER slot 0, kalani sirali.

    4 Eylul 2026, operator karari (YALNIZ GOREV 2): "ylp00 kalici lider ve
    her zaman ortada."

    NEDEN BU FONKSIYON SIRAYI URETIYOR: slot atamasi kimlik SIRASINA bagli
    (slot i <-> agent_ids[i]; Macar YOK, KARAR-11) ve compute_slot_offsets()
    slot 0'i her zaman (0,0,0) uretiyor. O nokta UC formasyonun da
    tepe/merkezi: cizgi -> hattin ortasi, okbasi -> uc, V -> arka kose.
    Yani "lider ortada" demek "lider agent_ids[0]" demek; baska bir
    mekanizmaya gerek yok.

    ONCESINDE sira dogrudan SURU_KADRO'dan geliyordu. Kadro "3 1" diye
    yazilsaydi slot 0 ylp02'ye giderdi ve HICBIR YERDE hata gorunmezdi —
    2 Eylul kume-toplanma olayinin sinifindan sessiz bir env bagimliligi.

    Mesh'te de korunur: TIP_FORMASYON payload'i `slot_ajan[i] = i. slottaki
    ajan` seklinde SIRAYI tasiyor (packet_parser:1085), alici ofsetleri ayni
    sirada yeniden uretiyor. Protokol degismedi.

    Args:
        lider_id: Slot 0'a oturacak kimlik. Cagiran taraf tarif basan
            ucaktir (tarif_yayinlanir_mi kapisini gecmistir), yani bu kendi
            kimligidir.
        agent_ids: Kadro. Sirasi onemsiz; cikti deterministik.

    Returns:
        list[int]: [lider_id] + sirali kalanlar. `lider_id` kadroda yoksa
        yalnizca sirali kadro doner — uydurma bir kimlik slot 0'a
        konulmaz, yoksa ofset dizisi kadroyla ayni boyda olmaz.
    """
    kalan = sorted(int(a) for a in agent_ids if int(a) != int(lider_id))
    if len(kalan) == len(list(agent_ids)):
        return kalan
    return [int(lider_id)] + kalan


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
