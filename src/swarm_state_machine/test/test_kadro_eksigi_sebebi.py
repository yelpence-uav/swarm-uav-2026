# Copyright 2026 Yelpence
"""KADRO eksilince SEBEBI yazilir — "muhtemelen mesh" ile yetinilmez.

🔴 8 EYLUL 2026, 22:49. Liderin logunda:

    KADRO SIFIRLANDI (aktif ajan listesi BOS) — ... 275. kez oluyor;
    sebebi ayrica aranmali (saglik bayragi? bayatlama? mesh?)

Kodun kendisi soruyu soruyor ama cevabi hicbir yerde yok. `active_agent_ids`
DORT sarta bagli (healthy / origin_synced / bayatlik / FORMATION_ACTIVE
durumu) ve dordu de mesh DURUM paketinden besleniyor. Hangisi patladigi
yazilmadigi icin teshis "muhtemelen paket kaybi"nda kaliyor.

Sonucu hafif degil: kadro cokunce formasyon komutu YALNIZ LIDERI
adresliyor, takipciler donuyor ve hicbir yerde hata gorunmuyor —
operatorun "sadece lider irtifa degistirdi" dedigi olay.

Bu dosya, eksilme aninda ucak basina sebep yazilmasini kilitler.

⚠️ Log cagrisi rclpy bicimindedir: TEK metin + throttle. printf ('%s' +
arg) bicimi RcutilsLogger'da TypeError atar — 8 Eylul 22:41'de tam bunu
yapip mission_fsm'i cokerttik ve iki ucak kalkamadi.
"""

import inspect

from swarm_state_machine.swarm_fsm import swarm_fsm_node


def _kaynak():
    return inspect.getsource(swarm_fsm_node)


def _blok():
    k = _kaynak()
    i = k.find('m.active_agent_ids = [a.agent_id for a in active_agents]')
    assert i > 0, 'active_agent_ids atamasi bulunamadi'
    return k[i:i + 2600]


def test_EKSILME_LOGLANIYOR():
    """🔴 Asil eksik: eksilme sessizdi."""
    assert 'KADRO EKSIK' in _blok(), (
        'kadro eksildiginde sebep yazilmiyor — teshis yine tahmine kalir'
    )


def test_DORT_SART_DA_AYIRT_EDILIYOR():
    """Dordunden hangisi patladigi ayri ayri yazilmali."""
    b = _blok()
    for anahtar in ('healthy', 'origin_synced', 'BAYAT', 'durum='):
        assert anahtar in b, f'{anahtar} sebebi ayirt edilmiyor'


def test_UCAK_KIMLIGI_YAZILIYOR():
    """Hangi ucak dustugunu soylemeyen log ise yaramaz."""
    assert 'a.agent_id' in _blok()


def test_BAYATLIK_YASI_SAYIYLA():
    """'bayat' demek yetmez; KAC SANIYE bayat oldugu mesh teshisi icin sart."""
    b = _blok()
    assert 'last_update' in b and '_yas' in b


def test_LOG_BOGMUYOR():
    """5 Hz'de her tick yazsa log kullanilamaz hale gelir."""
    assert 'throttle_duration_sec' in _blok()


def test_RCLPY_BICIMI_PRINTF_DEGIL():
    """🔴 8 Eylul 22:41: printf bicimi mission_fsm'i cokertti, iki ucak kalkamadi."""
    b = _blok()
    i = b.find('get_logger().warning')
    cagri = b[i:i + 400]
    assert "f'" in cagri or 'f"' in cagri, 'f-string kullanilmiyor'
    assert '%s' not in cagri and '%d' not in cagri, (
        'printf bicimi — RcutilsLogger TypeError atar ve dugum COKER'
    )
