#!/usr/bin/env python3
# Copyright 2026 Yelpence
r"""PIL TESTI — ucakta KAYDEDER, sonra (ROS'suz) COZUMLER.

NIYE AYRI BIR LOG (3 Eylul 2026, operator istegi)
-------------------------------------------------
Veri zaten rosbag'de var, ama pil testi icin ise yaramiyor: alanlar
DORT AYRI KONUDA ve DORT AYRI HIZDA akiyor (thrust 10 Hz, PWM 10 Hz,
FCU pili 4 Hz, INA226 2 Hz). "Gaz su anda kacti, gerilim o anda neydi"
sorusunu cevaplamak icin hepsini TEK ZAMAN EKSENINE oturtmak gerekiyor ve
bunu her cozumlemede yeniden yapmak hem yavas hem hataya acik.

Bu betik ucakta kosar, hepsini tek satirda ayni damgayla yazar. Mesh'e
HICBIR SEY gitmez — dosya Pi'de kalir, sonra okunur. Boyut: 5 Hz'de
satir ~120 bayt, 20 dakikalik test ~700 KB.

🔴 AKIM HICBIR YERDEN OLCULMUYOR (3 Eylul, operator dogruladi)
`ina226_node` parametresi `sont_ohm = 0.0`; `ina226.akim_a()` bu durumda
0.0 donuyor. FCU'nun kendi pil olcumu de yok (asagiya bak). Yani su anda
elimizde YALNIZ GERILIM var. Bunun sonucu: **mAh, Wh, W ve ic direnc
VERILEMEZ** — betik bunlari sifir olarak basmiyor, "olculmuyor" diyor.
Sifir bir olcum degil, olcum yoklugudur.

Akimsiz elde kalanlar (ve testin asil ciktisi):
  * gerilimin DUSUS HIZI (V/dakika) ve esige kalan sure kestirimi
  * COKME: yukteki en dusuk gerilim ile inisten sonraki dinlenme gerilimi
    farki — ic direncin akimsiz vekili, ayni pil/profil icin karsilastirilir
  * HOVER GAZININ SURUKLENMESI: pil dustukce gaz artar; gaz-gerilim egimi
  * motorlar arasi DENGESIZLIK

Sont direnci girilirse (`INA226_SONT_OHM`) betik akim yolunu KENDILIGINDEN
acar; kod hazir, veri yok.

🔴 GERCEK MOTOR DEVRI OLCULMUYOR — 3 Eylul'de ylp02'de dogrulandi:
    /mavros/esc_telemetry/telemetry   VERI YOK
    /mavros/esc_status/status         VERI YOK
    /mavros/esc_status/info           VERI YOK
ESC'ler telemetri gondermiyor. Elimizdeki "motorun ne kadar dondugu"
olcusu, ucus kontrolcusunun her motora verdigi PWM KOMUTU (`rc/out`,
4 aktif kanal). Bu komuttur, sonuc degildir: tikali bir motor ya da
bozulmus bir pervane KOMUT olarak gorunmez. Yine de dengesizligi
yakalamak icin yeterli — bir motor digerlerinden yuksek PWM aliyorsa
o kol daha cok itki uretmek zorunda kaliyor demektir.
Gercek devir istiyorsak DShot telemetri hattini baglamak gerekir; o ayri
bir donanim isi (YAPILACAKLAR).

KULLANIM
--------
1) UCAKTA KAYIT (konteynerde, ucus boyunca acik kalir):
     ./deploy/yki/drone_bul.sh ylp02 "docker exec -d -e ROS_LOCALHOST_ONLY=1 \\
        drone3 python3 /ws/pil_testi.py kaydet --ajan 3"
   Durdurmak: dosyaya bir kez SIGINT (asagida "durdur" komutu) ya da
   konteyner restart. Her satir aninda diske yazilir (flush), yani guc
   kesilse bile EN COK SON SATIR kaybolur — rosbag'in metadata sorunu
   burada YOK.

2) COZUMLEME (laptopta da kosar, ROS GEREKMEZ):
     python3 deploy/rpi/teshis/pil_testi.py coz --csv ylp02_20260903.csv
     python3 ... coz --csv dosya.csv --cizelge      # 30 sn'lik ozet tablo

3) Dosyayi laptopa almak:
     ./deploy/yki/drone_bul.sh ylp02 'cat ~/yelpence_ws/pil_testi/<ad>.csv' > yerel.csv
"""

