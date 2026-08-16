"""test_entegrasyon_formasyon.py - koprunun suru yollarini UCTAN UCA dogrular.

Donanim gerekmez: socat ile sanal pty cifti kurulur, koprunun bir ucunu o
tutar, test digerini. Boylece GERCEK bayt akisi dogrulanir - birim testlerin
goremedigi seyler burada yakalanir:

  A) Lider kapisi (KARAR 11) - lider bilinmezken formasyon mesh'e CIKMAMALI
  B) Lider olunca cikmali VE loopback ile yerel public'e yayinlanmali
  C) Komsudan gelen TIP_FORMASYON offsetleri DOLU yayinlanmali (KARAR 9)
  D) TIP_QR_GOREV team_id DOLDURULARAK yayinlanmali (KARAR 7 tuzagi)
  E) Teshis sayaclari dogru artmali

NEDEN LOOPBACK KRITIK (B)
Sahada her Pi'nin ROS grafigi ayri (ROS_LOCALHOST_ONLY=1) ve koprunun kendi
mesh yayini dispatch'te filtreleniyor (iha_id == agent_id -> return). Yani
LIDERIN formation_node'u formasyon hedefini baska hicbir yoldan alamaz.
Simulasyonda bu bosluk GORUNMUYOR: network_proxy tek ROS grafiginde gonderene
de geri veriyor. Bu test o boslugu yakalar.

NEDEN VARSAYILAN OLARAK ATLANIR
socat, ROS ortami ve surec baslatma gerektiriyor; birim test degil entegrasyon
testi. Bilerek calistirmak icin:

    YELPENCE_ENTEGRASYON=1 pytest test/test_entegrasyon_formasyon.py -s
"""

import os
import pathlib
import shutil
import subprocess
import threading
import time

import pytest
import rclpy                                                    # noqa: E402
import serial                                                   # noqa: E402
from rclpy.node import Node                                     # noqa: E402
from rclpy.qos import (                                         # noqa: E402
    QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy,
)
from swarm_interfaces.msg import (                               # noqa: E402
    ElectionResult, FormationCommand, QRMissionData, SystemEvent,
)

from swarm_control.esp32_bridge import packet_parser as pp       # noqa: E402
from swarm_control.esp32_bridge.cobs import cobs_encode          # noqa: E402
from swarm_control.esp32_bridge.crc16 import crc16               # noqa: E402

PTY_KOPRU = '/tmp/pty_kopru'
PTY_TEST = '/tmp/pty_test'
AGENT = 1
TAKIM = 'YLP26'

_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST, depth=10,
)
_QOS_REL = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST, depth=10,
)

hata = 0


def kontrol(ad, kosul, ek=''):
    global hata
    print(f'   {"OK  " if kosul else "HATA"} {ad} {ek}')
    if not kosul:
        hata += 1


def cerceve_uret(tip, iha_id, payload):
    """Firmware uart_gonder'i taklit eder."""
    govde = bytes([tip, iha_id]) + payload
    c = crc16(govde)
    return cobs_encode(govde + bytes([(c >> 8) & 0xFF, c & 0xFF]))


class Yardimci(Node):
    def __init__(self):
        super().__init__('test_yardimci')
        self.form_pub = self.create_publisher(
            FormationCommand, '/swarm/internal/formation/target', _QOS)
        self.qr_pub = self.create_publisher(
            QRMissionData, '/swarm/internal/perception/qr_data', _QOS)
        self.sec_pub = self.create_publisher(
            ElectionResult, '/swarm/internal/election/result', _QOS_REL)
        self.alinan_form = []
        self.alinan_qr = []
        self.olaylar = []
        self.create_subscription(
            SystemEvent, '/swarm/internal/events/system',
            lambda m: self.olaylar.append(m.message), _QOS)
        self.create_subscription(
            FormationCommand, '/swarm/public/formation/target',
            lambda m: self.alinan_form.append(m), _QOS)
        self.create_subscription(
            QRMissionData, '/swarm/public/perception/qr_data',
            lambda m: self.alinan_qr.append(m), _QOS)


def formasyon_mesaji(tip=1, ajanlar=(3, 1, 2), spacing=5.0,
                     merkez=(12.0, -8.0, -15.0), heading=137.0, hiz=3.0):
    m = FormationCommand()
    m.formation_type = tip
    m.agent_ids = list(ajanlar)
    m.spacing_m = spacing
    m.center_x, m.center_y, m.center_z = merkez
    m.heading_deg = heading
    m.max_speed_mps = hiz
    m.source_module = 'test'
    return m


