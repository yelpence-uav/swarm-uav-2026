# Copyright 2026 Yelpence
"""command_valid AYRISMASI — 5 Eylul 2026, ucusta olculdu.

BELIRTI (operator): "iki ucagi da cizgide dizip kaldirdim, havada
beklediler ve formasyonu tamamlamadilar."

OLCULEN (/swarm/public/control/command, iki ucagin bag'i):
    t=13.68  formasyon=1  ylp00 gecerli=FALSE   ylp01 gecerli=True
    t=17.31  formasyon=3  ylp00 gecerli=FALSE   ylp01 gecerli=True
    t=23.96  formasyon=3  ylp00 gecerli=True
ylp01 loglari: "Formasyon degisikligi: 3" (isledi)
ylp00 loglari: hicbir formasyon satiri YOK (dusurdu)

IKI AYRI KUSUR VARDI:

1) command_valid MESH'TEN GECMIYORDU. esp32_bridge alici tarafta
   `msg.command_valid = True` SABIT yaziyordu ve KOMUT bayraklarinda
   karsiligi yoktu. Sonuc lider/takipci AYRISMASI:
     lider  -> gercek B18 gaz-merkez kapisi -> False
     takipci-> mesh'ten sabit True
   Tarifi basmaya TEK YETKILI ucak (lider) istegi dusurdugu icin
   formasyon hic kurulmadi.
   🔴 Daha tehlikelisi: `command_valid=False` dalinda lider CUBUKLARI
   SIFIRLIYOR, takipciler ayni pakette cubuklari UYGULUYOR — gaz
   dipteyken suru ikiye bolunur. Duzeltme: KOMUT_FLAG_COMMAND_VALID
   (0x80) eklendi, paket 16 bayt kaldi.

2) FORMASYON TALEBI gecersiz pakette dusuruluyordu. command_valid'i
   False yapan sey B18 GAZ MERKEZ kapisi; formasyon talebi ise bir cubuk
   hareketi DEGIL — hiz tasimiyor, suruyu kendi basina hareket
   ettirmiyor, yerde kalkis kapisi (B15) yayini zaten kilitli tutuyor.
   Kodun kendi ayrimi ("IPTAL aksiyonlari HER ZAMAN gecer") bu talebi de
   kapsamaliydi.

Ayni sinif: deadman_timeout_s mesh'te tasinmiyordu (gorev2.md §7.18) ve
belirtisi de aynidir — "yarim calisiyor" gibi gorunup gozden kaciyor.
"""

import unittest

from swarm_control.esp32_bridge import packet_parser as pp


class TestMeshBayragi(unittest.TestCase):
    """command_valid artik mesh'ten tasiniyor."""

    def test_bayrak_TANIMLI_ve_bos_bitte(self):
        self.assertEqual(pp.KOMUT_FLAG_COMMAND_VALID, 0x80)

    def test_diger_bayraklarla_CAKISMIYOR(self):
        digerleri = (
            pp.KOMUT_FLAG_TAKEOFF, pp.KOMUT_FLAG_LAND, pp.KOMUT_FLAG_RTL,
            pp.KOMUT_FLAG_EMERGENCY, pp.KOMUT_FLAG_FORMATION_CHANGE,
            pp.KOMUT_FLAG_DEADMAN_PRESSED, pp.KOMUT_FLAG_ARM,
        )
        for b in digerleri:
            with self.subTest(bayrak=hex(b)):
                self.assertEqual(pp.KOMUT_FLAG_COMMAND_VALID & b, 0)

    def test_butun_bayraklar_TEK_BAYTA_sigiyor(self):
        toplam = (pp.KOMUT_FLAG_TAKEOFF | pp.KOMUT_FLAG_LAND
                  | pp.KOMUT_FLAG_RTL | pp.KOMUT_FLAG_EMERGENCY
                  | pp.KOMUT_FLAG_FORMATION_CHANGE
                  | pp.KOMUT_FLAG_DEADMAN_PRESSED | pp.KOMUT_FLAG_ARM
                  | pp.KOMUT_FLAG_COMMAND_VALID)
        self.assertEqual(toplam, 0xFF)

    def test_paket_16_BAYT_kaldi(self):
        """Bayrak mevcut bir bayta eklendi — firmware degismedi."""
        b = pp.komut_paketle(
            0, pp.KOMUT_FLAG_COMMAND_VALID | pp.KOMUT_FLAG_DEADMAN_PRESSED,
            0, 0, 0, 0)
        self.assertEqual(len(b), 16)

    def test_gidis_donus(self):
        bayraklar = (pp.KOMUT_FLAG_COMMAND_VALID
                     | pp.KOMUT_FLAG_FORMATION_CHANGE)
        k = pp.komut_coz(pp.komut_paketle(0, bayraklar, 0, 0, 0, 0))
        self.assertTrue(k.flags & pp.KOMUT_FLAG_COMMAND_VALID)
        self.assertTrue(k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE)

    def test_bayraksiz_pakette_GECERSIZ(self):
        """Eski davranis (sabit True) geri gelmemeli."""
        k = pp.komut_coz(pp.komut_paketle(0, 0, 0, 0, 0, 0))
        self.assertFalse(k.flags & pp.KOMUT_FLAG_COMMAND_VALID)


if __name__ == '__main__':
    unittest.main()
