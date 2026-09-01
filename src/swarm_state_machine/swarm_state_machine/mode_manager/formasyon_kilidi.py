# Copyright 2026 Yelpence
"""VrB formasyon ANA ANAHTARI. Saf mantik, ROS yok.

NEDEN AYRI MODUL: kardesleri rc_eksen.py · swd_mandal.py · swc_debounce.py ·
tek_atis_seri.py ile ayni gerekce — joystick_interpreter_node rclpy olmadan
import edilemiyor, bu mantik ise birim testle KILITLENMEK ZORUNDA.

═══════════════════════════════════════════════════════════════════
NEDEN VAR (31 Agustos 2026, UC UCAKLI KALKIS)

SwC'nin KAPALI konumu YOK: uc konumu da bir formasyon (okbasi / V /
cizgi). Yani kumanda acilir acilmaz salterin durdugu yer bir formasyon
TALEBI olarak okunuyor.

Ucusta olculdu: kimse SwC'ye dokunmadan
    requested_formation               0 -> 3 (cizgi)
    formation_change_requested        True
mesh'e cikti. Suru daha havalanirken formasyon degistirme emri aldi.

Operator karari: bos duran VrB potansiyometresi anahtar olsun.

═══════════════════════════════════════════════════════════════════
🔴 DEGISIM KILIDI DEGIL, ANA ANAHTAR

Ilk surum yalnizca DEGISIMI engelliyordu: VrB kapaliyken SwC izleniyor
ama talep uretilmiyordu. Operator bunu YETERSIZ buldu ve tanimi
genisletti (kendi ifadesiyle):

    * VrB KAPALI iken hicbir formasyon aktif OLMAZ.
    * Suru ilk kalktiginda VrB kapaliysa, ACILANA KADAR formasyon olusmaz.
    * VrB ACILINCA SwC'nin gosterdigi formasyon aktif olur.
    * Suru HAVADA ve formasyon aktifken VrB kapatilirsa ucaklar OLDUGU
      YERDE kalir, formasyon artik aktif degildir.

Fark onemli: eski davranista VrB'yi kapatmak SON formasyonu DONDURUP
aktif birakiyordu. Yenisinde kapatmak formasyonu KALDIRIYOR.

Son madde bedava gelmiyor ama zaten kuruluydu: FORMATION_UNKNOWN'a
donuldugunde mode_manager ofsetleri O ANKI konumlardan yeniden olcup
DONDURUYOR (mode_manager_node, FORMATION_UNKNOWN dali). Yani
"formasyon yok" = "bulundugun yeri tut", bir hareket komutu DEGIL.

═══════════════════════════════════════════════════════════════════
OLCUM — 31 Agustos 2026, ylp00 (kumanda_web.py /k ucu)

    VrB -> ch10 -> aux6,  tam aralik PWM 1000..2000, purussuz analog
    Ayni yakalamada diger 13 kanalin genligi 0 -> capraz karisma YOK.

Esik aux 800 (~PWM 1900). Tepe 2000 oldugu icin 100 us pay var;
supurmede 1912/1920/1950/1980 degerleri goruldugu icin 1900'e ulasmak
sorun degil. aux olcegi -1000..+1000 (PWM 1000..2000).

═══════════════════════════════════════════════════════════════════
🔴 GECIS NEDEN AYRI DURUM (YENI_ACILDI)

Kilit acildiginda formasyonun HEMEN aktif olmasi gerekiyor. Ama SwC o
sirada zaten bir konumda DURUYOR: SwcDebounce yalnizca bolge DEGISINCE
tetikler, duran salter icin hicbir zaman tetiklemez. Kilit kapaliyken
`esitle` cagrildigi icin `kararli` zaten o bolgeye esitlenmis olur ve
acilista `guncelle` sessiz kalirdi — formasyon HIC olusmazdi.

Bu yuzden acilis ayri bir durum olarak bildiriliyor ve talep DOGRUDAN
uretiliyor, debounce beklenmeden. Kararlilik sarti bir GECIS icin
anlamli, duran salter icin degil.

⚠️ Bunun bilinen bedeli: VrB TAM CEVRILI unutulursa, suru irtifaya
varip READY'ye gectigi anda SwC'nin gosterdigi formasyon olusur. Kilit
durumu kumanda_web senaryo panelinde ve mode_manager logunda gorunuyor;
kalkis oncesi bakilmasi gereken bir sey. (Operator 31 Agu'da bunu
bilerek kabul etti — "acilinca gecerli formasyon aktif olacak".)
═══════════════════════════════════════════════════════════════════
"""

