#!/usr/bin/env python3
# =============================================================================
# GOREV 2 KUMANDA OLCUM ARAYUZU — tarayicidan
#
# NEDEN VAR (31 Agustos 2026): ayni olcumler once terminalden yapildi ve
# UST USTE BOSA GITTI. Sebep teknik degil, KOORDINASYONDU:
#   * `grep` boru ucunda BLOK TAMPONLUYOR -> "simdi basla" talimati
#     operatore kayit BITTIKTEN sonra ulasiyordu
#   * ilerleme satirlari talimati ekrandan kaydiriyordu
#     ("rehberi netde goremiyorum")
#   * sabit sureli kayit, iki kisinin saniye hassasiyetinde anlasmasini
#     gerektiriyor
# Tarayicida bunlarin hicbiri yok: operator kanallari CANLI gorur, olcumu
# KENDI baslatir, sonucu aninda okur.
#
# NE OLCER (gorev2.md maddeleri):
#   madde 17 — eksen isaretleri (rc_eksen.py TERS_* sabitleri)
#   madde 26 — SwC gecis suresi -> debounce esigi
#   madde 30 — kumanda kaybinda deadman dusuyor mu
#   + kanal haritasi (hangi salter hangi kanali suruyor)
#
# SALT OKUR. Hicbir sey yayinlamaz, hicbir parametre degistirmez.
#
# NASIL KOSAR (konteyner host aginda, /ws = ~/yelpence_ws):
#   ./deploy/yki/drone_bul.sh ylp00 'cat > ~/yelpence_ws/kumanda_web.py' \
#       < src/gcs/kumanda_web.py
#   ./deploy/yki/drone_bul.sh ylp00 'docker exec -d drone1 bash -lc \
#       "source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; \
#        python3 -u /ws/kumanda_web.py > /tmp/kumanda_web.log 2>&1"'
#   -> tarayici: http://<pi-ip>:8090
# =============================================================================

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

from mavros_msgs.msg import RCIn
import rclpy
from std_msgs.msg import UInt8
from swarm_interfaces.msg import SwarmControlCommand
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

KONU = '/drone_1/rc/suru'
KOMUT_KONU = '/swarm/internal/control/command'
# Ucuncu kalkis kapisi (G2-K10): gorev YKI'den baslatilmis olmali.
GOREV_KONU = '/swarm/internal/mission/state'
PORT = 8090

# rc_ibus_kopru BEST_EFFORT yayinliyor; RELIABLE abone ESLESMEZ ve tek
# mesaj bile gelmez (D1'in birebir aynisi, 30 Agustos'ta olculdu).
_RC_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# joystick_interpreter bu konuya RELIABLE yayinliyor (D1 duzeltmesi,
# 30 Agustos). BEST_EFFORT abone RELIABLE yayinciyla ESLESIR.
_KOMUT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

_durum = {'ch': [0] * 14, 'n': 0, 't': 0.0, 'cmd': None, 'cmd_t': 0.0,
          'gorev': None}
_kilit = threading.Lock()

# 🔴 SONUCLAR SUNUCUDA SAKLANIR (31 Agustos). Ilk surumde butun hesap
# tarayicida kaliyordu; operator olcumu yapti, "kontrol et" dedi ve
# sonuclara ULASILAMADI — bir tur daha kaybedildi. Artik her tamamlanan
# olcum buraya dusuyor ve `curl /sonuc` ile okunabiliyor.
_SONUC_DOSYA = '/tmp/kumanda_sonuc.jsonl'
_sonuclar = []


