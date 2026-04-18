import qrcode
import json
import os


def create_qr():
    # --- QR 1 İÇERİĞİ (Başlangıç ve Formasyon) ---
    qr1_data = {
        "qr_id": 1,
        "gorev": {
            "formasyon": {
                "aktif": True,
                "tip": "CIZGI",
            },  # Sürü Ok Başı formasyonuna geçsin
            "manevra_pitch_roll": {"aktif": True, "pitch_deg": 0, "roll_deg": -20},
            "irtifa_degisim": {"aktif": True, "deger": 3},
            "bekleme_suresi_s": 10,
            "suruden_ayrilma": {
                "aktif": False,
                "ayrilacak_drone_id": None,
                "hedef_renk": None,
            },
        },
        "sonraki_qr": {
            "team_1": 2,
            "team_2": 3,
            "team_3": 3,
        },
    }

    # --- QR 2 İÇERİĞİ (Kırmızı Pede İniş / Ayrılma) ---
    qr2_data = {
        "qr_id": 2,
        "gorev": {
            "formasyon": {"aktif": True, "tip": "OKBASI"},
            "manevra_pitch_roll": {"aktif": True, "pitch_deg": -30, "roll_deg": 0},
            "irtifa_degisim": {"aktif": True, "deger": 6},
            "bekleme_suresi_s": 10,
            # 1 numaralı İHA sürüden ayrılıp KIRMIZI pede insin
            "suruden_ayrilma": {
                "aktif": False,
                "ayrilacak_drone_id": None,
                "hedef_renk": None,
            },
        },
        "sonraki_qr": {
            "team_1": 3,  # Kalan İHA'ları QR 3'e yönlendir
            "team_2": 1,
            "team_3": 1,
        },
    }

    # --- QR 3 İÇERİĞİ (Mavi Pede İniş / Görev Sonu) ---
    qr3_data = {
        "qr_id": 3,
        "gorev": {
            "formasyon": {"aktif": True, "tip": "v"},
            "manevra_pitch_roll": {"aktif": False, "pitch_deg": 0, "roll_deg": 0},
            "irtifa_degisim": {"aktif": True, "deger": 3},
            "bekleme_suresi_s": 10,
            "suruden_ayrilma": {
                "aktif": True,
                "ayrilacak_drone_id": 3,
                "hedef_renk": "KIRMIZI",
            },
        },
        "sonraki_qr": {
            "team_1": 0,
            "team_2": 2,
            "team_3": 2,
        },
    }

    # Tüm QR'ları bir listede toplayalım
    qrs = [qr1_data, qr2_data, qr3_data]

    # QR kodları oluştur ve kaydet
    for data in qrs:
        qr_id = data["qr_id"]
        # JSON'ı string formatına çevir (boşlukları silerek boyutu küçültür)
        json_string = json.dumps(data, separators=(",", ":"))

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(json_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Dosya adı Gazebo dünyasında (task1_dynamic_swarm.sdf) yazdığımız ile aynı olmalı
        filename = f"qr_model_{qr_id}.png"
        
        # Dosyayı doğrudan textures klasörüne kaydetmek için yol hesabı
        script_dir = os.path.dirname(os.path.abspath(__file__))
        textures_dir = os.path.join(os.path.dirname(script_dir), "textures")
        os.makedirs(textures_dir, exist_ok=True)
        
        filepath = os.path.join(textures_dir, filename)
        img.save(filepath)
        print(f"[{filepath}] başarıyla oluşturuldu. İçerik: {json_string}")


if __name__ == "__main__":
    create_qr()

