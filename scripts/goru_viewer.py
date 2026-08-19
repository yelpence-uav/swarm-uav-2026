#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""Canli goru izleyici — BIZIM vision_node dedektorleriyle bounding box.

Ne yapar: picam-web'in yayinindan (http://127.0.0.1:8080/stream) kareyi alir,
BIZIM kodumuzla (qr_detector + landing_zone_detector) QR ve kirmizi/mavi bolge
bulur, ETRAFINA KUTU cizer, sonucu :8090'da MJPEG olarak yayinlar.
Tarayicidan  http://<pi-ip>:8090  acinca canli goruntu + bizim kutular gorunur.
Ses YOK. picam-web'e dokunmaz (sadece yayinini okur).

Kullanim (bu dosya + qr_detector.py + landing_zone_detector.py ayni klasorde):
    python3 goru_viewer.py
"""
import http.server
import os
import socket
import socketserver
import sys
import threading
import time
import types

import cv2

import numpy as np

# pyzbar bu Debian'da paketli degil; qr_detector.py'nin yuklenmesi icin shim.
try:
    from pyzbar.pyzbar import decode as _d  # noqa: F401
    HAVE_PYZBAR = True
except ImportError:
    HAVE_PYZBAR = False
    _f = types.ModuleType('pyzbar.pyzbar')
    _f.decode = lambda i: []
    _p = types.ModuleType('pyzbar')
    _p.pyzbar = _f
    sys.modules['pyzbar'] = _p
    sys.modules['pyzbar.pyzbar'] = _f

from landing_zone_detector import LandingZoneDetector
from qr_detector import QRDetector

SRC = 'http://127.0.0.1:8080/stream'
PORT = 8090
DET_W = 1024   # tespit + gosterim genisligi (hiz icin kucultulur)
QR_HER = 3     # QR'i her N. karede tara (zbar pahali); renk her kare.
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tespit.log')
# Tespit olunca (kutu cizilince) laptop'a UDP sinyal -> laptop ses calar.
SES_ADDR = tuple(os.environ.get('SES_ADDR', '172.20.10.2:9099').rsplit(':', 1))
SES_ADDR = (SES_ADDR[0], int(SES_ADDR[1]))

# HSV esikleri SAHADA CANLI KAMERADA olculdu (2026-08-19, deneme Pi IMX477):
#   mavi pad  H 120-128  S 90-131  V 91-124  -> S_min 70 (beyaz S~50 elenir, pad S>=90 tutulur)
#   kirmizi   H 0-12 ve 170-177  S 74-208  V 96-171
# hue'lar ayri (mavi<=135, kirmizi>=160) ki kirmizi kart mavi sanilmasin.
LZ_CONFIG = {
    # 4000 SADECE TEZGAH icin (yakin kart, oda gurultusu). IRTIFADA GECERSIZ:
    # 30 m'de 2 m'lik pad ~2800-4300 px^2 gorunur ve 4000 onu eler. Ucus
    # config'i (vision_params.yaml) 500 kullanir — dogru olan o.
    'min_zone_area_px': 4000.0, 'gaussian_blur_kernel': 5,
    'color_ranges': {
        'red_lower_1': [0, 60, 60], 'red_upper_1': [12, 255, 255],
        'red_lower_2': [160, 60, 60], 'red_upper_2': [180, 255, 255],
        'blue_lower': [100, 70, 40], 'blue_upper': [135, 255, 255],
    },
}
_RENK = {1: ('KIRMIZI', (0, 0, 255)), 2: ('MAVI', (255, 0, 0))}

_lock = threading.Lock()
_jpeg = [None]

_qr_detector = QRDetector(min_confidence=0.5)
_lz_detector = LandingZoneDetector(config=LZ_CONFIG)


def _make_qr():
    """Decoder sec: pyzbar > zbar (kurulu) > cv2. PARSE her zaman BIZIM kod."""
    if HAVE_PYZBAR:
        def oku(f):
            out = _qr_detector.detect(f)
            for r in out:
                r['bbox'] = None
            return out
        return oku, 'pyzbar (BIZIM detect)'
    try:
        import zbar
        sc = zbar.ImageScanner()
        sc.parse_config('enable')

        def oku(f):
            g = np.ascontiguousarray(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
            h, w = g.shape[:2]
            zi = zbar.Image(w, h, 'Y800', g.tobytes())
            sc.scan(zi)
            out = []
            for s in zi:
                t = (s.data.decode('utf-8', 'replace')
                     if isinstance(s.data, bytes) else s.data)
                r = _qr_detector._parse_qr_text(t)   # BIZIM parser
                r['raw_text'] = t
                xs = [p[0] for p in s.location]
                ys = [p[1] for p in s.location]
                r['bbox'] = (min(xs), min(ys), max(xs), max(ys))
                out.append(r)
            del zi
            return out
        return oku, 'zbar (kurulu) + BIZIM parser'
    except ImportError:
        cq = cv2.QRCodeDetector()

        def oku(f):
            d, pts, _ = cq.detectAndDecode(f)
            if not d:
                return []
            r = _qr_detector._parse_qr_text(d)
            r['raw_text'] = d
            if pts is not None and len(pts):
                p = pts.reshape(-1, 2)
                r['bbox'] = (p[:, 0].min(), p[:, 1].min(),
                             p[:, 0].max(), p[:, 1].max())
            else:
                r['bbox'] = None
            return [r]
        return oku, 'cv2 dahili + BIZIM parser'


_qr_oku, QR_BACKEND = _make_qr()


def _ic_renk(hsv, mask, cfg):
    """Daire ICININ hakim rengi (TON-agirlikli; soluk renge/isik degisimine dayanikli).

    Daire zaten sekli filtreledigi icin renk kontrolu doygunluga (S) fazla
    baglanmaz: ic pikseller arasinda kirmizi-ton mu mavi-ton mu baskin, ona
    bakariz (S/V yalniz beyaz/siyahi elemek icin dusuk esikli).
    Hue sinirlari cfg'den turetilir -> yarisma gunu yeniden kalibre edilirse
    iki yol (renk kutusu + daire) AYNI degerleri kullanir, ayrismaz.
    0 = renksiz/beyaz daire, 1 = kirmizi, 2 = mavi.
    """
    cr = cfg['color_ranges']
    red_h_ust = cr['red_upper_1'][0]      # kirmizi alt bant: 0..bu
    red_h_alt2 = cr['red_lower_2'][0]     # kirmizi ust bant: bu..180
    blue_h_alt = cr['blue_lower'][0]
    blue_h_ust = cr['blue_upper'][0]
    sel = (mask > 0) & (hsv[:, :, 1] > 40) & (hsv[:, :, 2] > 40)
    tot = cv2.countNonZero(mask)
    n = int(sel.sum())
    if tot == 0 or n < tot * 0.35:   # ic yeterince renkli degil -> hedef degil
        return 0, 0.0
    hh = hsv[:, :, 0][sel]
    red = int(((hh <= red_h_ust) | (hh >= red_h_alt2)).sum())
    blue = int(((hh >= blue_h_alt) & (hh <= blue_h_ust)).sum())
    ro, bo = red / n, blue / n
    if ro >= 0.5 and ro >= bo:
        return 1, ro
    if bo >= 0.5:
        return 2, bo
    return 0, max(ro, bo)


def daire_hedef_bul(frame, cfg):
    """DAIRE BUL (HoughCircles) -> ic rengine bak -> kirmizi/mavi ise INIS HEDEFI.

    "Daire gorursen icinin rengine bak" mantigi. Mevcut renk/QR tespitine
    DOKUNMAZ; ayri/ek yol. Ic renk BIZIM kalibre HSV esiklerini kullanir.
    """
    gray = cv2.medianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 5)
    h, w = gray.shape[:2]
    # IRTIFA GERCEKLIGI: 2 m'lik pad 25-30 m'den ~30-45 px yaricapinda gorunur
    # (fx~1108 @1280 -> 1024'e olcekli ~25-35 px). minRadius bunu KAPSAMALI;
    # onceki w*0.06 (~61 px) irtifadaki pad'i hic aramiyordu. Kucuk yaricapin
    # actigi sahte daireleri asagidaki %75 renk-baskinlik filtresi eler.
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(h * 0.15),
        param1=90, param2=35,
        minRadius=max(10, int(w * 0.015)), maxRadius=int(w * 0.6),
    )
    out, dbg = [], []
    if circles is None:
        return out, dbg
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for cx, cy, r in np.round(circles[0]).astype(int):
        mask = np.zeros(gray.shape, np.uint8)
        cv2.circle(mask, (int(cx), int(cy)), max(1, int(r * 0.6)), 255, -1)
        renk, oran = _ic_renk(hsv, mask, cfg)
        dbg.append((int(r), round(float(oran), 2), int(renk)))  # teshis
        if renk and oran >= 0.75:  # ici cok baskin tek renk -> gercek pad
            out.append({'x': int(cx), 'y': int(cy), 'r': int(r),
                        'renk': renk, 'oran': round(float(oran), 2)})
    # Gorev geregi HER IKI rengin konumu da kaydedilmeli (sartname 457-460):
    # renk BASINA en buyuk daire tutulur (en fazla 1 kirmizi + 1 mavi).
    secilen = {}
    for d in out:
        if d['renk'] not in secilen or d['r'] > secilen[d['renk']]['r']:
            secilen[d['renk']] = d
    return list(secilen.values()), dbg


def _ciz(frame, qr_list, zones, hedefler=None):
    """Tespitlerin etrafina bounding box + etiket cizer."""
    h, w = frame.shape[:2]
    for qr in qr_list:
        bb = qr.get('bbox')
        if bb:
            x1, y1, x2, y2 = (int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3]))
        else:
            x1, y1, x2, y2 = 4, 4, w - 4, h - 4
        ok = qr.get('valid')
        col = (0, 255, 0) if ok else (0, 165, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 3)
        lbl = (f"QR{qr.get('qr_id', '?')} GECERLI" if ok
               else f"QR gecersiz ({qr.get('error_message', '')[:20]})")
        cv2.putText(frame, lbl, (x1, max(22, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
    for z in zones:
        cx, cy = int(z['image_x'] * w), int(z['image_y'] * h)
        r = int(z['radius_px'])
        name, col = _RENK.get(z['color'], ('?', (255, 255, 255)))
        cv2.rectangle(frame, (cx - r, cy - r), (cx + r, cy + r), col, 3)
        cv2.putText(frame, f"{name} {z['confidence']:.2f}",
                    (cx - r, max(22, cy - r - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
    for hd in (hedefler or []):
        ad = 'KIRMIZI' if hd['renk'] == 1 else 'MAVI'
        cv2.circle(frame, (hd['x'], hd['y']), hd['r'], (0, 255, 255), 4)
        cv2.putText(frame, f"HEDEF {ad} {hd['oran']}",
                    (hd['x'] - hd['r'], max(22, hd['y'] - hd['r'] - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    return frame


def _log_yaz(satir):
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(satir + '\n')
    except OSError:
        pass


def _merkez_hsv(img):
    """Karenin merkezindeki renkli piksellerin ortanca HSV'si (teshis icin)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = img.shape[:2]
    c = hsv[int(h * 0.30):int(h * 0.70), int(w * 0.30):int(w * 0.70)]
    m = (c[:, :, 1] > 30) & (c[:, :, 2] > 30)
    px = int(m.sum())
    if px < 50:
        return f'renkli_px_az({px})'
    return (f"H{int(np.median(c[:, :, 0][m]))} "
            f"S{int(np.median(c[:, :, 1][m]))} "
            f"V{int(np.median(c[:, :, 2][m]))} px{px}")


