# Copyright 2026 Yelpence
"""QR formasyon gecis hizi TEK KAYNAKTA ve gecise UYGULANIYOR.

🔴 8 EYLUL 2026, SAHADA OLCULDU. QR2 okununca suru yer dizilisinden
(CUSTOM, ~9 m ayrim) V'ye (6 m aralik) gecerken ucaklar birbirinin
slotuna dogru AYNI ANDA hareket etti ve ayrim 8 saniyede coktu:

    9.06 -> 6.84 -> 4.41 -> 2.70 m        en dar 3B: 2.69 m
    yatayda 0.59 m'ye kadar yaklastilar
    ayiran sey kacinmanin actigi 7.4 m DIKEY paydi (ylp01 2.98 m/s yukari)

Esikler: MIN_AYRIM 4.0 ASILDI · KACINMA_D0 3.0 ASILDI ·
KACINMA_HARD 2.0'a 0.69 m kalmisti.

IKI KUSUR VARDI, IKISI DE BURADA KILITLENIYOR:

  ① Gecis hizi orchestrator.py'de KODA GOMULUYDU (max_speed=1.0).
    CLAUDE.md §8 "hizlar baska hicbir yerde elle yazilmaz" diyor. Gomulu
    oldugu icin o gun YANLIS parametre (gorev_kurulum_hiz_mps) arandi ve
    onerildi — kural boyle bir zaman kaybini onlemek icin var.

  ② Deger 1.0'di; 0.5'e cekildi. Kacinma MESAFEYE gore tetiklendigi icin
    (3.0 m) yavaslamak tetigi erkene ALMAZ; kazanc esik sonrasi ASIMDA
    (hizin karesiyle): 0.31 m -> ~0.08 m, dip 2.69 -> ~2.90 m.

⚠️ BU AYAR RISKI KALDIRMAZ, yalnizca payi acar. Yapisal cozum gecisten
once dikey katmanlamadir.
"""

import pathlib

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    OrchestratorConfig,
)

KOK = pathlib.Path(__file__).resolve().parents[3]
ORK = (KOK / 'src' / 'swarm_missions' / 'swarm_missions'
       / 'mission1_dynamic_swarm' / 'orchestrator.py').read_text()


# ------------------------------------------------------- ① tek kaynak

def test_GECIS_HIZI_YAPILANDIRMADA():
    """Alan var ve varsayilani eski davranisla ayni (geriye uyum)."""
    assert OrchestratorConfig().qr_formasyon_gecis_hiz_mps == 1.0


def test_KODA_GOMULU_HIZ_KALMADI():
    """🔴 Kusurun ta kendisi: `max_speed=1.0` gomulu duruyordu."""
    assert 'max_speed=1.0,' not in ORK, (
        'QR gecis hizi hala koda gomulu — §8 tek kaynak kurali'
    )


def test_GECIS_KOMUTU_AYARDAN_BESLENIYOR():
    assert 'max_speed=float(self._cfg.qr_formasyon_gecis_hiz_mps)' in ORK


def test_UCUS_AYARLARINDA_TANIMLI():
    """Tek kaynak dosyasinda olmali, yoksa 'baska yerde' demektir."""
    ua = (KOK / 'src' / 'gcs' / 'ucus_ayarlari.py').read_text()
    assert 'GOREV_QR_FORMASYON_GECIS_HIZ_MPS' in ua
    assert 'GOREV_QR_FORMASYON_GECIS_HIZ=' in ua      # --kabuk ciktisi


def test_BASLAT_SH_PARAMETREYI_GECIYOR():
    """Ayarlamak yetmez; baslat.sh gecmezse dugum varsayilanda kalir."""
    bs = (KOK / 'deploy' / 'rpi' / 'baslat.sh').read_text()
    assert 'qr_formasyon_gecis_hiz_mps:=' in bs
    assert 'GOREV_QR_FORMASYON_GECIS_HIZ' in bs


def test_MISSION1_NODE_OKUYOR():
    m = (KOK / 'src' / 'swarm_missions' / 'swarm_missions'
         / 'mission1_dynamic_swarm' / 'mission1_node.py').read_text()
    assert "declare_parameter('qr_formasyon_gecis_hiz_mps'" in m
    assert 'qr_formasyon_gecis_hiz_mps=float(' in m


# --------------------------------------------------------- ② deger

def test_DEGER_1_0_DA_KALIYOR():
    """🔴 0.5 DENENDI ve GERI ALINDI — ayni gun, sahada olculdu.

    Yavaslatmak "formasyon kuruldu" olcutunu kandiriyor:
        plateau = (max(hist)-min(hist)) <= settle_improve_eps_m
        stopped = max_move <= settle_move_eps_m
    ikisi de HIZA bagli; yari hizda ikisi de kolaylasiyor ve faz suru
    henuz 5 m uzaktayken ilerliyor. Olculen sonuc:
        slot hatasi 0.00 -> 5.12 m · en dar ayrim 2.69 -> 1.88 m
        irtifa yayilimi 0.80 -> 5.90 m
    Bu test degeri kilitliyor: dusurulecekse settle esikleri de
    orantili kucultulmeli, yoksa geri tepiyor.
    """
    ua = (KOK / 'src' / 'gcs' / 'ucus_ayarlari.py').read_text()
    for satir in ua.splitlines():
        if satir.startswith('GOREV_QR_FORMASYON_GECIS_HIZ_MPS'):
            assert float(satir.split('=')[1].strip()) == 1.0, (
                'gecis hizi degistirilmis — settle esikleri de orantili '
                'kucultulmeden dusurmek 8 Eylul de geri tepti'
            )
            return
    raise AssertionError('GOREV_QR_FORMASYON_GECIS_HIZ_MPS bulunamadi')


def test_GECIS_HIZI_SEYIR_HIZINDAN_DUSUK():
    """Gecis seyirden hizli olursa slota firlama olur (3 Eylul olcumu)."""
    import sys
    sys.path.insert(0, str(KOK / 'src' / 'gcs'))
    import ucus_ayarlari as UA
    assert UA.GOREV_QR_FORMASYON_GECIS_HIZ_MPS < UA.GOREV_HIZ_MPS


def test_YAPILANDIRMA_DEGERI_KOMUTA_GECIYOR():
    """Alan gercekten kullaniliyor mu — 0.5 verilince 0.5 gitmeli."""
    c = OrchestratorConfig(qr_formasyon_gecis_hiz_mps=0.5)
    assert c.qr_formasyon_gecis_hiz_mps == 0.5
