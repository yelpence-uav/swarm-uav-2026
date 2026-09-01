#!/usr/bin/env python3
# =============================================================================
# GOREV 2 KUMANDA OLCUM ARACI — SwC gecis suresi ve alici failsafe
#
# NEDEN VAR: gorev2.md iki maddede acikca "ONCE OLC" diyor ve bu projenin
# kurali "olcmeden teshis koyma" (CLAUDE.md §9). Ikisi de ayni donanimi
# istiyor (kumanda #2 + ylp00'daki ikinci alici) ve ikisi de UCUS ISTEMIYOR.
#
#   madde 26 — SwC DEBOUNCE ESIGI.  SwC detentli 3 konumlu; okbasi (1000)
#     -> cizgi (2000) giderken FIZIKSEL OLARAK ortadan (1500) gecmek
#     zorunda ve orta = V FORMASYONU. Kod her ayri geciste formasyon
#     degisimi tetikliyor, yani hakem "cizgiye gec" dedigi anda suru ONCE
#     V'ye morf olmaya BASLIYOR. Kuru test okbasi->V en dar anini 4,95 m
#     olctu, kacinma esigi 4,0 m — istenmeyen ara morf kacinmanin kucagina
#     giriyor (carpisma -20xN).
#
#     🔴 ESIK IKI SAYI ARASINA KONUR, tek sayidan turetilmez:
#         (a) GECERKEN ortada gecen sure  -> REDDEDILMELI
#         (b) V'yi KASITLI secerken sure  -> KABUL EDILMELI
#     gorev2.md'deki "200-400 ms" bir TAHMIN, olcum degil. Ikisi ortusurse
#     yazilim debounce'u yetmez ve bunu ucustan ONCE bilmek gerekir.
#
#   madde 30 — ALICI FAILSAFE KAYDI (SwA = 1000).
#     §7.3'te olculdu: kumanda kapaninca alici SUSMUYOR, butun anahtar
#     kanallarini 1500'e aliyor. Deadman yine de dusuyor (aux1=0 < esik
#     300) — AMA BU BIR VARSAYILAN, GARANTI DEGIL. FlySky'da "son konumu
#     tut" secenegi de var; biri onu acarsa SwA 2000'de KALIR ve deadman
#     DUSMEZ. Bu arac failsafe'in gercekten SwA=1000 yazdigini dogrular.
#
# NEREDE KOSAR: UCAKTA, konteynerin ICINDE. YKI'den kosmaz — baslat.sh
# ROS_LOCALHOST_ONLY=1 ile DDS'i loopback'e kapatiyor, YKI drone'un ROS
# grafigini GORMEZ (px4_param.py basligindaki ayni gerekce).
#
#   ./deploy/yki/drone_bul.sh ylp00 \
#       'docker exec -i drone1 python3 -u - --swc' < src/gcs/kumanda_olc.py
#
#   ./deploy/yki/drone_bul.sh ylp00 \
#       'docker exec -i drone1 python3 -u - --failsafe' < src/gcs/kumanda_olc.py
#
# 🔴 `python3 -u` SART: stdout bir tty degil (boru), tamponlanirsa
# "simdi basla" talimati kayit BITTIKTEN SONRA gorunur ve olcum bosa gider.
#
# ON KOSUL: `joystick` bayragi acik olmali (rc_ibus_kopru kosuyor).
# Kontrol:  ros2 topic hz /drone_1/rc/suru
# =============================================================================

import argparse
import statistics
import sys
import time

from mavros_msgs.msg import RCIn
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

# rc_ibus_kopru BEST_EFFORT yayinliyor; RELIABLE abone ESLESMEZ ve tek
# mesaj bile gelmez (D1'in birebir aynisi, 30 Agustos'ta olculdu).
_RC_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

KONU = '/drone_1/rc/suru'

# Kanal indeksleri (0 tabanli) — joystick_interpreter ile AYNI olmak
# ZORUNDA, yoksa olctugumuz sey kodun okudugu sey olmaz.
CH_SWA = 4      # emniyet / deadman
CH_SWC = 6      # formasyon (3 konum)

