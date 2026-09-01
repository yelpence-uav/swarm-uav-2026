# Copyright 2026 Yelpence
"""MADDE 29 — Gorev 2 aralik/irtifa dogrulamasi ve HAVADA kapisi.

Operator (31 Agustos 2026): "gorev 2 yi baslatmadan once bize dronelar
kalktiktan sonra kac m acilsin diye sorsun... ayrica kac m irtifa
istedigimizide sorsun."

Sayi YKI'den geliyor ama SINIR DENETIMI UCAKTA. Sebep: YKI tek kopya
degil (tarayici formu + backend + mesh) ve kopyalar kaciniilmaz olarak
ayrisir; ucak kendine gelen sayiyi kendisi denetlerse kaynagi ne olursa
olsun ayni kapidan gecer.

🔴 IKI AYRI KAPI, IKI AYRI DUGUM. Ikisi de olmak zorunda:
  * mode_manager: irtifa + aralik, `ctx.kalkis_tamam` ile kapali,
  * joystick:     aralik, `_kalkis_istendi` ile kapali.
Aralik ucusta ctx'e mode_manager'in KENDI alanindan degil, formasyon
degisikliginde joystick komutundan giriyor (mode_manager_node ~914).
Yalniz mode_manager'da kapatilsaydi kapi KAGIT UZERINDE kalirdi: havada
gelen yeni aralik joystick'e yazilir, sonraki SwC hareketinde formasyon
ISTENMEDEN morf ederdi.
"""

import os

import pytest

from swarm_state_machine.mode_manager import canli_param as cp


class TestSinirlar:

    def test_kabul_edilen_tipik_degerler(self):
        assert cp.g2_ayar_dogrula(9.0, 15.0) == (9.0, 15.0)
        assert cp.g2_ayar_dogrula(7.0, 5.0) == (7.0, 5.0)

    def test_bos_birakmak_GECERLI(self):
        """Kutuyu bos birakmak = "varsayilani koru", hata DEGIL."""
        for bos in (0.0, 0, None, ''):
            a, i = cp.g2_ayar_dogrula(bos, bos)
            assert a == cp.BELIRTILMEDI and i == cp.BELIRTILMEDI

    def test_tek_alan_da_verilebilir(self):
        assert cp.g2_ayar_dogrula(9.0, 0.0) == (9.0, 0.0)
        assert cp.g2_ayar_dogrula(0.0, 12.0) == (0.0, 12.0)

    @pytest.mark.parametrize('aralik', [3.9, 0.5, 25.6, 100.0, -5.0])
    def test_aralik_sinir_disi_REDDEDILIR(self, aralik):
        with pytest.raises(cp.ParamRed):
            cp.g2_ayar_dogrula(aralik, 0.0)

    @pytest.mark.parametrize('irtifa', [2.9, 0.5, 30.1, 120.0, -3.0])
    def test_irtifa_sinir_disi_REDDEDILIR(self, irtifa):
        with pytest.raises(cp.ParamRed):
            cp.g2_ayar_dogrula(0.0, irtifa)

    def test_tam_sinirlar_GECER(self):
        """Kapali aralik: 4.0 ve 25.5 kabul, 3.0 ve 30.0 kabul."""
        assert cp.g2_ayar_dogrula(4.0, 3.0) == (4.0, 3.0)
        assert cp.g2_ayar_dogrula(25.5, 30.0) == (25.5, 30.0)

    def test_sayi_olmayan_REDDEDILIR(self):
        for kotu in ('abc', [1], {}, True):
            with pytest.raises(cp.ParamRed):
                cp.g2_ayar_dogrula(kotu, 0.0)

    def test_red_mesaji_SINIRLARI_SOYLUYOR(self):
        """Mesaj dogrudan operatore gidiyor; sayi icermezse ise yaramaz."""
        with pytest.raises(cp.ParamRed) as e:
            cp.g2_ayar_dogrula(30.0, 0.0)
        metin = str(e.value)
        assert '4' in metin and '25.5' in metin