import argparse
import csv
import math
import os
import signal
import sys
import time

# --- Sabitler --------------------------------------------------------------

# PWM tavan/taban: PX4 varsayilani. Yuzdeye cevirmek icin; ham deger de
# yaziliyor, yani yanlissa cozumlemede --pwm-min/--pwm-max ile duzeltilir.
PWM_MIN_VARS = 1000.0
PWM_MAX_VARS = 2000.0

# Asili durma (hover) tespiti. Ucak arm'li, yatay+dikey hizi kucuk ve bu
# hal en az MIN_SURE surmus olmali. Esikler gevsek secildi: ruzgarda
# konum tutan ucak 0.3-0.4 m/s salinim yapiyor ve daha dar bir esik
# hover'i HIC bulamiyordu.
HOVER_HIZ_ESIK = 0.5      # m/s
HOVER_MIN_SURE = 8.0      # sn


def _dosya_adi(kok):
    """Istanbul damgali cikti yolu."""
    os.makedirs(kok, exist_ok=True)
    ad = f"{os.uname().nodename}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    return os.path.join(kok, ad)


BASLIKLAR = [
    't_epoch', 't_rel', 'armed', 'mod', 'irtifa_m', 'hiz_mps',
    'thrust', 'pwm1', 'pwm2', 'pwm3', 'pwm4',
    'v_fcu', 'i_fcu', 'v_ina', 'i_ina', 'ivme_rms',
]


# --- KAYIT KIPI (ucakta, ROS gerekir) --------------------------------------

