"""packet_parser.py — ESP32 UART paketlerini çözümleme.

UART çerçevesi (COBS çözüldükten sonra):
    [tip 1B][iha_id 1B][payload 16B][crc_hi 1B][crc_lo 1B]  = 20 byte
CRC16-CCITT ilk 18 bayt (tip + iha_id + payload) üzerinden hesaplanır.
CRC big-endian gönderilir: crc_hi = (crc >> 8), crc_lo = (crc & 0xFF).

payload struct'ları firmware'deki mesh_config.h ile BİREBİR aynıdır
(little-endian, packed). Bir alan değişirse iki taraf birlikte
güncellenmelidir.
"""

from dataclasses import dataclass
import struct

from .crc16 import crc16

# ===== Paket tipleri (firmware mesh_config.h ile aynı) =====
TIP_KOMUT = 0x02
TIP_POSE = 0x04
TIP_GOREV = 0x05

# 🔴 GOREV 2 BASLAT — 31 Agustos 2026. TIP_GOREV'e YENI BIR TIP; yeni mesaj
# tipi ACILMADI, paket buyumedi (_GOREV_FMT'te 12 bayt rezerv zaten vardi).
#
# NEDEN VAR: gorev YKI'den `TriggerMission` ROS SERVISIYLE baslatiliyordu ve
# baslat.sh `ROS_LOCALHOST_ONLY=1` ile kosuyor — yani o servis YKI
# laptopundan GORUNMUYOR (olculdu: `ros2 service list` icinde yok). Sonuc:
# YKI'deki "Gorev 2 BASLAT" butonu ucaklara ULASAMIYORDU; 31 Agustos gecesi
# gorev SSH ile elle tetiklendi.
#
# Bu tip mesh'ten gidiyor, yani Wi-Fi'ye bagimli DEGIL. Bir ucaga ulasmasi
# yeter: o ucak SEMI_AUTONOMOUS'a gecince durum paketindeki
# DURUM2_BAYRAK_GOREV_YARI_OTONOM biti digerlerine yayiliyor (G2-K11).
#
# ⚠️ Alici tarafta ARM ETMEZ. Gorev baslatmak yalniz G2-K10'un UCUNCU
# KAPISINI acar; armlama yetkisi hala SwD'de ve kendi kapilarinda.
GOREV_TIP_G2_BASLAT = 0x20

# GOREV 2 DURDUR — kumanda yetkisini geri alir (G2-K10 ucuncu kapiyi KAPATIR).
#
# ⚠️ UCAN SURUYU DURDURMAZ. mode_manager bir kez READY'ye gectikten sonra
# mission_state'i yeniden okumuyor; bu komut yalniz YENI kalkislari engeller.
# Havadaki suruyu indirmenin yolu SwD (madde 24) ya da kill switch.
#
# 🔴 YAYIN OLARAK GIDER ve alicida KISA BIR SOGUMA baslatir. Sebep: durum
# paketindeki DURUM2_BAYRAK_GOREV_YARI_OTONOM biti komsulari tetikliyor
# (G2-K11). Tek ucak dursaydi, hala 8'de olan komsusunun biti onu HEMEN
# yeniden baslatirdi. Soguma, bir ucak DURDUR paketini kacirsa bile
# digerlerinin geri tetiklenmesini onluyor.
GOREV_TIP_G2_DURDUR = 0x21
TIP_RENK = 0x06
TIP_DURUM = 0x07
TIP_ORIGIN = 0x08
TIP_LEADER_HB = 0x09
TIP_ELECTION = 0x0A
TIP_HEARTBEAT = 0x03
TIP_VERSION = 0x0B
TIP_RTK = 0x0C
TIP_SWARM_STATE = 0x0D
TIP_QR_DATA = 0x0E
TIP_FAILSAFE = 0xFA  # mesh kopunca gelen failsafe (fail_safe.h)
TIP_QR_COORDS = 0x0F  # YKİ'den gelen QR konumları (her nokta ayrı çerçeve)
TIP_GOTO = 0x10  # YKİ'den gelen guided tekil nokta-git (goto_veri_t)
# 0x11-0x15: sürü koordinasyonu (30 Temmuz, docs/MESH_PROTOKOL_KARARLARI.md).
# Firmware mesh_config.h ile BİREBİR aynı olmalı; orada da aynı uyarı var.
TIP_FORMASYON = 0x11  # lider -> sürü: formasyon tarifi (5 Hz)
TIP_FORMASYON_DEVAM = 0x12  # 5-8 ajan için slot listesi devamı
TIP_FORM_OFSET = 0x13  # yalnız CUSTOM: açık slot offsetleri
TIP_QR_GOREV = 0x14  # QR'ı okuyan drone -> sürü: çözülmüş görev
TIP_QR_HAM = 0x15  # yalnız ayrıştırma hatasında: ham metin dilimi

# TIP_OLAY (0x16) — uçak olaylarını YKİ'ye taşır (27 Ağustos 2026).
#
# NEDEN YENİ BİR TİP: bu dosyanın §DURUM2 notunda yazdığı gibi mesh
# protokolünde olay tipi YOKTU; körlük alarmı o yüzden DURUM paketine bit
# olarak sıkıştırılmıştı. Bit tek bir "var/yok" taşıyor; operatörün istediği
# "her drone'un olay defteri" için tip + şiddet + bağlam gerekiyor.
#
# METİN TAŞIMIYOR: 16 baytlık yük ~16 karakter eder, cümle taşımaz. Bunun
# yerine SystemEvent.msg'deki 60 tanımlı EVENT_* kodu taşınıyor ve metni YKİ
# üretiyor — bant genişliği ödemeden uzun, Türkçe, anlamlı mesaj.
#
# Tip tablosu tavanı MESH_TIP_TABLO_BOYU = 24; 0x16 = 22, yer var.
TIP_OLAY = 0x16

# Failsafe türleri (fail_safe.h)
FAILSAFE_TIP_UYARI = 0x01
FAILSAFE_TIP_RTL = 0x02
FAILSAFE_TIP_LAND = 0x03

# Mesh kimlik sabitleri (mesh_config.h)
BAZ_ID = 99          # RTK UART sentinel'i, mesh kimliği DEĞİL
BAZ_MESH_ID = 10     # baz istasyonu mesh kimliği
MESH_MAX_NODES = 8

# ===== Payload struct formatları (little-endian, packed) =====
# POSE 18B (vz), diğer tipler 16B.
_POSE_FMT = '<iihhhhh'       # lat, lon, alt_dm, heading, vx, vy, vz
# REV C: firmware mesh_config.h::durum_veri_t ile BİREBİR.
# 16 bayt sabit; float voltaj ve altı ayrı bool bayt sıkıştırılarak
# kill switch / RC link / uçuş modu / uydu / HDOP'a yer açıldı.
_DURUM_FMT = '<BBBBBBBBBbBB4x'  # bkz. DurumVeri alanları

# durum_veri_t.bayraklar bit maskeleri (firmware DURUM_BAYRAK_* ile aynı).
DURUM_BAYRAK_ARMED = 0x01
DURUM_BAYRAK_EKF_OK = 0x02
DURUM_BAYRAK_IMU_OK = 0x04
DURUM_BAYRAK_MAG_OK = 0x08
DURUM_BAYRAK_BARO_OK = 0x10
DURUM_BAYRAK_MESH_LINK = 0x20
DURUM_BAYRAK_KILL = 0x40
DURUM_BAYRAK_RC_LINK = 0x80

# İkinci bayrak baytı (bayraklar2) — ilk bayt 8 bitle doldu.
DURUM2_BAYRAK_READY_TO_ARM = 0x01
# ORIGIN_SYNCED mesh'ten GEÇMİYORDU ve baz istasyonu onu UYDURUYORDU:
# _isle_pose, kendi GPS→NED çevirimini yapabildiği için komşunun bayrağına
# True yazıyordu. Oysa bayrağın anlamı "O DRONE'UN PX4'ü ortak origin'i
# uyguladı mı" — bambaşka bir şey. 1 Ağustos 22:18'de YKİ origin_synced=True
# gösterirken PX4'ün çerçevesi 12.1 m kayıktı ve ylp01 kaçtı.
# Bayrak artık drone'un KENDİ doğrulamasından (px4_bridge._origin_dogrula)
# geliyor. Firmware bayraklar2'yi opak taşır — flash GEREKMEZ.
DURUM2_BAYRAK_ORIGIN_SYNCED = 0x02
# KACINMA KORU — P0.16, 21 Agustos 2026.
#
# Bu drone komsularindan EN AZ BIRINI goremiyorsa (mesh tek yonlu olmus
# olabilir) 1 olur. Anlami: "o komsuya karsi carpisma korumam YOK".
#
# NEDEN BAYRAK, NEDEN OLAY DEGIL: mesh protokolunde TIP_EVENT yok ve
# eklemek uc ESP'yi yeniden flashlamak demek. Oysa DURUM paketini PI
# olusturuyor (esp32_bridge._yayinla_kendi_durum -> durum_paketle), ESP
# yalniz bayt tasiyor. Yani bos bir bit kullanmak TAMAMEN ROS TARAFI:
# firmware degismiyor, paket boyutu ayni (16 bayt), eski alicilar biti
# yok sayar (geriye uyumlu).
#
# Ayrica semantik olarak da DOGRU: "su an koruyamiyorum" bir DURUM,
# bir olay degil. Kendiliginden temizlenir ve YKI surekli gosterebilir.
DURUM2_BAYRAK_KACINMA_KORU = 0x04

