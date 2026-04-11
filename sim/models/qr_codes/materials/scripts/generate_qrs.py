import qrcode
import json

def create_qr(qr_id, next_qr):
    # Teknofest Şartnamesine Birebir Uygun JSON Formatı
    data = {
        "qr_id": qr_id,
        "gorev": {
            "formasyon": {"aktif": False, "tip": "OKBASI"},
            "manevra_pitch_roll": {"aktif": False, "pitch_deg": 0, "roll_deg": 0},
            "irtifa_degisim": {"aktif": False, "deger": 0},
            "bekleme_suresi_s": 2,
            "suruden_ayrilma": {"aktif": False, "ayrilacak_drone_id": None, "hedef_renk": None}
        },
        "sonraki_qr": {
            "team_1": next_qr, 
            "team_2": next_qr, 
            "team_3": next_qr
        }
    }
    
    # Şov için görevleri dinamikleştirelim
    if qr_id == 1:
        data["gorev"]["formasyon"] = {"aktif": True, "tip": "OKBASI"}
    elif qr_id == 4:
        data["gorev"]["irtifa_degisim"] = {"aktif": True, "deger": 15}
        
    # JSON verisini QR koda çevir
    json_string = json.dumps(data, separators=(',', ':'))
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(json_string)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(f"qr_model_{qr_id}.png")
    print(f"🎯 QR {qr_id} Üretildi! -> Sonraki Hedef: {next_qr}")

# Şartnamedeki Örnek Rota: 1 -> 4 -> 2 -> 3 -> 5 -> 6 -> 0 (Bitiş)
rota = {1: 4, 4: 2, 2: 3, 3: 5, 5: 6, 6: 0}

print("QR Kodlar Teknofest standartlarında üretiliyor...")
for current_qr, next_q in rota.items():
    create_qr(current_qr, next_q)