# Copyright 2026 Yelpence
"""`_on_formation_command` HICBIR SEKILDE COKMEMELI — sahada olculdu.

🔴 8 EYLUL 2026, 16:27 UCUSU. Supurme surdurucusu baglanirken nesne
`__init__`'e degil, `_on_formation_command`'in ICINE ve kullanildigi
satirdan SONRAYA konmustu. Sonuc:

    formation.log (ylp01):
      File "formation_node.py", line 471, in _on_formation_command
        self._supurme.hedef_geldi(
      AttributeError: 'FormationControlNode' object has no attribute '_supurme'

Takipciler gelen HER formasyon komutunda cokuyor, hicbirini islemiyordu:
    rotasyon yakinsamadi        -> "hata 7.57 m (suru yari donuk olabilir)"
    suru QR'a hic gitmedi       -> yatayda net 0.14 m
    QR mesafe 8.25 -> 8.41 m    -> hic azalmadi
Ve HICBIR SEY hata gibi gorunmedi: istisna ROS callback'i icinde kaldi,
ne YKI'ye ne mesh'e yansidi. Operator "kalktilar, oylece kaldilar" dedi.

BU DOSYA IKI SEYI KILITLIYOR
  ① `_supurme` __init__'te kurulur — abonelikler ondan SONRA baglanir
  ② callback eksik alana karsi savunmacidir (ikinci kat)
"""

import pathlib
import re

KAYNAK = (pathlib.Path(__file__).resolve().parents[3] / 'src' / 'swarm_core'
          / 'swarm_core' / 'formation_control' / 'formation_node.py').read_text()


def _govde(ad: str) -> str:
    """Verilen metodun govdesini doner (bir sonraki `    def` a kadar)."""
    i = KAYNAK.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = KAYNAK.find('\n    def ', i + 1)
    return KAYNAK[i:j if j > 0 else len(KAYNAK)]


def test_SURDURUCU_INIT_TE_KURULUYOR():
    """🔴 Kusurun ta kendisi: eskiden callback'in icinde kuruluyordu."""
    assert 'self._supurme = SupurmeSurdurucu()' in _govde('__init__')


def test_SURDURUCU_CALLBACK_ICINDE_KURULMUYOR():
    """Callback icinde kurmak, ilk cagrida AttributeError demekti."""
    assert 'SupurmeSurdurucu()' not in _govde('_on_formation_command')


def test_KURULUM_ABONELIKLERDEN_ONCE():
    """Abonelik once baglanirsa ilk komut nesne yokken gelebilir."""
    g = _govde('__init__')
    kurulum = g.find('self._supurme = SupurmeSurdurucu()')
    abone = g.find('self._setup_subscribers()')
    assert kurulum >= 0 and abone >= 0
    assert kurulum < abone, 'surdurucu aboneliklerden SONRA kuruluyor'


def test_CALLBACK_SAVUNMACI():
    """Ikinci kat: eksik alan callback'i COKERTMEMELI."""
    g = _govde('_on_formation_command')
    assert "getattr(self, '_supurme', None)" in g


def test_MERKEZ_COZUCU_DE_SAVUNMACI():
    """`_resolve_center` de ayni korumaya sahip olmali."""
    assert "getattr(self, '_supurme', None)" in _govde('_resolve_center')


def test_CALLBACKTE_KORUMASIZ_SURDURUCU_KULLANIMI_YOK():
    """Her `self._supurme.` kullanimi ya init sonrasi ya korumali olmali."""
    g = _govde('_on_formation_command')
    for m in re.finditer(r'self\._supurme\.', g):
        onceki = g[:m.start()]
        assert "getattr(self, '_supurme', None)" in onceki, (
            'callback icinde korumasiz surdurucu kullanimi var')
