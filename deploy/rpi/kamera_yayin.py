#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""Kamera yayini ve odak/QR test arayuzu — Pi'de kosar, tarayicidan izlenir.

NEDEN VAR (27 Agustos 2026, operator istegi)
--------------------------------------------
"hotspottan yayin yapacak bir site yaz, ben pc den kamerayi izleyeyim ordan
odak ayari yapayim." Ardindan: "4k'ya kadar kamera secenekleri ekle... 4k gibi
yuksek cozunurlukte hotspot yetisemeyecek, ethernet kablosu ile aktarim da
yapalim... ucus sirasinda ethernet kullanamayacagim icin rpi yine 4k gorsun
ama bana hotspottan dusuk cozunurlukte gondersin."

⚠️ EN ONEMLI TASARIM KARARI — YAKALAMA ile ONIZLEME AYRI
---------------------------------------------------------
`--mode` sensorun HANGI COZUNURLUKTE OKUDUGUNU secer; `--width/--height` ise
ISP'nin ne buyuklukte KODLADIGINI. Ikisi bagimsiz. Yani:

    --mode 4056:3040:12:P  --width 640 --height 480

sensoru TAM 12,3 MP'de okur, hotspot'a 640 genisliginde gonderir. QR icin
onemli olan yakalama cozunurlugudur; senin ekranindaki onizleme degil.
Ucusta ethernet olmayacagi icin dogru kip tam olarak budur.

⚠️ NEDEN `camera_driver` DEGIL — 27 Agustos'ta OLCULDU
------------------------------------------------------
Repodaki `swarm_perception/camera_driver` bu donanimda oldugu gibi calisamaz:
`FrameGrabber` `cv2.VideoCapture(0)` kullaniyor, ama Pi 5'te IMX477'nin V4L2
dugumu `/dev/video0` = **rp1-cfe-csi2_ch0** — ham Bayer veren CSI yakalama
dugumu, UVC kamera DEGIL. Ustelik konteynerde ne `cv2` var ne `/dev/video*`.
Bu betik o zinciri hic kullanmiyor.

⚠️ KAMERAYI TEK SUREC ACABILIR. Bu betik kosarken `camera_driver` ya da baska
bir `rpicam-*` kamerayi acamaz. Isin bitince DURDUR:
    pkill -f '[k]amera_yayin'

BAGIMLILIK YOK: yalniz Python stdlib + `rpicam-vid`.

KESKINLIK OLCUSU
----------------
Sabit JPEG kalitesinde **kare BOYUTU**. Odak duzeldikce yuksek frekans icerigi
artar, JPEG daha kotu sikisir, kare buyur. Mutlak degeri anlamsiz — ekranda
tepeye gore yuzde, egilim ve ham egri birlikte gosteriliyor.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SINIR = b'yelpencekare'
EMA_ALFA = 0.25
BUYUTEC_ROI = '0.375,0.375,0.25,0.25'      # merkezin %25'i = 4x
# Diskte tutulacak EN FAZLA kayit sayisi; sinira gelince en ESKI silinir.
# Tam cozunurlukte kayit dakikada 0,5-1,5 GB yaziyor. Sinir olmadan bir
# gunluk denemede kart doluyor — ve dolmus diskte Pi'nin kendisi de yazamaz
# hale gelir (bu depoda bir kez yasandi, bkz. TUZAKLAR disk maddeleri).
KAYIT_SINIRI = 5
# Diskte tutulacak en fazla foto. Foto ~1,5 MB, 20 tane 30 MB — ucuz.
FOTO_SINIRI = 20

# IMX477 sensor kipleri. fps degerleri 27 Agustos'ta `rpicam-hello
# --list-cameras` ciktisindan alindi — kipin USTUNE cikilirsa rpicam-vid
# kirpar, o yuzden her kip kendi tavaniyla duruyor.
MODLAR = {
    'hizli':  {'ad': '1332x990  hizli',        'w': 1332, 'h': 990,
               'mod': '1332:990:10:P',  'fps': 40},
    'hd':     {'ad': '2028x1080  16:9',        'w': 2028, 'h': 1080,
               'mod': '2028:1080:12:P', 'fps': 30},
    'tamfov': {'ad': '2028x1520  tam FOV',     'w': 2028, 'h': 1520,
               'mod': '2028:1520:12:P', 'fps': 30},
    'dk169':  {'ad': '4056x2160  4K 16:9',     'w': 4056, 'h': 2160,
               'mod': '4056:2160:12:P', 'fps': 15},
    'tam':    {'ad': '4056x3040  TAM 12,3MP',  'w': 4056, 'h': 3040,
               'mod': '4056:3040:12:P', 'fps': 10},
}

# Onizleme GENISLIGI. Yukseklik yakalama en-boy oranindan turetiliyor —
# boylece onizleme ile yakalama ayni kareyi gosterir, kirpma olmaz.
# 0 = kirpmasiz tam boy (ethernet icin).
ONIZLEMELER = (480, 640, 960, 1280, 1920, 0)

# q = JPEG sikistirma kalitesi; COZUNURLUKLE ILGISI YOK. 4056x3040'ta
# olculdu (28 Agustos): q90 2574 KB/kare, q75 1350, q60 930, q45 670 —
# dordu de ayni 12,3 megapiksel. SD kart 25,3 MB/s yaziyor, 4K q90 21,9
# istiyor; sinira dayandigi icin kare dusuruyordu (8,7 fps, 2,7 sn bosluk).
# q60 9,3 MB/s ile rahat. 60 ve 45 bu yuzden listede.
KALITELER = (45, 60, 75, 90)

# POZLAMA — 28 Agustos 2026'da olculdu, QR icin BELIRLEYICI.
# Otomatik pozlama karanlikta sureyi UZATARAK isik topluyor; drone o
# surede yol aldigi icin goruntu surukleniyor. Olcum (4 m/s, 20 m irtifa,
# 189 px/m):
#     1/500 sn ->  1,5 px bulaniklik   QR OKUNDU
#     1/250 sn ->  3,0 px              QR OKUNDU   <- SINIR
#     1/125 sn ->  6,1 px              QR OKUNAMADI
#     1/60  sn -> 12,6 px              QR OKUNAMADI
# 20 m'de bir QR modulu 3,8 piksel; bulaniklik onu asinca desen siliniyor.
# Daire bundan etkilenmiyor (1/30'da bile bulunuyor) — buyuk duz leke.
#
# 'sport' otomatigi kisa pozlamaya yonlendirir, kazanci yukseltir.
# Sabit degerler pozlamayi kilitler: bulaniklik yerine gurultu.
POZLAMALAR = (
    ('auto', 'Otomatik'),
    ('sport', 'Kisa (spor)'),
    ('4000', 'Sabit 1/250'),
    ('2000', 'Sabit 1/500'),
)
META_YOLU = '/tmp/kamera_meta.txt'

# Beyaz ayari. `--denoise off` + `--sharpness 0` gibi bunlar da olcumu
# etkiliyor: yanlis beyaz ayari kareyi tek renge kaydirir ve renk tespiti
# her yeri o renk sanir. 27 Agustos'ta magenta kare 6 sahte "KIRMIZI bolge"
# uretti — bu secici o yuzden var.
BEYAZ_AYARLARI = (
    ('auto', 'Otomatik'),
    ('indoor', 'Ic mekan'),
    ('tungsten', 'Ampul'),
    ('fluorescent', 'Floresan'),
    ('daylight', 'Gun isigi'),
    ('cloudy', 'Bulutlu'),
)

PROFILLER = {
    'hotspot':  {'mod': 'tam', 'onizleme': 640, 'kalite': 55},
    'ethernet': {'mod': 'tam', 'onizleme': 1920, 'kalite': 90},
}


# ------------------------------------------------------------------ sistem

