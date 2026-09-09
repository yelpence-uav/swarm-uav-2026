# Copyright 2026 Yelpence
"""Kamerayla okunan QR'da `team_id` DOLU olmali — yoksa sessizce atilir.

🔴 8 EYLUL 2026, SAHADA OLCULDU. Gorev 1'in ilk KAMERALI ucusu.

ylp00 QR1'i gercekten okudu — goru.log kanit:
    1788870990.3  [KARAR-21] QR ayrilma istedi (ajan=3 renk=2) — PAS GECILDI
    1788870990.9  (ayni satir, tekrar)
    1788870991.5  ...
Ama ayni anda mission_fsm.log'da:
    "QR kabul edildi" sayisi = 0

ZINCIR
    QR'in JSON icerigi team_id TASIMIYOR — sartname `team` tablosunu takim
    SLOTU ile anahtarliyor ({"team":{"1":[paket,sonraki], ...}}).
      -> qr_detector._parse_qr_text parsed['team_id']'i HIC doldurmuyor
      -> _blank_result varsayilani: ''
      -> vision_node: msg.team_id = ''
      -> mission_fsm._on_qr_data:
             elif msg.team_id != self._ctx.team_id: return
         '' != '752825'  ->  SESSIZCE ATILDI

Hicbir yerde hata gorunmuyordu. Enjeksiyon CALISIYORDU cunku
qr_enjekte.py alani elle yaziyor (m.team_id = a.takim) — yani kusur tam
olarak "gercek kamerayla test edilene kadar gizli kalan" cinsten.

COZUM: vision_node kendi `team_id` parametresini geri dusus olarak
kullanir; deger baslat.sh'ten TAKIM_ID ile gelir, yani mission_fsm ve
mission1_node ile AYNI kaynak.
"""

import json
import sys
from unittest.mock import MagicMock

sys.modules.setdefault('pyzbar', MagicMock())
sys.modules.setdefault('pyzbar.pyzbar', MagicMock())

from swarm_perception.vision_node.qr_detector import QRDetector  # noqa: E402

SAHA_QR = ('{"qr":1,"w":4,"mis":[[["leav",3,"b"]],[["frm","ok",6],'
           '["mnv",-5,10],["alt",28]],[["frm","l",6],["mnv",-5,-10],'
           '["alt",20]]],"team":{"1":[1,2],"2":[2,4],"3":[3,5],'
           '"4":[3,3],"5":[2,4]}}')


# ------------------------------------------------------------ kok neden

def test_QR_ICERIGI_TEAM_ID_TASIMIYOR():
    """Kok neden: sartname QR'inda team_id alani YOK — slot tablosu var."""
    d = json.loads(SAHA_QR)
    assert 'team_id' not in d
    assert 'team' in d and set(d['team']) == {'1', '2', '3', '4', '5'}


def test_COZUCU_TEAM_ID_BIRAKMAZ_BOS():
    """Cozucu bu alani dolduramaz (bilgi QR'da yok) — bos donmeli.

    Bu testin amaci cozucuyu suclamak DEGIL: bosluğun NEREDE olustugunu
    kayda gecirmek. Doldurma isi dugumun (vision_node), cunku takim
    kimligi bir DUGUM AYARI, QR icerigi degil.
    """
    p = QRDetector(team_slot=1)._parse_qr_text(SAHA_QR)
    assert p['valid'] is True          # QR'in kendisi gecerli
    assert p['team_id'] == ''          # ama kimlik bos


# ------------------------------------------------------------- sonucu

def test_BOS_TEAM_ID_MISSION_FSM_KAPISINDAN_GECEMEZ():
    """Sessiz atilmanin ta kendisi: bos kimlik esitlik testinde duser."""
    ctx_team_id = '752825'
    msg_team_id = ''                                  # sahada boyleydi
    assert msg_team_id != ctx_team_id                 # -> return (sessiz)


# --------------------------------------------------------------- cozum

def test_VISION_NODE_GERI_DUSUSU_VAR():
    """Duzeltme kaynakta duruyor: cozucu bos birakirsa dugum kendi
    kimligini yazar.

    Kaynaktan okumak kirilgan ama alternatifi (tam ROS dugum kurulumu)
    bu kusurun tekrarini yakalamak icin orantisiz — ayni yaklasim
    test_landed_idle_donusu.py'de de kullanildi.
    """
    # ROS modulleri laptopta yok; iceri aktarmak yerine kaynagi DOSYADAN
    # okuyoruz — sinanan sey zaten kaynagin kendisi.
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[3]
    kaynak = (kok / 'src' / 'swarm_perception' / 'swarm_perception'
              / 'vision_node' / 'vision_node_core.py').read_text()
    assert "msg.team_id = res.get('team_id') or self._team_id" in kaynak, (
        'vision_node team_id geri dususu YOK — kamerayla okunan QR '
        'mission_fsm kapisinda sessizce atilir (8 Eylul sahada olculdu)'
    )
    assert "self.declare_parameter('team_id'" in kaynak, (
        'vision_node team_id parametresi bildirilmemis'
    )


def test_BASLAT_SH_TEAM_ID_GECIYOR():
    """Parametre bildirmek yetmez — baslat.sh onu GECMELI, yoksa
    varsayilan kalir ve TAKIM_ID degisirse ayrisir."""
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[3]
    bs = (kok / 'deploy' / 'rpi' / 'baslat.sh').read_text()
    i = bs.find('vision_node --ros-args')
    assert i > 0, 'baslat.sh icinde vision_node baslatma satiri yok'
    assert 'team_id' in bs[i:i + 250], (
        'baslat.sh vision_node a team_id GECMIYOR'
    )
