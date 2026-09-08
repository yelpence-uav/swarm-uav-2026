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
        # --- CUSTOM OFSET ONBELLEGI (8 Eylul 2026) ----------------------
        # 🔴 SAHADA OLCULDU. CUSTOM'da bir komut UC cerceve istiyor
        # (baslik + 2 ofset) ve alici ucunu de beklerken biri dusunce
        # komutun TAMAMI atiliyordu. Gorev 1'in ilk onboard ucusunda
        # takipcinin donus sirasinda aldigi hedef olculdu:
        #     21 mesaj / 29.4 sn = 0.72 Hz   (gonderim 2 Hz)
        #     aralik medyan 622 ms, MAX 12671 ms
        #     heading adimi medyan 6.5 deg, MAX 32.4 deg
        # 32.4 derecelik tek adim, 7.5 m yaricapta 4.2 m'lik ani hedef
        # sicramasi demek: kanat ucaklari hedefe atilip bekliyor, sonra
        # yine atiliyor — operatorun gordugu "bas-cek" salinimi bu.
        # Setpoint ileribeslemesi de onu dogruladi: |v| medyan 1.22 m/s,
        # MAX 4.20 m/s (3.4 kati sicrama).
        #
        # COZUM: CUSTOM ofsetleri her turda AYNI — diziliş `frozen_offsets`
        # ile donmus, tur basina degisen yalniz merkez ve heading. Yani
        # degismeyen veriyi saniyede iki kez yolluyor ve komutun tamamini
        # o cercevelerin sansina bagliyorduk. Artik kaynak basina son
        # GECERLI ofset kumesi saklaniyor; yeni baslik gelip ofset paketi
        # gelmezse eskisi kullaniliyor.
        #   once : komut icin 3/3 cerceve  -> tur basina basari ~%47
        #   sonra: ilk seferden sonra 1/3  -> ~%78
        # Gonderici DEGISMEDI (ofsetler yine gidiyor, yedek olarak),
        # protokol ve firmware DEGISMEDI.
        #
        # ⚠️ ONBELLEK AJAN LISTESI DEGISINCE GECERSIZ: slot sayisi
        # degistiyse eski ofsetler yanlis dizilis demek olurdu. Anahtar
        # bu yuzden (kaynak, ajan_listesi).
        # kaynak -> (ajan_anahtari, {slot_indeksi: ofset})
        self._ofset_onbellek: dict[int, tuple[tuple, dict]] = {}
        # kaynak -> son baslikta gorulen ajan anahtari (sahipsiz ofset
        # paketlerini dogru anahtarla onbellege yazabilmek icin).
        self._son_ajan_anahtari: dict[int, tuple] = {}
        #: Onbellekten karsilanan komut sayisi — teshis icin okunur.
        self.ofset_onbellek_kullanildi = 0

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
        """TIP_FORM_OFSET geldi (CUSTOM, paket başına 2 slot).

        🔴 SAHIPSIZ PAKET ARTIK ATILMIYOR, ONBELLEGI TAZELIYOR.
        Onbellek devreye girince komut BASLIKLA birlikte tamamlaniyor ve
        hemen ardindan gelen ofset paketleri "bekleyen montaj yok" diye
        dusuyordu. O hâlde onbellek ilk turdan sonra HIC tazelenmezdi ve
        diziliş gercekten degisirse (yeni snapshot) BAYAT ofsetler sonsuza
        kadar servis edilirdi — dusundugumuz kusurdan beter, sessiz bir
        yanlis. Simdi sahipsiz paket dogrudan onbellege yaziliyor: en fazla
        BIR tur bayat kalinir (5 Hz'de 200 ms), sonra duzelir.
        """
        self._temizle(simdi)
        m = self._bekleyen.get(kaynak)
        if m is None:
            self.sahipsiz_parca_sayisi += 1
            anahtar = self._son_ajan_anahtari.get(kaynak)
            if anahtar is not None:
                self._onbellege_yaz(
                    kaynak, anahtar,
                    {veri.slot_bas + i: o
                     for i, o in enumerate(veri.slot_ofsetleri())},
                    birlestir=True,
                )
            return None
        for i, ofset in enumerate(veri.slot_ofsetleri()):
            m.ofsetler[veri.slot_bas + i] = ofset
        return self._tamamla(kaynak, simdi)

    def _onbellege_yaz(self, kaynak: int, anahtar: tuple, ofsetler: dict,
                       birlestir: bool = False) -> None:
        """CUSTOM ofsetlerini onbellege yazar; kadro degisince SIFIRLAR."""
        mevcut = self._ofset_onbellek.get(kaynak)
        if birlestir and mevcut is not None and mevcut[0] == anahtar:
            yeni = dict(mevcut[1])
            yeni.update(ofsetler)
        else:
            yeni = dict(ofsetler)
        self._ofset_onbellek[kaynak] = (anahtar, yeni)

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
            anahtar = tuple(int(a) for a in ajanlar)
            self._son_ajan_anahtari[kaynak] = anahtar
            if len(m.ofsetler) >= len(ajanlar):
                ofsetler = [m.ofsetler[i] for i in range(len(ajanlar))]
                self._onbellege_yaz(kaynak, anahtar, m.ofsetler)
            else:
                # Ofset paketi eksik — ONBELLEGE DUS (bkz. __init__ notu).
                onbellek = self._ofset_onbellek.get(kaynak)
                if (onbellek is None or onbellek[0] != anahtar
                        or len(onbellek[1]) < len(ajanlar)):
                    return None                   # offset paketleri bekleniyor
                ofsetler = [onbellek[1][i] for i in range(len(ajanlar))]
                self.ofset_onbellek_kullanildi += 1
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
