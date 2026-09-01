# Copyright 2026 Yelpence
"""TEK ATISLIK bayraklari mesh'te yasatan kisa seri. Saf mantik, ROS yok.

NEDEN AYRI MODUL: kardesleri rc_eksen.py · swd_mandal.py · swc_debounce.py ·
canli_param.py ile ayni gerekce — dugum rclpy olmadan import edilemiyor,
bu mantik ise birim testle KILITLENMEK ZORUNDA.

═══════════════════════════════════════════════════════════════════
🔴 NEDEN VAR — 31 Agustos 2026, SAHADA UCUSLA ODENDI

Ilk pervaneli kalkis denemesinde YALNIZ PILOT UCAGI (ylp00) kalkti;
ylp01 ve ylp02 armlanmadi bile. Loglarda o ikisinde "YETKI YOK" hatasi
BILE YOKTU — yani kalkis istegi onlara HIC ULASMADI.

OLCULEN SEBEP:
    ylp00 komutu yayinliyor        : ~46 Hz
    ylp01'e mesh'ten varan         :  12,6 Hz     -> ~4'te 1 gecıyor
    kalkis bayragi                 : TEK CERCEVE  -> ~%75 dusme olasiligi

`_timer_callback` de tekrarlamiyordu: mode/eksenler/deadman kopyalaniyor
ama takeoff ve formation_change KOPYALANMIYOR.

Sonuclari zincirleme buyudu: iki ucak armlanmayinca B15 kalkis kapisi
(TUM ucaklar armli sarti) HIC ACILMADI, mode_manager tek bir setpoint
bile yayinlamadi ve ylp00'i 21 saniye boyunca yalniz px4_bridge'in
kalkis capasi ucurdu.

⚠️ AYNI KUSUR FORMASYON DEGISIMINDE DE VARDI ve yarisma-kritik: hakem
"cizgiye gec" der, talep ~%75 ihtimalle komsulara ULASMAZ.

═══════════════════════════════════════════════════════════════════
NEDEN MANDAL DEGIL SERI

Mandal (surekli true) yanlis olurdu — swd_mandal.py'nin dedigi gibi
"salter yukarida kaldigi surece surekli kalkis istegi uretilirdi".
Suru inip PREFLIGHT'a dondugunde salter hala yukaridaysa KENDILIGINDEN
tekrar kalkardi.

Seri ise SINIRLI: kenardan sonra N ms boyunca true, sonra kendiliginden
duser. Alici tarafta anlam degismiyor — mode_manager zaten TAKEOFF'a
gecince istegi temizliyor ve PREFLIGHT disinda yok sayiyor.

SURE = 600 ms. 46 Hz'de ~28 cerceve; 4'te 1 gecen bir kanalda ~7 kopya.
Hepsinin birden dusme olasiligi ihmal edilebilir.
═══════════════════════════════════════════════════════════════════
"""

# 600 ms: yukaridaki hesap. Kisaltilirsa mesh kaybina karsi pay azalir.
VARSAYILAN_SURE_MS = 600.0


class TekAtisSeri:
    """Bir kenari kisa sureli seriye cevirir; sonra kendiliginden duser."""

    def __init__(self, sure_ms: float = VARSAYILAN_SURE_MS) -> None:
        self.sure_s = max(0.0, float(sure_ms)) / 1000.0
        self._bitis = None

    def tetikle(self, simdi: float) -> None:
        """Kenar gorulunce cagrilir; seriyi baslatir/uzatir."""
        self._bitis = simdi + self.sure_s

    def aktif(self, simdi: float) -> bool:
        """Seri hala suruyor mu."""
        if self._bitis is None:
            return False
        if simdi >= self._bitis:
            self._bitis = None
            return False
        return True

    def sifirla(self) -> None:
        """Seriyi hemen keser (or. emniyet kapandi)."""
        self._bitis = None