def kaydet(a):
    """Konulari dinler, sabit hizda TEK SATIRA yazar."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data

    from geometry_msgs.msg import TwistStamped
    from mavros_msgs.msg import Altitude, AttitudeTarget, RCOut, State
    from sensor_msgs.msg import BatteryState, Imu

    ns = f'/drone_{a.ajan}'
    yol = a.cikti or _dosya_adi('/ws/pil_testi')

    class PilTesti(Node):
        """Tek satirlik pil testi kaydedicisi."""

        def __init__(self):
            """Abonelikleri kurar ve CSV'yi acar."""
            super().__init__('pil_testi')
            self.son = {k: None for k in BASLIKLAR}
            self.pwm = [None] * 4
            self.t0 = None
            self.n = 0

            # 🔴 QoS: MAVROS'un telemetri konulari BEST_EFFORT yayinliyor.
            # RELIABLE abone olursak HICBIR SEY almayiz ve dosya bos kalir
            # (TUZAKLAR 2.1 — sessiz uyusmazlik).
            q = qos_profile_sensor_data
            self.create_subscription(
                State, f'{ns}/mavros/state', self._durum, 10)
            self.create_subscription(
                Altitude, f'{ns}/mavros/altitude', self._irtifa, q)
            self.create_subscription(
                TwistStamped, f'{ns}/mavros/local_position/velocity_local',
                self._hiz, q)
            self.create_subscription(
                AttitudeTarget, f'{ns}/mavros/setpoint_raw/target_attitude',
                self._itki, q)
            self.create_subscription(
                RCOut, f'{ns}/mavros/rc/out', self._pwm, q)
            self.create_subscription(
                BatteryState, f'{ns}/mavros/battery', self._pil_fcu, q)
            # 🔴 INA226 DA BEST_EFFORT. Ilk surumde burada `10` (varsayilan
            # RELIABLE) yazmistim ve ucakta olculdu: "offering incompatible
            # QoS. No messages will be received" -> v_ina/i_ina sutunlari
            # BOM BOS cikti. Pil TEK gercek kaynak bu oldugu icin (FCU'nun
            # kendi pil olcumu yok, bkz. asagidaki 65.535 notu) test tamamen
            # ise yaramaz hale geliyordu. TUZAKLAR 2.1: QoS uyusmazligi
            # SESSIZDIR, yalniz bir WARN satiri birakir.
            self.create_subscription(
                BatteryState, f'{ns}/pil/ina226', self._pil_ina, q)
            self.create_subscription(
                Imu, f'{ns}/mavros/imu/data', self._imu, q)

            # 🔴 PID DOSYASI — desen eslestirme YERINE.
            # `pgrep -f pil_testi.py` uc ayri sekilde yanildi (3 Eylul):
            #   1) kontrol komutunun KENDI satirini yakaladi -> hep KOSUYOR
            #   2) tirnakli desen ic ice tirnakta bozuldu   -> hep DURDU
            #   3) [p]il_testi.py numarasi KABUK GLOBU oldu: konteynerin
            #      calisma dizini /ws ve orada pil_testi.py DURUYOR, yani
            #      bash deseni gercek ada genisletti ve (1) geri geldi.
            # PID dosyasinda desen yok: `kill -0 <pid>` ya vardir ya yoktur.
            self.pid_yolu = os.path.join(os.path.dirname(yol), '.pid')
            with open(self.pid_yolu, 'w', encoding='utf-8') as pf:
                pf.write(str(os.getpid()))

            self.f = open(yol, 'w', newline='', encoding='utf-8')
            self.yaz = csv.writer(self.f)
            self.yaz.writerow(BASLIKLAR)
            self.f.flush()
            self.get_logger().info(f'[pil_testi] yaziliyor: {yol}')
            self.create_timer(1.0 / max(0.2, a.hz), self._tik)

        # --- geri cagrimlar: yalniz SON degeri saklar ---------------------
        def _durum(self, m):
            self.son['armed'] = int(bool(m.armed))
            self.son['mod'] = m.mode

        def _irtifa(self, m):
            self.son['irtifa_m'] = float(m.relative)

        def _hiz(self, m):
            v = m.twist.linear
            self.son['hiz_mps'] = math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2)

        def _itki(self, m):
            self.son['thrust'] = float(m.thrust)

        def _pwm(self, m):
            # Ilk DORT kanal motorlar; gerisi 0 (3 Eylul'de ylp02'de
            # dogrulandi: kanal 5-16 sifir).
            for i in range(4):
                self.pwm[i] = (float(m.channels[i])
                               if i < len(m.channels) else None)

        def _pil_fcu(self, m):
            # 🔴 BU UCAKTA FCU PIL OLCUMU YOK. 3 Eylul'de ylp02'de olculdu:
            # voltage = 65.535 = 0xFFFF/1000, yani MAVLink'in "BILINMIYOR"
            # degeri. Pil, Pi'ye AYRI bagli INA226'dan okunuyor. Alan yine de
            # yaziliyor ki kaynak karisirsa gorulebilsin; cozumleme bu degeri
            # tanıyip "gecersiz" diyor, sayi UYDURMUYOR.
            self.son['v_fcu'] = float(m.voltage)
            # ROS sozlesmesinde bosalma NEGATIF; isareti burada ATMIYORUZ,
            # cozumlemede abs() aliniyor. Ham kalsin ki kaynak karisirsa
            # gorulebilsin.
            self.son['i_fcu'] = float(m.current)

        def _pil_ina(self, m):
            self.son['v_ina'] = float(m.voltage)
            self.son['i_ina'] = float(m.current)

        def _imu(self, m):
            g = m.linear_acceleration
            self.son['ivme_rms'] = math.sqrt(g.x ** 2 + g.y ** 2 + g.z ** 2)

        # --- ornekleme ----------------------------------------------------
        def _tik(self):
            """Sabit hizda tek satir yazar ve HEMEN diske gecirir."""
            simdi = time.time()
            if self.t0 is None:
                self.t0 = simdi
            s = dict(self.son)
            s['t_epoch'] = f'{simdi:.3f}'
            s['t_rel'] = f'{simdi - self.t0:.2f}'
            for i in range(4):
                s[f'pwm{i + 1}'] = self.pwm[i]
            self.yaz.writerow(
                ['' if s.get(k) is None else s[k] for k in BASLIKLAR])
            # 🔴 HER SATIRDA FLUSH. Ucus guc kesilerek bitiyor; rosbag'in
            # basina gelen ("metadata yalniz temiz kapanista yaziliyor")
            # burada tekrarlanmasin diye tamponu bekletmiyoruz. 5 Hz'de
            # maliyeti olculebilir degil.
            self.f.flush()
            self.n += 1
            if self.n % (int(a.hz) * 30) == 0:
                self.get_logger().info(
                    f'[pil_testi] {self.n} satir · '
                    f'{simdi - self.t0:.0f} sn · '
                    f'V={s.get("v_ina") or s.get("v_fcu")}')

    rclpy.init()
    d = PilTesti()

    def kapat(*_):
        d.f.flush()
        d.f.close()
        try:
            os.remove(d.pid_yolu)
        except OSError:
            pass
        print(f'\n[pil_testi] kapandi: {yol} ({d.n} satir)')
        rclpy.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, kapat)
    signal.signal(signal.SIGTERM, kapat)
    try:
        rclpy.spin(d)
    finally:
        try:
            d.f.close()
        except Exception:                                # noqa: BLE001
            pass


