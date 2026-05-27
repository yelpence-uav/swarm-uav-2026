"""test_ema.py — _EmaDurum sınıfı birim testleri.

EMA matematiği basit; testin amacı:
- İlk ölçümde "warm start" yaparak ham değeri kullanmak
- Sonraki güncellemelerde sönümlü ortalama almak
- Konum ve hız için ayrı alpha kullanmak
- Spike (ani sıçrama) etkisini sınırlamak
- NaN/Inf ölçümleri reddetmek, filtreyi kirletmemek
- sifirla() çağrısında warm start durumuna dönmek
"""

import math

from swarm_interfaces.msg import AgentStatus

from swarm_perception.kinematic_fusion.kinematic_fusion_node import (
    _EmaDurum,
    _makul_aralikta,
    _sayisal_gecerli,
)


def _yapay_status(pos_x: float, vel_x: float) -> AgentStatus:
    """Tek bir eksende konum/hız taşıyan yapay AgentStatus üretir."""
    s = AgentStatus()
    s.pos_x = pos_x
    s.vel_x = vel_x
    return s


def test_warm_start_ilk_olcum():
    """İlk update'te EMA henüz tahmin yok; ham değer aynen alınmalı."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    assert f.x == 10.0
    assert f.vx == 1.0


def test_konum_sonumleme():
    """İkinci ölçümde EMA formülü uygulanmalı (konum, alpha=0.3)."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=0.0))
    f.guncelle(_yapay_status(pos_x=20.0, vel_x=0.0))
    # 0.3 * 20 + 0.7 * 10 = 13
    assert abs(f.x - 13.0) < 1e-6


def test_hiz_sonumleme():
    """Hız için ayrı alpha (0.5) doğru uygulanmalı."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=0.0, vel_x=2.0))
    f.guncelle(_yapay_status(pos_x=0.0, vel_x=4.0))
    # 0.5 * 4 + 0.5 * 2 = 3
    assert abs(f.vx - 3.0) < 1e-6


def test_spike_etkisi_sinirli():
    """Ani sıçrayan değer EMA tarafından büyük ölçüde sönümlenmeli."""
    f = _EmaDurum(alpha_pos=0.2, alpha_vel=0.5)
    # 10 adım dengeli 10.0
    for _ in range(10):
        f.guncelle(_yapay_status(pos_x=10.0, vel_x=0.0))
    assert abs(f.x - 10.0) < 1e-6
    # Bir spike: 50.0
    f.guncelle(_yapay_status(pos_x=50.0, vel_x=0.0))
    # 0.2 * 50 + 0.8 * 10 = 18  (50 değil, sönümlendi)
    assert 17.0 < f.x < 19.0


def test_yakinsama_sabit_olcume():
    """Sabit ölçüm akarsa EMA o değere yakınsamalı."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    for _ in range(50):
        f.guncelle(_yapay_status(pos_x=42.0, vel_x=7.0))
    assert abs(f.x - 42.0) < 0.01
    assert abs(f.vx - 7.0) < 0.01


def test_nan_olcum_reddedilir():
    """NaN içeren ölçüm filtreyi kirletmemeli (geçmiş korunmalı)."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    onceki_x = f.x
    bozuk = _yapay_status(pos_x=float('nan'), vel_x=1.0)
    sonuc = f.guncelle(bozuk)
    assert sonuc is False
    assert f.x == onceki_x  # filtre dokunulmadı
    assert f.son_olcum_gecerli is False


def test_inf_olcum_reddedilir():
    """Inf içeren ölçüm de reddedilmeli."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    onceki_x = f.x
    bozuk = _yapay_status(pos_x=float('inf'), vel_x=1.0)
    assert f.guncelle(bozuk) is False
    assert f.x == onceki_x


def test_sifirla_warm_start_geri_doner():
    """sifirla() çağrısı tüm tahminleri None'a çekmeli."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    assert f.hazir()
    f.sifirla()
    assert not f.hazir()
    assert f.x is None and f.vx is None


def test_hazir_yari_warm_durumda_false():
    """Filtre henüz warm değilse hazir() False döner."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    assert not f.hazir()
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    assert f.hazir()


def test_sayisal_gecerli_yardimci():
    """_sayisal_gecerli NaN, Inf, normal sayıları doğru ayırmalı."""
    assert _sayisal_gecerli(0.0, 1.0, -2.5) is True
    assert _sayisal_gecerli(float('nan')) is False
    assert _sayisal_gecerli(float('inf')) is False
    assert _sayisal_gecerli(float('-inf')) is False
    assert _sayisal_gecerli(1.0, float('nan'), 2.0) is False
    # math'in NaN sabiti de kabul edilmeli
    assert _sayisal_gecerli(math.nan) is False


def test_makul_aralikta_normal_degerler():
    """Normal sürü değerleri makul aralıkta kabul edilmeli."""
    assert _makul_aralikta(
        pos_x=10.0, pos_y=-5.0, pos_z=20.0,
        vel_x=1.0, vel_y=0.5, vel_z=-0.2,
    ) is True


def test_makul_aralikta_konum_disi():
    """100 km'den uzak konum reddedilmeli (sensör glitch'i)."""
    assert _makul_aralikta(
        pos_x=200_000.0, pos_y=0.0, pos_z=0.0,
        vel_x=0.0, vel_y=0.0, vel_z=0.0,
    ) is False


def test_makul_aralikta_hiz_disi():
    """200 m/s üstü hız reddedilmeli (uçak değil, drone)."""
    assert _makul_aralikta(
        pos_x=0.0, pos_y=0.0, pos_z=0.0,
        vel_x=500.0, vel_y=0.0, vel_z=0.0,
    ) is False


def test_sinir_disi_olcum_filtreye_yansimaz():
    """Saçma değer EMA filtresini kirletmemeli."""
    f = _EmaDurum(alpha_pos=0.3, alpha_vel=0.5)
    f.guncelle(_yapay_status(pos_x=10.0, vel_x=1.0))
    onceki_x = f.x
    # 1 milyar metre saçmalığı
    sacma = _yapay_status(pos_x=1e9, vel_x=1.0)
    assert f.guncelle(sacma) is False
    assert f.x == onceki_x
