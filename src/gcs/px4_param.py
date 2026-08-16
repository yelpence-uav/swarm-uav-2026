#!/usr/bin/env python3
# =============================================================================
# PX4 PARAMETRE OKUYUCU / KARSILASTIRICI
#
# NEDEN VAR: 2 Agustos'ta d1'in MPC_XY_VEL_MAX'i 12.0, d3'unki 4.0 cikti.
# Frenleme mesafesi ~24 m, oysa carpisma payi 3.07 m. Bu UCUSTA anlasildi;
# ucmadan yakalanmasi gerekiyordu ve yakalayacak arac yoktu.
#
# NEDEN 'ros2 param get' YETMIYOR (14 Agustos'ta olculdu):
#   * '/drone_N/mavros/param/get' diye bir servis YOK. MAVROS 2 PX4
#     parametrelerini YEREL ROS 2 parametresi olarak sunuyor; eski
#     mavros_msgs/srv/ParamGet yolu bu surumde bulunmuyor. Onu cagirmak
#     "waiting for service to become available" ile takilir — ilk teshiste
#     tam bu tuzaga dusuldu ve "parametre okunamiyor" sanildi.
#   * Dogrusu 'ros2 param get /drone_N/mavros/param <AD>'. AMA her cagri
#     YENI bir dugum acip DDS kesfi yapiyor ve dugumde 1007 parametre var;
#     ard arda cagrilarin yarisi zaman asimina dusuyor (olculdu: 4 istekten
#     2'si "Wait for service timed out").
#
# BU BETIGIN FARKI: TEK dugum acar, TEK kesif yapar ve get_parameters
# servisine TOPLU istek atar (rcl_interfaces/srv/GetParameters 'names' alani
# bir LISTE alir). 1007 parametre tek seferde, saniyeler icinde gelir.
#
# NEREDE KOSAR: DRONE UZERINDE, konteynerin ICINDE. YKI'den kosmaz cunku
# baslat.sh ROS_LOCALHOST_ONLY=1 ile DDS'i loopback'e kapatiyor — YKI drone'un
# ROS grafigini GORMEZ. Calistirmak icin:
#
#   ./deploy/yki/drone_bul.sh ylp00 \
#       'docker exec -i drone1 python3 -' < src/gcs/px4_param.py
#
# ya da iki ucagi karsilastirmak icin: deploy/yki/param_karsilastir.sh
# =============================================================================

import argparse
import json
import os
import sys

import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters, ListParameters, SetParameters
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue

# UCUSU DOGRUDAN ETKILEYEN PARAMETRELER.
#
# --onemli ile yalniz bunlar okunur. Tam dokum uzun; sahada hizli bakmak
# gerektiginde liste bu. Degerler ve gerekceler docs/RPI_ESITLEME.md §5'te.
ONEMLI = [
    'MPC_XY_VEL_MAX',      # kacinmanin kacis payi buradan gelir
    'MPC_VEL_MANUAL',      # kumandayla POSCTL hizi (14 Agu: 4 / 2 ayrisikti)
    'MPC_Z_VEL_MAX_UP',
    'MPC_Z_VEL_MAX_DN',
    'MPC_TKO_SPEED',
    'MPC_LAND_SPEED',
    'MPC_ACC_HOR',
    'MPC_XY_P',            # yurutucu hesabi buna dayaniyor
    'MPC_TILTMAX_AIR',
    'MC_YAWRATE_MAX',
    'MPC_YAWRAUTO_MAX',
    'COM_OBL_RC_ACT',      # offboard kaybinda motor KESILMEZ (0 = POSCTL)
    'COM_RCL_EXCEPT',
    'BAT1_SOURCE',         # regulatorden besleme -> -1 (disabled)
    'MAV_SYS_ID',          # ucaga OZGU, esit OLMAMALI
    'EKF2_HGT_REF',
    'EKF2_GPS_CTRL',
]

# Ucaga OZGU olmasi GEREKEN parametreler — karsilastirmada fark cikmasi
# NORMAL, uyari verilmez. Tersi tehlikeli: ikisi de ayni olursa QGC iki ucagi
# TEK arac sanar (30 Tem'de yasandi).
UCAGA_OZGU = {'MAV_SYS_ID'}


def _deger(pv):
    """ParameterValue -> python degeri."""
    t = pv.type
    if t == ParameterType.PARAMETER_BOOL:
        return pv.bool_value
    if t == ParameterType.PARAMETER_INTEGER:
        return pv.integer_value
    if t == ParameterType.PARAMETER_DOUBLE:
        return pv.double_value
    if t == ParameterType.PARAMETER_STRING:
        return pv.string_value
    if t == ParameterType.PARAMETER_NOT_SET:
        return None
    return str(pv)