# Cagiranin gordugu uc durum. Metin sabit: log'a da bu yaziliyor.
KAPALI = 'kapali'
YENI_ACILDI = 'yeni_acildi'
ACIK = 'acik'

# SwarmControlCommand.FORMATION_UNKNOWN karsiligi. Sabit BURAYA
# kopyalaniyor cunku modul ROS'suz kalmak zorunda; degeri (0)
# sozlesmenin parcasi ve test_formasyon_kilidi bunu kilitliyor.
FORMASYON_YOK = 0

# talep_hesapla'nin "karari SwcDebounce versin" cevabi.
DEBOUNCE = 'debounce'

# aux olcegi -1000..+1000. 800 ~ PWM 1900. Gerekce yukarida.
VARSAYILAN_ESIK = 800.0


def talep_hesapla(kilit: str, swc_bolge: int, onceki_talep: int):
    """Kilit durumundan formasyon TALEBINI ve degisim bayragini uretir.

    Davranis sozlesmesi dosya basliginda ("DEGISIM KILIDI DEGIL, ANA
    ANAHTAR").

    Args:
        kilit (str): KAPALI · YENI_ACILDI · ACIK.
        swc_bolge (int): SwC'nin o anki formasyon bolgesi.
        onceki_talep (int): en son yayinlanan requested_formation.

    Returns:
        tuple: (talep, degisim_bayragi). Talep DEBOUNCE ise cagiran
            karari SwcDebounce'a birakir (kilit ACIK ve gercek bir
            SwC hareketi beklenir).
    """
    if kilit == KAPALI:
        # Zaten formasyonsuzsak bayragi TEKRAR yakmayiz: komut ~46 Hz
        # yayinlaniyor, her cerceve "degisti" demek mesh'i bosa doldurur
        # ve alici tarafta her cerceve reshape tetiklerdi.
        return FORMASYON_YOK, onceki_talep != FORMASYON_YOK
    if kilit == YENI_ACILDI:
        # Debounce beklenmez — gerekcesi dosya basliginda.
        return swc_bolge, True
    return DEBOUNCE, False


class FormasyonKilidi:
    """VrB'nin kapali/yeni-acildi/acik durumunu uretir."""

    def __init__(self, esik: float = VARSAYILAN_ESIK) -> None:
        self.esik = float(esik)
        # False = kilit kapali kabul edilir. Acilista bilerek False:
        # ilk cerceve VrB acik gelse bile YENI_ACILDI dondurulur, yani
        # formasyon acilis olayi olarak uretilir (sessizce degil).
        self._acikti = False

    def degerlendir(self, aux_val: float) -> str:
        """Bir cerceve isler ve kilit durumunu dondurur.

        Args:
            aux_val (float): VrB kanalinin -1000..+1000 olcegindeki degeri.

        Returns:
            str: KAPALI · YENI_ACILDI · ACIK.
        """
        acik = float(aux_val) > self.esik
        onceki = self._acikti
        self._acikti = acik
        if not acik:
            return KAPALI
        return ACIK if onceki else YENI_ACILDI

    def sifirla(self) -> None:
        """Kilidi kapali kabul eder.

        Emniyet (SwA) kapaninca cagrilir: emniyet tekrar acildiginda VrB
        yukarida BIRAKILMIS olsa bile bir sonraki degerlendirme
        YENI_ACILDI doner, yani formasyon yeniden ACILIS olayi olarak
        uretilir. Aksi halde emniyet dongusu formasyonu sessizce
        canlandirirdi.
        """
        self._acikti = False
