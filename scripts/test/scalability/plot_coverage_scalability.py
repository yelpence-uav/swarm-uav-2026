#!/usr/bin/env python3
"""
TEKNOFEST 2026 Sürü İHA — Yayın Kalitesi Şekil
Kapsama Zamanı – İHA Sayısı İlişkisi

Sol panel : Ortalama ± 95% CI çizgi grafiği + kazanım anotasyonları
Sağ panel : Monte Carlo dağılım kutu grafiği (N=3/4/5, her iki hız)
"""

import math, os, statistics
import numpy as np
import scipy.stats as sp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch
import warnings
warnings.filterwarnings("ignore")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suru_kapsama_analizi.png")

# ══════════════════════════════════════════════════════════════════════════════
# PARAMETRELER  —  Şartname (5.1) + SITL gerçek değerleriyle kalibre
# ══════════════════════════════════════════════════════════════════════════════
SAFE_S, MAX_S = 480, 600         # güvenli görev sınırı / pil ömrü [s]

# Gerçek QR konumları (generate_task_world.py ile birebir) ve örnek rota
QR    = {1:(-28,-12), 2:(-28,16), 3:(0,35), 4:(28,16), 5:(28,-12), 6:(0,-30)}
ROUTE = [1, 4, 2, 3, 5, 6]        # inter-QR toplam ≈ 240 m  (+home ≈ 158 m ⇒ ~399 m)

ALT   = 15.0                      # görev irtifası [m]   (QR örnek: 15 m)
VZ    = 1.5                       # dikey hız (tırmanma/alçalma/iniş) [m/s]
SEP_P = 0.50                      # QR başına birey-çıkarma olasılığı (generator: %50)

# Dağıtık haberleşme / konsensüs gecikmesi.
# Tek-mesaj latency, ekibin scalability_latency.py dağıtık modeliyle TUTARLI:
#   Distributed(N) = 18 + 6·log2(N)  [ms]   (O(log N) gossip-tree, 20 Hz)
# Her QR'da konsensüs ~COMM_ROUNDS mesaj turu gerektirir.
COMM_OFFSET = 18.0                # ms  (DIST_OFFSET)
COMM_LOG    = 6.0                 # ms  (DIST_LOG)
COMM_ROUNDS = 20                  # konsensüs için mesaj turu / koordinasyon olayı
def comm_latency_s(n, jitter):
    """Dağıtık O(log N) konsensüs gecikmesi [s]; jitter ORTAK senaryodan gelir."""
    lat_ms = COMM_OFFSET + COMM_LOG * math.log2(n)
    return jitter * COMM_ROUNDS * lat_ms / 1000.0

def dist(a, b): return math.hypot(a[0]-b[0], a[1]-b[1])

def random_home(rng):
    """Spawn ±70 m, tüm QR'lara >40 m (şartname güvenlik mesafesi varsayımı)."""
    while True:
        x, y = rng.uniform(-70,70), rng.uniform(-70,70)
        if all(dist((x,y),p)>40 for p in QR.values()):
            return float(x), float(y)

def make_scenario(rng):
    """
    Tek bir görev senaryosu — N'den BAĞIMSIZ rastgele kısımlar.
    Ortak Rastgele Sayılar (CRN): aynı senaryo N=3/4/5'e verilir → fark = SAF N etkisi.
    """
    home = random_home(rng)
    qrs = []
    for _ in ROUTE:
        qrs.append(dict(
            maneuver   = rng.random() < 0.50,          # pitch/roll var mı
            altitude   = rng.random() < 0.50,          # irtifa değişimi var mı
            alt_dz     = rng.uniform(0, 15),           # |Δirtifa| [m]
            wait       = rng.uniform(5, 15),           # bekleme_suresi_s
            separation = rng.random() < SEP_P,         # birey-çıkarma var mı
            sep_wait   = rng.uniform(5, 15),           # ayrılan ajanın bekleme süresi
            sep_integ  = rng.uniform(8, 12),           # yedek entegrasyon süresi
            jit_qr     = rng.uniform(0.7, 1.3),        # haberleşme jitter (QR)
            jit_sep    = rng.uniform(0.7, 1.3),        # haberleşme jitter (takas)
        ))
    return home, qrs