class Dinleyici(Node):
    """RC akisini paylasilan duruma yazar. SALT OKUR."""

    def __init__(self) -> None:
        super().__init__('kumanda_web')
        self.create_subscription(RCIn, KONU, self._geldi, _RC_QOS)
        # 🔴 YORUMLANMIS KOMUT — ham PWM degil, rc_eksen'den GECMIS hali.
        # Isaret hatasi bu projede ucusla odeniyor: ters bir yaw "pilot saga
        # cevirir, suru SOLA doner" demek ve hicbir yerde hata vermez.
        # Ham kanala bakmak yetmez, KODUN NE ANLADIGINI gormek gerek.
        self.create_subscription(
            SwarmControlCommand, KOMUT_KONU, self._komut, _KOMUT_QOS)
        self.create_subscription(UInt8, GOREV_KONU, self._gorev, 10)
        self.get_logger().info(f'kumanda_web: {KONU} dinleniyor, port {PORT}')

    def _geldi(self, msg: RCIn) -> None:
        if len(msg.channels) < 8:
            return
        ch = list(msg.channels)[:14]
        ch += [0] * (14 - len(ch))
        with _kilit:
            _durum['ch'] = ch
            _durum['n'] += 1
            _durum['t'] = time.monotonic()

    def _gorev(self, m: UInt8) -> None:
        with _kilit:
            _durum['gorev'] = int(m.data)

    def _komut(self, m: SwarmControlCommand) -> None:
        with _kilit:
            _durum['cmd'] = {
                'pitch': round(float(m.pitch_cmd), 3),
                'roll': round(float(m.roll_cmd), 3),
                'yaw': round(float(m.yaw_cmd), 3),
                'gaz': round(float(m.throttle_cmd), 3),
                'valid': bool(m.command_valid),
                'deadman': bool(m.deadman_pressed),
                'mod': int(m.mode),
                'takeoff': bool(m.takeoff),
                'land': bool(m.land),
                'form': int(m.requested_formation),
                'form_degisti': bool(m.formation_change_requested),
                'maxhiz': round(float(m.max_speed_mps), 2),
                'aralik': round(float(m.requested_spacing_m), 1),
            }
            _durum['cmd_t'] = time.monotonic()


