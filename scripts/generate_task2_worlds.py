import os
import random
import math


def generate_task2_worlds():
    script_dir = os.path.dirname(__file__)
    base_world_path = os.path.join(
        script_dir, "..", "sim", "worlds", "base_world.sdf")

    # base_world.sdf dosyasını şablon olarak oku
    try:
        with open(base_world_path, "r") as f:
            base_sdf_content = f.read()
    except FileNotFoundError:
        print("Hata: base_world.sdf bulunamadı. Lütfen önce base_world.sdf dosyasını oluşturun.")
        return

    insertion_point = base_sdf_content.rfind("</world>")
    if insertion_point == -1:
        print("Hata: base_world.sdf içinde </world> etiketi bulunamadı.")
        return

    # 1. task2_formation.sdf (Sadece boş saha)
    formation_sdf = base_sdf_content.replace(
        'name="base_world"', 'name="task2_formation"')
    formation_path = os.path.join(
        script_dir, "..", "sim", "worlds", "task2_formation.sdf")
    with open(formation_path, "w") as f:
        f.write(formation_sdf)
    print(f"Başarılı: {os.path.abspath(formation_path)}")

    # 2. task2_navigation.sdf (Sadece Rastgele İniş Pedleri)
    nav_elements = "\n    \n"

    pads = []

    def get_valid_nav_position():
        # Sahanın güvenli sınırları
        while True:
            x = random.uniform(-22, 22)
            y = random.uniform(-12, 12)

            # Diğer iniş alanlarıyla çakışmasın (aralarında en az 3 metre mesafe olsun)
            overlap = False
            for px, py in pads:
                if math.hypot(x - px, y - py) < 3.0:
                    overlap = True
                    break

            if not overlap:
                return x, y

    # 4 Farklı renk için iniş pedi oluşturma
    colors = [
        ("red", "0.8 0.1 0.1 1"),
        ("blue", "0.1 0.1 0.8 1"),
        ("green", "0.1 0.8 0.1 1"),
        ("yellow", "0.8 0.8 0.1 1")
    ]

    for color_name, rgba in colors:
        px, py = get_valid_nav_position()
        pads.append((px, py))

        nav_elements += f"""
    <model name="landing_pad_{color_name}">
      <static>true</static>
      <pose>{px:.2f} {py:.2f} 0.02 0 0 0</pose>
      <link name="link">
        <visual name="visual">
          <geometry><cylinder><radius>0.5</radius><length>0.01</length></cylinder></geometry>
          <material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material>
        </visual>
      </link>
    </model>
"""

    nav_sdf = base_sdf_content[:insertion_point] + \
        nav_elements + "\n  " + base_sdf_content[insertion_point:]
    nav_sdf = nav_sdf.replace('name="base_world"', 'name="task2_navigation"')
    nav_path = os.path.join(script_dir, "..", "sim",
                            "worlds", "task2_navigation.sdf")
    with open(nav_path, "w") as f:
        f.write(nav_sdf)
    print(f"Başarılı: {os.path.abspath(nav_path)}")

    # 3. task2_collision.sdf (Sadece Boş Saha)
    col_sdf = base_sdf_content.replace(
        'name="base_world"', 'name="task2_collision"')
    col_path = os.path.join(script_dir, "..", "sim",
                            "worlds", "task2_collision.sdf")
    with open(col_path, "w") as f:
        f.write(col_sdf)
    print(f"Başarılı: {os.path.abspath(col_path)}")


if __name__ == "__main__":
    generate_task2_worlds()
