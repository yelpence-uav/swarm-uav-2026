"""SwD (kalkis/inis salteri) kenar ve mandal mantigi.

NEDEN AYRI DOSYA: joystick_interpreter_node rclpy olmadan import
edilemiyor, bu mantik ise birim testle KILITLENMEK ZORUNDA. 30 Agustos
2026 saha olayinda pilot kumandanin hicbir tusuyla inis veremedi; iptal
yolunun her kosulda calistigini kanitlayacak yer burasi. Ayni gerekceyle
ayrilmis kardesleri: rc_eksen.py (eksen isaretleri), ibus_cozucu.py.

TASARIM (gorev2.md G2-K7):

* KALKIS TEK ATIS. Mandal olsaydi salter yukarida kaldigi surece surekli
  kalkis istegi uretilirdi.
* INIS MANDAL, tek tick'lik kenar DEGIL. Kenar bayragi mesh'in 200 ms'lik
  joystick kapisina (JOYSTICK_MIN_ARALIK_MS) ya da tek bir paket kaybina
  takilirsa iptal TAMAMEN kaybolur ve tekrari yoktur. Mandal SwD yukari
  alinana kadar basili kalir: asagi akista seviye tetikli gorunur,
  salterin kendisinde hala kenar tetiklidir.
* INIS EMNIYET (SwA) KAPALIYKEN DE URETILIR. Tasarim iptali iki kademeli
  tanimliyor — "SwA kapat -> HOLD" ve "SwD -> inis" — ve bu ikisi bagimsiz
  olmak zorunda. KALKIS ise emniyet kapaliyken sayilmaz.
* ILK CERCEVE KENAR SAYILMAZ. Aksi halde kumanda SwD YUKARIDA ve SwA ACIK
  ikenki bir `docker restart`, tohum degerinden ilk olculen degere gecisi
  SAHTE KALKIS kenari olarak okurdu.
"""

# Varsayilan esikler — joystick_interpreter_node kendi sabitlerini gecirir,
# burasi yalniz tek basina kullanim icin makul deger tutar.
TAKEOFF_ESIK = 300
LAND_ESIK = -300


class SwdMandal:
    """SwD kenarlarini isler; kalkis tek atis, inis mandal."""

    def __init__(
        self,
        takeoff_esik: int = TAKEOFF_ESIK,
        land_esik: int = LAND_ESIK,
    ) -> None:
        self.takeoff_esik = takeoff_esik
        self.land_esik = land_esik
        # None = henuz cerceve gorulmedi; ilk cerceve yalniz tohumlar.
        self.son_deger: int | None = None
        self.inis_mandali = False
        self.kalkis_kenari = False

    def guncelle(self, deger: int, emniyet_acik: bool) -> None:
        """Yeni SwD degerini isler."""
        if self.son_deger is None:
            self.son_deger = deger
            return
        if deger > self.takeoff_esik and self.son_deger <= self.takeoff_esik:
            if emniyet_acik:
                self.kalkis_kenari = True
            # Salter yukari alindi: artik inis istenmiyor. Bu, emniyet
            # kapaliyken de gecerli — mandali dusuren tek sey budur.
            self.inis_mandali = False
        elif deger < self.land_esik and self.son_deger >= self.land_esik:
            self.inis_mandali = True
        self.son_deger = deger

    def kalkisi_tuket(self) -> bool:
        """Bekleyen kalkis kenarini dondurur ve TEMIZLER (tek atis)."""
        kenar = self.kalkis_kenari
        self.kalkis_kenari = False
        return kenar
