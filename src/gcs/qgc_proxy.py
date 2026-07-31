#!/usr/bin/env python3
# =============================================================================
# !!! BU ARAC ARTIK KULLANILMIYOR — ONCE BUNU OKU !!!
#
# 31 Temmuz'da sysid cakismasini cozmek icin yazildi, sonra DAHA IYI bir cozum
# bulundu ve bu arac devre disi birakildi. Otomatik baslatilmiyor.
#
# NEDEN BIRAKILDI — iki sebep, ikisi de olculdu:
#
# 1) MAVROS'UN KARSI-TARAF KESFINI BOZUYOR. udp-b (broadcast) ucnoktasi bir
#    karsi taraf gorunce yayini birakip O ADRESE tekil gonderime geciyor
#    (mavros.log: "link[1001] detected remote address 255.190"). Proxy drone'a
#    paket yollayinca MAVROS proxy'ye kilitlendi; proxy durunca telemetri
#    TAMAMEN kesildi. 14550'de ylp00'dan sifir paket kaldi, duzeltmek icin
#    konteyner restarti gerekti.
#
# 2) TEK SOKET IKI AMACLA KULLANILIYORDU. QGC'ye gonderim ve drone'a gonderim
#    ayni soketten yapiliyordu; MAVROS'un tekil gonderimi o sokete dusunce
#    "QGC'den geldi" sanilip drone'lara GERI yollandi. Kendi kendini besleyen
#    dongu: QGC->drone sayaci 21296'ya firlarken drone->QGC 12'de dondu.
#
# DOGRU COZUM: her PX4'un MAV_SYS_ID'sini AYRI yap, QGC dogrudan 14550'ye
# baglansin. Cift yonluluk native calisir (parametre indirme, kalibrasyon,
# komut). Bizde: ylp00 -> 1, ylp01 -> 2, ylp02 -> 3.
#   ros2 param set /drone_N/mavros/param MAV_SYS_ID <N>
#   + FCU YENIDEN BASLAT (PX4 bu parametreyi ancak boyle uygular — ilk
#     denemede "yazilmadi" sanilmasinin sebebi buydu)
#   + /ws/tgt_system dosyasina <N> yaz, konteyneri yeniden baslat
#
# Bu dosya yalnizca sysid'leri AYIRMANIN mumkun olmadigi bir durumda, ve
# yukaridaki iki kusur giderilerek kullanilmali.
# =============================================================================
# QGC PROXY — iki drone'un MAVLink akisini QGC'nin AYRI ARAC olarak gormesi
# icin sysid'yi kaynak IP'ye gore yeniden yazar.
#
# NEDEN VAR (31 Temmuz'da olculdu)
# Kanit videosu yonergesi "ucus modunun ve yonelimlerin acikca gorundugu"
# QGroundControl ekranini sart kosuyor. MAVROS'a gcs_url verilince iki drone
# da MAVLink'i yayina basiyor — ama UDP 14550 dinlenince goruldu ki iki
# FARKLI IP'den gelen paketlerin HEPSI sysid=1:
#     10.158.16.134 -> 2041 paket, 10.158.16.189 -> 1837 paket, hepsi sysid 1
# QGC araclari sysid ile ayirir; ikisi de 1 olunca tek arac sanip iki ucagin
# telemetrisini birbirine karistirir (HUD iki ucak arasinda ziplar).
#
# Dogru cozum PX4'te MAV_SYS_ID'yi ayirmakti ama PX4 bu parametreyi hem
# MAVROS'tan hem dogrudan MAVLink PARAM_SET'ten REDDETTI. Ucus oncesi FCU
# ile ugrasmak yerine duzeltmeyi tamamen YERE aliyoruz: bu proxy paketi
# cozup srcSystem'i degistirerek yeniden paketliyor (CRC dahil).
#
# Ucaga hicbir sey yapmaz; calismasa bile ucus etkilenmez.
#
# AKIS — CIFT YONLU
#   drone MAVROS --(udp-b broadcast :14550)--> proxy --(:14551)--> QGC
#   QGC        --(cevap)--------------------> proxy --(:14555)--> ilgili drone
#
# DONUS YOLU SART: ilk surum tek yonluydu ve QGC'de PARAMETRE INDIRME YARIDA
# KALIYORDU. Sebep: QGC parametreleri almak icin araca PARAM_REQUEST_LIST
# GONDERMEK zorunda; tek yonlu proxy'de o istek hicbir zaman ulasmiyor,
# QGC de sonsuza kadar bekliyor (yesil ilerleme cubugu takiliyor).
# Ayni sebeple komut/kalibrasyon da calismazdi.
#
# Donuste sysid TERSINE cevrilir: QGC 'sysid 2'ye yaziyorum' der, biz onu
# ylp01'in IP'sine yollar ve target_system'i FCU'nun gercek kimligine (1)
# geri yazariz.
#
# MAVROS TUZAGI (olculdu): udp-b:// semasinda '@PORT' kismi YOK SAYILIYOR.
# gcs_url'e 'udp-b://:14555@14560' yazilip MAVROS "GCS URL: ...@14560" diye
# loglasa ve endpoint'i "opened successfully" dese bile yayin yine 14550'ye
# gidiyor. Uc portu ayni anda dinleyerek dogrulandi: 14560'a sifir paket,
# 14550'ye iki drone'dan 4393 paket. Bu yuzden dinleme portu 14550 SABIT
# kabul edilir ve ayrimi QGC tarafinda yapariz.
#
# QGC AYARI (bir kerelik): Application Settings -> Comm Links ->
#   Add -> Type: UDP, Port: 14551 -> OK -> Connect.
#   Ayrica "AutoConnect to UDP" KAPATILMALI, yoksa QGC 14550'yi kapmaya
#   calisir ve proxy ile yarisir.
#
# Kullanim:
#     ~/gcs-venv/bin/python qgc_proxy.py
# =============================================================================

