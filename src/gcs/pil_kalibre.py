#!/usr/bin/env python3
# Copyright 2026 Yelpence
# =============================================================================
# INA226 PIL KALIBRASYON ARAYUZU — tarayicidan, uc ucak birden
#
# NEDEN VAR (31 Agustos 2026)
# ---------------------------
# INA226 modulleri multimetreye gore SAPIYOR ve sapma her uçakta FARKLI:
#     ylp00  INA226 15.89 V · DMM 15.67 V  -> %1.4 yuksek
#     ylp01  INA226 16.71 V · DMM 15.88 V  -> %5.2 yuksek
# Farkli oranlar yazilim olceginin dogru oldugunu kanitliyor (ortak hata
# olsaydi ucu de ayni oranda sapardi); sapma karta ozgu.
#
# Kalibrasyon ELLE yapilinca iki sey ters gidiyordu:
#   1) Multimetre okumasi ile INA226 okumasi FARKLI ANLARDA aliniyor. Pil
#      dakikada ~0.02 V dusuyor; 10 dakikalik gecikme 0.2 V hata demek —
#      yani duzeltmenin kendisi kadar buyuk.
#   2) Zaten bir carpan uygulanmissa, yeni carpani "DMM / ekrandaki deger"
#      diye hesaplamak duzeltmeleri UST USTE BINDIRIR ve sessizce bozar.
#
# Bu arayuz ikisini de kapatiyor: deger O AN okunuyor ve carpan HAM degere
# gore hesaplaniyor.
#
# 🔴 UST USTE BINME MATEMATIGI
#     ekran = ham x carpan_eski
#     ham   = ekran / carpan_eski
#     yeni  = DMM / ham = DMM x carpan_eski / ekran
# Yani mevcut carpan hesaba KATILIYOR. Bu satir olmasa ikinci kalibrasyon
# ilkini ezmek yerine onunla carpilir ve deger daha da kayar.
#
# SALT OKUR + TEK YAZI: yalnizca `/ws/ina226_carpan` dosyasini yazar ve
# pil dugumunu yeniden baslatir. Ucus kontrolune dokunmaz.
#
# NASIL KOSAR (YKI laptopunda, depo kokunden)
#     python3 src/gcs/pil_kalibre.py
#     -> tarayici: http://localhost:8091
# =============================================================================

import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

PORT = 8091
BULUCU = './deploy/yki/drone_bul.sh'

# ad -> (konteyner, agent_id)
DRONELAR = {
    'ylp00': ('drone1', 1),
    'ylp01': ('drone2', 2),
    'ylp02': ('drone3', 3),
}

# 🔴 MAKUL CARPAN ARALIGI. Disina cikan bir deger, kalibrasyon degil
# YANLIS OLCUM demektir (yanlis uçak, yanlis pil, virgul hatasi). Sessizce
# uygulamak yerine reddediyoruz — bu projede sessiz olcek kaymasi pahali.
CARPAN_ALT, CARPAN_UST = 0.80, 1.20
# Multimetre degeri icin makul aralik: 4S bos ~13.2 V, 6S dolu ~25.2 V.
DMM_ALT, DMM_UST = 5.0, 30.0

_kilit = threading.Lock()
_onbellek: dict = {}


def _kabuk(ad: str, komut: str, zaman_asimi: int = 25) -> str:
    """drone_bul.sh uzerinden uçakta komut kosar, ciktiyi dondurur."""
    try:
        s = subprocess.run(
            [BULUCU, ad, komut],
            capture_output=True, text=True, timeout=zaman_asimi,
        )
        return s.stdout
    except subprocess.TimeoutExpired:
        return ''


