# Copyright 2026 Yelpence
"""VrB formasyon kilidi — 31 Agustos 2026 saha olayini kilitleyen testler.

OLAY: uc ucakli kalkista kimse SwC'ye dokunmadan formasyon degisimi
mesh'e cikti. Sebep: SwC'nin KAPALI konumu yok, uc konumu da bir
formasyon; salterin durdugu yer talep olarak okunuyor.

Gerekce ve saha olcumu (VrB -> ch10 -> aux6): formasyon_kilidi.py basligi.
"""

import unittest

from swarm_state_machine.mode_manager import formasyon_kilidi as FK


class TestEsik(unittest.TestCase):
    """Esik aux 800 (~PWM 1900) — olculen tepe 2000."""

    def test_varsayilan_esik_800(self):
        self.assertEqual(FK.VARSAYILAN_ESIK, 800.0)

    def test_tam_cevrili_ACIK(self):
        k = FK.FormasyonKilidi()
        self.assertEqual(k.degerlendir(1000), FK.YENI_ACILDI)
        self.assertEqual(k.degerlendir(1000), FK.ACIK)

    def test_yarim_cevrili_KAPALI(self):
        """Ortada birakilan VrB kilidi ACMAZ."""
        k = FK.FormasyonKilidi()
        for v in (-1000, -300, 0, 300, 700, 800):
            self.assertEqual(k.degerlendir(v), FK.KAPALI,
                             f'aux={v} kilidi acmamali')


class TestGecisMantigi(unittest.TestCase):
    """🔴 Kilit SEVIYEYE degil GECISE bagli — VrB acik UNUTULABILIR."""

    def test_acilista_VrB_acikSA_once_YENI_ACILDI(self):
        """Olcume basladigimda ch10 ZATEN 2000'di: bu hal gercek.

        Acilis ACIK'tan ayri bir durum olmak zorunda: SwC duran bir
        salter ve SwcDebounce duran salter icin hicbir zaman
        tetiklemez. Ayrilmasaydi kilit acildiginda formasyon HIC
        olusmazdi.
        """
        k = FK.FormasyonKilidi()
        self.assertEqual(k.degerlendir(1000), FK.YENI_ACILDI,
                         'ilk cerceve ACILIS olarak bildirilmeli')

    def test_YENI_ACILDI_yalniz_BIR_cerceve(self):
        k = FK.FormasyonKilidi()
        k.degerlendir(1000)
        for _ in range(20):
            self.assertEqual(k.degerlendir(1000), FK.ACIK)

    def test_kapanip_acilinca_YENIDEN_taban(self):
        k = FK.FormasyonKilidi()
        k.degerlendir(1000)
        self.assertEqual(k.degerlendir(1000), FK.ACIK)
        self.assertEqual(k.degerlendir(0), FK.KAPALI)
        self.assertEqual(k.degerlendir(1000), FK.YENI_ACILDI,
                         'kilit her acilista tabani yeniden benimsemeli')

    def test_sifirla_tabani_yeniden_kurar(self):
        """Emniyet (SwA) kapaninca cagrilir."""
        k = FK.FormasyonKilidi()
        k.degerlendir(1000)
        self.assertEqual(k.degerlendir(1000), FK.ACIK)
        k.sifirla()
        self.assertEqual(k.degerlendir(1000), FK.YENI_ACILDI,
                         'sifirla sonrasi VrB acik olsa da taban benimsenmeli')


class TestOlayinKendisi(unittest.TestCase):
    """31 Agustos senaryosunun birebir yeniden oynatilmasi."""

    def test_kumanda_acildi_VrB_kapali_SwC_cizgide(self):
        """Kilit kapaliyken hicbir cerceve degisim URETMEZ."""
        k = FK.FormasyonKilidi()
        uretilen = [d for d in (k.degerlendir(-1000) for _ in range(200))
                    if d is FK.ACIK]
        self.assertEqual(uretilen, [],
                         'VrB kapaliyken SwC hicbir zaman canli olmamali')

    def test_pilot_VrB_yi_cevirdi_ilk_cerceve_ACILIS(self):
        k = FK.FormasyonKilidi()
        for _ in range(50):
            self.assertEqual(k.degerlendir(-1000), FK.KAPALI)
        self.assertEqual(k.degerlendir(1000), FK.YENI_ACILDI)
        self.assertEqual(k.degerlendir(1000), FK.ACIK)


