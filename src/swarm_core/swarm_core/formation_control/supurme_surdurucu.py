# Copyright 2026 Yelpence
"""QR SUPURMESINDE takipcinin dikey rampayi MESH BOSLUGUNDA surdurmesi.

🔴 8 EYLUL 2026, SAHADA GORULDU — operator: "lider olmayan diger dronelar
inis sirasinda bas cek yapiyorlar."

NEDEN OLUYOR
    Supurme hedefini LIDER uretiyor ve mesh'ten yayinliyor (5 Hz). Kanat
    ucaklar o hedefi takip ediyor. Paket dusunce kanat SON hedefte DONUYOR;
    sonraki paket gelince yeni hedefe ATILIYOR. Gozle "bas-cek" budur.
    Ayni kusuru 8 Eylul'de formasyon ofsetlerinde yasadik ve cozumu ayni
    ilkeydi: DEGERI her tik gondermek yerine KURALI bir kez gondermek.

BU MODULUN YAPTIGI
    Supurme dogrusal bir rampa (sabit dikey hiz). Iki ardisik hedeften
    hizi cikarip, paket YOKKEN rampayi YEREL olarak surduruyoruz. Her yeni
    paket geldiginde deger MESH'E GERI SENKRONLANIR — yani mesh hala
    dogruluk kaynagi, biz yalnizca aradaki bosluğu dolduruyoruz.
    (Operator: "meshten arada bir kontrol etsinler.")

🔴 SAPMA OLUNCA HIZLI OLAN BEKLER, YAVAS OLAN HIZLANMAZ
    Operator ikisini de onerdi; olcum birincisini secdiriyor. 8 Eylul:
    tirmanmak asili durmanin USTUNDE itki ister ve pay dar — ylp00 bos
    pille gazi 1.000'e dayamis, komut edilen irtifaya cikamamisti. Geri
    kalan ucak zaten YETISEMEDIGI icin geridedir; ona "hizlan" demek
    calismayabilir. Beklemek ise sinirli ve guvenli. Bu yuzden
    ekstrapolasyon SAPMA_TAVANI'nda DURUR (bekler), hizlanma YOK.

NE YAPMAZ
    * Yeni mesh cercevesi/protokol YOK — mevcut hedef akisindan turuyor.
    * Ikinci bir uretici YOK (CLAUDE.md §4) — ayni boru hattinda, ayni
      hedefin yalniz Z bileseni bosluk boyunca surduruluyor.
    * Yatay eksene HIC dokunmaz.
"""

# Ekstrapolasyonun son mesh degerinden ne kadar uzaklasabilecegi.
# 1.5 m/s supurme hizinda 1.0 m ~ 0.67 saniyelik bosluk demek: tipik mesh
# boslugunu (olculen medyan 622 ms) tam kapatir, uzun kesintide ise ucak
# BEKLER — sicramanin yerini gecikme alir, ki dikeyde gecikme guvenlidir.
SAPMA_TAVANI_M = 1.0

# Rampa hizi bu bandin disindaysa "supurme degil" sayilir ve surdurme
# KAPALI kalir. Ust sinir supurme hizindan (1.5 m/s) bir miktar yuksek.
_MIN_HIZ_MPS = 0.15
_MAKS_HIZ_MPS = 3.0

# Iki hedef arasinda bundan uzun sure varsa hiz tahmini guvenilmez sayilir.
_MAKS_ORNEK_ARALIGI_S = 3.0

# Yatay merkez bu kadardan fazla oynadiysa supurme degil SEYIR var demektir;
# seyirde dikey ekstrapolasyon yapmak hedefi kaydirir.
_YATAY_DURGUNLUK_M = 1.5


class SupurmeSurdurucu:
    """Mesh boslugunda supurme rampasini surdurur; pakette senkronlanir."""

    def __init__(self, sapma_tavani_m: float = SAPMA_TAVANI_M) -> None:
        self.sapma_tavani_m = float(sapma_tavani_m)
        self._onceki = None          # (t, z, x, y)
        self._son = None             # (t, z, x, y)
        self._hiz = 0.0              # m/s, +z asagi (NED)
        self.aktif = False
        self.surdurulen_sayisi = 0
        self.tavana_dayanma_sayisi = 0

    # ------------------------------------------------------------- girdi

    def hedef_geldi(self, t: float, z: float, x: float = 0.0,
                    y: float = 0.0) -> None:
        """Mesh'ten formasyon hedefi geldi — DOGRULUK KAYNAGI budur."""
        self._onceki = self._son
        self._son = (float(t), float(z), float(x), float(y))
        self._hiz = 0.0
        self.aktif = False
        if self._onceki is None:
            return
        dt = self._son[0] - self._onceki[0]
        if not (0.0 < dt <= _MAKS_ORNEK_ARALIGI_S):
            return
        yatay = abs(self._son[2] - self._onceki[2]) + \
            abs(self._son[3] - self._onceki[3])
        if yatay > _YATAY_DURGUNLUK_M:
            return                       # seyir var, supurme degil
        hiz = (self._son[1] - self._onceki[1]) / dt
        if _MIN_HIZ_MPS <= abs(hiz) <= _MAKS_HIZ_MPS:
            self._hiz = hiz
            self.aktif = True

    # ------------------------------------------------------------- cikti

    def z(self, simdi: float) -> float | None:
        """Bu anda komut edilecek Z. Hedef hic gelmediyse None."""
        if self._son is None:
            return None
        t0, z0 = self._son[0], self._son[1]
        if not self.aktif:
            return z0                    # surdurme kapali: son deger
        gecen = simdi - t0
        if gecen <= 0.0:
            return z0
        sapma = self._hiz * gecen
        tavan = self.sapma_tavani_m
        if abs(sapma) > tavan:
            # 🔴 BEKLE — hizlanma yok, tavanda durulur (bkz. modul notu).
            self.tavana_dayanma_sayisi += 1
            sapma = tavan if sapma > 0 else -tavan
        else:
            self.surdurulen_sayisi += 1
        return z0 + sapma

    def sifirla(self) -> None:
        """Supurme bitti — surdurme kapanir, son degere donulur."""
        self._onceki = None
        self._son = None
        self._hiz = 0.0
        self.aktif = False
