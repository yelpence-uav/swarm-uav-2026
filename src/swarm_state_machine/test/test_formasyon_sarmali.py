# Copyright 2026 Yelpence
"""FORMASYONSUZ OFSET SARMALI — 31 Agustos 2026, uc ucakli kalkis.

OLAY: SwD ile kalkis verildi, uc ucak da birlikte kalkti (dogru).
Kalkis bitip `formasyon_sustur` birakildigi an ucaklar birbirine
kapanmaya basladi. Rosbag'den olculen ucak arasi mesafeler:

    t = 8,45 sn  (susturma ACIK)   8,35 / 6,91 / 7,40 m
    t = 9,05 sn  (BIRAKILDI)       8,38 / 6,92 / 7,44 m
    t = 10,74 sn                   5,05 / 4,54 / 4,21 m
    t = 11,25 sn                   3,04 / 3,29 / 2,00 m
    t = 12,34 sn                   0,36 / 1,54 / 1,19 m   <-- 36 SANTIM

Kacinma 3 m altinda kapali (altitude_gate_m = 3.0) oldugu icin hicbir
sey durdurmadi; operator elle indirdi.

SEBEP — iki kusur birlikte:
  (1) mode_manager FORMATION_UNKNOWN dalinda ofsetleri HER YAYINDA
      yeniden olcuyordu (~19 Hz).
  (2) Olcum DUNYA cercevesinde, tuketim FORMASYON cercevesinde:
      formation_node gomulu ofseti heading ile DONDURUYOR.

Ikisi kapali bir dongu kuruyor: olc -> Rot(+212 deg) ile hedefle ->
ucak geriden gelir -> yeniden olc -> TEKRAR dondur -> yaricap kucul.
Yani ICE DOGRU SARMAL.

Bu dosya duzeltmenin iki parcasini da kilitliyor.
"""

import math
import os
import re
import unittest

from swarm_core.formation_control.formation_geometry import rotate_offset


def _kaynak(paket_alt_yol: str) -> str:
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, paket_alt_yol), encoding='utf-8') as f:
        return f.read()


def _yorumsuz(govde: str) -> str:
    """Yorum satirlarini atar — testin kendi ACIKLAMA metnini yakalamasin."""
    cikti = []
    for satir in govde.splitlines():
        kirpik = satir.split('#', 1)[0]
        if kirpik.strip():
            cikti.append(kirpik)
    return '\n'.join(cikti)


class TestTersDondurmeMatematigi(unittest.TestCase):
    """(a) Rot(-h) ile gom, tuketici Rot(+h) uygular -> DUNYA cercevesi.

    formation_node ile AYNI rotate_offset kullaniliyor, bilerek: iki ayri
    kopya isaret ya da eksen sirasinda sessizce kayabilir.
    """

    def test_tur_gidis_donus_BIRIM(self):
        for heading in (0.0, 45.0, 90.0, 180.0, 212.4, 270.0, 359.9):
            h = math.radians(heading)
            for (dx, dy) in ((1.0, 0.0), (0.0, 1.0), (-2.12, -3.95),
                             (4.65, 0.99), (-2.52, 2.97)):
                gx, gy = rotate_offset(dx, dy, -h)      # mode_manager gomer
                sx, sy = rotate_offset(gx, gy, h)       # formation_node acar
                self.assertAlmostEqual(sx, dx, places=6,
                                       msg=f'heading={heading} dx bozuldu')
                self.assertAlmostEqual(sy, dy, places=6,
                                       msg=f'heading={heading} dy bozuldu')

    def test_ters_dondurme_YOKSA_hedef_KAYAR(self):
        """Duzeltme olmadan ne oluyordu: ofset 212 derece donuyordu."""
        h = math.radians(212.4)
        dx, dy = -2.12, -3.95
        sx, sy = rotate_offset(dx, dy, h)       # eski (hatali) yol
        kayma = math.dist((dx, dy), (sx, sy))
        self.assertGreater(
            kayma, 5.0,
            'eski yolda ofset donuyordu; bu test kusuru belgeliyor')

    def test_dondurme_MESAFE_korur_tek_basina_carpistirmaz(self):
        """Sarmali yaratan dondurme DEGIL, dondurme + YENIDEN OLCUM.

        Dondurme bir izometridir: tek basina uygulansaydi ucaklar yanlis
        yerlere giderdi ama BIRBIRINE girmezdi. Carpisan sey her turda
        yeniden olculup tekrar dondurulen ofsetin yaricapini kaybetmesi.
        Bu testin amaci teshisi kalici kilmak.
        """
        h = math.radians(212.4)
        ofsetler = [(-2.12, -3.95), (4.65, 0.99), (-2.52, 2.97)]
        donuk = [rotate_offset(x, y, h) for (x, y) in ofsetler]
        for i in range(3):
            for j in range(i + 1, 3):
                once = math.dist(ofsetler[i], ofsetler[j])
                sonra = math.dist(donuk[i], donuk[j])
                self.assertAlmostEqual(once, sonra, places=6)


