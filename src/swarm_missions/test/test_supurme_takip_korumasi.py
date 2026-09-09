# Copyright 2026 Yelpence
"""Supurme, suru YETISEMIYORSA BEKLER — kademe kademe asagi kaymaz.

🔴 8 EYLUL 2026, SAHADA OLCULDU.

Supurme her ~12 saniyede 5 metre TIRMANMA istiyor. Ucak tirmanamazsa
(pil, ruzgar, itki) program bunu BILMIYORDU: bir sonraki turda yeni bir
INIS komutu daha veriyor, ucak zaten geride oldugu icin biraz daha
aliyor. Kademe kademe asagi kayiyorlar.

    komut edilen   10.00 .. 14.78 m      (profil DOGRU calisti)
    ylp00 fiili     6.1  .. 19.3  m      -> TABANIN (10 m) 4 m ALTINA
    ucaklar arasi dikey dagilma          7 metreye kadar

    gerilim (havada medyan):
        ylp01 13.90 V -> 12.1 m'nin ALTINA HIC INMEDI  (takip etti)
        ylp02 13.70 V -> 6.7 m'ye kadar indi
        ylp00 12.90 V -> 6.1 m'ye kadar indi           (en bos pil, en kotu)

Supurme asagi inerken yercekimi yardim ediyor, YUKARI cikarken itki
gerekiyor. Bos pille itki yok — ucak iniyor ama cikamiyor.

COZUM: supurmenin SAATI takibe bagli. Suru komut edilen irtifayi
tutamiyorsa saat DURUR; yeni komut uretilmez, suru yetisene kadar
beklenir, yetisince kaldigi yerden devam eder.
"""

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE = 5
TAVAN_H = 3.0
_IDS = [1, 2, 3]


def _orch(tavan=TAVAN_H, gecikme=8.0):
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=3, qr_okuma_irtifa_m=15.0,
        qr_arama_dikey_hiz_mps=1.5, qr_arama_taban_bekleme_s=5.0,
        qr_recovery_delay_s=gecikme, qr_arama_takip_tavani_m=tavan,
    ))
    o.set_origin(41.0, 29.0)
    return o


def _inp(t, irtifalar):
    """irtifalar: her ucagin GERCEK irtifasi (m, pozitif yukari)."""
    pos = [(0.0, i * 7.0, -a) for i, a in enumerate(irtifalar)]
    return OrchestratorInput(
        mission_state=S_EXECUTE, qr_step=0, is_leader=True,
        agent_ids=list(_IDS), positions=pos,
        centroid=(0.0, 7.0, -sum(irtifalar) / 3.0),
        home=(0.0, 0.0, 0.0), time_in_state=t,
    )


def _komut_irtifasi(o, t, irtifalar):
    cmd = o._maybe_qr_recovery(_inp(t, irtifalar))
    if cmd is None:
        return None
    assert isinstance(cmd, FormationTargetCmd)
    return -cmd.center[2]


# ------------------------------------------------------------ asil kusur

def test_TAKIP_BOZULUNCA_SAAT_DURUR():
    """🔴 Kusurun ta kendisi: suru geride kalinca supurme devam ediyordu."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])      # ilk komut
    faz1 = o._st.supurme_faz_s
    # suru 6 metre geride (sahada ylp00 4 m tabanin altindaydi)
    for t in (9.0, 10.0, 11.0, 12.0):
        _komut_irtifasi(o, t, [8.0, 8.0, 8.0])
    assert o._st.supurme_faz_s == faz1, (
        'takip bozukken supurme fazi ilerledi — suru daha asagi itilir')
    assert o._st.supurme_bekleme_sayaci >= 1


def test_TAKIP_DUZELINCE_DEVAM_EDER():
    """Bekleme kalici olmamali: yetisince kaldigi yerden surer."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    for t in (9.0, 10.0):
        _komut_irtifasi(o, t, [8.0, 8.0, 8.0])       # geride
    duran = o._st.supurme_faz_s
    for t in (11.0, 12.0, 13.0):
        hedef = o._st.search_alt_m
        _komut_irtifasi(o, t, [hedef, hedef, hedef])  # yetisti
    assert o._st.supurme_faz_s > duran, 'takip duzeldi ama saat ilerlemedi'