SAYFA = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yelpence — Kumanda Olcum</title>
<style>
:root{--bg:#0d1117;--k:#161b22;--cz:#30363d;--y:#c9d1d9;--sn:#8b949e;
      --ok:#3fb950;--uy:#d29922;--hata:#f85149;--mavi:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--y);
     font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{padding:12px 16px;background:var(--k);border-bottom:1px solid var(--cz);
       display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}
.rozet{padding:2px 8px;border-radius:10px;font-size:12px}
.canli{background:#0d4429;color:var(--ok)}
.olu{background:#4d1f1c;color:var(--hata)}
main{padding:16px;display:grid;gap:16px;
     grid-template-columns:repeat(auto-fit,minmax(340px,1fr));max-width:1500px}
section{background:var(--k);border:1px solid var(--cz);border-radius:8px;
        padding:14px}
h2{font-size:14px;margin:0 0 10px;color:var(--mavi)}
.kanal{display:grid;grid-template-columns:52px 1fr 58px;gap:8px;
       align-items:center;margin-bottom:3px}
.ad{color:var(--sn);font-size:12px}
.cubuk{height:14px;background:#0d1117;border-radius:3px;position:relative;
       overflow:hidden}
.dolgu{position:absolute;top:0;bottom:0;background:var(--mavi);opacity:.75}
.val{text-align:right;font-variant-numeric:tabular-nums}
.rol{color:var(--uy);font-size:11px}
button{background:#21262d;color:var(--y);border:1px solid var(--cz);
       border-radius:6px;padding:7px 12px;cursor:pointer;font:inherit;
       font-size:13px}
button:hover{border-color:var(--mavi)}
button.birincil{background:#1f6feb;border-color:#1f6feb;color:#fff}
button:disabled{opacity:.4;cursor:default}
.satir{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.kutu{background:#0d1117;border:1px solid var(--cz);border-radius:6px;
      padding:10px;margin-top:8px;white-space:pre-wrap;font-size:12.5px}
.ok{color:var(--ok)}.uy{color:var(--uy)}.hata{color:var(--hata)}
.sn{color:var(--sn)}
.mavi{color:var(--mavi)}
.buyuk{font-size:22px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td,th{text-align:left;padding:3px 6px;border-bottom:1px solid var(--cz)}
th{color:var(--sn);font-weight:500}
</style></head><body>

<header>
  <h1>Yelpençe — Kumanda Ölçüm</h1>
  <span id="link" class="rozet olu">bağlantı yok</span>
  <span id="hz" class="sn"></span>
  <span id="donuk" class="sn"></span>
</header>

<main>
  <section>
    <h2>Canlı kanallar</h2>
    <div id="kanallar"></div>
  </section>

  <section>
    <h2>🔴 Yorumlanmış komut — sürünün GÖRDÜĞÜ</h2>
    <div class="sn" style="margin-bottom:8px">
      Ham PWM değil, <code>rc_eksen</code>'den geçmiş hâli. Çubuğu it,
      okun doğru yöne baktığını gör. Sözleşme:
      pitch&gt;0 ileri · roll&gt;0 sağa · yaw&gt;0 <b>saat yönü</b> ·
      gaz&gt;0 tırmanış.
    </div>
    <div id="kapilar" class="kutu sn">komut akışı yok</div>
    <div id="eksenler" class="kutu"></div>
  </section>

  <section>
    <h2>🎯 ŞU AN NE OLUR — salteri oynatmadan önce oku</h2>
    <div class="sn" style="margin-bottom:8px">
      Kapılar ve her salterin O ANKİ sonucu. Tahmin değil: canlı
      telemetriden okunuyor.
    </div>
    <div id="senaryo" class="kutu">bekleniyor…</div>
  </section>

  <section>
    <h2>madde 17 — Eksen işaretleri</h2>
    <div class="sn" style="margin-bottom:8px">
      Butona bas, çubuğu <b>söylenen yöne</b> it ve tut, sonra bırak.
      🔴 Tek yöne oynat.
    </div>
    <div class="satir">
      <button onclick="eksenBasla('PITCH')">PITCH — ileri</button>
      <button onclick="eksenBasla('ROLL')">ROLL — sağa</button>
      <button onclick="eksenBasla('YAW')">YAW — sağa</button>
      <button onclick="eksenBasla('GAZ')">GAZ — yukarı</button>
    </div>
    <div id="eksenDurum" class="kutu sn">hazır</div>
    <div id="eksenSonuc" class="kutu"></div>
  </section>

  <section>
    <h2>madde 26 — SwC geçiş süresi</h2>
    <div class="sn" style="margin-bottom:8px">
      Kaydı başlat, SwC'yi <b>uçtan uca</b> 5-6 kez gezdir —
      <b>ortada durma</b>. Sonra durdur.
    </div>
    <div class="satir">
      <button id="swcBtn" class="birincil" onclick="swcAcKapa()">
        Kaydı başlat</button>
      <button onclick="swcSifirla()">Sıfırla</button>
    </div>
    <div id="swcSonuc" class="kutu sn">kayıt yok</div>
  </section>

  <section>
    <h2>madde 30 — Kumanda kaybında deadman</h2>
    <div class="sn" style="margin-bottom:8px">
      SwA'yı <b>CH5 = 2000</b> veren konuma al, sonra
      <b>kumandayı kapat</b>. Sayfa gerisini kendi anlar.
    </div>
    <div class="satir">
      <button id="fsBtn" class="birincil" onclick="fsBasla()">
        Testi başlat</button>
    </div>
    <div id="fsDurum" class="kutu sn">hazır</div>
  </section>
</main>

<script>
const ADLAR = ['CH1 roll','CH2 pitch','CH3 gaz','CH4 yaw','CH5 SwA','CH6 SwB',
               'CH7 SwC','CH8 SwD','CH9','CH10','CH11','CH12','CH13','CH14'];
const ROLLER = {4:'emniyet / deadman',5:'mod',6:'formasyon (3 konum)',
                7:'kalkış / iniş'};
// joystick_interpreter esikleri: aux = (pwm-1500)*2, esik +-300 -> 1350/1650
const ALT = 1350, UST = 1650;

let sonN = -1, sonCh = null, sonDegisim = 0, gecmis = [];
let eksen = null, swcKayit = null, fs = null;

function bolge(v){ return v < ALT ? 'OKBASI' : (v > UST ? 'CIZGI' : 'V'); }

// Tamamlanan her olcumu UCAGA yaz. Tarayicida kalan sonuc, sonuc degildir:
// operator "hallettim" der, karsi taraf goremez ve olcum bir kez daha
// yapilir (31 Agustos'ta yasandi).
function kaydet(tip, veri){
  fetch('/sonuc', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({tip, veri, zaman: new Date().toISOString()})
  }).catch(()=>{});
}

function kanalCiz(ch){
  const k = document.getElementById('kanallar');
  if(!k.dataset.kur){
    k.innerHTML = ADLAR.map((a,i)=>
      `<div class="kanal"><span class="ad">${a}</span>
       <div class="cubuk"><div class="dolgu" id="d${i}"></div></div>
       <span class="val" id="v${i}">—</span></div>
       ${ROLLER[i]?`<div class="rol" style="margin:-2px 0 6px 60px">
       ${ROLLER[i]}</div>`:''}`).join('');
    k.dataset.kur = '1';
  }
  ch.forEach((v,i)=>{
    const p = Math.max(0, Math.min(100, (v-1000)/10));
    document.getElementById('d'+i).style.width = p+'%';
    document.getElementById('v'+i).textContent = v;
  });
}

async function tik(){
  let d;
  try{ d = await (await fetch('/k',{cache:'no-store'})).json(); }
  catch(e){ document.getElementById('link').className='rozet olu';
            document.getElementById('link').textContent='sunucu yok'; return; }

  const canli = d.n !== sonN;
  sonN = d.n;
  const rz = document.getElementById('link');
  rz.className = 'rozet ' + (d.yas < 1 ? 'canli' : 'olu');
  rz.textContent = d.yas < 1 ? 'akış var' : 'akış YOK';
  document.getElementById('hz').textContent = d.hz ? d.hz.toFixed(1)+' Hz' : '';

  const ch = d.ch;
  kanalCiz(ch);
  const t = performance.now()/1000;

  // Donukluk: butun kanallar bit-birebir ayni kaldigi sure. Kumanda
  // kapaliyken alici SON CERCEVEYI TUTUYOR (31 Agu, B20) — canli ile olu
  // hali ayiran tek iz bu.
  if(sonCh && ch.every((v,i)=>v===sonCh[i])){
    document.getElementById('donuk').textContent =
      'donuk ' + (t-sonDegisim).toFixed(1) + ' s';
  } else { sonDegisim = t;
           document.getElementById('donuk').textContent = 'donuk 0.0 s'; }
  sonCh = ch.slice();

  cmdCiz(d.cmd);
  // Panelde bir JS hatasi olursa SESSIZCE donuyordu ('bekleniyor…'
  // yazisi kaliyor, sebep hicbir yerde gorunmuyor — 31 Agu'da tam bu
  // yasandi: senaryoCiz icinde kapsam disi bir degisken vardi).
  // Hata artik panelin kendisine yaziliyor ve tik() kirilmiyor.
  try{ senaryoCiz(d); }
  catch(e){ document.getElementById('senaryo').innerHTML =
      '<span class="hata">panel hatası: ' + e + '</span>'; }
  gecmis.push({t, ch});
  if(gecmis.length > 4000) gecmis.shift();

  if(eksen) eksenTik(ch, t);
  if(swcKayit) swcTik(ch, t);
  if(fs) fsTik(ch, t);
}

/* ---------- yorumlanmis komut ---------- */
const OKLAR = {
  pitch:{art:'▲ İLERİ', eksi:'▼ GERİ'},
  roll :{art:'▶ SAĞA',  eksi:'◀ SOLA'},
  yaw  :{art:'↻ SAAT YÖNÜ (sağ)', eksi:'↺ SAAT TERSİ (sol)'},
  gaz  :{art:'▲ TIRMANIŞ', eksi:'▼ ALÇALMA'},
};
function cmdCiz(c){
  const kp = document.getElementById('kapilar');
  const ek = document.getElementById('eksenler');
  if(!c){ kp.innerHTML = '<span class="hata">komut akışı YOK — ' +
    'joystick_interpreter koşuyor mu?</span>'; ek.innerHTML = ''; return; }
  // Iki kapi: SwA (deadman) ve gaz merkez kapisi (B18). Ikisi de acik
  // degilse eksenler SIFIRLANIR ve suru komut almaz — bunu gormek sart,
  // yoksa "cubugu oynatiyorum bir sey olmuyor" diye vakit kaybedilir.
  kp.innerHTML =
    `emniyet (SwA): <b class="${c.deadman?'ok':'hata'}">` +
      `${c.deadman?'AÇIK':'KİLİTLİ'}</b>   ` +
    `paket geçerli: <b class="${c.valid?'ok':'uy'}">` +
      `${c.valid?'EVET':'HAYIR (gazı bir kez ORTAYA getir)'}</b>\n` +
    `mod: ${c.mod===2?'MANEVRA':'HAREKET'}   ` +
    `formasyon: ${['?','okbaşı','V','çizgi'][c.form]||c.form}` +
    (c.form_degisti?' <b class="uy">← DEĞİŞİM</b>':'') + '\n' +
    `SwD: takeoff=<b class="${c.takeoff?'uy':'sn'}">${c.takeoff}</b>  ` +
    `land=<b class="${c.land?'uy':'sn'}">${c.land}</b>`;
  ek.innerHTML = ['pitch','roll','yaw','gaz'].map(a=>{
    const v = c[a], o = OKLAR[a];
    const yon = Math.abs(v) < 0.08 ? '<span class="sn">— nötr</span>'
      : `<b class="ok">${v>0?o.art:o.eksi}</b>`;
    return `${a.padEnd(6)} ${v>=0?' ':''}${v.toFixed(2)}   ${yon}`;
  }).join('\n');
}

/* ---------- SENARYO: salterlerin O ANKI sonucu ---------- */
/* VrB formasyon kilidi — formasyon_kilidi.py ile AYNI esik.
   aux olcegi -1000..+1000; ham PWM'de karsiligi 1900. */
const VRB_PWM_ESIK = 1900;
const GOREV_YARI_OTONOM = 8;

function ib(v, e, h){ return `<b class="${v?'ok':(h||'hata')}">${v?e[0]:e[1]}</b>`; }

function senaryoCiz(d){
  const el = document.getElementById('senaryo');
  const c = d.cmd;
  if(!c){ el.innerHTML = '<span class="hata">komut akışı YOK — ' +
    'joystick_interpreter koşuyor mu?</span>'; return; }

  const vrb      = d.ch[9];
  const kilitAcik= vrb > VRB_PWM_ESIK;
  const gorevOK  = d.gorev === GOREV_YARI_OTONOM;
  const gazPwm   = d.ch[2];
  const gazHam   = ((gazPwm-1000)/1000)*2 - 1;   // rc_eksen ile ayni donusum
  const hiz      = c.maxhiz || 0;

  // --- kalkis kapilari (G2-K10) ---
  const eksik = [];
  if(!c.deadman) eksik.push('SwA emniyet KAPALI');
  if(!c.valid)   eksik.push('gaz merkez kapısı KAPALI (gazı bir kez ortaya getir)');
  if(!gorevOK)   eksik.push(`görev başlatılmadı (mission_state=${d.gorev===null?'yok':d.gorev}, 8 bekleniyor)`);

  const satir = [];
  satir.push('<b class="mavi">KAPILAR</b>');
  satir.push('  SwA emniyet          ' + ib(c.deadman, ['AÇIK','KİLİTLİ']));
  satir.push('  gaz merkez (B18)     ' + ib(c.valid, ['GEÇERLİ','KAPALI'], 'uy'));
  satir.push('  görev başlatıldı     ' + ib(gorevOK, ['EVET','HAYIR'], 'uy') +
             `  <span class="sn">(mission_state=${d.gorev===null?'—':d.gorev})</span>`);
  satir.push('  VrB formasyon anahtarı ' + ib(kilitAcik, ['AÇIK','KAPALI'], 'uy') +
             `  <span class="sn">(ch10=${vrb}, eşik ${VRB_PWM_ESIK})</span>`);
  satir.push('');
  satir.push('<b class="mavi">SALTERİ OYNATIRSAN</b>');

  satir.push('  SwD ↑ (kalkış)   → ' + (eksik.length
      ? '<b class="hata">KALKMAZ</b> <span class="sn">— ' + eksik.join(' · ') + '</span>'
      : '<b class="uy">KALKAR</b> <span class="sn">— üç kapı da açık</span>'));

  satir.push('  SwD ↓ (iniş)     → <b class="uy">İNİŞ</b> ' +
             '<span class="sn">— mandal, kapılara bakmaz (madde 24)</span>');

  const swcAd = bolge(d.ch[6]);   // aux3 = ch7
  satir.push('  SwC (formasyon)  → ' + (kilitAcik
      ? `<b class="uy">${swcAd}</b> <span class="sn">— çevirirsen değişir (yeni konumda 1300 ms kararlı kalmalı)</span>`
      : `<b class="ok">ETKİSİZ</b> <span class="sn">— VrB kapalı; SwC ${swcAd} gösteriyor ama formasyon OLUŞMAZ</span>`));

  const cubukCalisir = c.deadman && c.valid;
  satir.push('  Çubuklar         → ' + (cubukCalisir
      ? '<b class="uy">SÜRÜ HAREKET EDER</b> <span class="sn">— mod: ' +
        (c.mod===2?'MANEVRA':'HAREKET') + '</span>'
      : '<b class="ok">komut GİTMEZ</b> <span class="sn">— eksenler sıfırlanıyor</span>'));

  // --- formasyon: VrB ANA ANAHTAR davranisi (31 Agu operator karari) ---
  const FADI = ['YOK','ok başı','V','çizgi'];
  satir.push('');
  satir.push('<b class="mavi">FORMASYON</b>  <span class="sn">(VrB anahtar: kapalı = formasyon yok)</span>');
  satir.push('  sürüye giden     ' + (c.form === 0
      ? '<b class="ok">YOK</b> <span class="sn">— uçaklar bulunduğu yeri TUTAR (FORMATION_UNKNOWN)</span>'
      : `<b class="uy">${FADI[c.form]||c.form}</b> <span class="sn">· ${(c.aralik||0).toFixed(1)} m aralık</span>`)
      + (c.form_degisti ? '  <b class="uy">← DEĞİŞİM</b>' : ''));
  satir.push('  VrB kapatırsan   → ' + (c.form === 0
      ? '<span class="sn">zaten formasyon yok</span>'
      : '<b class="ok">FORMASYON KALKAR</b> <span class="sn">— uçaklar OLDUĞU YERDE kalır, hareket etmez</span>'));
  satir.push('  VrB açarsan      → ' + (kilitAcik
      ? '<span class="sn">zaten açık</span>'
      : `<b class="uy">${swcAd} AKTİF OLUR</b> <span class="sn">— SwC şu an orada duruyor</span>`));

  // --- dikey: 31 Agustos kusurunun canli gostergesi ---
  const dikeyKomut = c.gaz * hiz;
  let dikeyMetin;
  if(Math.abs(c.gaz) < 0.001 && Math.abs(gazHam) > 0.2){
    dikeyMetin = '<b class="ok">0.00 m/s — DİKEY YETKİ TUTUYOR</b> ' +
      '<span class="sn">çubuk ' + gazHam.toFixed(2) +
      ' ama komut sıfır. Gazı ORTAYA getir, yetki açılsın.</span>';
  } else if(Math.abs(dikeyKomut) < 0.05){
    dikeyMetin = '<b class="ok">0.00 m/s</b> <span class="sn">nötr</span>';
  } else {
    dikeyMetin = '<b class="hata">' + Math.abs(dikeyKomut).toFixed(2) + ' m/s ' +
      (dikeyKomut > 0 ? 'TIRMANIŞ' : 'ALÇALMA') + '</b>';
  }
  satir.push('');
  satir.push('<b class="mavi">DİKEY</b>  <span class="sn">(31 Ağustos kusuru: çubuk dipteyken 2 m/s alçalma)</span>');
  satir.push('  gaz çubuğu ham   ' + gazHam.toFixed(2) +
             ` <span class="sn">(PWM ${gazPwm})</span>`);
  satir.push('  sürüye giden     ' + c.gaz.toFixed(2) +
             ` <span class="sn">× ${hiz.toFixed(1)} m/s =</span> ` + dikeyMetin);

  el.innerHTML = satir.join('\n');
}

/* ---------- madde 17 — eksen isaretleri ---------- */
const EKSEN = {
  PITCH:{i:1, yon:'İLERİ it ve TUT', sozlesme:'>0 = ileri'},
  ROLL :{i:0, yon:'SAĞA it ve TUT',  sozlesme:'>0 = sağa'},
  YAW  :{i:3, yon:'SAĞA çevir ve TUT', sozlesme:'>0 = saat yönü'},
  GAZ  :{i:2, yon:'YUKARI it ve TUT', sozlesme:'>0 = tırmanış'},
};
function eksenBasla(ad){
  eksen = {ad, ...EKSEN[ad], uc:null, birakildi:false};
  document.getElementById('eksenDurum').innerHTML =
    `<span class="uy">${ad}: çubuğu <b>${EKSEN[ad].yon}</b></span>`;
}
function eksenTik(ch, t){
  const v = ch[eksen.i];
  // GAZ ORTALANMAZ (dinlenme yeri DIP, olculen 1000) — "merkezden sapma"
  // olcutu daha operator dokunmadan dogru olurdu. Gazda olcut UST uca
  // gitmek; digerlerinde merkezden 300 us sapmak.
  const sapti = eksen.ad === 'GAZ' ? v > 1700 : Math.abs(v-1500) > 300;
  if(sapti && (eksen.uc === null ||
      Math.abs(v-1500) > Math.abs(eksen.uc-1500))) eksen.uc = v;
  if(eksen.uc !== null){
    document.getElementById('eksenDurum').innerHTML =
      `<span class="uy">${eksen.ad}: uç = <b>${eksen.uc}</b> — şimdi BIRAK</span>`;
    const merkezde = eksen.ad === 'GAZ' ? v < 1300 : Math.abs(v-1500) < 150;
    if(merkezde) eksenBitir();
  }
}
function eksenBitir(){
  const {ad, uc, sozlesme} = eksen;
  const ust = uc > 1500;
  let satir;
  if(ad === 'GAZ'){
    satir = uc > 1700
      ? `<span class="ok">GAZ: ${uc} — ✅ doğru (yukarı = üst uç)</span>`
      : `<span class="hata">GAZ: ${uc} — 🔴 TERS, kumandada REVERSE et</span>`;
  } else {
    const ters = !ust;
    satir = `<span class="${ters?'uy':'ok'}">${ad}: ${uc} ` +
            `(${sozlesme}) → <b>TERS_${ad} = ${ters}</b></span>`;
  }
  const k = document.getElementById('eksenSonuc');
  k.innerHTML += (k.innerHTML ? '\n' : '') + satir;
  kaydet('eksen', {eksen: ad, uc,
                   ters: ad === 'GAZ' ? (uc <= 1700) : !ust});
  document.getElementById('eksenDurum').innerHTML =
    '<span class="sn">hazır — sıradaki ekseni seç</span>';
  eksen = null;
}

/* ---------- madde 26 — SwC gecis suresi ---------- */
function swcAcKapa(){
  const b = document.getElementById('swcBtn');
  if(swcKayit){ swcOzet(true); swcKayit = null;
                b.textContent = 'Kaydı başlat';
                b.className = 'birincil'; return; }
  swcKayit = {bloklar:[]};
  b.textContent = 'Kaydı durdur'; b.className = '';
}
function swcSifirla(){
  swcKayit = null;
  document.getElementById('swcBtn').textContent = 'Kaydı başlat';
  document.getElementById('swcBtn').className = 'birincil';
  document.getElementById('swcSonuc').innerHTML = 'kayıt yok';
}
function swcTik(ch, t){
  const b = bolge(ch[6]), bl = swcKayit.bloklar;
  if(bl.length && bl[bl.length-1].b === b) bl[bl.length-1].son = t;
  else bl.push({b, bas:t, son:t});
  swcCiz();
}
function swcCiz(){ swcOzet(false); }

function swcOzet(yolla){
  const bl = swcKayit ? swcKayit.bloklar : [];
  const gecis = [], kasitli = [];
  for(let i=0;i<bl.length;i++){
    if(bl[i].b !== 'V') continue;
    if(i+1 >= bl.length) continue;        // son blok KESIK olabilir
    const ms = (bl[i].son - bl[i].bas)*1000;
    const onc = i>0 ? bl[i-1].b : null, snr = bl[i+1].b;
    if(onc && snr !== onc) gecis.push(ms); else kasitli.push(ms);
  }
  const k = document.getElementById('swcSonuc');
  if(!gecis.length){
    k.innerHTML = `<span class="sn">geçiş: 0 — SwC'yi uçtan uca gezdir` +
                  ` (blok ${bl.length})</span>`;
    return;
  }
  // 1 s'yi asan "gecis" el hareketi degil DURAKLAMADIR; sessizce
  // kullanilirsa esigi bosuna yukari ceker. Ayiklaniyor ama GORUNUR.
  const supheli = gecis.filter(m=>m>1000), temiz = gecis.filter(m=>m<=1000);
  const enUzun = temiz.length ? Math.max(...temiz) : 0;
  const esik = enUzun ? Math.max(enUzun*1.5, enUzun+60) : 0;
  k.innerHTML =
    `<b>${temiz.length} geçiş</b> (ms): ${temiz.map(m=>m.toFixed(0)).join(' · ')}\n` +
    (supheli.length ? `<span class="uy">⚠ ${supheli.length} adet 1 s'yi ` +
      `aşan ayıklandı (ortada duraklanmış)</span>\n` : '') +
    `en uzun geçiş: <b>${enUzun.toFixed(0)} ms</b>\n` +
    `<span class="ok">önerilen debounce eşiği: ` +
    `<b>${esik.toFixed(0)} ms</b></span>\n` +
    `<span class="sn">kasıtlı V duruşu: ${kasitli.length} adet</span>`;
  if(yolla) kaydet('swc', {gecisler: temiz.map(m=>+m.toFixed(0)),
                           supheli: supheli.map(m=>+m.toFixed(0)),
                           en_uzun: +enUzun.toFixed(0),
                           onerilen_esik_ms: +esik.toFixed(0),
                           kasitli: kasitli.length});
}

/* ---------- madde 30 — failsafe / deadman ---------- */
function fsBasla(){
  fs = {faz:'bekle_acik', dususT:null, enDusuk:null};
  document.getElementById('fsBtn').disabled = true;
}
function fsTik(ch, t){
  const v = ch[4], k = document.getElementById('fsDurum');
  if(fs.faz === 'bekle_acik'){
    if(v >= 1900){ fs.faz = 'bekle_kapali';
      k.innerHTML = `<span class="ok">✅ CH5 = ${v} (emniyet AÇIK)</span>\n` +
        `<span class="buyuk uy">ŞİMDİ KUMANDAYI KAPAT</span>`;
    } else {
      k.innerHTML = `<span class="uy">CH5 = ${v} — SwA'yı <b>2000</b> ` +
        `veren konuma al</span>`;
    }
    return;
  }
  if(fs.faz === 'bekle_kapali'){
    if(v <= 1100){ fs.faz = 'kalicilik'; fs.dususT = t; fs.enDusuk = v;
      k.innerHTML = `<span class="ok">CH5 düştü: ${v}</span>\n` +
        `kalıcı mı diye izleniyor...`;
    }
    return;
  }
  if(fs.faz === 'kalicilik'){
    const gecen = t - fs.dususT;
    if(v >= 1900){
      k.innerHTML = `<span class="uy">⚠ CH5 tekrar 2000'e çıktı — ` +
        `düşüş KALICI DEĞİL.\nKumanda tekrar açılmış ya da salter ` +
        `oynatılmış olabilir. Testi tekrarla.</span>`;
      kaydet('failsafe', {sonuc: 'KALICI_DEGIL', ch5: v});
      fs = null; document.getElementById('fsBtn').disabled = false; return;
    }
    if(gecen >= 6){
      k.innerHTML = `<span class="ok buyuk">✅ FAILSAFE ÇALIŞIYOR</span>\n` +
        `CH5 = ${v}, ${gecen.toFixed(0)} sn boyunca düşük kaldı.\n` +
        `Kumanda kaybında deadman DÜŞER → sürü HOLD'a geçer.\n` +
        `<span class="sn">madde 30 kapandı — gorev2.md'ye yaz.</span>`;
      kaydet('failsafe', {sonuc: 'CALISIYOR', ch5: v,
                          kalici_s: +gecen.toFixed(1)});
      fs = null; document.getElementById('fsBtn').disabled = false; return;
    }
    k.innerHTML = `<span class="ok">CH5 = ${v}, ${gecen.toFixed(1)} sn` +
      ` düşük...</span>`;
  }
}

setInterval(tik, 50);
</script></body></html>
"""


class Sunucu(BaseHTTPRequestHandler):
    """Iki uc nokta: sayfa ve ham kanal JSON'u."""

    def log_message(self, bicim, *args):
        pass    # erisim gunlugu gurultu; hatalar zaten stderr'e gidiyor

    def _yolla(self, govde: bytes, tip: str) -> None:
        self.send_response(200)
        self.send_header('Content-Type', tip)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_POST(self):
        if not self.path.startswith('/sonuc'):
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get('Content-Length', 0))
        try:
            kayit = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        with _kilit:
            _sonuclar.append(kayit)
            try:
                with open(_SONUC_DOSYA, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(kayit, ensure_ascii=False) + '\n')
            except OSError:
                pass    # disk sorunu olcumu dusurmesin; bellekte duruyor
        self._yolla(b'{"ok":true}', 'application/json')

    def do_GET(self):
        if self.path.startswith('/sonuc'):
            with _kilit:
                govde = json.dumps(_sonuclar, ensure_ascii=False,
                                   indent=1).encode()
            self._yolla(govde, 'application/json')
            return
        if self.path.startswith('/k'):
            with _kilit:
                ch, n, t = _durum['ch'], _durum['n'], _durum['t']
            yas = time.monotonic() - t if t else 999.0
            with _kilit:
                cmd, cmd_t = _durum['cmd'], _durum['cmd_t']
            cmd_yas = time.monotonic() - cmd_t if cmd_t else 999.0
            govde = json.dumps({
                'ch': ch, 'n': n, 'yas': round(yas, 3),
                'hz': 32.5 if yas < 1 else 0.0,
                'cmd': cmd if cmd_yas < 1.0 else None,
                'gorev': _durum['gorev'],
            }).encode()
            self._yolla(govde, 'application/json')
            return
        self._yolla(SAYFA.encode(), 'text/html; charset=utf-8')


def main() -> None:
    rclpy.init()
    dugum = Dinleyici()
    sunucu = ThreadingHTTPServer(('0.0.0.0', PORT), Sunucu)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    print(f'kumanda_web hazir: http://0.0.0.0:{PORT}', flush=True)
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        sunucu.shutdown()
        dugum.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
