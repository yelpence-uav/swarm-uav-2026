# Copyright 2026 Yelpence
"""QR formasyon gecisinde ONCE DIKEY AYRIL, sonra yatayda yerles.

🔴 8 EYLUL 2026, SAHADA OLCULDU, OPERATOR KARARI.

QR2 okununca suru yer dizilisinden (CUSTOM, ~9 m ayrim) V'ye (6 m aralik)
gecerken ucaklar birbirinin slotuna dogru AYNI ANDA gitti ve yollari
KESISTI:

    ayrim  9.06 -> 6.84 -> 4.41 -> 1.88 m     (HARD kabuk 2.0'in ALTINDA)
    yatayda 1.82 m
    kacinma: "CA kacis aktif: v=(3.98,0.36,-0.05) m/s"  -> 3.98 m/s YATAY itme
        -> lider suru merkezinden 11.17 m saptı
        -> irtifa yayilimi 5.90 m
        -> bir ucak digerinin uzerine geldi

Operatorun bildirdigi UC sey de (irtifalar esit degildi / biri ezdi geldi /
biri alip basini gitti) bu TEK zincirden cikti.

ONCE HIZ DENENDI, GERI ALINDI: gecis hizi 1.0 -> 0.5 yapilinca "formasyon
kuruldu" olcutu (plato + durdu) kandirildi — ikisi de HIZA bagli — ve slot
hatasi 0.00 -> 5.12 m'ye cikti. Kesisme bir HIZ sorunu degil GEOMETRI
sorunu.

COZUM (bu dosya): yeni formasyon YATAYDA kurulmadan once ucaklar ayri
irtifalara acilir. Yollar kesisse bile dikey pay vardir, kacinma HIC
tetiklenmez. Yerlesme oturunca katman kalkar, irtifalar esitlenir —
kalkistaki toplanma merdiveniyle BIREBIR ayni yasam dongusu.
"""

from dataclasses import replace

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE = 5
STEP_FORMATION = 1
KATMAN = 3.0
_IDS = [1, 2, 3]
_POS = [(0.0, 0.0, -15.0), (-9.0, 0.0, -15.0), (0.0, 9.0, -15.0)]
_CEN = (-3.0, 3.0, -15.0)


class _QR:
    """QR2'nin sahadaki gercek paketi: frm v 6."""
    formation_type = 2          # V
    spacing_m = 6.0
    pitch_deg = 5.0
    roll_deg = 0.0
    yaw_deg = 0.0
    altitude_agl_m = 0.0


def _orch(katman=KATMAN):
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=3, gorev_formasyon=0, qr_okuma_irtifa_m=15.0,
        qr_gecis_katman_m=katman,
    ))
    o.set_origin(37.0297209, 37.3113894)
    o._st.heading_deg = 0.0
    return o


def _inp(t=0.0):
    return OrchestratorInput(
        mission_state=S_EXECUTE, qr_step=STEP_FORMATION, is_leader=True,
        agent_ids=list(_IDS), positions=list(_POS), centroid=_CEN,
        home=(0.0, 0.0, -15.0), time_in_state=t, swarm_yaw_deg=0.0,
    )


def _ofsetler(o, qr=None):
    cmds = o._exec_formation(_inp(), qr or _QR())
    fc = [c for c in cmds if isinstance(c, FormationTargetCmd)]
    assert fc, 'formasyon komutu uretilmedi'
    return fc[0].offsets


# ------------------------------------------------------------ asil karar

def test_GECISTE_DIKEY_AYRIM_ACILIYOR():
    """🔴 Kusurun ta kendisi: eskiden hepsi AYNI irtifada yer degistiriyordu."""
    z = sorted(o[2] for o in _ofsetler(_orch()))
    yayilim = max(z) - min(z)
    assert yayilim >= 2 * KATMAN - 1e-6, (
        f'dikey ayrim acilmadi (yayilim {yayilim:.2f} m)')


def test_KATMANLAR_ESIT_ARALIKLI():
    """Uc ucak icin 0, -3, -6 — kacinma esigi (3.0 m) her cift icin saglanir."""
    z = sorted((o[2] for o in _ofsetler(_orch())), reverse=True)
    for a, b in zip(z, z[1:]):
        assert abs((a - b) - KATMAN) < 1e-6, f'katman araligi {a-b:.2f} m'