# --- COZUMLEME KIPI (ROS gerekmez, laptopta da kosar) ----------------------

def _oku(yol):
    """CSV'yi sozluk listesine cevirir; bos alanlar None kalir."""
    satirlar = []
    with open(yol, newline='', encoding='utf-8') as f:
        for s in csv.DictReader(f):
            g = {}
            for k, v in s.items():
                if v == '' or v is None:
                    g[k] = None
                elif k == 'mod':
                    g[k] = v
                else:
                    try:
                        g[k] = float(v)
                    except ValueError:
                        g[k] = None
            satirlar.append(g)
    return satirlar


def _ort(xs):
    """Ortalama; bos liste icin None."""
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    """Standart sapma; iki degerden azsa None."""
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _hover_dilimleri(satirlar, hiz_esik, min_sure):
    """Arm'li ve HIZI KUCUK ardisik dilimleri bulur."""
    dilimler, bas = [], None
    for i, s in enumerate(satirlar):
        uygun = (s.get('armed') == 1.0
                 and s.get('hiz_mps') is not None
                 and s['hiz_mps'] <= hiz_esik
                 and (s.get('irtifa_m') or 0.0) > 1.0)
        if uygun and bas is None:
            bas = i
        elif not uygun and bas is not None:
            if satirlar[i - 1]['t_rel'] - satirlar[bas]['t_rel'] >= min_sure:
                dilimler.append((bas, i - 1))
            bas = None
    if bas is not None:
        son = len(satirlar) - 1
        if satirlar[son]['t_rel'] - satirlar[bas]['t_rel'] >= min_sure:
            dilimler.append((bas, son))
    return dilimler


def _dogru_uydur(xs, ys):
    """En kucuk kareler dogrusu: (egim, kesisim). Yetersiz veride None."""
    ciftler = [(x, y) for x, y in zip(xs, ys)
               if x is not None and y is not None]
    if len(ciftler) < 3:
        return None, None
    n = len(ciftler)
    sx = sum(x for x, _ in ciftler)
    sy = sum(y for _, y in ciftler)
    sxx = sum(x * x for x, _ in ciftler)
    sxy = sum(x * y for x, y in ciftler)
    payda = n * sxx - sx * sx
    if abs(payda) < 1e-12:
        return None, None
    egim = (n * sxy - sx * sy) / payda
    return egim, (sy - egim * sx) / n


def _motor_ozeti(dilim, pwm_min, pwm_max):
    """Motor basina PWM ortalamasi, yuzdesi ve DENGESIZLIK."""
    ort = []
    for k in ('pwm1', 'pwm2', 'pwm3', 'pwm4'):
        ort.append(_ort([s.get(k) for s in dilim]))
    gecerli = [o for o in ort if o is not None]
    if not gecerli:
        return ort, None, None
    yayilim = max(gecerli) - min(gecerli)
    ortalama = sum(gecerli) / len(gecerli)
    araligi = max(1.0, pwm_max - pwm_min)
    yuzdeler = [None if o is None else 100.0 * (o - pwm_min) / araligi
                for o in ort]
    # Dengesizlik: motorlar arasi PWM yayiliminin komut araligina orani.
    dengesizlik = 100.0 * yayilim / araligi
    return list(zip(yuzdeler, ort)), dengesizlik, ortalama


def _mah(satirlar, akim_alani):
    """Akimi zamana gore integre eder -> (mAh, Wh). Isaret ATILIR."""
    mah = wh = 0.0
    onceki = None
    for s in satirlar:
        i = s.get(akim_alani)
        t = s.get('t_rel')
        v = s.get('v_ina') if akim_alani == 'i_ina' else s.get('v_fcu')
        if i is None or t is None:
            continue
        if onceki is not None:
            dt = t - onceki[0]
            if 0.0 < dt < 5.0:                 # bosluk varsa atla
                a = abs(i)
                mah += a * dt / 3.6            # A*sn -> mAh
                if v is not None:
                    wh += a * v * dt / 3600.0
        onceki = (t, i)
    return mah, wh


