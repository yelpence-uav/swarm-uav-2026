# Copyright 2026 Yelpence
"""Dort suru davranis ayarinin UCAK TARAFI dogrulamasi — 5 Eylul 2026.

Sinir denetimi TEK YERDE, ucakta (canli_param). Backend ve arayuz
bilerek tekrarlamiyor: iki kopya kacinilmaz olarak ayrisir ve o gun
"YKI kabul etti ama ucak reddetti" (ya da tersi) yasanir.

🔴 UST SINIRLAR KEYFI DEGIL:
    yaw tavani  <= PX4 MPC_YAWRAUTO_MAX (25 deg/s)
    egim tavani <= PX4 MPC_TILTMAX_AIR  (30 deg)
Ustune cikmak ucagin YAPAMAYACAGI bir komut uretmek demek — 14 Agustos'ta
MAKS_EGIM_DEG'in kodda 35 sabit olmasi tam bu siniftaydi.
"""

import unittest

from swarm_state_machine.mode_manager import canli_param


class TestKabul(unittest.TestCase):
    """Sahadaki gercek varsayilanlar kabul edilmeli."""

    def test_bugunku_degerler_kabul(self):
        sonuc = canli_param.g2_suru_ayari_dogrula(0.6, 2.0, 14.7, 15.0)
        self.assertEqual(sonuc, (0.6, 2.0, 14.7, 15.0))

    def test_SIFIR_belirtilmedi_demek(self):
        """Operatorun bos birakmasi GECERLI — alan varsayilanda kalir."""
        sonuc = canli_param.g2_suru_ayari_dogrula(0, 0, 0, 0)
        self.assertEqual(
            sonuc, (canli_param.BELIRTILMEDI,) * 4)

    def test_None_ve_bos_metin_de_belirtilmedi(self):
        sonuc = canli_param.g2_suru_ayari_dogrula(None, '', None, '')
        self.assertEqual(sonuc, (canli_param.BELIRTILMEDI,) * 4)

    def test_KISMI_giris(self):
        """Yalniz bir alan verilirse digerleri varsayilanda kalir."""
        sonuc = canli_param.g2_suru_ayari_dogrula(0, 3.0, 0, 0)
        self.assertEqual(sonuc[1], 3.0)
        self.assertEqual(sonuc[0], canli_param.BELIRTILMEDI)


class TestRed(unittest.TestCase):
    """Sinir disi deger SESSIZCE kirpilmaz, ParamRed atilir."""

    def test_yaw_PX4_TAVANINI_asarsa_red(self):
        with self.assertRaises(canli_param.ParamRed):
            canli_param.g2_suru_ayari_dogrula(0, 0, 30.0, 0)

    def test_egim_PX4_TAVANINI_asarsa_red(self):
        with self.assertRaises(canli_param.ParamRed):
            canli_param.g2_suru_ayari_dogrula(0, 0, 0, 45.0)

    def test_hareket_hizi_tavani(self):
        with self.assertRaises(canli_param.ParamRed):
            canli_param.g2_suru_ayari_dogrula(0, 9.0, 0, 0)

    def test_morf_hizi_alt_sinir(self):
        """Cok dusuk morf hizi = morf pratikte hic bitmez."""
        with self.assertRaises(canli_param.ParamRed):
            canli_param.g2_suru_ayari_dogrula(0.05, 0, 0, 0)

    def test_red_mesaji_OPERATORE_gosterilebilir(self):
        """Mesaj alan adini ve izinli araligi soylemeli."""
        with self.assertRaises(canli_param.ParamRed) as c:
            canli_param.g2_suru_ayari_dogrula(0, 0, 99.0, 0)
        metin = str(c.exception)
        self.assertIn('yaw', metin.lower())
        self.assertIn('25', metin)


class TestCanliParamListesi(unittest.TestCase):
    """mode_manager geri cagrisi bu adlari kabul etmek zorunda.

    🔴 Liste eksik olsaydi `dogrula()` parametreyi REDDEDER ve ayar
    sessizce uygulanmazdi — mode_manager_node'un kendi docstring'inin
    anlattigi "SESSIZ NO-OP" tuzagi.
    """

    def test_dort_ad_da_izinli(self):
        for ad in ('morf_hiz_mps', 'max_speed_mps',
                   'max_yaw_rate_deg_s', 'max_tilt_deg'):
            with self.subTest(ad=ad):
                self.assertIn(ad, canli_param.MODE_MANAGER_CANLI)

    def test_eski_ikisi_KORUNDU(self):
        for ad in ('default_spacing_m', 'kalkis_irtifa_m'):
            with self.subTest(ad=ad):
                self.assertIn(ad, canli_param.MODE_MANAGER_CANLI)


if __name__ == '__main__':
    unittest.main()
