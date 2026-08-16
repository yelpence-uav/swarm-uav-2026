"""formasyon_montaj.py — çok parçalı formasyon paketlerini birleştirir.

NEDEN AYRI MODÜL
`esp32_bridge_node` 1500+ satır ve ROS'a bağımlı. Montaj mantığı saf: girdi
`packet_parser` veri sınıfları, çıktı düz bir dataclass. Böylece ROS ortamı
kurmadan birim testi yazılabiliyor — `cobs.py` / `crc16.py` ile aynı kalıp.

MESH'TE FORMASYON KAÇ PARÇA GELİR

    TIP_FORMASYON        (zorunlu)  başlık: tip, merkez, heading, spacing,
                                    kanat açısı, slot 0-3
    TIP_FORMASYON_DEVAM  (5+ ajan)  slot 4-7
    TIP_FORM_OFSET       (CUSTOM)   açık offsetler, paket başına 2 slot

3 drone + adlandırılmış formasyon (OKBASI/V/CIZGI) = **tek paket**, montaj
anında tamamlanır. Devam/offset yolu yalnız 5+ ajan ya da CUSTOM'da işler.

OFFSETLER NEDEN HESAPLANIYOR, TAŞINMIYOR
`compute_slot_offsets(tip, n, spacing, alfa)` saf bir fonksiyon: her dronda
birebir aynı sonucu verir. Konum bağımlı olan slot ATAMASI ve o `slot_ajan`
listesinin SIRASINDA taşınıyor. Bkz. docs/MESH_PROTOKOL_KARARLARI.md KARAR 4.
CUSTOM (jüri dizilişi) formülden türetilemez, offsetleri açıkça gelir.

ZAMAN AŞIMI
Eksik parça sonsuza kadar beklenmez. `ZAMAN_ASIMI_S` geçince yarım montaj
düşürülür ve sayaç artar — sessizce beklemek "formasyon neden gelmiyor"
sorusunu cevapsız bırakırdı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_CUSTOM,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_slot_offsets,
)

from . import packet_parser as pp

#: Yarım montajın düşürülmesi için beklenecek süre.
#: Formasyon 5 Hz akıyor (200 ms); 1 sn = 5 tur pay. Daha kısası ağ
#: dalgalanmasında sağlam montajı düşürür, daha uzunu bayat parçayı
#: yeni başlıkla karıştırma riskini büyütür.
ZAMAN_ASIMI_S = 1.0

#: Offsetlerin formülden türetilebildiği formasyonlar.
PARAMETRIK_TIPLER = (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI)


@dataclass
class TamFormasyon:
    """Birleştirilmiş formasyon hedefi — ROS mesajına çevrilmeye hazır.

    Bilinçli olarak `FormationCommand` DEĞİL: bu modülün `swarm_interfaces`'a
    bağımlı olmaması test edilebilirliğini koruyor.
    """

    formasyon_tipi: int
    merkez_kuzey_m: float
    merkez_dogu_m: float
    merkez_asagi_m: float
    heading_deg: float
    spacing_m: float
    maks_hiz_mps: float
    kanat_alfa_deg: float
    ajan_ids: list[int]                                   # slot sırasında
    ofsetler: list[tuple[float, float, float]]            # ajan_ids ile paralel


@dataclass
class _Montaj:
    """Tek kaynaktan gelen parçaların biriktiği geçici durum."""

    baslik: pp.FormasyonVeri
    ts: float
    devam_slotlar: list[int] | None = None
    ofsetler: dict[int, tuple[float, float, float]] = field(default_factory=dict)


class FormasyonMontaj:
    """Kaynak (drone) başına formasyon parçalarını biriktirip tamamlar.

    Kullanım: her parça için ilgili `*_ekle` çağrılır; montaj tamamlanınca
    `TamFormasyon` döner, değilse `None`.
    """

    def __init__(self, zaman_asimi_s: float = ZAMAN_ASIMI_S) -> None:
        self._zaman_asimi_s = float(zaman_asimi_s)
        self._bekleyen: dict[int, _Montaj] = {}
        #: Zaman aşımına düşen montaj sayısı — teşhis için okunur.
        self.zaman_asimi_sayisi = 0
        #: Başlığı görülmemiş devam/offset parçası sayısı.
        self.sahipsiz_parca_sayisi = 0

    # ---------------------------------------------------------------- ekle ---
    def baslik_ekle(self, kaynak: int, veri: pp.FormasyonVeri,
                    simdi: float) -> TamFormasyon | None:
        """TIP_FORMASYON geldi. Yeni montaj başlatır; tamsa hemen döner.

        Yeni başlık ESKİ montajı bilerek DÜŞÜRÜR: formasyon periyodik (5 Hz)
        akıyor, yarım kalmış eski turu yeni turla karıştırmak slot atamasını
        bozar — iki drone aynı slotu hedefleyebilir.
        """
        self._temizle(simdi)
        onceki = self._bekleyen.pop(kaynak, None)
        if onceki is not None:
            self.zaman_asimi_sayisi += 1
        self._bekleyen[kaynak] = _Montaj(baslik=veri, ts=simdi)
        return self._tamamla(kaynak, simdi)

    def devam_ekle(self, kaynak: int, slotlar: list[int],
                   simdi: float) -> TamFormasyon | None:
        """TIP_FORMASYON_DEVAM geldi (slot 4-7)."""
        self._temizle(simdi)
        m = self._bekleyen.get(kaynak)
        if m is None:
            self.sahipsiz_parca_sayisi += 1
            return None
        m.devam_slotlar = list(slotlar)
        return self._tamamla(kaynak, simdi)

    def ofset_ekle(self, kaynak: int, veri: pp.FormOfsetVeri,
                   simdi: float) -> TamFormasyon | None:
        """TIP_FORM_OFSET geldi (CUSTOM, paket başına 2 slot)."""
        self._temizle(simdi)
        m = self._bekleyen.get(kaynak)
        if m is None:
            self.sahipsiz_parca_sayisi += 1
            return None
        for i, ofset in enumerate(veri.slot_ofsetleri()):
            m.ofsetler[veri.slot_bas + i] = ofset
        return self._tamamla(kaynak, simdi)

    # -------------------------------------------------------------- yardim ---
    def _temizle(self, simdi: float) -> None:
        """Zaman aşımına düşen montajları atar ve sayar."""
        dusen = [k for k, m in self._bekleyen.items()
                 if simdi - m.ts > self._zaman_asimi_s]
        for k in dusen:
            del self._bekleyen[k]
            self.zaman_asimi_sayisi += 1

    def _tamamla(self, kaynak: int, simdi: float) -> TamFormasyon | None:
        """Montaj tamsa TamFormasyon üretir, değilse None."""
        m = self._bekleyen.get(kaynak)
        if m is None:
            return None
        b = m.baslik

        ajanlar = b.dolu_slotlar()
        if b.devam_var:
            if m.devam_slotlar is None:
                return None                       # devam paketi bekleniyor
            ajanlar = ajanlar + [a for a in m.devam_slotlar if a]
        if not ajanlar:
            # Boş slot listesi anlamsız; montajı düşür ki bir sonraki başlık
            # temiz başlasın.
            del self._bekleyen[kaynak]
            return None

        tip = int(b.formasyon_tipi)
        if tip in PARAMETRIK_TIPLER:
            try:
                slotlar = compute_slot_offsets(
                    tip, len(ajanlar), b.spacing_m,
                    math.radians(float(b.kanat_alfa_deg)),
                )
            except ValueError:
                # Geçersiz spacing/alfa: montajı düşür. Uyarıyı çağıran
                # (köprü) basar — bu modül loglamıyor.
                del self._bekleyen[kaynak]
                return None
            ofsetler = [(float(o[0]), float(o[1]), float(o[2])) for o in slotlar]
        elif tip == FORMATION_CUSTOM:
            if len(m.ofsetler) < len(ajanlar):
                return None                       # offset paketleri bekleniyor
            ofsetler = [m.ofsetler[i] for i in range(len(ajanlar))]
        else:
            # Bilinmeyen formasyon tipi (0 = UNKNOWN dahil). Montajı düşür;
            # çağıran uyarır.
            del self._bekleyen[kaynak]
            return None

        del self._bekleyen[kaynak]
        return TamFormasyon(
            formasyon_tipi=tip,
            merkez_kuzey_m=b.merkez_kuzey_m,
            merkez_dogu_m=b.merkez_dogu_m,
            merkez_asagi_m=b.merkez_asagi_m,
            heading_deg=b.heading_deg,
            spacing_m=b.spacing_m,
            maks_hiz_mps=b.maks_hiz_mps,
            kanat_alfa_deg=float(b.kanat_alfa_deg),
            ajan_ids=ajanlar,
            ofsetler=ofsetler,
        )


def parcala(ajan_ids: list[int], formasyon_tipi: int,
            ofsetler: list[tuple[float, float, float]] | None = None
            ) -> tuple[bool, list[tuple[int, list[tuple[float, float, float]]]]]:
    """Gönderme tarafı: kaç ek paket gerekiyor, hangi dilimlerle.

    Args:
        ajan_ids (list[int]): Slot sırasında ajan ID'leri.
        formasyon_tipi (int): FORMATION_*.
        ofsetler (list | None): CUSTOM için açık offsetler.

    Returns:
        tuple: (devam_gerekli, [(slot_bas, ofset_dilimi), ...]).
        `devam_gerekli` True ise `TIP_FORMASYON_DEVAM` da gönderilmeli.
        Liste boşsa `TIP_FORM_OFSET` gerekmiyor.
    """
    devam = len(ajan_ids) > pp.FORMASYON_SLOT_PAKET
    dilimler: list[tuple[int, list[tuple[float, float, float]]]] = []
    if formasyon_tipi == FORMATION_CUSTOM and ofsetler:
        adim = pp.FORM_OFSET_SLOT_PAKET
        for bas in range(0, min(len(ofsetler), len(ajan_ids)), adim):
            dilimler.append((bas, list(ofsetler[bas:bas + adim])))
    return devam, dilimler
