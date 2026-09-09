#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""QR ICIN SADE KAMERA YAYINI — her zaman 4K, q90.

🔴 8 EYLUL 2026, OPERATOR: "bu yayin konusunda bunu kopyalamak gibi bir sey
yap, ama sadece ihtiyacimiz olan kisim kalsin, onu kullanalim. Her zaman
4k q90 olacak sekilde qr okunacak."

`kamera_yayin.py` 1923 satir ve ICINDE COK SEY VAR: web arayuzu, SD karta
kayit, foto cekme, profiller, algi esik ayarlari, buyutec, kucultme,
canli parametre API'si. Ucusta QR okumak icin bunlarin HICBIRI gerekmiyor
ve her biri bir arıza yuzeyi. Bugun o surec kendiliginden oldu, camera_driver
"Kamera acilamadi" verdi ve QR okuma sessizce bitti.

BU DOSYA YALNIZ SUNU YAPAR:
    rpicam-vid (4056x3040, q90) -> MJPEG -> http://0.0.0.0:8080/akis

`camera_driver` ayni ucu (`/akis`) parametresiz cagiriyor ve TAM cozunurluk
aliyor — yani ROS zinciri degismeden calisir, tek satir dokunmaya gerek yok.

AYARLAR SABIT, API YOK. Degistirilebilir olmasi bugun ise yaramadi, tersine
"acaba hangi ayardaydi" sorusunu dogurdu. Degistirmek gerekirse bu dosya
duzenlenir ve yeniden baslatilir.

Degerlerin hepsi `kamera_yayin.py`den OLCULMUS haliyle alindi:
    kip      4056:3040:12:P   (IMX477 tam sensor, 12,3 MP)
    fps      5                (5 Eylul: QR isleme 2,5 Hz, 10 fps iki kat fazlaydi)
    kalite   90               (operator, 8 Eylul)
    pozlama  sport            (28 Agustos: sabit 1/250 gunesli tasta kirpiyordu)
    kazanc   2.5923,1.2225    (kalibre AWB; auto AWB kare kare renk kaydiriyordu)

KULLANIM
    setsid nohup python3 ~/yelpence_ws/kamera_qr.py \
        > ~/kamera_qr.log 2>&1 < /dev/null &