def test_KACINMA_ESIGINI_ASIYOR():
    """Her ucak cifti arasinda KACINMA_D0 (3.0 m) kadar dikey pay olmali."""
    z = [o[2] for o in _ofsetler(_orch())]
    for i in range(len(z)):
        for j in range(i + 1, len(z)):
            assert abs(z[i] - z[j]) >= 3.0 - 1e-6


def test_YATAY_OFSETLERE_DOKUNULMUYOR():
    """Katmanlama YALNIZ z'yi degistirir; sekil bozulmamali."""
    duz = _ofsetler(_orch(katman=0.0))
    katmanli = _ofsetler(_orch())
    assert len(duz) == len(katmanli)
    for a, b in zip(duz, katmanli):
        assert abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


# --------------------------------------------------------- yasam dongusu

def test_BAYRAK_ACILIYOR():
    o = _orch()
    assert o._st.gecis_katmani is False
    _ofsetler(o)
    assert o._st.gecis_katmani is True


def test_KAPALIYKEN_ESKI_DAVRANIS():
    """0.0 = kapali: hicbir sey degismemeli (geriye uyum)."""
    o = _orch(katman=0.0)
    z = [ofs[2] for ofs in _ofsetler(o)]
    assert max(z) - min(z) < 1e-6
    assert o._st.gecis_katmani is False


def test_ANAHTARDA_YER_ALIYOR():
    """🔴 _phase_key'de olmazsa emit-once DUZ komutu bastirir ve suru
    katmanda ASILI kalir — toplanma merdiveninde birebir ayni tuzak."""
    o = _orch()
    inp = _inp()
    k1 = o._phase_key(inp)
    o._st.gecis_katmani = True
    k2 = o._phase_key(inp)
    assert k1 != k2, 'gecis_katmani anahtari degistirmiyor'


def test_YERLESINCE_KATMAN_KALKAR_VE_ONCE_IRTIFA_ESITLENIR():
    """Yakinsama olunca bayrak duser ve o tick sinyal URETILMEZ —
    once duz ofsetlerle irtifa esitlenir, sonra 'bitti' denir."""
    o = _orch()
    _ofsetler(o)
    assert o._st.gecis_katmani is True
    o._st.gecis_katmani = False        # settle dalinin yaptigi
    z = [ofs[2] for ofs in _ofsetler(_orch(katman=0.0))]
    assert max(z) - min(z) < 1e-6      # duz -> irtifalar esit


def test_KATMAN_DEGERI_AYARDAN_GELIYOR():
    for k in (2.0, 4.0):
        z = sorted(o[2] for o in _ofsetler(_orch(katman=k)))
        assert abs((max(z) - min(z)) - 2 * k) < 1e-6


def test_UCUS_AYARLARINDA_TANIMLI():
    """Tek kaynak: deger ucus_ayarlari.py'de ve --kabuk ciktisinda olmali."""
    import pathlib
    kok = pathlib.Path(__file__).resolve().parents[3]
    ua = (kok / 'src' / 'gcs' / 'ucus_ayarlari.py').read_text()
    assert 'GOREV_QR_GECIS_KATMAN_M' in ua
    assert 'GOREV_QR_GECIS_KATMAN=' in ua
    bs = (kok / 'deploy' / 'rpi' / 'baslat.sh').read_text()
    assert 'qr_gecis_katman_m:=' in bs


# ==================== IKI ASAMALI GECIS (8 Eylul, ikinci tur) ==========
# 🔴 ILK SURUM TEK ASAMALIYDI ve SAHADA YETMEDI: yeni yatay formasyon ile
# katmanli irtifa AYNI komutta gidiyordu, ucaklar ikisini birden yurutunce
# yatay kapanma dikey acilmadan hizli oldu ve koruma GEC KALDI:
#     t+1.4 yayilim 0.40 m  ayrim 5.80 m
#     t+4.4 yayilim 0.40 m  ayrim 2.51 m   <- EN DAR AN, katman HENUZ YOK
#     t+7.4 yayilim 6.10 m  ayrim 4.98 m   <- katman ANCAK simdi oturdu
# Artik yatay hareket, dikey ayrim OTURANA KADAR hic baslamiyor.