# 🔴 HOME_SET — 31 Agustos 2026'da eklendi, SAHADA OLCULEN bir kilitlenmeyi
# cozmek icin. mission_fsm PREFLIGHT->SEMI_AUTONOMOUS gecisi
# `all_agents_home_set()` istiyor ve komsularin durumunu MESH'ten okuyor.
# home_set mesh paketinde YOKTU, yani alici tarafta hep False kaliyordu:
#
#     ylp01 KENDI ic durumu : home_set = true
#     ylp00'in mesh kopyasi : home_set = false     <- kaybolan bilgi
#
# Sonuc: PREFLIGHT HICBIR ZAMAN gecilemez, Gorev 2 HIC baslayamaz ve
# hicbir yerde hata gorunmez. G0 madde 18'in aynı sinifi.
#
# Paket boyutu DEGISMEDI (bayraklar2'de bes bos bit vardi) ve firmware
# payload'i yalnizca tasiyor. Iki yonde de geriye donuk uyumlu:
# eski gonderici -> bit 0 -> bugunku davranis; eski alici -> biti yok sayar.
DURUM2_BAYRAK_HOME_SET = 0x08

# 🔴 GOREV YARI OTONOM — 31 Agustos 2026, SAHADA OLCULEN ikinci kilitlenme.
# Gorev YKI'den TriggerMission servisiyle baslatiliyor ve o servis
# ROS_LOCALHOST_ONLY=1 yuzunden YALNIZ KENDI UCAGINA ulasiyor. Sahada
# olculdu: ylp00 mission_state=8 oldu ve SwD ile armlandi, ylp01/ylp02
# mission_state=1'de kaldi ve kalkisi REDDETTI —
#     "SwD KALKIS istendi ama YETKI YOK (mission_state=1, beklenen 8)"
# Yani suru BOLUNDU. G2-K10'un kapisi eksik kalkisi onledi (dogru
# davranis) ama gorev de hic baslayamadi.
#
# Bu bit gorev durumunu mesh'e tasiyor: bir ucak SEMI_AUTONOMOUS'a
# gecince komsulari GORUR ve KENDI preflight'ini calistirip KENDI
# kararini verir. Dagitik kalir — komsu "sen de gec" DEMEZ, yalniz
# "ben gectim" der.
#
# ⚠️ NEDEN EVENT_MISSION_STARTED KULLANILMIYOR: o olay mesh'ten zaten
# geciyor AMA agent_fsm onu ARM'a ceviriyor (agent_fsm_node.py:304) —
# 30 Agustos saha olayinin tetigi tam olarak oydu. Gorev baslatmak
# ARMLAMAK DEGILDIR; ayri kanal sart.
DURUM2_BAYRAK_GOREV_YARI_OTONOM = 0x10
_RENK_FMT = '<Bii7x'         # renk, lat, lon, rezerv[7]
# 🔴 GOREV 2 ARALIK/IRTIFA — madde 29, 31 Agustos 2026. Rezervden UC bayt
# alindi; paket 16 BAYTTA KALDI, firmware DEGISMEDI (ayni numara
# durum_paketle'de de kullanildi). Geriye kalan rezerv: 9 bayt.
#
# NEDEN param1/param2 KULLANILMADI: param2 int8, yani desimetre ile en
# fazla 12.7 m irtifa tasir — sartname ornegi 15 m. Ayrica ikisi de
# 'genel amacli' alanlar; adlandirilmis alan okunurlugu artiriyor.
#
# SIFIR = BELIRTILMEDI. Eski surum gonderici rezervi sifir birakir; alici
# o zaman KENDI varsayilanini korur. Geriye donuk uyumlu.
_GOREV_FMT = '<BBbBBH9x'
#              |||| | |  tip, param1, param2, bekleme,
#              |||| | +- irtifa_dm  (uint16, 0.1 m; 0 = belirtilmedi)
#              |||| +--- aralik_dm  (uint8,  0.1 m; 0 = belirtilmedi)
#              rezerv[9]
_ORIGIN_FMT = '<iiiI'        # lat_1e7, lon_1e7, alt_mm, sequence
# target_id (offset 10, rezerv[0]): guided komutun HEDEF drone'u. Mesh çerçevesi
# id taşımaz (base düşürür, drone MAC'ten kaynak id üretir), o yüzden hedef
# payload'da gider. Firmware bunu opak rezerv görür — flash gerekmez.
# talep_formasyon (offset 11) + talep_spacing_dm (offset 12): 30 Temmuz kusur
# düzeltmesi. SwarmControlCommand.requested_formation ve requested_spacing_m
# mesh'ten GEÇMİYORDU — köprü yalnız KOMUT_FLAG_FORMATION_CHANGE bayrağını
# taşıyordu, iki alan alıcıda ROS varsayılanında (0) kalıyordu. Sonuç:
# "formasyon değiştir" gidiyor, hangi formasyon bilgisi kayboluyor ve
# spacing=0.0 ile compute_slot_offsets() ValueError atıyordu.
_KOMUT_FMT = '<BBhhhhBBB3x'  # alt_tip, flags, roll/pitch/yaw/throttle x100,
#                              target_id, talep_formasyon, talep_spacing_dm
_LEADER_HB_FMT = '<BIBBB8x'  # leader_id, seq, round, agent_count, mission
_ELECTION_FMT = '<BBBBIBBBBH2x'
# leader, round, reason, trigger, seq, ids[4], incarnation, rezerv[2]
# incarnation 30 Temmuz'da rezerv[4]'ün ilk 2 baytından alındı; toplam boyut
# 16 bayt DEĞİŞMEDİ, o yüzden firmware'in sizeof(election_veri_t) kullanımı
# etkilenmiyor ve ESP'ler yeniden flaşlanmadan çalışır.
_QR_FMT = '<BIii3x'          # drone_id, action_id, lat, lon, rezerv[3]
_SWARM_STATE_FMT = '<BBBBI8x'  # mission_id, fsm, leader, formation, timestamp
_QR_COORD_FMT = '<BBii6x'    # qr_id, toplam, lat_1e7, lon_1e7, rezerv[6]
_GOTO_FMT = '<hhhhBB6x'      # kuzey_dm, dogu_dm, asagi_dm, yaw_ddeg, bayraklar, target_id, rezerv[6]
# --- Sürü koordinasyonu (firmware mesh_config.h struct'larıyla BİREBİR) ---
# Her biri 16 bayt; test_esp32_parser içinde struct.calcsize ile doğrulanıyor.
_FORMASYON_FMT = '<BhhhhBBBBBBB'
# tip|bit7=devam, merkez kuzey/doğu/aşağı dm, heading ddeg, spacing_dm,
# maks_hiz_x10, kanat_alfa_deg, slot_ajan[4]
_FORMASYON_DEVAM_FMT = '<BBBB12x'   # slot_ajan[4] (slot 4..7), rezerv[12]
_FORM_OFSET_FMT = '<BBhhhhhh2x'     # slot_bas, slot_sayisi, ofset_dm[6], rezerv[2]
_QR_GOREV_FMT = '<BBBBBBbbbBBBB3x'
# qr_id, qr_seq, sonraki_qr, bayraklar, formasyon_tipi, spacing_dm,
# pitch/roll/yaw_deg (int8), irtifa_m, bekleme_s, ayrilan_ajan,
# renk_ve_bekleme, rezerv[3]
_QR_HAM_FMT = '<BBB13s'             # hata_kodu, parca_no, toplam_parca, dilim[13]

# olay_veri_t — 16 bayt, paket BUYUMUYOR.
#   olay_tipi B · siddet B · kaynak_id B · hedef_id B · deger_x100 h
#   sira_no B · modul_kodu B · zaman_ms I · ek1 H · ek2 H
# deger float32 DEGIL int16 x100: §1.2 birim kurali (kodda yeni kodlama
# icat etmiyoruz). Aralik +-327.67, cozunurluk 0.01 — batarya %, mesafe m,
# aci derece hepsi bu aralikta.
_OLAY_FMT = '<BBBBhBBIHH'

# formasyon_tipi bit7: devam paketi geliyor (5+ ajan)
FORMASYON_BAYRAK_DEVAM = 0x80

# qr_gorev_veri_t.bayraklar bitleri
QR_BAYRAK_VALID = 0x01
QR_BAYRAK_DECODED = 0x02
QR_BAYRAK_FORMASYON = 0x04     # formation_active
QR_BAYRAK_MANEVRA = 0x08       # maneuver_active
QR_BAYRAK_IRTIFA = 0x10        # altitude_active
QR_BAYRAK_AYRILMA = 0x20       # detach_active
QR_BAYRAK_GOREV_BITTI = 0x40   # complete_mission

# qr_ham_veri_t.hata_kodu — qr_detector.py'deki altı hata yolu
QR_HATA_JSON = 1     # json.loads patladı
QR_HATA_SEMA = 2     # zorunlu alanlar eksik (qr/w/mis/team)
QR_HATA_SLOT = 3     # takım slotu tabloda yok
QR_HATA_TABLO = 4    # takım tablosu girdisi bozuk
QR_HATA_PAKET = 5    # paket numarası listede yok
QR_HATA_KOMUT = 6    # _apply_command hatası

QR_HAM_DILIM_BOYU = 13   # qr_ham_veri_t.dilim
QR_HAM_MAKS_PARCA = 4    # en fazla 4 parça = 52 karakter

# Mesh slot kapasitesi. İlk paket 4 slot taşır, devam paketi 4 daha.
FORMASYON_SLOT_PAKET = 4
FORMASYON_MAKS_AJAN = 8          # MESH_MAX_NODES ile aynı
FORM_OFSET_SLOT_PAKET = 2        # form_ofset_veri_t paket başına 2 slot