def test_TEK_UCAK_GERIDEYSE_DE_BEKLER():
    """Sahada ylp01 takip ediyordu, ylp00 ve ylp02 kaliyordu — EN KOTUSU
    olcut olmali, ortalama degil."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    hedef = o._st.search_alt_m
    for t in (9.0, 10.0):
        _komut_irtifasi(o, t, [hedef, hedef, hedef - 6.0])   # biri geride
    assert o._st.supurme_faz_s == faz1


# --------------------------------------------------------- yanlis alarm yok

def test_NORMAL_TAKIP_HATASI_DURDURMAZ():
    """Olculen normal takip hatasi ~0.5 m — bu supurmeyi kesmemeli."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0):
        hedef = o._st.search_alt_m
        _komut_irtifasi(o, t, [hedef - 0.5, hedef + 0.4, hedef - 0.3])
    assert o._st.supurme_faz_s > faz1, 'normal hata supurmeyi durdurdu'


def test_KAPALIYKEN_ESKI_DAVRANIS():
    """0.0 = kapali: takip ne olursa olsun saat ilerler (geriye uyum)."""
    o = _orch(tavan=0.0)
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0):
        _komut_irtifasi(o, t, [8.0, 8.0, 8.0])
    assert o._st.supurme_faz_s > faz1
    assert o._st.supurme_bekleme_sayaci == 0


def test_ILK_KOMUTTA_BEKLEME_YOK():
    """Henuz hedef yokken (NaN) takip olculemez — bekleme tetiklenmemeli."""
    o = _orch()
    assert _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0]) is not None
    assert o._st.supurme_bekleme_sayaci == 0


# ------------------------------------------------------------- yasam

def test_GOREV_DISINA_CIKINCA_SIFIRLANIR():
    """Yeni bir QR arayisi temiz sayfayla baslamali."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    _komut_irtifasi(o, 10.0, [15.0, 15.0, 15.0])
    assert o._st.supurme_faz_s > 0.0
    disari = _inp(11.0, [15.0, 15.0, 15.0])
    disari.qr_step = 1                       # artik "takilmis" degil
    o._maybe_qr_recovery(disari)
    assert o._st.supurme_faz_s == 0.0


def test_BEKLEME_GORUNUR():
    """Sessiz bekleme, yamasizliktan az farkli olurdu — not uretilmeli."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    _komut_irtifasi(o, 9.0, [8.0, 8.0, 8.0])
    n = o.supurme_notu
    assert n and 'BEKLIYOR' in n and 'takip hatasi' in n


# ------------------------------------------- yerdeki ucak kilitlemesin

def test_YERDEKI_UCAK_SUPURMEYI_KILITLEMEZ():
    """🔴 Inmis ama kadroda kalan ucak supurmeyi SONSUZA KADAR bekletirdi.

    8 Eylul 2026: ylp02 birkac kez indi/oldu ve mesh'te bir sure daha
    'aktif' gorundu. Takip hatasi onun 0 m'si yuzunden kalici olarak
    10 m'nin ustunde kalir, saat bir daha ilerlemez ve HICBIR YERDE hata
    gorunmezdi: "supurme calisiyor ama irtifa degismiyor."
    """
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0):
        # ikisi komutu tutuyor, ucuncusu YERDE
        _komut_irtifasi(o, t, [o._st.search_alt_m, o._st.search_alt_m, 0.1])
    assert o._st.supurme_faz_s > faz1, (
        'yerdeki ucak supurmeyi kilitledi — havadakiler bekletiliyor')


def test_HEPSI_YERDEYSE_BEKLENMEZ():
    """Kimse havada degilse takip olcusu anlamsizdir; saat durmaz."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0):
        _komut_irtifasi(o, t, [0.1, 0.1, 0.1])
    assert o._st.supurme_faz_s > faz1


def test_HAVADAKI_GERIDEYSE_HALA_BEKLER():
    """Filtre korumayi delmemeli: havadaki ucak geride ise saat DURUR."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0, 15.0, 15.0])
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0):
        _komut_irtifasi(o, t, [15.0, 6.0, 0.1])       # d2 havada ve geride
    assert o._st.supurme_faz_s == faz1


