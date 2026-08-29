# Copyright 2026 Yelpence
"""FlySky i-BUS cerceve cozucusu birim testleri (gorev2.md B1)."""

import unittest

from swarm_control.rc_ibus.ibus_cozucu import (
    IBUS_KANAL_SAYISI,
    IBUS_UZUNLUK,
    IbusAyiklayici,
    cerceve_kur,
    checksum_dogru,
    kanallari_coz,
    kanallar_makul,
)

# Gorev 2 kanal duzeni (joystick_interpreter._on_mavros_rc_in ile ayni):
# CH1 roll, CH2 pitch, CH3 throttle, CH4 yaw,
# CH5 SwA emniyet, CH6 SwB mod, CH7 SwC formasyon, CH8 SwD kalkis/inis
_ORNEK = [1500, 1500, 1000, 1500, 1000, 1000, 1500, 1000] + [1500] * 6


class TestCerceve(unittest.TestCase):
    """Tek cerceve: kurulum, checksum, cozum."""

    def test_kurulan_cerceve_32_bayt(self):
        self.assertEqual(len(cerceve_kur(_ORNEK)), IBUS_UZUNLUK)

    def test_kurulan_cercevenin_checksumi_tutar(self):
        self.assertTrue(checksum_dogru(cerceve_kur(_ORNEK)))

    def test_gidis_donus(self):
        """Kur -> coz, degerler birebir geri gelmeli."""
        self.assertEqual(kanallari_coz(cerceve_kur(_ORNEK)), _ORNEK)

    def test_bozuk_checksum_reddedilir(self):
        c = bytearray(cerceve_kur(_ORNEK))
        c[5] ^= 0xFF                      # bir kanal baytini boz
        self.assertFalse(checksum_dogru(bytes(c)))

    def test_eksik_cerceve_reddedilir(self):
        self.assertFalse(checksum_dogru(cerceve_kur(_ORNEK)[:-1]))

    def test_eksik_kanal_sifirla_doldurulur(self):
        kanallar = kanallari_coz(cerceve_kur([1500, 1600]))
        self.assertEqual(len(kanallar), IBUS_KANAL_SAYISI)
        self.assertEqual(kanallar[:2], [1500, 1600])
        self.assertTrue(all(k == 0 for k in kanallar[2:]))


class TestMakullukKapisi(unittest.TestCase):
    """FS-i6X 6 kanal kipinde kalirsa SwC/SwD sessizce olur."""

    def test_sekiz_kanal_saglikliysa_gecer(self):
        self.assertTrue(kanallar_makul(_ORNEK))

    def test_alti_kanal_kipi_YAKALANIR(self):
        """CH7/CH8 bos gelirse (0) makul DEGIL — sessiz ariza kapisi."""
        alti = [1500, 1500, 1000, 1500, 1000, 1000, 0, 0] + [0] * 6
        self.assertFalse(kanallar_makul(alti))

    def test_aralik_disi_yakalanir(self):
        bozuk = list(_ORNEK)
        bozuk[6] = 16416          # 0x4020 — bit yerlesimi farkli olsaydi
        self.assertFalse(kanallar_makul(bozuk))

    def test_kisa_liste_makul_degil(self):
        self.assertFalse(kanallar_makul([1500] * 4))


class TestAyiklayici(unittest.TestCase):
    """Bayt akisindan cerceve ayiklama ve resync."""

    def test_temiz_akis_uc_cerceve(self):
        a = IbusAyiklayici()
        akis = cerceve_kur(_ORNEK) * 3
        cikti = a.besle(akis)
        self.assertEqual(len(cikti), 3)
        self.assertEqual(cikti[0], _ORNEK)
        self.assertEqual(a.gecerli, 3)
        self.assertEqual(a.atilan_bayt, 0)

    def test_parcali_okuma_birlestirilir(self):
        """Seri port cerceveyi ortadan bolerse kaybolmamali."""
        a = IbusAyiklayici()
        c = cerceve_kur(_ORNEK)
        self.assertEqual(a.besle(c[:7]), [])
        self.assertEqual(a.besle(c[7:20]), [])
        cikti = a.besle(c[20:])
        self.assertEqual(cikti, [_ORNEK])

    def test_bastaki_coplukten_RESYNC(self):
        """Ortadan baglanmis bir akis ilk tam cerceveyi bulmali."""
        a = IbusAyiklayici()
        cikti = a.besle(b'\xAA\xBB\xCC\x01\x02' + cerceve_kur(_ORNEK))
        self.assertEqual(cikti, [_ORNEK])
        self.assertEqual(a.atilan_bayt, 5)

    def test_SAHTE_BASLIK_atlatilir(self):
        """Copluk 0x20 0x40 ile baslarsa checksum onu eler."""
        a = IbusAyiklayici()
        sahte = b'\x20\x40' + b'\x00' * 10        # baslik tutar, checksum tutmaz
        cikti = a.besle(sahte + cerceve_kur(_ORNEK))
        self.assertEqual(cikti, [_ORNEK])
        self.assertGreaterEqual(a.checksum_hata, 1)
        self.assertEqual(a.gecerli, 1)

    def test_bozuk_cerceve_sayilir_ve_sonraki_bulunur(self):
        a = IbusAyiklayici()
        bozuk = bytearray(cerceve_kur(_ORNEK))
        bozuk[10] ^= 0xFF
        cikti = a.besle(bytes(bozuk) + cerceve_kur(_ORNEK))
        self.assertEqual(cikti, [_ORNEK])
        self.assertGreaterEqual(a.checksum_hata, 1)

    def test_tampon_SINIRSIZ_buyumez(self):
        """Kopuk kablo / yanlis baud: tampon sismemeli."""
        a = IbusAyiklayici()
        for _ in range(50):
            a.besle(b'\xAA' * 64)
        self.assertLessEqual(len(a._tampon), IBUS_UZUNLUK * 4)
        self.assertEqual(a.gecerli, 0)

    def test_copluk_arasinda_cerceve_bulunur(self):
        a = IbusAyiklayici()
        akis = (b'\x11\x22' + cerceve_kur(_ORNEK)
                + b'\x33' + cerceve_kur([1200] * 14))
        cikti = a.besle(akis)
        self.assertEqual(len(cikti), 2)
        self.assertEqual(cikti[0], _ORNEK)
        self.assertEqual(cikti[1], [1200] * 14)


if __name__ == '__main__':
    unittest.main()
