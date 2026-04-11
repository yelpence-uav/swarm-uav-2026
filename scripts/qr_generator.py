"""QR kod PNG üretici — TEKNOFEST 2026 Sürü İHA Görev 1."""

import json
import os

import qrcode
from PIL import Image

# ── Takım rotaları ──────────────────────────────────────────────
TEAM_ROUTES = {
    "team_1": [1, 4, 2, 3, 5, 6],
    "team_2": [1, 3, 5, 2, 6, 4],
    "team_3": [1, 5, 6, 4, 3, 2],
}

# ── QR içerik tanımları ─────────────────────────────────────────
QR_DATA = {
    1: {
        "qr_id": 1,
        "mission": {
            "formasyon": "OKBASI",
            "manevra_pitch_roll": None,
            "irtifa_degisim": 3,
            "bekleme_suresi_s": 3,
            "suruden_ayrilma": None,
        },
    },
    2: {
        "qr_id": 2,
        "mission": {
            "formasyon": "V",
            "manevra_pitch_roll": None,
            "irtifa_degisim": 4,
            "bekleme_suresi_s": 5,
            "suruden_ayrilma": None,
        },
    },
    3: {
        "qr_id": 3,
        "mission": {
            "formasyon": "CIZGI",
            "manevra_pitch_roll": "pitch -15",
            "irtifa_degisim": None,
            "bekleme_suresi_s": 4,
            "suruden_ayrilma": None,
        },
    },
    4: {
        "qr_id": 4,
        "mission": {
            "formasyon": "UCGEN",
            "manevra_pitch_roll": None,
            "irtifa_degisim": 2.8,
            "bekleme_suresi_s": 3,
            "suruden_ayrilma": {"drone_id": "drone_3", "inis_alani": "KIRMIZI"},
        },
    },
    5: {
        "qr_id": 5,
        "mission": {
            "formasyon": "OKBASI",
            "manevra_pitch_roll": "roll +20",
            "irtifa_degisim": 4.5,
            "bekleme_suresi_s": 5,
            "suruden_ayrilma": None,
        },
    },
    6: {
        "qr_id": 6,
        "mission": {
            "formasyon": "V",
            "manevra_pitch_roll": None,
            "irtifa_degisim": None,
            "bekleme_suresi_s": 4,
            "suruden_ayrilma": {"drone_id": "drone_5", "inis_alani": "MAVI"},
        },
    },
}


def _next_qr_map():
    """Her QR için takım bazlı next_qr değerini hesapla."""
    result = {}
    for qr_id in QR_DATA:
        per_team = {}
        for team, route in TEAM_ROUTES.items():
            idx = route.index(qr_id)
            if idx < len(route) - 1:
                per_team[team] = route[idx + 1]
            else:
                per_team[team] = 0  # rota sonu
        result[qr_id] = per_team
    return result


def generate_qr_images(output_dir):
    """6 adet QR PNG üretir ve {qr_id: absolute_path} dict döndürür."""
    os.makedirs(output_dir, exist_ok=True)
    next_map = _next_qr_map()
    paths = {}

    for qr_id, data in QR_DATA.items():
        payload = dict(data)
        payload["next_qr"] = next_map[qr_id]

        json_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            border=4,
        )
        qr.add_data(json_str)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((1024, 1024), Image.NEAREST)

        filename = f"qr_model_{qr_id}.png"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath)
        paths[qr_id] = os.path.abspath(filepath)

    return paths


if __name__ == "__main__":
    # 1. Bu Python dosyasının o an çalıştığı klasörün yolunu dinamik olarak bulur
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Bulunduğu klasörden bir üste (..) çıkıp doğruca simülasyon klasörüne iner
    out = os.path.join(script_dir, "..", "sim", "models", "qr_codes", "materials", "textures")
    
    result = generate_qr_images(out)
    for qr_id, path in sorted(result.items()):
        print(f"BAŞARILI! Şifre Üretildi → {path}")