class Sistem:
    """Pi'nin CPU / RAM / sicaklik / kisitlama degerleri. Saf stdlib."""

    def __init__(self) -> None:
        self._veri: dict = {}
        self._onceki_cpu: tuple[int, int] | None = None
        self._kisit = ''
        self._kisit_an = 0.0
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self) -> None:
        while True:
            try:
                self._veri = self._olc()
            except Exception as e:                        # noqa: BLE001
                self._veri = {'hata': str(e)[:120]}
            time.sleep(1.0)

    def _cpu(self) -> float:
        with open('/proc/stat', encoding='ascii') as f:
            alan = [int(x) for x in f.readline().split()[1:9]]
        toplam, bos = sum(alan), alan[3] + alan[4]
        if self._onceki_cpu is None:
            self._onceki_cpu = (toplam, bos)
            return 0.0
        dt, db = toplam - self._onceki_cpu[0], bos - self._onceki_cpu[1]
        self._onceki_cpu = (toplam, bos)
        return round(100.0 * (1.0 - db / dt), 1) if dt > 0 else 0.0

    def _bellek(self) -> tuple[float, float]:
        degerler = {}
        with open('/proc/meminfo', encoding='ascii') as f:
            for satir in f:
                k, _, v = satir.partition(':')
                if k in ('MemTotal', 'MemAvailable'):
                    degerler[k] = float(v.split()[0]) / 1024.0     # MB
        return degerler.get('MemTotal', 0.0), degerler.get('MemAvailable', 0.0)

    def _sicaklik(self) -> float:
        try:
            with open('/sys/class/thermal/thermal_zone0/temp',
                      encoding='ascii') as f:
                return round(int(f.read().strip()) / 1000.0, 1)
        except OSError:
            return 0.0

    def _kisitlama(self) -> str:
        """`vcgencmd get_throttled` — 2 saniyede bir, surec pahali."""
        simdi = time.monotonic()
        if simdi - self._kisit_an < 2.0:
            return self._kisit
        self._kisit_an = simdi
        try:
            c = subprocess.run(['vcgencmd', 'get_throttled'],
                               capture_output=True, text=True, timeout=3)
            self._kisit = c.stdout.strip().split('=')[-1] or '?'
        except Exception:                                # noqa: BLE001
            self._kisit = '?'
        return self._kisit

    def _olc(self) -> dict:
        toplam_mb, bos_mb = self._bellek()
        return {
            'cpu': self._cpu(),
            'ram_bos_mb': round(bos_mb),
            'ram_toplam_mb': round(toplam_mb),
            'ram_yuzde': round(100.0 * (1 - bos_mb / toplam_mb), 1)
                         if toplam_mb else 0.0,
            'sicaklik': self._sicaklik(),
            'kisitlama': self._kisitlama(),
            'yuk': round(os.getloadavg()[0], 2),
        }

    def veri(self) -> dict:
        return dict(self._veri)