import argparse
import select
import socket
import sys
import time

try:
    from pymavlink.dialects.v20 import common as mav
except ImportError:
    sys.exit("pymavlink yok. Deneyin: ~/gcs-venv/bin/python qgc_proxy.py")

# Kaynak IP -> QGC'de gorunecek sysid. docs/cihazlar.md ile ayni eslesme.
IP_SYSID = {
    "10.158.16.134": 1,   # ylp00
    "10.158.16.211": 2,   # ylp01
    "10.158.16.189": 3,   # ylp02
}


def main() -> int:
    ap = argparse.ArgumentParser(description="QGC icin sysid yeniden yazan MAVLink proxy")
    ap.add_argument("--dinle", type=int, default=14550,
                    help="drone'larin yayin yaptigi port (MAVROS udp-b hep 14550)")
    ap.add_argument("--qgc", type=int, default=14551,
                    help="QGC'de elle eklenecek UDP link portu")
    ap.add_argument("--qgc-host", default="127.0.0.1")
    a = ap.parse_args()

    giris = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    giris.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        giris.bind(("", a.dinle))
    except OSError as e:
        return f"UDP {a.dinle} baglanamadi: {e}"
    giris.setblocking(False)

    # QGC tarafi TEK soket: hem QGC'ye yolluyoruz hem QGC'nin cevaplari
    # buraya donuyor (QGC gelen paketin kaynagina cevap verir).
    cikis = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cikis.setblocking(False)

    sysid_ip = {v: k for k, v in IP_SYSID.items()}

    cozucu = mav.MAVLink(None)
    cozucu.robust_parsing = True
    qcozucu = mav.MAVLink(None)
    qcozucu.robust_parsing = True
    qpaketleyiciler: dict = {}
    # Her (yeni sysid, component) icin ayri paketleyici: pack() srcSystem'i
    # MAVLink nesnesinden alir, o yuzden nesneyi yeniden kullanamayiz.
    paketleyiciler: dict = {}

    print(f"QGC proxy: :{a.dinle} -> {a.qgc_host}:{a.qgc}")
    print("IP -> sysid: " + ", ".join(f"{k}->{v}" for k, v in IP_SYSID.items()))
    print("Ctrl-C ile cik\n")

    sayac: dict = {}
    bilinmeyen: set = set()
    son_rapor = time.time()

    geri = 0
    while True:
        try:
            hazir, _, _ = select.select([giris, cikis], [], [], 1.0)
        except KeyboardInterrupt:
            print("\nkapatiliyor")
            return 0

        # --- QGC -> drone (donus yolu) --------------------------------------
        if cikis in hazir:
            try:
                qveri, _ = cikis.recvfrom(4096)
            except (BlockingIOError, OSError):
                qveri = None
            if qveri:
                try:
                    qmesajlar = qcozucu.parse_buffer(qveri) or []
                except Exception:
                    qmesajlar = []
                for qm in qmesajlar:
                    hedef_sys = getattr(qm, "target_system", 0)
                    hedefler = ([sysid_ip[hedef_sys]] if hedef_sys in sysid_ip
                                else list(IP_SYSID))       # 0 = yayin -> hepsi
                    # FCU'lar gercekte sysid 1; QGC'nin gordugu numarayi
                    # geri cevir, yoksa arac komutu kendisine ait saymaz.
                    if hasattr(qm, "target_system"):
                        qm.target_system = 1
                    anahtar = (qm.get_srcSystem(), qm.get_srcComponent())
                    pq = qpaketleyiciler.get(anahtar)
                    if pq is None:
                        pq = mav.MAVLink(None, srcSystem=anahtar[0], srcComponent=anahtar[1])
                        qpaketleyiciler[anahtar] = pq
                    try:
                        ham = qm.pack(pq)
                    except Exception:
                        continue
                    for hip in hedefler:
                        try:
                            cikis.sendto(ham, (hip, 14555))
                            geri += 1
                        except Exception:
                            pass

        # --- drone -> QGC ---------------------------------------------------
        veri = None
        if giris in hazir:
            try:
                veri, adres = giris.recvfrom(4096)
            except (BlockingIOError, OSError):
                veri = None

        if veri:
            yeni_sysid = IP_SYSID.get(adres[0])
            if yeni_sysid is None:
                # Tablodaki olmayan bir kaynak — sessizce atlamak yerine bir
                # kez bildir. Sahada yeni bir IP alan drone'u boyle yakalariz.
                if adres[0] not in bilinmeyen:
                    bilinmeyen.add(adres[0])
                    print(f"  UYARI: tabloda olmayan kaynak {adres[0]} — atlaniyor")
            else:
                try:
                    mesajlar = cozucu.parse_buffer(veri) or []
                except Exception:
                    mesajlar = []
                for m in mesajlar:
                    comp = m.get_srcComponent()
                    anahtar = (yeni_sysid, comp)
                    p = paketleyiciler.get(anahtar)
                    if p is None:
                        p = mav.MAVLink(None, srcSystem=yeni_sysid, srcComponent=comp)
                        paketleyiciler[anahtar] = p
                    try:
                        cikis.sendto(m.pack(p), (a.qgc_host, a.qgc))
                    except Exception:
                        continue
                    sayac[yeni_sysid] = sayac.get(yeni_sysid, 0) + 1

        if time.time() - son_rapor >= 5.0:
            if sayac:
                print("  " + "   ".join(f"sysid {k}: {v} msg" for k, v in sorted(sayac.items()))
                      + f"   | QGC->drone: {geri}")
            else:
                print("  (veri yok — drone'lar yayin yapiyor mu? gcs_url portu dogru mu?)")
            son_rapor = time.time()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nkapatiliyor")
