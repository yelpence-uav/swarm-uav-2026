"""TEKNOFEST 2026 Sürü İHA Görev 1 - Dinamik Dünya ve Rastgele QR Üretici"""

import json
import math
import os
import random

import qrcode
from PIL import Image


def generate_random_qr_data():
    """Belirlenen kurallara göre tamamen rastgele QR içeriklerini ve rotaları üretir."""
    # 1. Takım Rotalarını Rastgele Belirle
    teams = ["team_1", "team_2", "team_3"]
    # Her takım için 1'den 6'ya kadar olan sayıları karıştırarak bağımsız rotalar oluşturuyoruz
    routes = {team: random.sample(range(1, 7), 6) for team in teams}

    next_qrs = {i: {} for i in range(1, 7)}
    for team, route in routes.items():
        for idx in range(len(route)):
            current_qr = route[idx]
            if idx < len(route) - 1:
                next_qrs[current_qr][team] = route[idx + 1]
            else:
                next_qrs[current_qr][
                    team
                ] = 0  # Rotanın sonundaki QR için 0 değeri atanır

    qr_payloads = {}
    for qr_id in range(1, 7):
        # Formasyon Tipi
        formasyon_tip = random.choice(["OKBASI", "V", "CIZGI"])

        # Manevra
        manevra_aktif = random.choice([True, False])
        pitch_deg = 0
        roll_deg = 0

        if manevra_aktif:
            # KURAL: CIZGI formasyonu ve pitch manevrası aynı anda olamaz
            if formasyon_tip == "CIZGI":
                axis = "roll"
            else:
                axis = random.choice(["pitch", "roll"])

            deg = random.choice([-30, -25, -20, -15, -10, 10, 15, 20, 25, 30])
            if axis == "pitch":
                pitch_deg = deg
            else:
                roll_deg = deg

        # İrtifa
        irtifa_aktif = random.choice([True, False])
        irtifa_deger = (
            random.choice(
                [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
            )
            if irtifa_aktif
            else 0
        )

        # Sürüden Ayrılma (Landing)
        ayrilma_aktif = random.choice([True, False])
        ayrilacak_drone_id = random.randint(1, 3) if ayrilma_aktif else None
        hedef_renk = random.choice(["KIRMIZI", "MAVI"]) if ayrilma_aktif else None
        ayrilma_bekleme = random.randint(5, 15) if ayrilma_aktif else None

        # JSON formatını görseldeki yapıya birebir uyduruyoruz
        qr_payloads[qr_id] = {
            "qr_id": qr_id,
            "gorev": {
                "formasyon": {"aktif": True, "tip": formasyon_tip},
                "manevra_pitch_roll": {
                    "aktif": manevra_aktif,
                    "pitch_deg": str(pitch_deg),
                    "roll_deg": str(roll_deg),
                },
                "irtifa_degisim": {"aktif": irtifa_aktif, "deger": irtifa_deger},
                "bekleme_suresi_s": random.randint(5, 15),
            },
            "suruden_ayrilma": {
                "aktif": ayrilma_aktif,
                "ayrilacak_drone_id": ayrilacak_drone_id,
                "hedef_renk": hedef_renk,
                "bekleme_suresi_s": ayrilma_bekleme,
            },
            "sonraki_qr": next_qrs[qr_id],
        }

    return qr_payloads


def generate_qr_images(output_dir):
    """Rastgele üretilen içeriklerle 6 adet QR PNG ve JSON üretir, dosya yollarını döndürür."""
    os.makedirs(output_dir, exist_ok=True)
    payloads = generate_random_qr_data()
    paths = {}

    for qr_id, data in payloads.items():
        # 1. JSON İçeriğini Dosyaya Kaydetme (Okunabilir Format)
        json_pretty_str = json.dumps(data, indent=4, ensure_ascii=False)
        json_filename = f"QR{qr_id}.json"
        json_filepath = os.path.join(output_dir, json_filename)
        with open(json_filepath, "w", encoding="utf-8") as f:
            f.write(json_pretty_str)

        # 2. QR Kod PNG'sini Oluşturma (Sıkıştırılmış Format)
        json_compact_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            border=4,
        )
        qr.add_data(json_compact_str)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((1024, 1024), Image.NEAREST)

        png_filename = f"QR{qr_id}.png"
        png_filepath = os.path.join(output_dir, png_filename)
        img.save(png_filepath)
        paths[qr_id] = os.path.abspath(png_filepath)

    return paths