def algi_oku(yol: str) -> dict | None:
    """Konteynerdeki `algi_kopru` dugumunun yazdigi JSON.

    Bu sayfa host'ta kosuyor ve ROS'u yok; ROS konteynerin icinde. Arada
    `/ws` (konteyner) = `~/yelpence_ws` (host) bind mount'u kopru. Dosya
    yoksa None doner — kopru kosmuyor demektir, hata degil.
    """
    try:
        with open(yol, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def arayuz_haritasi() -> dict:
    """IP -> arayuz adi. Hangi baglantidan izlendigini soylemek icin."""
    try:
        c = subprocess.run(['ip', '-o', '-4', 'addr', 'show'],
                           capture_output=True, text=True, timeout=3)
    except Exception:                                    # noqa: BLE001
        return {}
    harita = {}
    for satir in c.stdout.splitlines():
        p = satir.split()
        if len(p) >= 4 and '/' in p[3]:
            harita[p[3].split('/')[0]] = p[1]
    return harita


# ------------------------------------------------------------------- yayin

class Yayin:
    """rpicam-vid'i besler, MJPEG karelerini dagitir, keskinligi olcer."""

    def __init__(self, mod: str, onizleme: int, kalite: int) -> None:
        self.mod = mod if mod in MODLAR else 'tamfov'
        self.onizleme = onizleme
        self.kalite = kalite
        self.buyutec = False
        self.awb = 'auto'
        self.pozlama = 'auto'

        self._kilit = threading.Condition()
        self._kare: bytes | None = None
        self._sayac = 0

        self._ham = 0
        self._yumusak = 0.0
        self._tepe = 0.0
        self._fps = 0.0
        self._bps = 0.0
        self._pencere_kare = 0
        self._pencere_bayt = 0
        self._pencere_an = time.monotonic()

        self._hata = ''
        # YEREL KAYIT — 28 Agustos 2026, ucus testi oncesi.
        # Yayin canli; mesafede hotspot koptugunda o anin goruntusu gider ve
        # ucus tekrarlanmak zorunda kalir. Kareler zaten elimizde oldugu icin
        # diske yazmak bedava: birlestirilmis JPEG = .mjpeg, VLC/ffmpeg acar.
        self._kayit_kilit = threading.Lock()
        self._kayit_dosya = None
        self._kayit_idx = None
        self._kayit_yol = ''
        self._kayit_bayt = 0
        self._kayit_kare = 0
        self._kayit_bas = 0.0
        self._kayit_hata = ''
        self.kayit_siniri = KAYIT_SINIRI
        self._silinen: list[str] = []
        # FOTO KIPI: cekim sirasinda akis kisa sure 4K'ya cikiyor. O kareleri
        # tarayiciya GONDERMIYORUZ — hotspot 125 Mbps'i tasimaz ve zaten
        # gereksiz. Tarayicida son kare birkac saniye donmus gorunur.
        self._foto_modu = False
        self._foto_kilit = threading.Lock()
        self._surec: subprocess.Popen | None = None
        self._dur = threading.Event()
        self._degisti = threading.Event()

    # -------------------------------------------------------------- olcu

    def onizleme_boyu(self) -> tuple[int, int]:
        """Onizleme genisligi + yakalama en-boy oranindan yukseklik.

        Yakalama 4:3 iken onizlemeyi 16:9 vermek kareyi KIRPAR ve ekranda
        gordugun sey QR'in gectigi kare olmaz. Bu yuzden oran korunuyor.
        """
        m = MODLAR[self.mod]
        if not self.onizleme or self.onizleme >= m['w']:
            return m['w'], m['h']
        g = int(self.onizleme)
        y = int(round(g * m['h'] / m['w'] / 2.0)) * 2
        return g, y

    def _komut(self) -> list[str]:
        m = MODLAR[self.mod]
        g, y = self.onizleme_boyu()
        komut = [
            'rpicam-vid', '-n', '-t', '0', '--codec', 'mjpeg',
            '--mode', m['mod'],                 # SENSOR ne okuyor
            '--width', str(g), '--height', str(y),   # AKISA ne cikiyor
            '--framerate', str(m['fps']),
            '-q', str(self.kalite),
            '--denoise', 'off', '--sharpness', '0', '--flush',
            '--awb', self.awb,
            # Kare basina pozlama/kazanc/lux buraya yaziliyor; canli
            # okunabiliyor (dogrulandi: dosya kayit sirasinda buyuyor).
            '--metadata', META_YOLU, '--metadata-format', 'txt',
            '-o', '-',
        ]
        if self.pozlama == 'sport':
            komut += ['--exposure', 'sport']
        elif self.pozlama.isdigit():
            komut += ['--shutter', self.pozlama]
        if self.buyutec:
            komut += ['--roi', BUYUTEC_ROI]
        return komut

    # ------------------------------------------------------------- surec

    def baslat(self) -> None:
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self) -> None:
        while not self._dur.is_set():
            try:
                self._surec = subprocess.Popen(
                    self._komut(), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, bufsize=0)
            except FileNotFoundError:
                self._hata = 'rpicam-vid bulunamadi'
                return

            self._hata = ''
            self._degisti.clear()
            threading.Thread(target=self._stderr_oku,
                             args=(self._surec,), daemon=True).start()
            try:
                self._kareleri_oku(self._surec)
            except Exception as e:                       # noqa: BLE001
                self._hata = f'akis: {e}'

            kod = self._surec.poll()
            if kod not in (0, None) and not self._degisti.is_set():
                self._hata = self._hata or f'rpicam-vid cikti (kod {kod})'
            if self._dur.is_set():
                return
            time.sleep(0.8)

    def _stderr_oku(self, surec: subprocess.Popen) -> None:
        """Sessiz olum olmasin — rpicam-vid'in hatasi arayuze cikar."""
        for satir in iter(surec.stderr.readline, b''):
            m = satir.decode('utf-8', 'replace').strip()
            if m and ('ERROR' in m or 'error' in m or 'Invalid' in m):
                self._hata = m[:200]

    def _kareleri_oku(self, surec: subprocess.Popen) -> None:
        """MJPEG akisini FFD8..FFD9 sinirlarindan kareye boler."""
        tampon = bytearray()
        while not self._dur.is_set() and not self._degisti.is_set():
            parca = surec.stdout.read(65536)
            if not parca:
                return
            tampon += parca
            while True:
                bas = tampon.find(b'\xff\xd8')
                if bas < 0:
                    tampon.clear()
                    break
                son = tampon.find(b'\xff\xd9', bas + 2)
                if son < 0:
                    if bas:
                        del tampon[:bas]
                    break
                self._kare_geldi(bytes(tampon[bas:son + 2]))
                del tampon[:son + 2]

    def durdur(self) -> None:
        self._dur.set()
        self.kayit_kapa()
        self._oldur()

    def _oldur(self) -> None:
        if self._surec and self._surec.poll() is None:
            self._surec.kill()

    # -------------------------------------------------------------- olcum

    def _kare_geldi(self, kare: bytes) -> None:
        self._ham = len(kare)
        self._yumusak = (float(self._ham) if self._yumusak <= 0.0 else
                         (1 - EMA_ALFA) * self._yumusak + EMA_ALFA * self._ham)
        self._tepe = max(self._tepe, self._yumusak)

        self._pencere_kare += 1
        self._pencere_bayt += self._ham
        simdi = time.monotonic()
        gecen = simdi - self._pencere_an
        if gecen >= 1.0:
            self._fps = self._pencere_kare / gecen
            self._bps = self._pencere_bayt / gecen
            self._pencere_kare = self._pencere_bayt = 0
            self._pencere_an = simdi

        self._kayda_yaz(kare)

        with self._kilit:
            self._kare = kare
            self._sayac += 1
            self._kilit.notify_all()

    def _kayda_yaz(self, kare: bytes) -> None:
        """Kareyi kayit dosyasina ekler. Kayit kapaliysa hicbir sey yapmaz."""
        with self._kayit_kilit:
            if self._kayit_dosya is None:
                return
            try:
                ofset = self._kayit_bayt
                self._kayit_dosya.write(kare)
                # Yan dosya: her karenin GERCEK zaman damgasi. Videoyu ucus
                # kaydiyla eslestirmek icin sart — sabit fps varsayimi kayar.
                self._kayit_idx.write(
                    f'{self._kayit_kare} {time.time():.3f} '
                    f'{ofset} {len(kare)}\n')
                self._kayit_bayt += len(kare)
                self._kayit_kare += 1
            except OSError as e:
                self._kayit_hata = f'yazma: {e}'
                self._kaydi_kapa_kilitli()
                return

            # DISK BEKCISI: her ~200 karede bir bak. Dolmus diskte Pi'nin
            # kendisi de yazamaz hale gelir — ucus sirasinda bunu gormeyiz.
            if self._kayit_kare % 200 == 0:
                bos = shutil.disk_usage(
                    os.path.dirname(self._kayit_yol) or '/').free
                if bos < 500 * 1024 * 1024:
                    self._kayit_hata = 'disk 500 MB altina indi, kayit durdu'
                    self._kaydi_kapa_kilitli()

    def kayit_ac(self, dizin: str) -> str:
        """Yeni kayit baslatir, dosya yolunu doner."""
        with self._kayit_kilit:
            if self._kayit_dosya is not None:
                return self._kayit_yol
            try:
                os.makedirs(dizin, exist_ok=True)
                self._eski_kayitlari_sil(dizin)
                ad = time.strftime('yelpence_%Y%m%d_%H%M%S')
                yol = os.path.join(dizin, ad + '.mjpeg')
                self._kayit_dosya = open(yol, 'wb', buffering=1024 * 256)
                self._kayit_idx = open(yol[:-6] + '.idx', 'w',
                                       encoding='ascii')
                self._kayit_idx.write('# kare epoch ofset uzunluk\n')
                self._kayit_yol = yol
                self._kayit_bayt = self._kayit_kare = 0
                self._kayit_bas = time.monotonic()
                self._kayit_hata = ''
                return yol
            except OSError as e:
                self._kayit_hata = str(e)
                self._kayit_dosya = self._kayit_idx = None
                return ''

    def _eski_kayitlari_sil(self, dizin: str) -> None:
        """Yeni kayit acilmadan ONCE en eskileri siler.

        Silme kayit BASLARKEN yapiliyor, bitince degil: boylece yeni kayda
        yer acilmis olur ve diskte her zaman en yeni KAYIT_SINIRI kadar
        dosya kalir. Dosya adlari zaman damgali oldugu icin sozluk sirasi
        = zaman sirasi; ayrica mtime'a guvenmiyoruz (kopyalama mtime'i
        degistirebilir, ad degismez).
        """
        try:
            dosyalar = sorted(f for f in os.listdir(dizin)
                              if f.endswith('.mjpeg'))
        except OSError:
            return
        while len(dosyalar) >= self.kayit_siniri:
            eski = dosyalar.pop(0)
            for uzanti in ('.mjpeg', '.idx'):
                try:
                    os.remove(os.path.join(dizin, eski[:-6] + uzanti))
                except OSError:
                    pass
            self._silinen.append(eski)
            del self._silinen[:-3]      # son 3'u goster, fazlasi gurultu

    def _kaydi_kapa_kilitli(self) -> None:
        """Kilit ZATEN tutulurken cagrilir."""
        for f in (self._kayit_dosya, self._kayit_idx):
            if f is not None:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                    f.close()
                except OSError:
                    pass
        self._kayit_dosya = self._kayit_idx = None

    def kayit_kapa(self) -> None:
        """Kaydi kapatir ve diske BASTIRIR (fsync).

        fsync onemli: ucus sonunda Pi'nin gucu kesilirse tampondaki kareler
        kaybolurdu. Bu projede bir kez yasandi (bkz. cokme_kopyala.sh).
        """
        with self._kayit_kilit:
            self._kaydi_kapa_kilitli()

    def foto_modunda(self) -> bool:
        """Foto cekiliyorsa akis tarayiciya dagitilmaz."""
        return self._foto_modu

    def foto_cek(self, dizin: str, atlanacak: int = 8) -> dict:
        """Tam cozunurlukte TEK kare ceker, sonra ESKI ayara doner.

        Neden ayar degistirip geri aliyoruz: sensor zaten 4056x3040 okuyor
        ama ISP onizleme boyutuna kuculterek kodluyor. Tam cozunurlukte
        kare almanin tek yolu kodlama boyutunu gecici olarak tam yapmak.

        `atlanacak`: ilk kareler atiliyor. rpicam-vid yeniden basladiginda
        otomatik pozlama ve beyaz ayari birkac kare oturuyor; ilk kare
        koyu ya da renk kaymis cikardi.
        """
        with self._foto_kilit:
            eski = (self.mod, self.onizleme, self.kalite)
            self._foto_modu = True
            try:
                os.makedirs(dizin, exist_ok=True)
                self._eski_fotolari_sil(dizin)
                self.ayarla('tam', 0, 90, self.buyutec)
                bitis = time.monotonic() + 25.0
                gorulen, son, kare = 0, -1, None
                while time.monotonic() < bitis:
                    son, k = self.kare_bekle(son, 3.0)
                    if k is None:
                        continue
                    gorulen += 1
                    if gorulen > atlanacak:
                        kare = k
                        break
                if kare is None:
                    return {'ok': False, 'hata': 'kare gelmedi (zaman asimi)'}
                ad = time.strftime('foto_%Y%m%d_%H%M%S.jpg')
                yol = os.path.join(dizin, ad)
                with open(yol, 'wb') as f:
                    f.write(kare)
                    f.flush()
                    os.fsync(f.fileno())     # guc kesilirse kaybolmasin
                return {'ok': True, 'ad': ad, 'kb': round(len(kare) / 1024)}
            except OSError as e:
                return {'ok': False, 'hata': str(e)}
            finally:
                self.ayarla(eski[0], eski[1], eski[2], self.buyutec)
                self._foto_modu = False

    def _eski_fotolari_sil(self, dizin: str) -> None:
        """En eski fotolari siler; adlar zaman damgali, sozluk sirasi yeter."""
        try:
            f = sorted(x for x in os.listdir(dizin) if x.endswith('.jpg'))
        except OSError:
            return
        while len(f) >= FOTO_SINIRI:
            try:
                os.remove(os.path.join(dizin, f.pop(0)))
            except OSError:
                pass

    def kayit_durumu(self) -> dict:
        with self._kayit_kilit:
            acik = self._kayit_dosya is not None
            return {
                'acik': acik,
                'dosya': os.path.basename(self._kayit_yol)
                         if self._kayit_yol else '',
                'saniye': round(time.monotonic() - self._kayit_bas, 1)
                          if acik else 0.0,
                'mb': round(self._kayit_bayt / 1048576.0, 1),
                'kare': self._kayit_kare,
                'hata': self._kayit_hata,
                'sinir': self.kayit_siniri,
                'silinen': list(self._silinen),
            }

    @staticmethod
    def pozlama_olcumu() -> dict:
        """rpicam-vid'in yazdigi son kare verisi: pozlama, kazanc, lux.

        Dosyanin SONUNDAN okuyoruz — surekli buyuyor ve tamami gereksiz.
        """
        try:
            with open(META_YOLU, 'rb') as f:
                f.seek(0, os.SEEK_END)
                boy = f.tell()
                f.seek(max(0, boy - 4096))
                kuyruk = f.read().decode('ascii', 'replace')
        except OSError:
            return {}
        d = {}
        for satir in kuyruk.splitlines():
            k, _, v = satir.partition('=')
            if k in ('ExposureTime', 'AnalogueGain', 'DigitalGain', 'Lux',
                     'SensorTemperature'):
                try:
                    d[k] = float(v)
                except ValueError:
                    pass
        return d

    def _disk_bos_mb(self) -> int:
        """Kayit dizinindeki bos alan — sayfa kalan sureyi buradan hesaplar."""
        try:
            yol = os.path.dirname(self._kayit_yol) or os.path.expanduser('~')
            return int(shutil.disk_usage(yol).free / 1048576)
        except OSError:
            return 0

    def tepeyi_sifirla(self) -> None:
        self._tepe = self._yumusak

    def olcum(self) -> dict:
        m = MODLAR[self.mod]
        g, y = self.onizleme_boyu()
        return {
            'ham_kb': round(self._ham / 1024.0, 1),
            'yumusak_kb': round(self._yumusak / 1024.0, 1),
            'tepe_kb': round(self._tepe / 1024.0, 1),
            'yuzde': round(100.0 * self._yumusak / self._tepe, 1)
                     if self._tepe > 0 else 0.0,
            'fps': round(self._fps, 1),
            'mbps': round(self._bps * 8 / 1e6, 2),
            'kbs': round(self._bps / 1024.0),
            'mod': self.mod,
            'mod_ad': m['ad'],
            'yakalama': f"{m['w']}x{m['h']}",
            'onizleme': f'{g}x{y}',
            'onizleme_g': self.onizleme,
            'kalite': self.kalite,
            'buyutec': self.buyutec,
            'awb': self.awb,
            'pozlama': self.pozlama,
            'poz_olcum': self.pozlama_olcumu(),
            'kayit': self.kayit_durumu(),
            'disk_bos_mb': self._disk_bos_mb(),
            'kare_sayisi': self._sayac,
            'hata': self._hata,
        }

    # --------------------------------------------------------------- ayar

    def ayarla(self, mod: str, onizleme: int, kalite: int,
               buyutec: bool, awb: str = '', pozlama: str = '') -> None:
        awb = awb or self.awb
        gecerli = {a for a, _ in BEYAZ_AYARLARI}
        awb = awb if awb in gecerli else self.awb
        poz = pozlama or self.pozlama
        poz = poz if poz in {a for a, _ in POZLAMALAR} else self.pozlama
        yeni = (mod, int(onizleme), int(kalite), bool(buyutec), awb, poz)
        if yeni == (self.mod, self.onizleme, self.kalite, self.buyutec,
                    self.awb, self.pozlama):
            return
        self.mod = mod if mod in MODLAR else self.mod
        self.onizleme, self.kalite = yeni[1], yeni[2]
        self.buyutec, self.awb = yeni[3], yeni[4]
        self.pozlama = yeni[5]
        # Cozunurluk/kalite degisince kare boyutu toptan degisir; eski tepe
        # anlamsiz kalir ve yuzde hep dusuk gorunurdu.
        self._yumusak = self._tepe = 0.0
        self._degisti.set()
        self._oldur()

    def kare_bekle(self, son: int, zaman_asimi: float = 5.0):
        with self._kilit:
            if self._sayac == son:
                self._kilit.wait(zaman_asimi)
            return self._sayac, self._kare