def _onceki_diziliş(o):
    """Gecis oncesi yatay diziliş (CUSTOM snapshot) — asama 1 bunu korur."""
    o._st.frozen_offsets = {
        1: (0.0, 0.0, 0.0), 2: (-9.0, 0.0, 0.0), 3: (0.0, 9.0, 0.0)}
    return o


def test_ASAMA_1_YATAYI_KORUR():
    """🔴 Asil duzeltme: ilk komut YATAYDA hic yer degistirtmemeli."""
    o = _onceki_diziliş(_orch())
    ofs = _ofsetler(o)
    assert o._st.gecis_asamasi == 1
    beklenen = [(0.0, 0.0), (-9.0, 0.0), (0.0, 9.0)]
    for (x, y), got in zip(beklenen, ofs):
        assert abs(got[0] - x) < 1e-6 and abs(got[1] - y) < 1e-6, (
            'asama 1 yatay ofsetleri degistirdi — dikey ayrim otururken '
            'ucaklar yer degistirmeye baslar (sahada 2.51 m)')


def test_ASAMA_1_DIKEYI_ACAR():
    o = _onceki_diziliş(_orch())
    z = sorted(ofs[2] for ofs in _ofsetler(o))
    assert abs((max(z) - min(z)) - 2 * KATMAN) < 1e-6


def test_ASAMA_1_OTURUNCA_ASAMA_2():
    """Dikey oturunca yataya gecilir; o tick SINYAL URETILMEZ."""
    o = _onceki_diziliş(_orch())
    _ofsetler(o)
    assert o._st.gecis_asamasi == 1
    o._st.gecis_asamasi = 2          # settle dalinin yaptigi
    ofs = _ofsetler(o)
    # asama 2: yatay ARTIK yeni formasyon, katman hala acik
    z = sorted(x[2] for x in ofs)
    assert abs((max(z) - min(z)) - 2 * KATMAN) < 1e-6
    assert o._st.gecis_katmani is True


def test_ASAMA_ANAHTARDA():
    """Asama 1 -> 2 gecisinde state/step/seq AYNI kalir; asama anahtarda
    olmazsa emit-once asama 2 komutunu BASTIRIR ve suru dikey ayrilmis
    halde asili kalir."""
    o = _orch()
    inp = _inp()
    o._st.gecis_asamasi = 1
    k1 = o._phase_key(inp)
    o._st.gecis_asamasi = 2
    assert k1 != o._phase_key(inp)


def test_ONCEKI_DIZILIS_YOKSA_ASAMA_1_ATLANIR():
    """Ilk formasyonda ayrilacak bir diziliş yok — dogrudan asama 2."""
    o = _orch()
    o._st.frozen_offsets = {}
    _ofsetler(o)
    assert o._st.gecis_asamasi == 2


def test_GECIS_BITINCE_YENIDEN_BASLAMAZ():
    """🔴 `_exec_formation` FORMATION adimi boyunca HER TICK cagriliyor.
    Seq kilidi olmazsa asama 2 bitip 0'a donunce asama 1 yeniden baslar
    ve suru sonsuz katmanlanip duzlesir."""
    o = _onceki_diziliş(_orch())
    qr = _QR()
    qr.qr_seq = 7
    o._exec_formation(_inp(), qr)
    o._st.gecis_asamasi = 0
    o._st.gecis_katmani = False
    o._st.gecis_bitti_seq = 7        # settle dalinin yaptigi
    o._exec_formation(_inp(), qr)
    assert o._st.gecis_asamasi == 0, 'gecis yeniden basladi (dongu)'
    assert o._st.gecis_katmani is False


def test_YENI_QR_GECISI_YENIDEN_ACAR():
    """Sonraki QR baska bir formasyon isterse gecis TEKRAR calismali."""
    o = _onceki_diziliş(_orch())
    q1 = _QR(); q1.qr_seq = 7
    o._exec_formation(_inp(), q1)
    o._st.gecis_asamasi = 0
    o._st.gecis_katmani = False
    o._st.gecis_bitti_seq = 7
    q2 = _QR(); q2.qr_seq = 8        # YENI QR
    o._st.frozen_offsets = {
        1: (0.0, 0.0, 0.0), 2: (-6.0, 0.0, 0.0), 3: (0.0, 6.0, 0.0)}
    o._exec_formation(_inp(), q2)
    assert o._st.gecis_asamasi == 1, 'yeni QR gecisi acmadi'
