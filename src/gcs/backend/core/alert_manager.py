# Copyright 2026 Yelpence
"""Uyarı motoru."""

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from backend.core.log_store import LogStore
from backend.core.state_store import DroneState

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# GPS fix tipi -> operatorun okuyabilecegi ad. Uyari metninde "fix=2" yerine
# "2B konum" yaziyoruz; sahada sayiyi kimse akilda tutmuyor.
FIX_ADI = {
    0: "konum yok",
    1: "konum yok",
    2: "2B konum",
    3: "3B konum",
    4: "DGPS",
    5: "RTK (kayan)",
    6: "RTK (sabit)",
}


@dataclass
class Alert:
    """Tek bir aktif uyarının özeti."""

    drone_id: int
    severity: str
    code: str
    message: str
    timestamp: float


class AlertManager:
    """Sürü durumlarına göre uyarılar üreten motor."""

    GPS_GRACE_SEC = 15.0
    # PIL ESIKLERI — 2 Eylul 2026, gosterge 14.2 V = %0 / 16.8 V = %100
    # olarak yeniden olceklendikten sonra secildi (ucus_ayarlari.PIL_*).
    # Gerilim karsiliklari (4S, span 2.6 V):
    #     %30 -> 14.98 V   %25 -> 14.85 V   %16 -> 14.62 V   %10 -> 14.46 V
    #
    # 🔴 COKUS PAYI: LiPo yuk altinda duser. Olculdu (1 Eylul, ylp00):
    # dururken 15.29 V -> motorlar kalkista 14.72 V = 0.57 V, bu olcekte
    # %22 PUAN. Yani yari dolu bir pil motor calisinca %20 gorunur.
    # Esikler bu yuzden "sagduyulu" degerlerden DAHA ASAGI: yanlis alarm
    # alarm sistemine olan guveni oldurur ve gercek uyariyi da gorunmez
    # yapar. Gercek koruma zaten YUZDE degil GERILIM tabanli
    # (agent_context.healthy -> BATARYA_KRITIK_V = 13.8 V).
    BAT_LOW_ON = 25.0
    BAT_LOW_OFF = 30.0
    BAT_CRIT_ON = 10.0
    BAT_CRIT_OFF = 16.0
    # 🔴 DALGALANMA BASTIRMASI (2 Eylul 2026, operator): uyari bolgesine
    # girdikten sonra gerilim BU KADAR oynamadikca yeni bildirim YOK.
    # Sebep: eleme mesaj metnine bakiyor, metinde yuzde var; gerilim
    # dalgalandikca yuzde oynayip her tik yeni uyari uretiyordu.
    # Olcut GERILIM secildi cunku yuzde turetilmis ve gurultuyu buyutuyor
    # (bu olcekte 1 V ~ %38, yani 0.03 V'luk bir dalgalanma ~1 puan).
    #
    # 0.5 V, LOW bandinin genisliginden (14.85-14.46 = 0.39 V) BUYUK:
    # yani ayni bant icinde mesaj pratikte hic guncellenmez. Bu bilincli —
    # bant degisimi (LOW -> KRITIK) AYRI bir anahtar oldugu icin ANINDA
    # bildirilir, bastirma yalnizca ayni bandin icindeki gurultuyu keser.
    BAT_TITRESIM_V = 0.5
    EVENT_TTL_SEC = 10.0
    RTK_FIX_MIN = 5

    # SUSTURULABILIR UYARILAR — kanit videosu icin.
    #
    # Yonerge YKI ekraninin videoda gorunmesini SART kosuyor ve videoya
    # mudahale (kirpma/kesme) YASAK. Yani ekranda ne varsa hakem onu goruyor.
    # Ucus sirasinda "Baglanti koptu" ve "Dusuk batarya" kutulari surekli
    # aciIip kapaniyor (mesh %30 paket kaybi yasiyor, tek bir bosluk bile
    # link_timeout uretiyor) ve ekrani ariza gorunumune sokuyor.
    #
    # SILMIYORUZ, SUSTURUYORUZ: kod tarafinda uyari yine uretiliyor, yalniz
    # listeye konmuyor. config.yaml -> alerts.susturulan ile ac/kapa.
    #
    # DIKKAT: batarya uyarisini susturmak, pilin bittigini EKRANDAN
    # ogrenmeyecegin anlamina gelir. Kalan yuzdeyi drone kartlarindaki
    # BatteryGauge gostermeye devam ediyor — ucustan once oraya bak.
    SUSTURULABILIR = frozenset(
        {"link_timeout", "low_battery", "critical_battery", "weak_gps",
         "rtk_lost"}
    )

    # ✅ PIL DEGERLENDIRMESI ACILDI (2 Eylul 2026, operator karari)
    #
    # KOSUL GERCEKLESTI: INA226 uc ucakta da calisiyor ve olcum GERCEK.
    # 2 Eylul'de dogrulandi — MAVROS pili hala GECERSIZ (`voltage: 65.535`
    # = 0xFFFF sentinel, `percentage: -0.01`), yani PX4'ten pil okumasi
    # YOK; tek gercek kaynak INA226 ve AgentStatus'a dogru geciyor
    # (olculen: ylp00 14.688 V, ylp02 15.095 V).
    # Esikler yukarida BAT_* olarak yeniden secildi.
    #
    # Asagidaki gerekce KAPANDI ama ogretici oldugu icin duruyor:
    #
    # ~~NEDEN: su an sahada pil olcumu YOK.~~ ylp01'in guc olcum karti eksik,
    # digerlerinde de PX4 tezgahta sabit "12.6 V / %100" sentinel'i veriyor
    # (TUZAKLAR §1.20). Yani gelen sayi ne dolu ne bos — ANLAMSIZ.
    #
    # Bunu "sustur" ile cozmuyoruz: susturma, GERCEK bir sinyali ekrandan
    # gizlemek demek ve o sinyal deftere yine giriyor. Burada gizlenecek bir
    # sinyal yok; olmayan bir olcumden uyari uretmeyi tamamen birakiyoruz.
    # Aksi halde her arka uc acilisinda "Batarya kritik %0" defteri
    # kirletiyor ve LOG butonunu bos yere kirmizi yakiyordu — telemetri
    # gelmeden once durum sifir ve pilin GPS'teki gibi lutuf suresi yok.
    #
    # ACMAK ICIN: pil olcum kartlari takilinca config.yaml -> alerts.pil: true.
    # O gun esikler (BAT_*) ve lutuf suresi de bastan gozden gecirilmeli.
    def __init__(
        self,
        susturulan: Iterable[str] = (),
        gunluk: "LogStore | None" = None,
        pil: bool = False,
    ) -> None:
        self.susturulan = {
            k for k in susturulan if k in self.SUSTURULABILIR
        }
        # Kalici defter (bkz. core/log_store.py). Uyari motorunun davranisi
        # DEGISMIYOR — ayni kayitlar bir de deftere dusuyor. None ise hicbir
        # sey degismez, yani mevcut testler ve cagirilar etkilenmez.
        #
        # DIKKAT: susturulan uyarilar da deftere GIRER. Ekranda susturmak
        # "hakem videosunda ariza gorunumu olmasin" icindi; sonradan
        # incelerken o kayitlarin YOK olmasi bambaska bir sey olurdu.
        self._gunluk = gunluk
        self._pil = bool(pil)
        self._active: dict[tuple[int, str], Alert] = {}
        # Uyari basina SON BILDIRIM ANINDAKI olcum (pil icin gerilim).
        # Dalgalanma bastirmasi bunu kullaniyor — bkz. _set.
        self._son_olcum: dict[tuple[int, str], float] = {}
        self._events: list[Alert] = []
        self._events_lock = threading.Lock()
        self._started_at = time.time()
        self._had_rtk: set[int] = set()

    def push_event(
        self, drone_id: int, severity: str, code: str, message: str
    ) -> None:
        """Tek seferlik bir event yayınla."""
        with self._events_lock:
            self._events.append(
                Alert(
                    drone_id=drone_id,
                    severity=severity,
                    code=code,
                    message=message,
                    timestamp=time.time(),
                )
            )
        if self._gunluk is not None:
            self._gunluk.ekle(drone_id, severity, code, message)

    def _grace_active(self) -> bool:
        return (time.time() - self._started_at) < self.GPS_GRACE_SEC

    def _set(self, key: tuple[int, str], severity: str, message: str,
             olcum: float | None = None, olcum_esigi: float = 0.0) -> None:
        """Uyariyi kurar; DEGISMEDIYSE dokunmaz.

        🔴 `olcum` / `olcum_esigi` NEDEN VAR (2 Eylul 2026, operator):
        Eleme MESAJ METNINE bakiyor ve pil mesajinin icinde yuzde var
        ("Pil azaldi: %24"). Gerilim dalgalandikca yuzde oynuyor, metin
        degisiyor, eleme tutmuyor ve HER TIK yeni uyari + yeni defter
        kaydi uretiliyordu. Gosterge olcegi 14.2-16.8'e daraltilinca
        (1 V ~ %38) bu daha da kotulesti: 0.03 V'luk bir dalgalanma
        yuzdeyi ~1 puan oynatiyor.

        Cozum: ayni uyari SURERKEN mesaji ancak OLCUM yeterince
        degistiyse guncelle. Pil icin olcut GERILIM (yuzde degil) —
        yuzde zaten turetilmis ve gurultuyu buyutuyor.

        Args:
            key: (drone_id, kod).
            severity: SEVERITY_*.
            message: Gosterilecek metin.
            olcum (float | None): Gurultu olcutu (pil icin gerilim, V).
            olcum_esigi (float): Bu kadar degismeden mesaj GUNCELLENMEZ.
        """
        existing = self._active.get(key)
        if existing and existing.severity == severity:
            if existing.message == message:
                return
            # Mesaj degisti ama olcum yerinde sayiyorsa: DALGALANMA.
            if olcum is not None and olcum_esigi > 0.0:
                onceki = self._son_olcum.get(key)
                if (onceki is not None
                        and abs(olcum - onceki) < olcum_esigi):
                    return
        self._active[key] = Alert(
            drone_id=key[0],
            severity=severity,
            code=key[1],
            message=message,
            timestamp=time.time(),
        )
        # Yalniz DEGISIM aninda deftere dusuyoruz: yukaridaki erken donus,
        # ayni uyari surdugu surece buraya gelinmesini engelliyor. Aksi halde
        # "Baglanti koptu" her degerlendirme turunda (10 Hz) deftere yazilir
        # ve defter tek bir arizayla dolardi.
        if olcum is not None:
            self._son_olcum[key] = float(olcum)
        if self._gunluk is not None:
            self._gunluk.ekle(key[0], severity, key[1], message)

    def _clear(self, key: tuple[int, str]) -> None:
        self._active.pop(key, None)
        # Olcum hafizasi da gitmeli: uyari kapanip yeniden acilirsa ILK
        # bildirim bastirilmamali (esik yeni girise gore hesaplansin).
        self._son_olcum.pop(key, None)

    def evaluate(self, drones: Iterable[DroneState]) -> list[Alert]:
        """Durumu degerlendirip aktif uyarilari doner."""
        for d in drones:
            link_key = (d.drone_id, "link_timeout")
            bat_low_key = (d.drone_id, "low_battery")
            bat_crit_key = (d.drone_id, "critical_battery")
            gps_key = (d.drone_id, "weak_gps")
            rtk_key = (d.drone_id, "rtk_lost")

            if not d.connected:
                self._set(link_key, SEVERITY_CRITICAL, "Telemetri kesildi")
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
                self._clear(gps_key)
                self._clear(rtk_key)
                continue

            self._clear(link_key)

            if not self._pil:
                # Pil olcumu yok -> hic uyari uretme, eskisini de temizle.
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
            elif d.battery_percent <= self.BAT_CRIT_ON:
                self._set(
                    bat_crit_key,
                    SEVERITY_CRITICAL,
                    f"Pil kritik: %{d.battery_percent:.0f}",
                    olcum=d.battery_voltage,
                    olcum_esigi=self.BAT_TITRESIM_V,
                )
            elif d.battery_percent >= self.BAT_CRIT_OFF:
                self._clear(bat_crit_key)

            if self._pil and bat_crit_key not in self._active:
                if (
                    d.battery_percent <= self.BAT_LOW_ON
                    and d.battery_percent > 0
                ):
                    self._set(
                        bat_low_key,
                        SEVERITY_CRITICAL,
                        f"Pil azaldı: %{d.battery_percent:.0f}",
                        olcum=d.battery_voltage,
                        olcum_esigi=self.BAT_TITRESIM_V,
                    )
                elif d.battery_percent >= self.BAT_LOW_OFF:
                    self._clear(bat_low_key)
            else:
                self._clear(bat_low_key)

            if not self._grace_active():
                if d.gps_fix_type < 3:
                    msg = (
                        f"GPS zayıf: {FIX_ADI.get(d.gps_fix_type, d.gps_fix_type)}"
                        f", {d.gps_satellites} uydu"
                    )
                    self._set(gps_key, SEVERITY_WARNING, msg)
                else:
                    self._clear(gps_key)

            if d.gps_fix_type >= self.RTK_FIX_MIN:
                self._had_rtk.add(d.drone_id)
                self._clear(rtk_key)
            elif d.drone_id in self._had_rtk and not self._grace_active():
                self._set(
                    rtk_key,
                    SEVERITY_WARNING,
                    "RTK kilidi kayboldu — şu an "
                    f"{FIX_ADI.get(d.gps_fix_type, d.gps_fix_type)}",
                )

        now = time.time()
        with self._events_lock:
            self._events = [
                e
                for e in self._events
                if (now - e.timestamp) < self.EVENT_TTL_SEC
            ]
            current_events = list(self._events)

        order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
        hepsi = list(self._active.values()) + current_events
        if self.susturulan:
            hepsi = [a for a in hepsi if a.code not in self.susturulan]
        return sorted(
            hepsi,
            key=lambda a: (order.get(a.severity, 3), -a.timestamp),
        )