# Joystick komutu bayrak bitleri (komut_veri_t.flags için).
# DEADMAN_PRESSED: SwarmControlCommand.deadman_pressed mesh üzerinden
# taşınması için. False ise downstream motion uygulamaz (msg dosyası
# kuralı). Bayrak biti olmadığında her komut sessizce reddedilir.
KOMUT_FLAG_TAKEOFF = 0x01
KOMUT_FLAG_LAND = 0x02
KOMUT_FLAG_RTL = 0x04
KOMUT_FLAG_EMERGENCY = 0x08
KOMUT_FLAG_FORMATION_CHANGE = 0x10
KOMUT_FLAG_DEADMAN_PRESSED = 0x20
# Guided (YKİ tekil komut) ek bayrakları — takeoff/land/rtl yukarıdakiyle ortak.
KOMUT_FLAG_ARM = 0x40
KOMUT_FLAG_DISARM = 0x80

# SwarmControlCommand.mode değerleri
KOMUT_MODE_SWARM_MOVEMENT = 1
KOMUT_MODE_MANEUVER = 2
KOMUT_MODE_GUIDED = 3  # YKİ tekil guided komut; drone FSM'i baypas edip px4_bridge'e çevirir

# goto_veri_t.bayraklar bit maskeleri (firmware GOTO_BAYRAK_* ile aynı).
GOTO_BAYRAK_YAW_GECERLI = 0x01

_FRAME_MIN = 4  # tip + iha_id + crc16 (payload değişken)

# F3: mesh-liveness yalnızca bilinen peer'dan bilinen telemetri tipiyle
# tazelenir. RTK (0x0C) ve VERSION dışarıda; RTK ayrı izlenir.
_LIVENESS_TIPLERI = frozenset({
    TIP_KOMUT, TIP_POSE, TIP_GOREV, TIP_RENK, TIP_DURUM, TIP_ORIGIN,
    TIP_LEADER_HB, TIP_ELECTION, TIP_HEARTBEAT, TIP_SWARM_STATE, TIP_QR_DATA,
    TIP_GOTO,
})


def liveness_tazeler(iha_id: int, tip: int) -> bool:
    """Bu (iha_id, tip) mesh-liveness zaman damgasını tazelemeli mi (F3).

    Bilinen peer (1..MESH_MAX_NODES veya BAZ_MESH_ID) VE bilinen telemetri
    tipi gerekir. RTK sentinel'i (99) ve bilinmeyen tipler tazelemez.
    """
    peer_ok = 1 <= iha_id <= MESH_MAX_NODES or iha_id == BAZ_MESH_ID
    return peer_ok and tip in _LIVENESS_TIPLERI


@dataclass
class PoseVeri:
    """TIP_POSE payload — komşu drone'un konum/hız verisi."""

    lat: int       # 1e-7 derece
    lon: int       # 1e-7 derece
    alt_dm: int    # desimetre
    heading: int   # 0.1 derece
    vx: int        # cm/s
    vy: int        # cm/s
    vz: int        # cm/s


@dataclass
class DurumVeri:
    """TIP_DURUM payload — komşu drone'un durum/sağlık verisi.

    Firmware'in durum kodu 14 değerli enum'dur (AgentStatus.STATE_*
    ile eşleşir). Bkz. esp32_bridge_node._DURUM_STATE_MAP.
    """

    drone_id: int
    durum: int              # 0=BILINMIYOR..13=STANDBY (14 değerli enum)
    bayraklar: int          # DURUM_BAYRAK_* bit alanı
    ucus_modu: int          # AgentStatus.FLIGHT_MODE_* (PX4'ün bildirdiği)
    gps_fix_type: int       # 0-6 (4=DGPS, 5=RTK float, 6=RTK fixed)
    gps_uydu: int           # görünen uydu sayısı
    gps_hdop_x10: int       # HDOP*10, 255 = bilinmiyor
    battery_pct: int        # 0-100
    battery_volt_x10: int   # volt*10
    rssi: int               # dBm
    mesh_komsu_sayisi: int  # aktif mesh node sayısı
    bayraklar2: int         # DURUM2_BAYRAK_* bit alanı

    # --- bit alanı okuyucuları: çağıran taraf maskeyle uğraşmasın ---
    @property
    def armed(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_ARMED)

    @property
    def ekf_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_EKF_OK)

    @property
    def imu_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_IMU_OK)

    @property
    def mag_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_MAG_OK)

    @property
    def baro_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_BARO_OK)

    @property
    def mesh_link_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_MESH_LINK)

    @property
    def kill_switch_active(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_KILL)

    @property
    def rc_link_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_RC_LINK)

    @property
    def ready_to_arm(self) -> bool:
        """PX4 PREARM_CHECK: emniyet anahtarı dahil tüm ön-kontroller geçti mi."""
        return bool(self.bayraklar2 & DURUM2_BAYRAK_READY_TO_ARM)

    @property
    def origin_synced(self) -> bool:
        """O drone'un PX4'ü ortak origin'i UYGULADI mı (ölçerek doğrulandı).

        Kaynağı px4_bridge._origin_dogrula: GPS'in ortak origin'e göre
        vermesi gereken NED ile PX4'ün bildirdiği yerel NED karşılaştırılır.
        """
        return bool(self.bayraklar2 & DURUM2_BAYRAK_ORIGIN_SYNCED)

    @property
    def kacinma_koru(self) -> bool:
        """Bu drone komsularindan birini goremiyor (P0.16)."""
        return bool(self.bayraklar2 & DURUM2_BAYRAK_KACINMA_KORU)

    @property
    def home_set(self) -> bool:
        """PX4 HOME konumu kuruldu mu (mission_fsm preflight sarti)."""
        return bool(self.bayraklar2 & DURUM2_BAYRAK_HOME_SET)

    @property
    def gorev_yari_otonom(self) -> bool:
        """Bu ucagin mission_fsm'i SEMI_AUTONOMOUS'ta mi (Gorev 2)."""
        return bool(self.bayraklar2 & DURUM2_BAYRAK_GOREV_YARI_OTONOM)

    @property
    def battery_volt(self) -> float:
        """Voltaj, 0.1 V çözünürlükte."""
        return self.battery_volt_x10 / 10.0

    @property
    def gps_hdop(self) -> float:
        """HDOP; 255 sentineli 99.9 (kötü) olarak döner."""
        return 99.9 if self.gps_hdop_x10 == 255 else self.gps_hdop_x10 / 10.0


@dataclass
class RenkVeri:
    """TIP_RENK payload — tespit edilen renk bölgesi koordinatı."""

    renk: int      # RENK_KIRMIZI=1, RENK_MAVI=2
    lat: int       # 1e-7 derece
    lon: int       # 1e-7 derece


@dataclass
class GorevVeri:
    """TIP_GOREV payload — sürüye gelen görev komutu."""

    tip: int
    param1: int
    param2: int
    bekleme_suresi_s: int
    # Madde 29 — Görev 2 başlatılırken YKİ'den gelen aralık/irtifa.
    # 0 = BELİRTİLMEDİ; alıcı kendi varsayılanını korur.
    aralik_dm: int = 0
    irtifa_dm: int = 0

    @property
    def aralik_m(self) -> float:
        """Formasyon aralığı, metre. 0.0 = belirtilmedi."""
        return self.aralik_dm / 10.0

    @property
    def irtifa_m(self) -> float:
        """Kalkış irtifası, metre. 0.0 = belirtilmedi."""
        return self.irtifa_dm / 10.0


@dataclass
class OriginVeri:
    """TIP_ORIGIN payload — paylaşılan NED origin (SwarmOrigin).

    NOT: firmware tarafında origin 16 bayta sığdırılmıştır. Float64
    lat/lon mesh'e sığmadığı için 1e-7 derece tamsayı kullanılır.
    """

    lat_1e7: int   # 1e-7 derece
    lon_1e7: int   # 1e-7 derece
    alt_mm: int    # milimetre
    sequence: int


@dataclass
class KomutVeri:
    """TIP_KOMUT payload — joystick / yarı otonom sürü komutu.

    SwarmControlCommand'ın 16 bayta sığdırılmış mesh karşılığıdır.
    Float32 komutlar int16 * 100 (×0.01 ölçek) ile taşınır.
    """

    alt_tip: int        # MODE_SWARM_MOVEMENT=1 / MODE_MANEUVER=2 / MODE_GUIDED=3
    flags: int          # bit alanı, KOMUT_FLAG_* bitleri
    roll_x100: int      # roll_cmd * 100  ([-32767, 32767])
    pitch_x100: int
    yaw_x100: int
    throttle_x100: int
    target_id: int = 0  # guided hedef drone (0 = tümü). Joystick modunda kullanılmaz.
    talep_formasyon: int = 0     # requested_formation; 0 = belirtilmedi
    talep_spacing_dm: int = 0    # requested_spacing_m * 10; 0 = belirtilmedi

    @property
    def talep_spacing_m(self) -> float:
        """0 = belirtilmedi — çağıran taraf bunu spacing 0.0 sanmamalı."""
        return self.talep_spacing_dm / 10.0

    @property
    def formasyon_talebi_gecerli(self) -> bool:
        """FORMATION_CHANGE bayrağı anlamlı bir talep mi taşıyor?

        Eski bir gönderici (bu alanlar 30 Temmuz'da eklenmeden önceki
        sürüm) bayrağı set edip İKİ BAYTI DA sıfır bırakır. O talebi
        uygulamak sürüyü spacing=0 ile FORMATION_UNKNOWN'a göndermekti;
        alıcı bunu uygulamak yerine reddetmeli.

        🔴 formasyon=0 ARTIK MEŞRU BİR TALEP — 31 Ağustos 2026. VrB
        formasyon ana anahtarı kapatıldığında kumanda bilerek
        `requested_formation = FORMATION_UNKNOWN` yayınlıyor ve anlamı
        "formasyon yok, bulunduğun yeri tut". Eski kural bu isteği
        mesh'te DÜŞÜRÜYORDU: pilot uçağı formasyondan çıkıyor, komşular
        eski formasyonda kalıyordu — sürü ikiye bölünürdü.

        AYIRT EDİCİ: eski gönderici İKİ alanı da boş bırakır. Bilinçli
        "formasyon yok" isteğinde spacing DOLU gelir (joystick
        `default_spacing_m`'i her çerçevede yazıyor; 31 Ağustos uçuş
        kaydında requested_formation=0 iken bile spacing 7.0 m ölçüldü).
        Bu yüzden şart "formasyon sıfır" değil, "İKİSİ DE sıfır".
        """
        return bool(self.flags & KOMUT_FLAG_FORMATION_CHANGE) and not (
            self.talep_formasyon == 0 and self.talep_spacing_dm == 0)