# Bolge esikleri: joystick_interpreter AUX_FORMATION_THRESH_* degerleri
# aux (-1000..1000) uzerinden +-300; aux = (pwm - 1500) * 2 oldugu icin
# PWM karsiligi 1350 / 1650. Burada PWM ile calisiyoruz.
ALT_ESIK = 1350
UST_ESIK = 1650


def bolge(pwm: int) -> str:
    """PWM'i joystick_interpreter'in gordugu bolgeye cevirir."""
    if pwm < ALT_ESIK:
        return 'OKBASI'
    if pwm > UST_ESIK:
        return 'CIZGI'
    return 'V'


def gecisleri_ayikla(ornek):
    """[(t, pwm)] -> (gecis_ms, kasitli_ms). SAF — ROS yok, testli.

    GECIS   = bir uctan OBUR uca giderken ortada gecen sure. REDDEDILMELI.
    KASITLI = ortaya girilip AYNI uca donuldu ya da kayit ortada basladi;
              yani kullanici V'de DURDU. KABUL EDILMELI.

    Son blok BILEREK sayilmaz: kayit bittigi icin kesilmis olabilir ve
    kesik bir durus "kisa kasitli durus" gibi gorunup esigi asagi cekerdi.
    """
    if not ornek:
        return [], []

    bloklar = []
    for t, v in ornek:
        b = bolge(v)
        if bloklar and bloklar[-1][0] == b:
            bloklar[-1] = (b, bloklar[-1][1], t)
        else:
            bloklar.append((b, t, t))

    gecis, kasitli = [], []
    for i, (b, gt, ct) in enumerate(bloklar):
        if b != 'V':
            continue
        if i + 1 >= len(bloklar):
            continue
        onceki = bloklar[i - 1][0] if i > 0 else None
        sonraki = bloklar[i + 1][0]
        kalis_ms = (ct - gt) * 1000.0
        if onceki is not None and sonraki != onceki:
            gecis.append(kalis_ms)
        else:
            kasitli.append(kalis_ms)
    return gecis, kasitli


class KumandaDinleyici(Node):
    """/drone_1/rc/suru akisini zaman damgasiyla toplar."""

    def __init__(self) -> None:
        super().__init__('kumanda_olc')
        self.ornekler: list[tuple[float, list[int]]] = []
        self.create_subscription(RCIn, KONU, self._geldi, _RC_QOS)

    def _geldi(self, msg: RCIn) -> None:
        if len(msg.channels) < 8:
            return
        self.ornekler.append((time.monotonic(), list(msg.channels)))


def _topla(dugum: KumandaDinleyici, saniye: float,
           canli: bool = False) -> None:
    """Verilen sure boyunca akisi toplar.

    canli=True ise saniyede bir SEKIZ KANALI birden basar. Iki isi var:
    (1) operator kaydin aktigini GORUR — ilk denemede 60 saniye boyunca
    hicbir sey degismedi ve bunu ancak sonda anladik; (2) SwC'yi oynatinca
    hangi kanalin degistigi ANINDA gorunur, yani kanal haritasi yanlissa
    ayri bir tarama olcumu gerekmez.
    """
    baslangic = time.monotonic()
    bitis = baslangic + saniye
    son_basim = 0.0
    while time.monotonic() < bitis and rclpy.ok():
        rclpy.spin_once(dugum, timeout_sec=0.05)
        if not canli or not dugum.ornekler:
            continue
        simdi = time.monotonic()
        if simdi - son_basim < 1.0:
            continue
        son_basim = simdi
        ch = dugum.ornekler[-1][1]
        print(f'  [{simdi - baslangic:4.0f}s] '
              + ' '.join(f'{v:4d}' for v in ch[:14])
              + f'   SwC={bolge(ch[CH_SWC])}')


def _geri_sayim(saniye: int = 5) -> None:
    """Operatorun kumandaya donmesi icin gorunur geri sayim."""
    for k in range(saniye, 0, -1):
        print(f'  ...{k}')
        time.sleep(1.0)


