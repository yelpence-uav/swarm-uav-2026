# Copyright 2026 Yelpence
"""LIDER HER ZAMAN SLOT 0 (= ortada) — 4 Eylul 2026, YALNIZ GOREV 2.

Operator: "YLP00'i kalici lider secelim ve o her zaman ortaya konulacak."

Ozelligin dayandigi IKI olgu var; ikisi de burada kilitleniyor:

  1) GEOMETRI — compute_slot_offsets() slot 0'i her formasyonda (0,0,0)
     uretiyor ve o nokta formasyonun tepe/merkezidir. Bu kirilirsa "lider
     ortada" cumlesi sessizce yanlis olur.

  2) SIRA — slot i <-> agent_ids[i] (Macar YOK, KARAR-11). Yani lideri
     ortaya koymak, onu agent_ids listesinin BASINA koymak demek.
     Oncesinde bu sira dogrudan SURU_KADRO env'inden geliyordu; kadro
     "3 1" yazilsaydi slot 0 ylp02'ye gider ve hicbir yerde hata
     gorunmezdi.

⚠️ KAPSAM: `mode_manager` yalnizca Gorev 2 profilinde kosuyor (`mod`
bayragi). Gorev 1'in slot atamasini mission1 yapiyor
(formation_cmd.build_slot_assignment, Macar) ve ona DOKUNULMADI.
"""

import unittest

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
)

from swarm_state_machine.mode_manager import tek_yayinci

ALFA = 0.7853981633974483   # 45 derece


class TestSlotSifirMerkezdir(unittest.TestCase):
    """(1) Geometri olgusu: slot 0 = tepe/merkez, uc formasyonda da."""

    def test_slot0_ucunde_de_orijinde(self):
        for tip in (FORMATION_CIZGI, FORMATION_OKBASI, FORMATION_V):
            for n in (2, 3):
                with self.subTest(tip=tip, n=n):
                    slots = compute_slot_offsets(tip, n, 7.0, ALFA)
                    self.assertEqual(slots[0], (0.0, 0.0, 0.0))

    def test_cizgide_slot0_hattin_ORTASI(self):
        """Uc ucakta cizgi: slot 0 iki kanadin tam ortasinda."""
        s = compute_slot_offsets(FORMATION_CIZGI, 3, 7.0, ALFA)
        self.assertEqual(s[0], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(s[1][1], +7.0)
        self.assertAlmostEqual(s[2][1], -7.0)
        # Kanatlarin ortalamasi slot 0'a esit -> gercekten "orta".
        self.assertAlmostEqual((s[1][1] + s[2][1]) / 2.0, s[0][1])

    def test_okbasinda_slot0_UCTA_kanatlar_geride(self):
        s = compute_slot_offsets(FORMATION_OKBASI, 3, 7.0, ALFA)
        self.assertEqual(s[0], (0.0, 0.0, 0.0))
        self.assertLess(s[1][0], 0.0)     # kanatlar GERIDE
        self.assertLess(s[2][0], 0.0)

    def test_vde_slot0_ARKA_kosede_kanatlar_onde(self):
        s = compute_slot_offsets(FORMATION_V, 3, 7.0, ALFA)
        self.assertEqual(s[0], (0.0, 0.0, 0.0))
        self.assertGreater(s[1][0], 0.0)  # kanatlar ONDE
        self.assertGreater(s[2][0], 0.0)


class TestLiderOnde(unittest.TestCase):
    """(2) Sira kurali: lider listenin basina, kalani sirali."""

    def test_lider_basa_alinir(self):
        self.assertEqual(tek_yayinci.lider_onde(1, [1, 2, 3]), [1, 2, 3])

    def test_lider_ortadaysa_basa_ceker(self):
        self.assertEqual(tek_yayinci.lider_onde(2, [1, 2, 3]), [2, 1, 3])

    def test_lider_sondaysa_basa_ceker(self):
        self.assertEqual(tek_yayinci.lider_onde(3, [1, 2, 3]), [3, 1, 2])

    def test_KADRO_SIRASI_ONEMSIZ(self):
        """Asil kazanc: SURU_KADRO nasil yazilirsa yazilsin cikti ayni.

        Once sira dogrudan env'den geliyordu ve "3 1" yazmak slot 0'i
        sessizce ylp02'ye verirdi — hicbir yerde hata gorunmeden.
        """
        for kadro in ([1, 3], [3, 1]):
            with self.subTest(kadro=kadro):
                self.assertEqual(tek_yayinci.lider_onde(1, kadro), [1, 3])

    def test_iki_ucakli_kadro(self):
        """Gorev 2 bugun iki ucakla kosuyor: ylp00 (1) + ylp02 (3)."""
        self.assertEqual(tek_yayinci.lider_onde(1, [1, 3]), [1, 3])

    def test_uzunluk_KORUNUR(self):
        """Ofset dizisi kadroyla ayni boyda olmali.

        Boyut kaymasi butun slot eslemesini yanlis ucaga kaydirir.
        """
        for kadro in ([1, 3], [1, 2, 3]):
            with self.subTest(kadro=kadro):
                self.assertEqual(
                    len(tek_yayinci.lider_onde(1, kadro)), len(kadro))

    def test_lider_kadroda_YOKSA_uydurma_kimlik_EKLENMEZ(self):
        """Kadro disi lider id'si slot 0'a KONULMAZ.

        Konulsaydi ofset dizisi kadrodan bir uzun olur ve butun eslesme
        kayardi. Guvenli taraf: sirali kadro.
        """
        self.assertEqual(tek_yayinci.lider_onde(2, [1, 3]), [1, 3])

    def test_bos_kadro_bos_doner(self):
        self.assertEqual(tek_yayinci.lider_onde(1, []), [])


class TestUctanUcaSlotEslemesi(unittest.TestCase):
    """(1)+(2) birlikte: lider gercekten merkez ofsetini aliyor."""

    def test_lider_merkez_ofsetini_alir(self):
        for tip in (FORMATION_CIZGI, FORMATION_OKBASI, FORMATION_V):
            for kadro in ([1, 3], [3, 1], [1, 2, 3]):
                with self.subTest(tip=tip, kadro=kadro):
                    ids = tek_yayinci.lider_onde(1, kadro)
                    slots = compute_slot_offsets(tip, len(ids), 7.0, ALFA)
                    atama = dict(zip(ids, slots))
                    self.assertEqual(atama[1], (0.0, 0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
