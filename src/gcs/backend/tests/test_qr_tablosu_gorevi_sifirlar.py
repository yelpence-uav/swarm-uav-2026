# Copyright 2026 Yelpence
"""QR TABLOSU YAYINI, BEKLEYEN GOREV EMRINI DUSURUR.

🔴 8 EYLUL 2026, SAHADA YASANDI — kimse komut vermeden bir ucak kalkti.

    22:25:03  operator YANLISLIKLA "gorev baslat" dedi
              ylp02'nin QR tablosu YOKTU (Pi yeniden baslamisti)
              -> mission_fsm PREFLIGHT'ta bekledi:
                 "QR KONUM TABLOSU YOK — Suru KALKMAYACAK"
              -> ama emir IPTAL OLMADI, ASILI KALDI
    22:27:38  operator QR tablosunu gonderdi
              -> PREFLIGHT kapisi acildi
              -> 🔴 ylp02 KENDI KENDINE KALKTI

Yani QR tablosu yayini, farkinda olmadan bir KALKIS TETIKLEYICISIYDI.
Operatorun tablo gondermesi ile "kalkis" arasinda hicbir zihinsel bag
yok; bu yuzden bu, hata vermeden yanlis sonuc ureten sinifin en
tehlikelisi — sonucu havada.

COZUM: tablo basilmadan ONCE gorev DURDUR yayinlanir. Bekleyen emir
varsa dusar; yoksa DURDUR zaten IDLE/ABORTED'da yok sayilir, yani
maliyeti sifirdir.

NEDEN UCAN SURUYU RISKE ATMAZ: mission_fsm'in DURDUR yolu ucan suruyu
INDIRMIYOR (kodda acikca yazili) — yalniz kalkis yetkisini geri aliyor.
"""

import pathlib

KAYNAK = (pathlib.Path(__file__).resolve().parents[3] / 'gcs' / 'backend'
          / 'connections' / 'ros_bridge.py').read_text()


def _govde(ad: str) -> str:
    i = KAYNAK.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = KAYNAK.find('\n    def ', i + 1)
    return KAYNAK[i:j if j > 0 else len(KAYNAK)]


# ------------------------------------------------------------ asil kusur

def test_TABLO_ONCESI_DURDUR_YAYINLANIYOR():
    """🔴 Kusurun ta kendisi: asili emir tablo gelince kalkis yapiyordu."""
    g = _govde('publish_qr_coords')
    assert 'self.publish_gorev1_baslat(False)' in g, (
        'QR tablosu basilmadan once gorev DURDUR yayinlanmiyor — bekleyen '
        'baslatma emri tablo gelir gelmez kalkisa donusur (8 Eylul, ylp02)'
    )


def test_DURDUR_TABLODAN_ONCE():
    """Sira onemli: once DURDUR, sonra tablo. Tersi ayni tuzagi birakir."""
    g = _govde('publish_qr_coords')
    i_dur = g.find('self.publish_gorev1_baslat(False)')
    i_yay = g.find('self._qr_coords_pub.publish(')
    assert 0 < i_dur < i_yay, (
        'DURDUR tablodan SONRA gonderiliyor — arada kalan pencerede '
        'ucak kalkabilir'
    )


def test_DURDUR_BASLAT_DEGIL():
    """Yanlislikla True yazilirsa tablo yayini KALKIS EMRI olur."""
    g = _govde('publish_qr_coords')
    assert 'self.publish_gorev1_baslat(True)' not in g


# ------------------------------------------------------- yan etkiler

def test_COZULEN_QR_KARTI_DA_SIFIRLANIYOR():
    """Yeni tablo = yeni kurulum; ekranda onceki ucusun QR'i kalmamali."""
    g = _govde('publish_qr_coords')
    assert 'self.latest_qr = None' in g


def test_KART_SIFIRLAMA_KILIT_ALTINDA():
    """`latest_qr` baska bir is parcaciginda yaziliyor — kilitsiz dokunma."""
    g = _govde('publish_qr_coords')
    i = g.find('self.latest_qr = None')
    assert 'with self._qr_lock:' in g[max(0, i - 200):i]


def test_BASLAT_YOLU_BOZULMADI():
    """trigger_mission hala BASLAT'ta karti sifirliyor (onceki karar)."""
    g = _govde('trigger_mission')
    assert 'self.latest_qr = None' in g


def test_GEREKCE_KODDA_DURUYOR():
    """Nicin oldugunu bilmeyen biri bunu 'gereksiz' diye silebilir."""
    g = _govde('publish_qr_coords')
    assert 'KENDI KENDINE' in g and '8 EYLUL' in g.upper()