def generate_task1_sdf():
    """QR kodları üretir ve SDF dünyasına rastgele yerleştirir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_world_path = os.path.join(script_dir, "..", "sim", "worlds", "base_world.sdf")
    output_path = os.path.join(
        script_dir, "..", "sim", "worlds", "task1_dynamic_swarm.sdf"
    )

    qr_output_dir = os.path.join(script_dir, "..", "sim", "qr")
    print("[1/2] Rastgele görevlere sahip QR Kodlar ve JSON dosyaları oluşturuluyor...")
    qr_paths = generate_qr_images(qr_output_dir)

    print("[2/2] Dinamik SDF dünyası oluşturuluyor...")
    try:
        with open(base_world_path, "r") as f:
            base_sdf_content = f.read()
    except FileNotFoundError:
        print(f"Hata: base_world.sdf bulunamadı. Aranan yol: {base_world_path}")
        return

    radius = 24.0
    angles = [0, 60, 120, 180, 240, 300]
    qr_names = ["QR1", "QR2", "QR3", "QR4", "QR5", "QR6"]
    random.shuffle(qr_names)

    dynamic_elements_sdf = "\n    \n"

    for i, angle in enumerate(angles):
        x = radius * math.cos(math.radians(angle))
        y = radius * math.sin(math.radians(angle))
        qr_name = qr_names[i]
        qr_num = int(qr_name[2:])
        texture_path = qr_paths[qr_num]

        dynamic_elements_sdf += f"""
    <model name="{qr_name}">
      <static>true</static>
      <pose>{x:.2f} {y:.2f} 0.02 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>1.2 1.2 0.01</size></box></geometry>
          <material>
            <ambient>1 1 1 1</ambient>
            <diffuse>1 1 1 1</diffuse>
            <pbr>
              <metal>
                <albedo_map>{texture_path}</albedo_map>
                <roughness>1.0</roughness>
                <metalness>0.0</metalness>
              </metal>
            </pbr>
          </material>
        </visual>
      </link>
    </model>
"""

    pads = []

    def get_valid_position():
        while True:
            x = random.uniform(-radius, radius)
            y = random.uniform(-radius, radius)

            h_limit = radius * math.sqrt(3) / 2
            if abs(y) > h_limit or abs(y) > math.sqrt(3) * (radius - abs(x)):
                continue

            if math.hypot(x, y) < 5.0:
                continue

            overlap = False
            for px, py in pads:
                if math.hypot(x - px, y - py) < 6.0:
                    overlap = True
                    break

            if not overlap:
                return x, y

    rx, ry = get_valid_position()
    pads.append((rx, ry))

    bx, by = get_valid_position()
    pads.append((bx, by))

    dynamic_elements_sdf += f"""
    <model name="landing_pad_red">
      <static>true</static>
      <pose>{rx:.2f} {ry:.2f} 0.02 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><cylinder><radius>0.5</radius><length>0.01</length></cylinder></geometry>
          <material><ambient>0.8 0.1 0.1 1</ambient><diffuse>0.8 0.1 0.1 1</diffuse></material>
        </visual>
      </link>
    </model>

    <model name="landing_pad_blue">
      <static>true</static>
      <pose>{bx:.2f} {by:.2f} 0.02 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><cylinder><radius>0.5</radius><length>0.01</length></cylinder></geometry>
          <material><ambient>0.1 0.1 0.8 1</ambient><diffuse>0.1 0.1 0.8 1</diffuse></material>
        </visual>
      </link>
    </model>
"""

    insertion_point = base_sdf_content.rfind("</world>")
    if insertion_point != -1:
        final_sdf = (
            base_sdf_content[:insertion_point]
            + dynamic_elements_sdf
            + "\n  "
            + base_sdf_content[insertion_point:]
        )

        final_sdf = final_sdf.replace('name="base_world"', 'name="task1_dynamic_swarm"')

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(final_sdf)

        print(f"\n[BAŞARILI] Görev 1 dünyası üretildi.")
        print(f"  → JSON ve PNG dosyaları 'sim/qr/' klasörüne kaydedildi.")
        print(f"  → Dünya dosyası: {os.path.abspath(output_path)}")
    else:
        print("Hata: base_world.sdf yapısı uyumsuz.")


if __name__ == "__main__":
    generate_task1_sdf()
