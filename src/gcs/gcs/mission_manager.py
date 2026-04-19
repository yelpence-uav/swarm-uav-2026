import json
import math
from datetime import datetime


class MissionManager:
    def __init__(self, bridge_node, formation_mgr, socketio):
        self.bridge_node = bridge_node
        self.formation_mgr = formation_mgr
        self.socketio = socketio
        self.is_executing = (
            False  # Aynı anda iki görev yapılmasını engelleyen güvenlik kilidi
        )

        # Gazebo (X,Y) ile PX4 (X,Y) uyuşmazlığını çözen yeni koordinatlar
        self.qr_coordinates = {
            1: (0.00, 8.00),  # Eski: (8.0, 0.0) -> Manuel testindeki mükemmel ayar!
            2: (6.93, -4.00),  # Eski: (-8.0, 0.0)
            3: (-6.93, -4.00),  # Eski: (-4.0, 6.93)
        }
        self.alt_locks = {}
        self.alt_protectors = {}

    def set_altitude_locks(self, locks, protectors):
        """Web sunucusundaki global irtifa sözlüklerine referans bağlar."""
        self.alt_locks = locks
        self.alt_protectors = protectors

    def send_gui_log(self, msg, level="info"):
        """SocketIO üzerinden GUI terminaline log gönderir."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.socketio.emit("gui_log", {"msg": msg, "level": level, "time": timestamp})

    def process_qr_task(self, qr_text):
        """Kameradan gelen metni JSON'a çevirip Görev Zincirini başlatır."""
        if self.is_executing:
            self.bridge_node.get_logger().warn(
                "Görev reddedildi: Zaten bir işlem yürütülüyor."
            )
            self.send_gui_log("GÖREV REDDEDİLDİ: Sistem meşgul.", "warning")
            return

        try:
            task_data = json.loads(qr_text)
            qr_id = task_data.get("qr_id", "Bilinmiyor")
            self.is_executing = True
            self.send_gui_log(f"Yeni Görev Başlatıldı: QR {qr_id}", "info")
            # Kamerayı ve ROS'u dondurmamak için görevi arka planda (Thread) çalıştır
            self.socketio.start_background_task(self.execute_mission, task_data)
        except json.JSONDecodeError:
            self.bridge_node.get_logger().error(
                "HATA: Okunan QR metni geçerli bir JSON formatında değil!"
            )

    def execute_mission(self, data):
        """Teknofest şartnamesindeki orijinal JSON formatıyla emirleri icra eder."""
        try:
            qr_id = data.get("qr_id", "Bilinmiyor")
            mission = data.get(
                "gorev", {}
            )

            self.bridge_node.get_logger().info(
                f"🚀 [OTONOM BEYİN] QR {qr_id} Resmi Şifresi İşleniyor..."
            )
            self.send_gui_log(f"Çözümlenen JSON: {json.dumps(mission, ensure_ascii=False)}", "info")

            # --- Görevlere başlamadan önce hedefe varılmasını bekle ---
            self.bridge_node.get_logger().info(" ---> Görevlere başlamadan önce hedefe varılması bekleniyor...")
            self.send_gui_log(f"QR {qr_id} okundu. Hedefe varılması bekleniyor...", "info")
            while self.formation_mgr.state != 0:  # STATE_IDLE = 0
                self.socketio.sleep(1)
            self.bridge_node.get_logger().info(f" ---> Hedefe varıldı, QR {qr_id} görevleri başlatılıyor...")
            self.send_gui_log(f"Hedefe varıldı. QR {qr_id} görevleri icra ediliyor.", "success")
            # ----------------------------------------------------------------------------


            # 1. FORMASYON EMRİ
            formasyon_dict = mission.get("formasyon", {})
            if formasyon_dict.get("aktif"):
                tip = formasyon_dict.get("tip", "").lower()
                if tip == "okbasi":
                    tip = "arrowhead"
                elif tip == "cizgi":
                    tip = "line"
                elif tip == "v":
                    tip = "v"
                elif tip == "ucgen":
                    tip = "arrowhead"  # Üçgeni ok başı gibi kabul edebiliriz

                self.bridge_node.get_logger().info(
                    f" ---> EYLEM 1: Formasyon Değiştiriliyor ({tip.upper()})"
                )
                self.send_gui_log(f"EYLEM 1: Formasyon {tip.upper()} olarak ayarlanıyor...", "info")
                if not self.formation_mgr.active:
                    self.formation_mgr.start(formation_type=tip)
                else:
                    self.formation_mgr.formation_type = tip
                
                self.send_gui_log("Formasyon dizilimi için fiziksel süre bekleniyor...", "info")
                self.socketio.sleep(5)  # Dronların fiziksel olarak yerlerine geçmesi için süre ver

            # 2. İRTİFA EMRİ
            irtifa_dict = mission.get("irtifa_degisim", {})
            if irtifa_dict.get("aktif") and irtifa_dict.get("deger") is not None:
                hedef_alt = float(irtifa_dict.get("deger"))
                self.bridge_node.get_logger().info(
                    f" ---> EYLEM 2: İrtifa Değiştiriliyor ({hedef_alt}m)"
                )
                self.send_gui_log(f"EYLEM 2: İrtifa {hedef_alt}m olarak güncelleniyor...", "info")
                self.formation_mgr.virtual_alt = hedef_alt
                self.send_gui_log("İrtifa hedefine ulaşılması bekleniyor...", "info")
                
                # İrtifa için Akıllı Bekleme (Tolerans: 0.4m, Max 10sn)
                for _ in range(10):
                    all_reached = True
                    for d_id, d_data in self.bridge_node.drones.items():
                        current_alt = -d_data.get('local_z', -hedef_alt)
                        if abs(current_alt - hedef_alt) > 0.4:
                            all_reached = False
                            break
                    if all_reached:
                        break
                    self.socketio.sleep(1)
                
                self.socketio.sleep(1) # Stabilizasyon payı

            # 2.5 MANEVRA EMRİ
            manevra_dict = mission.get("manevra_pitch_roll", {})
            if manevra_dict.get("aktif"):
                pitch = float(manevra_dict.get("pitch_deg", 0))
                roll = float(manevra_dict.get("roll_deg", 0))
                
                self.bridge_node.get_logger().info(f" ---> EYLEM 2.5: Manevra Yapılıyor (Pitch: {pitch}°, Roll: {roll}°)")
                self.send_gui_log(f"EYLEM 2.5: Manevra İcrası (Pitch: {pitch}°, Roll: {roll}°)", "info")
                
                self.formation_mgr.set_maneuver(pitch, roll)
                
                # Manevranın fiziksel olarak tamamlanması için bekleme (Açılara göre drone'lar irtifa değiştirecek)
                self.socketio.sleep(4)
            else:
                # Manevra aktif değilse (veya bitmişse) düz duruşa geç
                if self.formation_mgr.swarm_pitch != 0.0 or self.formation_mgr.swarm_roll != 0.0:
                    self.formation_mgr.set_maneuver(0.0, 0.0)
                    self.socketio.sleep(3)

            # 3. BEKLEME EMRİ
            bekleme = mission.get("bekleme_suresi_s")
            if bekleme and bekleme > 0:
                self.bridge_node.get_logger().info(
                    f" ---> EYLEM 3: Görev Beklemesi ({bekleme} saniye)"
                )
                self.send_gui_log(f"EYLEM 3: {bekleme} saniye havada bekleniyor...", "warning")
                self.socketio.sleep(bekleme)

            # 3.5 SÜRÜDEN AYRILMA EMRİ
            ayrilma_dict = mission.get("suruden_ayrilma", {})
            if ayrilma_dict.get("aktif"):
                ayrilacak_id = ayrilma_dict.get("ayrilacak_drone_id")
                hedef_renk = ayrilma_dict.get("hedef_renk")
                
                pad_coords = getattr(self.bridge_node, 'pad_coordinates', {})
                if hedef_renk in pad_coords:
                    pad_x, pad_y = pad_coords[hedef_renk]
                    self.bridge_node.get_logger().info(f" ---> EYLEM 3.5: Drone {ayrilacak_id}, {hedef_renk} pede ({pad_x:.1f}, {pad_y:.1f}) inmek üzere ayrılıyor.")
                    self.send_gui_log(f"EYLEM 3.5: Drone {ayrilacak_id}, {hedef_renk} pede inmek için sürüden ayrılıyor!", "warning")
                    
                    # 1. Drone'u formasyondan muaf tut (ama boşluğunu koru)
                    if ayrilacak_id not in self.formation_mgr.detached_mask:
                        self.formation_mgr.detached_mask.append(ayrilacak_id)
                    
                    f_data = self.bridge_node.drones.get(ayrilacak_id)
                    if f_data:
                        master_lat = getattr(self.bridge_node, 'master_lat', f_data['gps']['lat'])
                        master_lon = getattr(self.bridge_node, 'master_lon', f_data['gps']['lon'])
                        
                        # Pedi Unified X,Y'den Lat,Lon'a çevir
                        target_lat = master_lat + (pad_x / 111111.0)
                        target_lon = master_lon + (pad_y / (111111.0 * math.cos(math.radians(master_lat))))
                        
                        f_ref_alt = f_data.get('ref_alt', 0.0)
                        target_amsl = f_ref_alt + 3.0 # İniş öncesi yaklaşma irtifası
                        
                        # 2. Pede doğru uçur
                        self.send_gui_log(f"Drone {ayrilacak_id} {hedef_renk} pedin üzerine gidiyor...", "info")
                        self.bridge_node.send_command(
                            ayrilacak_id, 192, # MAV_CMD_DO_REPOSITION
                            param1=2.0, param2=1.0, param4=0.0,
                            param5=target_lat, param6=target_lon, param7=target_amsl
                        )
                        
                        # Varmasını bekle
                        for _ in range(20):
                            dx = f_data.get('unified_x', 0) - pad_x
                            dy = f_data.get('unified_y', 0) - pad_y
                            if math.hypot(dx, dy) < 0.5:
                                break
                            self.socketio.sleep(1)
                        
                        # 3. İniş yap
                        self.send_gui_log(f"Drone {ayrilacak_id} pede iniş yapıyor...", "info")
                        self.bridge_node.send_command(ayrilacak_id, 21) # MAV_CMD_NAV_LAND
                        
                        # İnişin tamamlanmasını bekle
                        for _ in range(25):
                            if f_data.get('local_z', 0) > -0.3: # Yerde sayılır (PX4 disarm da edebilir)
                                break
                            self.socketio.sleep(1)
                            
                        # İniş tamamlandı, sapmayı hesapla ve logla
                        landed_x = f_data.get('unified_x', 0.0)
                        landed_y = f_data.get('unified_y', 0.0)
                        err_x = abs(landed_x - pad_x)
                        err_y = abs(landed_y - pad_y)
                        err_dist = math.hypot(err_x, err_y)
                        
                        self.send_gui_log(f"Drone {ayrilacak_id} {hedef_renk} pede başarıyla indi! | Hedef: ({pad_x:.1f}, {pad_y:.1f}) | İniş: ({landed_x:.1f}, {landed_y:.1f}) | Sapma: {err_dist:.2f}m", "success")
                        
                        # 4. 5 saniye bekle
                        self.send_gui_log(f"Drone {ayrilacak_id} {hedef_renk} pedde 5 saniye bekliyor.", "success")
                        self.socketio.sleep(5)
                        
                        # 5. Tekrar Kalkış yap ve eski irtifasına dön
                        self.send_gui_log(f"Drone {ayrilacak_id} kalkış için hazırlanıyor...", "info")
                        # 1. Modu AUTO.TAKEOFF'a al (Land modundan çıkmak ve Arm'a izin vermek için)
                        self.bridge_node.send_command(ayrilacak_id, 176, param1=1.0, param2=4.0, param3=2.0)
                        self.socketio.sleep(1.0)
                        
                        self.send_gui_log(f"Drone {ayrilacak_id} motorları çalıştırıyor (Arm)...", "info")
                        # 2. Force ARM (Güvenlik kilidini aşmak için param2=21196)
                        self.bridge_node.send_command(ayrilacak_id, 400, param1=1.0, param2=21196.0)
                        self.socketio.sleep(2.0) # Arming işlemi için süre tanı
                        
                        self.send_gui_log(f"Drone {ayrilacak_id} sürüye katılmak üzere dikey havalanıyor...", "info")
                        # 3. Kalkışı tetiklemek için tekrar AUTO.TAKEOFF komutu
                        self.bridge_node.send_command(ayrilacak_id, 176, param1=1.0, param2=4.0, param3=2.0)
                        
                        # Ekstra Güvence: MAV_CMD_NAV_TAKEOFF (22)
                        target_takeoff_alt = f_ref_alt + self.formation_mgr.virtual_alt
                        self.bridge_node.send_command(ayrilacak_id, 22, param5=float('nan'), param6=float('nan'), param7=target_takeoff_alt)
                        
                        # Havalanmasını bekle (Daha uzun kontrol)
                        for _ in range(40): # Max 20 saniye
                            if f_data.get('local_z', 0) < -1.5:
                                break
                            self.socketio.sleep(0.5)
                            
                        # 6. Sürüye tekrar katıl (Mask'ı kaldır, formation manager onu geri çekecek)
                        self.send_gui_log(f"Drone {ayrilacak_id} görevini tamamladı, sürüdeki pozisyonuna geri dönüyor.", "success")
                        if ayrilacak_id in self.formation_mgr.detached_mask:
                            self.formation_mgr.detached_mask.remove(ayrilacak_id)
                        
                        # Formasyona tam yerleşmesini dinamik olarak bekle
                        self.socketio.sleep(2) # İlk hareketin başlaması için pay
                        for _ in range(120): # Max 60 saniye
                            err = self.formation_mgr.drone_errors.get(ayrilacak_id, 999)
                            current_alt = -f_data.get('local_z', -self.formation_mgr.virtual_alt)
                            alt_err = abs(current_alt - self.formation_mgr.virtual_alt)
                            
                            if err < 0.5 and alt_err < 0.5: # Formasyondaki hedefine 3D olarak yaklaştıysa yerleşmiş sayılır
                                break
                            self.socketio.sleep(0.5)
                            
                        self.send_gui_log(f"Drone {ayrilacak_id} sürüye başarıyla tam entegre oldu! Görev devam ediyor.", "success")
                else:
                    self.bridge_node.get_logger().error(f"HATA: {hedef_renk} pedin konumu henüz bulunamadı!")
                    self.send_gui_log(f"HATA: {hedef_renk} ped konumu bilinmiyor! Görev atlandı.", "error")

            # Bekleme bittikten sonra bir sonraki hedefe geçmeden önce manevrayı sıfırla (düz seyir için)
            if self.formation_mgr.swarm_pitch != 0.0 or self.formation_mgr.swarm_roll != 0.0:
                self.send_gui_log("Manevra tamamlandı. Sürü düz uçuş pozisyonuna geçiyor...", "info")
                self.formation_mgr.set_maneuver(0.0, 0.0)
                self.socketio.sleep(3)

            # 4. SONRAKİ HEDEFE SEYİR
            next_qr_dict = data.get("sonraki_qr", {})
            # Takım 1 (team_1) olduğumuzu varsayarak rotayı çekiyoruz
            sonraki_qr_id = next_qr_dict.get("team_1", 0)

            if sonraki_qr_id in self.qr_coordinates and sonraki_qr_id != 0:
                hedef_x, hedef_y = self.qr_coordinates[sonraki_qr_id]
                self.bridge_node.get_logger().info(
                    f" ---> EYLEM 4: Seyir Başlıyor. Hedef QR {sonraki_qr_id} (X:{hedef_x}, Y:{hedef_y})"
                )
                self.formation_mgr.set_target(hedef_x, hedef_y)

            elif sonraki_qr_id == 0:
                self.bridge_node.get_logger().info(
                    " ---> EYLEM 4: Şartname Rotası Bitti! Ana Üsse (Home: 0.0, 0.0) dönülüyor."
                )
                self.send_gui_log("Görev Sonu: Ana Üsse (0,0) Dönüş ve Toplu İniş Başladı!", "info")
                self.formation_mgr.set_target(0.0, 0.0)
                
                # Hedefe varana kadar bekle (state 0 olunca hedefe varılmış demektir)
                while self.formation_mgr.state != 0:
                    self.socketio.sleep(1)
                
                self.socketio.sleep(2) # Stabilizasyon payı
                
                self.bridge_node.get_logger().warn(
                    "!!! ANA ÜSSE ULAŞILDI: TÜM SÜRÜ İÇİN İNİŞ EMRİ VERİLİYOR !!!"
                )
                self.send_gui_log("Ana Üsse Ulaşıldı: Tüm sürü için İNİŞ EMRİ verildi!", "success")
                
                self.formation_mgr.stop()
                self.alt_locks.clear()
                self.alt_protectors.clear()
                
                for d_id in list(self.bridge_node.drones.keys()):
                    self.bridge_node.send_command(d_id, 21)  # MAV_CMD_NAV_LAND

            else:
                self.bridge_node.get_logger().info(
                    " ---> EYLEM 4: Sonraki Hedef Bulunamadı. Olduğun yerde asılı kal."
                )

            self.bridge_node.get_logger().info(
                f"✅ [OTONOM BEYİN] QR {qr_id} Görev Zinciri Kusursuz Tamamlandı!"
            )

        except Exception as e:
            self.bridge_node.get_logger().error(
                f"❌ [HATA] Görev icra edilirken kritik hata: {str(e)}"
            )
        finally:
            # Görev bitti, bir sonraki QR kodu okumak için kilidi aç
            self.socketio.sleep(2)
            self.is_executing = False
            self.bridge_node.get_logger().info(
                "🔓 [SİSTEM] Görev kilidi açıldı. Yeni QR taranabilir."
            )