class TestTalepHesapla(unittest.TestCase):
    """🔴 VrB ANA ANAHTAR — 31 Agustos operator karari.

    Sozlesme (operatorun kendi ifadesiyle):
      * VrB KAPALI iken hicbir formasyon aktif OLMAZ.
      * Ilk kalkista VrB kapaliysa ACILANA KADAR formasyon olusmaz.
      * VrB ACILINCA SwC'nin gosterdigi formasyon aktif olur.
      * Havada formasyon aktifken VrB kapatilirsa ucaklar OLDUGU YERDE
        kalir, formasyon aktif degildir.
    """

    def test_KAPALI_formasyonu_KALDIRIR(self):
        """Havada cizgi formasyonundayken VrB kapatildi."""
        talep, degisim = FK.talep_hesapla(FK.KAPALI, 3, onceki_talep=3)
        self.assertEqual(talep, FK.FORMASYON_YOK)
        self.assertTrue(degisim, 'formasyonun kalktigi DUYURULMALI')

    def test_KAPALI_zaten_formasyonsuzsa_bayrak_YAKMAZ(self):
        """46 Hz'de surekli 'degisti' demek mesh'i bosa doldurur."""
        talep, degisim = FK.talep_hesapla(FK.KAPALI, 3, onceki_talep=0)
        self.assertEqual(talep, FK.FORMASYON_YOK)
        self.assertFalse(degisim)

    def test_KAPALI_SwC_ne_olursa_olsun_FORMASYON_YOK(self):
        for bolge in (1, 2, 3):
            talep, _ = FK.talep_hesapla(FK.KAPALI, bolge, onceki_talep=bolge)
            self.assertEqual(talep, FK.FORMASYON_YOK,
                             f'SwC={bolge} iken bile formasyon olmamali')

    def test_YENI_ACILDI_SwC_nin_gosterdigini_AKTIF_eder(self):
        for bolge in (1, 2, 3):
            talep, degisim = FK.talep_hesapla(
                FK.YENI_ACILDI, bolge, onceki_talep=0)
            self.assertEqual(talep, bolge)
            self.assertTrue(degisim)

    def test_ACIK_karari_DEBOUNCE_a_birakir(self):
        talep, degisim = FK.talep_hesapla(FK.ACIK, 2, onceki_talep=2)
        self.assertEqual(talep, FK.DEBOUNCE)
        self.assertFalse(degisim)


class TestUctanUcaSenaryo(unittest.TestCase):
    """Operatorun tarif ettigi ucusun birebir yeniden oynatilmasi."""

    def test_kalkis_VrB_kapali_sonra_acildi_sonra_kapatildi(self):
        k = FK.FormasyonKilidi()
        talep = 0

        # 1) Suru kalkiyor, VrB kapali, SwC cizgide duruyor.
        for _ in range(100):
            durum = k.degerlendir(-1000)
            yeni, _dg = FK.talep_hesapla(durum, 3, talep)
            talep = yeni
        self.assertEqual(talep, FK.FORMASYON_YOK,
                         'VrB kapaliyken formasyon OLUSMAMALI')

        # 2) Pilot VrB'yi tam cevirdi -> SwC'nin gosterdigi aktif olur.
        durum = k.degerlendir(1000)
        self.assertEqual(durum, FK.YENI_ACILDI)
        talep, degisim = FK.talep_hesapla(durum, 3, talep)
        self.assertEqual(talep, 3, 'acilinca cizgi formasyonu aktif olmali')
        self.assertTrue(degisim)

        # 3) Formasyon aktif, VrB acik kaliyor -> karar debounce'da.
        for _ in range(50):
            durum = k.degerlendir(1000)
            self.assertEqual(durum, FK.ACIK)
            yeni, _dg = FK.talep_hesapla(durum, 3, talep)
            self.assertEqual(yeni, FK.DEBOUNCE)

        # 4) Havada VrB kapatildi -> formasyon kalkar, yer tutulur.
        durum = k.degerlendir(-1000)
        self.assertEqual(durum, FK.KAPALI)
        talep, degisim = FK.talep_hesapla(durum, 3, talep)
        self.assertEqual(talep, FK.FORMASYON_YOK)
        self.assertTrue(degisim, 'formasyonun kalktigi mesh e DUYURULMALI')


if __name__ == '__main__':
    unittest.main()