class TestModeManagerKaynagi(unittest.TestCase):
    """(a) ters dondurme ve (b) dondurma kodda DURUYOR mu."""

    def _unknown_dali(self) -> str:
        kod = _kaynak(os.path.join(
            'swarm_state_machine', 'mode_manager', 'mode_manager_node.py'))
        m = re.search(
            r'elif ftype == FORMATION_UNKNOWN:.*?(?=\n        self\._formation_pub)',
            kod, re.S)
        self.assertIsNotNone(m, 'FORMATION_UNKNOWN dali bulunamadi')
        return m.group(0)

    def test_ters_dondurme_UYGULANIYOR(self):
        kod = _yorumsuz(self._unknown_dali())
        self.assertIn('rotate_offset', kod,
                      'ofsetler formasyon cercevesine cevrilmiyor — '
                      '31 Agustos sarmali geri gelir')
        self.assertRegex(
            kod, r'ters_h\s*=\s*-math\.radians',
            'dondurme TERS isaretle yapilmiyor')

    def test_ofsetler_DONDURULUYOR(self):
        kod = _yorumsuz(self._unknown_dali())
        self.assertIn('_donmus_ofsetler', kod,
                      'ofsetler her yayinda yeniden olculuyor')

    def test_dondurma_READY_girisinde_COZULUYOR(self):
        """Ofsetler ve centroid AYNI ana ait olmak zorunda."""
        kod = _kaynak(os.path.join(
            'swarm_state_machine', 'mode_manager', 'mode_manager_node.py'))
        m = re.search(
            r'self\._donmus_ofsetler = None\n\s*if self\._ctx\.konumdan_tohumla\(\)',
            kod)
        self.assertIsNotNone(
            m, 'READY girisinde dondurma cozulmuyor — centroid tazelenirken '
               'ofsetler eski ana ait kalir')

    def test_gercek_formasyona_gecince_dondurma_COZULUYOR(self):
        kod = _kaynak(os.path.join(
            'swarm_state_machine', 'mode_manager', 'mode_manager_node.py'))
        i_tip = kod.index('if ftype in (FORMATION_OKBASI')
        i_unknown = kod.index('elif ftype == FORMATION_UNKNOWN')
        self.assertIn(
            'self._donmus_ofsetler = None', kod[i_tip:i_unknown],
            'gercek formasyona gecerken dondurma cozulmuyor — formasyondan '
            'cikip tekrar formasyonsuza donunce ESKI dizilim geri gelirdi')


class TestDikeyYetkiKaynagi(unittest.TestCase):
    """Ayri kusur: gaz cubugu dipteyken kalkis sonrasi 2 m/s ALCALMA.

    Olculen: throttle_cmd = -1,00 SABIT (cubuk yayli degil, dipte durur),
    max_speed 2,0 -> vz = +2,00 m/s NED, doyumda. B18 gaz-merkez kapisi
    tek atislik mandal oldugu icin tutmadi.
    """

    def _kaynak_joy(self) -> str:
        return _kaynak(os.path.join(
            'swarm_state_machine', 'mode_manager',
            'joystick_interpreter_node.py'))

    def test_dikey_yetki_mandali_VAR(self):
        kod = _yorumsuz(self._kaynak_joy())
        self.assertIn('_dikey_yetki', kod, 'dikey yetki mandali yok')

    def test_kalkis_kenarinda_SIFIRLANIYOR(self):
        kod = _yorumsuz(self._kaynak_joy())
        m = re.search(
            r'if self\._swd\.kalkisi_tuket\(\):.*?(?=\n        cmd\.takeoff)',
            kod, re.S)
        self.assertIsNotNone(m, 'kalkis kenari dali bulunamadi')
        self.assertIn(
            'self._dikey_yetki = False', m.group(0),
            'kalkis istendiginde dikey yetki yeniden kurulmuyor — suru '
            'irtifaya varinca gaz dipteyse ANINDA alcalir')

    def test_command_valid_e_DOKUNMUYOR(self):
        """command_valid G2-K10 kalkis kapilarindan biri; sifirlanamaz."""
        kod = _yorumsuz(self._kaynak_joy())
        m = re.search(r'if not self\._dikey_yetki:.*?(?=\n        cmd\.rtl)',
                      kod, re.S)
        self.assertIsNotNone(m, 'dikey yetki blogu bulunamadi')
        self.assertNotIn(
            'command_valid', m.group(0),
            'dikey yetki mandali command_valid e dokunuyor — kalkisin '
            'KENDISI bloke olur')
        self.assertIn('cmd.throttle_cmd = 0.0', m.group(0),
                      'yetki yokken dikey komut sifirlanmiyor')

    def test_merkez_sinamasi_HAM_deger_uzerinden(self):
        """Merkez sinamasi HAM gaz uzerinden yapilmali.

        Kapilar cmd.throttle_cmd'i sifirlayabiliyor; sifirlanan deger
        "merkezde" gorunup kapiyi kendi kendine acardi.
        """
        kod = _yorumsuz(self._kaynak_joy())
        self.assertIn('ham_gaz = cmd.throttle_cmd', kod)
        i_ham = kod.index('ham_gaz = cmd.throttle_cmd')
        i_kullanim = kod.index('gaz_merkezde(ham_gaz')
        self.assertLess(i_ham, i_kullanim)


if __name__ == '__main__':
    unittest.main()
