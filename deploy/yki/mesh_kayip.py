#!/usr/bin/env python3
"""MESH KAYIP ORANI — broadcast'te kaç çerçeve havada kayboluyor.

NEDEN VAR (4 Eylül 2026)
------------------------
QR görevi mesh'e **broadcast** çıkıyor ve broadcast'te 802.11 ACK yoktur
(`mesh_config.h::_mesh_gonder`): çerçeve havada kaybolursa ne gönderen ne
alan fark eder. Takipçiler formasyon komutunu almaz, YKİ'de QR görünmez,
hiçbir yerde hata satırı çıkmaz.

"Onaylı gönderim yazalım mı" sorusunun cevabı kayıp oranına bağlı:
kayıp binde birse ACK boşa emek, %10'sa kör tekrar zaten yetmez. Bu araç
o oranı ölçer.

NASIL ÖLÇÜYOR — paket formatına DOKUNMADAN
------------------------------------------
DURUM paketi her uçaktan **sabit periyotla** ve **broadcast** gidiyor,
yani QR ile aynı yolu ve aynı kaybı yaşıyor — ama düzenli olduğu için
sayılabiliyor. Her uçak `esp.log`'a 30 saniyede bir şunu yazıyor:

    KAYIP-OLCUM t=600s ben=d3 durum_periyot=0.50s
                durum_tx=1200 durum_rx=d1:1150,d2:1160 qr_tx=3 qr_rx=0

Kayıp = 1 − (ALICININ aldığı) / (GÖNDERENİN gönderdiği), yani iki ayrı
uçağın satırı gerekiyor. Bu yüzden tek uçakla ölçüm YAPILAMAZ.

⚠️ TOPLAM DEĞİL FARK kullanılıyor. Sayaçlar konteyner açılışında sıfırdan
başlıyor ve uçaklar farklı zamanlarda açılıyor; toplamları bölmek geç
açılan uçağı "kaybediyor" gibi gösterirdi. Bunun yerine son iki kaydın
FARKI alınıp saniyeye bölünüyor — pencere ortak olduğu için açılış
farkı düşüyor.

KULLANIM
    python3 deploy/yki/mesh_kayip.py                  # ağdaki hepsi
    python3 deploy/yki/mesh_kayip.py ylp00 ylp02      # seçilenler
    python3 deploy/yki/mesh_kayip.py --kayit 20       # daha uzun pencere
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
BUL = KOK / 'deploy' / 'yki' / 'drone_bul.sh'
UCAKLAR = ('ylp00', 'ylp01', 'ylp02')
LOG = '~/yelpence_ws/gunluk/son/esp.log'

_SATIR = re.compile(
    r'KAYIP-OLCUM\s+t=(?P<t>[\d.]+)s\s+ben=d(?P<ben>\d+).*?'
    r'durum_periyot=(?P<per>[\d.]+)s\s+durum_tx=(?P<tx>\d+)\s+'
    r'durum_rx=(?P<rx>\S+)\s+qr_tx=(?P<qtx>\d+)\s+qr_rx=(?P<qrx>\d+)'
    r'(?:\s+uart_tx_ok=(?P<utxok>\d+)\s+uart_tx_drop=(?P<utxdrop>\d+)'
    r'\s+uart_rx_ok=(?P<urxok>\d+)\s+crc_fail=(?P<crc>\d+))?')


def _rx_coz(alan: str) -> dict:
    """'d1:1150,d2:1160' -> {1: 1150, 2: 1160}. '-' bos demek."""
    if alan == '-':
        return {}
    cikti = {}
    for parca in alan.split(','):
        k, _, v = parca.partition(':')
        if k.startswith('d') and v.isdigit():
            cikti[int(k[1:])] = int(v)
    return cikti


def _oku(ad: str, kayit: int) -> list:
    """Uçaktan son `kayit` KAYIP-OLCUM satırını çeker ve çözer."""
    komut = f'grep KAYIP-OLCUM {LOG} 2>/dev/null | tail -{kayit}'
    try:
        c = subprocess.run([str(BUL), ad, komut],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f'  {ad}: ULASILAMADI ({e})')
        return []
    kayitlar = []
    for satir in c.stdout.splitlines():
        m = _SATIR.search(satir)
        if m:
            kayitlar.append({
                't': float(m['t']), 'ben': int(m['ben']),
                'periyot': float(m['per']), 'tx': int(m['tx']),
                'rx': _rx_coz(m['rx']),
                'qr_tx': int(m['qtx']), 'qr_rx': int(m['qrx']),
                # UART sayaclari eski satirlarda YOK -> None kalir
                'uart_tx_drop': (int(m['utxdrop'])
                                 if m['utxdrop'] is not None else None),
                'crc_fail': (int(m['crc'])
                             if m['crc'] is not None else None),
            })
    return kayitlar


def main() -> int:
    """Uçaklardan sayaçları çeker ve kayıp matrisini basar."""
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('ucaklar', nargs='*', default=list(UCAKLAR))
    a.add_argument('--kayit', type=int, default=10,
                   help='her uçaktan okunacak son satır sayısı (30 sn/satır)')
    n = a.parse_args()

    veri = {}
    for ad in (n.ucaklar or UCAKLAR):
        print(f'{ad} okunuyor...', file=sys.stderr)
        k = _oku(ad, n.kayit)
        if len(k) < 2:
            print(f'  {ad}: yeterli kayıt yok ({len(k)} satır) — '
                  f'köprü en az 60 sn koşmalı', file=sys.stderr)
            continue
        veri[k[-1]['ben']] = (ad, k[0], k[-1])

    if len(veri) < 2:
        print('\n🔴 EN AZ İKİ UÇAK GEREKİYOR. Kayıp = alıcının aldığı / '
              'gönderenin gönderdiği;\n   tek uçakta bölünecek bir şey yok.')
        return 1

    print('\n=== PENCERE ===')
    hiz = {}                      # gonderen -> DURUM/sn
    for did, (ad, ilk, son) in sorted(veri.items()):
        dt = son['t'] - ilk['t']
        if dt <= 0:
            print(f'  d{did} ({ad}): pencere 0 sn — atlandı')
            continue
        hiz[did] = (son['tx'] - ilk['tx']) / dt
        print(f'  d{did} ({ad}): {dt:.0f} sn · gönderdiği {son["tx"]-ilk["tx"]}'
              f' DURUM = {hiz[did]:.2f}/sn  (beklenen '
              f'{1.0/son["periyot"]:.2f}/sn)')
        # UART sayaclari: kaybin NEREDE oldugunu ayirir. Ikisi de 0 ise
        # kalan tek aciklama HAVA kaybidir.
        if son.get('uart_tx_drop') is not None:
            d_drop = son['uart_tx_drop'] - (ilk['uart_tx_drop'] or 0)
            d_crc = son['crc_fail'] - (ilk['crc_fail'] or 0)
            im = '🔴' if (d_drop or d_crc) else '🟢'
            print(f'       {im} UART: Pi->ESP düşen {d_drop} · '
                  f'ESP->Pi CRC hatası {d_crc}')

    print('\n=== KAYIP MATRİSİ  (gönderen -> alıcı) ===')
    kotu = []
    for alici, (ad_a, ilk_a, son_a) in sorted(veri.items()):
        for gonderen in sorted(hiz):
            if gonderen == alici:
                continue
            dt = son_a['t'] - ilk_a['t']
            alinan = son_a['rx'].get(gonderen, 0) - ilk_a['rx'].get(gonderen, 0)
            if dt <= 0 or hiz[gonderen] <= 0:
                continue
            alis_hizi = alinan / dt
            kayip = max(0.0, 1.0 - alis_hizi / hiz[gonderen])
            im = '🔴' if kayip > 0.05 else ('🟠' if kayip > 0.01 else '🟢')
            print(f'  {im} d{gonderen} -> d{alici} ({ad_a}): '
                  f'{alis_hizi:.2f}/sn alındı, {hiz[gonderen]:.2f}/sn '
                  f'gönderildi  ->  KAYIP %{kayip*100:.2f}')
            if kayip > 0.01:
                kotu.append(kayip)

    print('\n=== HÜKÜM ===')
    if not kotu:
        print('  🟢 Kayıp %1 altında. Kör tekrar (3x) fazlasıyla yeterli;')
        print('     ACK yazmak bu veriyle GEREKÇESİZ.')
    else:
        en = max(kotu)
        print(f'  En kötü çift: %{en*100:.2f} kayıp.')
        print(f'  Üç kör tekrarın hepsinin kaybolma olasılığı: '
              f'%{en**3*100:.4f}')
        if en > 0.05:
            print('  🔴 ACK GEREKLİ — kör tekrar bu oranda güvenilir değil.')
        else:
            print('  🟠 Sınırda. ACK faydalı ama acil değil.')
    print('\n  ⚠️ Bu ölçüm YERDE ve HAVADA farklı çıkar (mesafe, gövde,')
    print('     titreşim). Karar için UÇUŞTA ölçülmüş sayı kullan.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
