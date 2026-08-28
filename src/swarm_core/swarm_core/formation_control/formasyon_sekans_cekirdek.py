# Copyright 2026 Yelpence
"""Formasyon geçiş testinin saf çekirdeği (ROS'suz).

⚠️ GEÇİCİ TEST APARATI — mission1 zinciri sahaya alındığında bu modül ve
`formasyon_sekans_node` SİLİNECEK. Kalıcı mimari değil; tek işi 28 Ağustos
formasyon geçiş testinde tarif kaynağı olmak (çizgi → ok başı → V).

NEDEN AYRI MODÜL
Sekansın bütün kararları (faz çizelgesi, kalkış kapısı, ağırlık merkezi,
heading seçimi, slot ataması, geçiş-yolu mesafe denetimi) burada ve saf —
`formasyon_montaj.py` / `ca_core.py` ile aynı kalıp. İki tüketicisi var:

    1. `formasyon_sekans_node`  (uçakta, ROS kabuğu)
    2. `gorev_kanit_ucus.py`    (YKİ'de, --kuru senaryo denetimi + harita)

Kuru testin uçaktaki düğümle BİREBİR AYNI fonksiyonları çağırması bilinçli:
harita neyi gösteriyorsa uçak onu uçar. İki ayrı kopya, 14 Ağustos'taki
"aynı sabit iki yerde" hatasının (CLAUDE.md §9) formasyon hâli olurdu.

SLOT SIRASI SÖZLEŞMESİ
Mesh'te atama, TIP_FORMASYON paketindeki `slot_ajan[]` SIRASIYLA taşınır ve
köprü o listeyi `FormationCommand.agent_ids`'ten aynen alır
(esp32_bridge_node._on_formation_out → pp.formasyon_paketle, "Slot sırasında
ajan ID'leri"). Yani bu modülün ürettiği `agent_ids[k]` = k. slotun sahibi.
"""

from __future__ import annotations

import math

from .formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_slot_offsets,
    hungarian_assignment,
    rotate_offset,
)

#: Senaryo adları → FormationCommand tipleri. Sıra testin kendisi:
#: yerden kalkış → çizgi → ok başı → V (operatör tarifi, 28 Ağustos).
FAZ_TIPLERI = {
    'cizgi': FORMATION_CIZGI,
    'okbasi': FORMATION_OKBASI,
    'v': FORMATION_V,
}

_TIP_ADLARI = {v: k for k, v in FAZ_TIPLERI.items()}


def faz_tipi(ad: str) -> int:
    """Faz adını FormationCommand tipine çevirir; bilinmeyen ad = hata."""
    anahtar = ad.strip().lower()
    if anahtar not in FAZ_TIPLERI:
        raise ValueError(
            f"bilinmeyen faz adi '{ad}' — gecerli: {sorted(FAZ_TIPLERI)}"
        )
    return FAZ_TIPLERI[anahtar]


def tip_adi(tip: int) -> str:
    """Tip sabitini okunur ada çevirir (log/harita için)."""
    return _TIP_ADLARI.get(int(tip), f'tip{tip}')


def faz_plani(fazlar: list[str], sureler: list[float]):
    """Faz listesi + süre listesini doğrulayıp [(tip, süre_s)] döner.

    Süre listesi fazlardan kısaysa SON değer tekrarlanır — parametre
    dosyasında tek sayı yazmak yetsin diye. Uzunsa hata: sessizce yutulan
    fazla süre, "2 dk sanıyordum 4 dk sürdü" tuzağı olurdu.
    """
    if not fazlar:
        raise ValueError('faz listesi bos')
    if not sureler:
        raise ValueError('sure listesi bos')
    if len(sureler) > len(fazlar):
        raise ValueError(
            f'sure listesi ({len(sureler)}) faz listesinden ({len(fazlar)}) '
            f'uzun — fazla degerler sessizce yutulmaz'
        )
    plan = []
    onceki_tip = None
    for i, ad in enumerate(fazlar):
        tip = faz_tipi(ad)
        if tip == onceki_tip:
            # formation_node atamayı formation_type'a donduruyor (freeze);
            # ardışık aynı tip reshape ÜRETMEZ. Bunu sessizce kabul etmek
            # "geçiş oldu sanıyorum" yanılgısı olurdu.
            raise ValueError(f'ardisik ayni faz: {ad} (reshape uretmez)')
        sure = float(sureler[i]) if i < len(sureler) else float(sureler[-1])
        if sure <= 0.0:
            raise ValueError(f'faz suresi > 0 olmali: {ad}={sure}')
        plan.append((tip, sure))
        onceki_tip = tip
    return plan


def toplam_sure_s(plan) -> float:
    """Faz planının toplam süresi."""
    return float(sum(sure for _tip, sure in plan))