def _dedektor_dongusu():
    """picam-web akisini okur, BIZIM kodla tespit + kutu; her sn tespit.log'a yazar."""
    import urllib.request
    kare = 0
    kare0 = 0
    son_ozet = time.monotonic()
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    son_bip = 0.0
    son_hedefler, son_daire_dbg = [], []  # daire HoughCircles seyrek calisir, sonuc korunur
    _log_yaz(f"{time.strftime('%H:%M:%S')} === goru_viewer basladi "
             f"(QR backend: {QR_BACKEND}, ses -> {SES_ADDR[0]}:{SES_ADDR[1]}) ===")
    while True:
        try:
            with urllib.request.urlopen(SRC, timeout=10) as r:
                buf = b''
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    buf += chunk
                    son = None
                    while True:
                        s = buf.find(b'\xff\xd8')
                        if s < 0:
                            if len(buf) > (1 << 22):
                                buf = b''
                            break
                        e = buf.find(b'\xff\xd9', s + 2)
                        if e < 0:
                            if s:
                                buf = buf[s:]
                            break
                        son = buf[s:e + 2]
                        buf = buf[e + 2:]
                    if son is None:
                        continue
                    img = cv2.imdecode(np.frombuffer(son, np.uint8),
                                       cv2.IMREAD_COLOR)
                    if img is None:
                        continue
                    if img.shape[1] > DET_W:
                        sc = DET_W / img.shape[1]
                        img = cv2.resize(img, None, fx=sc, fy=sc,
                                         interpolation=cv2.INTER_AREA)
                    kare += 1
                    zones = _lz_detector.detect(img)
                    qrs = _qr_oku(img) if kare % QR_HER == 0 else []
                    if kare % 4 == 0:   # HoughCircles pahali -> her 4 karede
                        son_hedefler, son_daire_dbg = daire_hedef_bul(img, LZ_CONFIG)
                    hedefler, daire_dbg = son_hedefler, son_daire_dbg

                    # Kutu cizilecekse laptop'a ses sinyali (throttle 1.2 sn).
                    gecerli_qr = any(q.get('valid') for q in qrs)
                    if zones or gecerli_qr:
                        _n = time.monotonic()
                        if _n - son_bip > 1.2:
                            son_bip = _n
                            m = ('QR' if gecerli_qr else
                                 'kirmizi' if any(z['color'] == 1 for z in zones)
                                 else 'mavi')
                            try:
                                usock.sendto(m.encode('utf-8'), SES_ADDR)
                            except OSError:
                                pass

                    now = time.monotonic()
                    if now - son_ozet >= 1.0:
                        fps = (kare - kare0) / (now - son_ozet)
                        son_ozet = now
                        kare0 = kare
                        kirmizi = sum(1 for z in zones if z['color'] == 1)
                        mavi = sum(1 for z in zones if z['color'] == 2)
                        qr_txt = '-'
                        for q in qrs:
                            if q.get('valid'):
                                qr_txt = f"QR{q.get('qr_id')}-GECERLI"
                            elif q.get('raw_text'):
                                qr_txt = 'QR-gecersiz'
                        hd_txt = ', '.join(
                            f"{'KIRMIZI' if hd['renk'] == 1 else 'MAVI'}"
                            f"(r{hd['r']} %{int(hd['oran'] * 100)})"
                            for hd in hedefler) or 'yok'
                        _log_yaz(f"{time.strftime('%H:%M:%S')} fps={fps:.1f} "
                                 f"QR={qr_txt} kirmizi={kirmizi} mavi={mavi} "
                                 f"HEDEF=[{hd_txt}] HAM_DAIRE={len(daire_dbg)}:"
                                 f"{daire_dbg[:4]} merkezHSV[{_merkez_hsv(img)}]")
                        for q in qrs:
                            if q.get('valid'):
                                _log_yaz(f"    QR{q['qr_id']} "
                                         f"formasyon={q['formation_type']} "
                                         f"spacing={q['spacing_m']} "
                                         f"alt={q['altitude_agl_m']}")

                    _ciz(img, qrs, zones, hedefler)
                    ok, enc = cv2.imencode('.jpg', img,
                                           [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        with _lock:
                            _jpeg[0] = enc.tobytes()
        except Exception as e:
            _log_yaz(f"{time.strftime('%H:%M:%S')} akis koptu: {e}")
            time.sleep(1.0)


_HTML = (b"<html><head><title>Yelpence goru</title></head>"
         b"<body style='margin:0;background:#111;text-align:center'>"
         b"<img src='/stream' style='max-width:100%;height:auto'></body></html>")


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=FRAME')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            while True:
                with _lock:
                    j = _jpeg[0]
                if j:
                    try:
                        self.wfile.write(b'--FRAME\r\nContent-Type: image/jpeg'
                                         b'\r\n\r\n' + j + b'\r\n')
                    except Exception:
                        break
                time.sleep(0.08)
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_HTML)


class _Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    threading.Thread(target=_dedektor_dongusu, daemon=True).start()
    print(f'[goru_viewer] QR backend: {QR_BACKEND}')
    print(f'[goru_viewer] tarayici: http://<pi-ip>:{PORT}   (Ctrl-C ile cik)')
    _Srv(('0.0.0.0', PORT), _H).serve_forever()


if __name__ == '__main__':
    main()