# ------------------------------------------- 🔴 CERCEVE OFSETI (8 Eylul 22:49)

def test_SABIT_OFSET_KORUMAYI_KILITLEMEZ():
    """🔴 Kusurun ta kendisi: 3.33 m sabit fark supurmeyi DONDURDU.

    Sahada olculen: mission NED ile ucaktan gelen irtifa arasinda sabit
    3.33 m fark var. Tavan 3.0 m oldugu icin koruma ilk saniyede kapandi
    ve bir daha acilmadi — suru QR1'in TAM ustunde (mesafe 0.00 m) 17.2
    m'de asili kaldi, gorev ilerlemedi, hicbir yerde hata gorunmedi.
    """
    o = _orch()
    # ucaklar HEP komuttan 3.33 m yukarida "gorunuyor" ama rampayi
    # kusursuz takip ediyorlar
    OFS = 3.33
    _komut_irtifasi(o, 8.1, [15.0 + OFS] * 3)
    faz1 = o._st.supurme_faz_s
    for t in (9.0, 10.0, 11.0, 12.0, 13.0):
        hedef = o._st.search_alt_m
        _komut_irtifasi(o, t, [hedef + OFS] * 3)
    assert o._st.supurme_faz_s > faz1 + 3.0, (
        'sabit cerceve ofseti supurmeyi kilitledi — 8 Eylul kusuru geri geldi'
    )
    assert o._st.supurme_bekleme_sayaci == 0, (
        f'{o._st.supurme_bekleme_sayaci} kez bosuna beklendi')


def test_OFSET_YAKALANSA_DA_GERI_KALMA_YAKALANIR():
    """Ofset dusulur ama GERCEK geri kalma hala saati durdurmali."""
    o = _orch()
    OFS = 3.33
    _komut_irtifasi(o, 8.1, [15.0 + OFS] * 3)
    _komut_irtifasi(o, 9.0, [o._st.search_alt_m + OFS] * 3)
    faz = o._st.supurme_faz_s
    # simdi bir ucak ofsetin USTUNE 5 m daha geride
    for t in (10.0, 11.0, 12.0):
        hedef = o._st.search_alt_m
        _komut_irtifasi(o, t, [hedef + OFS, hedef + OFS - 5.0, hedef + OFS])
    assert o._st.supurme_faz_s == faz, 'gercek geri kalma yakalanmadi'


def test_OFSET_BIR_KEZ_YAKALANIR():
    """Her tick yeniden yakalansa koruma tamamen ANLAMSIZ olurdu."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [18.33] * 3)
    _komut_irtifasi(o, 9.0, [o._st.search_alt_m + 3.33] * 3)
    ofs1 = o._st.supurme_ofset_m
    for t in (10.0, 11.0):
        _komut_irtifasi(o, t, [o._st.search_alt_m + 9.0] * 3)
    assert o._st.supurme_ofset_m == ofs1, 'ofset yeniden yakalandi'


def test_OFSET_GOREV_DISINDA_SIFIRLANIR():
    """Sonraki QR'da yeni ofset yakalanmali — eskisi tasinmaz."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [18.33] * 3)
    _komut_irtifasi(o, 9.0, [o._st.search_alt_m + 3.33] * 3)
    assert o._st.supurme_ofset_m == o._st.supurme_ofset_m   # NaN degil
    inp = _inp(10.0, [15.0] * 3)
    inp.qr_step = 1
    o._maybe_qr_recovery(inp)
    assert o._st.supurme_ofset_m != o._st.supurme_ofset_m, 'ofset sifirlanmadi'


def test_OFSET_TAVANI_KORUMAYI_KAPATMAZ():
    """Bozuk ilk ornek 40 m ofset yakalatip korumayi susturmamali."""
    o = _orch()
    _komut_irtifasi(o, 8.1, [15.0] * 3)
    _komut_irtifasi(o, 9.0, [60.0] * 3)
    assert abs(o._st.supurme_ofset_m) <= 8.0