def _senaryo():
    global hata
    os.environ['ROS_DOMAIN_ID'] = '42'          # calisan YKI'ye bulasmasin
    os.environ.pop('ROS_LOCALHOST_ONLY', None)

    # Onceki kosumdan artik surec kalmis olabilir; kalirsa AYNI pty'ye
    # yazar ve testi bozar (yasandi: 'multiple access on port', lider
    # kapisi testi 44 bayt gordu). Once temizle.
    _artik_surecleri_temizle()
    time.sleep(1.0)

    print('=== socat pty cifti kuruluyor ===')
    for p in (PTY_KOPRU, PTY_TEST):
        if os.path.islink(p) or os.path.exists(p):
            os.unlink(p)
    sc = subprocess.Popen(
        ['socat', '-d', f'pty,raw,echo=0,link={PTY_KOPRU}',
         f'pty,raw,echo=0,link={PTY_TEST}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if os.path.exists(PTY_KOPRU) and os.path.exists(PTY_TEST):
            break
        time.sleep(0.1)
    kontrol('pty cifti hazir', os.path.exists(PTY_KOPRU))

    ser = serial.Serial(PTY_TEST, 460800, timeout=0.3)
    # pty DTR/RTS ioctl'ini desteklemiyor; gercek ESP kartinda gerekli olan
    # bu cagrilar burada anlamsiz (bkz saha gunlugu §5.6).
    try:
        ser.setDTR(False)
        ser.setRTS(False)
    except OSError:
        pass

    print('=== kopru baslatiliyor ===')
    ortam = dict(os.environ)
    kopru = subprocess.Popen(
        ['ros2', 'run', 'swarm_control', 'esp32_bridge', '--ros-args',
         '-p', f'agent_id:={AGENT}', '-p', f'serial_port:={PTY_KOPRU}',
         '-p', f'team_id:={TAKIM}', '-p', 'wing_alpha_deg:=45.0'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=ortam)
    kopru_log = []
    threading.Thread(
        target=lambda: [kopru_log.append(x) for x in kopru.stdout],
        daemon=True).start()
    time.sleep(4.0)
    kontrol('kopru ayakta', kopru.poll() is None)

    rclpy.init()
    y = Yardimci()

    def don(sn):
        t = time.time()
        while time.time() - t < sn:
            rclpy.spin_once(y, timeout_sec=0.05)

    don(1.0)
    ser.reset_input_buffer()

    # ---------------------------------------------------------------- A ---
    print()
    print('=== A) LIDER KAPISI: lider bilinmezken cikmamali ===')
    y.form_pub.publish(formasyon_mesaji())
    don(1.5)
    ham = ser.read(4096)
    kontrol('mesh e HIC bayt cikmadi', len(ham) == 0, f'-> {len(ham)} bayt')
    kontrol('yerel public de yayin YOK', len(y.alinan_form) == 0,
            f'-> {len(y.alinan_form)}')
    uyari = any('LİDER BİLİNMİYOR' in x or 'LIDER BILINMIYOR' in x
                for x in kopru_log)
    kontrol('uyari basildi (sessiz kalmadi)', uyari)

    # ---------------------------------------------------------------- B ---
    print()
    print('=== B) LIDER OLUNCA: mesh e cikmali + LOOPBACK ===')
    e = ElectionResult()
    e.new_leader_id = AGENT
    e.election_round = 1
    e.sequence_num = 1
    y.sec_pub.publish(e)
    don(1.0)
    ser.reset_input_buffer()
    y.alinan_form.clear()

    y.form_pub.publish(formasyon_mesaji(ajanlar=(3, 1, 2)))
    don(1.5)
    ham = ser.read(4096)
    kontrol('mesh e bayt cikti', len(ham) > 0, f'-> {len(ham)} bayt')

    # cerceveyi coz
    from swarm_control.esp32_bridge.cobs import cobs_decode
    parcalar = [p for p in ham.split(b'\x00') if p]
    cozulen = []
    for p in parcalar:
        c = pp.cerceve_coz(cobs_decode(p))
        if c:
            cozulen.append(c)
    tipler = [c.tip for c in cozulen]
    kontrol('TIP_FORMASYON gonderildi', pp.TIP_FORMASYON in tipler,
            f'-> tipler {[hex(t) for t in tipler]}')
    kontrol('DEVAM paketi YOK (3 ajan)', pp.TIP_FORMASYON_DEVAM not in tipler)
    kontrol('OFSET paketi YOK (adlandirilmis)', pp.TIP_FORM_OFSET not in tipler)

    f = next((c for c in cozulen if c.tip == pp.TIP_FORMASYON), None)
    if f:
        v = pp.formasyon_coz(f.payload)
        kontrol('slot sirasi korundu', v.dolu_slotlar() == [3, 1, 2],
                f'-> {v.dolu_slotlar()}')
        kontrol('kanat alfa pakete kondu', v.kanat_alfa_deg == 45,
                f'-> {v.kanat_alfa_deg}')

    kontrol('LOOPBACK: yerel public e yayinlandi', len(y.alinan_form) >= 1,
            f'-> {len(y.alinan_form)}')
    if y.alinan_form:
        lb = y.alinan_form[-1]
        kontrol('loopback offsetleri DOLU', len(lb.offset_x) == 3,
                f'-> {len(lb.offset_x)}')
        kontrol('loopback agent_ids sirasi', list(lb.agent_ids) == [3, 1, 2],
                f'-> {list(lb.agent_ids)}')
        kontrol('loopback merkez kuantize (12.0)',
                abs(lb.center_x - 12.0) < 0.06, f'-> {lb.center_x}')

    # ---------------------------------------------------------------- C ---
    print()
    print('=== C) ALMA: komsudan TIP_FORMASYON -> offsetler DOLU ===')
    y.alinan_form.clear()
    payload, uyarilar = pp.formasyon_paketle(
        formasyon_tipi=3, merkez_kuzey_m=5.0, merkez_dogu_m=0.0,
        merkez_asagi_m=-20.0, heading_deg=90.0, spacing_m=4.0,
        slot_ajan=[2, 1, 3], maks_hiz_mps=2.0, kanat_alfa_deg=45.0)
    kontrol('test paketi uyarisiz', uyarilar == [], f'-> {uyarilar}')
    ser.write(cerceve_uret(pp.TIP_FORMASYON, 2, payload))
    ser.flush()
    don(1.5)
    kontrol('public e yayinlandi', len(y.alinan_form) >= 1,
            f'-> {len(y.alinan_form)}')
    if y.alinan_form:
        r = y.alinan_form[-1]
        kontrol('formasyon tipi CIZGI', r.formation_type == 3)
        kontrol('agent_ids sirasi', list(r.agent_ids) == [2, 1, 3])
        kontrol('offsetler DOLU (KARAR 9)', len(r.offset_x) == 3,
                f'-> {len(r.offset_x)}')
        # cizgi formasyonu 4m aralik -> -4, 0, +4 civari
        genislik = max(r.offset_y) - min(r.offset_y)
        kontrol('cizgi genisligi ~8m (3 ajan x 4m)', abs(genislik - 8.0) < 0.2,
                f'-> {genislik:.2f}')
        kontrol('merkez dogru', abs(r.center_z + 20.0) < 0.06, f'-> {r.center_z}')

    # ---------------------------------------------------------------- D ---
    print()
    print('=== D) QR: team_id DOLDURULMALI ===')
    y.alinan_qr.clear()
    qp, qu = pp.qr_gorev_paketle(
        qr_id=3, qr_seq=7, sonraki_qr=4, valid=True, decoded=True,
        formasyon_aktif=True, formasyon_tipi=2, spacing_m=6.0,
        pitch_deg=10.0, irtifa_m=15.0, bekleme_s=5.0)
    kontrol('QR paketi uyarisiz', qu == [], f'-> {qu}')
    ser.write(cerceve_uret(pp.TIP_QR_GOREV, 2, qp))
    ser.flush()
    don(1.5)
    kontrol('QR public e yayinlandi', len(y.alinan_qr) >= 1,
            f'-> {len(y.alinan_qr)}')
    if y.alinan_qr:
        q = y.alinan_qr[-1]
        kontrol('team_id DOLDURULDU', q.team_id == TAKIM, f'-> {q.team_id!r}')
        kontrol('detector_agent_id kaynaktan', q.detector_agent_id == 2,
                f'-> {q.detector_agent_id}')
        kontrol('qr_id/seq/next', (q.qr_id, q.qr_seq, q.next_qr) == (3, 7, 4),
                f'-> {(q.qr_id, q.qr_seq, q.next_qr)}')
        kontrol('formasyon bayragi', q.formation_active is True)
        kontrol('spacing', abs(q.spacing_m - 6.0) < 0.05, f'-> {q.spacing_m}')
        kontrol('pitch', abs(q.pitch_deg - 10.0) < 0.5, f'-> {q.pitch_deg}')

    # ---------------------------------------------------------------- E ---
    print()
    print('=== E) TESHIS SAYAÇLARI ===')
    don(6.0)   # mesh_diag timer'ini bekle
    sayac = [x for x in y.olaylar if 'form_tx=' in x]
    if sayac:
        son = sayac[-1]
        import re
        for ad in ('lider', 'form_tx', 'form_rx', 'form_lider_degil', 'qr_rx'):
            m = re.search(rf'{ad}=(\d+)', son)
            print(f'      {ad} = {m.group(1) if m else "?"}')
        kontrol('form_tx >= 1', 'form_tx=0' not in son)
        kontrol('form_rx >= 1', 'form_rx=0' not in son)
        kontrol('lider dogru', f'lider={AGENT}' in son)
    else:
        kontrol('teshis satiri bulundu', False, '-> mesh_diag gorulmedi')

    # ------------------------------------------------------------ kapat ---
    y.destroy_node()
    rclpy.shutdown()
    ser.close()
    kopru.terminate()
    try:
        kopru.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kopru.kill()
    sc.terminate()

    print()
    print('=' * 60)
    if hata:
        print(f'BASARISIZ: {hata} kontrol')
        print()
        print('--- kopru loglarindan son 25 satir ---')
        for x in kopru_log[-25:]:
            print('   ' + x.rstrip())
    else:
        print('HEPSI GECTI')
    return hata


def _artik_surecleri_temizle() -> None:
    """Onceki kosumdan kalan kopru/socat sureclerini durdurur.

    `pkill -f` KULLANILMIYOR: desen cagiran kabugun komut satirinda da gectigi
    icin kendi kabugunu olduruyor (yasandi). /proc okunup kendi PID ve ata
    zinciri dislaniyor. YKI'nin base koprusune (agent_id:=10) DOKUNULMAZ.

    Neden gerekli: artik surec AYNI pty'ye yazar ve lider kapisi testini
    bozar - "multiple access on port" hatasiyla 0 yerine 44 bayt gorulur.
    """
    import signal
    benim = os.getpid()
    dokunma = {benim}
    pid = benim
    while pid and pid != 1:
        try:
            stat = pathlib.Path(f'/proc/{pid}/stat').read_text()
            pid = int(stat.rsplit(')', 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            break
        dokunma.add(pid)

    oldurulen = []
    for d in pathlib.Path('/proc').iterdir():
        if not d.name.isdigit() or int(d.name) in dokunma:
            continue
        try:
            cmd = (d / 'cmdline').read_bytes().replace(
                b'\x00', b' ').decode('utf-8', 'replace')
        except OSError:
            continue
        if 'agent_id:=10' in cmd:          # YKI base koprusu - koru
            continue
        if 'zsh' in cmd or 'pytest' in cmd:
            continue
        if PTY_KOPRU in cmd or PTY_TEST in cmd:
            try:
                os.kill(int(d.name), signal.SIGTERM)
                oldurulen.append(int(d.name))
            except OSError:
                pass
    if oldurulen:
        time.sleep(2.0)
        for pid in oldurulen:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


@pytest.mark.skipif(
    not os.environ.get('YELPENCE_ENTEGRASYON'),
    reason='entegrasyon testi: YELPENCE_ENTEGRASYON=1 ile bilerek calistirilir',
)
@pytest.mark.skipif(
    shutil.which('socat') is None,
    reason='socat kurulu degil (sanal seri port icin gerekli)',
)
def test_kopru_suru_yollari_uctan_uca():
    """Senaryoyu kosturur; tek bir kontrol bile duserse test basarisiz."""
    basarisiz = _senaryo()
    assert basarisiz == 0, f'{basarisiz} kontrol basarisiz'
