# Copyright 2026 Yelpence
"""AgentSetpoint hiz/ivme tavanlari px4_bridge'de BAGLI DEGILDI.

`AgentSetpoint.msg:68-73` acikca soyluyor:
    "Speed and acceleration limits for px4_interface TrajectorySetpoint
     computation. 0.0 means 'use px4_interface default / no override'."

Dort dugum bu alanlari DOLDURUYOR (collision_avoidance, maneuver_executor,
formation_node) ama px4_bridge HICBIRINI okumuyordu — yani formasyon
"3 m/s'i gecme" dediginde de kimse dinlemiyordu.

22 Agustos'ta baglandi. Bu testler sozlesmeyi kilitliyor:
  * 0.0 -> hicbir sey degismez (kanitlanmis guided yol korunur)
  * tavan yalniz DUSURULEBILIR, artirilamaz
  * ivme tavani tepe hizi da dusurur (v_tepe = sqrt(a*d))
"""

import math


def _profil(mesafe, hiz_par, ivme_par, sp_hiz=0.0, sp_ivme=0.0, dt=0.02):
    """px4_bridge._yurutucu_ilerlet'in yatay profilini birebir taklit eder.

    Kaynak: px4_bridge.py `_yurutucu_ilerlet` — trapez hiz profili.
    Burada yeniden yazilmasinin sebebi: gercek fonksiyon ROS dugumune ve
    50 Hz zamanlayiciya bagli; profilin MATEMATIGI ayrica kilitlensin.
    """
    hiz_tavan = min(hiz_par, sp_hiz) if sp_hiz > 0.0 else hiz_par
    ivme = min(ivme_par, sp_ivme) if sp_ivme > 0.0 else ivme_par
    kalan = mesafe
    v = 0.0
    tepe = 0.0
    t = 0.0
    while kalan > 1e-3 and t < 60.0:
        v_fren = math.sqrt(2.0 * ivme * kalan)
        v_hedef = min(hiz_tavan, v_fren)
        v = (min(v_hedef, v + ivme * dt) if v < v_hedef
             else max(v_hedef, v - ivme * dt))
        kalan -= v * dt
        tepe = max(tepe, v)
        t += dt
    return tepe, t


def test_SIFIR_tavan_hicbir_sey_degistirmez():
    """Bugunku guided setpoint'ler max_speed/max_acc = 0.0 gonderiyor.
    Kanitlanmis yol BIREBIR ayni kalmali."""
    a = _profil(3.9, 3.0, 1.5)
    b = _profil(3.9, 3.0, 1.5, sp_hiz=0.0, sp_ivme=0.0)
    assert a == b


def test_olculen_donus_tepesi_dogrulanir():
    """21 Agustos ucusunda 3.9 m donuste 2.27 m/s olculdu.
    Ucgen profil tepesi v=sqrt(a*d)=sqrt(1.5*3.9)=2.42; olcum bunun
    altinda kalmali (telemetri ornekleme + ruzgar)."""
    tepe, _ = _profil(3.9, 3.0, 1.5)
    assert 2.2 <= tepe <= 2.5, f'profil tepesi beklenenden uzak: {tepe:.2f}'


def test_IVME_tavani_tepe_hizi_DUSURUR():
    """Operator onerisi: hiz tavani yerine IVME kis — profil dogal kalir."""
    tepe_normal, sure_normal = _profil(3.9, 3.0, 1.5)
    tepe_yavas, sure_yavas = _profil(3.9, 3.0, 1.5, sp_ivme=0.5)
    assert tepe_yavas < tepe_normal * 0.65, (
        f'ivme tavani tepeyi dusurmedi: {tepe_normal:.2f} -> {tepe_yavas:.2f}')
    assert sure_yavas > sure_normal, 'yavas ivme daha kisa surdu (imkansiz)'
    assert 1.2 <= tepe_yavas <= 1.6, f'0.5 m/s2 tepesi: {tepe_yavas:.2f}'


def test_HIZ_tavani_da_calisir():
    tepe, _ = _profil(20.0, 3.0, 1.5, sp_hiz=1.0)
    assert tepe <= 1.01, f'hiz tavani asildi: {tepe:.2f}'


def test_tavan_ARTIRAMAZ_yalniz_dusurur():
    """Guvenlik: bir dugum yanlislikla buyuk deger gonderirse ucak
    parametre tavanindan hizli gitmemeli."""
    tepe_h, _ = _profil(50.0, 3.0, 1.5, sp_hiz=99.0)
    assert tepe_h <= 3.01, f'setpoint hiz tavani ASTIRDI: {tepe_h:.2f}'
    tepe_i, _ = _profil(3.9, 3.0, 1.5, sp_ivme=99.0)
    tepe_ref, _ = _profil(3.9, 3.0, 1.5)
    assert abs(tepe_i - tepe_ref) < 1e-6, 'setpoint ivme tavani ASTIRDI'


def test_kod_gercekten_bagli():
    """Yukaridaki matematik TAKLIT; asil kodun alanlari OKUDUGUNU dogrula.

    px4_bridge ROS'suz import EDILEMIYOR (rcl_interfaces), o yuzden kaynak
    dosyadan okunuyor. Kaba ama dogru soruyu soruyor: bu iki alan
    yurutucunun icinde geciyor mu? Gecmezse tavanlar bagli degildir ve
    yukaridaki testler bos yere gecer.
    """
    import os
    import re
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'px4_interface', 'px4_bridge.py')
    with open(yol, encoding='utf-8') as f:
        tam = f.read()
    m = re.search(r'def _yurutucu_ilerlet.*?\n    def ', tam, re.S)
    assert m, '_yurutucu_ilerlet bulunamadi'
    govde = m.group(0)
    assert 'max_speed_mps' in govde, 'px4_bridge max_speed_mps OKUMUYOR'
    assert 'max_acc_mps2' in govde, 'px4_bridge max_acc_mps2 OKUMUYOR'
    assert 'min(self._hiz_yatay' in govde, 'hiz tavani min() ile alinmiyor'
    assert 'min(self._ivme_yatay' in govde, 'ivme tavani min() ile alinmiyor'