def _akis_var_mi(dugum: KumandaDinleyici) -> bool:
    """Akisi dogrular; yoksa SEBEBINI soyler."""
    _topla(dugum, 2.0)
    if dugum.ornekler:
        return True
    print()
    print('🔴 HIC CERCEVE GELMEDI — olcum yapilamaz.')
    print(f'   Konu: {KONU}')
    print('   Sirasiyla bak:')
    print('     1. `joystick` bayragi acik mi   -> cat /ws/suru_dugumleri')
    print('     2. rc_ibus_kopru kosuyor mu     -> ros2 node list | grep ibus')
    print('     3. alici besleniyor mu (kumanda ACIK olmasa da akmali —')
    print('        §7.3: alici SUSMUYOR, failsafe degeri yayinliyor)')
    return False


def swc_olc(dugum: KumandaDinleyici, sure: float) -> int:
    """SwC gecislerini olcer ve debounce esigi onerir."""
    print()
    print('=' * 70)
    print('MADDE 26 — SwC GECIS SURESI OLCUMU')
    print('=' * 70)
    print()
    print('YAPILACAK (sirayla, acele etmeden):')
    print('  1) SwC\'yi OKBASI ucuna al ve bekle.')
    print('  2) NORMAL HIZDA cizgiye gecir, orada bekle. Tersini yap.')
    print('     Bunu 5 kez tekrarla — ORTADA DURMA, gecip git.')
    print('  3) Sonra 3 kez ORTADA (V) KASITLI dur, birkac saniye bekle.')
    print()
    print(f'  {sure:.0f} saniye kayit alinacak. Kumandaya don:')
    _geri_sayim()
    print('  >>> KAYIT BASLADI — SIMDI OYNAT <<<')
    print('        CH1  CH2  CH3  CH4  CH5  CH6  CH7  CH8')
    print()

    dugum.ornekler.clear()
    _topla(dugum, sure, canli=True)
    print()

    ornek = [(t, ch[CH_SWC]) for t, ch in dugum.ornekler]
    if len(ornek) < 10:
        print(f'🔴 Yetersiz ornek ({len(ornek)}). Akis kesildi mi?')
        return 1

    sure_ger = ornek[-1][0] - ornek[0][0]
    hz = (len(ornek) - 1) / sure_ger if sure_ger > 0 else 0.0
    print(f'{len(ornek)} ornek, {sure_ger:.1f} s, {hz:.1f} Hz')
    print(f'PWM araligi: {min(v for _, v in ornek)} .. '
          f'{max(v for _, v in ornek)}')
    print()

    gecis, kasitli = gecisleri_ayikla(ornek)

    # 🔴 SUPHELI GECISI SESSIZCE KULLANMA.
    # "V'de durup sonra obur uca devam etmek" ile "gecip gitmek" olcumde
    # AYIRT EDILEMEZ (ikisi de: uc -> orta -> obur uc). Boyle bir kayit
    # en uzun gecisi saniyelere cikarir ve esigi bosuna yukari ceker —
    # yani KASITLI V secimi gereksiz yere gecikir. 1 s'yi asan bir "gecis"
    # el hareketi degil, duraklamadir. Ayiklaniyor ama GORUNUR sekilde:
    # sessiz kirpma "hepsi olculdu" gibi okunurdu.
    supheli = [ms for ms in gecis if ms > 1000.0]
    if supheli:
        gecis = [ms for ms in gecis if ms <= 1000.0]
        print(f'⚠️  {len(supheli)} adet 1 s\'yi asan "gecis" AYIKLANDI: '
              + ', '.join(f'{ms:.0f} ms' for ms in supheli))
        print('    Bunlar ortada DURAKLAMIS olmali (adim 2\'de durmamak '
              'gerekiyordu).')
        print('    Esik kalan gecislerden hesaplaniyor.')
        print()
        if not gecis:
            print('🔴 Ayiklamadan sonra gecis KALMADI — olcumu tekrarla,')
            print('   bu sefer ortada hic durmadan gecir.')
            return 1

    print(f'GECIS (ortadan gecerken)  : {len(gecis)} adet')
    if gecis:
        for ms in gecis:
            print(f'    {ms:7.0f} ms')
        print(f'  en kisa {min(gecis):.0f} · ortanca '
              f'{statistics.median(gecis):.0f} · EN UZUN {max(gecis):.0f} ms')
    print()
    print(f'KASITLI V durusu          : {len(kasitli)} adet')
    if kasitli:
        for ms in kasitli:
            print(f'    {ms:7.0f} ms')
        print(f'  EN KISA {min(kasitli):.0f} · ortanca '
              f'{statistics.median(kasitli):.0f} · en uzun '
              f'{max(kasitli):.0f} ms')
    print()

    if not gecis:
        en_az, en_cok = min(v for _, v in ornek), max(v for _, v in ornek)
        if en_az == en_cok:
            print(f'🔴 CH{CH_SWC + 1} HIC KIPIRDAMADI (sabit {en_az}).')
            print('   Ya SwC oynatilmadi, ya da SwC BASKA BIR KANALDA.')
            print('   Yukaridaki canli satirlara bak: SwC\'yi oynatinca')
            print('   hangi sutun degisti? Degisen kanal SwC\'dir ve')
            print('   §7.2 kanal haritasi (CH7) GECERSIZ demektir —')
            print('   joystick_interpreter da yanlis kanali okuyor olur.')
        else:
            print('🔴 Hic GECIS yakalanmadi — bir uctan obur uca gecmedin')
            print('   ya da gecisler kayit disinda kaldi. Tekrarla.')
        return 1

    en_uzun_gecis = max(gecis)
    print('-' * 70)
    print('SONUC')
    print('-' * 70)
    if not kasitli:
        print('⚠️  KASITLI V durusu yakalanmadi — ust sinir bilinmiyor.')
        print(f'   Alt sinir olculdu: esik > {en_uzun_gecis:.0f} ms olmali.')
        print('   Olcumu KASITLI durus adimiyla tekrarla.')
        return 1

    en_kisa_kasitli = min(kasitli)
    print(f'  gecerken EN UZUN ortada kalis : {en_uzun_gecis:6.0f} ms')
    print(f'  kasitli EN KISA V durusu      : {en_kisa_kasitli:6.0f} ms')
    print()
    if en_kisa_kasitli <= en_uzun_gecis:
        print('🔴 IKI DAGILIM ORTUSUYOR — yazilim debounce\'u TEK BASINA')
        print('   YETMEZ. Gecerken kalinan sure, kasitli durustan uzun.')
        print('   Secenekler: (a) SwC\'yi daha hizli cevirme yordami —')
        print('   ZAYIF, bu proje yordama guvenmiyor (B18 dersi);')
        print('   (b) V\'yi ayri bir kanala/anahtara tasi (donanim);')
        print('   (c) formasyon degisimini SwC kenarina degil, ayri bir')
        print('   ONAY hareketine bagla. Operator karari.')
        return 1

    # Esik iki dagilimin ORTASINA degil, gecise YAKIN konur: amac gecisi
    # elemek, kasitli secimi GECIKTIRMEMEK. Pay %50 ya da 60 ms — hangisi
    # buyukse; tek olcumun kuyrugunu hafife almamak icin.
    pay = max(en_uzun_gecis * 0.5, 60.0)
    onerilen = en_uzun_gecis + pay
    if onerilen >= en_kisa_kasitli:
        onerilen = (en_uzun_gecis + en_kisa_kasitli) / 2.0
        print('  (pay dagilimlarin arasina sigmadi -> tam ortasi alindi)')
    print(f'  ✅ ONERILEN DEBOUNCE ESIGI    : {onerilen:6.0f} ms')
    print()
    print(f'  Bu esikle: gecerken tetiklenmez (en uzun {en_uzun_gecis:.0f} ms)')
    print(f'             kasitli V {onerilen:.0f} ms sonra secilir')
    print(f'             (en hizli kasitli durus {en_kisa_kasitli:.0f} ms)')
    print()
    print('  Sayiyi gorev2.md madde 26\'ya ve koda YAZ; bu cikti kanittir.')
    return 0


