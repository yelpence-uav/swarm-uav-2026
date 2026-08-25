# Copyright 2026 Yelpence
"""Hiz tabanli carpisma onleme cekirdegi."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class NeighborObs:
    """Tek komsunun CA girdisi.

    ISARET: rel = KOMSU - BEN, NED (z ASAGI pozitif). Yani
        rel_z > 0  ->  komsu BENDEN ASAGIDA
        rel_z < 0  ->  komsu BENDEN YUKARIDA
    Dikey yol verme bu isarete dogrudan bagli; ters yazilirsa ucak
    komsusunun UZERINE tirmanir. Bkz. komsu_adaptoru.py basligi.
    """

    rel_x: float
    rel_y: float
    rel_z: float
    rel_vx: float
    rel_vy: float
    rel_vz: float
    distance: float
    # Dikey yol vermede RUTBE icin sart: kim capa, kim yukari cikacak.
    # 0 = bilinmiyor -> dikey kural o komsu icin uygulanmaz (guvenli taraf).
    agent_id: int = 0


@dataclass
class CaParams:
    """CA ayar kumesi."""

    d0: float = 4.0
    hard: float = 2.0
    r_min: float = 1.5
    f_sat: float = 6.0
    c_dead: float = 0.2
    c_ref: float = 1.0
    c_damp: float = 0.7
    damp_band: float = 0.5
    k_tan: float = 0.0
    v_max: float = 4.0
    xy_guard: float = 0.3
    slew_normal: float = 4.0
    # 30.0 DEGIL 5.66 — 22 Agustos 2026'da ucusta olculdu.
    #
    # Eski sinif varsayilani 30 m/s2 idi ve bu `a = g*tan(theta)` ile
    # 71.9 DERECE egim demek: ucagin YAPAMAYACAGI bir komut. Sahada
    # gorunmuyordu cunku baslat.sh degeri eziyor; ama dugum tek basina
    # kosarsa (yer testi, benzetim, birim test) imkansiz deger devreye
    # giriyordu. CA.md acik soru #6.
    slew_emergency: float = 5.66
    hyst_band: float = 0.2
    dt: float = 0.05

    # =====================================================================
    # DIKEY YOL VERME — 23 Agustos 2026, operator karari
    # =====================================================================
    # Yatay duzlem gorev geometrisinin KENDISI (formasyon slotlari, rota,
    # QR konumlari). Yatay itmek formasyonu bozar; dikey eksen bos. Ayrica
    # yatay "saga gec" kurali n=3'te DONGUSEL (A->B->C->A), dikeyde kimlik
    # siralamasi dongueyi matematiksel olarak imkansiz kiliyor.
    #
    # k_dikey = 0 -> dikey KAPALI, dugum birebir eski davranisina doner.
    k_dikey: float = 1.0
    # Ardisik rutbeler arasi dikey ayrim. 3.0 = operator karari (23 Agu).
    # Rotor izi 8045 pervanede ~1 m'de biter (5 cap); 3 m = 15 cap.
    katman_m: float = 3.0
    # Dikey kacis hiz/ivme tavani.
    #
    # 🔴 v_dikey_max = PX4'UN KENDI TAVANI (MPC_Z_VEL_MAX_UP), ucaktan
    # okundu 23 Agustos 2026: 1.2 m/s. USTUNU YAZMA — PX4 sessizce kirpar
    # ve ayar/log istenen degeri gosterirken ucak baskasini yapar. Daha
    # hizli isteniyorsa ONCE PX4 parametresi yukseltilir.
    #
    # a=2.0 kp=2.0 — operator karari (23 Agustos), "en dengeli deger".
    # Hiz tavani baskin oldugu icin a=3.0'in kazanci yalnizca 0.04 m;
    # bedeli %75 gaz (aski %66) ve MPC_ACC_DOWN_MAX=3.0 sinirina basmak.
    #
    # kp neden 2.0: 0.8 ile 3 m'lik hatada komut yalnizca 2.4 m/s cikiyor
    # ve hiz tavanina hic ulasilmiyordu — sinir kp'nin kendisiydi.
    v_dikey_max: float = 1.2
    a_dikey_max: float = 2.0
    kp_dikey: float = 2.0
    # MUTLAK irtifa tavani (m, goreli). 0 = kapali.
    #
    # Once "catisma basindaki irtifamin en fazla 2 x katman ustu" seklinde
    # yazilmisti; YANLISTI. Gorev irtifa degisimi komutu verdiginde (QR
    # "20 m'ye cik") capa tirmanir ve merdiven onu takip eder — o kaskad
    # DOGRU davranistir, ama baslangica sabitlenmis bir tavan onu keserdi.
    #
    # Yeni formulasyonda kacak zaten imkansiz: hedef her zaman OLCULEN
    # komsu irtifasi + katman, yani trafige gore sinirli. Geriye yalniz
    # fiziksel/sartname tavani kaliyor ve o da opsiyonel.
    irtifa_tavan_m: float = 0.0
    # Catisma cikis histerezisi: giris d0'da, cikis d0 + bu kadar.
    # Asili duran iki ucak tam d0'da titresirse merdiven acilip kapanmasin.
    #
    # 0.5 -> 2.5 (24 Agustos 2026): 23 Agustos ucusunda cikis 4.5 m
    # pilotun gozle kestiremeyecegi kadar dardi — komsu 4.9 m'de dururken
    # 3 m'lik ayrim 6 saniyede geri veriliyordu ve operator bunu yo-yo
    # olarak gordu (CA.md §6.5, §7.2). Tek kaynak ucus_ayarlari.py
    # (KACINMA_HIST_M); buradaki yalnizca yedek.
    hist_m: float = 2.5
    # Catisma bittikten sonra nominal irtifaya donus.
    donus_bekleme_s: float = 2.0
    donus_hiz_mps: float = 0.5
    donus_tolerans_m: float = 0.3
    # Dikey inisin altina inemeyecegi taban (irtifa kapisi + pay).
    dikey_taban_m: float = 4.0

    # YATAY ITME — "DIKEY BIRINCIL, YATAY SON CARE" (operator, 23 Agustos).
    #
    # k_yatay: yatay itmenin olcegi. 0 = saf dikey.
    # yatay_esik_m: yatay itmenin ACILDIGI mesafe. 0 = `hard` kullanilir.
    #
    # NEDEN SON CARE, NEDEN HIC DEGIL — BENZETIMLE OLCULDU (23 Agustos):
    # bir ucak asili, digeri uzerine suruluyor (22 Agustos saha testinin
    # birebir karsiligi), en yakin 3B mesafe:
    #
    #     yaklasma     SAF DIKEY    SAF YATAY
    #      1.0 m/s       2.63 m       2.27 m     <- dikey onde
    #      2.5 m/s       1.01 m       2.02 m
    #      4.0 m/s       0.47 m       1.53 m     <- dikey COKUYOR
    #
    # Dikey yetkiyi gercekci olmayan degerlere cikarmak bile kapatmiyor
    # (v=5 a=5 -> 1.83 m, yatay 2.02 m). Sebep AYAR DEGIL GEOMETRI: dikey
    # kacisin kazanabilecegi en fazla mesafe `katman` kadardir (3 m) ve
    # onu kurmak 2-3 saniye alir. Yatay itmenin boyle bir tavani yok —
    # kapanma ekseni boyunca iter, hem mesafe acar hem zaman kazandirir.
    #
    # Cozum: normal catismada SAF DIKEY (formasyon bozulmaz), yalniz sert
    # kabuga girilirse — yani dikey yetisememisse — yatay da acilir.
    k_yatay: float = 1.0
    yatay_esik_m: float = 0.0
    # Bu dugumun kendi kimligi — rutbe karsilastirmasi icin ZORUNLU.
    # 0 birakilirsa dikey kural hic uygulanmaz (guvenli taraf).
    agent_id: int = 0

    # RUTBE: suru kadrosunda (FormationCommand.agent_ids) kimligimin sirasi.
    # 0 = en kucuk kimlik = CAPA. -1 = bilinmiyor.
    #
    # 🔴 NEDEN SABIT KATMAN, "komsunun 3 m ustu" DEGIL — 23 Agustos 2026,
    # BENZETIMLE OLCULDU.
    #
    # Ilk tasarim "benden kucuk kimliklerin en yuksegininin katman kadar
    # ustune cik" diyordu. Benzetimde uc ucakli capraz slot degisiminde
    # COKTU:
    #     t=1.45 s -> drone2 13.16 m, drone3 13.16 m, DIKEY AYRIM 0.00 m
    # Sebep bir YARIS: t=0'da ikisi de yalniz drone1'i goruyor, ikisi de
    # ayni hedefi (drone1 + 3) hesapliyor ve AYNI HIZLA oraya tirmaniyor.
    # Kaskad sirali, ama ucaklar es zamanli hareket ediyor. drone2 kendi
    # katmanina yerlesene kadar drone3 onu "hedefte" goremiyor.
    #
    # DONUSUMLU MERDIVEN yarisi ortadan kaldiriyor: hedefler bastan FARKLI
    # oldugu icin ucaklar ilk andan itibaren BIRBIRINDEN AYRILIYOR.
    #     rutbe 0 -> capa, +0
    #     rutbe 1 -> +katman        (yukari)
    #     rutbe 2 -> -katman        (asagi)
    #     rutbe 3 -> +2*katman
    #     rutbe 4 -> -2*katman
    # Uc ucakta en buyuk sapma yalnizca 1 katman (3 m) — hem daha guvenli
    # hem daha ucuz. Rutbe KADRODAN gelir, anlik catisma kumesinden DEGIL;
    # yoksa iki ucak ayni katmani secebilir.
    rutbe: int = -1


def _finite(*vals: float) -> bool:
    """Degerlerin sonlu olup olmadigini denetler."""
    for v in vals:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _smoothstep(t: float) -> float:
    """Smoothstep adimini hesaplar."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def komsu_yerde_pasif(
    armed: bool, pos_z_ned: float, z_valid: bool, yer_esigi_m: float
) -> bool:
    """Kaybolan komsunun SON bilinen durumu 'yerde + disarm' mi?

    25 Agustos 2026 sahada: ylp02 KAPALI masada dururken ylp01 kacisa
    girdi; catisma bitince korluk tutmasi (ca 549) donusu SURESIZ blokladi
    ve ucak gorev bitene dek 7.8 m'de kaldi. Kapali ucak "havada bir yerde
    olabilir" varsayimiyla korunuyordu — oysa son telemetrisi yerde ve
    disarm oldugunu SOYLUYORDU.

    Bu fonksiyon o ayrimi yapar: yerde VE disarm kaybolan komsu tutma
    sebebi OLMAZ (kalkamaz; arm ederse yeni telemetri gelir ve zaten
    korluk biter). Havada ya da arm'li kaybolan komsu icin tutma aynen
    surer — 46.4 sn'lik tek yonlu mesh vakasi (TUZAKLAR 2.15) bu siniftir.

    Dusen ucak notu: PX4 carpismada kendini disarm eder, son paketleri
    yerde+disarm gorunur -> kalanlar gereksiz yere yukseklikte kalmaz.

    z_valid False ise konuma guvenilmez -> guvenli taraf: pasif SAYILMAZ.
    NED: yerde pos_z ~ 0, havada negatif.
    """
    if armed or not z_valid:
        return False
    return -pos_z_ned < yer_esigi_m


