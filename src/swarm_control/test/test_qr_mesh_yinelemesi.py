# Copyright 2026 Yelpence
"""QR gorevi mesh'e BIR KEZ cikar — ayni icerik tekrar tekrar basilmaz.

4 EYLUL 2026, ylp02, gercek ucus:

    tek QR'dan dusen okuma      36    (hepsinde qr_id=2, qr_seq=1)
    mesh'e giden cerceve        36    (yineleme suzgeci YOKTU)

`vision_node` QR mesajini COZULEN HER KAREDE yayinliyor (`for res in
results`). 3 Hz'de bir QR'in uzerinde 20 saniye asili kalmak ~60 ozdes
cerceve demek. Icerik ayni oldugu icin YKI bunlardan YENI HICBIR SEY
ogrenmiyor; mesh ise o sure boyunca dolu.

Kapi iki yonden birden kilitleniyor, cunku iki yonde de bedel var:
  * ayni icerik SUSTURULMALI   -> yoksa mesh isgal edilir
  * yeni icerik GECMELI        -> yoksa QR kacirilir, bu puan kaybidir

Ayrica "tam olarak tek sefer" BILEREK yapilmadi: ESP-NOW teslimat garantisi
vermiyor, tek cerceve kaybolursa YKI o QR'i hic ogrenemez. Uc cerceve
36'nin yaninda ihmal edilebilir ama kayba karsi uc sans demek.
"""

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.esp32_bridge_node import (
    Esp32BridgeNode,
    _QR_TEKRAR,
    _QR_TEKRAR_ARALIK_S,
)


class _Mesaj:
    """QRMissionData yerine gecen kabuk.

    conftest swarm_interfaces'i taklit ettigi icin gercek mesaj kurulamiyor.
    """

    def __init__(self, **kw):
        self.team_id = ''
        self.qr_id = 2
        self.qr_seq = 1
        self.next_qr = 3
        self.valid = True
        self.decoded = True
        self.formation_active = True
        self.maneuver_active = False
        self.altitude_active = False
        self.detach_active = False
        self.complete_mission = False
        self.formation_type = 1
        self.spacing_m = 6.0
        self.pitch_deg = 0.0
        self.roll_deg = 0.0
        self.yaw_deg = 0.0
        self.altitude_agl_m = 18.0
        self.wait_s = 0.0
        self.target_agent_id = 0
        self.detach_color = 0
        self.detach_wait_s = 0.0
        self.error_message = ''
        self.raw_text = '{"qr":2}'
        self.__dict__.update(kw)


class _Kayitci:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass


def _dugum():
    """Esp32BridgeNode'u __init__ CAGIRMADAN kurar (conftest deseni)."""
    d = object.__new__(Esp32BridgeNode)
    d._takim_id = '752825'
    d._agent_id = 3
    d._qr_son_payload = None
    d._qr_kalan_tekrar = 0
    d._qr_son_gonderim = 0.0
    d._qr_bastirilan = 0
    d._qr_gorev_gonderilen = 0
    d.gonderilen = []
    d._uart_yaz = lambda tip, aid, yuk: d.gonderilen.append((tip, yuk))
    d.get_logger = _Kayitci
    return d


def _zamani_ilerlet(d):
    """Tekrar araligini gecmis say — saat beklemeden."""
    d._qr_son_gonderim -= (_QR_TEKRAR_ARALIK_S + 0.1)


def test_ayni_icerik_SUSTURULUYOR():
    """36 okuma -> mesh'e _QR_TEKRAR cerceve. Asil duzeltme bu."""
    d = _dugum()
    for _ in range(36):
        d._on_qr_data_out(_Mesaj())
        _zamani_ilerlet(d)          # sure kapisi degil, TEKRAR HAKKI sinirlasin
    assert len(d.gonderilen) == _QR_TEKRAR
    assert d._qr_gorev_gonderilen == _QR_TEKRAR
    assert d._qr_bastirilan == 36 - _QR_TEKRAR


def test_ilk_okuma_HEMEN_gidiyor():
    """Gecikme yok: QR gorulur gorulmez ilk cerceve cikar."""
    d = _dugum()
    d._on_qr_data_out(_Mesaj())
    assert len(d.gonderilen) == 1
    assert d.gonderilen[0][0] == pp.TIP_QR_GOREV


def test_tekrarlar_ARALIKLA_gidiyor():
    """Ayni icerik pes pese gelirse ikinci cerceve HEMEN cikmaz."""
    d = _dugum()
    d._on_qr_data_out(_Mesaj())
    d._on_qr_data_out(_Mesaj())     # zaman ilerlemedi
    assert len(d.gonderilen) == 1
    _zamani_ilerlet(d)
    d._on_qr_data_out(_Mesaj())
    assert len(d.gonderilen) == 2


def test_YENI_QR_gecer():
    """En kritik yon: yeni icerik susturulursa QR kacirilir = puan kaybi."""
    d = _dugum()
    for _ in range(10):             # ilk QR'i tekrar hakkini tuketene kadar bas
        d._on_qr_data_out(_Mesaj(qr_id=2))
        _zamani_ilerlet(d)
    once = len(d.gonderilen)
    d._on_qr_data_out(_Mesaj(qr_id=5, next_qr=6))
    assert len(d.gonderilen) == once + 1, 'yeni QR mesh e CIKMADI'


def test_ayni_QR_ID_farkli_ICERIK_gecer():
    """Anahtar qr_id degil PAYLOAD: ayni QR'in cozumu degistiyse haber ver."""
    d = _dugum()
    for _ in range(10):
        d._on_qr_data_out(_Mesaj(spacing_m=6.0))
        _zamani_ilerlet(d)
    once = len(d.gonderilen)
    d._on_qr_data_out(_Mesaj(spacing_m=9.0))
    assert len(d.gonderilen) == once + 1


def test_ONCEKI_QR_geri_gelirse_yeniden_gonderilir():
    """Onceki QR geri gelirse yeniden gonderilir.

    QR1 -> QR2 -> QR1 dizisinde son QR1 susturulmamali; her an gecerli olan
    komut EN SON okunandir.
    """
    d = _dugum()
    d._on_qr_data_out(_Mesaj(qr_id=2))
    d._on_qr_data_out(_Mesaj(qr_id=5))
    n = len(d.gonderilen)
    d._on_qr_data_out(_Mesaj(qr_id=2))
    assert len(d.gonderilen) == n + 1


def test_BASKA_TAKIM_QR_i_mesh_e_CIKMAZ():
    """KARAR 7 kapisi yineleme kapisindan ONCE gelmeli."""
    d = _dugum()
    d._on_qr_data_out(_Mesaj(team_id='999999'))
    assert d.gonderilen == []
    assert d._qr_son_payload is None, 'reddedilen QR yineleme durumunu kirletti'