def _degisim_dokumu(ornekler) -> None:
    """Her kanalin DEGISIM anlarini basar.

    🔴 NEDEN GEREKLI: ilk/son cerceve karsilastirmasi "hicbir sey
    degismedi" ile "kumanda hic kapanmadi"yi AYIRT ETMIYOR. 30 Agustos
    gecesi tam bu yuzden bir olcum bosa gitti. Kanal bazinda degisim
    dokumu belirsizligi kaldiriyor: link gercekten koptuysa EN AZ BIR
    kanal siciramaz kalamaz.
    """
    t0 = ornekler[0][0]
    print('  KANAL DEGISIM DOKUMU (yalniz degisen kanallar):')
    hic = True
    for k in range(14):
        seri = [(t - t0, ch[k]) for t, ch in ornekler if len(ch) > k]
        bloklar = []
        for t, v in seri:
            if bloklar and abs(bloklar[-1][2] - v) <= 6:
                # +-6 us: i-BUS gurultusu, degisim SAYILMAZ.
                bloklar[-1] = (bloklar[-1][0], t, bloklar[-1][2])
            else:
                bloklar.append((t, t, v))
        if len(bloklar) < 2:
            continue
        hic = False
        print(f'    CH{k + 1}: ' + '  ->  '.join(
            f'{v} ({gt:.1f}-{ct:.1f}s)' for gt, ct, v in bloklar))
    if hic:
        print('    (hicbir kanal degismedi)')
    print()