class ParamOkuyucu(Node):
    def __init__(self, ns):
        super().__init__('yelpence_param_okuyucu')
        self._ns = ns
        self._list = self.create_client(ListParameters, f'{ns}/list_parameters')
        self._get = self.create_client(GetParameters, f'{ns}/get_parameters')

    def _bekle(self, cli, sn=15.0):
        if not cli.wait_for_service(timeout_sec=sn):
            raise RuntimeError(
                f'servis yok: {cli.srv_name}\n'
                f'  MAVROS ayakta mi?  ros2 node list | grep mavros/param')
        return True

    def adlar(self, zaman_asimi=40.0):
        """Butun parametre adlarini doner."""
        self._bekle(self._list)
        istek = ListParameters.Request()
        istek.depth = 0
        gelecek = self._list.call_async(istek)
        rclpy.spin_until_future_complete(self, gelecek, timeout_sec=zaman_asimi)
        if not gelecek.done():
            raise RuntimeError(
                f'list_parameters {zaman_asimi:.0f} sn icinde cevap vermedi')
        return sorted(gelecek.result().result.names)

    def yaz(self, degerler: dict, zaman_asimi=30.0):
        """Parametreleri TEK istekte yazar.

        'ros2 param set' her cagride yeni dugum acip DDS kesfi yapiyor ve
        dugumde 1007 parametre oldugu icin ard arda cagrilarin yarisi zaman
        asimina dusuyor (olculdu: 5 istekten 3'u). Burada tek dugum, tek
        istek.

        TIP ONEMLI: PX4 parametreleri INT32 ya da FLOAT32. Yanlis tiple
        yazmak reddedilir. Bu yuzden once MEVCUT deger okunup tipi
        ogreniliyor, sonra ayni tiple yaziliyor.
        """
        self._bekle(self._get)
        mevcut = self.oku(list(degerler))

        istek = SetParameters.Request()
        for ad, yeni in degerler.items():
            eski = mevcut.get(ad)
            if eski is None:
                self.get_logger().warn(f'{ad}: okunamadi, yazilmiyor')
                continue
            pv = ParameterValue()
            if isinstance(eski, bool):
                pv.type = ParameterType.PARAMETER_BOOL
                pv.bool_value = bool(yeni)
            elif isinstance(eski, int):
                pv.type = ParameterType.PARAMETER_INTEGER
                pv.integer_value = int(round(float(yeni)))
            else:
                pv.type = ParameterType.PARAMETER_DOUBLE
                pv.double_value = float(yeni)
            istek.parameters.append(Parameter(name=ad, value=pv))

        if not istek.parameters:
            return {}
        set_cli = self.create_client(SetParameters, f'{self._ns}/set_parameters')
        self._bekle(set_cli)
        gelecek = set_cli.call_async(istek)
        rclpy.spin_until_future_complete(self, gelecek, timeout_sec=zaman_asimi)
        if not gelecek.done():
            raise RuntimeError(f'set_parameters {zaman_asimi:.0f} sn icinde cevap vermedi')
        sonuc = {}
        for par, cev in zip(istek.parameters, gelecek.result().results):
            sonuc[par.name] = (cev.successful, cev.reason)
        return sonuc

    def oku(self, adlar, kume=60, zaman_asimi=25.0):
        """Adlari KUMELER halinde okur.

        Tek istekte 1007 ad gondermek servisi zorluyor; 60'lik kumeler
        guvenli ve hizli (17 tur, birkac saniye).
        """
        self._bekle(self._get)
        sonuc = {}
        for i in range(0, len(adlar), kume):
            parca = adlar[i:i + kume]
            istek = GetParameters.Request()
            istek.names = parca
            gelecek = self._get.call_async(istek)
            rclpy.spin_until_future_complete(self, gelecek,
                                             timeout_sec=zaman_asimi)
            if not gelecek.done():
                for ad in parca:
                    sonuc[ad] = None      # okunamadi, sessizce atlama
                continue
            for ad, pv in zip(parca, gelecek.result().values):
                sonuc[ad] = _deger(pv)
        return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(
        description='PX4 parametrelerini MAVROS uzerinden okur '
                    '(drone uzerinde, konteyner icinde kosar)')
    ap.add_argument('--ns', default=None,
                    help='param dugumu (varsayilan: AGENT_ID ortamindan)')
    ap.add_argument('--onemli', action='store_true',
                    help='yalniz ucusu etkileyen parametreler')
    ap.add_argument('--al', nargs='+', metavar='AD',
                    help='belirli parametreleri oku')
    ap.add_argument('--json', action='store_true', help='JSON bas')
    ap.add_argument('--yaz', nargs='+', metavar='AD=DEGER',
                    help='parametre yaz, or: --yaz MPC_XY_VEL_MAX=5.0')
    a = ap.parse_args()

    ns = a.ns
    if ns is None:
        aid = os.environ.get('AGENT_ID', '1')
        ns = f'/drone_{aid}/mavros/param'

    rclpy.init()
    dugum = ParamOkuyucu(ns)

    if a.yaz:
        try:
            istenen = {}
            for parca in a.yaz:
                ad, _, deger = parca.partition('=')
                istenen[ad.strip()] = float(deger)
            sonuc = dugum.yaz(istenen)
        except Exception as exc:                  # noqa: BLE001
            print(f'HATA: {exc}', file=sys.stderr)
            dugum.destroy_node(); rclpy.shutdown()
            return 1
        kotu = 0
        for ad in sorted(sonuc):
            ok, sebep = sonuc[ad]
            print(f'{ad}: {"YAZILDI" if ok else "BASARISIZ " + sebep}')
            kotu += 0 if ok else 1
        dugum.destroy_node(); rclpy.shutdown()
        return 1 if kotu else 0

    try:
        if a.al:
            istenen = list(a.al)
        elif a.onemli:
            istenen = list(ONEMLI)
        else:
            istenen = dugum.adlar()
        degerler = dugum.oku(istenen)
    except Exception as exc:                      # noqa: BLE001
        print(f'HATA: {exc}', file=sys.stderr)
        return 1
    finally:
        dugum.destroy_node()
        rclpy.shutdown()

    if a.json:
        print(json.dumps({'ns': ns, 'parametreler': degerler},
                         ensure_ascii=False, sort_keys=True))
        return 0

    okunamayan = [k for k, v in degerler.items() if v is None]
    for ad in sorted(degerler):
        d = degerler[ad]
        print(f'{ad}={"?" if d is None else d}')
    if okunamayan:
        print(f'# okunamayan {len(okunamayan)}: {", ".join(okunamayan[:8])}'
              + (' ...' if len(okunamayan) > 8 else ''), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