@dataclass
class GotoVeri:
    """TIP_GOTO payload — YKİ'den gelen guided tekil nokta-git komutu.

    Hedef, paylaşılan SwarmOrigin'e göre NED (desimetre) taşınır. Yön (yaw)
    yalnızca GOTO_BAYRAK_YAW_GECERLI set ise geçerlidir.
    """

    kuzey_dm: int       # NED kuzey, desimetre
    dogu_dm: int        # NED doğu, desimetre
    asagi_dm: int       # NED aşağı, desimetre (pozitif = aşağı; irtifa = -asagi_dm)
    yaw_ddeg: int       # hedef yaw, desi-derece (0.1°)
    bayraklar: int      # GOTO_BAYRAK_* bitleri
    target_id: int = 0  # hedef drone (0 = tümü). Mesh id taşımadığı için payload'da.

    @property
    def kuzey_m(self) -> float:
        return self.kuzey_dm / 10.0

    @property
    def dogu_m(self) -> float:
        return self.dogu_dm / 10.0

    @property
    def asagi_m(self) -> float:
        return self.asagi_dm / 10.0

    @property
    def yaw_deg(self) -> float:
        return self.yaw_ddeg / 10.0

    @property
    def yaw_gecerli(self) -> bool:
        return bool(self.bayraklar & GOTO_BAYRAK_YAW_GECERLI)


@dataclass
class LeaderHbVeri:
    """TIP_LEADER_HB payload — aktif liderin consensus heartbeat'i."""

    leader_id: int
    sequence_num: int       # her yayında +1
    election_round: int     # mevcut election turu
    active_agent_count: int  # liderin gördüğü aktif ajan sayısı
    mission_active: int      # 0/1


@dataclass
class ElectionVeri:
    """TIP_ELECTION payload — yeni lider seçim sonucu."""

    new_leader_id: int
    election_round: int
    reason: int              # REASON_* (1=TIMEOUT, 2=FAULT, 3=MANUAL)
    triggered_by: int        # election'ı başlatan ajan, 0=sistem
    sequence_num: int
    confirmed_ids: tuple[int, int, int, int]  # max 4 ajan, 0 = boş
    incarnation: int = 0     # yayıncının açılış kimliği; 0 = bilinmiyor


@dataclass
class QrVeri:
    """TIP_QR_DATA payload — komşunun çözümlediği QR."""

    drone_id: int
    action_id: int   # çözümlenen QR eylemi
    lat: int         # 1e-7 derece
    lon: int         # 1e-7 derece


@dataclass
class SwarmStateVeri:
    """TIP_SWARM_STATE payload — sürü seviyesi FSM görünümü."""

    mission_id: int
    swarm_fsm_state: int
    active_leader: int
    formation: int
    timestamp: int


@dataclass
class QrKoordVeri:
    """TIP_QR_COORDS payload — YKİ'den gelen tek QR konumu."""

    qr_id: int
    toplam: int      # tablodaki toplam QR sayısı
    lat: int         # 1e-7 derece
    lon: int         # 1e-7 derece


@dataclass
class Cerceve:
    """COBS+CRC doğrulanmış UART çerçevesi."""

    tip: int
    iha_id: int
    payload: bytes  # değişken uzunluk


def cerceve_coz(decoded: bytes) -> Cerceve | None:
    """COBS çözülmüş baytları doğrular ve çerçeveye ayırır.

    Args:
        decoded (bytes): COBS çözülmüş ham çerçeve (>= 20 byte).

    Returns:
        Cerceve: CRC doğru ise tip/iha_id/payload içeren çerçeve.
        None: Uzunluk yetersiz veya CRC uyuşmuyorsa.
    """
    if len(decoded) < _FRAME_MIN:
        return None

    govde = decoded[:-2]  # tip + iha_id + payload (CRC hariç)
    crc_gelen = (decoded[-2] << 8) | decoded[-1]
    if crc16(govde) != crc_gelen:
        return None

    return Cerceve(tip=decoded[0], iha_id=decoded[1], payload=govde[2:])


def pose_coz(payload: bytes) -> PoseVeri:
    """TIP_POSE payload'ını PoseVeri'ye çözer."""
    lat, lon, alt_dm, heading, vx, vy, vz = struct.unpack(_POSE_FMT, payload)
    return PoseVeri(lat, lon, alt_dm, heading, vx, vy, vz)


def durum_coz(payload: bytes) -> DurumVeri:
    """TIP_DURUM payload'ını DurumVeri'ye çözer (REV C, 16 bayt)."""
    alanlar = struct.unpack(_DURUM_FMT, payload)
    return DurumVeri(
        drone_id=alanlar[0],
        durum=alanlar[1],
        bayraklar=alanlar[2],
        ucus_modu=alanlar[3],
        gps_fix_type=alanlar[4],
        gps_uydu=alanlar[5],
        gps_hdop_x10=alanlar[6],
        battery_pct=alanlar[7],
        battery_volt_x10=alanlar[8],
        rssi=alanlar[9],
        mesh_komsu_sayisi=alanlar[10],
        bayraklar2=alanlar[11],
    )


def durum_paketle(drone_id: int, durum: int, armed: int,
                  gps_fix_type: int, battery_pct: int,
                  battery_volt: float, ekf_ok: int, imu_ok: int,
                  mag_ok: int, baro_ok: int, rssi: int,
                  mesh_link_ok: int,
                  mesh_komsu_sayisi: int = 0,
                  ucus_modu: int = 0,
                  gps_uydu: int = 0,
                  gps_hdop: float = 99.9,
                  kill_switch_active: int = 0,
                  rc_link_ok: int = 0,
                  ready_to_arm: int = 0,
                  origin_synced: int = 0,
                  kacinma_koru: int = 0,
                  home_set: int = 0,
                  gorev_yari_otonom: int = 0) -> bytes:
    """Durum verisi alanlarını 16 baytlık mesh payload'ına paketler (REV C).

    RPi kendi durumunu (agent_fsm çıktısı) ESP32'ye gönderirken kullanır.

    Bool alanlar tek bayta paketlenir; çağıran taraf yine 0/1 verir, bit
    işini bu fonksiyon yapar. Böylece çağrı yerleri REV B ile aynı kalır ve
    yeni alanlar isteğe bağlı parametre olarak eklenir.

    Args:
        drone_id (int): Kendi ID.
        durum (int): _DURUM_* enum kodu (firmware ile aynı).
        armed (int): 0/1.
        gps_fix_type (int): 0-6 (4=DGPS, 5=RTK float, 6=RTK fixed).
        battery_pct (int): 0-100.
        battery_volt (float): Paket voltajı; 0.1 V çözünürlükte taşınır.
        ekf_ok, imu_ok, mag_ok, baro_ok (int): 0/1 sağlık bayrakları.
        rssi (int): dBm, -128..127.
        mesh_link_ok (int): 0/1.
        mesh_komsu_sayisi (int): aktif mesh node sayısı.
        ucus_modu (int): AgentStatus.FLIGHT_MODE_* — PX4'ün BİLDİRDİĞİ mod.
        gps_uydu (int): görünen uydu sayısı.
        gps_hdop (float): HDOP; bilinmiyorsa 99.9 → 255 sentineli gider.
        kill_switch_active (int): 0/1 — RC kill switch aktif mi.
        rc_link_ok (int): 0/1 — kumanda bağlantısı var mı.

    Returns:
        bytes: 16 baytlık payload.
    """
    bayraklar = 0
    if armed:
        bayraklar |= DURUM_BAYRAK_ARMED
    if ekf_ok:
        bayraklar |= DURUM_BAYRAK_EKF_OK
    if imu_ok:
        bayraklar |= DURUM_BAYRAK_IMU_OK
    if mag_ok:
        bayraklar |= DURUM_BAYRAK_MAG_OK
    if baro_ok:
        bayraklar |= DURUM_BAYRAK_BARO_OK
    if mesh_link_ok:
        bayraklar |= DURUM_BAYRAK_MESH_LINK
    if kill_switch_active:
        bayraklar |= DURUM_BAYRAK_KILL
    if rc_link_ok:
        bayraklar |= DURUM_BAYRAK_RC_LINK

    bayraklar2 = 0
    if ready_to_arm:
        bayraklar2 |= DURUM2_BAYRAK_READY_TO_ARM
    if origin_synced:
        bayraklar2 |= DURUM2_BAYRAK_ORIGIN_SYNCED
    if kacinma_koru:
        bayraklar2 |= DURUM2_BAYRAK_KACINMA_KORU
    if home_set:
        bayraklar2 |= DURUM2_BAYRAK_HOME_SET
    if gorev_yari_otonom:
        bayraklar2 |= DURUM2_BAYRAK_GOREV_YARI_OTONOM

    # 255 = "bilinmiyor/kötü" sentineli. 25.4'ten büyük HDOP zaten kullanılamaz
    # kalitededir, sentinele kırpmak bilgi kaybetmez.
    hdop_x10 = 255 if gps_hdop >= 25.5 else max(0, int(round(gps_hdop * 10)))
    volt_x10 = max(0, min(255, int(round(battery_volt * 10))))

    return struct.pack(
        _DURUM_FMT,
        drone_id, durum, bayraklar, ucus_modu, gps_fix_type,
        min(255, gps_uydu), hdop_x10, battery_pct, volt_x10,
        rssi, mesh_komsu_sayisi, bayraklar2,
    )