def _titresim_dokumu(ornekler) -> None:
    """Kanal basina AYRIK DEGER SAYISI ve aralik.

    NEDEN: alicinin failsafe'ine tek basina guvenmek 30 Agustos gecesi
    ISIRDI — kumanda kapaninca alici son cerceveyi TUTTU ve CH5 acik
    kaldi, yani deadman DUSMEDI. Yazilim tarafinda bagimsiz bir dedektor
    icin aday isaret: CANLI bir vericide analog kanallar 1-2 us TITRER,
    tutulan cerceve ise BIT-BIREBIR donar.

    ⚠️ Bu dokum o fikri OLCMEK icin; dogrulanmadan koda yazilmaz. Yanlis
    pozitif bir "link oldu" karari deadman'i havada dusurur — kendi
    basina tehlikeli. Once "canli + eller cekilmis" halde titresimin
    HER ZAMAN var oldugu gosterilmeli.
    """
    print('  TITRESIM DOKUMU (canli link kaniti):')
    donuk = []
    for k in range(14):
        seri = [ch[k] for _, ch in ornekler if len(ch) > k]
        if not seri:
            continue
        ayrik = sorted(set(seri))
        etiket = f'CH{k + 1}'
        if len(ayrik) == 1:
            donuk.append(etiket)
            print(f'    {etiket}: DONUK — tek deger {ayrik[0]}')
        else:
            print(f'    {etiket}: {len(ayrik)} ayrik deger, '
                  f'{min(ayrik)}..{max(ayrik)} (yayilim {max(ayrik) - min(ayrik)})')
    print()
    if len(donuk) == 8:
        print('    🔴 SEKIZ KANAL DA BIT-BIREBIR DONUK — canli bir verici')
        print('       boyle gorunmez. Cerceve TUTULUYOR olabilir.')
    elif donuk:
        print(f'    Donuk kanallar: {", ".join(donuk)} '
              f'(salterler icin NORMAL, analog kanallar icin degil)')
    print()


def izle(dugum: KumandaDinleyici, sure: float) -> int:
    """Sadece bakar: kanallari basar, HUKUM VERMEZ.

    Iki kisi arasinda "sen ne goruyorsun" sorusunu cevaplamak icin.
    Failsafe hukmu vermeye calismak burada YANLIS olurdu: salteri elle
    cevirmekle linkin kopmasi ayni kanal degisimini uretiyor.
    """
    print()
    print('=' * 70)
    print(f'IZLE — {sure:.0f} saniye, sadece okuma')
    print('=' * 70)
    print('        CH1  CH2  CH3  CH4  CH5  CH6  CH7  CH8')
    print('                            ^SwA ^SwB ^SwC ^SwD')
    print()
    dugum.ornekler.clear()
    _topla(dugum, sure, canli=True)
    print()
    if dugum.ornekler:
        _degisim_dokumu(dugum.ornekler)
        _titresim_dokumu(dugum.ornekler)
    return 0