def simulate(n, v, home, qrs):
    """
    AYNI senaryoyu (home + qrs ORTAK) N ajanla değerlendir.
    Sadece N'e bağlı olanlar — yani saf ölçeklenebilirlik etkileri:
      • yedek takası (madde 16): N>3 kesintisiz, N=3 tam rejoin (~30–40 s)
      • kamera sayısı (QR decode), dağıtık haberleşme (O(log N))
    Transit, formasyon, görev süreleri tüm N'lerde AYNI (CRN).
    """
    t = 5.0 + ALT/VZ                                   # arm + 15 m tırmanma
    t += dist(home, QR[ROUTE[0]]) / v                  # home → ilk QR transit
    spares = [0.0] * max(0, n - 3)                     # yer-yedeklerinin uygunluk zamanı

    for i, (qid, s) in enumerate(zip(ROUTE, qrs)):
        t += max(2.5, 4.0 - 0.5*min(len(spares), 2))   # QR decode (kamera sayısı = N etkisi)
        t += 3.0                                       # formasyon rotasyonu / heading
        t += comm_latency_s(n, s["jit_qr"])            # dağıtık konsensüs (N etkisi)
        t += 6.0                                       # formasyon kurma/değişim
        if s["maneuver"]: t += 6.0
        if s["altitude"]: t += s["alt_dz"] / VZ
        t += s["wait"]
        if s["separation"]:                            # birey ekleme/çıkarma (madde 15–16)
            # in+land+wait+arm+climb ≈30–40 s — member_detach_rejoin testiyle uyumlu
            cycle = ALT/VZ + 5.0 + s["sep_wait"] + ALT/VZ
            ready = [k for k, rt in enumerate(spares) if rt <= t]
            if ready:                                  # hazır yedek ⇒ kesintisiz takas
                t += s["sep_integ"] + comm_latency_s(n, s["jit_sep"])
                spares[ready[0]] = t + cycle           # ayrılan ajan yeni yedek olur
            else:                                      # yedek yok (N=3) ⇒ tam rejoin
                t += cycle
        nxt = QR[ROUTE[i+1]] if i < len(ROUTE)-1 else home
        t += dist(QR[qid], nxt) / v                    # sonraki QR / home transit

    return t + ALT/VZ + 5.0                            # 15 m alçal + güvenli iniş

def mc(v, seed=42, iters=300):
    """Her iterasyonda TEK senaryo üret, N=3/4/5 için AYNI senaryoda koş (paired/CRN)."""
    rng = np.random.default_rng(seed + int(v*10))
    out = {n: [] for n in N_LIST}
    for _ in range(iters):
        home, qrs = make_scenario(rng)
        for n in N_LIST:
            out[n].append(simulate(n, v, home, qrs))
    return {n: np.array(out[n]) for n in N_LIST}

# ══════════════════════════════════════════════════════════════════════════════
# VERİ
# ══════════════════════════════════════════════════════════════════════════════
N_LIST   = [3, 4, 5]
SPEEDS   = {"3 m/s": 3.0}
samples  = {}
for lbl, v in SPEEDS.items():
    res = mc(v)                                   # tek çağrı: tüm N aynı senaryolarda
    for n in N_LIST:
        samples[(n, lbl)] = res[n]

# ══════════════════════════════════════════════════════════════════════════════
# TASARIM SİSTEMİ
# ══════════════════════════════════════════════════════════════════════════════
BG      = "#ffffff"    # beyaz arka plan (PDF / baskı)
PANEL   = "#ffffff"
BORDER  = "#c5ccd6"
TXT     = "#19222e"    # koyu metin
SUBTLE  = "#5c6773"
C2      = "#1f6feb"    # mavi  – 3 m/s (ana çizgi)
C3      = "#2da44e"    # yeşil (yedek)
CDANGER = "#cf222e"
CWARN   = "#9a6700"

plt.rcParams.update({
    "font.family":        "DejaVu Sans",
    "figure.facecolor":   BG,
    "axes.facecolor":     PANEL,
    "axes.edgecolor":     BORDER,
    "axes.linewidth":     1.2,
    "axes.labelcolor":    TXT,
    "axes.labelpad":      10,
    "xtick.color":        SUBTLE,
    "ytick.color":        SUBTLE,
    "xtick.labelsize":    10,
    "ytick.labelsize":    10,
    "xtick.major.pad":    6,
    "ytick.major.pad":    6,
    "text.color":         TXT,
    "grid.color":         "#e3e7ee",
    "grid.linewidth":     0.8,
})

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE YAPISI
# ══════════════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(10.5, 7))
fig.patch.set_facecolor(BG)
ax_line = fig.add_axes([0.10, 0.23, 0.86, 0.61])