SAYFA = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yelpence — kamera</title>
<style>
:root{
  --bg:#0b0e13; --kart:#151b24; --cizgi:#232c39; --ana:#e9eff7;
  --soluk:#7c8a9c; --iyi:#3ddc84; --orta:#ffcc4d; --kotu:#ff5f56; --vurgu:#4da3ff;
}
*{box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{margin:0;background:var(--bg);color:var(--ana);
  font:13px/1.45 ui-monospace,"DejaVu Sans Mono",Menlo,Consolas,monospace;
  display:flex;flex-direction:column}

header{display:flex;align-items:center;gap:8px;padding:6px 11px;
  border-bottom:1px solid var(--cizgi);background:var(--kart);flex:0 0 auto}
header h1{margin:0;font-size:12px;letter-spacing:.06em;white-space:nowrap}
.cipler{display:flex;gap:5px;margin-left:auto;flex-wrap:wrap}
.cip{background:#1d2632;border:1px solid var(--cizgi);border-radius:4px;
  padding:0 6px;font-size:11px;color:var(--soluk);white-space:nowrap}
.cip b{color:var(--ana);font-weight:600;font-variant-numeric:tabular-nums}
.cip b.iyi{color:var(--iyi)} .cip b.orta{color:var(--orta)} .cip b.kotu{color:var(--kotu)}
.rozet{padding:0 6px;border-radius:4px;font-size:11px;background:#1d2632;
  border:1px solid var(--cizgi);color:var(--soluk);white-space:nowrap}
.rozet.eth{background:#10321f;border-color:var(--iyi);color:var(--iyi)}
.rozet.wifi{background:#332a10;border-color:var(--orta);color:var(--orta)}
.kayit-cip.acik{background:#3a1416;border-color:var(--kotu);color:#ffb4b0;
  font-weight:700;animation:yanip 1.4s ease-in-out infinite}
@keyframes yanip{50%{opacity:.45}}

main{flex:1 1 auto;display:flex;gap:8px;padding:8px;min-height:0}
.sahne{flex:1 1 auto;min-width:0;background:#000;border:1px solid var(--cizgi);
  border-radius:6px;display:flex;align-items:center;justify-content:center;
  overflow:hidden}
.cerceve{position:relative;display:inline-block;line-height:0;max-width:100%;max-height:100%}
.cerceve img{display:block;max-width:100%;max-height:calc(100vh - 62px);height:auto}
.nisan{position:absolute;inset:0;pointer-events:none}
.nisan::before,.nisan::after{content:"";position:absolute;background:rgba(77,163,255,.35)}
.nisan::before{left:50%;top:0;bottom:0;width:1px}
.nisan::after{top:50%;left:0;right:0;height:1px}
.isaret{position:absolute;display:none;transform:translate(-50%,-50%);
  pointer-events:none;border-radius:50%;box-shadow:0 0 0 2px rgba(0,0,0,.55)}
.isaret span{position:absolute;left:50%;top:-19px;transform:translateX(-50%);
  font-size:10px;font-weight:700;white-space:nowrap;padding:0 5px;
  border-radius:3px;line-height:1.6}
#isaret-qr{width:22px;height:22px;border:3px solid var(--iyi)}
#isaret-qr span{background:var(--iyi);color:#06111f}
#isaret-lz{width:30px;height:30px;border:3px solid var(--orta)}
#isaret-lz span{background:var(--orta);color:#06111f}

aside{flex:0 0 268px;display:flex;flex-direction:column;gap:7px;
  overflow-y:auto;min-height:0}
aside::-webkit-scrollbar{width:6px}
aside::-webkit-scrollbar-thumb{background:var(--cizgi);border-radius:3px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:6px;
  padding:8px 9px;flex:0 0 auto}
.bas{display:flex;align-items:center;gap:5px;margin-bottom:6px}
.bas h2{margin:0;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--soluk);font-weight:600}

.ipuc{display:inline-flex;align-items:center;justify-content:center;
  width:13px;height:13px;flex:0 0 13px;border-radius:50%;
  border:1px solid var(--cizgi);color:var(--soluk);font-size:9px;
  font-style:normal;cursor:help;position:relative}
.ipuc:hover{border-color:var(--vurgu);color:var(--vurgu)}
.ipuc::after{content:attr(data-ip);position:absolute;bottom:calc(100% + 6px);
  right:-6px;width:250px;background:#080b0f;border:1px solid var(--vurgu);
  border-radius:5px;padding:7px 9px;font-size:11px;line-height:1.5;
  color:var(--ana);text-align:left;opacity:0;visibility:hidden;
  transition:opacity .1s;z-index:60;white-space:normal;pointer-events:none;
  box-shadow:0 8px 24px rgba(0,0,0,.7)}
.ipuc:hover::after{opacity:1;visibility:visible}

label{display:flex;align-items:center;gap:6px;margin-top:5px;
  font-size:11px;color:var(--soluk)}
label>span{display:flex;align-items:center;gap:4px;flex:1 1 auto}
select{flex:0 0 128px;background:#1d2632;color:var(--ana);
  border:1px solid var(--cizgi);border-radius:4px;padding:3px 5px;
  font:inherit;font-size:11px;cursor:pointer}
select:hover{border-color:var(--vurgu)}

.satir{display:flex;gap:4px}
button{flex:1 1 auto;background:#1d2632;color:var(--ana);
  border:1px solid var(--cizgi);border-radius:4px;padding:5px 6px;
  font:inherit;font-size:11px;cursor:pointer;white-space:nowrap}
button:hover{border-color:var(--vurgu)}
button.acik{background:var(--vurgu);border-color:var(--vurgu);color:#06111f;font-weight:700}
button.genis{padding:7px 5px;font-weight:700;letter-spacing:.04em}
button.kayit.acik{background:var(--kotu);border-color:var(--kotu);color:#210708}

table{width:100%;border-collapse:collapse;font-size:11.5px}
td{padding:1px 0}
td:first-child{color:var(--soluk)}
td:last-child{text-align:right;font-variant-numeric:tabular-nums}
td.iyi{color:var(--iyi)} td.orta{color:var(--orta)} td.kotu{color:var(--kotu)}
.metin-kutu{margin-top:5px;padding:5px 6px;background:#0b0e13;border-radius:4px;
  font-size:10.5px;word-break:break-all;color:var(--soluk);max-height:46px;
  overflow-y:auto}
.metin-kutu.dolu{color:var(--ana)}

.hukum{font-size:15px;font-weight:700;letter-spacing:.03em;margin:2px 0 5px}
.hukum.iyi{color:var(--iyi)} .hukum.orta{color:var(--orta)} .hukum.kotu{color:var(--kotu)}

.odakSatir{display:flex;align-items:baseline;gap:7px}
.dev{font-size:26px;line-height:1;font-weight:700;font-variant-numeric:tabular-nums}
.dev small{font-size:12px;color:var(--soluk);font-weight:400}
.egilim{font-size:10px;letter-spacing:.08em;font-weight:700;color:var(--soluk)}
.egilim.artiyor{color:var(--iyi)} .egilim.azaliyor{color:var(--kotu)}
.bar{height:6px;background:#0b0e13;border-radius:3px;overflow:hidden;margin:5px 0 0}
.bar i{display:block;height:100%;width:0;background:var(--kotu);
  transition:width .12s linear,background .25s}
canvas{width:100%;height:40px;display:block;margin-top:4px}

/* AYARLAR katlanabilir — kurulunca bir daha dokunulmayan seyler burada */
details.ayarlar{background:var(--kart);border:1px solid var(--cizgi);
  border-radius:6px;flex:0 0 auto}
details.ayarlar>summary{list-style:none;cursor:pointer;padding:7px 9px;
  font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--soluk);font-weight:600;user-select:none}
details.ayarlar>summary::-webkit-details-marker{display:none}
details.ayarlar>summary::before{content:"▸ ";color:var(--vurgu)}
details.ayarlar[open]>summary::before{content:"▾ "}
details.ayarlar>div{padding:0 9px 9px}
.ipucu{color:var(--soluk);font-size:10px;margin:6px 0 0;line-height:1.4}
.hata{display:none;background:#3a1416;border:1px solid var(--kotu);color:#ffb4b0;
  border-radius:5px;padding:6px 8px;font-size:10.5px;word-break:break-word}
.hata.gorun{display:block}
@media (max-width:900px){html,body{overflow:auto}main{flex-wrap:wrap}aside{flex:1 1 100%}}
</style>
</head>
<body>

<header>
  <h1>YELPENCE KAMERA</h1>
  <span class="rozet" id="arayuz">—</span>
  <span class="cip kayit-cip" id="c-kayit">kayıt kapalı</span>
  <div class="cipler">
    <span class="cip"><b id="c-boyut">—</b></span>
    <span class="cip">fps <b id="c-fps">—</b></span>
    <span class="cip">bant <b id="c-mbps">—</b></span>
    <span class="cip">boyut <b id="c-mbdk">—</b></span>
    <span class="cip">cpu <b id="c-cpu">—</b></span>
    <span class="cip">ram <b id="c-ram">—</b></span>
    <span class="cip">ısı <b id="c-sic">—</b></span>
    <span class="cip">kısıt <b id="c-kis">—</b></span>
  </div>
</header>

<main>
  <div class="sahne"><div class="cerceve">
    <img id="kare" alt="kamera">
    <div class="nisan"></div>
    <div class="isaret" id="isaret-qr"><span>QR</span></div>
    <div class="isaret" id="isaret-lz"><span id="isaret-lz-ad">BÖLGE</span></div>
  </div></div>

  <aside>

    <div class="kart">
      <div class="satir">
        <button class="genis" data-profil="hotspot">HOTSPOT</button>
        <button class="genis" data-profil="ethernet">ETHERNET</button>
      </div>
      <div class="satir" style="margin-top:4px">
        <button class="kayit" id="btn-kayit">KAYIT</button>
        <button id="btn-foto">FOTO</button>
        <button id="btn-buyutec" title="Merkezin %25'i">4x</button>
      </div>
    </div>

    <div class="kart">
      <div class="bas"><h2>Algı</h2><i class="ipuc" data-ip="QR ve renk sonuçları. Kareye QR girince yeşil, renkli bölge girince turuncu halka görüntü üstünde belirir. QR yapışkandır: kareden çıksa da son okuma yaşıyla gösterilir.">?</i></div>
      <div class="hukum" id="a-hukum">—</div>
      <table>
        <tr><td>pozlama</td><td id="a-poz">—</td></tr>
        <tr><td>bulanıklık</td><td id="a-bul">—</td></tr>
        <tr><td>ışık</td><td id="a-isik">—</td></tr>
        <tr><td>QR</td><td id="a-qr">—</td></tr>
        <tr><td>renk</td><td id="a-lz">—</td></tr>
        <tr><td>dairesellik</td><td id="a-daire">—</td></tr>
      </table>
      <div class="metin-kutu" id="a-metin">QR metni burada çıkacak</div>
    </div>

    <div class="kart">
      <div class="bas"><h2>Odak</h2><i class="ipuc" data-ip="Sabit JPEG kalitesinde kare BOYUTU. Netleştikçe JPEG kötü sıkışır, kare büyür. Halkayı yavaş çevir: NETLEŞİYOR ▲ doğru yön. Tepeyi geçince %100'ün altına düşer — orası en iyi noktan.">?</i></div>
      <div class="odakSatir">
        <div class="dev"><span id="yuzde">—</span><small>%</small></div>
        <div class="egilim" id="egilim">ölçülüyor</div>
      </div>
      <div class="bar"><i id="cubuk"></i></div>
      <canvas id="grafik" width="600" height="84"></canvas>
    </div>

    <details class="ayarlar">
      <summary>Ayarlar</summary>
      <div>
        <label><span>Yakalama <i class="ipuc" data-ip="Sensörün hangi çözünürlükte OKUDUĞU. QR menzili buna bağlı. Üst kipler daha çok detay, daha düşük fps tavanı.">?</i></span><select id="s-mod"></select></label>
        <label><span>Önizleme <i class="ipuc" data-ip="Sana GÖNDERİLEN boyut. Yükseklik yakalamanın en-boy oranından türetilir, kırpma olmaz. TAM = küçültmesiz, ~125 Mbps, yalnız ethernette.">?</i></span><select id="s-onz"></select></label>
        <label><span>Kalite <i class="ipuc" data-ip="JPEG sıkıştırma kalitesi. ÖLÇÜLDÜ: tespite etkisi YOK — q45 de q90 da aynı mesafede okuyor. q90 sadece dosyayı 2,4 kat büyütür ve çözmeyi %21 yavaşlatır.">?</i></span><select id="s-kal"></select></label>
        <label><span>Pozlama <i class="ipuc" data-ip="Otomatik pozlama karanlıkta süreyi UZATARAK ışık toplar; drone o sürede yol aldığı için görüntü sürüklenir. ÖLÇÜLDÜ (4 m/s, 20 m): 1/250'de QR okundu, 1/125'te okunamadı. ⚠️ AMA pozlamayı kısaltmak ışığı da keser (1/15→1/500 = 33 kat az ışık). Kazanç tavandaysa kare kararır — keskin ama siyah, yine okunmaz.">?</i></span><select id="s-poz"></select></label>
        <label><span>Beyaz ayarı <i class="ipuc" data-ip="Yanlış beyaz ayarı kareyi tek renge kaydırır ve renk tespiti her yeri o renk sanır. Magenta kare 6 sahte KIRMIZI bölge üretmişti.">?</i></span><select id="s-awb"></select></label>
        <label><span>Referans <i class="ipuc" data-ip="Bulanıklık hesabının hangi uçuş koşulu için yapılacağı. Bulanıklık = hız × pozlama süresi × (piksel/metre). Kamera ayarı DEĞİL, yalnızca gösterge: 'bu hızda bu irtifada uçarsam bulanıklık kaç piksel olur'. QR için sınır ~3 px.">?</i></span><select id="s-ref"></select></label>
        <label><span>En küçük alan <i class="ipuc" data-ip="Bundan küçük renk lekeleri elenir. Kare ALANINA ORANLIDIR, mutlak piksel değil.">?</i></span><select id="s-alan"></select></label>
        <label><span>En az dairesellik <i class="ipuc" data-ip="Kontur alanı ÷ çevreleyen dairenin alanı. Kusursuz daire 1,0; KARE 0,64. ÖLÇÜLDÜ: gerçek hedef 0,985, bayrak 0,281, poster 0,130. Ayrımı yapan tek ölçüt bu.">?</i></span><select id="s-daire"></select></label>
        <div class="satir" style="margin-top:6px">
          <button id="btn-sifirla">TEPEYİ SIFIRLA</button>
          <button id="btn-kare">KAREYİ İNDİR</button>
        </div>
        <div class="metin-kutu" id="foto-kutu">henüz foto çekilmedi</div>
        <p class="ipucu" id="kayit-not">diskte en fazla 5 kayıt tutulur</p>
      </div>
    </details>

    <div class="hata" id="hata"></div>
  </aside>
</main>

<script>
const $ = (s) => document.querySelector(s);
const gecmis = [];
let d = {mod:'tam', onizleme:640, kalite:55, buyutec:false, awb:'auto'};

const MODLAR = __MODLAR__;
const ONIZLEMELER = __ONIZLEMELER__;
const KALITELER = __KALITELER__;
const BEYAZ = __BEYAZ__;
const POZLAMALAR = __POZLAMALAR__;
// Bulanıklık referansı: hız (m/s) ve irtifa (m). QR modülü 20 m'de 3,8 px;
// bulanıklık onu aşınca desen siliniyor (28 Ağustos ölçümü).
const REFLER = [[4,10],[4,20],[4,30],[6,20],[8,20],[2,20]];
let ref = [4,20];
const ALANLAR = [[0.0005,'%0,05'],[0.0015,'%0,15'],[0.005,'%0,5'],
                 [0.02,'%2'],[0.05,'%5']];
const DAIRELER = [0.50, 0.65, 0.75, 0.85, 0.92];
let esik = {alan:0.0015, daire:0.75};

function akisiTazele(){ $('#kare').src = '/akis?t=' + Date.now(); }
$('#kare').addEventListener('error', () => setTimeout(akisiTazele, 1200));
akisiTazele();

// Grafik YÜZDEYİ değil HAM keskinliği çizer, otomatik ölçekle. Sebep:
// tırmanırken tepe de seninle yükseldiği için yüzde %100'de yapışık kalır
// ve eğri düz görünür — tam da bakman gereken şey kaybolur.
function ciz(){
  const c = $('#grafik'), x = c.getContext('2d');
  const G = c.width, Y = c.height;
  x.clearRect(0,0,G,Y);
  if (gecmis.length < 2) return;
  const dizi = gecmis.map(o => o.k);
  let alt = Math.min(...dizi), ust = Math.max(...dizi);
  const pay = Math.max((ust-alt)*0.15, ust*0.01, 0.3);
  alt -= pay; ust += pay;
  x.strokeStyle = '#232c39'; x.lineWidth = 1;
  for (let i=1;i<4;i++){ const y=Y*i/4; x.beginPath(); x.moveTo(0,y); x.lineTo(G,y); x.stroke(); }
  x.strokeStyle = '#4da3ff'; x.lineWidth = 2; x.beginPath();
  const adim = G/Math.max(1,(dizi.length-1));
  dizi.forEach((v,i) => {
    const y = Y - ((v-alt)/(ust-alt))*(Y-4) - 2;
    i ? x.lineTo(i*adim,y) : x.moveTo(i*adim,y);
  });
  x.stroke();
}

function egilimGuncelle(){
  const e = $('#egilim');
  if (gecmis.length < 20){ e.textContent='ölçülüyor'; e.className='egilim'; return; }
  const ort = (a) => a.reduce((t,o)=>t+o.k,0)/a.length;
  const son = ort(gecmis.slice(-5)), onceki = ort(gecmis.slice(-20,-15));
  const fark = (son-onceki)/Math.max(onceki,0.001)*100;
  if (fark > 0.4){ e.textContent='NETLEŞİYOR ▲'; e.className='egilim artiyor'; }
  else if (fark < -0.4){ e.textContent='BULANIKLAŞIYOR ▼'; e.className='egilim azaliyor'; }
  else { e.textContent='SABİT'; e.className='egilim'; }
}

function boya(el, deger, orta, kotu){
  el.className = deger >= kotu ? 'kotu' : (deger >= orta ? 'orta' : 'iyi');
}

// Sonuçlar burada çıkıyor ki terminalden `ros2 topic echo` yazmak gerekmesin.
// QR YAPIŞKAN: kareye bir saniye girip çıkıyor; anlık durum gösterilseydi tam
// o anda ekrana bakmak gerekirdi.
function algiGoster(a){
  const qrEl=$('#a-qr'), lzEl=$('#a-lz'), metin=$('#a-metin');
  const isQ=$('#isaret-qr'), isL=$('#isaret-lz');
  isQ.style.display = isL.style.display = 'none';

  if (!a){
    qrEl.textContent='köprü kapalı'; qrEl.className='';
    lzEl.textContent='—'; lzEl.className='';
    metin.textContent='kamera_zincir.sh basla'; metin.className='metin-kutu';
    return;
  }
  const q = a.qr;
  if (q){
    const yas = a.an - q.an;
    if (yas < 3){
      qrEl.textContent = q.valid ? 'GEÇERLİ' : (q.decoded ? 'OKUNDU' : 'görüldü');
      qrEl.className = q.valid ? 'iyi' : 'orta';
      isQ.style.left = (q.image_x*100)+'%';
      isQ.style.top  = (q.image_y*100)+'%';
      isQ.style.display = 'block';
    } else {
      qrEl.textContent = 'son okuma ' + yas.toFixed(0) + ' sn önce';
      qrEl.className = '';
    }
    const t = q.raw_text || q.error_message || '';
    metin.textContent = t || '(boş)';
    metin.className = 'metin-kutu' + (t ? ' dolu' : '');
  } else {
    qrEl.textContent='henüz okunmadı'; qrEl.className='';
    metin.textContent='QR metni burada çıkacak'; metin.className='metin-kutu';
  }

  if (a.esik){
    if (a.esik.min_zone_area_frac != null) esik.alan = a.esik.min_zone_area_frac;
    if (a.esik.min_circularity != null) esik.daire = a.esik.min_circularity;
  }
  const dEl = $('#a-daire');
  const z = a.lz;
  if (z && (a.an - z.an) < 3 && z.zone_detected){
    dEl.textContent = (z.dairesellik || []).map(v => v.toFixed(2)).join(' ') || '—';
    lzEl.textContent = z.zone_count + '× ' + (z.primary_color || '');
    lzEl.className = 'iyi';
    isL.style.left = (z.image_x*100)+'%';
    isL.style.top  = (z.image_y*100)+'%';
    isL.style.display = 'block';
    $('#isaret-lz-ad').textContent = z.primary_color || 'BÖLGE';
  } else {
    lzEl.textContent = z ? 'yok' : '—'; lzEl.className = '';
    dEl.textContent = '—';
  }
}

async function olc(){
  try{
    const o = await (await fetch('/olcum',{cache:'no-store'})).json();
    d = {mod:o.mod, onizleme:o.onizleme_g, kalite:o.kalite,
         buyutec:o.buyutec, awb:o.awb, pozlama:o.pozlama};

    const p = o.yuzde;
    $('#yuzde').textContent = p.toFixed(0);
    const cubuk = $('#cubuk');
    cubuk.style.width = Math.max(2,Math.min(100,p)) + '%';
    cubuk.style.background = p>=97 ? 'var(--iyi)' : (p>=85 ? 'var(--orta)' : 'var(--kotu)');

    $('#c-boyut').textContent = o.yakalama + ' → ' + o.onizleme;
    $('#c-fps').textContent   = o.fps;
    const mb=$('#c-mbps'); mb.textContent = o.mbps + ' Mbps'; boya(mb, o.mbps, 10, 30);

    const s = o.sistem || {};
    const cpu=$('#c-cpu'); cpu.textContent=(s.cpu ?? '—')+'%'; boya(cpu, s.cpu||0, 80, 95);
    const ram=$('#c-ram'); ram.textContent=(s.ram_bos_mb ?? '—')+' MB';
    ram.className=(s.ram_bos_mb ?? 9999)<300?'kotu':((s.ram_bos_mb ?? 9999)<600?'orta':'iyi');
    const sic=$('#c-sic'); sic.textContent=(s.sicaklik ?? '—')+'°'; boya(sic, s.sicaklik||0, 70, 80);
    // POZLAMA ve BULANIKLIK — QR için belirleyici olan sayı bu.
    const pz = o.poz_olcum || {};
    const pozEl = $('#a-poz'), bulEl = $('#a-bul');
    if (pz.ExposureTime){
      const sn = pz.ExposureTime / 1e6;
      pozEl.textContent = '1/' + Math.round(1/sn) + ' sn  ×' +
        (pz.AnalogueGain || 1).toFixed(1);
      // 4056 px / (2 × irtifa × tan(28,2°)) = piksel/metre
      const pxm = 4056 / (1.073 * ref[1]);
      const bulanik = ref[0] * sn * pxm;
      bulEl.textContent = bulanik.toFixed(1) + ' px  @' + ref[0] + 'm/s '
                          + ref[1] + 'm';
      bulEl.className = bulanik > 4 ? 'kotu' : (bulanik > 2.5 ? 'orta' : 'iyi');
      pozEl.className = bulanik > 4 ? 'kotu' : '';

      // ⚠️ BULANIKLIK TEK BASINA YETMEZ. Poz suresini kisaltmak bulanikligi
      // dusurur ama isigi da keser: 1/15 -> 1/500 = 33 KAT az isik. Kazanc
      // tavandaysa (x16) kamerada telafi edecek kaldirac kalmamis demektir
      // ve kare kararir. Keskin bir siyah kare de okunmaz.
      const isikEl = $('#a-isik'), hukEl = $('#a-hukum');
      const kazancTavanda = (pz.AnalogueGain || 0) >= 15.5;
      isikEl.textContent = (pz.Lux != null ? pz.Lux.toFixed(1) + ' lüks' : '—')
        + (kazancTavanda ? '  (kazanç TAVANDA)' : '');
      isikEl.className = kazancTavanda ? 'kotu' : 'iyi';

      if (bulanik > 4){
        hukEl.textContent = 'HAYIR — bulanık'; hukEl.className = 'kotu';
      } else if (kazancTavanda){
        hukEl.textContent = 'HAYIR — ışık yetersiz'; hukEl.className = 'kotu';
      } else if (bulanik > 2.5){
        hukEl.textContent = 'sınırda'; hukEl.className = 'orta';
      } else {
        hukEl.textContent = 'EVET'; hukEl.className = 'iyi';
      }
    } else {
      pozEl.textContent = '—'; bulEl.textContent = '—';
      $('#a-isik').textContent = '—'; $('#a-hukum').textContent = '—';
      pozEl.className = bulEl.className = '';
    }

    const kay = o.kayit || {};
    const kc = $('#c-kayit'), kb = $('#btn-kayit');
    if (kay.acik){
      const dk = Math.floor(kay.saniye/60), sn = Math.floor(kay.saniye%60);
      kc.textContent = '● KAYIT ' + dk + ':' + String(sn).padStart(2,'0')
                       + '  ' + kay.mb + ' MB';
      kc.classList.add('acik'); kb.classList.add('acik');
      kb.textContent = 'KAYDI DURDUR';
    } else {
      kc.textContent = kay.hata ? ('kayıt HATA: ' + kay.hata) : 'kayıt kapalı';
      kc.classList.remove('acik'); kb.classList.remove('acik');
      kb.textContent = 'KAYIT BAŞLAT';
    }

    // CANLI BOYUT KESTIRIMI — o anki kare boyutu x fps. Tablodan degil
    // olcumden: ayni ayar gece gurultusunde iki katina cikabiliyor.
    // Basliktaki cipe yaziliyor; kenar cubugu kisa kalsin diye.
    const mbdk = o.ham_kb * o.fps * 60 / 1024;
    const bicim = (mb) => mb >= 1024 ? (mb/1024).toFixed(1) + ' GB'
                                     : mb.toFixed(0) + ' MB';
    const bos = o.disk_bos_mb || 0;
    const kalanDk = mbdk > 0 ? bos / mbdk : 0;
    const boyutCip = $('#c-mbdk');
    boyutCip.textContent = bicim(mbdk) + '/dk · ' + kalanDk.toFixed(0) + ' dk yer';
    boyutCip.className = kalanDk < 5 ? 'kotu' : (kalanDk < 15 ? 'orta' : '');

    const not = $('#kayit-not');
    let m = 'diskte en fazla ' + (kay.sinir ?? 5) + ' kayıt tutulur';
    if (kay.silinen && kay.silinen.length)
      m += ' — silinen: ' + kay.silinen.join(', ');
    not.textContent = m;

    const kis=$('#c-kis'); kis.textContent=s.kisitlama ?? '—';
    kis.className=(s.kisitlama==='0x0')?'iyi':((s.kisitlama&&s.kisitlama!=='?')?'kotu':'');

    const a=$('#arayuz');
    a.textContent = (o.arayuz || '?') + (o.sunucu_ip ? ' ' + o.sunucu_ip : '');
    a.className = 'rozet ' + (/^(eth|en|usb)/.test(o.arayuz||'') ? 'eth'
                 : (/^(wl|wlan)/.test(o.arayuz||'') ? 'wifi' : ''));

    algiGoster(o.algi);
    gecmis.push({y:p, k:o.yumusak_kb});
    if (gecmis.length > 150) gecmis.shift();
    ciz(); egilimGuncelle(); secicileriTazele();

    const h=$('#hata'); h.textContent=o.hata || '';
    h.classList.toggle('gorun', !!o.hata);
  }catch(e){ /* ağ koptu; bir sonraki turda yine denenir */ }
}

function secicileriKur(){
  const m=$('#s-mod');
  for (const [k,v] of Object.entries(MODLAR)){
    const o=document.createElement('option');
    o.value=k; o.textContent=v.ad+'  ≤'+v.fps+'fps'; m.appendChild(o);
  }
  const z=$('#s-onz');
  for (const g of ONIZLEMELER){
    const o=document.createElement('option');
    o.value=g; o.textContent = g===0 ? 'TAM (kırpmasız)' : g+' px'; z.appendChild(o);
  }
  const q=$('#s-kal');
  for (const k of KALITELER){
    const o=document.createElement('option'); o.value=k; o.textContent='q'+k; q.appendChild(o);
  }
  const pz=$('#s-poz');
  for (const [k,ad] of POZLAMALAR){
    const o=document.createElement('option'); o.value=k; o.textContent=ad; pz.appendChild(o);
  }
  pz.onchange = () => { d.pozlama = pz.value; ayarla(); };
  const rf=$('#s-ref');
  for (const [h,i] of REFLER){
    const o=document.createElement('option'); o.value=h+','+i;
    o.textContent = h+' m/s · '+i+' m'; rf.appendChild(o);
  }
  rf.value = ref.join(',');
  rf.onchange = () => { ref = rf.value.split(',').map(Number); };

  const w=$('#s-awb');
  for (const [k,ad] of BEYAZ){
    const o=document.createElement('option'); o.value=k; o.textContent=ad; w.appendChild(o);
  }
  const al=$('#s-alan');
  for (const [v,ad] of ALANLAR){
    const o=document.createElement('option'); o.value=v; o.textContent=ad; al.appendChild(o);
  }
  const dr=$('#s-daire');
  for (const v of DAIRELER){
    const o=document.createElement('option'); o.value=v;
    o.textContent = v.toFixed(2).replace('.',',') + (v===0.64?'':''); dr.appendChild(o);
  }
  al.value = esik.alan; dr.value = esik.daire;
  const esikGonder = () => {
    esik.alan = +al.value; esik.daire = +dr.value;
    fetch(`/algi_ayar?alan=${esik.alan}&daire=${esik.daire}`, {cache:'no-store'});
  };
  al.onchange = esikGonder; dr.onchange = esikGonder;

  m.onchange = () => { d.mod = m.value; ayarla(); };
  z.onchange = () => { d.onizleme = +z.value; ayarla(); };
  q.onchange = () => { d.kalite = +q.value; ayarla(); };
  w.onchange = () => { d.awb = w.value; ayarla(); };
}

function secicileriTazele(){
  $('#s-mod').value = d.mod;
  $('#s-onz').value = d.onizleme;
  $('#s-kal').value = d.kalite;
  $('#s-awb').value = d.awb;
  $('#s-poz').value = d.pozlama;
  $('#btn-buyutec').classList.toggle('acik', d.buyutec);
}

async function ayarla(){
  await fetch(`/ayar?mod=${d.mod}&onizleme=${d.onizleme}&kalite=${d.kalite}`
              + `&b=${d.buyutec?1:0}&awb=${d.awb}&poz=${d.pozlama}`,
              {cache:'no-store'});
  gecmis.length = 0; setTimeout(akisiTazele, 900);
}
document.querySelectorAll('[data-profil]').forEach(b => b.onclick = async () => {
  await fetch('/profil?ad=' + b.dataset.profil, {cache:'no-store'});
  gecmis.length = 0; setTimeout(akisiTazele, 900);
});
$('#btn-buyutec').onclick = () => { d.buyutec = !d.buyutec; ayarla(); };
$('#btn-sifirla').onclick = () => { fetch('/sifirla',{cache:'no-store'}); gecmis.length = 0; };
$('#btn-kare').onclick = () => { window.location = '/kare.jpg'; };

// FOTO CEK — cekim sirasinda kamera gecici olarak 4K'ya cikiyor, o yuzden
// akis birkac saniye donuyor. Dugmeyi kilitliyoruz ki ust uste basilmasin.
const fotoDugme = $('#btn-foto');
fotoDugme.onclick = async () => {
  fotoDugme.disabled = true;
  const eski = fotoDugme.textContent;
  fotoDugme.textContent = 'ÇEKİLİYOR…';
  $('#foto-kutu').textContent = "kamera 4K'ya alınıyor, poz oturuyor…";
  try {
    const r = await (await fetch('/foto', {cache:'no-store'})).json();
    $('#foto-kutu').textContent = r.ok ? '' : ('HATA: ' + (r.hata || '?'));
    if (r.ok) fotolariTazele();
  } catch (e) {
    $('#foto-kutu').textContent = 'HATA: istek düştü';
  }
  fotoDugme.textContent = eski;
  fotoDugme.disabled = false;
};

async function fotolariTazele(){
  try{
    const liste = await (await fetch('/fotolar',{cache:'no-store'})).json();
    const k = $('#foto-kutu');
    if (!liste.length){ k.textContent = 'henüz foto çekilmedi'; return; }
    k.innerHTML = liste.slice(0,6).map(f =>
      '<a href="/foto.jpg?ad=' + encodeURIComponent(f.ad) + '" '
      + 'style="color:var(--vurgu);text-decoration:none">▼ ' + f.ad
      + '</a>  <span style="color:var(--soluk)">' + f.kb + ' KB</span>'
    ).join('<br>');
  }catch(e){ /* ag koptu */ }
}
fotolariTazele();
$('#btn-kayit').onclick = () => {
  const acik = $('#btn-kayit').classList.contains('acik');
  fetch('/kayit?ac=' + (acik ? 0 : 1), {cache:'no-store'});
};
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'SELECT') return;
  if (e.key === 'r') $('#btn-sifirla').click();
  if (e.key === 'b') $('#btn-buyutec').click();
});

secicileriKur(); setInterval(olc, 200); olc();
</script>
</body>
</html>
"""

SAYFA_BAYT = (
    SAYFA
    .replace('__MODLAR__', json.dumps(
        {k: {'ad': v['ad'], 'fps': v['fps']} for k, v in MODLAR.items()}))
    .replace('__ONIZLEMELER__', json.dumps(list(ONIZLEMELER)))
    .replace('__KALITELER__', json.dumps(list(KALITELER)))
    .replace('__BEYAZ__', json.dumps([list(b) for b in BEYAZ_AYARLARI]))
    .replace('__POZLAMALAR__', json.dumps([list(b) for b in POZLAMALAR]))
    .encode('utf-8')
)


class Istek(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    yayin: Yayin = None
    sistem: Sistem = None
    algi_yolu: str = ''
    algi_ayar_yolu: str = ''
    kayit_dizin: str = ''
    foto_dizin: str = ''
    _arayuzler: dict = {}
    _arayuz_an: float = 0.0

    def log_message(self, bicim, *args):        # noqa: A002
        pass                                     # erisim kaydi gurultu yapmasin

    def _duz(self, govde: bytes, tip: str, ek: dict | None = None) -> None:
        self.send_response(200)
        self.send_header('Content-Type', tip)
        self.send_header('Content-Length', str(len(govde)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(govde)

    def _arayuz_adi(self) -> tuple[str, str]:
        simdi = time.monotonic()
        if simdi - Istek._arayuz_an > 5.0:
            Istek._arayuzler = arayuz_haritasi()
            Istek._arayuz_an = simdi
        try:
            ip = self.connection.getsockname()[0]
        except OSError:
            return '', ''
        return Istek._arayuzler.get(ip, ''), ip

    def do_GET(self):                            # noqa: N802
        yol = urlparse(self.path)
        s = parse_qs(yol.query)

        if yol.path == '/':
            return self._duz(SAYFA_BAYT, 'text/html; charset=utf-8')

        if yol.path == '/olcum':
            o = self.yayin.olcum()
            o['sistem'] = self.sistem.veri()
            o['arayuz'], o['sunucu_ip'] = self._arayuz_adi()
            o['algi'] = algi_oku(self.algi_yolu) if self.algi_yolu else None
            return self._duz(json.dumps(o).encode(), 'application/json')

        if yol.path == '/sifirla':
            self.yayin.tepeyi_sifirla()
            return self._duz(b'{"ok":true}', 'application/json')

        if yol.path == '/ayar':
            y = self.yayin
            self.yayin.ayarla(
                s.get('mod', [y.mod])[0],
                int(s.get('onizleme', [y.onizleme])[0]),
                int(s.get('kalite', [y.kalite])[0]),
                s.get('b', ['0'])[0] == '1',
                s.get('awb', [y.awb])[0],
                s.get('poz', [y.pozlama])[0])
            return self._duz(b'{"ok":true}', 'application/json')

        if yol.path == '/profil':
            p = PROFILLER.get(s.get('ad', [''])[0])
            if p:
                self.yayin.ayarla(p['mod'], p['onizleme'], p['kalite'], False,
                                  '', self.yayin.pozlama)
            return self._duz(b'{"ok":true}', 'application/json')

        if yol.path == '/kare.jpg':
            _, kare = self.yayin.kare_bekle(-1)
            if not kare:
                return self.send_error(503, 'kare yok')
            ad = time.strftime('yelpence_%Y%m%d_%H%M%S.jpg')
            return self._duz(kare, 'image/jpeg',
                             {'Content-Disposition': f'attachment; filename={ad}'})

        if yol.path == '/foto':
            # Senkron: cekim ~8-12 sn surer (4K'ya gecis + poz oturmasi +
            # geri donus). Sayfa bu sure boyunca "cekiliyor" gosteriyor.
            sonuc = self.yayin.foto_cek(self.foto_dizin)
            return self._duz(json.dumps(sonuc).encode(), 'application/json')

        if yol.path == '/fotolar':
            try:
                ad = sorted((x for x in os.listdir(self.foto_dizin)
                             if x.endswith('.jpg')), reverse=True)
                liste = [{'ad': a, 'kb': round(os.path.getsize(
                    os.path.join(self.foto_dizin, a)) / 1024)} for a in ad[:20]]
            except OSError:
                liste = []
            return self._duz(json.dumps(liste).encode(), 'application/json')

        if yol.path == '/foto.jpg':
            ad = os.path.basename(s.get('ad', [''])[0])
            tam = os.path.join(self.foto_dizin, ad)
            if not ad.endswith('.jpg') or not os.path.isfile(tam):
                return self.send_error(404, 'foto yok')
            with open(tam, 'rb') as f:
                govde = f.read()
            return self._duz(govde, 'image/jpeg',
                             {'Content-Disposition':
                              f'attachment; filename={ad}'})

        if yol.path == '/kayit':
            if s.get('ac', ['0'])[0] == '1':
                d = self.yayin.kayit_ac(self.kayit_dizin)
                govde = json.dumps({'ok': bool(d), 'dosya': d}).encode()
            else:
                self.yayin.kayit_kapa()
                govde = b'{"ok":true}'
            return self._duz(govde, 'application/json')

        if yol.path == '/algi_ayar':
            # Sayfa esikleri buraya yaziyor; konteynerdeki `algi_kopru`
            # dosyayi izleyip `vision_node`'un parametrelerini set ediyor.
            # Sayfanin ROS'u yok, o yuzden dogrudan cagiramaz.
            try:
                istek = {
                    'min_zone_area_frac': float(s['alan'][0]),
                    'min_circularity': float(s['daire'][0]),
                    'min_zone_area_px': 0.0,   # oranli esik yonetsin
                }
            except (KeyError, ValueError, IndexError):
                return self.send_error(400, 'alan/daire gerekli')
            gecici = self.algi_ayar_yolu + '.tmp'
            try:
                with open(gecici, 'w', encoding='utf-8') as f:
                    json.dump(istek, f)
                os.replace(gecici, self.algi_ayar_yolu)
            except OSError as e:
                return self.send_error(500, str(e))
            return self._duz(b'{"ok":true}', 'application/json')

        if yol.path == '/akis':
            return self._akis()

        self.send_error(404)

    def _akis(self) -> None:
        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Content-Type',
                         'multipart/x-mixed-replace; boundary=' + SINIR.decode())
        self.end_headers()
        son = -1
        try:
            while True:
                son, kare = self.yayin.kare_bekle(son)
                if kare is None:
                    continue
                if self.yayin.foto_modunda():
                    continue        # 4K kareler tarayiciya gitmesin
                self.wfile.write(b'--' + SINIR + b'\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n')
                self.wfile.write(b'Content-Length: %d\r\n\r\n' % len(kare))
                self.wfile.write(kare)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass                                 # tarayici kapandi, normal


def main() -> int:
    a = argparse.ArgumentParser(description='Kamera yayini ve odak/QR testi')
    a.add_argument('--port', type=int, default=8080)
    a.add_argument('--profil', default='hotspot', choices=sorted(PROFILLER))
    a.add_argument('--algi',
                   default=os.path.expanduser('~/yelpence_ws/algi_durum.json'),
                   help='algi_kopru dugumunun yazdigi JSON (host yolu)')
    a.add_argument('--algi-ayar',
                   default=os.path.expanduser('~/yelpence_ws/algi_ayar.json'),
                   help='esik istekleri buraya yazilir (host yolu)')
    a.add_argument('--kayit-dizin',
                   default=os.path.expanduser('~/kamera_kayit'),
                   help='yerel kayitlarin yazilacagi dizin')
    a.add_argument('--foto-dizin',
                   default=os.path.expanduser('~/kamera_foto'),
                   help='tam cozunurluklu fotolarin yazilacagi dizin')
    a.add_argument('--kayit', action='store_true',
                   help='acilista KAYDI BASLAT (ucus testinde unutmamak icin)')
    a.add_argument('--kayit-sayisi', type=int, default=KAYIT_SINIRI,
                   help=f'diskte tutulacak en fazla kayit (varsayilan '
                        f'{KAYIT_SINIRI}); sinira gelince en eski silinir')
    d = a.parse_args()

    p = PROFILLER[d.profil]
    yayin = Yayin(p['mod'], p['onizleme'], p['kalite'])
    yayin.kayit_siniri = max(1, d.kayit_sayisi)
    yayin.baslat()
    Istek.yayin = yayin
    Istek.sistem = Sistem()
    Istek.algi_yolu = d.algi
    Istek.algi_ayar_yolu = d.algi_ayar
    Istek.kayit_dizin = d.kayit_dizin
    Istek.foto_dizin = d.foto_dizin
    if d.kayit:
        yol = yayin.kayit_ac(d.kayit_dizin)
        print(f'  KAYIT ACIK -> {yol or "BASLATILAMADI"}', flush=True)

    sunucu = ThreadingHTTPServer(('0.0.0.0', d.port), Istek)
    sunucu.daemon_threads = True
    for ip, ad in sorted(arayuz_haritasi().items()):
        if ad != 'lo':
            print(f'  http://{ip}:{d.port}/   ({ad})', flush=True)
    print('  Ctrl-C ile dur', flush=True)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print('\n  duruyor...', flush=True)
    finally:
        yayin.durdur()          # kaydi fsync ile kapatir
        sunucu.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