def _ic_direnc(satirlar, v_alani, i_alani):
    """Ic direnc (ohm) — ZAMAN EGILIMI AYRILARAK.

    🔴 TEK DEGISKENLI UYDURMA YANLIS SONUC VERIYOR. Gerilim iki sebeple
    duser: (a) anlik yuk (I x R), (b) pilin bosalmasi (zaman). V'yi yalniz
    I'ya uydurursak bosalma egilimi R'ye karisir. Sentetik kayitla olculdu:
    gercek 12 mohm, tek degiskenli uydurma 8 mohm verdi — %33 hata.

    Cozum: V = a + b*t + c*I iki degiskenli uydurma; R = -c. b bosalma
    egilimini soguruyor, c geriye saf yuk tepkisini birakiyor.
    """
    veri = [(s.get('t_rel'), s.get(v_alani),
             None if s.get(i_alani) is None else abs(s[i_alani]))
            for s in satirlar]
    veri = [(t, v, i) for t, v, i in veri
            if t is not None and v is not None and i is not None]
    if len(veri) < 30:
        return None
    akimlar = [i for _, _, i in veri]
    if max(akimlar) - min(akimlar) < 2.0:
        # Yuk hep ayni kaldiysa egim gurultudur; sayi UYDURMA.
        return None

    n = float(len(veri))
    st = sum(t for t, _, _ in veri)
    si = sum(i for _, _, i in veri)
    sv = sum(v for _, v, _ in veri)
    stt = sum(t * t for t, _, _ in veri)
    sii = sum(i * i for _, _, i in veri)
    sti = sum(t * i for t, _, i in veri)
    stv = sum(t * v for t, v, _ in veri)
    siv = sum(i * v for _, v, i in veri)

    # Normal denklemler (3x3), Cramer ile cozuluyor.
    A = [[n, st, si], [st, stt, sti], [si, sti, sii]]
    y = [sv, stv, siv]

    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    d = det3(A)
    if abs(d) < 1e-9:
        return None
    Ac = [[A[r][k] if k != 2 else y[r] for k in range(3)] for r in range(3)]
    c = det3(Ac) / d
    return -c


def _akim_olculuyor_mu(satirlar, alan):
    """Akim gercekten olculuyor mu, yoksa hep 0 mi.

    🔴 3 EYLUL: SONT DIRENCI YOK. `ina226_node` parametresi
    `sont_ohm = 0.0` ve `ina226.akim_a()` bu durumda 0.0 donuyor (kodda
    yazili: "Sont bilinmiyorsa 0.0"). Yani su anda AKIM HICBIR YERDEN
    OLCULMUYOR — ne INA226'dan ne FCU'dan; yalnizca GERILIM var.

    Bunu tespit etmezsek rapor "0 mAh, 0 W, ic direnc 0" yazar ve bunlar
    OLCUM gibi gorunur. Sifir bir olcum degil, olcum YOKLUGUDUR.
    """
    degerler = [abs(s[alan]) for s in satirlar if s.get(alan) is not None]
    if not degerler:
        return False
    return max(degerler) > 0.05          # 50 mA ustu = gercekten akiyor


def _gecersiz_gerilim(vs):
    """MAVLink 'bilinmiyor' (0xFFFF mV = 65.535 V) degerini tanir."""
    gecerli = [v for v in vs if v is not None]
    if not gecerli:
        return True
    return all(abs(v - 65.535) < 0.01 for v in gecerli)


def _sayi(x, b='{:.2f}'):
    """None'i tire yapan bicimleyici."""
    return '   —' if x is None else b.format(x)