# Eksen sozlesmesi — SwarmControlCommand.msg:
#   pitch_cmd > 0 = ileri · roll_cmd > 0 = saga
#   yaw_cmd   > 0 = saat yonu (saga) · throttle_cmd > 0 = tirmanis
# (ad, yonerge, kanal_index, "ust uc dogru mu" beklentisi)
EKSENLER = (
    ('PITCH', 'cubugu ILERI it ve TUT', 1, 'ileri'),
    ('ROLL', 'cubugu SAGA it ve TUT', 0, 'saga'),
    ('YAW', 'cubugu SAGA cevir ve TUT', 3, 'saat yonu'),
    ('GAZ', 'gazi YUKARI it ve TUT', 2, 'tirmanis'),
)


def isaret_olc(dugum: KumandaDinleyici, sure: float) -> int:
    """madde 17 — eksen isaretlerini olcer ve rc_eksen sabitlerini uretir.

    🔴 NEDEN EN KRITIK OLCUM: ters bir isaret "suru cubugun TERSINE
    gider" demek ve HICBIR YERDE hata vermez. Eski kumandada kodda
    "genellikle RCIn pitch ileri itince pwm duser" diye bir VARSAYIM
    yaziliydi; olcum tersini gosterdi ve duzeltilmeseydi Ucus A'da suru
    ters yone giderdi (gorev2.md §7.2).

    ⚠️ Her eksen TEK YONE oynatilir. Ilk olcumde her cubuk iki yone
    birden oynatildigi icin sonuc belirsiz kalmis ve roll de ters
    saniilmisti; sira varsayimiyla koda dokunulsaydi DOGRU olan roll
    bozulacakti.
    """
    print()
    print('=' * 70)
    print('MADDE 17 — EKSEN ISARETLERI')
    print('=' * 70)
    print()
    print('Her eksen icin: soylenen yone it, TUT, sonra BIRAK.')
    print('🔴 TEK YONE oynat — iki yone birden oynatma.')
    print()

    sonuc = []
    for ad, yonerge, k, beklenen in EKSENLER:
        print(f'--- {ad}: {yonerge}')
        if ad == 'GAZ':
            def _kosul(ch, _k=k):
                return ch[_k] > 1700
        else:
            def _kosul(ch, _k=k):
                return abs(ch[_k] - 1500) > 300
        tamam, _ = _bekle(dugum, _kosul, sure, f'{ad}: {yonerge}')
        if not tamam:
            print(f'  🔴 {ad} icin sapma gorulmedi — atlaniyor.')
            sonuc.append((ad, None, beklenen))
            continue
        # Sapma yonundeki UC degeri yakala (2 saniye izle).
        uc = dugum.ornekler[-1][1][k]
        bitis = time.monotonic() + 2.0
        while time.monotonic() < bitis and rclpy.ok():
            rclpy.spin_once(dugum, timeout_sec=0.05)
            v = dugum.ornekler[-1][1][k]
            if abs(v - 1500) > abs(uc - 1500):
                uc = v
        ust = uc > 1500
        print(f'  olculen: CH{k + 1} = {uc}  ({"UST" if ust else "ALT"} uc)')
        sonuc.append((ad, uc, beklenen))
        print('  cubugu BIRAK...')
        _bekle(dugum, lambda ch, _k=k: abs(ch[_k] - 1500) < 150, 15.0,
               f'{ad} birakilmasi')
        print()

    print('-' * 70)
    print('SONUC — rc_eksen.py sabitleri')
    print('-' * 70)
    print()
    hata = 0
    for ad, uc, beklenen in sonuc:
        if uc is None:
            print(f'  {ad:6s}: OLCULEMEDI')
            hata = 1
            continue
        ters = uc < 1500
        if ad == 'GAZ':
            # Gaz ORTALANMAZ, dinlenme yeri DIP. Olcut: yukari itince UST
            # uca gitmeli. gaz_normalize dip=0/tepe=1 varsayiyor; ters
            # cikarsa cozum TERS_* degil, kumandada kanal REVERSE'udur.
            durum = ('✅ dogru (yukari = ust uc)' if uc > 1700
                     else '🔴 TERS — kumandada REVERSE et')
            print(f'  {ad:6s}: {uc} -> {durum}')
            if uc <= 1700:
                hata = 1
        else:
            print(f'  {ad:6s}: {uc:4d} ({beklenen} icin) -> '
                  f'TERS_{ad} = {ters}')
    print()
    print('  Bu degerleri rc_eksen.py TERS_PITCH / TERS_ROLL / TERS_YAW')
    print('  sabitlerine YAZ ve olcum blogunu guncelle. Bu cikti kanittir.')
    return hata


