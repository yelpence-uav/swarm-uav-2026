"""AlertManager pil uyarilari — DALGALANMA BASTIRMASI.

🔴 2 Eylul 2026, operator bildirdi: "bazen voltaj dalgalaniyor, o yuzden
her yuzde degisiminde uyari veriyor."

KOK NEDEN: `_set()` tekrari MESAJ METNINE bakarak eliyor ve pil mesajinin
icinde yuzde var ("Pil azaldi: %24"). Gerilim dalgalandikca yuzde oynuyor,
metin degisiyor, eleme tutmuyor ve HER degerlendirme turunda yeni uyari +
yeni defter kaydi uretiliyordu. Gosterge olcegi 14.2-16.8'e daraltilinca
(1 V ~ %38) daha da kotulesti: 0.03 V'luk dalgalanma ~1 puan oynatiyor.

COZUM: ayni uyari surerken mesaj ancak GERILIM `BAT_TITRESIM_V` kadar
degistiyse guncellenir. Yuzde degil gerilim, cunku yuzde turetilmis ve
gurultuyu buyutuyor.

CALISTIRMA (depoda backend icin ayri test kosucusu yok):
    cd src/gcs && python3 -m pytest backend/tests -q
"""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.core.alert_manager import AlertManager      # noqa: E402
from backend.core.state_store import DroneState          # noqa: E402

DUSUK = (1, "low_battery")
KRITIK = (1, "critical_battery")


def _drone(volt: float, yuzde: float) -> DroneState:
    """Pil disindaki her sey saglikli bir drone durumu."""
    d = DroneState(drone_id=1, name="ylp00", sysid=1)
    d.connected = True
    d.battery_voltage = volt
    d.battery_percent = yuzde
    d.gps_fix_type = 3
    d.gps_hdop = 0.5
    return d


class TestDalgalanmaBastirmasi(unittest.TestCase):
    """Bolgeye girdikten sonra kucuk gerilim oynamalari SUSMALI."""

    def setUp(self):
        self.am = AlertManager(susturulan=[], pil=True)

    def _mesaj(self, volt, yuzde):
        self.am.evaluate([_drone(volt, yuzde)])
        a = self.am._active.get(KRITIK) or self.am._active.get(DUSUK)
        return a.message if a else None

    def test_ilk_giris_BILDIRIR(self):
        self.assertEqual(self._mesaj(14.85, 25.0), "Pil azaldı: %25")

    def test_kucuk_dalgalanma_MESAJI_DEGISTIRMEZ(self):
        self._mesaj(14.85, 25.0)
        # Operatorun tarif ettigi durum: gerilim asagi yukari oynuyor.
        for v, p in ((14.82, 23.8), (14.86, 25.4), (14.80, 23.1),
                     (14.84, 24.6), (14.60, 15.4)):
            self.assertEqual(self._mesaj(v, p), "Pil azaldı: %25",
                             f"{v} V'ta mesaj degisti — bastirma calismadi")

    def test_esigi_ASAN_dususte_mesaj_GUNCELLENIR(self):
        # 15.20 -> 14.60 = 0.60 V > BAT_TITRESIM_V, ayni bant icinde.
        self._mesaj(15.20, 38.5)          # bolgenin disinda, uyari yok
        self._mesaj(14.90, 26.9)          # hala disarida (>25)
        self.assertEqual(self._mesaj(14.84, 24.6), "Pil azaldı: %25")
        self.assertEqual(self._mesaj(14.30, 3.8), "Pil kritik: %4")

    def test_BANT_DEGISIMI_aninda_bildirilir(self):
        """LOW -> KRITIK bastirilamaz: ayri anahtar, ayri uyari."""
        self._mesaj(14.85, 25.0)
        # 0.40 V dususte esik (0.5) asilmadi ama bant DEGISTI.
        self.assertEqual(self._mesaj(14.45, 9.6), "Pil kritik: %10")

    def test_toparlaninca_TEMIZLENIR(self):
        self._mesaj(14.85, 25.0)
        self.assertIsNone(self._mesaj(15.10, 34.6))

    def test_temizlenince_olcum_hafizasi_da_gider(self):
        """Yeniden girişte ILK bildirim bastirilmamali."""
        self._mesaj(14.85, 25.0)
        self._mesaj(15.10, 34.6)                    # temizlendi
        self.assertNotIn(DUSUK, self.am._son_olcum)
        self.assertEqual(self._mesaj(14.80, 23.1), "Pil azaldı: %23")


class TestPilKapaliyken(unittest.TestCase):
    """`alerts.pil: false` iken hic uyari uretilmemeli."""

    def test_pil_kapali_uyari_YOK(self):
        am = AlertManager(susturulan=[], pil=False)
        am.evaluate([_drone(14.20, 0.0)])
        self.assertIsNone(am._active.get(DUSUK))
        self.assertIsNone(am._active.get(KRITIK))


class TestEsikGerilimKarsiliklari(unittest.TestCase):
    """Esikler gosterge olcegiyle (14.2-16.8) tutarli kalmali."""

    def test_esikler(self):
        # 4S, span 2.6 V: %25 -> 14.85 V, %10 -> 14.46 V
        self.assertAlmostEqual(
            14.2 + AlertManager.BAT_LOW_ON / 100.0 * 2.6, 14.85, places=2)
        self.assertAlmostEqual(
            14.2 + AlertManager.BAT_CRIT_ON / 100.0 * 2.6, 14.46, places=2)

    def test_titresim_esigi_bant_genisliginden_BUYUK(self):
        """0.5 V, LOW bandindan (0.39 V) buyuk — bilincli.

        Ayni bant icinde mesaj pratikte guncellenmez; bant degisimi
        zaten ayri anahtar oldugu icin aninda bildirilir.
        """
        bant_v = (AlertManager.BAT_LOW_ON
                  - AlertManager.BAT_CRIT_ON) / 100.0 * 2.6
        self.assertGreater(AlertManager.BAT_TITRESIM_V, bant_v)


if __name__ == "__main__":
    unittest.main()