BAGIMLILIK: yalniz Python stdlib + rpicam-vid.
"""

import http.server
import socketserver
import subprocess
import threading
import time

PORT = 8080
SINIR = b'yelpencekare'

# --- SABIT AYARLAR — bilerek degistirilemez (bkz. modul aciklamasi) --------
KIP = '4056:3040:12:P'
GENISLIK, YUKSEKLIK = 4056, 3040
FPS = 5
KALITE = 90
POZLAMA = 'sport'
KAZANC = '2.5923,1.2225'

# rpicam-vid olurse bu kadar bekleyip yeniden baslatilir. Sifir yapmak
# bozuk bir kamerada sonsuz hizli dongu demek olurdu (CPU yakar).
YENIDEN_BASLATMA_BEKLEME_S = 0.8


def komut() -> list:
    """rpicam-vid komut satiri. --flush sart: kare beklemeden aksin."""
    return [
        'rpicam-vid', '-n', '-t', '0', '--codec', 'mjpeg',
        '--mode', KIP,
        '--width', str(GENISLIK), '--height', str(YUKSEKLIK),
        '--framerate', str(FPS),
        '-q', str(KALITE),
        '--denoise', 'off', '--sharpness', '0', '--flush',
        # awbgains verilince rpicam AWB'yi kapatir; --awb ile BIRLIKTE
        # verilmez (kamera_yayin.py'de de ayri kollar).
        '--awbgains', KAZANC,
        '--exposure', POZLAMA,
        '-o', '-',
    ]


class Kamera:
    """rpicam-vid'i besler, son MJPEG karesini paylasir, olurse yeniden acar."""

    def __init__(self) -> None:
        self._kilit = threading.Condition()
        self._kare = None
        self._sayac = 0
        self._surec = None
        self._hata = ''
        self._kare_sayaci = 0
        self._basladi = time.monotonic()

    # --------------------------------------------------------------- yasam

    def baslat(self) -> None:
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self) -> None:
        """rpicam-vid olurse YENIDEN ACAR. Bugun surecin olmesi QR okumayi
        sessizce bitirdi; tek basina yeniden baslama bunun yarisini kapatir
        (digeri: bu Python surecini disaridan canli tutmak)."""
        while True:
            try:
                self._surec = subprocess.Popen(
                    komut(), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, bufsize=0)
            except FileNotFoundError:
                self._hata = 'rpicam-vid bulunamadi'
                print('[kamera_qr] rpicam-vid bulunamadi', flush=True)
                return

            self._hata = ''
            threading.Thread(target=self._stderr_oku,
                             args=(self._surec,), daemon=True).start()
            try:
                self._kareleri_oku(self._surec)
            except Exception as e:                        # noqa: BLE001
                self._hata = f'akis: {e}'

            kod = self._surec.poll()
            print(f'[kamera_qr] rpicam-vid bitti (kod={kod}) '
                  f'hata="{self._hata}" — yeniden aciliyor', flush=True)
            time.sleep(YENIDEN_BASLATMA_BEKLEME_S)

    def _stderr_oku(self, surec) -> None:
        """Sessiz olum olmasin — rpicam-vid'in hatasi loga dussun."""
        for satir in iter(surec.stderr.readline, b''):
            m = satir.decode('utf-8', 'replace').strip()
            if m and ('ERROR' in m or 'error' in m or 'Invalid' in m):
                self._hata = m[:200]
                print(f'[kamera_qr] rpicam-vid: {m[:200]}', flush=True)

    def _kareleri_oku(self, surec) -> None:
        """MJPEG akisini FFD8..FFD9 sinirlarindan kareye boler."""
        tampon = bytearray()
        while True:
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

    def _kare_geldi(self, kare: bytes) -> None:
        with self._kilit:
            self._kare = kare
            self._sayac += 1
            self._kare_sayaci += 1
            self._kilit.notify_all()

    # ---------------------------------------------------------- okuyucular

    def kare_bekle(self, son: int, zaman_asimi: float = 5.0):
        with self._kilit:
            if self._sayac == son:
                self._kilit.wait(zaman_asimi)
            return self._sayac, self._kare

    def durum(self) -> dict:
        gecen = max(1e-6, time.monotonic() - self._basladi)
        with self._kilit:
            boy = len(self._kare) if self._kare else 0
            sayac = self._kare_sayaci
        return {
            'kip': KIP, 'genislik': GENISLIK, 'yukseklik': YUKSEKLIK,
            'fps_hedef': FPS, 'kalite': KALITE, 'pozlama': POZLAMA,
            'kazanc': KAZANC,
            'kare_kb': round(boy / 1024.0, 1),
            'kare_sayisi': sayac,
            'fps_olculen': round(sayac / gecen, 2),
            'hata': self._hata,
        }


class Istek(http.server.BaseHTTPRequestHandler):
    """Iki uc: /akis (camera_driver icin) ve /durum (teshis icin)."""

    kamera: Kamera = None

    def log_message(self, *_a) -> None:
        pass                          # her istegi loglamak logu bogar

    def do_GET(self) -> None:
        if self.path.startswith('/akis'):
            return self._akis()
        if self.path.startswith('/durum'):
            import json
            govde = json.dumps(self.kamera.durum()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
            return
        self.send_error(404)

    def _akis(self) -> None:
        """MJPEG akisi — KUCULTME YOK, kare oldugu gibi gider.

        camera_driver bu ucu parametresiz cagiriyor ve tam cozunurluk
        bekliyor. Kucultme secenegi BILEREK YOK: bu dosyanin tek isi
        algi zincirini beslemek.
        """
        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Content-Type',
                         'multipart/x-mixed-replace; boundary=' + SINIR.decode())
        self.end_headers()
        son = -1
        try:
            while True:
                son, kare = self.kamera.kare_bekle(son)
                if kare is None:
                    continue
                self.wfile.write(b'--' + SINIR + b'\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n')
                self.wfile.write(b'Content-Length: %d\r\n\r\n' % len(kare))
                self.wfile.write(kare)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass                      # istemci kapadi — normal


class Sunucu(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    kamera = Kamera()
    kamera.baslat()
    Istek.kamera = kamera
    print(f'[kamera_qr] {GENISLIK}x{YUKSEKLIK} q{KALITE} {FPS}fps '
          f'poz={POZLAMA} — http://0.0.0.0:{PORT}/akis', flush=True)
    with Sunucu(('', PORT), Istek) as s:
        s.serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