def agirlik_merkezi(
    konumlar: dict[int, tuple[float, float]],
) -> tuple[float, float]:
    """Kadro konumlarının (ortak NED) ağırlık merkezi."""
    if not konumlar:
        raise ValueError('konum listesi bos')
    n = len(konumlar)
    sx = sum(p[0] for p in konumlar.values())
    sy = sum(p[1] for p in konumlar.values())
    return sx / n, sy / n


def otomatik_heading_deg(
    konumlar: dict[int, tuple[float, float]],
) -> float:
    """Kalkış diziliminden formasyon heading'ini türetir.

    Kural: uçakların yerdeki ana ekseni (PCA birinci bileşeni) bulunur ve
    ÇİZGİ formasyonunun yanal ekseni (slotların ±y açılımı) o eksene
    oturtulur → heading = eksen − 90°. Böylece rastgele bırakılan uçaklar
    çizgiye EN AZ yolla ve kesişmeden girer.

    Neden parametre değil de türetme: heading sahaya göre değişiyor ve
    uçaktaki env'i her saha oturumunda elle güncellemek (SSH) tam da bu
    testin kaldırmaya çalıştığı bağımlılık. Türetme deterministik: kuru
    test aynı konumlardan aynı heading'i hesaplar, operatör haritada
    GÖRÜP onaylar. Ayrı ayrı hesaplayan üç uçak cm'lik konum farklarıyla
    ancak derece kesri kadar ayrışır (süreklilik; slotta <0,2 m).

    İŞARET KURALI (kritik): PCA ekseni bir DOĞRUDUR, yönü mod 180°
    belirsizdir ve cm'lik gürültü işareti terslendirebilir — ilk yazımda
    birim test bunu yakaladı (iki uçak 180° farklı heading hesaplayıp
    liderlik devrinde OKBAŞI/V'nin ok yönünü terslerdi). Kural: eksen
    [0°,180°)'a katlanır, sonra kadroda kimliği EN KÜÇÜK olup eksene
    izdüşümü |0,5 m|'yi aşan uçağın izdüşümü pozitif olacak şekilde
    işaret seçilir. Uç uçaklar birbirinden metrelerce ayrık olduğu için
    cm gürültüsü bu kararı çeviremez; üç uçak da aynı sonucu bulur.

    Yozlaşık durumda (uçaklar tek noktada / izotrop) 0° döner — kuzey.
    """
    n = len(konumlar)
    if n < 2:
        return 0.0
    mx, my = agirlik_merkezi(konumlar)
    sxx = syy = sxy = 0.0
    for px, py in konumlar.values():
        dx, dy = px - mx, py - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    if sxx + syy < 1e-9:
        return 0.0
    # atan2(2Sxy, Sxx-Syy)/2: kovaryans ana ekseninin NED x'ten açısı,
    # (-90°, +90°] aralığında gelir; önce [0°, 180°)'a katla.
    eksen_rad = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    if eksen_rad < 0.0:
        eksen_rad += math.pi
    ux, uy = math.cos(eksen_rad), math.sin(eksen_rad)
    for a in sorted(konumlar):
        px, py = konumlar[a]
        izdusum = (px - mx) * ux + (py - my) * uy
        if abs(izdusum) > 0.5:
            if izdusum < 0.0:
                eksen_rad += math.pi
            break
    heading = math.degrees(eksen_rad) - 90.0
    return heading % 360.0


def atama(
    tip: int,
    konumlar: dict[int, tuple[float, float]],
    merkez: tuple[float, float],
    heading_deg: float,
    aralik_m: float,
    alfa_deg: float,
):
    """Slot atamasını hesaplar: (slot sırasında agent_ids, slot ofsetleri).

    Macar algoritması `formation_node`'un dağıtık atamasıyla AYNI maliyet
    matrisini (uçak → dünya slot mesafesi) kullanır. Bilinçli: liderin
    tarife gömdüğü sıra ile takipçinin yerel hesabı aynı girdiden aynı
    sonucu verirse formation_node "yerel kullanılıyor" der ve dağıtık
    puan korunur; ayrışırsa takipçi lidere düşer, çakışma yine olmaz.
    """
    ids = sorted(int(a) for a in konumlar)
    n = len(ids)
    slotlar = compute_slot_offsets(
        tip, n, float(aralik_m), math.radians(float(alfa_deg))
    )
    h_rad = math.radians(float(heading_deg))
    dunya = []
    for (ox, oy, _oz) in slotlar:
        rx, ry = rotate_offset(ox, oy, h_rad)
        dunya.append((merkez[0] + rx, merkez[1] + ry))
    maliyet = [
        [math.hypot(konumlar[a][0] - sx, konumlar[a][1] - sy)
         for (sx, sy) in dunya]
        for a in ids
    ]
    secim = hungarian_assignment(maliyet)  # secim[i] = ids[i]'nin slotu
    slot_sahibi = [0] * n
    for i, a in enumerate(ids):
        slot_sahibi[secim[i]] = a
    return slot_sahibi, [tuple(s) for s in slotlar]


