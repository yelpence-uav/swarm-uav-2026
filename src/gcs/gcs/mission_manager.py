import json
from datetime import datetime

class MissionManager:
    def __init__(self, bridge_node, formation_mgr, socketio):
        self.bridge_node = bridge_node
        self.formation_mgr = formation_mgr
        self.socketio = socketio
        self.is_executing = False # Aynı anda iki görev yapılmasını engelleyen güvenlik kilidi
        
        # Gazebo (X,Y) ile PX4 (X,Y) uyuşmazlığını çözen yeni koordinatlar
        self.qr_coordinates = {
            1: (0.00, 8.00),    # Eski: (8.0, 0.0) -> Manuel testindeki mükemmel ayar!
            2: (0.00, -8.00),   # Eski: (-8.0, 0.0)
            3: (6.93, -4.00),   # Eski: (-4.0, 6.93)
            4: (-6.93, 4.00),   # Eski: (4.0, -6.93)
            5: (-6.93, -4.00),  # Eski: (-4.0, -6.93)
            6: (6.93, 4.00),    # Eski: (4.0, 6.93)
            0: (0.00, 0.00)     # Merkez
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
        self.socketio.emit('gui_log', {'msg': msg, 'level': level, 'time': timestamp})

    def process_qr_task(self, qr_text):
        """Kameradan gelen metni JSON'a çevirip Görev Zincirini başlatır."""
        if self.is_executing:
            self.bridge_node.get_logger().warn("Görev reddedildi: Zaten bir işlem yürütülüyor.")
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
            self.bridge_node.get_logger().error("HATA: Okunan QR metni geçerli bir JSON formatında değil!")

    def execute_mission(self, data):
        """Teknofest şartnamesindeki orijinal JSON formatıyla emirleri icra eder."""
        try:
            qr_id = data.get("qr_id", "Bilinmiyor")
            mission = data.get("mission", {}) # Artık 'gorev' değil 'mission' kelimesi geliyor
            
            self.bridge_node.get_logger().info(f"🚀 [OTONOM BEYİN] QR {qr_id} Resmi Şifresi İşleniyor...")

            # --- ÖZEL GÖREV: QR 6 -> TOPLU İNİŞ ---
            if str(qr_id) == "6":
                self.bridge_node.get_logger().warn("!!! QR 6 ALGILANDI: TÜM SÜRÜ İÇİN İNİŞ EMRİ VERİLİYOR !!!")
                self.send_gui_log("🎯 QR 6: TÜM SÜRÜ İÇİN İNİŞ EMRİ VERİLDİ!", "warning")
                
                # 1. Önce formasyon navigasyonunu durdur (Offboard'dan çıkabilmeleri için)
                self.formation_mgr.stop()
                
                # 2. Sistemdeki tüm irtifa kilitlerini temizle (Hovering problem fix)
                self.alt_locks.clear()
                self.alt_protectors.clear()
                self.send_gui_log("🔓 Tüm irtifa kilitleri temizlendi.", "success")
                
                # 3. Sistemdeki tüm aktif dronlara iniş emri gönder
                for d_id in list(self.bridge_node.drones.keys()):
                     self.bridge_node.send_command(d_id, 21) # MAV_CMD_NAV_LAND
                return # Görevin geri kalanını (seyir vb.) çalıştırma
            # -------------------------------------

            # 1. FORMASYON EMRİ (Artık sözlük değil, direkt String geliyor: "OKBASI")
            formasyon_tipi = mission.get("formasyon")
            if formasyon_tipi:
                tip = formasyon_tipi.lower()
                if tip == "okbasi": tip = "arrowhead"
                elif tip == "cizgi": tip = "line"
                elif tip == "v": tip = "v"
                elif tip == "ucgen": tip = "arrowhead" # Üçgeni ok başı gibi kabul edebiliriz
                
                self.bridge_node.get_logger().info(f" ---> EYLEM 1: Formasyon Değiştiriliyor ({tip.upper()})")
                if not self.formation_mgr.active:
                    self.formation_mgr.start(formation_type=tip)
                else:
                    self.formation_mgr.formation_type = tip
                self.socketio.sleep(3) # Dronların hizalanması için fiziksel süre ver

            # 2. İRTİFA EMRİ (Artık direkt sayı geliyor: 15, 20 vb.)
            irtifa = mission.get("irtifa_degisim")
            if irtifa is not None:
                hedef_alt = float(irtifa)
                self.bridge_node.get_logger().info(f" ---> EYLEM 2: İrtifa Değiştiriliyor ({hedef_alt}m)")
                self.formation_mgr.virtual_alt = hedef_alt
                self.socketio.sleep(4) # Tırmanış/Alçalış için fiziksel süre ver

            # 3. BEKLEME EMRİ
            bekleme = mission.get("bekleme_suresi_s")
            if bekleme and bekleme > 0:
                self.bridge_node.get_logger().info(f" ---> EYLEM 3: Görev Beklemesi ({bekleme} saniye)")
                self.socketio.sleep(bekleme)

            # 4. SONRAKİ HEDEFE SEYİR (Artık 'sonraki_qr' değil 'next_qr' geliyor)
            next_qr_dict = data.get("next_qr", {})
            # Takım 1 (team_1) olduğumuzu varsayarak rotayı çekiyoruz
            sonraki_qr_id = next_qr_dict.get("team_1", 0) 
            
            if sonraki_qr_id in self.qr_coordinates and sonraki_qr_id != 0:
                hedef_x, hedef_y = self.qr_coordinates[sonraki_qr_id]
                self.bridge_node.get_logger().info(f" ---> EYLEM 4: Seyir Başlıyor. Hedef QR {sonraki_qr_id} (X:{hedef_x}, Y:{hedef_y})")
                self.formation_mgr.set_target(hedef_x, hedef_y)
                
            elif sonraki_qr_id == 0:
                self.bridge_node.get_logger().info(" ---> EYLEM 4: Şartname Rotası Bitti! Ana Üsse (Home: 0,0) dönülüyor.")
                hedef_x, hedef_y = self.qr_coordinates[0]
                self.formation_mgr.set_target(hedef_x, hedef_y)
            else:
                self.bridge_node.get_logger().info(" ---> EYLEM 4: Sonraki Hedef Bulunamadı. Olduğun yerde asılı kal.")

            self.bridge_node.get_logger().info(f"✅ [OTONOM BEYİN] QR {qr_id} Görev Zinciri Kusursuz Tamamlandı!")
        
        except Exception as e:
            self.bridge_node.get_logger().error(f"❌ [HATA] Görev icra edilirken kritik hata: {str(e)}")
        finally:
            # Görev bitti, bir sonraki QR kodu okumak için kilidi aç
            self.socketio.sleep(2) 
            self.is_executing = False
            self.bridge_node.get_logger().info("🔓 [SİSTEM] Görev kilidi açıldı. Yeni QR taranabilir.")