# ── Başlık ────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.955,
         "Görev Tamamlama (Kapsama) Süresi – İHA Sayısı İlişkisi",
         ha="center", va="center",
         fontsize=17, fontweight="bold", color=TXT)
fig.text(0.5, 0.916,
         "TEKNOFEST 2026 Sürü İHA  ·  Dinamik Görev (6 QR)  ·  Monte Carlo  n = 300",
         ha="center", va="center",
         fontsize=10.5, color=SUBTLE)

# ══════════════════════════════════════════════════════════════════════════════
# SOL PANEL — Çizgi Grafik
# ══════════════════════════════════════════════════════════════════════════════
ax = ax_line

# Çizgiler
for lbl, clr, ls, zo in [("3 m/s", C2, "-", 5)]:
    arr   = np.array([samples[(n,lbl)] for n in N_LIST])   # shape (3, 300)
    means = arr.mean(axis=1)
    # 95% güven aralığı (ortalamanın kesinliği)
    ci95  = sp.t.ppf(0.975, df=299) * arr.std(axis=1, ddof=1) / np.sqrt(300)
    # P5–P95 senaryo değişkenlik aralığı (görevin gerçek saçılımı)
    p5_   = np.percentile(arr, 5,  axis=1)
    p95_  = np.percentile(arr, 95, axis=1)

    ax.fill_between(N_LIST, p5_, p95_, alpha=0.15, color=clr, zorder=zo-2)
    ax.plot(N_LIST, means,
            color=clr, lw=3.0, ls=ls, zorder=zo,
            marker="o", ms=12, mec=BG, mew=2,
            label=f"v = {lbl}  (95% GA)")

    # Değer kutuları
    for n, m in zip(N_LIST, means):
        ax.annotate(
            f"{m:.1f} s",
            xy=(n, m), xytext=(0, 22), textcoords="offset points",
            ha="center", fontsize=10.5, color=TXT, fontweight="semibold",
            bbox=dict(boxstyle="round,pad=0.3", fc=PANEL, ec=clr,
                      lw=1.2, alpha=0.95),
            arrowprops=dict(arrowstyle="-", color=clr, lw=0.9, alpha=0.6)
        )

    # N=3→4 ve N=4→5 kazanım anotasyonları
    for i in range(1, len(N_LIST)):
        pct = (means[i-1]-means[i])/means[i-1]*100
        abs_s = means[i-1]-means[i]
        mx = (N_LIST[i-1]+N_LIST[i])/2
        my = (means[i-1]+means[i])/2 - 40
        ax.annotate(
            f"−{abs_s:.0f} s\n(−{pct:.1f}%)",
            xy=(mx, my), ha="center", fontsize=9,
            color=clr, linespacing=1.4,
            bbox=dict(boxstyle="round,pad=0.25", fc=BG, ec=clr, lw=0.8, alpha=0.7)
        )

# N=3→5 toplam kazanım — yatay çift ok
for lbl, clr, dy in [("3 m/s", C2, 26)]:
    arr   = np.array([samples[(n,lbl)] for n in N_LIST])
    m3, m5 = arr[0].mean(), arr[2].mean()
    total  = (m3-m5)/m3*100
    y_arr  = (m3+m5)/2 + dy
    ax.annotate("", xy=(5, y_arr), xytext=(3, y_arr),
                arrowprops=dict(arrowstyle="<->", color=clr,
                                lw=1.4, alpha=0.55))
    ax.text(4, y_arr+5, f"Toplam: −{total:.1f}%",
            ha="center", fontsize=8.5, color=clr, alpha=0.85)

ax.set_xticks(N_LIST)
ax.set_xticklabels([f"N = {n}" for n in N_LIST], fontsize=12, color=TXT)
ax.set_xlim(2.48, 5.52)
ax.set_ylim(320, 560)
ax.yaxis.set_major_locator(ticker.MultipleLocator(50))
ax.yaxis.set_minor_locator(ticker.MultipleLocator(25))
ax.set_xlabel("Aktif İHA Sayısı  (N)", fontsize=12.5, color=TXT)
ax.set_ylabel("Görev Tamamlama Süresi  [s]", fontsize=12.5, color=TXT)
ax.grid(True, which="major", ls="--", alpha=0.35)
ax.grid(True, which="minor", ls=":",  alpha=0.15)