def renk_coz(payload: bytes) -> RenkVeri:
    """TIP_RENK payload'ını RenkVeri'ye çözer."""
    renk, lat, lon = struct.unpack(_RENK_FMT, payload)
    return RenkVeri(renk, lat, lon)


def renk_paketle(renk: int, lat: int, lon: int) -> bytes:
    """Renk bölgesi tespitini 16 baytlık mesh payload'a paketler.

    Args:
        renk (int): 1=KIRMIZI, 2=MAVI.
        lat (int): Enlem, 1e-7 derece.
        lon (int): Boylam, 1e-7 derece.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_RENK_FMT, renk, lat, lon)


def gorev_coz(payload: bytes) -> GorevVeri:
    """TIP_GOREV payload'ını GorevVeri'ye çözer."""
    (tip, param1, param2, bekleme,
     aralik_dm, irtifa_dm) = struct.unpack(_GOREV_FMT, payload)
    return GorevVeri(tip, param1, param2, bekleme, aralik_dm, irtifa_dm)


def gorev_paketle(tip: int, param1: int, param2: int,
                  bekleme_suresi_s: int,
                  aralik_m: float = 0.0,
                  irtifa_m: float = 0.0) -> bytes:
    """Sürü görev komutunu 16 baytlık mesh payload'a paketler.

    Args:
        tip (int): Görev tipi (formasyon/irtifa/manevra alt-tipi).
        param1 (int): 0-255 birinci parametre.
        param2 (int): -128..127 ikinci parametre.
        bekleme_suresi_s (int): 0-255 saniye bekleme süresi.
        aralik_m (float): formasyon aralığı, metre. 0.0 = belirtilmedi.
        irtifa_m (float): kalkış irtifası, metre. 0.0 = belirtilmedi.

    Returns:
        bytes: 16 baytlık payload.

    🔴 KIRPMA SESSİZ DEĞİL: aralık 1 bayt desimetre ile taşındığı için
    tavanı 25.5 m. Üstü verilirse ValueError atılır — sessizce kırpmak
    "12 m istedim, 25.5 m uçtu" sınıfı bir hata üretirdi.
    """
    aralik_dm = int(round(aralik_m * 10.0))
    irtifa_dm = int(round(irtifa_m * 10.0))
    if not 0 <= aralik_dm <= 255:
        raise ValueError(
            f'aralik_m {aralik_m} mesh sinirlarinin disinda (0..25.5 m)')
    if not 0 <= irtifa_dm <= 65535:
        raise ValueError(
            f'irtifa_m {irtifa_m} mesh sinirlarinin disinda (0..6553.5 m)')
    return struct.pack(_GOREV_FMT, tip, param1, param2, bekleme_suresi_s,
                       aralik_dm, irtifa_dm)


def origin_coz(payload: bytes) -> OriginVeri:
    """TIP_ORIGIN payload'ını OriginVeri'ye çözer."""
    lat, lon, alt_mm, seq = struct.unpack(_ORIGIN_FMT, payload)
    return OriginVeri(lat, lon, alt_mm, seq)


def origin_paketle(lat_1e7: int, lon_1e7: int, alt_mm: int,
                   sequence: int) -> bytes:
    """Origin verisi alanlarını 16 baytlık mesh payload'ına paketler.

    Args:
        lat_1e7 (int): Enlem, 1e-7 derece.
        lon_1e7 (int): Boylam, 1e-7 derece.
        alt_mm (int): Yükseklik, milimetre.
        sequence (int): Origin sıra numarası.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_ORIGIN_FMT, lat_1e7, lon_1e7, alt_mm, sequence)


def pose_paketle(lat: int, lon: int, alt_dm: int, heading: int,
                 vx: int, vy: int, vz: int) -> bytes:
    """Pose verisi alanlarını 18 baytlık mesh payload'ına paketler.

    int16 alanlar ±327.67 aralığına kırpılır (sensör glitch koruması).

    Returns:
        bytes: 18 baytlık payload.
    """
    def _kirp(v: int) -> int:
        return max(-32768, min(32767, int(v)))
    return struct.pack(
        _POSE_FMT, int(lat), int(lon),
        _kirp(alt_dm), _kirp(heading), _kirp(vx), _kirp(vy), _kirp(vz),
    )


def komut_coz(payload: bytes) -> KomutVeri:
    """TIP_KOMUT payload'ını KomutVeri'ye çözer."""
    (alt_tip, flags, roll, pitch, yaw, throttle, target_id,
     talep_formasyon, talep_spacing_dm) = struct.unpack(_KOMUT_FMT, payload)
    return KomutVeri(alt_tip, flags, roll, pitch, yaw, throttle, target_id,
                     talep_formasyon, talep_spacing_dm)


def komut_paketle(alt_tip: int, flags: int, roll_x100: int,
                  pitch_x100: int, yaw_x100: int,
                  throttle_x100: int, target_id: int = 0,
                  talep_formasyon: int = 0,
                  talep_spacing_m: float = 0.0) -> bytes:
    """Joystick / formasyon komutunu 16 baytlık mesh payload'ına paketler.

    Args:
        alt_tip (int): Mod (1=SWARM_MOVEMENT, 2=MANEUVER, 3=GUIDED).
        flags (int): KOMUT_FLAG_* bitleri.
        roll_x100 (int): roll_cmd * 100 (float -> int16 ölçek).
        pitch_x100 (int): pitch_cmd * 100.
        yaw_x100 (int): yaw_cmd * 100.
        throttle_x100 (int): throttle_cmd * 100.
        target_id (int): Guided hedef drone (0 = tümü).
        talep_formasyon (int): requested_formation (1/2/3/99); 0 = belirtilmedi.
        talep_spacing_m (float): requested_spacing_m; 0 = belirtilmedi.

    Returns:
        bytes: 16 baytlık payload.

    Note:
        Bu fonksiyon `bytes` döndürmeye devam ediyor (yeni sürü paketleyicileri
        `tuple[bytes, list[str]]` döndürüyor) — 10 çağrı yeri var ve imzayı
        kırmaya değmez. Ayrım ilkeli: aralık kırpma codec'in bilgisi ve burada
        sessizce yapılıyor; "FORMATION_CHANGE bayrağı formasyon 0 ile anlamsız"
        gibi ANLAMSAL doğrulama uygulama katmanının işi ve `esp32_bridge`
        tarafında loglanarak yapılıyor. Bkz. docs/MESH_PROTOKOL_KARARLARI.md §10.
    """
    # 25.5 m üstü aralık çitli yarışma alanında gerçekçi değil; kırpmak bilgi
    # kaybetmez. Gerçek doğrulama ve uyarı köprüde (o katman loglayabiliyor).
    spacing_dm = max(0, min(255, int(round(talep_spacing_m * 10.0))))
    return struct.pack(
        _KOMUT_FMT, alt_tip, flags,
        roll_x100, pitch_x100, yaw_x100, throttle_x100, target_id,
        talep_formasyon & 0xFF, spacing_dm,
    )


def goto_coz(payload: bytes) -> GotoVeri:
    """TIP_GOTO payload'ını GotoVeri'ye çözer."""
    kuzey, dogu, asagi, yaw, bayraklar, target_id = struct.unpack(_GOTO_FMT, payload)
    return GotoVeri(kuzey, dogu, asagi, yaw, bayraklar, target_id)


def goto_paketle(kuzey_dm: int, dogu_dm: int, asagi_dm: int,
                 yaw_ddeg: int = 0, bayraklar: int = 0,
                 target_id: int = 0) -> bytes:
    """Guided nokta-git hedefini 16 baytlık mesh payload'ına paketler.

    Args:
        kuzey_dm (int): NED kuzey, desimetre (int16).
        dogu_dm (int): NED doğu, desimetre (int16).
        asagi_dm (int): NED aşağı, desimetre (int16; irtifa = -asagi_dm).
        yaw_ddeg (int): Hedef yaw, desi-derece (0.1°). bayrak yoksa yok sayılır.
        bayraklar (int): GOTO_BAYRAK_* bitleri.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _GOTO_FMT, kuzey_dm, dogu_dm, asagi_dm, yaw_ddeg, bayraklar, target_id,
    )


def leader_hb_coz(payload: bytes) -> LeaderHbVeri:
    """TIP_LEADER_HB payload'ını LeaderHbVeri'ye çözer."""
    leader_id, seq, election_round, agent_count, mission = struct.unpack(
        _LEADER_HB_FMT, payload
    )
    return LeaderHbVeri(leader_id, seq, election_round, agent_count, mission)


def leader_hb_paketle(leader_id: int, sequence_num: int,
                      election_round: int, active_agent_count: int,
                      mission_active: int) -> bytes:
    """Lider kalp atışı alanlarını 16 baytlık payload'a paketler.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _LEADER_HB_FMT,
        leader_id, sequence_num, election_round,
        active_agent_count, mission_active,
    )


def election_coz(payload: bytes) -> ElectionVeri:
    """TIP_ELECTION payload'ını ElectionVeri'ye çözer."""
    (leader, election_round, reason, triggered_by, seq,
     id0, id1, id2, id3, incarnation) = struct.unpack(
        _ELECTION_FMT, payload
    )
    return ElectionVeri(
        new_leader_id=leader,
        election_round=election_round,
        reason=reason,
        triggered_by=triggered_by,
        sequence_num=seq,
        confirmed_ids=(id0, id1, id2, id3),
        incarnation=incarnation,
    )