def dunya_konumlari(
    agent_ids: list[int],
    ofsetler,
    merkez: tuple[float, float],
    heading_deg: float,
) -> dict[int, tuple[float, float]]:
    """atama() çıktısını dünya (ortak NED) konumlarına çevirir: {id: (x,y)}.

    Kuru test/harita bu fonksiyonla çizer; uçaktaki formation_node aynı
    rotate_offset ile uçar — iki taraf tek geometriden beslenir.
    """
    h_rad = math.radians(float(heading_deg))
    sonuc = {}
    for k, aid in enumerate(agent_ids):
        rx, ry = rotate_offset(ofsetler[k][0], ofsetler[k][1], h_rad)
        sonuc[int(aid)] = (merkez[0] + rx, merkez[1] + ry)
    return sonuc


def gecis_min_mesafe(
    tip_a: int,
    tip_b: int,
    n: int,
    aralik_m: float,
    alfa_deg: float,
    adim: int = 200,
) -> float:
    """A→B reshape sırasında en yakın çift mesafesinin alt sınırı (nominal).

    Uçaklar A'nın slotlarında kabul edilir; B'ye atama, formasyon
    zincirindekiyle aynı Macar maliyetiyle yapılır ve her uçak kendi B
    slotuna DÜZ HAT ile taşınır. formation_node'un rampası da hedefe düz
    ilerlediği için bu, nominal yörüngenin iyi bir modeli; GPS/takip
    hatası (~1 m, 26 Ağustos ölçümü) bunun ÜSTÜNE biner — kuru test bu
    yüzden sonucu paysız değil eşiklerle yorumlar.
    """
    alfa_rad = math.radians(float(alfa_deg))
    a_slot = compute_slot_offsets(tip_a, n, float(aralik_m), alfa_rad)
    b_slot = compute_slot_offsets(tip_b, n, float(aralik_m), alfa_rad)
    # A slotlarında oturan "uçaklar" B slotlarına Macar ile atanır.
    maliyet = [
        [math.hypot(ax - bx, ay - by) for (bx, by, _bz) in b_slot]
        for (ax, ay, _az) in a_slot
    ]
    secim = hungarian_assignment(maliyet)
    en_kucuk = float('inf')
    for k in range(adim + 1):
        t = k / adim
        noktalar = []
        for i in range(n):
            bx, by, _bz = b_slot[secim[i]]
            ax, ay, _az = a_slot[i]
            noktalar.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        for i in range(n):
            for j in range(i + 1, n):
                d = math.hypot(
                    noktalar[i][0] - noktalar[j][0],
                    noktalar[i][1] - noktalar[j][1],
                )
                if d < en_kucuk:
                    en_kucuk = d
    return en_kucuk


def kalkis_hazir_mi(
    kadro: list[int],
    irtifalar: dict[int, float],
    yaslar: dict[int, float],
    origin_senkron: dict[int, bool],
    hedef_irtifa_m: float,
    esik_orani: float,
    taze_s: float,
    irtifa_sart: bool = True,
):
    """Sekansın başlayabilmesi için kalkış kapısı: (hazır mı, eksikler).

    Kapı ÜÇ şartı birden arar — her uçak için:
      1. verisi taze (mesh'ten yaş <= taze_s)
      2. origin senkron (ortak NED'e oturmadan merkez hesabı anlamsız)
      3. irtifası hedefe ulaşmış (>= esik_orani × hedef)

    `irtifa_sart=False` YALNIZ G0 yer testi için: uçaklar yerdeyken
    (/ws/gozlem takılı, tarif uçağı süremez) zincirin geri kalanını
    ölçmek üzere 3. şart atlanır; tazelik ve origin şartı AYNEN kalır —
    verisi olmayan uçakla tarif kurulamaz.

    Eksikler listesi loglama için: 15 Ağustos dersi — kapı sessiz
    kalırsa "neden başlamadı" sorusu cevapsız kalıyor (formation_node
    `_neden_yok` ile aynı gerekçe).
    """
    eksikler = []
    esik_m = float(hedef_irtifa_m) * float(esik_orani)
    for a in kadro:
        a = int(a)
        yas = yaslar.get(a)
        if yas is None:
            eksikler.append(f'drone{a}: veri HIC gelmedi')
            continue
        if yas > taze_s:
            eksikler.append(f'drone{a}: veri bayat ({yas:.1f}s)')
            continue
        if not origin_senkron.get(a, False):
            eksikler.append(f'drone{a}: origin_synced degil')
            continue
        if not irtifa_sart:
            continue
        irtifa = irtifalar.get(a)
        if irtifa is None or irtifa < esik_m:
            gosterim = 'yok' if irtifa is None else f'{irtifa:.1f} m'
            eksikler.append(
                f'drone{a}: irtifa {gosterim} < esik {esik_m:.1f} m'
            )
    return (not eksikler), eksikler
