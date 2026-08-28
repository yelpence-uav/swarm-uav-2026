# Copyright 2026 Yelpence
"""Görev koşucusunu (gorev_kanit_ucus.py) YKİ arayüzünden başlat/durdur.

NEDEN AYRI BIR YOL: /api/mission/trigger ROS'taki TriggerMission servisine
gider, yani surunun KENDI durum makinesini tetikler. Kanit ucusu koreografisi
orada degil; YKI'de kosan bir betikte (gorev_kanit_ucus.py). Sahada onu her
seferinde ayri bir terminalden elle baslatmak gerekiyordu — kanit videosu
cekilirken laptop basinda komut yazmak hem yavas hem videoda kotu duruyor.

TASARIM KARARLARI (uctaki bir seyi calistiriyoruz, dikkatli olmak gerekiyor):

  * TEK GOREV. Ayni anda ikinci bir kosu baslatilamaz; canli ucusta iki ayri
    surecin ayni drone'lara setpoint gondermesi cakisma demektir.

  * DURDURMA = SIGINT, kill DEGIL. Betik SIGINT'i yakalayip indir() cagiriyor
    (bkz. gorev_kanit_ucus.py:_kesildi). SIGKILL gonderirsek ucaklar havada
    son setpoint'te asili kalir ve kimse komut gondermez. Bu yuzden once
    SIGINT, ancak cevap vermezse SIGKILL.

  * KURU ve CANLI AYRI ISTEK. Ayni endpoint'e bayrak gecirmek, arayuzde yanlis
    dugmeye basmayi tek karakterlik bir hataya indirger.

  * CIKTI HALKA TAMPONDA. Betik binlerce satir basiyor (her rotasyon dilimi);
    hepsini bellekte tutmanin anlami yok, son N satir yeter.
"""

import os
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["kosucu"])

# backend/api/kosucu.py -> backend/api -> backend -> gcs
_GCS = Path(__file__).resolve().parent.parent.parent
_BETIK = _GCS / "gorev_kanit_ucus.py"

_SATIR_TAMPON = 400
_DURDURMA_ZAMAN_ASIMI_S = 12.0