def election_paketle(new_leader_id: int, election_round: int,
                     reason: int, triggered_by: int,
                     sequence_num: int,
                     confirmed_ids: tuple,
                     incarnation: int = 0) -> bytes:
    """Seçim sonucu alanlarını 16 baytlık payload'a paketler.

    Args:
        confirmed_ids (tuple): Onay veren ajan ID'leri. 4'ten kısaysa 0
            ile doldurulur, 4'ten uzunsa kırpılır.
        incarnation (int): Yayıncının açılış kimliği (0 = bilinmiyor).
            Varsayılanı 0 çünkü bu parametre 30 Temmuz'da eklendi ve eski
            çağıranların kırılmaması gerekiyordu; gerçek yayıncı her zaman
            sıfırdan farklı verir.

    Returns:
        bytes: 16 baytlık payload.
    """
    ids = list(confirmed_ids[:4]) + [0] * (4 - len(confirmed_ids[:4]))
    return struct.pack(
        _ELECTION_FMT,
        new_leader_id, election_round, reason, triggered_by,
        sequence_num, ids[0], ids[1], ids[2], ids[3],
        int(incarnation) & 0xFFFF,
    )


def qr_coz(payload: bytes) -> QrVeri:
    """TIP_QR_DATA payload'ını QrVeri'ye çözer."""
    drone_id, action_id, lat, lon = struct.unpack(_QR_FMT, payload)
    return QrVeri(drone_id, action_id, lat, lon)


def swarm_state_coz(payload: bytes) -> SwarmStateVeri:
    """TIP_SWARM_STATE payload'ını SwarmStateVeri'ye çözer."""
    mission_id, fsm, leader, formation, ts = struct.unpack(
        _SWARM_STATE_FMT, payload
    )
    return SwarmStateVeri(mission_id, fsm, leader, formation, ts)


def qr_koord_paketle(qr_id: int, toplam: int,
                     lat_deg: float, lon_deg: float) -> bytes:
    """Tek QR konumunu 16 baytlik mesh payload'a paketler.

    🔴 NEDEN VAR — 2 Eylul 2026. Alici taraf (esp32_bridge._isle_qr_coords)
    30 Temmuz'dan beri duruyordu ama GONDEREN YOKTU: YKI tabloyu
    /swarm/internal/mission/qr_coords'a yayinliyor ve o konuya ABONE
    KIMSE YOK. Yani "Drone'lara Gonder" dugmesi bosluga basiyordu.
    Sahada sonucu: mission_fsm "Ilk hedef QR1 konum tabloda yok" der,
    route_unknown=True olur, orkestrator ROTATE/NAVIGATE'te komut
    uretmez ve suru hedefsiz asili kalir (2 Eylul, dort ucus).

    Her QR AYRI cerceve gider (16 bayt sinirina bir tablo sigmaz);
    alici `toplam` alanina bakip tabloyu tamamlaninca yayinlar.

    Args:
        qr_id (int): QR numarasi, 0-255.
        toplam (int): tablodaki toplam QR sayisi, 0-255.
        lat_deg (float): enlem, derece.
        lon_deg (float): boylam, derece.

    Returns:
        bytes: 16 baytlik payload.

    Raises:
        ValueError: qr_id/toplam aralik disi ya da koordinat gecersizse.
    """
    if not 0 <= int(qr_id) <= 255:
        raise ValueError(f'qr_id 0-255 olmali: {qr_id}')
    if not 0 <= int(toplam) <= 255:
        raise ValueError(f'toplam 0-255 olmali: {toplam}')
    if not -90.0 <= float(lat_deg) <= 90.0:
        raise ValueError(f'enlem gecersiz: {lat_deg}')
    if not -180.0 <= float(lon_deg) <= 180.0:
        raise ValueError(f'boylam gecersiz: {lon_deg}')
    return struct.pack(
        _QR_COORD_FMT,
        int(qr_id), int(toplam),
        int(round(float(lat_deg) * 1e7)),
        int(round(float(lon_deg) * 1e7)),
    )


def qr_koord_coz(payload: bytes) -> QrKoordVeri:
    """TIP_QR_COORDS payload'ını QrKoordVeri'ye çözer."""
    qr_id, toplam, lat, lon = struct.unpack(_QR_COORD_FMT, payload)
    return QrKoordVeri(qr_id, toplam, lat, lon)


# ===========================================================================
# Sürü koordinasyonu (30 Temmuz) — docs/MESH_PROTOKOL_KARARLARI.md
#
# NEDEN BU PAKETLEYİCİLER `list[str]` DE DÖNDÜRÜYOR
# Diğer *_paketle fonksiyonları sınır aşımını sessizce kırpıyor (örn.
# durum_paketle'deki HDOP sentineli) ve bu orada güvenli: kırpılan değer
# zaten kullanılamaz kalitede, bilgi kaybı yok.
#
# Burada durum farklı. spacing 25.5 m'yi ya da merkez ±3276.7 m'yi aşarsa
# kırpılan şey GERÇEK bir hedef — sessizce kırpmak sürüyü yanlış yere uçurur.
# İstisna fırlatmak da doğru değil: köprü yakalamazsa formasyon akışı komple
# durur, ki bu daha kötü. O yüzden: kırp AMA neyi kırptığını döndür. Köprü
# bunu loglar. Uyarı listesi göz ardı edilirse bu kodda görünür olur, sahada
# sessiz kalmaz.
# ===========================================================================


@dataclass
class FormasyonVeri:
    """TIP_FORMASYON payload — liderin yayınladığı formasyon tarifi.

    Offsetler taşınmaz: slot geometrisi `compute_slot_offsets()` ile her
    dronda yerel üretilir (saf fonksiyon). Taşınan şey slot ATAMASI ve o
    `slot_ajan` listesinin SIRASINDA kodlu — slot_ajan[i] = i. slottaki ajan.
    """

    formasyon_tipi: int          # 1=OKBASI 2=V 3=CIZGI 99=CUSTOM (bit7 ayrı)
    merkez_kuzey_dm: int
    merkez_dogu_dm: int
    merkez_asagi_dm: int
    heading_ddeg: int
    spacing_dm: int
    maks_hiz_x10: int
    kanat_alfa_deg: int
    slot_ajan: list[int]         # 0 = boş slot; sıra = atama
    devam_var: bool = False      # bit7 set idi: TIP_FORMASYON_DEVAM bekleniyor

    @property
    def merkez_kuzey_m(self) -> float:
        return self.merkez_kuzey_dm / 10.0

    @property
    def merkez_dogu_m(self) -> float:
        return self.merkez_dogu_dm / 10.0

    @property
    def merkez_asagi_m(self) -> float:
        return self.merkez_asagi_dm / 10.0

    @property
    def heading_deg(self) -> float:
        return self.heading_ddeg / 10.0

    @property
    def spacing_m(self) -> float:
        return self.spacing_dm / 10.0

    @property
    def maks_hiz_mps(self) -> float:
        """0 = alıcı yerel varsayılanını kullanır (formation_node davranışı)."""
        return self.maks_hiz_x10 / 10.0

    def dolu_slotlar(self) -> list[int]:
        """Sıfır olmayan ajan ID'leri, slot sırasında."""
        return [a for a in self.slot_ajan if a]


@dataclass
class FormOfsetVeri:
    """TIP_FORM_OFSET payload — yalnız CUSTOM formasyonda açık offsetler."""

    slot_bas: int
    slot_sayisi: int
    ofset_dm: list[int]          # 6 değer: slot0 k,d,a | slot1 k,d,a

    def slot_ofsetleri(self) -> list[tuple[float, float, float]]:
        """Geçerli slotları (kuzey_m, doğu_m, aşağı_m) listesine çevirir."""
        out = []
        for i in range(min(self.slot_sayisi, FORM_OFSET_SLOT_PAKET)):
            k, d, a = self.ofset_dm[i * 3:i * 3 + 3]
            out.append((k / 10.0, d / 10.0, a / 10.0))
        return out


@dataclass
class QrGorevVeri:
    """TIP_QR_GOREV payload — QR'ı okuyan dronun çözdüğü görev paketi."""

    qr_id: int
    qr_seq: int
    sonraki_qr: int
    bayraklar: int
    formasyon_tipi: int
    spacing_dm: int
    pitch_deg: int
    roll_deg: int
    yaw_deg: int
    irtifa_m: int
    bekleme_s: int
    ayrilan_ajan: int
    renk_ve_bekleme: int

    @property
    def valid(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_VALID)

    @property
    def decoded(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_DECODED)

    @property
    def formasyon_aktif(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_FORMASYON)

    @property
    def manevra_aktif(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_MANEVRA)

    @property
    def irtifa_aktif(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_IRTIFA)

    @property
    def ayrilma_aktif(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_AYRILMA)

    @property
    def gorev_bitti(self) -> bool:
        return bool(self.bayraklar & QR_BAYRAK_GOREV_BITTI)

    @property
    def spacing_m(self) -> float:
        return self.spacing_dm / 10.0

    @property
    def ayrilma_renk(self) -> int:
        """detach_color: 0=bilinmiyor 1=kırmızı 2=mavi (alt 2 bit)."""
        return self.renk_ve_bekleme & 0x03

    @property
    def ayrilma_bekleme_s(self) -> int:
        """detach_wait_s, 0-63 saniye (üst 6 bit)."""
        return (self.renk_ve_bekleme >> 2) & 0x3F


@dataclass
class QrHamVeri:
    """TIP_QR_HAM payload — ayrıştırma hatasında ham metnin bir dilimi."""

    hata_kodu: int
    parca_no: int
    toplam_parca: int
    dilim: bytes                 # sonlandırıcı YOK; UTF-8 ortasından kesilebilir


