# Copyright 2026 Yelpence
"""YKI'den TAKIM SLOTU gonderilebilmeli — sahada SSH sart olmasin.

🔴 9 EYLUL 2026, operator: "yarismada SSH ile baglanamayabilirim.
Ayarlayamaz miyiz?"

QR'in `team` tablosu SLOT ile anahtarli, slotu hakem gorev aninda veriyor
ve yanlis slot QR'i TAMAMEN okunamaz yapiyor. Onceki tek yol ucaga ag
uzerinden erisip `ros2 param set` yapmakti; sahada Wi-Fi olmayabilir.

Zincir: YKI formu -> parameters_json -> backend -> g1_ayar dizisi ->
base ESP -> GOREV 1 BASLAT paketinin REZERV bayti -> ucak -> goru dugumu.
"""

import pathlib

KAYNAK = (pathlib.Path(__file__).resolve().parents[3] / 'gcs' / 'backend'
          / 'connections' / 'ros_bridge.py').read_text()
PANEL = (pathlib.Path(__file__).resolve().parents[3] / 'gcs' / 'frontend'
         / 'src' / 'components' / 'MissionPanel' / 'MissionPanel.tsx').read_text()


def _govde(ad: str) -> str:
    i = KAYNAK.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = KAYNAK.find('\n    def ', i + 1)
    return KAYNAK[i:j if j > 0 else len(KAYNAK)]


def _g1_ayar_govdesi() -> str:
    i = KAYNAK.find('_g1_ayar_pub.publish')
    assert i > 0
    return KAYNAK[max(0, i - 1800):i + 400]


def test_BACKEND_SLOTU_OKUYOR():
    """🔴 Asil istek: parameters_json'daki takim_slot ise yaramali."""
    g = _g1_ayar_govdesi()
    assert '"takim_slot"' in g, 'backend takim_slot alanini okumuyor'


def test_BACKEND_SLOTU_YAYINLIYOR():
    """Okuyup yayinlamazsa hicbir sey degismez — 4. eleman olmali."""
    g = _g1_ayar_govdesi()
    assert 'float(slot)' in g, 'slot g1_ayar dizisine konmuyor'


def test_BOS_BIRAKMAK_GECERLI():
    """Slot verilmezse 0 gider ve ucak KENDI slotunu korur."""
    g = _g1_ayar_govdesi()
    assert 'slot = 0' in g, 'varsayilan 0 degil — bos birakinca ne gidecegi belirsiz'


def test_YKI_FORMUNDA_ALAN_VAR():
    """Operatorun gorev aninda yazacagi yer; olmazsa zincir kopuk."""
    assert 'Takım slotu' in PANEL
    assert 'g1Slot' in PANEL


def test_FORM_SIFIRI_GONDERMIYOR():
    """0/bos JSON'a KONMAMALI — 'belirtilmedi' anlamini bozar."""
    i = PANEL.find('p.takim_slot')
    assert i > 0
    onceki = PANEL[max(0, i - 200):i]
    assert 'gs > 0' in onceki, 'sifir da gonderiliyor'


def test_GEREKCE_KODDA():
    """Nicin oldugunu bilmeyen biri bu alani 'gereksiz' diye silebilir."""
    assert 'SSH' in PANEL or 'mesh' in PANEL