class _Kosu:
    """Tek bir görev koşusunun durumu."""

    def __init__(self) -> None:
        self.kilit = threading.Lock()
        self.surec: subprocess.Popen | None = None
        self.satirlar: deque[str] = deque(maxlen=_SATIR_TAMPON)
        self.komut: list[str] = []
        self.kuru: bool = True
        self.baslangic: float = 0.0
        self.bitis: float = 0.0
        self.cikis: int | None = None
        self.durduruluyor: bool = False

    def calisiyor(self) -> bool:
        return self.surec is not None and self.surec.poll() is None

    def _oku(self, surec: subprocess.Popen) -> None:
        """stdout'u satır satır tampona al. Ayrı iş parçacığı."""
        assert surec.stdout is not None
        for ham in surec.stdout:
            self.satirlar.append(ham.rstrip("\n"))
        surec.wait()
        with self.kilit:
            if self.surec is surec:
                self.bitis = time.time()
                self.cikis = surec.returncode
                self.durduruluyor = False

    def baslat(self, argv: list[str], kuru: bool) -> None:
        with self.kilit:
            if self.calisiyor():
                raise HTTPException(
                    status_code=409,
                    detail="Zaten çalışan bir görev var. Önce durdur.",
                )
            self.satirlar.clear()
            self.komut = argv
            self.kuru = kuru
            self.baslangic = time.time()
            self.bitis = 0.0
            self.cikis = None
            self.durduruluyor = False
            # start_new_session: SIGINT'i SADECE betige gonderelim; aksi halde
            # uvicorn'un kendi surec grubuna da gider ve YKI kapanir.
            self.surec = subprocess.Popen(
                argv,
                cwd=str(_GCS.parent.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        threading.Thread(
            target=self._oku, args=(self.surec,), daemon=True
        ).start()

    def durdur(self) -> str:
        with self.kilit:
            surec = self.surec
            if surec is None or surec.poll() is not None:
                raise HTTPException(
                    status_code=409, detail="Çalışan görev yok."
                )
            self.durduruluyor = True
        # SIGINT -> betik indir() calistirir (ucaklar LAND'e gecer).
        os.killpg(os.getpgid(surec.pid), signal.SIGINT)
        t0 = time.time()
        while time.time() - t0 < _DURDURMA_ZAMAN_ASIMI_S:
            if surec.poll() is not None:
                return "SIGINT ile durduruldu (iniş komutu gönderildi)"
            time.sleep(0.2)
        os.killpg(os.getpgid(surec.pid), signal.SIGKILL)
        return (
            "SIGINT'e yanıt vermedi, SIGKILL gönderildi — "
            "UÇAKLAR SON SETPOINT'TE ASILI KALMIŞ OLABİLİR, kumandaya geç"
        )


_KOSU = _Kosu()


class BaslatBody(BaseModel):
    """Görev koşusu istek gövdesi."""

    # VARSAYILANLAR SAHADAKI FILOYU YANSITMALI. Panel yalnizca {kuru}
    # gonderiyor, geri kalani bu varsayilanlardan geliyor — yani "GOREV
    # BASLAT" dugmesinin gercekte hangi ucaklari ucuracagi BURADA yaziyor.
    #
    # 2 AGUSTOS: "2,3" / lider 2 idi. ylp01 (agent 2) o gun dustu; bu
    # degerlerle dugmeye basmak goreve "Telemetride yok: drone [2]" dedirtip
    # cikartiyordu — sahada dugme calismiyor gibi gorunuyordu, oysa filo
    # degismisti. Filo her degistiginde BURASI guncellenir.
    senaryo: str = Field("saha", description="gorev_kanit_ucus.py --senaryo")
    dronelar: str | None = Field(
        None, description="virgülle, ör. '1,3'. BOŞSA senaryoya göre "
        "varsayılan (_coz_dronelar) uygulanır — tek kaynak burası kalsın "
        "diye panel bu alanı GÖNDERMİYOR.")
    lider: int = Field(3, description="lider drone id")
    kuru: bool = Field(True, description="True ise KOMUT GÖNDERİLMEZ")
    kacinma: bool = Field(False, description="çarpışma kaçınması açık mı")
    harita: bool = Field(True, description="uydu haritası üret")


# Filo varsayilani (yukaridaki 2 Agustos dersinin tek kaynagi).
_FILO_DRONELAR = "1,3"
# ⚠️ GECICI — formasyon_gecis senaryosu UC ucak ister (2 ucakta reshape
# anlamini yitirir) ve sekansi ucaktaki formasyon_sekans dugumu kosar.
# ylp02'nin PX4 guc soketi P0'i kapanmadan bu senaryo CANLI baslatilmamali
# (YAPILACAKLAR.md) — betik on kontrolu yine de tutar ama karar operatorun.
_SENARYO_DRONELAR = {"formasyon_gecis": "1,2,3"}


def _coz_dronelar(b: BaslatBody) -> str:
    if b.dronelar:
        return b.dronelar
    return _SENARYO_DRONELAR.get(b.senaryo, _FILO_DRONELAR)


def _argv(b: BaslatBody) -> list[str]:
    if not _BETIK.exists():
        raise HTTPException(
            status_code=500, detail=f"Betik bulunamadı: {_BETIK}"
        )
    argv = [
        "python3", "-u", str(_BETIK),
        "--senaryo", b.senaryo,
        "--dronelar", _coz_dronelar(b),
        "--lider", str(b.lider),
    ]
    if b.kuru:
        argv.append("--kuru")
    if b.kacinma:
        argv.append("--kacinma")
    if b.harita:
        argv += ["--harita", "/tmp/yelpence_gorev.html"]
    return argv


def _durum() -> dict:
    k = _KOSU
    calisiyor = k.calisiyor()
    # ETKIN VARSAYILANLAR ARAYUZE GIDIYOR. Panel bunu dugmelerin yaninda
    # gosteriyor, boylece "hangi ucaklar ucacak" basmadan ONCE gorunur olur.
    # 2 Agustos'ta bu bilgi gizliydi ve arayuz backend'den FARKLI bir filo
    # gonderiyordu; hata ancak on kontrol patlayinca fark edildi.
    _v = BaslatBody()
    return {
        "varsayilan": {"senaryo": _v.senaryo, "dronelar": _coz_dronelar(_v),
                       "lider": _v.lider},
        "calisiyor": calisiyor,
        "kuru": k.kuru,
        "durduruluyor": k.durduruluyor,
        "komut": " ".join(k.komut),
        "gecen_s": round(
            (time.time() if calisiyor else (k.bitis or time.time()))
            - k.baslangic, 1
        ) if k.baslangic else 0.0,
        "cikis_kodu": k.cikis,
        "satirlar": list(k.satirlar),
    }


@router.post("/api/kosucu/baslat")
def kosucu_baslat(body: BaslatBody):
    """Görev koşucusunu başlatır. kuru=False ise GERÇEK UÇUŞ."""
    _KOSU.baslat(_argv(body), body.kuru)
    return {"ok": True, **_durum()}


@router.post("/api/kosucu/durdur")
def kosucu_durdur():
    """SIGINT gönderir — betik uçakları indirir."""
    mesaj = _KOSU.durdur()
    return {"ok": True, "mesaj": mesaj, **_durum()}


@router.get("/api/kosucu/durum")
def kosucu_durum(satir: int = 60):
    """Çalışma durumu ve son çıktı satırları."""
    d = _durum()
    d["satirlar"] = d["satirlar"][-max(1, min(satir, _SATIR_TAMPON)):]
    return d