def _bekle(dugum, kosul, zaman_asimi: float, etiket: str):
    """kosul(ch) saglanana kadar bekler. (basarili, gecen_sure) doner.

    🔴 NEDEN FAZLI: 30 Agustos gecesi bu olcum DORT KEZ bosa gitti —
    hepsinde sebep zamanlamaydi (operator "simdi" anini yakalayamadi ya
    da salteri yanlis konumda birakti). Sabit sureli kayit, iki insanin
    saniye hassasiyetinde anlasmasini gerektiriyor; arac BEKLERSE bu
    gereksinim ortadan kalkiyor.
    """
    baslangic = time.monotonic()
    son_basim = 0.0
    while time.monotonic() - baslangic < zaman_asimi and rclpy.ok():
        rclpy.spin_once(dugum, timeout_sec=0.05)
        if not dugum.ornekler:
            continue
        ch = dugum.ornekler[-1][1]
        if kosul(ch):
            return True, time.monotonic() - baslangic
        simdi = time.monotonic()
        if simdi - son_basim >= 4.0:
            son_basim = simdi
            # 🔴 TALIMAT HER SATIRDA TEKRARLANIR. Ilk surumde yonerge bir
            # kez basiliyordu ve ilerleme satirlari onu ekrandan
            # kaydiriyordu; operator "rehberi goremiyorum" dedi ve UC
            # olcum ust uste bosa gitti (31 Agustos).
            print(f'  >>> {etiket}   [{simdi - baslangic:3.0f}s]   '
                  + ' '.join(f'{v:4d}' for v in ch[:8]))
    return False, time.monotonic() - baslangic