def _oku(ad: str) -> dict:
    """Bir uçagin O ANKI INA226 degerini ve mevcut carpanini okur.

    Ikisi TEK SSH oturumunda aliniyor: ayri ayri alinsa arada pil duser ve
    carpan hesabi kayar.
    """
    kap = DRONELAR[ad][0]
    aid = DRONELAR[ad][1]
    komut = (
        f"printf 'CARPAN='; cat ~/yelpence_ws/ina226_carpan 2>/dev/null "
        f"|| echo 1.0; "
        f"docker exec {kap} bash -lc '"
        f"source /opt/ros/jazzy/setup.bash; "
        f"source /ws/install/setup.bash 2>/dev/null; "
        f"printf \"VOLT=\"; timeout 6 ros2 topic echo --once "
        f"/drone_{aid}/pil/ina226 2>/dev/null | grep \"^voltage\" "
        f"| awk \"{{print \\$2}}\"'"
    )
    cikti = _kabuk(ad, komut)
    m_v = re.search(r'VOLT=\s*([0-9.]+)', cikti)
    m_c = re.search(r'CARPAN=\s*([0-9.]+)', cikti)
    return {
        'ad': ad,
        'ekran_v': float(m_v.group(1)) if m_v else None,
        'carpan': float(m_c.group(1)) if m_c else 1.0,
        't': time.time(),
    }


def _tek_dongu(ad: str) -> None:
    """Bir ucagi surekli okur. HER UCAK ICIN AYRI IS PARCACIGI.

    🔴 SIRAYLA OKUMAK YETERSIZ: bir SSH turu ~14 sn suruyor, uc ucak
    sirayla ~45 sn eder. Kalibrasyonda operator multimetreyi okurken
    ekrandaki sayinin O ANA ait olmasi gerekiyor; 45 sn'lik gecikme
    pilin ~0.9 V dusmesi demek (olculen dusus ~0.02 V/dk) — yani
    duzeltmenin kendisinden buyuk bir hata. Paralel okuyunca her ucagin
    kendi tazeligi ~14 sn'de kaliyor.

    Not: `_uygula` zaten KENDI taze okumasini yapiyor; bu dongu yalnizca
    ekrani besliyor. Yani kalibrasyonun dogrulugu bu tazelige BAGLI DEGIL,
    ama operatorun dogru ani secebilmesi icin ekran guncel olmali.
    """
    while True:
        d = _oku(ad)
        with _kilit:
            _onbellek[ad] = d
        time.sleep(0.5)


def _yenile_dongusu() -> None:
    """Her ucak icin ayri okuma is parcacigi baslatir."""
    for ad in DRONELAR:
        threading.Thread(target=_tek_dongu, args=(ad,), daemon=True).start()


def _uygula(ad: str, dmm_v: float) -> dict:
    """Multimetre degerine gore carpani hesaplar, yazar, dugumu yeniler."""
    if not (DMM_ALT <= dmm_v <= DMM_UST):
        return {'ok': False, 'mesaj':
                f'Multimetre degeri {dmm_v} V makul araligin ({DMM_ALT}-'
                f'{DMM_UST} V) disinda — yazim hatasi olabilir.'}

    # O ANI oku: onbellek 1 sn'ye kadar eski olabilir, kalibrasyonda taze
    # deger sart.
    d = _oku(ad)
    ekran = d['ekran_v']
    eski = d['carpan']
    if ekran is None:
        return {'ok': False, 'mesaj':
                f'{ad}: INA226 okunamadi. Pil dugumu kosuyor mu?'}

    # 🔴 UST USTE BINMEYI ONLEYEN SATIR — gerekce dosya basliginda.
    yeni = dmm_v * eski / ekran

    if not (CARPAN_ALT <= yeni <= CARPAN_UST):
        return {'ok': False, 'mesaj':
                f'Hesaplanan carpan {yeni:.5f}, makul araligin '
                f'({CARPAN_ALT}-{CARPAN_UST}) DISINDA. '
                f'(INA226 {ekran:.3f} V, DMM {dmm_v:.3f} V, eski carpan '
                f'{eski:.5f}.) Yanlis uçak ya da yanlis okuma olabilir — '
                f'UYGULANMADI.'}

    kap = DRONELAR[ad][0]
    _kabuk(ad, f"echo '{yeni:.5f}' > ~/yelpence_ws/ina226_carpan", 20)
    _kabuk(ad, f'docker restart {kap}', 60)
    return {
        'ok': True,
        'mesaj': (f'{ad}: carpan {eski:.5f} -> {yeni:.5f} yazildi ve '
                  f'konteyner yeniden basladi. '
                  f'(INA226 {ekran:.3f} V, DMM {dmm_v:.3f} V, '
                  f'sapma %{(ekran / dmm_v - 1) * 100:+.2f}) '
                  f'Dugum ~40 sn icinde geri gelir.'),
        'yeni': yeni, 'eski': eski, 'ekran': ekran,
    }


