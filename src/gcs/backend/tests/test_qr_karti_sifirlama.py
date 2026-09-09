# Copyright 2026 Yelpence
"""Yeni gorev BASLARKEN "cozulen QR" karti sifirlanir.

🔴 8 EYLUL 2026, operator: "gorev baslattigimda YKI'deki qr2 cozuldu
isareti sifirlansin, kafami karistiriyor."

NIYE KALICIYDI: `_on_qr_data` yalnizca `decoded=True` kareleri sakliyor
ve son gecerli QR'i EZDIRMIYOR — sartname V2'ye gore cozulen QR gorev
BOYUNCA ekranda kalmali (yoksa -20 puan). O kural DOGRU.

KUSUR: kalicilik GOREVLER ARASINDA da suruyordu. Yeni goreve baslarken
bir onceki ucusun QR'i ekranda duruyordu; operator "bu simdi mi okundu,
once mi?" diye ayirt edemedi. Sahada tam bu soru soruldu ve cevabi ancak
ucak loglarini kazarak (goru.log zaman damgalari) verilebildi.

COZUM: yalnizca COMMAND_START'ta silinir. ABORT/PAUSE/RTL/LAND'de kart
DURUR — o an gorev suruyordur ve sartname ekranda kalmasini ister.
"""

import pathlib

KAYNAK = (pathlib.Path(__file__).resolve().parents[3] / 'gcs' / 'backend'
          / 'connections' / 'ros_bridge.py').read_text()


def _govde(ad: str) -> str:
    i = KAYNAK.find(f'    def {ad}(')
    assert i > 0, f'{ad} bulunamadi'
    j = KAYNAK.find('\n    def ', i + 1)
    return KAYNAK[i:j if j > 0 else len(KAYNAK)]


def test_BASLATTA_SIFIRLANIYOR():
    """🔴 Asil istek: BASLAT komutunda kart temizlenmeli."""
    assert 'self.latest_qr = None' in _govde('trigger_mission'), (
        'gorev baslatilirken cozulen QR karti sifirlanmiyor'
    )


def test_SIFIRLAMA_YALNIZ_BASLATTA():
    """ABORT/PAUSE/RTL/LAND'de kart DURMALI (sartname V2: -20)."""
    g = _govde('trigger_mission')
    onceki = g[:g.find('self.latest_qr = None')]
    assert 'if int(command) == _COMMAND_START:' in onceki, (
        'sifirlama BASLAT kosuluna bagli degil — iptalde de silerdi'
    )


def test_KILIT_ALTINDA():
    """`latest_qr`'a _qr_lock olmadan dokunmak yaris kosulu demek."""
    g = _govde('trigger_mission')
    i = g.find('self.latest_qr = None')
    assert 'with self._qr_lock:' in g[max(0, i - 200):i]


def test_GOREV_BOYUNCA_KALICILIK_KORUNDU():
    """`_on_qr_data` hala cozulmemis kareyi ATLAMALI — o kural dogruydu."""
    g = _govde('_on_qr_data')
    assert 'if not msg.decoded:' in g


def test_GORUNURLUK():
    """Sessiz silme olmasin: log satiri bulunmali."""
    assert 'sifirlandi' in _govde('trigger_mission')
