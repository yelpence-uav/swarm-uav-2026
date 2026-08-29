"""FlySky i-BUS (Servo) cerceve cozucusu — saf matematik, ROS yok.

NEDEN VAR (30 Agustos 2026, gorev2.md B1): Gorev 2'de suruyu suren kumanda
ylp00'a takilan IKINCI bir FS-iA6B alicisindan geliyor. O alici Pixhawk'a
BAGLANAMAZ — PX4'te tek RC girisi var ve orasi kill-switch pilotunun
alicisina ait (CH5 kill, CH8 arm, CH3 failsafe 2100). Bu yuzden ikinci
alici Pi'ye baglaniyor ve cercevesini bu modul cozuyor.

NEDEN i-BUS, PPM DEGIL: i-BUS duz bir UART akisi (115200 8N1, ters
cevrilmemis) ve CHECKSUM TASIYOR. PPM'de darbe zamanlamasi Linux
zamanlayicisina kalirdi ve bozuk bir darbe SESSIZCE yanlis kanal degeri
uretirdi — o kanal emniyet anahtari olabilir.

CERCEVE (32 bayt, ~7,7 ms arayla, yani ~130 Hz):

    [0]      0x20   uzunluk (32)
    [1]      0x40   komut (servo verisi)
    [2..29]  14 kanal, her biri 2 bayt LITTLE-ENDIAN, tipik 1000..2000
    [30..31] checksum, little-endian = 0xFFFF - (ilk 30 baytin toplami)

⚠️ 7-14. kanallarin bit yerlesimi bazi FlySky alicilarinda "genisletilmis"
olabiliyor. Burada DUZ 16-bit varsayiliyor — FS-iA6B + FS-i6X icin
beklenen bu. Varsayim G0'da (gorev2.md madde 17) her anahtar tek tek
oynatilarak DOGRULANACAK; `kanallar_makul` bu yuzden var.
"""

IBUS_UZUNLUK = 32
IBUS_BAS0 = 0x20
IBUS_BAS1 = 0x40
IBUS_KANAL_SAYISI = 14

# Saglikli bir RC kanalinin PWM araligi. Disina cikan deger "kumanda
# 10 kanal kipinde degil" ya da "bit yerlesimi farkli" demektir.
KANAL_ALT = 900
KANAL_UST = 2100

# Tamponun sisme sigortasi: iki cerceve boyu yeter, fazlasi resync
# kaybi demektir.
_TAMPON_TAVANI = IBUS_UZUNLUK * 4


def checksum_hesapla(cerceve: bytes) -> int:
    """Cercevenin ilk 30 baytindan beklenen checksum'i uretir."""
    return (0xFFFF - sum(cerceve[:IBUS_UZUNLUK - 2])) & 0xFFFF


def checksum_dogru(cerceve: bytes) -> bool:
    """Cercevenin checksum'i tutuyor mu."""
    if len(cerceve) != IBUS_UZUNLUK:
        return False
    tasinan = int.from_bytes(cerceve[IBUS_UZUNLUK - 2:], 'little')
    return tasinan == checksum_hesapla(cerceve)


def kanallari_coz(cerceve: bytes) -> list[int]:
    """32 baytlik gecerli cerceveden 14 kanali cikarir (PWM, us)."""
    return [
        int.from_bytes(cerceve[2 + 2 * i:4 + 2 * i], 'little')
        for i in range(IBUS_KANAL_SAYISI)
    ]


def kanallar_makul(kanallar: list[int], sayi: int = 8) -> bool:
    """Ilk `sayi` kanal saglikli PWM araliginda mi.

    Gorev 2 sekiz kanal kullaniyor (4 cubuk + SwA/SwB/SwC/SwD). FS-i6X
    VARSAYILANI ALTI kanal; 10 kanal kipine alinmazsa 7. ve 8. kanallar
    (SwC formasyon, SwD kalkis/inis) bos/copluk gelir. Bu SESSIZ bir
    ariza olurdu — kumandadaki iki anahtar hicbir sey yapmazdi.
    """
    if len(kanallar) < sayi:
        return False
    return all(KANAL_ALT <= k <= KANAL_UST for k in kanallar[:sayi])


class IbusAyiklayici:
    """Bayt akisindan i-BUS cercevesi ayiklar.

    i-BUS'ta AYIRICI BAYT YOK (esp32_bridge'in COBS 0x00'i gibi bir sey
    yok), o yuzden senkron basligi + checksum ile bulunur: bas 0x20 0x40
    ve checksum tutuyorsa cerceve gercektir. Tutmuyorsa TEK BAYT atilir
    ve yeniden aranir — sahte hizalanma boyle cozulur.
    """

    def __init__(self) -> None:
        self._tampon = bytearray()
        self.gecerli = 0        # checksum'i tutan cerceve sayisi
        self.checksum_hata = 0  # basligi tutup checksum'i tutmayan
        self.atilan_bayt = 0    # resync sirasinda dusen bayt

    def besle(self, veri: bytes) -> list[list[int]]:
        """Yeni baytlari isler, tamamlanan cercevelerin kanallarini doner."""
        self._tampon.extend(veri)

        # Sisme sigortasi: hicbir cerceve bulunamiyorsa tampon sonsuz
        # buyumesin (kopuk kablo / yanlis baud).
        if len(self._tampon) > _TAMPON_TAVANI:
            fazla = len(self._tampon) - _TAMPON_TAVANI
            del self._tampon[:fazla]
            self.atilan_bayt += fazla

        cikti: list[list[int]] = []
        while len(self._tampon) >= IBUS_UZUNLUK:
            if self._tampon[0] != IBUS_BAS0 or self._tampon[1] != IBUS_BAS1:
                del self._tampon[0]
                self.atilan_bayt += 1
                continue

            cerceve = bytes(self._tampon[:IBUS_UZUNLUK])
            if not checksum_dogru(cerceve):
                # Basligi tutuyor ama checksum tutmuyor: ya bozuk cerceve
                # ya da veri icinde rastlanan sahte baslik. Tek bayt at.
                del self._tampon[0]
                self.checksum_hata += 1
                self.atilan_bayt += 1
                continue

            del self._tampon[:IBUS_UZUNLUK]
            self.gecerli += 1
            cikti.append(kanallari_coz(cerceve))

        return cikti


def cerceve_kur(kanallar: list[int]) -> bytes:
    """Verilen kanallardan gecerli bir i-BUS cercevesi uretir (TEST icin).

    Uretim yolunda kullanilmiyor; birim testlerin gercek cerceve
    kurabilmesi icin var — cozucuyu kendi urettigi veriyle sinamak
    yerine bagimsiz bir kurucuyla sinamak daha az yaniltir.
    """
    govde = bytearray([IBUS_BAS0, IBUS_BAS1])
    dolu = list(kanallar) + [0] * (IBUS_KANAL_SAYISI - len(kanallar))
    for k in dolu[:IBUS_KANAL_SAYISI]:
        govde.extend(int(k).to_bytes(2, 'little'))
    govde.extend(checksum_hesapla(bytes(govde)).to_bytes(2, 'little'))
    return bytes(govde)