def failsafe_olc(dugum: KumandaDinleyici, sure: float) -> int:
    """Kumanda kapatilinca alicinin ne yayinladigini olcer (iki fazli)."""
    print()
    print('=' * 70)
    print('MADDE 30 — ALICI FAILSAFE DOGRULAMASI')
    print('=' * 70)
    print()
    print('Zamanlama YOK — arac bekliyor. Sirasiyla:')
    print('  1) SwA\'yi YUKARI al (emniyet ACIK).')
    print('  2) Arac "SIMDI KAPAT" deyince kumandayi kapat, KAPALI birak.')
    print('  3) Salterlere ve cubuklara BASKA hicbir sey yapma.')
    print()

    # ---- FAZ 1: SwA ACIK gorulene kadar bekle ---------------------------
    print(f'FAZ 1 — SwA\'yi YUKARI al. ({sure:.0f} s icinde)')
    tamam, _ = _bekle(dugum, lambda ch: ch[CH_SWA] >= 1900, sure,
                      'SwA bekleniyor')
    if not tamam:
        print()
        print('🔴 SwA hic ACIK (2000) gorulmedi — olcum yapilamadi.')
        print('   Kumanda acik mi? SwA yukari = CH5 2000 (olculdu).')
        return 1
    print()
    print('  ✅ SwA ACIK (CH5=2000). Iki saniye sabit kalmasini bekliyorum...')
    kararli, _ = _bekle(dugum, lambda ch: ch[CH_SWA] < 1900, 2.0, 'kararlilik')
    if kararli:
        print('  ⚠️  SwA hemen dustu — yukarida SABIT tut ve tekrarla.')
        return 1

    # ---- FAZ 2: dususu bekle -------------------------------------------
    print()
    print('  ' + '=' * 60)
    print('  >>> SIMDI KUMANDAYI KAPAT (guc dugmesini basili tut) <<<')
    print('  ' + '=' * 60)
    print()
    dugum.ornekler.clear()
    tamam, gecen = _bekle(dugum, lambda ch: ch[CH_SWA] <= 1100, sure,
                          'kapatilmasi bekleniyor')
    if not tamam:
        print()
        print('🔴🔴 KUMANDA KAPANDI AMA CH5 DUSMEDI — ya da hic kapanmadi.')
        print('     Kapattiysan sonuc NET: alici SON KONUMU TUTUYOR,')
        print('     failsafe kaydi TUTMAMIS. Kumanda kaybinda deadman')
        print('     DUSMEZ ve suru son cubuk komutunu SURDURUR.')
        print('     🔴 BU HALDE UCULMAZ (madde 30).')
        return 1

    print()
    print(f'  CH5 dustu ({gecen:.1f}s). Kalici mi diye 6 saniye izliyorum...')
    geri, _ = _bekle(dugum, lambda ch: ch[CH_SWA] >= 1900, 6.0, 'kalicilik')
    _degisim_dokumu(dugum.ornekler)

    print('-' * 70)
    print('SONUC')
    print('-' * 70)
    if geri:
        print('  ⚠️  CH5 tekrar 2000\'e cikti — dusus KALICI DEGIL.')
        print('     Kumanda tekrar acilmis ya da salter oynatilmis olabilir.')
        print('     Failsafe imzasi TEK YONLU ve KALICIDIR. Tekrarla.')
        return 1

    son = dugum.ornekler[-1][1]
    print('  kumanda KAPALIYKEN son cerceve:')
    print('    ' + ' '.join(f'{v:4d}' for v in son[:14]))
    print('    CH1  CH2  CH3  CH4  CH5  CH6  CH7  CH8')
    print()
    print(f'  ✅ FAILSAFE DOGRULANDI — CH5 2000 -> {son[CH_SWA]} ve orada')
    print('     KALDI. Tek yonlu ve kalici: salter hareketi degil, failsafe.')
    print('     Kumanda kaybinda deadman DUSER -> suru HOLD\'a gecer.')
    print('     Madde 30 KAPANDI — gorev2.md\'ye yaz.')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Gorev 2 kumanda olcumleri (madde 26 ve 30)')
    ap.add_argument('--swc', action='store_true',
                    help='madde 26: SwC gecis suresi ve debounce esigi')
    ap.add_argument('--failsafe', action='store_true',
                    help='madde 30: kumanda kapaliyken SwA ne oluyor')
    ap.add_argument('--izle', action='store_true',
                    help='sadece kanallari bas, hukum verme')
    ap.add_argument('--isaret', action='store_true',
                    help='madde 17: eksen isaretleri (rehberli)')
    # 60 s: 5 gecis (~20 s) + 3 kasitli durus (~15 s) + aradaki
    # duraklamalar. 45 s ile denendiginde son adima yer kalmiyordu.
    ap.add_argument('--sure', type=float, default=60.0,
                    help='kayit suresi saniye (varsayilan 60)')
    a = ap.parse_args()

    if not (a.swc or a.failsafe or a.izle or a.isaret):
        ap.print_help()
        return 2

    rclpy.init()
    dugum = KumandaDinleyici()
    try:
        if not _akis_var_mi(dugum):
            return 1
        if a.izle:
            return izle(dugum, a.sure)
        if a.isaret:
            return isaret_olc(dugum, a.sure)
        if a.swc:
            return swc_olc(dugum, a.sure)
        return failsafe_olc(dugum, a.sure)
    finally:
        dugum.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
