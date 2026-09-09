# Copyright 2026 Yelpence TEKNOFEST 2026
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""qr_detector.py."""

import json
from typing import Any, Dict, List, Optional, Tuple

import cv2

import numpy as np

from pyzbar.pyzbar import decode

# BIRINCIL COZUCU: zxing-cpp. 28 Agustos 2026'da gercek sartname QR'i
# uzerinde olculdu (4056x3040, 74 modul, 204 bayt):
#
#   tam kare, QR VAR    pyzbar 695 ms  | zxing 268 ms  | wechat   122 ms
#   tam kare, QR YOK    pyzbar 628 ms  | zxing 275 ms  | wechat 11619 ms
#   kirpma (~1272 px)   pyzbar  61 ms  | zxing  34 ms  | wechat    11 ms
#   menzil (1,5 m QR)   pyzbar ~25 m   | zxing ~25 m   | wechat  ~40 m
#
# zxing SECILDI cunku: pyzbar ile AYNI menzil, YARI SURE ve QR yokken de
# ayni surede bitiyor. wechat daha menzilli ama bulamayinca 11,6 SANIYE
# harciyor — tam karede asla kullanilmaz (bkz. _wechat_ile_coz).
#
# ⚠️ zxing pip paketi (konteyner yeniden olusturulunca GIDER). Yoksa
# pyzbar'a dusuyoruz — o apt paketi, her zaman var. Islevsel fark yok,
# yalnizca iki kat yavas.
try:
    import zxingcpp
except ImportError:                                   # pragma: no cover
    zxingcpp = None

# QR komut kısaltmaları -> QRMissionData enum değerleri.
_FORMATION_CODES = {'ok': 1, 'v': 2, 'l': 3}     # OKBASI / V / CIZGI
_COLOR_CODES = {'r': 1, 'b': 2}                   # RED / BLUE


class QRDetector:
    """Goruntudeki QR kodlarini bulup ayristiran sinif."""

    def __init__(
        self, min_confidence: float = 0.5, team_slot: int = 1,
        iki_asamali: bool = True, olcek: int = 4,
        pay_orani: float = 0.25, aday_sayisi: int = 2,
        tam_tarama_periyodu: int = 5, wechat_yedek: bool = True,
        aday_alan_tavani: float = 0.0,
    ) -> None:
        """Aciklama: QRDetector sinifini ilklendirir."""
        self._min_confidence = min_confidence
        self._team_slot = int(team_slot)
        # KARAR-21: pas gecilen 'leav' sayisi — gorunurluk icin.
        self.atlanan_leav = 0
        # IKI ASAMALI TARAMA — 28 Agustos 2026, gercek sartname QR'i uzerinde
        # olculdu (1,5 m QR, 8,5 m mesafe, 4056x3040, 74 modul):
        #     tam kare taramasi            697 ms
        #     1/4 varyansla bul + kirp+oku 140 ms   -> 5,0 KAT HIZLI
        # Menzil kaybi YOK: okuma yine TAM COZUNURLUKTE, sadece karenin
        # tamami degil QR'in bulundugu bolge taraniyor.
        #
        # NEDEN cv2.QRCodeDetector DEGIL: o dedektor uc kose desenini ve
        # zamanlama desenini DOGRULAYARAK ariyor; 74 modullu yogun bir QR'da
        # 1/4 olcekte modul 2,25 piksele dusuyor ve desen ayirt edilemiyor.
        # Olculdu: 1/4'te de 1/8'de de BULAMADI.
        #
        # Varyans bulucu QR yapisina hic bakmiyor — yalnizca yerel degisintisi
        # anormal yuksek bolgeyi ariyor (yogun siyah-beyaz doku). Bu ozellik
        # kucultmeye cok daha dayanikli; 1/8'de bile 35 ms'de buldu.
        self._iki_asamali = bool(iki_asamali)
        self._olcek = max(1, int(olcek))
        self._pay_orani = float(pay_orani)
        self._aday_sayisi = max(1, int(aday_sayisi))
        # ⚠️ DEV ADAY KORUMASI — 5 Eylul 2026, ylp00'da gercek 4K karede
        # OLCULDU. Dis mekanda yuksek degisintili bolge HER YERDE (cimen,
        # doku); 9x9 kapama hepsini tek bloba birlestiriyor ve sinirlayici
        # kutu kareyi kapliyor. QR YOKKEN olculen bir tur:
        #     imdecode                 94,5 ms
        #     _adaylari_bul            76,8 ms  -> 2 aday
        #     aday 0: 4056x2692 px    zxing 523,2 ms   (karenin %89'u!)
        #     aday 1: 3128x1700 px    zxing 171,6 ms
        #     detect() TOPLAM         805,5 ms
        # Yani "kirpma" diye taranan sey neredeyse TUM KAREYDI ve iki
        # asamali yol TEK tam taramadan (406-470 ms) PAHALIYA calisiyordu.
        # 2,5 Hz'de %201 CPU talebi: dugum doymustu ve gercekte ~1,2 Hz'de
        # kosuyordu -- menzil olcumunde deneme sayisi da yariya iniyordu.
        # Bu yuzden `QR_HZ` 5 -> 2,5 hicbir sey degistirmemisti; zaten
        # ulasilamayan bir tavan indirilmis oluyordu.
        #
        # Kare alaninin bu oranindan BUYUK kutu QR adayi DEGILDIR,
        # bulucunun basarisizligidir: atilir ve zaten var olan periyodik
        # tam tarama guvenlik agi yakalar. 0.0 = koruma kapali.
        #
        # 🔴 VARSAYILAN 0.0 = KAPALI. Koruma 0,25 ile denendi ve
        # OLCUMLE CURUTULDU (5 Eylul 2026, ayni gun, ayni ucak). Ayni
        # canli kareye sentetik QR gomulup her iki kip olculdu:
        #        QR boyu     koruma KAPALI      koruma 0,25
        #     1200x1200 px   132 ms  BULDU     138 ms  BULDU
        #       600x600 px    59 ms  BULDU      58 ms  BULDU
        #       300x300 px   178 ms  BULDU     221 ms  KACIRDI
        #       150x150 px   667 ms  BULDU     202 ms  KACIRDI
        #     QR YOK         532 ms              52 ms
        # Yani dev kutu SALT GURULTU DEGIL: kucuk QR'i iceren kutu da dev
        # oluyor ve zxing onu tararken QR'i buluyor. Kutuyu atmak, QR'i
        # atmak demek -- ve kucuk QR tam olarak GOREV HALI (10 m'den 1,5 m
        # QR karenin ~%1,7'si). CPU kazanci gercekti (%97,7 -> %39,8) ama
        # bedeli menzilin tamami.
        # Dogru cozum kutuyu ATMAK degil, bulucuyu TIKIZ kutu uretmeye
        # zorlamak: 9x9 kapama tum dokuyu tek bloba birlestiriyor. Kernel
        # kucultmek ya da %99 esigin 0,55 carpanini yukseltmek denenmeli
        # -- ama once bu tabloyla olculmeli.
        # Bu bayrak DENEY icin duruyor; acmadan once yukaridaki tabloyu
        # yeniden uret.
        #
        # NOT: ayni tuzak asagida WECHAT icin yazilmisti ("koruma yanlis
        # yerde duruyor") ve dogruymus -- zxing de ayni felakete kirpma
        # uzerinden giriyordu. Koruma artik dogru yerde: kutunun kendisi.
        self._aday_alan_tavani = max(0.0, float(aday_alan_tavani))
        # ⚠️ TAM TARAMAYA HER BASARISIZLIKTA DUSMUYORUZ — 28 Agustos 2026'da
        # olculdu ve ilk uygulama TERS TEPTI:
        #     QR VAR : tam kare 833 ms -> iki asama  177 ms   4,7x HIZLI
        #     QR YOK : tam kare 928 ms -> iki asama 1331 ms   1,4x YAVAS
        # Cunku QR yokken bulucu + basarisiz kirpmalar + tam tarama UST USTE
        # odeniyordu. Ve gorevde karelerin COGUNDA QR YOKTUR — yani en sik
        # durum kotulesiyordu.
        # Cozum: tam tarama bir GUVENLIK AGI, her karede degil her
        # `tam_tarama_periyodu` basarisizlikta bir kez. 0 = hic yapma.
        self._tam_periyot = max(0, int(tam_tarama_periyodu))
        self._basarisiz = 0
        # WECHAT YEDEGI — 28 Agustos 2026, gercek QR uzerinde olculdu.
        # Ayni kirpmada, irtifa benzetimiyle:
        #     irtifa   pyzbar        wechat
        #      8,5 m   ✓  94 ms      ✓  18 ms
        #       25 m   ✓ 102 ms      ✓  21 ms
        #       35 m   ✗  86 ms      ✓ 188 ms   <- pyzbar BIRAKIYOR
        #       45 m   ✗  57 ms      ✓ 351 ms
        # Yani wechat hem hizli hem MENZILLI. Ama bir tuzagi var:
        #     QR YOKKEN, TAM KAREDE  ->  11 857 ms  (pyzbar 624 ms)
        # Bulamayinca cok pahali bir arama yapiyor. Bu yuzden:
        #   * TAM KAREYE ASLA wechat calistirilmaz,
        #   * yalniz KIRPMADA ve yalniz pyzbar basarisiz olunca,
        #   * o da periyodik yedek turunda — her karede degil.
        # Boylece menzil kazanci alinir, 12 saniyelik risk alinmaz.
        self._wechat_yedek = bool(wechat_yedek)
        self._wechat = None
        self._wechat_denendi = False

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """BGR goruntu uzerindeki QR kodlari bulur ve ayristirir."""
        if image is None or image.size == 0:
            return []

        if self._iki_asamali:
            hizli = self._iki_asamali_tara(image)
            if hizli:
                # Sayac BILEREK sifirlanmiyor: her basaridan sonra sifirlamak,
                # bir sonraki basarisizligi hep tam taramaya sokuyordu. Olculdu
                # (10 karenin 3'unde QR): sifirlarken 508 ms/kare, sifirlamadan
                # 237. Sayac tek bir ritim tutuyor; taze bir dedektorun ILK
                # basarisizligi yine tam tarama yapar, sozlesme korunur.
                return hizli
            self._basarisiz += 1
            # Guvenlik agi: bulucunun kacirdigi bir QR sonsuza kadar
            # gorunmez kalmasin diye ARADA BIR tam kare taraniyor.
            #
            # ⚠️ ILK basarisizlikta MUTLAKA tam tarama yapiliyor
            # ((n-1) % periyot), sonrakiler atlaniyor. Sebebi: `detect()`
            # tek basina cagrildiginda (birim testler, tek kare inceleme)
            # QR'i bulmak ZORUNDA. Once `n % periyot` yazmistim ve ilk
            # cagri bos donuyordu — iki birim test bunu yakaladi.
            if (self._tam_periyot == 0
                    or (self._basarisiz - 1) % self._tam_periyot != 0):
                return []
            # Periyodik yedek turu: once wechat'i KIRPMADA dene (pyzbar'in
            # yetismedigi uzak QR'lar icin), sonra tam kare taramasina dus.
            if self._wechat_yedek:
                w = self._wechat_ile_coz(image)
                if w:
                    return w

        return self._cerceveleri_coz(
            image, 0, 0, image.shape[1], image.shape[0])

    def _wechat_al(self):
        """Cozucuyu bir kez kurar; opencv_contrib yoksa None doner."""
        if self._wechat_denendi:
            return self._wechat
        self._wechat_denendi = True
        try:
            self._wechat = cv2.wechat_qrcode_WeChatQRCode()
        except (AttributeError, cv2.error):
            self._wechat = None      # opencv_contrib yoksa sessizce gec
        return self._wechat

    def _wechat_ile_coz(
        self, image: np.ndarray
    ) -> Optional[List[Dict[str, Any]]]:
        """Adaylari wechat ile dener — YALNIZ kirpmada, asla tam karede."""
        w = self._wechat_al()
        if w is None:
            return None
        for x0, y0, x1, y1 in self._adaylari_bul(image):
            parca = image[y0:y1, x0:x1]
            if parca.size == 0:
                continue
            try:
                metinler, kutular = w.detectAndDecode(parca)
            except cv2.error:
                continue
            for metin, kutu in zip(metinler, kutular):
                if not metin:
                    continue
                nk = np.asarray(kutu).reshape(-1, 2)
                gx, gy = float(nk[:, 0].mean()), float(nk[:, 1].mean())
                gen = float(nk[:, 0].max() - nk[:, 0].min())
                yuk = float(nk[:, 1].max() - nk[:, 1].min())
                d = {
                    'raw_text': metin,
                    'image_x': (x0 + gx) / image.shape[1],
                    'image_y': (y0 + gy) / image.shape[0],
                    'image_width': gen / image.shape[1],
                    'image_height': yuk / image.shape[0],
                }
                d.update(self._parse_qr_text(metin))
                return [d]
        return None

    def _cerceveleri_coz(
        self, parca: np.ndarray, ofs_x: int, ofs_y: int,
        tam_g: int, tam_y: int,
    ) -> List[Dict[str, Any]]:
        """Verilen parcayi tarar; konumlari TAM KAREYE gore normalize eder.

        ⚠️ ofs_x/ofs_y ve tam_g/tam_y sart: kirpilmis bir parcada bulunan
        QR'in konumu parcaya gore cikar. Bunlar eklenmezse dugum QR'i
        karenin yanlis yerinde sanir ve hedef koordinati kayar.
        """
        sonuc: List[Dict[str, Any]] = []
        for raw_text, sol, ust, gen, yuk in self._ham_coz(parca):
            qr_data = {
                'raw_text': raw_text,
                'image_x': float(ofs_x + sol + gen / 2) / tam_g,
                'image_y': float(ofs_y + ust + yuk / 2) / tam_y,
                'image_width': float(gen) / tam_g,
                'image_height': float(yuk) / tam_y,
            }
            qr_data.update(self._parse_qr_text(raw_text))
            sonuc.append(qr_data)
        return sonuc

    @staticmethod
    def _ham_coz(parca: np.ndarray) -> List[Tuple[str, int, int, int, int]]:
        """(metin, sol, ust, genislik, yukseklik) listesi.

        Iki cozucuyu tek bicime indirir. zxing varsa o, yoksa pyzbar.
        """
        if zxingcpp is not None:
            try:
                cikti = []
                for b in zxingcpp.read_barcodes(parca):
                    if not b.text:
                        continue
                    p = b.position
                    xs = [p.top_left.x, p.top_right.x,
                          p.bottom_left.x, p.bottom_right.x]
                    ys = [p.top_left.y, p.top_right.y,
                          p.bottom_left.y, p.bottom_right.y]
                    cikti.append((b.text, min(xs), min(ys),
                                  max(xs) - min(xs), max(ys) - min(ys)))
                return cikti
            except Exception:                          # pragma: no cover
                pass          # zxing takilirsa pyzbar'a dus, tespiti kaybetme

        cikti = []
        for obj in decode(parca):
            try:
                metin = obj.data.decode('utf-8')
            except UnicodeDecodeError:
                continue
            r = obj.rect
            cikti.append((metin, r.left, r.top, r.width, r.height))
        return cikti

    def _iki_asamali_tara(
        self, image: np.ndarray
    ) -> Optional[List[Dict[str, Any]]]:
        """Once kucukte QR adayini bul, sonra TAM COZUNURLUKTE oku."""
        for x0, y0, x1, y1 in self._adaylari_bul(image):
            parca = image[y0:y1, x0:x1]
            if parca.size == 0:
                continue
            s = self._cerceveleri_coz(
                parca, x0, y0, image.shape[1], image.shape[0])
            if s:
                return s
        return None

    def _adaylari_bul(
        self, image: np.ndarray
    ) -> List[Tuple[int, int, int, int]]:
        """Yerel degisintisi yuksek bolgeler — QR'in dokusal imzasi."""
        tam_y, tam_g = image.shape[:2]
        b = self._olcek
        if tam_g // b < 32 or tam_y // b < 32:
            return []
        try:
            kucuk = cv2.resize(image, (tam_g // b, tam_y // b),
                               interpolation=cv2.INTER_AREA)
            # Kare zaten tek kanalliysa cevirme (renk yolu kapaliyken
            # `_compressed_callback` IMREAD_GRAYSCALE ile coziyor). Eskiden
            # kosulsuz cvtColor vardi; gri kare gelince cv2.error atiyor,
            # asagidaki `except` yutuyor ve bulucu SESSIZCE bos donuyordu --
            # iki asamali tarama devre disi kalir, her sey tam taramaya
            # duserdi. Yani hata vermeden yavaslardik.
            gri = (kucuk if kucuk.ndim == 2
                   else cv2.cvtColor(kucuk, cv2.COLOR_BGR2GRAY))
            gri = gri.astype(np.float32)
            ort = cv2.blur(gri, (12, 12))
            # Degisinti kayan pencerede: E[x^2] - E[x]^2. Yuvarlama yuzunden
            # kucuk negatif cikabilir, karekokten once kirpiyoruz.
            std = np.sqrt(np.maximum(cv2.blur(gri * gri, (12, 12))
                                     - ort * ort, 0.0))
            esik = float(np.percentile(std, 99.0)) * 0.55
            maske = (std > esik).astype(np.uint8) * 255
            maske = cv2.morphologyEx(maske, cv2.MORPH_CLOSE,
                                     np.ones((9, 9), np.uint8))
            konturlar, _ = cv2.findContours(
                maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except cv2.error:
            return []

        kutular = []
        tavan = self._aday_alan_tavani * float(tam_g) * float(tam_y)
        for c in sorted(konturlar, key=cv2.contourArea,
                        reverse=True)[:self._aday_sayisi]:
            x, y, w, h = cv2.boundingRect(c)
            if w < 8 or h < 8:
                continue
            pay = int(max(w, h) * self._pay_orani)
            kx0, ky0 = max(0, (x - pay) * b), max(0, (y - pay) * b)
            kx1 = min(tam_g, (x + w + pay) * b)
            ky1 = min(tam_y, (y + h + pay) * b)
            # Kareyi kaplayan aday, aday degil -- bulucunun cokusu.
            # Gerekce ve olculen sayilar yapicida (`_aday_alan_tavani`).
            if tavan > 0.0 and float(kx1 - kx0) * (ky1 - ky0) > tavan:
                continue
            kutular.append((kx0, ky0, kx1, ky1))
        return kutular

    def _blank_result(self) -> Dict[str, Any]:
        """Tüm alanları nötr olan boş bir sonuç sözlüğü döndürür."""
        return {
            'team_id': '',
            'qr_id': 0,
            'qr_seq': 0,
            'next_qr': 0,
            'formation_type': 0,
            'spacing_m': 0.0,
            'altitude_agl_m': 0.0,
            'pitch_deg': 0.0,
            'roll_deg': 0.0,
            'yaw_deg': 0.0,
            'wait_s': 0.0,
            'target_agent_id': 0,
            'detach_color': 0,
            'detach_wait_s': 0.0,
            'formation_active': False,
            'target_active': False,
            'maneuver_active': False,
            'altitude_active': False,
            'detach_active': False,
            'complete_mission': False,
            'valid': False,
            'error_message': '',
        }

    def _parse_qr_text(self, text: str) -> Dict[str, Any]:
        """Şartname JSON'ını ayrıştırıp bu takımın görev paketini düzleştirir."""
        parsed = self._blank_result()

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed['error_message'] = 'QR JSON cozulemedi'
            return parsed

        try:
            parsed['qr_id'] = int(data['qr'])
            parsed['wait_s'] = float(data['w'])
            packages = data['mis']
            team_table = data['team']
        except (KeyError, TypeError, ValueError):
            parsed['error_message'] = 'QR sema alanlari eksik'
            return parsed

        slot = str(self._team_slot)
        if slot not in team_table:
            parsed['error_message'] = f'Takim slotu {slot} tabloda yok'
            return parsed

        try:
            package_no, next_qr = team_table[slot]
            package_no = int(package_no)
            parsed['next_qr'] = int(next_qr)
        except (ValueError, TypeError):
            parsed['error_message'] = 'Takim tablosu girdisi bozuk'
            return parsed

        parsed['target_active'] = True
        # sonraki_qr == 0 -> dinamik senaryo bitti, baslangica don.
        parsed['complete_mission'] = parsed['next_qr'] == 0

        # Paket numarasi 1-tabanli; mis listesi 0-tabanli.
        idx = package_no - 1
        if not isinstance(packages, list) or not (0 <= idx < len(packages)):
            parsed['error_message'] = f'Paket {package_no} listede yok'
            return parsed

        for command in packages[idx]:
            try:
                self._apply_command(parsed, command)
            except (ValueError, TypeError, IndexError) as exc:
                parsed['error_message'] = str(exc)
                return parsed

        parsed['valid'] = True
        return parsed

    def _apply_command(
        self, parsed: Dict[str, Any], command: List[Any]
    ) -> None:
        """Tek bir görev komutunu ([op, ...]) sonuç sözlüğüne uygular."""
        op = command[0]

        if op == 'frm':
            parsed['formation_active'] = True
            parsed['formation_type'] = _FORMATION_CODES.get(command[1], 0)
            parsed['spacing_m'] = float(command[2])
        elif op == 'mnv':
            parsed['maneuver_active'] = True
            parsed['pitch_deg'] = float(command[1])
            parsed['roll_deg'] = float(command[2])
        elif op == 'alt':
            parsed['altitude_active'] = True
            parsed['altitude_agl_m'] = float(command[1])
        elif op == 'leav':
            # 🔴 KARAR-21 (8 Eylul 2026, operator): "leav olmayacak.
            # Geldiginde PAS GECILECEK." Ayrilma senaryosu ucurulmayacak.
            #
            # NIYE BURADA KESILIYOR: kaynak TEK NOKTA. Asagidaki hicbir katman
            # (mission_fsm adim sirasi, swarm_fsm, agent_fsm) ayrilma gormez;
            # "bir yerde kapatmayi unuttuk" ihtimali kalmaz.
            #
            # NIYE SESSIZ DEGIL: istenen ajan ve renk ALANLARA YAZILIYOR,
            # yalniz detach_active False kaliyor. YKI'de "QR ajan 5 / KIRMIZI
            # istedi ama ayrilma=False" diye GORUNUR. Sessizce yutulan komut
            # bu depoda defalarca pahaliya patladi.
            #
            # Sahadaki 30 sayfada bize gelen leav hedefleri: ajan 4 ve 5
            # (bizde YOK, filo 1-2-3), ajan 1 (kamerali sabit liderimiz), 2, 3.
            parsed['target_agent_id'] = int(command[1])
            parsed['detach_color'] = _COLOR_CODES.get(command[2], 0)
            self.atlanan_leav += 1
        else:
            raise ValueError(f'Bilinmeyen komut: {op}')