class TestSinirDegerleriKaymasin:
    """Sayilar gerekcelerine BAGLI; sessizce degismesinler."""

    def test_aralik_alt_siniri_kacinma_esigi(self):
        """4.0 m = kacinma girisi (d0). Altinda kacinma SUREKLI acik."""
        assert cp.ARALIK_ALT_M == 4.0

    def test_aralik_ust_siniri_MESH_tavani(self):
        """25.5 m = 1 bayt desimetre tavani (packet_parser aralik_dm)."""
        assert cp.ARALIK_UST_M == 25.5

    def test_irtifa_sinirlari(self):
        assert cp.IRTIFA_ALT_M == 3.0
        assert cp.IRTIFA_UST_M == 30.0


def _kaynak(dosya: str) -> str:
    """Dugum ROS'suz import edilemiyor; govdeyi kaynaktan oku."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_state_machine', 'mode_manager', dosya)
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _govde(kaynak: str, imza: str) -> str:
    bas = kaynak.index(imza)
    son = kaynak.find('\n    def ', bas + len(imza))
    return kaynak[bas:son if son > 0 else len(kaynak)]


class TestHavadaKapisi:

    def test_mode_manager_HAVADA_uygulamaz(self):
        g = _govde(_kaynak('mode_manager_node.py'), 'def _on_g2_ayar')
        assert 'kalkis_tamam' in g, (
            'mode_manager havadayken ayari uyguluyor — irtifa degisirse '
            'TAKEOFF\'a donuste yanlis hedefe tirmanir, aralik degisirse '
            'formasyon istemeden morf eder'
        )
        # Kapi, degerler YAZILMADAN once gelmeli.
        assert g.index('kalkis_tamam') < g.index('default_spacing_m')

    def test_joystick_HAVADA_uygulamaz(self):
        g = _govde(_kaynak('joystick_interpreter_node.py'),
                   'def _on_g2_ayar')
        assert '_kalkis_istendi' in g, (
            'joystick kapisi YOK — mode_manager kapisi tek basina yetmez, '
            'aralik ctx\'e joystick komutundan giriyor'
        )
        assert g.index('_kalkis_istendi') < g.index('default_spacing_m')

    def test_joystick_mandali_kalkis_kenarinda_KAPANIR(self):
        k = _kaynak('joystick_interpreter_node.py')
        assert 'self._kalkis_istendi = True' in k
        assert 'self._kalkis_istendi = False' in k
        # Kalkis tuketimiyle ayni blokta kapanmali.
        i_tuket = k.index('self._swd.kalkisi_tuket()')
        assert 0 < k.index('self._kalkis_istendi = True') - i_tuket < 400

    def test_ayar_ROS_PARAMETRESINDEN_gecer(self):
        """🔴 31 Agustos, UCAKTA OLCULDU: alana dogrudan yazan surumde
        dugum 9.0 m kullanirken `ros2 param get default_spacing_m` hala
        7.0 diyordu. Sahada bu bir saat yakar.

        Ikinci kazanc mode_manager'a ozgu: parametre geri cagrisi
        `_init_default_offsets()` cagiriyor. Dogrudan yazan surumde
        `_formation_offsets` ESKI aralikta kaliyordu.
        """
        for dosya in ('mode_manager_node.py', 'joystick_interpreter_node.py'):
            g = _govde(_kaynak(dosya), 'def _on_g2_ayar')
            assert 'set_parameters' in g, (
                f'{dosya}: ayar alana dogrudan yaziliyor — `ros2 param get` '
                'eski degeri soyler')
            assert 'Parameter(' in g

    def test_her_iki_dugum_de_ayni_DOGRULAYICIYI_kullanir(self):
        """Sinir denetimi TEK YERDE; ikinci kopya kaciniilmaz ayrisir."""
        for dosya in ('mode_manager_node.py', 'joystick_interpreter_node.py'):
            g = _govde(_kaynak(dosya), 'def _on_g2_ayar')
            assert 'g2_ayar_dogrula' in g, f'{dosya} kendi sinirini yazmis'
