# Copyright 2026 Yelpence
"""BASLAT yok sayildiysa SEBEBI YAZILIR — sessiz ret yok.

🔴 8 EYLUL 2026, SAHADA.

ylp02 asili kalmis bir emir yuzunden kendi kendine kalkti, operator onu
indirdi, sonra uc ucaga birden BASLAT verdi:

    ylp00  kalkti
    ylp01  kalkti
    ylp02  KALKMADI — ve hicbir yerde sebep yazmadi

Sebep: `_on_gorev1_tetik` yalniz IDLE'dan tetikliyor. ylp02 daha once
inmis oldugu icin terminal durumdaydi; oradan IDLE'a donus "yerde +
3 sn oturma" istiyor. O pencerede gelen BASLAT sessizce dusuruldu.

Karar dogru (IDLE disindan baslatmak tehlikeli), EKSIK OLAN SESTI.
Bu dosya sesin kalmasini kilitliyor.
"""

import inspect

from swarm_state_machine.mission_fsm import mission_fsm_node


def _govde(ad):
    kaynak = inspect.getsource(mission_fsm_node)
    i = kaynak.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = kaynak.find('\n    def ', i + 1)
    return kaynak[i:j if j > 0 else len(kaynak)]


def test_IDLE_DISINDA_UYARI_VERIYOR():
    """🔴 Kusurun ta kendisi: eskiden yalniz `return` vardi."""
    g = _govde('_on_gorev1_tetik')
    i = g.find('if ctx.state != MissionState.IDLE:')
    assert i > 0, 'IDLE kapisi kaybolmus'
    blok = g[i:i + 1200]
    assert 'get_logger' in blok, (
        'IDLE disindan gelen BASLAT sessizce dusuruluyor — operator '
        '"neden kalkmadi" sorusunu kod okuyarak cevaplamak zorunda kalir'
    )


def test_UYARI_DURUMU_SOYLUYOR():
    """Hangi durumda oldugunu yazmayan uyari, olmayan uyaridir."""
    g = _govde('_on_gorev1_tetik')
    i = g.find('if ctx.state != MissionState.IDLE:')
    blok = g[i:i + 1200]
    assert 'ctx.state.name' in blok


def test_KAPI_HALA_DURUYOR():
    """Ses eklendi diye kapi acilmamali: IDLE disindan BASLAMAZ."""
    g = _govde('_on_gorev1_tetik')
    i = g.find('if ctx.state != MissionState.IDLE:')
    blok = g[i:i + 1400]
    assert 'return' in blok, 'IDLE disindan baslatma engeli kaldirilmis'


def test_UYARI_BOGMUYOR():
    """Yayin surekli akiyor; throttle olmazsa log kullanilamaz hale gelir."""
    g = _govde('_on_gorev1_tetik')
    i = g.find('if ctx.state != MissionState.IDLE:')
    assert 'throttle_duration_sec' in g[i:i + 1200]