def clamp_speed_xy(
    vx: float, vy: float, max_speed: float
) -> tuple[float, float]:
    """XY hizini max_speed degerine kirpar."""
    speed = math.sqrt(vx * vx + vy * vy)
    if speed > max_speed and speed > 1e-9:
        s = max_speed / speed
        return vx * s, vy * s
    return vx, vy


class CollisionAvoidanceCore:
    """Model B hiz tabanli carpisma onleme."""

    def __init__(self, params: CaParams | None = None) -> None:
        self.p = params or CaParams()
        self._prev_vx = 0.0
        self._prev_vy = 0.0
        self._prev_vz = 0.0
        self._emergency = False
        # --- dikey yol verme durumu ---
        self._catisma_aktif = False
        # Dikeye FIILEN mudahale ettim mi. Capa catismada da bu False
        # kalir; nominale donus yalnizca mudahale edilmisse calisir.
        self._mudahale_ettim = False
        self._h_nominal = 0.0        # ILK MUDAHALE anindaki irtifam
        # Secilen kacis yonu: 0 yok, +1 yukari, -1 asagi. Catisma boyunca
        # KORUNUR (yapiskan) — gerekce _dikey_hesapla icinde.
        self._dikey_yon = 0
        self._donus_sayaci = 0.0     # catisma bittikten sonra gecen sure
        # Tanilar — dugum bunlari loglar/olaya cevirir. Sessiz kalmasinlar.
        # dikey_yetersiz : gereken ayrimi saglayamadim (taban/tavan engeli)
        # dikey_donus_kor: komsuyu goremedigim icin ayrimi BIRAKMIYORUM
        self.dikey_yetersiz = False
        self.dikey_donus_kor = False

    def compute(
        self,
        v_form: tuple[float, float, float],
        neighbors: list[NeighborObs],
        h_now: float | None = None,
        kor: bool = False,
    ) -> tuple[tuple[float, float, float], bool]:
        """CA algoritmasini calistirip yeni komut hizini doner.

        h_now: kendi GORELI irtifam (m, YUKARI pozitif). Dikey yol verme
        icin ZORUNLU; None verilirse dikey kural kapali kalir ve dugum
        eski (saf yatay) davranisini birebir surdurur.

        kor: en az bir komsu KORLUK bayragi tasiyor mu. True ise kazanilan
        dikey ayrim BIRAKILMAZ — gerekce _dikey_hesapla icinde.
        """
        p = self.p
        vfx, vfy, vfz = float(v_form[0]), float(v_form[1]), float(v_form[2])

        active: list[tuple[float, float, float, float, float]] = []
        min_d3 = float('inf')
        any_within_rmin = False

        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z,
                           n.rel_vx, n.rel_vy, n.rel_vz):
                continue
            away_x = -n.rel_x
            away_y = -n.rel_y
            d_xy = math.sqrt(away_x * away_x + away_y * away_y)
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)

            # d3 >= d0 ise YATAY itme yok. (Dikey kural AYRI tarama
            # yapiyor ve YATAY mesafeye bakiyor — bkz. _dikey_hesapla.)
            if d3 >= p.d0:
                continue

            # r_min ve min_d3 xy_guard'DAN ONCE — 23 Agustos 2026.
            #
            # ESKIDEN xy_guard kapisi `continue` ile komsuyu TAMAMEN
            # listeden dusuruyordu: tam tepedeki/altindaki komsu ne
            # catisma kumesine, ne emniyet projeksiyonuna, ne de acil
            # slew'e giriyordu. Yani ucagin TAM USTUNDEN gecen komsuya
            # karsi koruma SIFIRDI (CA.md B2, acik soru #5).
            #
            # Dikey yol vermede ucaklarin ust uste gelmesi ARIZA DEGIL,
            # TASARIMIN KENDISI. O yuzden kor nokta istisnai bir hal
            # olmaktan cikip NORMAL hale geliyordu; duzeltilmeden dikey
            # acilamazdi.
            #
            # Artik xy_guard yalnizca YATAY YON VEKTORUNU koruyor
            # (0'a bolme), komsuyu listeden dusurmuyor.
            if d3 <= p.r_min:
                any_within_rmin = True
            if d3 < min_d3:
                min_d3 = d3

            if d_xy < p.xy_guard:
                continue

            ux = away_x / d_xy
            uy = away_y / d_xy

            c = -(n.rel_x * n.rel_vx + n.rel_y * n.rel_vy
                  + n.rel_z * n.rel_vz) / d3

            # KAPI — 22 Agustos 2026'da SUREKLI hale getirildi.
            #
            # ESKI HALI BASAMAKLIYDI:
            #     d3 <= hard  -> gate = 1.0            (tam kuvvet)
            #     d3 >  hard  -> gate = smoothstep(c)  (yavas yaklasmada ~0)
            # `hard` sinirini gecerken kapi ANINDA 0'dan 1'e atliyordu.
            # Ucak itilip disari cikiyor -> kapi kapaniyor -> itme sifir ->
            # geri yaklasiyor -> kapi aciliyor. Hedef hiz zipliyor, ucak
            # surekli hizlanip frenliyor.
            #
            # UCUSTA OLCULDU (ylp00, 22 Agustos): kacis evresinde roll
            # -24.7..+28.3 derece (53 derecelik yalpa), maks egim 34 derece.
            # Asili evrede yalniz 11.6 idi. Operator "devrilecek gibi sag sol
            # yapti" dedi ve haklıydi.
            #
            # YENI HALI: mesafe kapisi ile kapanma hizi kapisinin BUYUGU
            # aliniyor. Mesafe kapisi `hard + damp_band`ta 0, `hard`ta 1 —
            # yani kabuga yaklasirken kapi YUMUSAKCA aciliyor, basamak yok.
            # Icerideki tam kuvvet ve disarideki kapanma hizi mantigi AYNEN
            # korunuyor; yalniz aradaki sicrama gidiyor.
            if p.c_ref > 1e-6:
                gate_c = _smoothstep((c - p.c_dead) / p.c_ref)
            else:
                gate_c = 1.0
            # Rampa genisligi `damp_band`e (0.5 m) baglanmisti; cok dar
            # kaldi ve 0.2 m'de 3.2 m/s'lik sicrama uretti. Etki alaninin
            # DORTTE BIRI daha yumusak: d0=10 hard=6 icin 1.0 m.
            _band = max(0.25 * (p.d0 - p.hard), p.damp_band)
            if _band > 1e-6:
                gate_d = _smoothstep((p.hard + _band - d3) / _band)
            else:
                gate_d = 1.0 if d3 <= p.hard else 0.0
            gate = max(gate_c, gate_d)

            mag = self._repulsion_magnitude(d3) * gate
            dist_scale = (
                _smoothstep((p.d0 - d3) / (p.d0 - p.hard))
                if p.d0 > p.hard + 1e-6 else 1.0
            )
            # SONUMLEME TABANI — 22 Agustos 2026, olculdu ve duzeltildi.
            #
            # `c` kapanma hizi: yaklasirken +, UZAKLASIRKEN -. Tabansiz
            # birakilinca uzaklasan komsuda damp NEGATIF oluyor ve
            # `f_radial = mag + damp` isaret degistirip KOMSUYA DOGRU itiyor.
            #
            # OLCULDU (d0=10 hard=6): komsu 2 m/s uzaklasirken 6.5 m'de CA
            # 1.34 m/s KOMSUYA DOGRU komut veriyordu. Yani carpisma onleme
            # giden komsuyu KOVALIYORDU.
            #
            # Klasik yay-sonumleyicide negatif damp dogrudur (mesafeyi
            # KORUMAK icin), ama burasi mesafe koruma degil CARPISMA
            # ONLEME: uzaklasmanin bir zarari yok, geri cekmenin anlami yok.
            # Aralik korumasi formation_node'un isi.
            #
            # 21 Agustos ucusunda kayittaki ters yonlu kacis satirlari
            # (v=(-0.02,0.15), v=(-0.04,0.29)) bunun sahadaki izidir.
            damp = p.c_damp * max(0.0, c) * dist_scale
            tan_env = (
                _smoothstep((p.d0 - d3) / (0.5 * (p.d0 - p.hard)))
                if p.d0 > p.hard + 1e-6 else 1.0
            )
            mag_tan = p.f_sat * gate * tan_env
            # YATAY SON CARE KAPISI — operator karari, 23 Agustos 2026.
            #
            # Yatay itme d0'da DEGIL, sert kabukta acilir. Disarida saf
            # dikey calisir ve formasyon geometrisine hic dokunulmaz;
            # iceride dikey yetisememis demektir ve yatay devreye girer.
            # Gerekce ve olcumler: CaParams.k_yatay.
            _yesik = p.yatay_esik_m if p.yatay_esik_m > 0.0 else p.hard
            _yband = max(0.3, 0.2 * _yesik)
            yatay_zarf = p.k_yatay * _smoothstep(
                (_yesik + _yband - d3) / _yband)
            mag *= yatay_zarf
            damp *= yatay_zarf
            mag_tan *= yatay_zarf
            if mag > 1e-9 or abs(damp) > 1e-9 or mag_tan > 1e-9:
                active.append((ux, uy, mag, damp, mag_tan))

        # DIKEY once hesaplanir: saf dikey kipte (k_yatay=0) `active`
        # HER ZAMAN bos kalir ve asagidaki erken cikis dikeyi hic
        # calistirmazdi. Bu, kipi sessizce olu birakan bir tuzakti.
        vz, dikey_aktif = self._dikey_hesapla(vfz, neighbors, h_now, kor)

        if not active and not any_within_rmin and not dikey_aktif:
            # YALNIZ YATAY durum sifirlanir. `reset()` cagrilamaz cunku o
            # dikey durumu da siler: ucak katmanina cikmis ve "yeterince
            # ayrigim" diyorsa bu tikte dikey mudahale YOK — ama catisma
            # bitince nominale donebilmesi icin `_mudahale_ettim`in
            # hatirlanmasi sart. Silinseydi ucak kazandigi irtifada
            # SUREKLI kalirdi.
            self._prev_vx, self._prev_vy, self._prev_vz = vfx, vfy, vfz
            self._emergency = False
            return (vfx, vfy, vfz), False

        vx, vy = vfx, vfy
        for ux, uy, mag, damp, mag_tan in active:
            f_radial = mag + damp
            vx += f_radial * ux
            vy += f_radial * uy
            tx, ty = self._tangent(vfx, vfy, ux, uy, mag_tan)
            vx += tx
            vy += ty

        vx, vy = clamp_speed_xy(vx, vy, p.v_max)
        # EMNIYET PROJEKSIYONU k_yatay'DAN BAGIMSIZ — operator karari.
        # Bu bir itme degil: r_min icinde hiz vektorunun komsuya YAKLASAN
        # bileseni sifirlanir. Yeni yanal hareket uretmez, yalnizca
        # "ustune gitme"yi keser. Saf dikey kipte de acik kalir.
        vx, vy = self._safety_projection(vx, vy, neighbors)

        # SLEW YALNIZ YATAY MUDAHALE VARSA — 23 Agustos 2026, birim test
        # yakaladi.
        #
        # `_apply_slew` CA'nin KENDI kacis komutunun ne kadar hizli
        # degisecegini sinirlamak icin var. Saf dikey kipte (k_yatay=0)
        # `active` her zaman bos, yani CA yatayda hicbir sey yapmiyor —
        # ama slew yine de calisip GOREVIN hizini kirpiyordu: testte
        # 2.0 m/s'lik komut 0.2 m/s'ye dusuyordu. Yani "yatay itme yok"
        # dedigimiz kip, formasyonu sessizce frenliyordu.
        #
        # Acil durum histerezisi her kosulda guncellenir (min_d3'e bagli),
        # cunku yatay mudahale sonradan devreye girerse dogru esikten
        # baslamali.
        self._emergency_guncelle(min_d3)
        if active:
            vx, vy = self._slew_kirp(vx, vy)

        if not _finite(vx, vy):
            vx, vy = self._prev_vx, self._prev_vy
        if not _finite(vz):
            vz = self._prev_vz

        self._prev_vx, self._prev_vy, self._prev_vz = vx, vy, vz
        return (vx, vy, vz), True

    def reset(self, v_current: tuple[float, float, float]) -> None:
        """Slew baslangicini son okunan hiza esitler."""
        self._prev_vx = float(v_current[0])
        self._prev_vy = float(v_current[1])
        self._prev_vz = float(v_current[2])
        self._emergency = False
        self._dikey_sifirla()

    def _dikey_sifirla(self) -> None:
        """Dikey yol verme durumunu bosa alir."""
        self._catisma_aktif = False
        self._mudahale_ettim = False
        self._dikey_yon = 0
        self._donus_sayaci = 0.0
        self.dikey_yetersiz = False
        self.dikey_donus_kor = False

    # =====================================================================
    # DIKEY YOL VERME
    # =====================================================================
    #
    # KURAL (23 Agustos 2026, operator karari):
    #   "Kim hareket eder"  -> yalnizca CATISMA riskinde olanlar
    #   "Nereye gider"      -> BENDEN KUCUK kimlikli catisan komsunun
    #                          OLCULEN irtifasindan KATMAN kadar uzaga
    #
    # Neden komsunun KARARI degil OLCUMU: iki ucagin birbirinin catisma
    # listesini tahmin etmesi gerekseydi listeler tutmazdi. Klasik ornek,
    # 4 m aralikta cizgi formasyonu, kusursuz mesh ile bile:
    #     drone1 gorur {2}      -> siralamada 1. -> +0
    #     drone2 gorur {1,3}    -> siralamada 2. -> +1 katman
    #     drone3 gorur {2}      -> siralamada 2. -> +1 katman
    #                                        ^^^ 2 ve 3 AYNI KATMANDA
    # Kimse paket kaybetmedi; sorun "catisma" ikili bir iliski ama rutbe
    # sirali bir liste. Olculen irtifayi takip etmek bu sorunu tamamen
    # ortadan kaldiriyor: drone3 drone2'nin NEREDE OLDUGUNU biliyor,
    # NE DUSUNDUGUNU bilmesi gerekmiyor.
    #
    # DONGU IMKANSIZ: herkes yalnizca KENDINDEN KUCUK kimlige tepki verir,
    # yani bagimlilik zinciri her zaman en kucuk kimlikte biter. En kucuk
    # kimlik CAPADIR ve dikeyde hic kipirdamaz.
    #
    # KASKAD BEDAVA: gorev irtifa degisimi komutu verirse (QR "20 m'ye
    # cik") capa tirmanir, drone2 onu katman ustten, drone3 drone2'yi
    # katman ustten takip eder. Merdiven gorevle birlikte yukselir; bunun
    # icin ayrica kod yok.
    #
    # CATISMA TESTI YATAY MESAFEYE BAKAR, 3B'YE DEGIL — bilincli.
    # 3B olsaydi: ucak tirmanir -> 3B mesafe buyur -> catisma biter ->
    # iner -> mesafe kuculur -> yine tirmanir. SALINIM. Yatay mesafe
    # tirmanmaktan etkilenmedigi icin tetik kararli kaliyor; catisma
    # ancak ucaklar gercekten yanal ayrildiginda bitiyor.
    def _dikey_hesapla(
        self,
        vfz: float,
        neighbors: list[NeighborObs],
        h_now: float | None,
        kor: bool = False,
    ) -> tuple[float, bool]:
        """Dikey yol verme hizini doner. (vz, dikey_aktif)

        vz NED: NEGATIF = TIRMANMA. Isaret hatasi ucagi komsusunun
        uzerine surer; birim testte kilitlendi.
        """
        p = self.p
        if p.k_dikey <= 0.0 or h_now is None or p.agent_id <= 0:
            self._dikey_sifirla()
            return vfz, False

        # Histerezis: giris d0'da, cikis d0 + hist_m. Tam d0'da asili
        # duran iki ucak merdiveni acip kapatmasin.
        esik = p.d0 + (p.hist_m if self._catisma_aktif else 0.0)

        # rel_z = benim_irtifam - komsunun_irtifasi (NED, z asagi pozitif).
        rel_z_listesi: list[float] = []
        # Referans ucak: catistigim EN KUCUK kimlikli komsu. Donusumlu
        # merdivenin sifir noktasi odur.
        ref_id = 0
        ref_rel_z = 0.0
        catisma = False

        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z):
                continue
            if math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y) >= esik:
                continue
            catisma = True
            # RUTBE: yalnizca benden KUCUK kimlige yol veririm.
            # agent_id=0 (bilinmiyor) -> dikey kural uygulanmaz.
            if n.agent_id <= 0 or n.agent_id >= p.agent_id:
                continue
            rel_z_listesi.append(n.rel_z)
            if ref_id == 0 or n.agent_id < ref_id:
                ref_id = n.agent_id
                ref_rel_z = n.rel_z

        # --- CATISMA YOK: nominale donus ---------------------------------
        if not catisma:
            if not self._mudahale_ettim:
                self._catisma_aktif = False
                return vfz, False
            self._dikey_yon = 0

            # 🔴 KORLUKTE DONME — 23 Agustos 2026, operator sorusu uzerine.
            #
            # "Catisma bitti" karari komsunun 4.5 m'den UZAKTA olmasina
            # dayaniyor. Ama komsuyu KAYBETMEK de ayni gorunuyor: bayat
            # veri listeden dusuyor, catisma false oluyor ve ucak 2 saniye
            # sonra kazandigi 3 m'lik ayrimi GERI VERIYOR — hem de
            # komsusunun nerede oldugunu bilmedigi anda.
            #
            # 21 Agustos'ta mesh 46.4 saniye TEK YONLU oldu (TUZAKLAR
            # 2.15). O sirada bu kod olsaydi ucak ayrimi birakirdi.
            #
            # Dugumun kendi yorumunda yazili ilke: "komsuyu kaybetmek
            # 'engel yok' DEGIL, 'nerede oldugunu BILMIYORUM' demektir."
            # Yatay tutmada uygulanmisti (korluk_tut_s), dikeyde degildi.
            #
            # Davranis: irtifayi TUT, sayaci ILERLETME. Komsu tekrar
            # gorulunce ya merdiven surer ya normal donus baslar. Mesh
            # kalici koparsa ucak 3 m yukarida kalir — GUVENLI taraf, ve
            # korluk alarmi zaten YKI'ye kritik uyari basiyor.
            if kor:
                self.dikey_donus_kor = True
                return self._dikey_slew(0.0), True
            self.dikey_donus_kor = False

            self._donus_sayaci += p.dt
            if self._donus_sayaci < p.donus_bekleme_s:
                # Bekleme evresinde IRTIFAYI TUT. Catisma biter bitmez
                # inmeye baslamak, komsunun geri gelmesi halinde ayrimi
                # tam da en kotu anda kapatirdi.
                return self._dikey_slew(0.0), True
            # Nominal, donus evresinde de gorevle birlikte yurur.
            self._h_nominal -= vfz * p.dt
            fark = h_now - self._h_nominal
            if abs(fark) <= p.donus_tolerans_m:
                self._dikey_sifirla()
                return vfz, False
            # NED: asagi = POZITIF vz. Gorev hizi yine ileri-besleme.
            duzeltme = max(-p.donus_hiz_mps,
                           min(p.donus_hiz_mps, p.kp_dikey * fark))
            return self._dikey_slew(vfz + duzeltme), True

        # --- CATISMA VAR --------------------------------------------------
        self._catisma_aktif = True
        self._donus_sayaci = 0.0

        # HEPSINDEN katman kadar ayrik miyim? Oyleyse yapacak bir sey yok.
        # Bu test KOMSU KOMSU: iki komsunun ARASINDA olup ikisinden de
        # yeterince uzak olmak da gecerli bir cozumdur, bosuna hareket etme.
        tatmin = all(abs(rz) >= p.katman_m for rz in rel_z_listesi)

        if not rel_z_listesi or tatmin:
            # CAPAYIM (ya da zaten yeterince ayrigim): DIKEYE HIC DOKUNMAM.
            #
            # 🔴 Burasi bir kez YANLIS yazildi ve birim test yakaladi:
            # "catisma var, irtifayi tut" denmisti. O halde QR'dan gelen
            # "20 m'ye cik" komutunda CAPA TIRMANMAZ ve arkasindaki butun
            # merdiven donar — dikey kaciSin kaskad ozelligi olur.
            #
            # Dogrusu: gorev dikeyin sahibidir; yalnizca YOL VERMEK ZORUNDA
            # OLAN ucak dikeye mudahale eder. Capa tirmanirsa buyuk kimlikli
            # komsular onu olculen irtifasindan takip eder ve merdiven
            # gorevle birlikte yukselir.
            # 🔴🔴 YO-YO — 23 Agustos 2026, ILK UCUSTA SAHADA GORULDU.
            #
            # Burasi once `return vfz, False` idi: ayrim saglaninca CA
            # dikey yetkiyi GOREV katmanina geri veriyordu. Operator
            # gozlemi:
            #
            #   "02 sürekli kendini aşağı bırakıyor ama 00 risk alanında
            #    durduğu için tekrar yukarı atıyor. Yoyo gibi gidip
            #    geliyordu."
            #
            # SEBEP: guided gorev setpoint'i bir KONUM hedefi (asili
            # durulan 4.8 m). Yetki birakilinca PX4 o hedefi gorup ucagi
            # asagi cekiyor; inerken ayrim katman'in altina dusuyor, CA
            # tekrar devreye giriyor, yukari atiyor, ayrim saglanir
            # saglanmaz yine birakiyor... Kayittan olculdu: gaz %12'ye
            # inip %100'e cikiyor, anlik inis -1.48 m/s (= MPC_Z_VEL_MAX_DN).
            #
            # Yani "ayrim saglandi" KARARLI BIR DURUM DEGILDI: yetkiyi
            # birakmak, saglandi olmasinin SEBEBINI ortadan kaldiriyordu.
            #
            # NE BENZETIM NE BIRIM TEST YAKALADI:
            #   * benzetimde "gorev" bir HIZ komutu (sifir) — birakinca
            #     ucak yerinde kaliyor, geri ceken bir sey yok
            #   * test_zaten_katman_kadar_ayrikken_KOMUT_YOK "ayrikken
            #     komut yok"u dogruluyordu ama SONRASINI hic sormuyordu
            #
            # DOGRUSU: ayrimi BEN kurduysam ve catisma suruyorsa yetkiyi
            # TUTARIM — ama gorevin dikey HIZ niyetini (vfz) gecireyim ki
            # suru topluca tirmanirken merdiven onunla yukselsin (o da
            # ayri bir birim testle kilitli). Guided asili durmada
            # `velocity_valid` yok, vfz=0 gelir ve ucak irtifasini korur.
            #
            # Hic mudahale etmediysem birakmak dogru: gereksiz yere yetki
            # almayayim (or. komsu zaten 10 m yukarida).
            if not self._mudahale_ettim:
                return vfz, False
            return self._dikey_slew(vfz), True

        if not self._mudahale_ettim:
            # Ilk mudahale ani: nominal irtifayi burada dondur. Donus
            # hedefi ve tavan hesabi buna gore.
            self._mudahale_ettim = True
            self._h_nominal = h_now

        # YON SECIMI: KUME OLARAK, komsu komsu DEGIL.
        #
        # 🔴 Ilk yazim her komsuya AYRI yon seciyordu ("altimdakinden yukari,
        # ustumdekinden asagi") ve birim test kararli ama YANLIS bir dengeye
        # oturdugunu gosterdi:
        #     drone1 10 m'de, drone2 13 m'de, drone3 10 m'den basliyor
        #     -> drone3 drone1'den 3 m uzaklasip TAM DRONE2'NIN IRTIFASINDA
        #        duruyordu (13.00 m). Cunku drone1'in talebi sifira inerken
        #        drone2'nin talebi hic karsilanmiyordu.
        #
        # Dogrusu: BUTUN kucuk kimliklerin USTUNE ya da ALTINA gec. Ikisi de
        # hepsini birden saglar; ucuzu secilir. Boylece "ustunden gecmek"
        # zorunlu degil — cogu zaman altina inmek daha kisa ve daha az
        # irtifa harciyor.
        if p.rutbe > 0:
            # DONUSUMLU MERDIVEN — kadrodaki sabit rutbeden. Hedefler
            # bastan farkli oldugu icin yaris yok. Gerekce CaParams.rutbe.
            kat = (p.rutbe + 1) // 2                 # 1,1,2,2,3,3...
            isaret = 1.0 if p.rutbe % 2 == 1 else -1.0
            # referansin OLCULEN irtifasi
            h_ref = h_now - ref_rel_z
            h_hedef = h_ref + isaret * kat * p.katman_m
            if h_hedef < p.dikey_taban_m:
                # Asagi katman irtifa kapisinin altina dusuyor: yukari
                # aynala. Ayni rutbe her ucakta ayni sonucu verdigi icin
                # tutarlilik bozulmaz.
                h_hedef = h_ref + kat * p.katman_m
                self.dikey_yetersiz = True
            if p.irtifa_tavan_m > 0.0 and h_hedef > p.irtifa_tavan_m:
                h_hedef = p.irtifa_tavan_m
                self.dikey_yetersiz = True
            hata_h = h_hedef - h_now
            self._h_nominal -= vfz * p.dt
            vz_cmd = vfz - p.kp_dikey * hata_h
            vz_cmd = max(-p.v_dikey_max, min(p.v_dikey_max, vz_cmd))
            return self._dikey_slew(vz_cmd), True

        # --- RUTBE BILINMIYOR: en ucuz yon (yedek yol) --------------------
        h_en_yuksek_komsu = h_now - min(rel_z_listesi)
        h_en_alcak_komsu = h_now - max(rel_z_listesi)
        hedef_yukari = h_en_yuksek_komsu + p.katman_m
        hedef_asagi = h_en_alcak_komsu - p.katman_m
        maliyet_yukari = hedef_yukari - h_now
        maliyet_asagi = h_now - hedef_asagi

        # Asagi secenegi irtifa kapisinin altina inemez.
        asagi_uygun = hedef_asagi >= p.dikey_taban_m

        # YON YAPISKAN — 23 Agustos 2026, birim test yakaladi.
        #
        # Yon her tik yeniden secilseydi manevranin ortasinda DONERDI:
        # ilk tikte esitlik YUKARI'ya kirilir, ama dikey ivme rampasi
        # (0.05 m/s per tik) yuzunden ilk yarim saniyede komsu one gecer,
        # rel_z negatiflesir ve "asagi daha ucuz" olur. Olculen sonuc:
        # ucak once tirmaniyor, sonra fikir degistirip aliyordu.
        #
        # Bir KACIS MANEVRASINDA kararsizlik kabul edilemez: hem zaman
        # kaybi hem operator icin ongorulemez davranis. Yon bir kez
        # secilir ve catisma bitene kadar korunur.
        if self._dikey_yon == 0:
            self._dikey_yon = (
                1 if (not asagi_uygun or maliyet_yukari <= maliyet_asagi)
                else -1
            )
        elif self._dikey_yon == -1 and not asagi_uygun:
            # Sectigimiz yon artik uygun degil (taban engelliyor).
            self._dikey_yon = 1
            self.dikey_yetersiz = True

        h_hedef = hedef_yukari if self._dikey_yon > 0 else hedef_asagi

        # MUTLAK IRTIFA TAVANI (0 = kapali). Asilirsa gereken ayrim
        # SAGLANAMIYOR demektir; sessiz kalmasin.
        if p.irtifa_tavan_m > 0.0 and h_hedef > p.irtifa_tavan_m:
            h_hedef = p.irtifa_tavan_m
            self.dikey_yetersiz = True
        elif not asagi_uygun and maliyet_yukari > maliyet_asagi:
            # Asagi daha kisaydi ama taban engelledi; yukari gidiyoruz.
            # Tehlike degil, ama beklenenden fazla irtifa harcaniyor.
            self.dikey_yetersiz = True

        # Nominal irtifa GOREVLE BIRLIKTE yurur: gorev bu sirada tirmanma
        # komutu veriyorsa donus hedefi de tirmanmis olur.
        self._h_nominal -= vfz * p.dt             # NED: vfz<0 -> h artar

        hata_h = h_hedef - h_now                  # + = yukari cikmaliyim
        # GOREV DIKEY HIZI ILERI-BESLEME olarak eklenir — birim test
        # yakaladi. Oncesinde dikey mudahale gorevin dikey komutunu
        # TAMAMEN eziyordu: suru topluca tirmanirken (QR "20 m'ye cik")
        # takipci ucak tirmanmayi birakip merdivenin altinda kaliyordu.
        # Ileri-besleme ile iki terim toplaniyor: gorevle yuksel VE
        # ofset hatani duzelt.
        vz_cmd = vfz - p.kp_dikey * hata_h        # NED: yukari = NEGATIF
        vz_cmd = max(-p.v_dikey_max, min(p.v_dikey_max, vz_cmd))
        return self._dikey_slew(vz_cmd), True

    def _dikey_slew(self, vz: float) -> float:
        """Dikey hiz degisimini ivme tavaniyla sinirlar.

        Basamak komut motorlara ani yuk bindirir; aski gazi zaten %66 ve
        itki payi olculmedi (TUZAKLAR §0.3).
        """
        p = self.p
        maks = p.a_dikey_max * p.dt
        d = vz - self._prev_vz
        if abs(d) > maks:
            return self._prev_vz + math.copysign(maks, d)
        return vz

    def _repulsion_magnitude(self, d: float) -> float:
        """Etki alanindaki itme buyuklugunu hesaplar."""
        p = self.p
        if d >= p.d0:
            return 0.0
        if d <= p.hard:
            return p.f_sat
        t = (p.d0 - d) / (p.d0 - p.hard)
        return p.f_sat * _smoothstep(t)

    def _tangent(
        self, vfx: float, vfy: float, ux: float, uy: float, mag_rep: float,
    ) -> tuple[float, float]:
        """Kafa kafaya karsilasma durumunu cozen teget sapmasini doner."""
        vf_h = math.sqrt(vfx * vfx + vfy * vfy)
        if vf_h < 1e-3 or mag_rep < 1e-9:
            return 0.0, 0.0
        cos_a = (vfx * ux + vfy * uy) / vf_h
        w = max(0.0, -cos_a)
        if w < 1e-4:
            return 0.0, 0.0
        tx = uy
        ty = -ux
        f = self.p.k_tan * w * mag_rep
        return f * tx, f * ty

    def _safety_projection(
        self, vx: float, vy: float, neighbors: list[NeighborObs],
    ) -> tuple[float, float]:
        """Emniyet siniri altinda yaklasma hizini sifirlar."""
        p = self.p
        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z):
                continue
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)
            if d3 > p.r_min:
                continue
            d_xy = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y)
            if d_xy < 1e-3:
                continue
            tx = n.rel_x / d_xy
            ty = n.rel_y / d_xy
            v_close = vx * tx + vy * ty
            if v_close > 0.0:
                vx -= v_close * tx
                vy -= v_close * ty
        return vx, vy

    def _emergency_guncelle(self, min_d3: float) -> None:
        """Acil durum bayragini histerezis ile gunceller."""
        p = self.p
        if not self._emergency and min_d3 < p.hard:
            self._emergency = True
        elif self._emergency and min_d3 > p.hard + p.hyst_band:
            self._emergency = False

    def _apply_slew(
        self, vx: float, vy: float, min_d3: float,
    ) -> tuple[float, float]:
        """Hiz degisim ivmesini histerezis ile sinirlar."""
        self._emergency_guncelle(min_d3)
        return self._slew_kirp(vx, vy)

    def _slew_kirp(self, vx: float, vy: float) -> tuple[float, float]:
        """Yatay hiz degisimini ivme tavaniyla kirpar."""
        p = self.p
        max_delta = (
            p.slew_emergency if self._emergency else p.slew_normal
        ) * p.dt
        dvx = vx - self._prev_vx
        dvy = vy - self._prev_vy
        d = math.sqrt(dvx * dvx + dvy * dvy)
        if d > max_delta and d > 1e-9:
            s = max_delta / d
            return self._prev_vx + dvx * s, self._prev_vy + dvy * s
        return vx, vy