handles = [
    Line2D([0],[0], color=C2, lw=2.5, ls="-",  marker="o", ms=9,
           mec=BG, mew=1.5, label="v = 3 m/s  (ortalama)"),
    Patch(facecolor=C2, alpha=0.15, label="P5–P95 senaryo değişkenliği"),
]
leg = ax.legend(handles=handles, fontsize=9, loc="upper right",
                frameon=True, framealpha=0.95,
                facecolor="#ffffff", edgecolor=BORDER)
for t in leg.get_texts(): t.set_color(TXT)

# ══════════════════════════════════════════════════════════════════════════════
# DİPNOT (Parametreler)
# ══════════════════════════════════════════════════════════════════════════════
# — Senaryo değişkenlik yorumu (P5–P95 aralıkları, dinamik) —
def _rng_txt(n):
    s = samples[(n, "3 m/s")]
    return f"N={n}: {np.percentile(s,5):.0f}–{np.percentile(s,95):.0f} s"
var_line = (
    r"$\bf{Senaryo\ değişkenliği\ (P5–P95):}$   "
    + "     ·     ".join(_rng_txt(n) for n in N_LIST)
    + "      Kaynaklar: rastgele home konumu, QR görev aktivasyonları (p=0.50), "
      "bekleme 5–15 s, dağıtık haberleşme jitter'ı (±%30)"
)
fig.text(0.5, 0.085, var_line, ha="center", fontsize=8.6,
         color=TXT, linespacing=1.5)

params = (
    r"$\bf{Model:}$"
    "  Gerçek QR rotası (inter-QR 240 m + home ~158 m ≈ 399 m)  ·  cruise 3 m/s  ·  "
    "QR decode 2.5–4 s  ·  formasyon 6 s + rotasyon 3 s  ·  pitch/roll 6 s (p=0.50)  ·  "
    "irtifa Δ/1.5 m·s⁻¹ (p=0.50)  ·  bekleme 5–15 s  ·  haberleşme: dağıtık O(log N) konsensüs  ·  "
    r"$\bf{birey\ çıkarma}$ madde 16 yedek havuzu (N>3 kesintisiz takas, N=3 ~30–40 s rejoin)"
)
calib = (
    r"$\bf{Kalibrasyon:}$  Birey-çıkarma süresi → member_detach_rejoin testi (manevra 30 s+, RMS tepe 2.67 m)  ·  "
    "çarpışmasızlık → gorev_dinamik (min_dist 1.89 m, 0 ihlal) + 52 CA senaryosu  ·  "
    "haberleşme → scalability_latency.py dağıtık modeli.  Diğer faz süreleri: mühendislik tahmini."
)
fig.text(0.5, 0.046, params, ha="center", fontsize=7.6, color=SUBTLE, linespacing=1.5)
fig.text(0.5, 0.012, calib,  ha="center", fontsize=7.6, color=C2,     linespacing=1.5)

plt.savefig(OUT, dpi=300, bbox_inches="tight", facecolor=BG)
OUT_PDF = OUT.replace(".png", ".pdf")
plt.savefig(OUT_PDF, bbox_inches="tight", facecolor=BG)   # vektörel — PDF'e gömmek için
print(f"[OK] {OUT}\n[OK] {OUT_PDF}")

# ── Grafiği otomatik aç ───────────────────────────────────────────────────────
import sys, shutil, subprocess
def _open(path):
    if sys.platform == "darwin":
        return subprocess.Popen(["open", path]) or True
    if sys.platform.startswith("win"):
        os.startfile(path); return True  # type: ignore[attr-defined]
    # Linux: mevcut ilk açıcıyı dene (xdg-open, VS Code, yaygın görüntüleyiciler)
    for opener in ("xdg-open", "code", "eog", "feh", "display", "gio"):
        if shutil.which(opener):
            args = ["gio", "open", path] if opener == "gio" else [opener, path]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return opener
    return None
try:
    used = _open(OUT)
    print(f"[OK] açıldı ({used})" if used else "[!] Açıcı bulunamadı; dosyayı elle açın.")
except Exception as e:
    print(f"[!] Otomatik açma başarısız: {e}")