def coz(a):
    """CSV'yi okur, pil testi raporunu basar."""
    satirlar = _oku(a.csv)
    if not satirlar:
        print('CSV bos.')
        return 1
    sure = satirlar[-1]['t_rel'] - satirlar[0]['t_rel']
    armed = [s for s in satirlar if s.get('armed') == 1.0]

    print('=' * 72)
    print(f'PIL TESTI RAPORU — {os.path.basename(a.csv)}')
    print('=' * 72)
    print(f'kayit suresi      : {sure:.0f} sn ({sure / 60:.1f} dk), '
          f'{len(satirlar)} satir')
    print("arm'li sure       : "
          f'{len(armed) * (sure / max(1, len(satirlar))):.0f} sn')
    irt = [s.get('irtifa_m') for s in armed]
    if any(x is not None for x in irt):
        gecerli = [x for x in irt if x is not None]
        print(f'irtifa            : {min(gecerli):.1f} … {max(gecerli):.1f} m')

    # --- pil ---
    print('\n--- PIL ---')
    for etiket, va, ia in (('INA226 (asil)', 'v_ina', 'i_ina'),
                           ('FCU (yedek)', 'v_fcu', 'i_fcu')):
        vs = [s.get(va) for s in satirlar if s.get(va)]
        if not vs:
            print(f'{etiket:16s}: veri yok'
                  + (' — QoS uyusmazligi mi? kaydet kipi BEST_EFFORT '
                     'abone olmali' if va == 'v_ina' else ''))
            continue
        if _gecersiz_gerilim(vs):
            print(f'{etiket:16s}: GECERSIZ (~{_ort(vs):.3f} V = MAVLink '
                  f'"bilinmiyor"). Bu ucakta FCU pil olcumu YOK; pil Pi\'ye '
                  f'ayri bagli INA226\'dan okunuyor.')
            continue
        print(f'{etiket:16s}: {vs[0]:.2f} V -> {vs[-1]:.2f} V  '
              f'(dusus {vs[0] - vs[-1]:.2f} V)  ·  en dusuk {min(vs):.2f} V')

        if not _akim_olculuyor_mu(satirlar, ia):
            # 🔴 SIFIR BIR OLCUM DEGIL. mAh/Wh/W/ic direnc AKIMA baglidir;
            # akim yoksa dordu de VERILMEZ. Bkz. _akim_olculuyor_mu.
            print(f'{"":16s}  AKIM OLCULMUYOR (sont direnci yok) -> '
                  f'mAh · Wh · W · ic direnc VERILEMEZ')
            continue
        mah, wh = _mah(satirlar, ia)
        r = _ic_direnc(satirlar, va, ia)
        iss = [abs(s[ia]) for s in satirlar if s.get(ia) is not None]
        print(f'{"":16s}  akim ort {_ort(iss):.1f} A · tepe '
              f'{max(iss):.1f} A · cekilen {mah:.0f} mAh / {wh:.1f} Wh')
        if r is not None:
            print(f'{"":16s}  ic direnc ~{r * 1000:.0f} mohm '
                  f'(V=a+b*t+c*I uydurmasindan; bosalma egilimi ayrildi)')
        else:
            print(f'{"":16s}  ic direnc: yuk yeterince degismedi, '
                  f'SAYI VERILMIYOR')

    # --- hover dilimleri ---
    dilimler = _hover_dilimleri(satirlar, a.hiz_esik, a.min_sure)
    print(f'\n--- ASILI DURMA (hover) — {len(dilimler)} dilim '
          f'(hiz <= {a.hiz_esik} m/s, en az {a.min_sure:.0f} sn) ---')
    if not dilimler:
        print('Hic hover dilimi bulunamadi. Ucak hic arm olmadi ya da '
              'hep hareket halindeydi; --hiz-esik gevsetilebilir.')
    for no, (i, j) in enumerate(dilimler, 1):
        d = satirlar[i:j + 1]
        d_sure = d[-1]['t_rel'] - d[0]['t_rel']
        thrust = [s.get('thrust') for s in d]
        motorlar, dengesizlik, pwm_ort = _motor_ozeti(
            d, a.pwm_min, a.pwm_max)
        irtifa_ort = _ort([s.get('irtifa_m') for s in d])
        print(f'\n  [{no}] t={d[0]["t_rel"]:.0f}…{d[-1]["t_rel"]:.0f} sn '
              f'({d_sure:.0f} sn)  irtifa '
              f'~{_sayi(irtifa_ort, "{:.1f}")} m')
        print(f'      hover gazi   : {_sayi(_ort(thrust), "{:.3f}")} '
              f'± {_sayi(_std(thrust), "{:.3f}")}   (0…1 normalize)')
        # Gazin dilim ICINDE surukleniyor mu: pil dustukce gaz artar.
        egim, _ = _dogru_uydur([s.get('t_rel') for s in d], thrust)
        if egim is not None:
            print(f'      gaz egilimi  : {egim * 60.0:+.4f} / dakika')
        print('      motor PWM    : ', end='')
        for k, (yuzde, ham) in enumerate(motorlar, 1):
            print(f'M{k}={_sayi(ham, "{:.0f}")}us'
                  f'({_sayi(yuzde, "{:.1f}")}%) ', end='')
        print()
        if dengesizlik is not None:
            uyari = '  🔴 DENGESIZ' if dengesizlik > a.dengesizlik_esik else ''
            print(f'      dengesizlik  : {dengesizlik:.2f} % '
                  f'(motorlar arasi PWM yayilimi / komut araligi){uyari}')
        vd = [s.get('v_ina') for s in d if s.get('v_ina') is not None]
        if vd:
            v_egim, _ = _dogru_uydur([s.get('t_rel') for s in d],
                                     [s.get('v_ina') for s in d])
            satir = (f'      gerilim      : {vd[0]:.2f} -> {vd[-1]:.2f} V '
                     f'(en dusuk {min(vd):.2f})')
            if v_egim is not None:
                satir += f' · {v_egim * 60.0:+.3f} V/dk'
            print(satir)
        if _akim_olculuyor_mu(d, 'i_ina'):
            i_ = _ort([abs(s['i_ina']) for s in d
                       if s.get('i_ina') is not None])
            v = _ort(vd) if vd else None
            if v is not None and i_ is not None:
                print(f'      akim/guc     : {i_:.1f} A · {v * i_:.0f} W')
        tit = _ort([s.get('ivme_rms') for s in d])
        if tit is not None:
            print(f'      ivme RMS     : {tit:.2f} m/s² '
                  f'(9.81 civari normal; sapma titresim/manevra)')

    # --- testin asil sorusu: gaz pille birlikte nasil kaydi ---
    if len(dilimler) >= 1:
        hepsi = [s for i, j in dilimler for s in satirlar[i:j + 1]]
        vt = [s.get('v_ina') or s.get('v_fcu') for s in hepsi]
        th = [s.get('thrust') for s in hepsi]
        egim, _ = _dogru_uydur(vt, th)
        print('\n--- GAZ ↔ GERILIM ---')
        if egim is not None:
            print(f'  d(gaz)/d(gerilim) = {egim:+.4f} / V   '
                  f'(gerilim 1 V duserse gaz bu kadar artiyor)')
            ilk = _ort(th[:max(3, len(th) // 10)])
            son = _ort(th[-max(3, len(th) // 10):])
            if ilk and son:
                print(f'  hover gazi: bas {ilk:.3f} -> son {son:.3f} '
                      f'({100.0 * (son - ilk) / ilk:+.1f} %)')
        else:
            print('  Yeterli veri yok.')

    # --- GERILIM-TEK COZUMLEME (akim yokken testin asil ciktisi) -------
    if dilimler:
        hepsi = [s for i, j in dilimler for s in satirlar[i:j + 1]]
        vt = [s.get('v_ina') for s in hepsi]
        tt = [s.get('t_rel') for s in hepsi]
        th = [s.get('thrust') for s in hepsi]
        gecerli_v = [v for v in vt if v is not None]
        print('\n--- GERILIM (akim olculemedigi icin testin ASIL ciktisi) ---')
        v_egim, _ = _dogru_uydur(tt, vt)
        if v_egim is not None and gecerli_v:
            dk = v_egim * 60.0
            print(f'  dusus hizi        : {dk:+.3f} V/dakika '
                  f'(asili durma dilimlerinde)')
            if dk >= -1e-4:
                pass                       # asagida ele aliniyor
            elif gecerli_v[-1] <= a.esik_v:
                # Esik ZATEN gecilmis; negatif "kalan sure" basmak sacma
                # olurdu (ilk surumde -0.2 dakika yazdi).
                print(f'  {a.esik_v:.1f} V esigi      : ZATEN GECILDI '
                      f'(son {gecerli_v[-1]:.2f} V)')
            else:
                kalan = (gecerli_v[-1] - a.esik_v) / (-dk)
                print(f'  {a.esik_v:.1f} V esigine   : '
                      f'~{kalan:.1f} dakika (bu hiz surerse)')
                if kalan < 2.0:
                    print('                      🔴 ESIGE COK YAKIN')
            if dk >= -1e-4:
                print(f'  {a.esik_v:.1f} V esigine   : gerilim dusmuyor, '
                      f'kestirim YAPILMIYOR')

        # COKME (sag): yukteki en dusuk gerilim ile YERDEKI dinlenme
        # gerilimi arasindaki fark. Akim yokken ic direncin tek gostergesi.
        yerde_son = [s.get('v_ina') for s in satirlar[dilimler[-1][1]:]
                     if s.get('armed') == 0.0 and s.get('v_ina') is not None]
        if gecerli_v and yerde_son:
            cokme = max(yerde_son[-10:]) - min(gecerli_v)
            print(f'  cokme (sag)       : {cokme:.2f} V '
                  f'(yukte en dusuk {min(gecerli_v):.2f} -> '
                  f'inisten sonra dinlenme {max(yerde_son[-10:]):.2f})')
            print('                      Akim olculseydi bu, ic direnc '
                  'olurdu; simdilik yalniz KARSILASTIRMA icin anlamli '
                  '(ayni pil, ayni ucus profili).')

        # Gaz basina gerilim dususu — akimsiz "yuk tepkisi" vekili.
        egim_th, _ = _dogru_uydur(th, vt)
        if egim_th is not None:
            print(f'  d(gerilim)/d(gaz) : {egim_th:+.2f} V / birim gaz')

    print('\n🔴 NOT: MOTOR DEVRI OLCULMUYOR. ESC telemetrisi veri gondermiyor '
          '(3 Eylul, ylp02'
          "'de dogrulandi), yukaridaki PWM ucus kontrolcusunun "
          'KOMUTUDUR. Tikali motor ya da bozuk pervane komutta gorunmez; '
          'dengesizlik ise gorunur.')

    if a.cizelge:
        print('\n--- 30 SN OZET CIZELGE ---')
        print(f'{"t(sn)":>7} {"irtifa":>7} {"gaz":>6} {"V":>6} {"A":>6} '
              f'{"M1":>6} {"M2":>6} {"M3":>6} {"M4":>6}')
        kova = {}
        for s in satirlar:
            if s.get('t_rel') is None:
                continue
            kova.setdefault(int(s['t_rel'] // 30) * 30, []).append(s)
        for t in sorted(kova):
            d = kova[t]
            akim_ort = _ort([abs(x['i_ina']) for x in d
                             if x.get('i_ina') is not None])
            print(f'{t:>7} '
                  f'{_sayi(_ort([x.get("irtifa_m") for x in d]), "{:>7.1f}")} '
                  f'{_sayi(_ort([x.get("thrust") for x in d]), "{:>6.3f}")} '
                  f'{_sayi(_ort([x.get("v_ina") or x.get("v_fcu") for x in d]), "{:>6.2f}")} '
                  f'{_sayi(akim_ort, "{:>6.1f}")} '
                  + ' '.join(
                      _sayi(_ort([x.get(f"pwm{k}") for x in d]), "{:>6.0f}")
                      for k in (1, 2, 3, 4)))
    return 0


def main():
    """Alt komutu secer."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest='kip', required=True)

    k = alt.add_parser('kaydet', help='ucakta kaydet (ROS gerekir)')
    k.add_argument('--ajan', type=int, default=3, help='agent_id (ns)')
    k.add_argument('--hz', type=float, default=5.0, help='ornekleme hizi')
    k.add_argument('--cikti', default=None, help='CSV yolu (vars: /ws/pil_testi)')

    c = alt.add_parser('coz', help='CSV cozumle (ROS GEREKMEZ)')
    c.add_argument('--csv', required=True, help='kaydet ciktisi')
    c.add_argument('--hiz-esik', type=float, default=HOVER_HIZ_ESIK,
                   dest='hiz_esik', help='hover hiz esigi m/s')
    c.add_argument('--min-sure', type=float, default=HOVER_MIN_SURE,
                   dest='min_sure', help='en kisa hover dilimi sn')
    c.add_argument('--pwm-min', type=float, default=PWM_MIN_VARS,
                   dest='pwm_min')
    c.add_argument('--pwm-max', type=float, default=PWM_MAX_VARS,
                   dest='pwm_max')
    c.add_argument('--dengesizlik-esik', type=float, default=3.0,
                   dest='dengesizlik_esik',
                   help='bu %% ustunde DENGESIZ uyarisi')
    c.add_argument('--esik-v', type=float, default=14.2, dest='esik_v',
                   help='bu gerilime kalan sure kestirilir '
                        '(vars 14.2 = gosterge %%0; kritik esik 13.8)')
    c.add_argument('--cizelge', action='store_true',
                   help='30 sn kovalarla ozet tablo')

    a = p.parse_args()
    return kaydet(a) if a.kip == 'kaydet' else coz(a)


if __name__ == '__main__':
    sys.exit(main() or 0)
