# Copyright 2026 Yelpence
"""Merkez hizi ileri-beslemesi: SABIT PENCERELI turev (saf Python).

5 Eylul 2026, sahada olculdu. Operator: "ileri geri sag sol hareket
yaptim, hareketler gayet iyiydi ve akiciydi ama iki ucak da oldugu yerde
az sekilde bir saga bir sola yatti. Kucuk bir yatis ama sik yasandigi
icin salinim olarak gorunuyor."

KOK NEDEN — tick basina sonlu fark, PAYLA PAYDAYI FARKLI ARALIKTAN
aliyordu:

    v_ff = a * (x - onceki_x) / dt + (1 - a) * v_ff

`dt` yayin tick'inin suresi (20 Hz -> 0.05 sn); pay ise "hedef ne kadar
ilerledi". Hedef merkez ~10 Hz'de guncelleniyor, bu dongu 20 Hz'de
donuyor. formation_node'un KENDI CIKTISINDAN olculen adim dizisi:

    0.10  0.00  0.10  0.00  0.10  0.00  0.09  0.02  0.09  0.00 ...

Bir tick 0.10 m, sonraki 0.00 — ama payda ikisinde de 0.05 sn. Yani
v_ff donusumlu olarak 0.10/0.05 = 2.0 m/s ve 0.0 okuyor. Gercek merkez
hizi 1.0 m/s: ileri-besleme sirayla IKI KATINI ve SIFIRI soyluyor.

0.10 m sabiti tesadufi degil: target_ramp_mps=0 -> rampa hizi = max_speed
= 2.0 m/s -> adim tavani 2.0 * 0.05 = 0.10 m. Olculen adimla birebir.

NEDEN YALPA, neden hizlanip yavaslama degil: hedefin x ve y bilesenleri
FARKLI tick'lerde basamak atiyor (olculen: t=337 ms'de x, t=389 ms'de y).
Iki dalgalanma ters fazda olunca hiz vektorunun BUYUKLUGU degil YONU
savruluyor. Sahada olculen: yon genligi +-17 derece. PX4 hiz komutunu
dogrudan egime cevirdigi icin komut roll'u tepe-tepe 9.3 derece, gercek
roll 3.4 derece.

NEDEN SADECE HAREKETTE: asili dururken merkez kimildamaz, pay sifirdir,
v_ff soner. Olculen — asili: setpoint dalgasi 0.003 m, komut roll dalgasi
0.31 derece. Harekette: 0.048 m ve 2.33 derece.

ZINCIRIN GERISI TEMIZDI. Komut hizi uc terim (v_svt + v_sonum + v_ff) ve
sahada yapilan ayristirma su aci genliklerini verdi:

    SVT terimi (-0.8 * hata)      8.6 derece
    SONUM terimi (-0.35 * hiz)    2.4 derece
    GIDEN KOMUT                  53.6 derece

Sapmanin tamami v_ff'ten geliyor.

COZUM — sabit pencereli turev:

    v_ff = (x(t) - x(t - W)) / W

Pay ile payda YAPISI GEREGI ayni araligi olcer; hedefin varis temposu
ile yayin temposu uyusmasa da bozulmaz. Hedef durunca pencere bosalir ve
v_ff kendiliginden sifira iner — yani `vff_hold_s` bayatlik kapisi
anlamini korur, onun yerine gecmez.

LPF NEDEN DURUYOR: pencerenin en eski ornegi disari dustugunde aralik bir
miktar degisir ve bu kucuk bir basamak birakir. Hafif LPF onu siliyor.
Pencere ana filtre, LPF sinir temizleyici.

pencere_s = 0.0 -> ESKI davranis (tick basina sonlu fark). Geri donus
tek deger; kusurun geri alinmasi tek parametre.
"""

from __future__ import annotations

from collections import deque

# Kacak dongu emniyeti: zaman ilerlemezse gecmis buyumesin. 20 Hz'de
# 400 ornek 20 saniye demek — islevsel sinir degil, sadece tavan.
_GECMIS_TAVANI = 400


class MerkezHiziKestirici:
    """Merkez (rampalanmis hedef) hizini kestirir.

    Kullanim her yayin tick'inde:  vx, vy, vz = kestirici.guncelle(t, x, y, z)
    """

    def __init__(self, pencere_s: float = 0.25,
                 lpf_alpha: float = 0.3) -> None:
        self.pencere_s = float(pencere_s)
        self.lpf_alpha = float(lpf_alpha)
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self._gecmis: deque[tuple[float, float, float, float]] = deque()
        self._onceki: tuple[float, float, float, float] | None = None

    def sifirla(self) -> None:
        """Bayatlik kapisi icin: kestirimi ve gecmisi tumuyle bosaltir.

        Gecmis de silinir — komut akisi kesildiginde eski ornekler artik
        merkezin hareketini temsil etmiyor.
        """
        self.vx = self.vy = self.vz = 0.0
        self._gecmis.clear()
        self._onceki = None

    def guncelle(self, t: float, x: float, y: float,
                 z: float) -> tuple[float, float, float]:
        """Bir ornegi isler ve guncel (vx, vy, vz) doner."""
        if self.pencere_s > 0.0:
            return self._pencereli(t, x, y, z)
        return self._tick_basina(t, x, y, z)

    # --- yeni yol -------------------------------------------------------
    def _pencereli(self, t, x, y, z):
        self._gecmis.append((t, x, y, z))
        while len(self._gecmis) > _GECMIS_TAVANI:
            self._gecmis.popleft()
        # Pencerenin DISINA dusen en eski ornegi tut, bir oncekini at:
        # boylece aralik gecmis yeterliyse her zaman >= pencere_s olur.
        kes = t - self.pencere_s
        while len(self._gecmis) >= 2 and self._gecmis[1][0] <= kes:
            self._gecmis.popleft()
        t0, x0, y0, z0 = self._gecmis[0]
        aralik = t - t0
        if aralik > 1e-3:
            a = self.lpf_alpha
            self.vx = a * (x - x0) / aralik + (1.0 - a) * self.vx
            self.vy = a * (y - y0) / aralik + (1.0 - a) * self.vy
            self.vz = a * (z - z0) / aralik + (1.0 - a) * self.vz
        return self.vx, self.vy, self.vz

    # --- eski yol (pencere_s = 0.0) -------------------------------------
    def _tick_basina(self, t, x, y, z):
        """Dagitilmis kodun birebir davranisi.

        `dt` orada yayin dongusunun suresiydi; burada t - t_onceki ile
        ayni sey hesaplaniyor.
        """
        if self._onceki is None:
            self._onceki = (t, x, y, z)
            return self.vx, self.vy, self.vz
        dt = t - self._onceki[0]
        if dt > 1e-3:
            a = self.lpf_alpha
            self.vx = a * (x - self._onceki[1]) / dt + (1.0 - a) * self.vx
            self.vy = a * (y - self._onceki[2]) / dt + (1.0 - a) * self.vy
            self.vz = a * (z - self._onceki[3]) / dt + (1.0 - a) * self.vz
            self._onceki = (t, x, y, z)
        return self.vx, self.vy, self.vz
