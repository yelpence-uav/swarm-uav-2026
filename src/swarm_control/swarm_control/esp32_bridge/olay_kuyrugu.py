# Copyright 2026 Yelpence
"""Olay yolunun SAF mantığı — bütçe, tekrar, sıra numarası.

NEDEN AYRI MODUL (27 Agustos 2026)
----------------------------------
ROS sembolu (rclpy, Node, parametre) KULLANMAZ. Boylece dizustunde, konteyner
ve donanim olmadan test edilebilir. Depo bu kalibi zaten kullaniyor:
`rtk_pure.h` ayni gerekceyle ayrilmis ("Arduino/ESP-IDF sembolu kullanmaz,
PlatformIO native ortaminda donanimsiz derlenip test edilebilir"), carpisma
onlemenin cekirdegi `ca_core.py` de oyle.

Burada yasayan uc karar:

1. BUTCE (jeton kovasi). Bir olay kaynagi cildirirsa mesh'i yememeli.
   26/27 Agustos'ta MAVROS'un GCS hatti bozulunca tek oturumda 5 MILYON satir
   uretti; ayni sey olay yolunda olsaydi suru telemetrisini bogardi.

2. TEKRAR. Broadcast'te ACK YOK. Operator onceligi: "loglarin cok seri
   akmasina gerek yok, asil onemli olan YKI'ye SAGLAM sekilde ulasmasi."
   Yani hiz dusuk tutulup guvenilirlik tekrarla aliniyor.

3. SIRA NUMARASI. Tek bayt, 255'ten sonra sarar. Teslimati garanti edemeyiz
   ama YKI BOSLUGU GOREBILIR — sessiz kayip yerine bilinen kayip.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OlayKuyrugu:
    """Bütçe + tekrar zamanlaması. Zaman DIŞARIDAN verilir (test edilebilirlik)."""

    butce_hz: float = 1.0
    patlama: float = 4.0
    tekrar: int = 3
    tekrar_aralik_s: float = 0.25
    halka: int = 32

    # --- ic durum ---
    _jeton: float = field(default=0.0, init=False)
    _jeton_ts: float = field(default=0.0, init=False)
    _sira: int = field(default=0, init=False)
    _kuyruk: list = field(default_factory=list, init=False)
    _halka_tampon: list = field(default_factory=list, init=False)
    dusen: int = field(default=0, init=False)
    gonderilen: int = field(default=0, init=False)
    _dusen_rapor_ts: float = field(default=0.0, init=False)
    _yineleme: dict = field(default_factory=dict, init=False)

    def basla(self, now: float) -> None:
        """Zaman tabanını kurar. Node açılışında bir kez çağrılır."""
        self._jeton = float(self.patlama)
        self._jeton_ts = now
        self._dusen_rapor_ts = now

    # ------------------------------------------------------------------ bütçe
    def _jeton_tazele(self, now: float) -> None:
        self._jeton = min(
            float(self.patlama),
            self._jeton + max(0.0, now - self._jeton_ts) * float(self.butce_hz),
        )
        self._jeton_ts = now

    def izin_var_mi(self, now: float) -> bool:
        """Bütçe bir olaya izin veriyor mu; veriyorsa jetonu HARCAR.

        Vermiyorsa `dusen` artar — sessizce dusurmek, defterin "tamam"
        gorunmesi demek olurdu.
        """
        self._jeton_tazele(now)
        if self._jeton < 1.0:
            self.dusen += 1
            return False
        self._jeton -= 1.0
        return True

    # ------------------------------------------------------------- sıra / kuyruk
    def sonraki_sira(self) -> int:
        """Tek baytlık, saran sayaç."""
        self._sira = (self._sira + 1) & 0xFF
        return self._sira

    def kuyrukla(self, payload: bytes, now: float) -> None:
        """Olayı tekrar kuyruğuna ve halka tampona koyar.

        Ilk gonderim HEMEN (sonraki_ts = 0), kalan tekrarlar araliklarla.
        """
        self._kuyruk.append([payload, max(1, int(self.tekrar)), 0.0])
        self._halka_tampon.append(payload)
        fazla = len(self._halka_tampon) - max(1, int(self.halka))
        if fazla > 0:
            del self._halka_tampon[:fazla]

    def hazir_olanlar(self, now: float) -> list[bytes]:
        """Zamanı gelmiş gönderimleri döner ve kuyruğu ilerletir."""
        cikan: list[bytes] = []
        kalanlar = []
        for payload, kalan, sonraki in self._kuyruk:
            if now < sonraki:
                kalanlar.append([payload, kalan, sonraki])
                continue
            cikan.append(payload)
            self.gonderilen += 1
            if kalan - 1 > 0:
                kalanlar.append(
                    [payload, kalan - 1, now + float(self.tekrar_aralik_s)]
                )
        self._kuyruk = kalanlar
        return cikan

    # ------------------------------------------------------------- düşen raporu
    def dusen_raporu(self, now: float, periyot_s: float = 10.0) -> int | None:
        """Bildirilecek düşen sayısı; yoksa None. Sayacı sıfırlar.

        Bu bildirim BUTCEYE GIRMEZ: butce yuzunden dusurulen bir seyi anlatan
        mesaji da butceye tabi tutmak, tam da anlatmasi gereken durumda
        susturur.
        """
        if self.dusen <= 0:
            return None
        if (now - self._dusen_rapor_ts) < periyot_s:
            return None
        self._dusen_rapor_ts = now
        n = self.dusen
        self.dusen = 0
        return n

    # -------------------------------------------------------------- yineleme
    def yinelenen_mi(self, anahtar, now: float,
                     pencere_s: float = 5.0) -> bool:
        """Aynı olay bu pencerede zaten gönderildi mi.

        27 AGUSTOS, CANLI TESTTE BULUNDU: `esp32_bridge._diag_yayinla` her
        saniye bir SystemEvent yayinliyor (mesh saglik sayaclari, yerel
        swarm_fsm icin). Aktarici onu yakalayinca butcenin TAMAMINI yedi:
        defter saniyede bir ayni satirla dolardi ve — daha kotusu — GERCEK
        olaylar butce dolu oldugu icin DUSERDI.

        Bu suzgec genel: hangi dugum olursa olsun, ayni olayi pencere
        icinde bir kez gecirir. Periyodik bir kaynak eklendiginde yeniden
        ayni tuzaga dusulmesin diye tip bazli kara liste yerine bu secildi.
        """
        eski = self._yineleme.get(anahtar)
        if eski is not None and (now - eski) < pencere_s:
            return True
        self._yineleme[anahtar] = now
        # Sozluk sinirsiz buyumesin: pencerenin cok disinda kalanlari at.
        if len(self._yineleme) > 128:
            for k in [k for k, t in self._yineleme.items()
                      if (now - t) > pencere_s * 4]:
                del self._yineleme[k]
        return False

    # ------------------------------------------------------------------ halka
    def halka_icerik(self) -> list[bytes]:
        """Son gönderilen olaylar (tekrar-isteme eklenirse buradan çıkacak)."""
        return list(self._halka_tampon)


class BoslukIzleyici:
    """Alıcı tarafı: kopyaları eler, GERÇEK kayıpları sayar.

    NEDEN GECIKMELI ONAY (27 Agustos 2026)
    --------------------------------------
    Her olay `tekrar` kez, ~250 ms arayla yayilir ve hepsi AYNI sira_no'yu
    tasir. Yogun anda yeni bir olay, onceki olayin tekrarlarindan ONCE
    varabilir — yani alicida sira KARISIK gorunur:

        gonderim : 5 5 5 6 6 6
        varis    : 5 6 5 6 5 6        <- naif sayac burada "kayip" sanir

    Naif bir "beklenen != gelen -> kayip" sayaci bu durumda YANLIS ALARM
    uretirdi. Yanlis kayip raporu, defterin guvenilirligini bitirirdi —
    "3 olay kacti" yazip aslinda kacmamis olmak, hic yazmamaktan kotudur.

    Bu yuzden atlanan sira_no'lar once BEKLEYEN'e alinir; `bekleme_s`
    icinde gelirlerse sessizce silinir, gelmezlerse KAYIP sayilir.
    """

    def __init__(self, bekleme_s: float = 2.0, pencere: int = 64,
                 makul_kayip: int = 16) -> None:
        self.bekleme_s = float(bekleme_s)
        self.pencere = int(pencere)
        # Bundan BUYUK bir atlama "kayip" degil SAYAC SICRAMASI sayilir.
        # Gerekce: sira_no tek bayt ve sariyor, yani 200 -> 1 gecisi hem
        # "56 olay kayboldu" hem "ucak yeniden basladi, sayac 1'e dondu"
        # diye okunabilir — sira numarasindan AYIRT EDILEMEZ.
        # 1 Hz butcede 16 ardisik kayip = 16 saniyelik tam karartma; bunun
        # ustu gercek kayiptan cok yeniden baslatmadir.
        # SESSIZ GECMIYOR: ayri sayacta tutulup ayri bildiriliyor, cunku
        # "bilmiyorum" demek "hicbir sey olmadi" demekten iyidir.
        self.makul_kayip = int(makul_kayip)
        self._gorulen: dict[int, list[int]] = {}
        self._bekleyen: dict[int, dict[int, float]] = {}
        self._son: dict[int, int] = {}
        self._sicrama: dict[int, int] = {}

    @staticmethod
    def _ileri_mi(yeni: int, eski: int) -> bool:
        """Saran tek baytta `yeni`, `eski`den ileride mi (yarim tur payi)."""
        return ((yeni - eski) & 0xFF) < 128

    def gelen(self, drone_id: int, sira: int, now: float) -> bool:
        """Yeni bir olay mı (True) yoksa kopya mı (False).

        Kopyalar tekrar mekanizmasinin dogal sonucu — hata degil.
        """
        gorulen = self._gorulen.setdefault(drone_id, [])
        bekleyen = self._bekleyen.setdefault(drone_id, {})

        if sira in gorulen:
            return False                       # tekrarin kopyasi

        gorulen.append(sira)
        fazla = len(gorulen) - self.pencere
        if fazla > 0:
            del gorulen[:fazla]

        if sira in bekleyen:
            # Gecikmeli geldi — kayip DEGILMIS.
            del bekleyen[sira]
            return True

        son = self._son.get(drone_id)
        if son is not None and self._ileri_mi(sira, son):
            # Aradaki sira_no'lari BEKLEYEN'e al; onay suresi dolarsa kayip.
            atlanan = (sira - son - 1) & 0xFF
            if 0 < atlanan <= self.makul_kayip:
                for k in range(1, atlanan + 1):
                    bekleyen[(son + k) & 0xFF] = now
            elif atlanan > self.makul_kayip:
                # Kayip mi sicrama mi bilinmiyor -> KAYIP SAYMIYORUZ ama
                # sessiz de gecmiyoruz (bkz. makul_kayip notu).
                self._sicrama[drone_id] = self._sicrama.get(drone_id, 0) + 1

        if son is None or self._ileri_mi(sira, son):
            self._son[drone_id] = sira
        return True

    def kayiplar(self, now: float) -> list[tuple[int, int]]:
        """Onay süresi dolmuş, gerçekten kaybolmuş olay sayıları.

        [(drone_id, adet), ...] — yalniz adedi olanlar doner.
        """
        cikti: list[tuple[int, int]] = []
        for drone_id, bekleyen in self._bekleyen.items():
            dolmus = [s for s, ts in bekleyen.items()
                      if (now - ts) >= self.bekleme_s]
            if not dolmus:
                continue
            for s in dolmus:
                del bekleyen[s]
            cikti.append((drone_id, len(dolmus)))
        return cikti

    def sicramalar(self) -> dict[int, int]:
        """Sayaç sıçraması görülen drone'lar ve kaç kez.

        Sicrama = "sira_no cok atladi; kayip mi yeniden baslatma mi
        BILINMIYOR". Kayipla ayni sepete koymuyoruz: yanlis sayilan bir
        kayip, defterin guvenilirligini bitirir.
        """
        return {k: v for k, v in self._sicrama.items() if v > 0}

    def sicrama_temizle(self, drone_id: int) -> None:
        self._sicrama.pop(drone_id, None)