def formasyon_coz(payload: bytes) -> FormasyonVeri:
    """TIP_FORMASYON payload'ını FormasyonVeri'ye çözer."""
    (tip_ham, k, d, a, hdg, spacing, hiz, alfa,
     s0, s1, s2, s3) = struct.unpack(_FORMASYON_FMT, payload)
    return FormasyonVeri(
        formasyon_tipi=tip_ham & ~FORMASYON_BAYRAK_DEVAM,
        merkez_kuzey_dm=k, merkez_dogu_dm=d, merkez_asagi_dm=a,
        heading_ddeg=hdg, spacing_dm=spacing, maks_hiz_x10=hiz,
        kanat_alfa_deg=alfa, slot_ajan=[s0, s1, s2, s3],
        devam_var=bool(tip_ham & FORMASYON_BAYRAK_DEVAM),
    )


def formasyon_paketle(formasyon_tipi: int,
                      merkez_kuzey_m: float, merkez_dogu_m: float,
                      merkez_asagi_m: float, heading_deg: float,
                      spacing_m: float, slot_ajan: list[int],
                      maks_hiz_mps: float = 0.0,
                      kanat_alfa_deg: float = 45.0,
                      devam_var: bool = False) -> tuple[bytes, list[str]]:
    """Formasyon tarifini 16 baytlık payload'a paketler.

    Args:
        formasyon_tipi (int): 1=OKBASI 2=V 3=CIZGI 99=CUSTOM.
        merkez_kuzey_m, merkez_dogu_m, merkez_asagi_m (float): NED metre.
        heading_deg (float): Formasyon yönü, derece.
        spacing_m (float): Ajanlar arası mesafe, metre.
        slot_ajan (list[int]): Slot sırasında ajan ID'leri (en fazla 4).
        maks_hiz_mps (float): 0 = alıcı yerel varsayılanını kullansın.
        kanat_alfa_deg (float): OKBASI/V kanat açısı.
        devam_var (bool): 5+ ajan var, devam paketi gelecek.

    Returns:
        tuple[bytes, list[str]]: 16 baytlık payload ve kırpma uyarıları.
        Uyarı listesi BOŞ DEĞİLSE çağıran taraf loglamalı — sessizce
        kırpılan bir hedef sürüyü yanlış yere uçurur.
    """
    uyarilar: list[str] = []

    def _kirp_i16(deger_m: float, ad: str) -> int:
        dm = int(round(deger_m * 10.0))
        if dm < -32768 or dm > 32767:
            uyarilar.append(
                f'{ad}={deger_m:.1f} m int16 desimetre aralığı dışında '
                f'(±3276.7 m), kırpıldı'
            )
            dm = max(-32768, min(32767, dm))
        return dm

    kuzey = _kirp_i16(merkez_kuzey_m, 'merkez_kuzey')
    dogu = _kirp_i16(merkez_dogu_m, 'merkez_dogu')
    asagi = _kirp_i16(merkez_asagi_m, 'merkez_asagi')

    hdg = int(round(heading_deg * 10.0)) % 3600
    if hdg > 1800:
        hdg -= 3600            # int16 ddeg: -1800..1800

    spacing_dm = int(round(spacing_m * 10.0))
    if spacing_dm > 255:
        uyarilar.append(
            f'spacing={spacing_m:.1f} m uint8 desimetre tavanını (25.5 m) '
            f'aştı, kırpıldı'
        )
        spacing_dm = 255
    spacing_dm = max(0, spacing_dm)

    hiz_x10 = int(round(maks_hiz_mps * 10.0))
    if hiz_x10 > 255:
        uyarilar.append(
            f'maks_hiz={maks_hiz_mps:.1f} m/s tavanı (25.5 m/s) aştı, kırpıldı'
        )
        hiz_x10 = 255
    hiz_x10 = max(0, hiz_x10)

    alfa = int(round(kanat_alfa_deg))
    if not 0 <= alfa <= 255:
        uyarilar.append(f'kanat_alfa={kanat_alfa_deg} 0-255 dışında, kırpıldı')
        alfa = max(0, min(255, alfa))

    slotlar = list(slot_ajan[:FORMASYON_SLOT_PAKET])
    if len(slot_ajan) > FORMASYON_SLOT_PAKET and not devam_var:
        uyarilar.append(
            f'{len(slot_ajan)} ajan var ama devam_var=False — '
            f'{FORMASYON_SLOT_PAKET} üstü slot DÜŞTÜ'
        )
    slotlar += [0] * (FORMASYON_SLOT_PAKET - len(slotlar))

    tip_ham = (formasyon_tipi & ~FORMASYON_BAYRAK_DEVAM)
    if devam_var:
        tip_ham |= FORMASYON_BAYRAK_DEVAM

    return (
        struct.pack(_FORMASYON_FMT, tip_ham, kuzey, dogu, asagi, hdg,
                    spacing_dm, hiz_x10, alfa, *slotlar),
        uyarilar,
    )


def formasyon_devam_coz(payload: bytes) -> list[int]:
    """TIP_FORMASYON_DEVAM payload'ını slot 4..7 ajan listesine çözer."""
    return list(struct.unpack(_FORMASYON_DEVAM_FMT, payload))


def formasyon_devam_paketle(slot_ajan: list[int]) -> bytes:
    """Slot 4..7 ajan ID'lerini 16 baytlık payload'a paketler."""
    s = list(slot_ajan[:FORMASYON_SLOT_PAKET])
    s += [0] * (FORMASYON_SLOT_PAKET - len(s))
    return struct.pack(_FORMASYON_DEVAM_FMT, *s)


def form_ofset_coz(payload: bytes) -> FormOfsetVeri:
    """TIP_FORM_OFSET payload'ını FormOfsetVeri'ye çözer."""
    alanlar = struct.unpack(_FORM_OFSET_FMT, payload)
    return FormOfsetVeri(
        slot_bas=alanlar[0], slot_sayisi=alanlar[1],
        ofset_dm=list(alanlar[2:8]),
    )


def form_ofset_paketle(slot_bas: int,
                       ofsetler: list[tuple[float, float, float]]
                       ) -> tuple[bytes, list[str]]:
    """CUSTOM formasyon offsetlerini paketler (paket başına en fazla 2 slot).

    Args:
        slot_bas (int): Bu paketteki ilk slot indeksi.
        ofsetler (list): En fazla 2 adet (kuzey_m, doğu_m, aşağı_m).

    Returns:
        tuple[bytes, list[str]]: payload ve kırpma uyarıları.
    """
    uyarilar: list[str] = []
    kullanilan = ofsetler[:FORM_OFSET_SLOT_PAKET]
    if len(ofsetler) > FORM_OFSET_SLOT_PAKET:
        uyarilar.append(
            f'{len(ofsetler)} offset verildi, paket {FORM_OFSET_SLOT_PAKET} '
            f'taşır — fazlası DÜŞTÜ (çağıran tarafın bölmesi gerekir)'
        )

    dm: list[int] = []
    for i, (k, d, a) in enumerate(kullanilan):
        for deger, ad in ((k, 'kuzey'), (d, 'dogu'), (a, 'asagi')):
            v = int(round(deger * 10.0))
            if v < -32768 or v > 32767:
                uyarilar.append(
                    f'slot{slot_bas + i} {ad}={deger:.1f} m int16 dm '
                    f'aralığı dışında, kırpıldı'
                )
                v = max(-32768, min(32767, v))
            dm.append(v)
    dm += [0] * (6 - len(dm))

    return (
        struct.pack(_FORM_OFSET_FMT, slot_bas, len(kullanilan), *dm),
        uyarilar,
    )


def qr_gorev_coz(payload: bytes) -> QrGorevVeri:
    """TIP_QR_GOREV payload'ını QrGorevVeri'ye çözer."""
    return QrGorevVeri(*struct.unpack(_QR_GOREV_FMT, payload))


def qr_gorev_paketle(qr_id: int, qr_seq: int, sonraki_qr: int,
                     valid: bool = False, decoded: bool = False,
                     formasyon_aktif: bool = False,
                     manevra_aktif: bool = False,
                     irtifa_aktif: bool = False,
                     ayrilma_aktif: bool = False,
                     gorev_bitti: bool = False,
                     formasyon_tipi: int = 0, spacing_m: float = 0.0,
                     pitch_deg: float = 0.0, roll_deg: float = 0.0,
                     yaw_deg: float = 0.0, irtifa_m: float = 0.0,
                     bekleme_s: float = 0.0, ayrilan_ajan: int = 0,
                     ayrilma_renk: int = 0, ayrilma_bekleme_s: float = 0.0
                     ) -> tuple[bytes, list[str]]:
    """Çözülmüş QR görevini 16 baytlık payload'a paketler.

    Manevra açıları TAM DERECE (int8) taşınır: şartname manevraları "belirli
    bir açı" diyor ve QR'dan gelen değerler tam derece. 0.1° çözünürlük
    gerekirse int16'ya geçmek 2 bayt daha ister; rezervde yer var.

    Returns:
        tuple[bytes, list[str]]: payload ve kırpma uyarıları.
    """
    uyarilar: list[str] = []

    bayraklar = 0
    for kosul, bit in (
        (valid, QR_BAYRAK_VALID),
        (decoded, QR_BAYRAK_DECODED),
        (formasyon_aktif, QR_BAYRAK_FORMASYON),
        (manevra_aktif, QR_BAYRAK_MANEVRA),
        (irtifa_aktif, QR_BAYRAK_IRTIFA),
        (ayrilma_aktif, QR_BAYRAK_AYRILMA),
        (gorev_bitti, QR_BAYRAK_GOREV_BITTI),
    ):
        if kosul:
            bayraklar |= bit

    def _kirp_u8(deger: float, ad: str, olcek: float = 1.0) -> int:
        v = int(round(deger * olcek))
        if v > 255:
            uyarilar.append(f'{ad}={deger} uint8 tavanını aştı, kırpıldı')
            v = 255
        return max(0, v)

    def _kirp_i8(deger: float, ad: str) -> int:
        v = int(round(deger))
        if v < -128 or v > 127:
            uyarilar.append(f'{ad}={deger}° int8 aralığı dışında, kırpıldı')
            v = max(-128, min(127, v))
        return v

    renk = ayrilma_renk & 0x03
    bekleme_ayrilma = int(round(ayrilma_bekleme_s))
    if bekleme_ayrilma > 63:
        uyarilar.append(
            f'ayrilma_bekleme={ayrilma_bekleme_s} s 6 bitlik alana (63 s) '
            f'sığmadı, kırpıldı'
        )
        bekleme_ayrilma = 63
    bekleme_ayrilma = max(0, bekleme_ayrilma)

    return (
        struct.pack(
            _QR_GOREV_FMT,
            _kirp_u8(qr_id, 'qr_id'),
            qr_seq & 0xFF,          # sarma bilinçli: karşılaştırılmıyor, bkz. belge
            _kirp_u8(sonraki_qr, 'sonraki_qr'),
            bayraklar,
            _kirp_u8(formasyon_tipi, 'formasyon_tipi'),
            _kirp_u8(spacing_m, 'spacing', 10.0),
            _kirp_i8(pitch_deg, 'pitch'),
            _kirp_i8(roll_deg, 'roll'),
            _kirp_i8(yaw_deg, 'yaw'),
            _kirp_u8(irtifa_m, 'irtifa'),
            _kirp_u8(bekleme_s, 'bekleme'),
            _kirp_u8(ayrilan_ajan, 'ayrilan_ajan'),
            renk | (bekleme_ayrilma << 2),
        ),
        uyarilar,
    )


