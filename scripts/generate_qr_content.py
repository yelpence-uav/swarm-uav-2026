"""TEKNOFEST 2026 Sürü İHA — resmi QR şemasında QR görselleri üretir.

Şartname "QR VERİ FORMATI VE ÖRNEK GÖREV SENARYOSU" belgesindeki JSON
şemasını (qr / w / mis / team) kullanır. QR1-5 içerikleri belgedeki
örneklerle birebir aynıdır; QR6 rotalarda kullanılmaz (geçerli dolgu).

Yalnız sim/qr/QR{n}.png ve QR{n}.json dosyalarını yazar; dünya SDF'sine
DOKUNMAZ (QR konumları ve texture bağları korunur, Gazebo geçersiz olmaz).

Çalıştırma (qrcode + PIL gerektirir):
    python3 scripts/generate_qr_content.py
"""

import json
import os

import qrcode
from PIL import Image

# Şartname belgesindeki resmi örnek QR içerikleri (birebir).
QR_PAYLOADS = {
    1: {"qr": 1, "w": 4,
        "mis": [[["frm", "ok", 6], ["mnv", -10, 0], ["alt", 20]],
                [["frm", "v", 8], ["mnv", 0, 10], ["alt", 25]],
                [["frm", "l", 5], ["mnv", 0, -5], ["alt", 22]]],
        "team": {"1": [1, 3], "2": [2, 2], "3": [3, 5],
                 "4": [1, 4], "5": [2, 2]}},
    2: {"qr": 2, "w": 4,
        "mis": [[["frm", "ok", 7], ["mnv", 15, 5], ["alt", 30]],
                [["leav", 3, "b"]],
                [["frm", "l", 6], ["mnv", 0, -10], ["alt", 24]]],
        "team": {"1": [1, 4], "2": [3, 4], "3": [2, 3],
                 "4": [1, 5], "5": [3, 5]}},
    3: {"qr": 3, "w": 4,
        "mis": [[["frm", "v", 7], ["mnv", -15, 0], ["alt", 28]],
                [["leav", 1, "r"]],
                [["frm", "ok", 6], ["mnv", 5, 5], ["alt", 25]]],
        "team": {"1": [2, 5], "2": [1, 0], "3": [3, 4],
                 "4": [2, 2], "5": [1, 0]}},
    4: {"qr": 4, "w": 4,
        "mis": [[["frm", "ok", 5], ["mnv", -5, 5], ["alt", 21]],
                [["leav", 4, "r"]],
                [["frm", "l", 7], ["mnv", 0, -5], ["alt", 26]]],
        "team": {"1": [1, 0], "2": [2, 5], "3": [1, 0],
                 "4": [3, 3], "5": [1, 3]}},
    5: {"qr": 5, "w": 4,
        "mis": [[["frm", "v", 9], ["mnv", 10, 0], ["alt", 26]],
                [["leav", 2, "b"]],
                [["frm", "l", 5], ["mnv", 0, -10], ["alt", 3]]],
        "team": {"1": [3, 2], "2": [1, 3], "3": [1, 2],
                 "4": [1, 0], "5": [2, 4]}},
    # QR6: resmi örnek rotalarında referans edilmez; geçerli dolgu içerik.
    6: {"qr": 6, "w": 4,
        "mis": [[["frm", "ok", 6], ["alt", 20]]],
        "team": {"1": [1, 0], "2": [1, 0], "3": [1, 0],
                 "4": [1, 0], "5": [1, 0]}},
}


def generate(output_dir: str) -> None:
    """Her QR için okunabilir JSON ve kompakt-QR PNG üretir."""
    os.makedirs(output_dir, exist_ok=True)

    for qr_id, data in QR_PAYLOADS.items():
        json_path = os.path.join(output_dir, f"QR{qr_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=4, ensure_ascii=False))

        compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H, border=4,
        )
        qr.add_data(compact)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((1024, 1024), Image.NEAREST)
        img.save(os.path.join(output_dir, f"QR{qr_id}.png"))
        print(f"  QR{qr_id}: {len(compact)} byte -> QR{qr_id}.png + .json")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(script_dir, "..", "sim", "qr")
    print("Resmi şemada QR içerikleri üretiliyor (SDF'ye dokunulmaz)...")
    generate(out)
    print(f"[BAŞARILI] -> {os.path.abspath(out)}")
