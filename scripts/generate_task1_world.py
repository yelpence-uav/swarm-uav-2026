import random
import math
import os

def generate_task1_sdf():
    # Yolların belirlenmesi
    script_dir = os.path.dirname(__file__)
    base_world_path = os.path.join(script_dir, "..", "sim", "worlds", "base_world.sdf")
    output_path = os.path.join(script_dir, "..", "sim", "worlds", "task1_dynamic_swarm.sdf")
    
    # base_world.sdf dosyasını şablon olarak oku
    try:
        with open(base_world_path, "r") as f:
            base_sdf_content = f.read()
    except FileNotFoundError:
        print("Hata: base_world.sdf bulunamadı. Lütfen önce base_world.sdf dosyasını oluşturun.")
        return

    # 1. QR Kodları Altıgen Dizilimi (Genişletilmiş Aralık)
    radius = 8.0  # Altıgenin merkezden köşelere uzaklığı (yarıçap: 8 metre)
    angles = [0, 60, 120, 180, 240, 300]
    
    # QR İsimlerini rastgele karıştır
    qr_names = ["QR1", "QR2", "QR3", "QR4", "QR5", "QR6"]
    random.shuffle(qr_names)

    dynamic_elements_sdf = "\n    \n"
    
    for i, angle in enumerate(angles):
        x = radius * math.cos(math.radians(angle))
        y = radius * math.sin(math.radians(angle))
        qr_name = qr_names[i]
        
        dynamic_elements_sdf += f"""
    <model name="{qr_name}">
      <static>true</static>
      <pose>{x:.2f} {y:.2f} 0.02 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><box><size>1.2 1.2 0.01</size></box></geometry>
          <material><ambient>1 1 1 1</ambient><diffuse>1 1 1 1</diffuse></material>
        </visual>
      </link>
    </model>
"""

    # 2. İniş Alanları (Kırmızı ve Mavi - Çapı 1 metre)
    pads = []
    
    def get_valid_position():
        # Sahanın güvenli sınırları
        while True:
            x = random.uniform(-22, 22)
            y = random.uniform(-12, 12)
            
            # Merkeze ve QR alanına çok yakın olmasın (en az 10 metre uzakta)
            if math.hypot(x, y) < 10.0:
                continue
                
            # Diğer iniş alanlarıyla çakışmasın (aralarında en az 3 metre mesafe olsun)
            overlap = False
            for px, py in pads:
                if math.hypot(x - px, y - py) < 3.0:
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

    # base_world.sdf içine enjekte etme işlemi
    insertion_point = base_sdf_content.rfind("</world>")
    if insertion_point != -1:
        # Nesneleri </world> etiketinden hemen önceye ekle
        final_sdf = base_sdf_content[:insertion_point] + dynamic_elements_sdf + "\n  " + base_sdf_content[insertion_point:]
        
        # Dünya adını güncelle
        final_sdf = final_sdf.replace('name="base_world"', 'name="task1_dynamic_swarm"')
        
        # Dosyayı kaydet
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(final_sdf)
            
        print(f"Rastgele Görev 1 dünyası başarıyla oluşturuldu: {os.path.abspath(output_path)}")
    else:
        print("Hata: base_world.sdf içinde </world> etiketi bulunamadı. Lütfen dosya yapısını kontrol edin.")

if __name__ == "__main__":
    generate_task1_sdf()