SAYFA = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yelpence — Pil Kalibrasyonu</title>
<style>
:root{--bg:#0d1117;--k:#161b22;--cz:#30363d;--y:#c9d1d9;--sn:#8b949e;
      --ok:#3fb950;--uy:#d29922;--hata:#f85149;--mavi:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--y);
     font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
header{padding:14px 18px;background:var(--k);border-bottom:1px solid var(--cz)}
h1{font-size:16px;margin:0 0 4px}
.aciklama{font-size:12px;color:var(--sn)}
main{padding:18px;display:grid;gap:16px;
     grid-template-columns:repeat(auto-fit,minmax(330px,1fr));max-width:1200px}
section{background:var(--k);border:1px solid var(--cz);border-radius:8px;
        padding:16px}
h2{font-size:15px;margin:0 0 12px;color:var(--mavi)}
.satir{display:flex;justify-content:space-between;margin-bottom:6px}
.ad{color:var(--sn);font-size:12px}
.buyuk{font-size:26px;font-weight:600;letter-spacing:-.5px}
.giris{display:flex;gap:8px;margin-top:14px}
input{flex:1;background:#0d1117;border:1px solid var(--cz);color:var(--y);
      padding:9px 11px;border-radius:6px;font:inherit;font-size:16px}
button{background:#1f6feb;color:#fff;border:0;padding:9px 16px;
       border-radius:6px;font:inherit;font-weight:600;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
.sonuc{margin-top:10px;font-size:12px;line-height:1.5;min-height:34px}
.ok{color:var(--ok)}.uy{color:var(--uy)}.hata{color:var(--hata)}
.sn{color:var(--sn)}
.rozet{font-size:11px;padding:2px 7px;border-radius:9px;margin-left:8px}
.canli{background:#0d4429;color:var(--ok)}
.olu{background:#4d1f1c;color:var(--hata)}
</style></head><body>
<header>
  <h1>INA226 Pil Kalibrasyonu</h1>
  <div class="aciklama">
    Multimetreyle O ANDA oku, kutuya yaz, Uygula'ya bas. Çarpan
    <b>ham değere göre</b> hesaplanır — üst üste binmez, tekrar tekrar
    kalibre edebilirsin.
  </div>
</header>
<main id="kartlar"></main>
<script>
const DRONELAR = ["ylp00","ylp01","ylp02"];
let mesgul = {};

function kartCiz(d){
  const canli = d.ekran_v !== null;
  const sapma = d.carpan !== 1 ? ` · çarpan ${d.carpan.toFixed(5)}` : " · çarpan yok";
  return `
    <h2>${d.ad}<span class="rozet ${canli?'canli':'olu'}">${canli?'canlı':'okunamıyor'}</span></h2>
    <div class="satir"><span class="ad">INA226 (ekranda)</span></div>
    <div class="buyuk">${canli ? d.ekran_v.toFixed(3)+" V" : "—"}</div>
    <div class="satir"><span class="ad sn">${d.carpan!==1?"kalibre edilmiş":"ham"}${sapma}</span></div>
    <div class="giris">
      <input id="dmm-${d.ad}" type="number" step="0.01" placeholder="multimetre V"
             ${canli?"":"disabled"}>
      <button id="btn-${d.ad}" onclick="uygula('${d.ad}')" ${canli?"":"disabled"}>Uygula</button>
    </div>
    <div class="sonuc" id="sonuc-${d.ad}"></div>`;
}

async function tik(){
  let d;
  try { d = await (await fetch('/oku',{cache:'no-store'})).json(); }
  catch(e){ return; }
  const kok = document.getElementById('kartlar');
  if(kok.children.length !== DRONELAR.length){
    kok.innerHTML = DRONELAR.map(a=>`<section id="s-${a}"></section>`).join('');
  }
  for(const ad of DRONELAR){
    if(mesgul[ad]) continue;               // yazarken kart yenilenmesin
    const kart = document.getElementById('s-'+ad);
    const eskiDeger = (document.getElementById('dmm-'+ad)||{}).value;
    const eskiSonuc = (document.getElementById('sonuc-'+ad)||{}).innerHTML;
    kart.innerHTML = kartCiz(d[ad] || {ad, ekran_v:null, carpan:1});
    if(eskiDeger) document.getElementById('dmm-'+ad).value = eskiDeger;
    if(eskiSonuc) document.getElementById('sonuc-'+ad).innerHTML = eskiSonuc;
  }
}

async function uygula(ad){
  const kutu = document.getElementById('dmm-'+ad);
  const v = parseFloat(kutu.value);
  const sonuc = document.getElementById('sonuc-'+ad);
  if(!isFinite(v)){ sonuc.innerHTML = '<span class="hata">Bir sayı gir.</span>'; return; }
  mesgul[ad] = true;
  document.getElementById('btn-'+ad).disabled = true;
  sonuc.innerHTML = '<span class="uy">uygulanıyor… (konteyner yeniden başlıyor, ~40 sn)</span>';
  try{
    const r = await (await fetch('/uygula', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ad, dmm: v})})).json();
    sonuc.innerHTML = `<span class="${r.ok?'ok':'hata'}">${r.mesaj}</span>`;
    if(r.ok) kutu.value = '';
  }catch(e){
    sonuc.innerHTML = '<span class="hata">sunucuya ulaşılamadı: '+e+'</span>';
  }
  mesgul[ad] = false;
  const b = document.getElementById('btn-'+ad);
  if(b) b.disabled = false;
}

tik(); setInterval(tik, 1500);
</script></body></html>
"""


class Sunucu(BaseHTTPRequestHandler):
    """Salt okur + tek yazi (carpan dosyasi)."""

    def log_message(self, bicim, *args):
        pass

    def _yolla(self, govde: bytes, tip: str) -> None:
        self.send_response(200)
        self.send_header('Content-Type', tip)
        self.send_header('Content-Length', str(len(govde)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        if self.path.startswith('/oku'):
            with _kilit:
                govde = json.dumps(_onbellek).encode()
            self._yolla(govde, 'application/json')
            return
        self._yolla(SAYFA.encode(), 'text/html; charset=utf-8')

    def do_POST(self):
        if not self.path.startswith('/uygula'):
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get('Content-Length', 0))
        try:
            istek = json.loads(self.rfile.read(n) or b'{}')
            ad = str(istek.get('ad'))
            dmm = float(istek.get('dmm'))
            if ad not in DRONELAR:
                raise ValueError(f'bilinmeyen drone: {ad}')
            sonuc = _uygula(ad, dmm)
        except Exception as e:      # noqa: BLE001
            sonuc = {'ok': False, 'mesaj': f'istek hatasi: {e}'}
        self._yolla(json.dumps(sonuc, ensure_ascii=False).encode(),
                    'application/json')


def main() -> None:
    threading.Thread(target=_yenile_dongusu, daemon=True).start()
    sunucu = ThreadingHTTPServer(('127.0.0.1', PORT), Sunucu)
    print(f'pil_kalibre hazir: http://localhost:{PORT}', flush=True)
    print('  Multimetreyle O ANDA oku, kutuya yaz, Uygula.', flush=True)
    sunucu.serve_forever()


if __name__ == '__main__':
    main()