def qr_ham_coz(payload: bytes) -> QrHamVeri:
    """TIP_QR_HAM payload'ını QrHamVeri'ye çözer."""
    hata, parca, toplam, dilim = struct.unpack(_QR_HAM_FMT, payload)
    return QrHamVeri(hata, parca, toplam, dilim)


def qr_ham_paketle(hata_kodu: int, ham_metin: str) -> list[bytes]:
    """Ham QR metnini en fazla 4 parçaya bölüp payload listesi döndürür.

    Metin UTF-8'e çevrilip 13 baytlık dilimlere bölünür. Dilim sınırı UTF-8
    karakterinin ORTASINDAN geçebilir — bu bilinçli: amaç metni doğru
    çözmek değil, formatın ne olduğunu görmek (`{"QR":` mi `{"qr":` mi).
    Birleştiren taraf `errors='replace'` ile çözmeli.

    Returns:
        list[bytes]: 1-4 adet 16 baytlık payload.
    """
    ham = ham_metin.encode('utf-8', errors='replace')
    maks = QR_HAM_DILIM_BOYU * QR_HAM_MAKS_PARCA
    ham = ham[:maks]
    parcalar = [ham[i:i + QR_HAM_DILIM_BOYU]
                for i in range(0, len(ham), QR_HAM_DILIM_BOYU)] or [b'']
    toplam = len(parcalar)
    return [
        struct.pack(_QR_HAM_FMT, hata_kodu, i, toplam,
                    p.ljust(QR_HAM_DILIM_BOYU, b'\x00'))
        for i, p in enumerate(parcalar)
    ]


# =============================================================================
# TIP_OLAY — uçak olayları (27 Ağustos 2026)
# =============================================================================

# source_module STRING'i mesh'te taşınamaz (16 bayta sığmaz). Kodla taşınıp
# YKİ'de geri açılıyor. Tablodaki isimler depoda fiilen kullanılanlardan
# çıkarıldı (`grep source_module`).
#
# ⚠️ Tablo İKİ TARAFTA da aynı olmalı — burası tek kaynak, YKİ bunu okuyor.
# Yeni bir modül eklenirse SONA eklenir; aradaki kodlar KAYDIRILMAZ, yoksa
# eski kayıtlar yanlış modül adıyla okunur.
MODUL_KODLARI: dict[str, int] = {
    'bilinmiyor': 0,
    'agent_fsm': 1,
    'collision_avoidance': 2,
    'consensus': 3,
    'esp32_bridge': 4,
    'formation_control': 5,
    'mission_fsm': 6,
    'mission1_dynamic_swarm': 7,
    'camera_driver': 8,
    'precision_landing': 9,
    'maneuver_executor': 10,
    'mode_manager': 11,
    'swarm_fsm': 12,
    'joystick_interpreter': 13,
    'path_planner': 14,
    'px4_bridge': 15,
    'basit_kacinma': 16,
    'yelpence_izle': 17,      # Pi ana sistem izlemesi (konteyner disi)
}
MODUL_ADLARI: dict[int, str] = {v: k for k, v in MODUL_KODLARI.items()}


def modul_kodu(ad: str) -> int:
    """Modül adını koda çevirir; bilinmeyen ad 0 döner.

    `collision_avoidance:korluk` gibi iki nokta ile alt-ad verilen yerler
    var; taban ada bakiyoruz ki her alt-ad icin ayri kod tutmak gerekmesin.
    """
    if not ad:
        return 0
    return MODUL_KODLARI.get(ad.split(':')[0].strip(), 0)


# TASIMA KATMANI OLAY KODLARI — SystemEvent.msg'nin 0-59 araligiyla
# CAKISMAZ. Bunlar ucaktaki bir dugumun urettigi olaylar degil, olay
# yolunun KENDI hakkinda soyledikleri:
#
#   DUSEN  : gonderici butcesi asildi, N olay gonderilmedi. Sessizce
#            dusurmek, defterin "tamam" gorunmesi demek olurdu.
#   BOSLUK : baz, sira_no'da atlama gordu — N olay HAVADA kayboldu.
#            Broadcast'te ACK yok; teslimat garanti edilemez ama kayip
#            GORUNUR kilinabilir.
# Pi ANA SISTEM olaylari (60-79). SystemEvent.msg 0-59'u kullaniyor, bu
# aralik BOS. Bunlar konteyner disindan gelir: olcumu `yelpence_izle.sh`
# yapar (vcgencmd konteynerde yok), esik/histerezis `sistem_sagligi.py`de.
#
# SIDDET DURUMU ANLATIR: acilis WARNING/CRITICAL, normale donus INFO.
# Deger her iki durumda da tasinir, yani "Pi sicakligi (82)" kritik,
# "Pi sicakligi (64)" bilgi olarak okunur.
OLAY_TIPI_PI_SICAKLIK = 60
OLAY_TIPI_PI_GERILIM = 61        # get_throttled != 0 (dusuk gerilim/kisitlama)
OLAY_TIPI_PI_DISK = 62
OLAY_TIPI_PI_BELLEK = 63
OLAY_TIPI_PI_YUK = 64
OLAY_TIPI_PI_KONTEYNER = 65
OLAY_TIPI_PI_ROS_EKSIK = 66
OLAY_TIPI_PI_WIFI = 67
OLAY_TIPI_MAVROS_TASKIN = 68

OLAY_TIPI_DUSEN = 250
OLAY_TIPI_BOSLUK = 251


@dataclass
class OlayVeri:
    """TIP_OLAY payload — bir uçak olayı.

    Alanlar SystemEvent.msg ile bire bir eşleşir; `message` ve konum
    TASINMIYOR (gerekce TIP_OLAY tanimindaki nota bak).
    """

    olay_tipi: int      # SystemEvent.EVENT_*
    siddet: int         # SystemEvent.SEVERITY_*
    kaynak_id: int      # 0 = sistem geneli
    hedef_id: int       # ilgili baska ajan; 0 = yok
    deger: float        # SystemEvent.value (x100 kodlanmis, geri acilmis)
    sira_no: int        # drone basina artan sayac — BOSLUK TESPITI icin
    modul: str          # source_module (koddan geri acilmis)
    zaman_ms: int       # ucaktaki zaman damgasi
    ek1: int
    ek2: int


def olay_coz(payload: bytes) -> OlayVeri:
    """TIP_OLAY payload'ını OlayVeri'ye çözer (16 bayt)."""
    a = struct.unpack(_OLAY_FMT, payload)
    return OlayVeri(
        olay_tipi=a[0],
        siddet=a[1],
        kaynak_id=a[2],
        hedef_id=a[3],
        deger=a[4] / 100.0,
        sira_no=a[5],
        modul=MODUL_ADLARI.get(a[6], 'bilinmiyor'),
        zaman_ms=a[7],
        ek1=a[8],
        ek2=a[9],
    )


# int16 x100'un tasiyabilecegi aralik. Disina cikan deger KIRPILIR — sarmak
# (overflow) sessizce ters isaretli bir sayi uretir ve "batarya %-321" gibi
# okunur bir sonucu YANLIS ama inandirici yapar.
OLAY_DEGER_MIN = -327.67
OLAY_DEGER_MAKS = 327.67


def olay_paketle(olay_tipi: int, siddet: int, kaynak_id: int,
                 sira_no: int,
                 hedef_id: int = 0,
                 deger: float = 0.0,
                 modul: str = '',
                 zaman_ms: int = 0,
                 ek1: int = 0,
                 ek2: int = 0) -> bytes:
    """Olay alanlarını 16 baytlık mesh payload'ına paketler.

    sira_no drone basina 0-255 arasi doner; YKI sarmayi hesaba katarak
    bosluk sayar (bkz. esp32_bridge baz tarafi).
    """
    d = max(OLAY_DEGER_MIN, min(OLAY_DEGER_MAKS, float(deger)))
    return struct.pack(
        _OLAY_FMT,
        int(olay_tipi) & 0xFF,
        int(siddet) & 0xFF,
        int(kaynak_id) & 0xFF,
        int(hedef_id) & 0xFF,
        int(round(d * 100.0)),
        int(sira_no) & 0xFF,
        modul_kodu(modul),
        int(zaman_ms) & 0xFFFFFFFF,
        int(ek1) & 0xFFFF,
        int(ek2) & 0xFFFF,
    )
