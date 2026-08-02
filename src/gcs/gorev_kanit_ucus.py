#!/usr/bin/env python3
# =============================================================================
# KANIT UÇUŞU GÖREV KOŞUCUSU
#
# Koreografi (şartname 5.1.2'deki görev komutlarının hepsini gösterir):
#   0. Yerde OK BAŞI dizilimi
#   1. Tek komutla eş zamanlı kalkış, formasyonu koruyarak irtifaya
#   2. Ok başında P1'e
#   3. P1'de ROLL manevrası (sürü merkezi SABİT, biri yukarı biri aşağı)
#   4. Roll'lu halde P2'ye
#   5. P2'de roll'u düzelt, sonra FORMASYON DEĞİŞİMİ
#   6. P3'e
#   7. P3'te İRTİFA DEĞİŞİMİ
#   8. Kalkış noktasına dön ve in
#
# Uçuş kanıt videosu yönergesi de karşılanır: >=2 İHA, üç doğrusal olmayan
# nokta, çarpışmasız, en az bir formasyon değişimi + rotasyon, tam otonom
# (RC'ye dokunulmaz), stabil iniş, <=5 dk, tek çekim.
#
# ---------------------------------------------------------------------------
# NEDEN YERDE KOŞUYOR
# Sürü düğümleri (formation_node, consensus_node, collision_avoidance, ...)
# simülasyon için yazıldı ve sahada HİÇ koşmadılar — bkz. deploy/rpi/baslat.sh
# yorumu, ve ölçüldü: dronlarda yalnız agent_fsm + esp32_bridge + px4_bridge
# çalışıyor, 14 sürü düğümünün hiçbiri açık değil.
#
# collision_avoidance'ı açmak tek başına MÜMKÜN DEĞİL: zincirde
# formation_node -> collision_avoidance -> px4_bridge şeklinde zorunlu halka,
# yani onu açmak bütün denenmemiş zinciri işin içine sokmak demek. Onun yerine
# çarpışmasızlık GEOMETRİK olarak garanti ediliyor ve uçuştan ÖNCE
# kanıtlanıyor (bkz. plan_dogrula).
#
# Komut yolu (hepsi kanıtlanmış):
#   REST -> YKİ backend -> base ESP -> mesh -> drone esp32_bridge
#        -> AgentSetpoint -> px4_bridge -> OFFBOARD -> PX4
#
# ---------------------------------------------------------------------------
# GÜVENLİK
# - Hedefler mutlak değil, ÖLÇÜLEN kalkış konumuna göreli. yki_baslat.sh'in
#   origin'i sahaya uymazsa mutlak hedef uçağı kilometrelerce öteye yollardı.
# - Plan uçmadan önce bütünüyle kurulur ve doğrulanır: her adımda ve
#   adımlar ARASINDAKİ geçişte uçaklar arası en küçük mesafe hesaplanır.
#   Eşiğin altına düşen varsa görev BAŞLAMAZ.
# - Her goto öncesi mesafe kelepçesi (MAX_GOTO_M).
# - Ctrl-C ve her hata yolu LAND gönderir. DISARM ASLA gönderilmez.
#
# Kullanım:
#     python3 gorev_kanit_ucus.py --kuru          # komut yok, plan + doğrulama
#     python3 gorev_kanit_ucus.py --dronelar 1,2  # prova (iki drone)
#     python3 gorev_kanit_ucus.py --dronelar 1,2,3
# =============================================================================

import argparse
import itertools
import math
import pathlib
import signal
import sys
import time
import urllib.error
import urllib.request

YKI = "http://localhost:8000"
ZAMAN_ASIMI_S = 5.0

# ylp00 -> 1, ylp01 -> 2, ylp02 -> 3 (bkz. docs/cihazlar.md)
# 31 Temmuz: ylp02 DEVRE DISI — pusulasi 143 uT / std 63 okuyor (saglami
# 48 uT / std 1), kalibrasyon "unable to fit mag 0" ile basarisiz.
# Olcumle elenenler: kamera guc kablosu, ESP32 mesh yayini, hareket,
# yapilandirma farki. Bkz. src/gcs/pusula_olc.py
DRONELAR = [1, 2]

# --- Geometri ---------------------------------------------------------------
ARALIK_M = 10.0         # formasyonda komşu slotlar arası mesafe (lider-kanat)
KANAT_ACISI_DEG = 45.0  # ok başı kanat açısı (orchestrator wing_alpha ile aynı)
# Görev noktaları arası. Kenarı kısaltmak çarpışma marjını HİÇ etkilemiyor
# (ölçüldü: kritik an bacaklarda değil, P1'deki roll'lu rotasyonda oluşuyor)
# ama kaplanan alanı küçültüyor — yani sahaya sığdırmanın bedavaya gelen kolu.
# Gorev rotasinin YONU (pusula derecesi). 0 = ilk bacak KUZEYE.
# NEDEN VAR: kod BINALARI GOREMEZ. Engel algilama, harita, geofence yok —
# ucgeni onunde ne varsa ucar. Guvenlik tamamen rotanin acik alana
# denk gelmesine bagli. Bu yuzden rota dondurulebilir: acik alan
# doguya bakiyorsa --yon 90, guneye bakiyorsa --yon 180.
# SAHADA SECILDI (31 Temmuz): -90 = ilk bacak BATIYA. Acik alan o yonde.
# Varsayilan yapildi ki --yon vermeyi unutan bir kosu ucagi kuzeye,
# yani binalarin oldugu tarafa yollamasin.
ROTA_YONU_DEG = -90.0

KENAR_M = 18.0
# "VARDI" YARICAPI — 2.5 idi, 2 Agustos'ta 1.0'a cekildi.
#
# 2.5 fazla genisti ve dongu 0.1 sn'ye inince bu GORUNUR hale geldi: dikey
# adimda "vardi: d2=1.9m" yazildi, yani ucak komut edilen irtifanin 1.9 m
# ALTINDAYKEN adim kapandi. Islevsel olarak yikici degil (5 sn'lik bekleme
# sirasinda setpoint hedefte oldugu icin ucak farki kapatiyor) ama "vardi"
# demek yanlisti ve bir sonraki adim yanlis yerden basliyordu.
#
# Sik ornekleme toleransi DAHA ERKEN yakaliyor: kontrol 2 Hz yerine 10 Hz
# kosunca, ucak henuz yolun basindayken sart saglaniyor. Yani hizli dongu
# gevsek toleransi ortaya cikardi, yaratmadi.
#
# 1.0 m RTK'da rahat ulasilir (konum hatasi cm mertebesinde) ve adim zaman
# asimi 70 sn — ruzgarda bile pay var.
TOLERANS_M = 1.0        # "vardı" yarıçapı
MAX_GOTO_M = 60.0       # tek goto için mesafe tavanı

# --- İrtifalar --------------------------------------------------------------
# KALKIS_IRTIFA_M agent_fsm_node'un target_altitude_m VARSAYILANIYLA (10.0)
# BİLEREK AYNI. Sebep ölçüldü: agent_fsm TAKEOFF durumuna girince px4_bridge'e
# kendi 'takeoff:10.0' komutunu yolluyor (agent_fsm_node.py:251). Farklı bir
# değer seçersek iki komut çakışır ve hangisinin kazandığı sıralamaya kalır.
KALKIS_IRTIFA_M = 10.0
# Görev (formasyon) irtifası — kalkış irtifasından AYRI. Roll manevrasında
# kanatlar merkezden dz = 0.408 x ARALIK_M kadar ayrılıyor; 10 m aralıkta
# ±4.1 m. Kalkış irtifası 10 m'de kalsaydı alttaki uçak 5.9 m'ye inerdi,
# manevra sırasında fazla alçak. 12 m'de yayılım 7.9 - 16.1 m arasında kalıyor.
GOREV_IRTIFA_M = 12.0
YENI_IRTIFA_M = 18.0    # P3'teki irtifa değişimi hedefi
FORMASYON_TEST_IRTIFA_M = 5.0   # --senaryo formasyon

# --- --senaryo tekli --------------------------------------------------------
# TEK UCAK, DUZ KOREOGRAFI: kalkis -> burnunun yonunde 7 m -> bekle ->
# ayni noktada 5 m daha tirman -> bekle -> in.
#
# Amaci sinama: hiz (2 m/s gercekten tutuyor mu), yon (bu senaryoda ucak
# burnunu HIC cevirmiyor, dolayisiyla "ani donus" ciksa sebep bizim
# komutumuz DEGIL demektir) ve irtifa sicramasi (iki ayri tirmanis var,
# ikisi de temiz olmali).
TEKLI_IRTIFA_M = 5.0          # kalkis irtifasi
TEKLI_ILERLEME_M = 7.0        # kalkis yonunde gidilecek mesafe
TEKLI_IRTIFA_ARTIS_M = 5.0    # ayni noktada ikinci tirmanis
TEKLI_BEKLEME_S = 5.0         # her adimda yerinde bekleme

# --- --senaryo asili (KACINMA TESTI) ----------------------------------------
# Tek ucak kalkar, KENDI yerinin ustunde belirtilen sure asili durur, iner.
# Yatayda hicbir komut yok — dolayisiyla ucak kimildarsa sebep BIZ DEGILIZ.
# Kacinmayi denemenin en temiz yolu bu: operator OTEKI dronu kumandayla
# yaklastirir ve otonom ucagin kacip kacmadigina bakar.
#
# IRTIFA AYRIMI GUVENLIK ICIN: kacinma yalniz YATAY calisiyor (itme_vektoru
# 'kuzey, dogu' aliyor, irtifa hesaba hic girmiyor). Yani iki ucagi farkli
# irtifada tutmak kacinmayi engellemez ama fiziksel carpismayi imkansiz kilar.
ASILI_IRTIFA_M = 8.0
ASILI_SURE_S = 60.0

# --- --senaryo takip (IKI DRONLU PROVA) -------------------------------------
# Kanit videosu koreografisinin ONCESINDE yapilan prova: roll YOK, formasyon
# degisimi YOK, irtifa degisimi YOK. Yalniz "formasyonu kur, git, bekle, don".
# Amac ilk kez IKI ucagi bu kodla birlikte havada tutmak.
#
# LIDER OPERATORUN SECTIGI ucaktir ve slot 0'a SABITLENIR — "en yakin slot"
# atamasi kullanilmaz. Formasyon merkezi, LIDER istenen noktada olacak sekilde
# geri hesaplanir (okbasi ofsetleri merkezlenmis geldigi icin lider merkezde
# DEGILDIR; n=2'de merkezin 3.54 m onunde ve 3.54 m solundadir).
#
# BURUN DONMEZ: gidiste de doniste de heading = liderin kalkis yonu. Ucaklar
# geri geri doner. Boylece yaw dilimleme hic devreye girmez — ilk iki dronlu
# ucusta bir degisken daha az.
TAKIP_MESAFE_M = 15.0
TAKIP_IRTIFA_M = 10.0
TAKIP_BEKLEME_S = 3.0

# --- --senaryo donus (CIZGI + 180 ROTASYON + EVE DONUS) ---------------------
# Kalkis -> cizgi formasyonu -> liderin baktigi yone DONUS_MESAFE_M ->
# 180 ROTASYON (lider YERINDE, takipci onun etrafinda yay cizer) -> eve don.
#
# ROTASYON NEDEN DILIMLENIYOR: 180'i tek adimda vermek, takipcinin baslangic
# ve bitis noktalarini liderin IKI YANINA koyar ve aradaki DUZ CIZGI tam
# liderin uzerinden gecer. Setpoint duz gider, yay cizmez — yani carpisma.
# plan_dogrula bunu zaten reddederdi.
#
# 30 derecelik dilimlerde: kiris boyu 2*R*sin(15) = 5.2 m ve takipci lidere
# en fazla R*cos(15) = 9.7 m'ye kadar yaklasir. Yani ARALIK_M'nin altina hic
# inmez ve hareket gercekten yay olur.
DONUS_MESAFE_M = 20.0
DONUS_IRTIFA_M = 10.0
# 2 Agustos ilk denemesi: 6 dilim (30 derece) ve her dilimde TAM VARIS
# bekleniyordu. Sonuc "taksit taksit" bir hareketti — ucak her dilimde
# sifirdan hizlanip duruyor, varis duzeltmesini yapiyor, sonra yeniden
# hizlaniyordu. Operator "cok kotu gorundu, asiri cirkin" dedi ve haklıydı.
#
# Duzeltme iki parcali:
#   1) Ara noktalar artik GECIS NOKTASI (bkz. DONUS_GECIS_R_M): tam varis
#      beklenmiyor, ucak yavaslamadan bir sonrakine geciyor.
#   2) Burun donusu ayri faz olarak yapilmiyor; yon konumla birlikte
#      degisiyor ve PX4 MPC_YAWRAUTO_MAX ile zaten yumusatiyor.
# Durmak gerekmedigi icin dilim sayisi ARTIRILDI: daha yuvarlak yay, ayni sure.
# 2. DENEME de yetmedi (8 dilim x 22.5, gecis yaricapi 2.0). Ucak artik
# DURMUYORDU — log: mesafe 5.0 -> 1.5 arasi ortalama 2.2 m/s, sifira inmiyor.
# Ama operator yine "taksit taksit" dedi ve yine hakliydi: sorun duraklama
# DEGIL, YON KIRILMASI. Her dilimde hedef 22.5 derece yana ziplıyor ve hiz
# vektoru o kadar donmek zorunda kaliyor — sekiz dilim, sekiz keskin kose.
#
# 3. DENEME: dilimler DURAK degil, ONDEN BAKIS noktalari. Cok sik nokta +
# noktalardan buyuk gecis yaricapi => hedef her zaman ucagin ~3 m onunde
# yay boyunca SUREKLI kayar (saf takip / pure pursuit). Ucak sabit hizla
# onu izler; ne durur ne sert doner.
#   7.5 derece -> 24 dilim, kiris 1.31 m, yon kirilmasi 7.5 derece
#   yay-cokgen sapmasi (sagitta) = R(1-cos(3.75)) = 0.02 m — olculemez
#   gecis yaricapi 3.0 m > kiris => ayni anda ~2 nokta kabul edilir,
#   hedef hep onde kalir
#   3.0 m'de yurutucunun fren hizi sqrt(2*1.5*3.0) = 3.0 m/s > 2.0 tavan
#   => hicbir noktada yavaslamaya baslamaz
# 3. DENEME (24 dilim, kiris 1.31 m) DE YETMEZDI. Ucurmadan once hesabi
# yapinca goruldu: dilimlemek KIRILMAYI azaltiyor ama ZIPLAMAYI bitirmiyor.
# Hedef bir plan adimi boyunca SABIT duruyor, sonra bir anda kiris kadar
# sicriyor. Ucagi tasiyan sey konum terimi (MPC_XY_P x mesafe) oldugu icin:
#     mesafe 3.31 <-> 2.00 m arasi gidip geliyor
#     hiz    3.14 <-> 1.90 m/s   -> ~%25 nabiz, ~1.4 Hz
# Ne kadar sik dilim koyulursa koyulsun sicrama boyu KIRISE esit kalir.
#
# 4. DENEME — SICRAMA BOYUNU DONGU PERIYODUNA ESITLE:
#     adim boyu = hiz x dongu periyodu = 1.9 m/s x 0.2 sn = 0.38 m
# Her tikte hedef tam bir adim ilerler; sicrama diye bir sey kalmaz, hedef
# yay boyunca SUREKLI kayar. R=10 m'de bu 2.25 derecelik dilim demek:
#     kiris 0.39 m · yon kirilmasi 2.25 derece · sapma 0.2 cm · 80 nokta
# Nokta sayisi cok ama her biri tek dongu tiki tuketiyor: 80 x 0.2 = 16 sn,
# yayin 1.9 m/s'te suresiyle (31.4/1.9 = 16.5 sn) birebir ortusuyor.
DONUS_ROTASYON_ADIM_DEG = 2.25      # 180/2.25 = 80 nokta, kiris 0.39 m
# ONDEN BAKIS MESAFESI. Kiristen BUYUK olmasi ARTIK KASITLI: birden fazla
# nokta ayni anda kabul edilir ve hedef ucagin hep ~bu kadar onunde, yay
# boyunca surekli kayan bir noktaya donusur. Kendini ayarlar — ucak
# yaklastikca sonraki noktalar kabul edilir, hedef ilerler.
#
# 2. denemede 2.0 idi ve kiristen (3.9) KUCUKTU; o yuzden her nokta ayri bir
# durak gibi davrandi ve yon 22.5 derece zipladi. Artik tersi.
#
# DEGERI 2.0 SECERKEN DIKKAT — once 3.0 yazmistim, gerekcem YANLISTI.
# "Yurutucu frene basmasin" diye buyuk sectim; oysa hedef surekli onde
# oldugu icin yurutucu ona ZATEN yetisiyor ve hiz ileri-beslemesi sifirlaniyor.
# O halde ucagi tasiyan sey KONUM terimi oluyor ve hizi MPC_XY_P x mesafe
# belirliyor:
#     onden bakis 3.0 m -> 0.95 x 3.0 = 2.85 m/s   (istedigimiz degil)
#     onden bakis 2.0 m -> 0.95 x 2.0 = 1.90 m/s   (hedef hizimiz)
# Yani bu sayi ayni zamanda YAY BOYUNCA HIZI belirliyor.
#
# 2. denemede de 2.0 idi ama o zaman KIRIS 3.9 m ile bu mesafeden BUYUKTU;
# noktalar tek tek durak gibi tuketiliyordu. Simdi kiris 1.31 m, yani
# mesafeden kucuk — birden fazla nokta ayni anda kabul ediliyor ve hedef
# gercekten surekli kayan bir noktaya donusuyor. Belirleyici olan sey
# yaricapin kendisi degil, KIRIS < YARICAP olmasi.
DONUS_GECIS_R_M = 2.0
DONUS_BEKLEME_S = 3.0

# --- --senaryo tam (KANIT VIDEOSU KOREOGRAFISI) -----------------------------
# cizgi -> 40 m ileri -> KD'ye rotasyon -> ROLL -> rollu KD navigasyonu ->
# irtifa esitleme -> eve rotasyon -> eve donus -> inis.
#
# "AYNI GUNEYDOGU EKSENI": kuzeydogu (45) ile guneydogu (135) DIK oldugu icin,
# KD boyunca ilerlerken evin tam GD yonunde kaldigi tek bir nokta vardir.
# Orada durulur; donus bacagi duz bir GD ucusu olur. Mesafe, (P-H) vektorunun
# KD birim vektoru uzerindeki izdusumu kadar.
#
# ROLLDA LIDER SABIT: egim_dz sürü merkezini sabit tutar (sartname sarti) ve
# n=2'de lideri 2.89 m ASAGI, takipciyi 2.89 m YUKARI alir. Operator liderin
# alcalmasini istemedi; bu yuzden liderin dz'si hepsinden CIKARILIYOR —
# lider 10.0'da kalir, takipci 10 + ARALIK_M*tan(roll) = 15.77 m'ye cikar.
# Bedeli: suru merkezi 2.89 m yukselir. Kanit videosunda merkezin sabit
# kalmasi isteniyorsa bu tercih yeniden dusunulmelidir.
TAM_MESAFE_M = 40.0
TAM_IRTIFA_M = 10.0
TAM_ROLL_DEG = 30.0
TAM_KD_DEG = 45.0            # kuzeydogu
TAM_BEKLEME_S = 3.0

# --- Manevra ----------------------------------------------------------------
# Şartname: sürü merkezi sabit, sağa/sola yatış. 30° seçildi çünkü 20°'de
# kanatlar merkezden yalnız ±2.7 m ayrılıyor ve yerden çekimde sınırda
# kalıyordu; 30°'de ±4.1 m'ye çıkıyor.
#
# SEZGİYE AYKIRI, DİKKAT: roll'u KÜÇÜLTMEK çarpışma marjını KÖTÜLEŞTİRİYOR.
# Ölçüldü (8 m aralıkta): roll 30° -> kritik an 4.13 m, roll 20° -> 3.26 m.
# Sebebi, roll'lu rotasyonda uçakları ayıran şeyin bir kısmının DİKEY ayrım
# olması ve onu roll'un üretmesi. "Daha az manevra = daha güvenli" burada
# yanlış; roll'u düşürürsen aralığı da büyütmen gerekir.
ROLL_ACISI_DEG = 30.0

# --- Çarpışma ---------------------------------------------------------------
# Uçaklar arası kabul edilen en küçük mesafe. Plan bunu ihlal ederse görev
# başlamaz. GPS hatası + pervane çapı + akış etkisi için bolca pay.
MIN_AYRIM_M = 4.0

# MAVLink GPS_FIX_TYPE. 5/6 = RTK; ancak orada konum hatasi cm mertebesine
# iner. Alttaki degerlerde metre mertebesinde hata var ve carpisma marji
# (5.16 m) bunu SOGURMAK zorunda kalir. RTK ENGEL DEGIL, uyari.
_FIX_ADI = {0: 'yok', 1: 'fixsiz', 2: '2D', 3: '3D', 4: 'DGPS',
            5: 'RTK-Float', 6: 'RTK-FIX'}

# --- Zamanlama (saniye) — 1 m/s'e göre; toplam 5 dk sınırına sığmalı --------
# Hız PX4'te: MPC_XY_VEL_MAX (31 Tem: 12 -> 1 -> 2 -> 4 m/s).
# 4 m/s'te bütçe: arm+kalkış ~30 + 4 bacak x 4.5 + manevralar ~25 +
# yerleşmeler ~48 + iniş (18 m / 0.7 m/s) ~26 =~ 150 s. Bol pay var.
#
# HIZ ARTTIKCA CARPISMA MARJI INCELIR: plan_dogrula KOMUT EDILEN geometriyi
# denetliyor, gercek ucusta hedefe yaklasirken frenleme mesafesi hizin
# KARESIYLE buyuyor. 3 drone senaryosunda kritik an 5.16 m; 4 m/s'te iki
# ucakta birden ~0.5 m asma olursa 4.2 m'ye iner (esik 4.0). Cok dronlu
# ucusta ya hizi 2'ye dondur ya ARALIK_M'i 12'ye cikar.
ARM_ASIM_S = 10
KALKIS_ASIM_S = 60
ADIM_ASIM_S = 70
YERLESME_S = 6.0        # YALNIZ manevra adimlarindan sonra (roll, rotasyon,
                        # formasyon, irtifa). Duz seyir bacaklarinda beklenmez:
                        # gosterilecek bir sey yok ve 5 dk sinirinda 24 sn yer actik.
GOREV_ASIM_S = 285

# AgentStatus.flight_mode degerleri (swarm_interfaces/msg/AgentStatus.msg)
# Bir rotasyonda yon kac derecelik dilimler halinde verilsin.
# NEDEN: OFFBOARD'da yon setpoint'i DOGRUDAN gecer; MPC_YAWRAUTO_MAX (25/s)
# yalniz Auto modlarda uygulanir, ic dongu tavani ise MC_YAWRATE_MAX=200/s.
# Yani 90'lik tek sicrama yarim saniyede donduruyor — sahada "ani donus"
# diye goruldu (31 Temmuz, ilk tam gorev). Dilimlere bolunce donus hem
# yumusuyor hem videoda rotasyon net gorunuyor (yonergenin sarti).
# MC_YAWRATE_MAX'e DOKUNULMADI: o ucagin toparlama yetenegi.
YAW_ADIM_DEG = 20.0
YAW_ADIM_BEKLE_S = 0.8

_MOD_OFFBOARD = 4
# Pilot modlari: MANUAL, ALTCTL, POSCTL, ACRO, STABILIZED. Bunlardan biri
# gorulurse kumandadan devralinmis demektir.
_PILOT_MODLARI = frozenset({1, 2, 3, 9, 10})

# BASE ESP KOMUTLARI HIZ SINIRINA TABI — bu aralik ondan.
# firmware/esp32_mesh/RX BASE/src/main.cpp:
#     TIP_KOMUT (arm/takeoff/land/rtl) -> JOYSTICK_MIN_ARALIK_MS = 200
#     TIP_GOTO                          -> MESH_GONDERIM_MIN_MS   =  50
# Sinir TIP BASINA tutulur (_son_tip_gonderim_ms[tip]), HEDEF BASINA DEGIL.
# Yani iki drone'a ayni tipte komut yollarsak ayni yuvayi paylasirlar ve
# ikincisi SESSIZCE DUSER.
#
# 1 Agustos'ta bu tam olarak yasandi: iki drone'a takeoff art arda gonderildi,
# ylp00 kalkti, ylp01 armli halde yerde kaldi. ylp01'in ESP logu drone 1'e
# giden dort takeoff paketini duydugunu ama kendisine hic gelmedigini
# gosteriyordu. Arm'lar calismisti cunku aralarinda teyit beklemesi vardi
# (2.5 ve 3.5 sn).
#
# ASIL COZUM ARTIK BASE KOPRUSUNDE: esp32_bridge_node._guided_gonder tum
# guided cerceveleri tek kuyruga alip tip basina arali gonderiyor ve
# ucaklara SIRAYLA veriyor (olculdu: her ucak 4/4 cerceve aliyor, oncesinde
# ikinci ucak 1/4 aliyordu). Burasi artik yalniz HTTP'yi dovmemek icin
# kucuk bir aralik; garanti orada.
KOMUT_ARALIK_S = 0.05

# --- Ucus dinamigi ----------------------------------------------------------
# SETPOINT YURUTULUR, HEDEF TEK ADIMDA VERILMEZ. Bkz. git_ve_bekle().
# Bu degerler UCAKTAKI parametreleri DEGISTIRMEZ; MPC_XY_VEL_MAX 4 m/s tavan
# olarak kalir. Tavani dusurmemek bilincli: carpisma kacinmasinin kacis payi
# oradan geliyor ve kumandadaki POSCTL de ayni parametreyle sinirli.
# LIDER — KALKAR ama YERINDE asili durur (yatayda hic kimildamaz).
# Ilk yazimda "lider yerde kalir" diye kurmustum, YANLISTI: istenen, lider de
# kalkip kendi noktasinin ustunde durmasi, takipcinin yanina gelmesi.
LIDER: int | None = None

GOREV_HIZ_MPS = 2.0          # yatay yurutme hizi
GOREV_DIKEY_HIZ_MPS = 1.0    # irtifa degisim hizi (motor isinmasi: daha yavas)
# SETPOINT GONDERIM ARALIGI — 0.5 idi, "gaz bas-cek" bundandi (2 Agustos).
#
# 0.5 sn'de bir 2.0 m/s x 0.5 = 1.0 METRE birden ileri atiyordu. PX4'e rampa
# degil MERDIVEN gidiyordu: her basamakta konum hatasi aniden 1 m buyuyor,
# MPC_XY_P (uctan okundu: 0.95) ile hiz talebi ~0.95 m/s sicriyor, ucak
# hizlaniyor, hatayi kapatinca yavasliyor, 0.5 sn sonra yeni basamak.
# Saniyede iki kez. Olculen hiz dizisi: 0.5-1.2-1.3-1.9-1.6-2.2-1.7 m/s.
#
# SONRA (2 Agustos, adim 1): yurutme px4_bridge'e TASINDI. Burasi artik ara
# nokta uretmiyor, adimin HEDEFINI tekrar tekrar gonderiyor. Dolayisiyla bu
# aralik "yorunge cozunurlugu" degil, iki isin periyodu:
#   1) guvenlik denetimleri (kill/failsafe/offboard/kacis) — 5 Hz yeterli
#   2) hedefin tekrari — mesh'te ~%30 kayip var, tekrar dayanikliligi verir
# Hedefin BIR KEZ ulasmasi yeterli oldugu icin (drone 10 Hz yerel tekrar
# yapiyor) 10 Hz'e gerek kalmadi; 0.2 mesh yukunu yariya indiriyor ve
# RTCM'e yer aciyor.
SETPOINT_ADIM_S = 0.2        # hedef tekrari + guvenlik denetimi periyodu
TASMA_M = 3.0                # setpoint ucaktan en fazla bu kadar onde olabilir

# --- Kacis kesicisi (bkz. git_ve_bekle) -------------------------------------
# Hedefe EN COK yaklastigi mesafeden bu kadar geri giderse ve ardisik
# KACIS_ARDISIK olcumde oyle kalirsa gorev kesilir. 1 Agustos 22:18'de bu
# kesici yoktu; mesafe 6.5 -> 78.7 m buyudu ve kod 40 sn seyretti.
KACIS_MARJ_M = 4.0
# KACINMA ACIKKEN MARJ GENISLER — yoksa kesici kacinmayi BOGAR.
#
# basit_kacinma setpoint'i max_itme_m kadar (varsayilan 6.0 m) kaydirabiliyor.
# Normal marj 4.0 m oldugu icin bir kacinma manevrasi kesicinin tanimina TAM
# UYUYOR: "hedeften 4 m uzaklasti ve oyle kaldi". Yani kacinma calissa bile
# gorev onu kacis sanip inis komutu gonderirdi — hem testi imkansiz kilar hem
# gercek gorevde bir kacinma manevrasini gorev iptaline cevirirdi.
#
# 8.0 = max_itme (6.0) + pay. Koruma zayiflar ama kaybolmaz: 1 Agustos'taki
# kacisda mesafe 6.5 -> 78.7 m gitmisti; 8 m marj + 0.8 sn onay ile en kotu
# kayip ~11 m olurdu. 78 metrenin yanina yaklasmaz.
#
# BILEREK ACIK BAYRAK: --kacinma verilmeden genislemiyor. Operator kacinmayi
# actigini beyan etmek zorunda; sessizce gevsemesi istenmez.
KACIS_MARJ_KACINMA_M = 8.0
# ONAY SURESI, ORNEK SAYISI DEGIL. Onceden "ardisik 3 olcum" idi ve bu
# SETPOINT_ADIM_S'e gizlice bagliydi: aralik 0.5 -> 0.1 sn olunca onay
# suresi 1.5 sn'den 0.3 sn'ye duser ve ruzgar darbesi yanlis alarm verirdi.
# Sure olarak yazilinca dongu hizindan bagimsiz.
KACIS_ONAY_S = 0.8           # en kotu kayip: 4 m + 4 m/s x 0.8 sn = 7.2 m

# --- Tirmanis oturmasi (bkz. irtifa ofseti olcumu) --------------------------
# Ofset, ucak HAREKETSIZ iken olculmeli. Tirmanis 1 m/s ile bitiyor ve
# 0.15 m/s'in altina inmesi ~1 sn suruyor; 6 sn tavan fazlasiyla yeterli.
OTURMA_DIKEY_HIZ_MPS = 0.15
OTURMA_ASIM_S = 6.0

_son_komut_t = 0.0
_iniyor = False
_HARITA_DOSYA = None
_SENARYO = "kanit"
_KACINMA_ACIK = False        # --kacinma: kacis kesicisinin marjini genisletir


# --- HTTP -------------------------------------------------------------------
def _komut_araligi_bekle() -> None:
    """Iki mesh komutu arasinda base ESP'nin hiz sinirini bekler."""
    global _son_komut_t
    kalan = KOMUT_ARALIK_S - (time.time() - _son_komut_t)
    if kalan > 0:
        time.sleep(kalan)
    _son_komut_t = time.time()


def _istek(yol: str, yontem: str = "POST", govde: dict | None = None):
    import json as _json
    # Yalniz mesh'e cikan guided komutlari sinirla; telemetri okumasi degil.
    if yontem == "POST" and yol.startswith("/api/guided/"):
        _komut_araligi_bekle()
    veri = None
    basliklar = {}
    if govde is not None:
        veri = _json.dumps(govde).encode()
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(YKI + yol, data=veri, headers=basliklar, method=yontem)
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_S) as c:
            return _json.loads(c.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{yol} -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{yol} -> YKİ'ye ulaşılamıyor ({e.reason}). "
                           "src/gcs/yki_baslat.sh çalışıyor mu?") from None


def durum() -> dict:
    snap = _istek("/api/telemetry/snapshot", "GET")
    return {d["drone_id"]: d for d in snap.get("drones", [])}


def durum_toleransli(kuru: bool) -> dict:
    try:
        return durum()
    except RuntimeError:
        if kuru:
            return {}
        raise


# --- Formasyon geometrisi ---------------------------------------------------
def _merkezle(ofsetler):
    """Ofsetleri merkezle: toplamları sıfır olsun.

    Şartname 'sürü merkezi' üzerinden konuşuyor; ofsetlerin ağırlık merkezi
    sıfır olursa komut verdiğimiz nokta gerçekten sürünün merkezi olur.
    """
    n = len(ofsetler)
    oi = sum(o[0] for o in ofsetler) / n
    od = sum(o[1] for o in ofsetler) / n
    return [(o[0] - oi, o[1] - od) for o in ofsetler]


def formasyon_ofsetleri(ad: str, n: int):
    """Gövde ekseninde (ileri, sağ) ofsetleri, METRE. Merkezlenmiş döner."""
    if ad == "okbasi":
        # Lider önde; kanatlar geride, ±KANAT_ACISI ile açılarak.
        a = math.radians(KANAT_ACISI_DEG)
        o = [(0.0, 0.0)]
        for k in range(1, n):
            yan = 1.0 if k % 2 == 1 else -1.0
            kat = (k + 1) // 2
            o.append((-math.cos(a) * ARALIK_M * kat, yan * math.sin(a) * ARALIK_M * kat))
        return _merkezle(o)
    if ad == "kolon":
        o = [(-ARALIK_M * i, 0.0) for i in range(n)]
        return _merkezle(o)
    if ad == "cizgi":
        o = [(0.0, ARALIK_M * i) for i in range(n)]
        return _merkezle(o)
    raise ValueError(f"bilinmeyen formasyon: {ad}")


def egim_dz(ofsetler, pitch_deg: float, roll_deg: float):
    """Eğim manevrasının slot başına irtifa deltası (metre, yukarı +).

    swarm_core.formation_control.manual_kinematics.apply_tilt ile AYNI
    matematik. Ortalamanın çıkarılması şartnamenin 'sürü merkezinin konumunu
    SABİT tutarak' şartını sağlar: bazı slot yukarı, bazı aşağı, net kayma 0.
    """
    if pitch_deg == 0.0 and roll_deg == 0.0:
        return [0.0] * len(ofsetler)
    tp = math.tan(math.radians(pitch_deg))
    tr = math.tan(math.radians(roll_deg))
    dz = [-dx * tp + dy * tr for (dx, dy) in ofsetler]
    ort = sum(dz) / len(dz)
    return [d - ort for d in dz]


def yon_dilimle(bas: float, son: float):
    """Bastan sona EN KISA yonden, YAW_ADIM_DEG'lik ara yonler uretir.

    Son eleman her zaman tam hedef yondur. Fark kucukse bos doner
    (ara adim gereksiz).
    """
    fark = (son - bas + 180.0) % 360.0 - 180.0   # -180..180, en kisa yon
    if abs(fark) <= YAW_ADIM_DEG:
        return []
    n = int(abs(fark) // YAW_ADIM_DEG)
    return [(bas + fark * (i + 1) / (n + 1)) % 360.0 for i in range(n)]


def yon_derece(a, b) -> float:
    """a'dan b'ye pusula yönü (kuzeyden saat yönüne, derece)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


def slot_dunya(merkez, heading_deg: float, ileri: float, sag: float):
    """Gövde ofsetini NED (kuzey, doğu)'ya çevirir."""
    h = math.radians(heading_deg)
    return (merkez[0] + ileri * math.cos(h) + sag * (-math.sin(h)),
            merkez[1] + ileri * math.sin(h) + sag * math.cos(h))


def hedefler_uret(merkez, heading, formasyon, irtifa, roll_deg,
                  onceki=None, slot=None, yeniden_ata=False):
    """drone_id -> (kuzey, doğu, irtifa). slot: drone_id -> slot indeksi.

    SLOT ATAMASI NE ZAMAN DEĞİŞİR — bu ayrım videoyu belirliyor:

    * Rotasyon ve eğim adımlarında slotlar SABİT kalır. Yoksa "en kısa yol"
      araması uçakları birbirinin slotuna yerleştiriyor; formasyon dönüyor
      ama uçaklar yerinde sayıyormuş gibi görünüyor (kuru koşuda ölçüldü:
      90° rotasyonda yatay hareket 2.7 m'ye düşüyordu). Yönerge rotasyonun
      "net bir şekilde" görünmesini istiyor, o yüzden uçaklar gerçekten
      savrulmalı.
    * FORMASYON DEĞİŞİMİNDE yeniden atama yapılır. Orada sabit atama
      uçakları birbirinin yerine yollayıp KAFA KAFAYA geçiriyordu.
    """
    n = len(DRONELAR)
    ofs = formasyon_ofsetleri(formasyon, n)
    dz = egim_dz(ofs, 0.0, roll_deg)
    noktalar = [slot_dunya(merkez, heading, *o) + (irtifa + z,)
                for o, z in zip(ofs, dz)]

    if slot is None:
        slot = {did: i for i, did in enumerate(DRONELAR)}

    if yeniden_ata and onceki:
        en_iyi, en_ucuz = None, float("inf")
        for perm in itertools.permutations(range(n)):
            maliyet = sum(
                math.dist(noktalar[perm[i]], onceki[did])
                for i, did in enumerate(DRONELAR) if did in onceki
            )
            if maliyet < en_ucuz:
                en_ucuz, en_iyi = maliyet, perm
        slot = {did: en_iyi[i] for i, did in enumerate(DRONELAR)}

    return {did: noktalar[slot[did]] for did in DRONELAR}, slot


# --- Çarpışma doğrulaması ---------------------------------------------------
def _min_mesafe_gecis(a0, a1, b0, b1) -> float:
    """İki uçak düz çizgide EŞ ZAMANLI giderken aralarındaki en küçük mesafe.

    Göreli konum r(t) = (a0-b0) + t*((a1-a0)-(b1-b0)), t in [0,1].
    |r(t)|'nin minimumu kapalı formülle bulunur — örnekleme yok, kesin.
    """
    r0 = tuple(a0[k] - b0[k] for k in range(3))
    r1 = tuple(a1[k] - b1[k] for k in range(3))
    d = tuple(r1[k] - r0[k] for k in range(3))
    dd = sum(x * x for x in d)
    if dd < 1e-9:
        return math.dist(r0, (0.0, 0.0, 0.0))
    t = -sum(r0[k] * d[k] for k in range(3)) / dd
    t = max(0.0, min(1.0, t))
    p = tuple(r0[k] + t * d[k] for k in range(3))
    return math.dist(p, (0.0, 0.0, 0.0))


def plan_dogrula(plan, baslangic=None) -> bool:
    """Uçmadan önce çarpışmasızlığı KANITLAR.

    İki şey denetlenir:
      1. Her adımda uçaklar arası mesafe (durağan hal)
      2. Bir adımdan diğerine GEÇERKEN en çok yaklaştıkları an
    İkincisi şart: hedefler ayrı ayrı güvenli olsa bile yollar kesişebilir.
    """
    if len(DRONELAR) < 2:
        print("\n=== ÇARPIŞMA DOĞRULAMASI: tek drone, denetim gereksiz ===")
        return True

    print(f"\n=== ÇARPIŞMA DOĞRULAMASI (eşik {MIN_AYRIM_M:.1f} m) ===")
    tamam = True
    en_kotu = (float("inf"), "")

    # YERDEKI GERCEK KONUM da denetlenir. Bu adim olmadan "kalkis noktasindan
    # ilk formasyona gecerken kesisiyorlar mi" sorusu hic sorulmuyordu.
    if baslangic:
        plan = [("YER (gerçek konum)", 0.0, baslangic, False)] + list(plan)

    for i, (etiket, _heading, hedefler, *_) in enumerate(plan):
        for a, b in itertools.combinations(DRONELAR, 2):
            m = math.dist(hedefler[a], hedefler[b])
            if m < en_kotu[0]:
                en_kotu = (m, f"{etiket} (durağan, d{a}-d{b})")
            if m < MIN_AYRIM_M:
                print(f"  İHLAL  {etiket}: d{a}-d{b} = {m:.2f} m")
                tamam = False
        if i == 0:
            continue
        onceki = plan[i - 1][2]
        for a, b in itertools.combinations(DRONELAR, 2):
            # Üç senaryo birden denetlenir. İkisi ve üçüncüsü şart, çünkü
            # "ikisi de eş zamanlı, aynı hızda gider" varsayımı sahada
            # tutmayabilir: mesh paketi biri için geç gelebilir, rüzgâr birini
            # yavaşlatabilir, biri hedefine erken oturup bekleyebilir.
            # DONMUŞ senaryosu bu durumların hepsini kapsayan en kötü hâldir.
            senaryolar = (
                ("eş zamanlı", onceki[a], hedefler[a], onceki[b], hedefler[b]),
                (f"d{a} donmuş", onceki[a], onceki[a], onceki[b], hedefler[b]),
                (f"d{b} donmuş", onceki[a], hedefler[a], onceki[b], onceki[b]),
            )
            for ad, a0, a1, b0, b1 in senaryolar:
                m = _min_mesafe_gecis(a0, a1, b0, b1)
                if m < en_kotu[0]:
                    en_kotu = (m, f"{plan[i-1][0]} -> {etiket} ({ad}, d{a}-d{b})")
                if m < MIN_AYRIM_M:
                    print(f"  İHLAL  {plan[i-1][0]} -> {etiket}: "
                          f"d{a}-d{b} [{ad}] {m:.2f} m'ye yaklaşıyor")
                    tamam = False

    print(f"  en kritik an: {en_kotu[0]:.2f} m  ({en_kotu[1]})")
    print("  SONUÇ: " + ("GEÇTİ" if tamam else "KALDI — görev başlatılmayacak"))
    return tamam


# --- Plan kurulumu ----------------------------------------------------------
def plan_kur(merkez0, baslangic=None):
    """Bütün görevi (etiket, hedefler) adımları olarak kurar.

    Uçmadan önce tamamı kurulur ki doğrulanabilsin. Noktalar kalkış
    merkezine GÖRELİ: P1=(K,0) P2=(K,K) P3=(0,K) — çapraz çarpım K^2 != 0,
    yani üçü doğrusal DEĞİL (yönergenin şartı).
    """
    K = KENAR_M
    # Ucgen once yerel eksende kurulur (ileri, saga), sonra ROTA_YONU_DEG
    # kadar dondurulur. Boylece sekil ve carpismasizlik aynen korunur,
    # yalniz sahadaki yonelim degisir.
    h = math.radians(ROTA_YONU_DEG)
    def _dondur(ileri, saga):
        return (merkez0[0] + ileri * math.cos(h) + saga * (-math.sin(h)),
                merkez0[1] + ileri * math.sin(h) + saga * math.cos(h))
    P1 = _dondur(K, 0.0)
    P2 = _dondur(K, K)
    P3 = _dondur(0.0, K)

    plan = []
    # ILK ADIMIN SLOT ATAMASI GERCEK YER KONUMUNA GORE. Onceden sabitti
    # (drone 1 -> lider, drone 2 -> kanat) ve ucaklar ters yerlestirilirse
    # kalkista BIRBIRLERININ ICINDEN geciyorlardi. Ustelik dogrulayici bunu
    # goremiyordu: yalnizca plan adimlari ARASINI denetliyor, yerdeki
    # gercek konumdan ilk adima gecisi denetlemiyordu.
    onceki = dict(baslangic) if baslangic else None
    slot = None

    def ekle(etiket, merkez, heading, formasyon, irtifa, roll,
             yeniden_ata=False, beklet=True):
        nonlocal onceki, slot
        h, slot = hedefler_uret(merkez, heading, formasyon, irtifa, roll,
                                onceki, slot, yeniden_ata)
        # heading PLANA yazılır. Onceden adım sırasında "bir önceki hedeften
        # bu hedefe" diye türetiliyordu; ilk adımda önceki olmadığı için
        # burun kuzeye (0°) bakıyordu. Formasyonun yönü zaten burada belli.
        plan.append((etiket, heading, h, beklet))
        onceki = h

    y1 = yon_derece(merkez0, P1)
    y2 = yon_derece(P1, P2)
    y3 = yon_derece(P2, P3)
    y4 = yon_derece(P3, merkez0)

    # 1) Kalkış sonrası diziliş — ok başı, P1 yönünde
    # yeniden_ata=True: ucaklar en yakin slota gitsin, kesismesin.
    ekle("kalkis/okbasi", merkez0, y1, "okbasi", GOREV_IRTIFA_M, 0.0,
         yeniden_ata=bool(baslangic))
    # 2) P1'e
    ekle("-> P1", P1, y1, "okbasi", GOREV_IRTIFA_M, 0.0, beklet=False)
    # 3) P1'de ROLL
    ekle("P1: ROLL %+.0f" % ROLL_ACISI_DEG, P1, y1, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG)
    # 4) rotasyon (P2 yönü), roll KORUNARAK
    ekle("P1: rotasyon->P2", P1, y2, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG)
    # 5) roll'lu halde P2'ye
    ekle("-> P2 (roll'lu)", P2, y2, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG, beklet=False)
    # 6) P2'de roll düzelt
    ekle("P2: roll duzelt", P2, y2, "okbasi", GOREV_IRTIFA_M, 0.0)
    # 7) P2'de FORMASYON DEĞİŞİMİ (ok başı -> çizgi), yön sabit.
    #    Slot yeniden ataması YALNIZ BURADA: şekil değiştiği için sabit atama
    #    uçakları birbirinin yerine yollayıp kafa kafaya geçirirdi.
    ekle("P2: FORMASYON okbasi->cizgi", P2, y2, "cizgi", GOREV_IRTIFA_M, 0.0,
         yeniden_ata=True)
    # 8) rotasyon (P3 yönü)
    ekle("P2: rotasyon->P3", P2, y3, "cizgi", GOREV_IRTIFA_M, 0.0)
    # 9) P3'e
    ekle("-> P3", P3, y3, "cizgi", GOREV_IRTIFA_M, 0.0, beklet=False)
    # 10) P3'te İRTİFA DEĞİŞİMİ
    ekle("P3: IRTIFA %.0f->%.0f m" % (GOREV_IRTIFA_M, YENI_IRTIFA_M),
         P3, y3, "cizgi", YENI_IRTIFA_M, 0.0)
    # 11) rotasyon (eve yön)
    ekle("P3: rotasyon->EV", P3, y4, "cizgi", YENI_IRTIFA_M, 0.0)
    # 12) kalkış noktasına dön
    ekle("-> EV (kalkis noktasi)", merkez0, y4, "cizgi", YENI_IRTIFA_M, 0.0, beklet=False)
    return plan


def _origin_bul(t):
    """Telemetriden NED origin'ini turetir.

    Drone hem lat/lon hem NED bildiriyor; ikisinin farki origin'i verir.
    Yapilandirmadaki sabiti okumaktansa bunu tercih ediyoruz: origin
    yanlis ayarlanmissa bile burada GERCEK donusum cikar, yani haritaya
    koydugumuz nokta ucagin gercekten gidecegi yer olur.
    """
    for d in t.values():
        if d.get("connected") and abs(d.get("lat", 0.0)) > 0.001:
            enlem = d["lat"] - d["pos_x"] / 111320.0
            boylam = d["lon"] - d["pos_y"] / (111320.0 * math.cos(math.radians(d["lat"])))
            return enlem, boylam
    return None


# UYDU GORUNTUSUNUN GEOREFERANS KAYMASI (1 Agustos'ta goruldu).
#
# QGC, YKI ve bu harita AYNI lat/lon'u ciziyor — dogrulandi: telemetri
# 38.6905781/39.1610555, YKI paneli 38.69058/39.16106, bu harita
# 38.6905782/39.1610556. Koordinat RTK-Fixed, ~2 cm. Yani kayan sey KOORDINAT
# DEGIL, ALTLIK GORUNTU: her saglayicinin georeferansi birkac metre farkli
# (bu harita Esri, YKI OpenStreetMap, QGC kendi saglayicisi).
#
# Sonucu onemsiz degil: harita bizim TEK engel kontrolumuz. Goruntu 4 m
# kaymissa "rotada bina yok" hukmu de 4 m kaymis demektir.
#
# Olculunce buraya (kuzey, dogu) metre yazilir; --harita-ofset ile de
# verilebilir. YALNIZ CIZIME uygulanir: ned_to_latlon'un tek kullanicilari
# koordinat_yaz ve harita_yaz'dir, ucus geometrisi NED'de kalir ve bundan
# ETKILENMEZ.
HARITA_OFSET_KD = (0.0, 0.0)


def ned_to_latlon(origin, kuzey, dogu):
    kuzey += HARITA_OFSET_KD[0]
    dogu += HARITA_OFSET_KD[1]
    enlem = origin[0] + kuzey / 111320.0
    boylam = origin[1] + dogu / (111320.0 * math.cos(math.radians(origin[0])))
    return enlem, boylam


def _plan_noktalari(plan, merkez0):
    """Planin gectigi NOKTALARI (adim merkezleri) sirayla dondurur.

    NEDEN PLANDAN TURETILIYOR: onceden bu liste kanit senaryosunun ucgeni
    (P1/P2/P3) olarak SABIT hesaplaniyordu. Baska senaryolarda ekrana ve
    haritaya YANLIS noktalar basiyordu — ve harita bizim tek engel
    kontrolumuz oldugu icin bu kabul edilemez.
    """
    noktalar = [("KALKIS/EV", merkez0)]
    for etiket, _h, hedefler, *_ in plan:
        n = len(hedefler)
        merkez = (sum(v[0] for v in hedefler.values()) / n,
                  sum(v[1] for v in hedefler.values()) / n)
        if math.dist(merkez, noktalar[-1][1]) < 1.0:
            continue                      # ayni noktada duruyor, tekrar yazma
        noktalar.append((etiket.split(":")[0].strip(), merkez))
    return noktalar


def koordinat_yaz(plan, merkez0, origin):
    """Gorev noktalarini GPS olarak basar — haritada kontrol edilebilsin.

    NEDEN VAR: kod engel GORMEZ. Ucmadan once noktalari haritaya koyup
    bina/agac var mi diye BAKMAK, elimizdeki tek engel kontrolu.
    """
    if origin is None:
        print("\n=== GPS KOORDİNATLARI: origin türetilemedi (telemetri yok) ===")
        return
    noktalar = _plan_noktalari(plan, merkez0)
    print("\n=== GPS KOORDİNATLARI (haritada kontrol et) ===")
    for ad, (kz, dg) in noktalar:
        la, lo = ned_to_latlon(origin, kz, dg)
        print(f"  {ad:<24} {la:.7f}, {lo:.7f}")


_HARITA_SABLON = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Yelpence - gorev rotasi</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#h{height:100%%;margin:0}
.bilgi{position:absolute;z-index:1000;top:10px;left:50px;background:#fff;
padding:8px 12px;font:13px system-ui;border-radius:6px;box-shadow:0 1px 6px #0006}
</style></head><body>
<div class="bilgi"><b>Gorev rotasi</b><br>%(ozet)s</div>
<div id="h"></div><script>
var m=L.map('h');
// maxNativeZoom 18 SART: bu bolgede Esri z19+ icin gercek goruntu yerine
// "Map data not available" yer tutucusu donduruyor (olculdu).
var uydu=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:22,maxNativeZoom:18,attribution:'Esri'}).addTo(m);
// IKINCI UYDU KATMANI: ayni saglayici, AYRI goruntu havuzu (farkli tarih ve
// georeferans). Katmanlar arasi gecip ucaklarin GERCEKTEN durdugu yere hangisi
// oturuyor diye bakmak icin — altlik kaymasini olcmenin en hizli yolu.
var clarity=L.tileLayer('https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:22,maxNativeZoom:19,attribution:'Esri Clarity'});
var sokak=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
 {maxZoom:22,maxNativeZoom:19,attribution:'OpenStreetMap'});
L.control.layers({'Uydu (Esri)':uydu,'Uydu (Esri Clarity)':clarity,
 'Sokak (binalar)':sokak}).addTo(m);

var yol=%(yol)s;        // gorev noktalari (adim merkezleri)
var hedef=%(hedef)s;    // her drone'un SON hedefi
var dronelar=%(dronelar)s;  // ucaklarin SU ANKI olculen yeri
var hepsi=[];
if(yol.length>1){
  var cizgi=yol.map(function(p){return [p[1],p[2]]});
  L.polyline(cizgi.concat([cizgi[0]]),{color:'#ff3b30',weight:3}).addTo(m);
  hepsi=hepsi.concat(cizgi);
}
yol.forEach(function(p){
  hepsi.push([p[1],p[2]]);
  L.circleMarker([p[1],p[2]],{radius:8,color:'#fff',weight:2,
    fillColor:'#34c759',fillOpacity:1}).addTo(m)
   .bindTooltip(p[0],{permanent:true,direction:'top'});
});
hedef.forEach(function(p){
  hepsi.push([p[1],p[2]]);
  L.circleMarker([p[1],p[2]],{radius:7,color:'#fff',weight:2,
    fillColor:'#0a84ff',fillOpacity:1}).addTo(m)
   .bindTooltip(p[0],{permanent:true,direction:'bottom'});
});
// TURUNCU = ucaklarin SU ANKI yeri. Iki ise yariyor:
//  1) altlik kaymasini gozle olcmek — isaretci ucagin gercekte durdugu
//     yerden ne kadar sapmis, oku
//  2) GOREVE GIRMEYEN ucaklar da gorunur; onlar da fiziksel engel
//     (1 Agustos: drone 1, gorevdeki drone 2'nin 1.98 m otesinde duruyordu
//      ve carpisma denetimi tek dronlu senaryoda bunu HIC gormuyordu)
dronelar.forEach(function(p){
  hepsi.push([p[1],p[2]]);
  // 5 m YARICAPLI CEMBER: kaymayi GOZLE METREYE cevirmek icin. Cember
  // gercek metreyle cizilir (L.circle, L.circleMarker DEGIL), yani
  // yakinlastirinca boyu degismez. Isaretci ucagin gercek yerinden bir
  // cember capi kadar sapmissa kayma ~10 m demektir.
  L.circle([p[1],p[2]],{radius:5,color:'#ff9f0a',weight:1,
    dashArray:'4,4',fill:false}).addTo(m);
  L.circleMarker([p[1],p[2]],{radius:9,color:'#000',weight:2,
    fillColor:'#ff9f0a',fillOpacity:0.95}).addTo(m)
   .bindTooltip(p[0],{permanent:true,direction:'right',offset:[10,14]});
});
// OLCEK CUBUGU: kaymayi "sanki biraz kaymis" degil, METRE olarak soyleyebil.
L.control.scale({metric:true,imperial:false,maxWidth:220}).addTo(m);
m.fitBounds(L.latLngBounds(hepsi).pad(1.5),{maxZoom:21});
</script></body></html>
"""


def harita_yaz(plan, merkez0, origin, dosya, t=None):
    """Gorev noktalarini UYDU goruntusu uzerinde tek haritaya yazar.

    NEDEN VAR: kod engel GORMEZ — harita, geofence, mesafe sensoru yok.
    Ucmadan once rotayi uydu goruntusune koyup bina/agac var mi diye
    BAKMAK, elimizdeki tek engel kontrolu.

    Iki katman cizilir: YESIL noktalar gorev noktalari (surunun merkezi),
    MAVI noktalar her drone'un son hedefi. Formasyon testi gibi yatay
    hareketin olmadigi senaryolarda tek yesil nokta cikar ve asil bilgi
    mavilerdedir — o yuzden ikisi de gosteriliyor.
    """
    if origin is None:
        print("  harita: origin turetilemedi, atlandi")
        return
    import json as _j
    yol = []
    for ad, (kz, dg) in _plan_noktalari(plan, merkez0):
        la, lo = ned_to_latlon(origin, kz, dg)
        yol.append([ad, la, lo])
    hedef = []
    if plan:
        for did, h in sorted(plan[-1][2].items()):
            la, lo = ned_to_latlon(origin, h[0], h[1])
            hedef.append([f"drone {did}", la, lo])
    # BAGLI HER ucak cizilir, yalnizca goreve girenler degil: goreve
    # girmeyen ucak da fiziksel engeldir. NED uzerinden ceviriliyor ki
    # plandaki noktalarla AYNI cerceveden (ve ayni ofsetle) ciksin.
    dronelar = []
    for did, d in sorted((t or {}).items()):
        if not d.get("connected") or abs(d.get("lat", 0.0)) < 0.001:
            continue
        la, lo = ned_to_latlon(origin, d["pos_x"], d["pos_y"])
        gorevde = "" if did in DRONELAR else "  (GÖREVDE DEĞİL)"
        dronelar.append([f"d{did} ŞU AN{gorevde}", la, lo])
    ofs = (f" &middot; harita ofseti {HARITA_OFSET_KD[0]:+.1f}K "
           f"{HARITA_OFSET_KD[1]:+.1f}D m" if any(HARITA_OFSET_KD) else "")
    ozet = (f"aralik {ARALIK_M:.0f} m &middot; yon {ROTA_YONU_DEG:.0f}&deg;{ofs}<br>"
            f"<b>kod engel gormez</b> - rotada bina/agac olmamali<br>"
            f"turuncu = ucaklarin SU ANKI yeri (altlik kaymasini buradan olc)")
    pathlib.Path(dosya).write_text(
        _HARITA_SABLON % {"yol": _j.dumps(yol), "hedef": _j.dumps(hedef),
                          "dronelar": _j.dumps(dronelar), "ozet": ozet},
        encoding="utf-8")
    print(f"\n=== HARITA YAZILDI ===\n  {dosya}")
    print(f"  Tarayicida ac:  xdg-open {dosya}")


def ayak_izi_yaz(plan, merkez0):
    """Kalkis noktasina gore HANGI YONDE NE KADAR yer gerektigini yazar.

    NEDEN VAR: kod binalari, agaclari, direkleri GORMEZ. Ucusun guvenligi
    tamamen rotanin acik alana denk gelmesine bagli. Ucmadan once
    "kuzeye 22 m, doguya 24 m yer lazim" diye somut gormek gerekiyor;
    "18 m'lik ucgen" demek yetmiyor cunku formasyon sapmasi ve rotasyon
    ucaklari noktalarin OTESINE tasiyor.
    """
    k = [h[0] - merkez0[0] for _e, _h, hed, *_ in plan for h in hed.values()]
    d = [h[1] - merkez0[1] for _e, _h, hed, *_ in plan for h in hed.values()]
    z = [h[2] for _e, _h, hed, *_ in plan for h in hed.values()]
    print("\n=== GEREKEN ALAN (kalkış noktasına göre) ===")
    print(f"  kuzey  : {max(k):+6.1f} m        güney  : {min(k):+6.1f} m")
    print(f"  doğu   : {max(d):+6.1f} m        batı   : {min(d):+6.1f} m")
    print(f"  irtifa : {min(z):.1f} - {max(z):.1f} m")
    print(f"  toplam kutu: {max(k)-min(k):.0f} m (K-G) x {max(d)-min(d):.0f} m (D-B)")
    print(f"  rota yönü  : {ROTA_YONU_DEG:.0f}°  (0=kuzey, 90=doğu)")
    print("  UYARI: kod engel GÖRMEZ. Bu kutunun içinde bina/ağaç/direk olmamalı.")


def plan_kur_test(merkez0, baslangic=None):
    """BASIT IKI DRONE TESTI — tam koreografiden once zinciri sinamak icin.

    Kalkis -> kuzeybatiya kisa gidis -> bekle -> irtifa degisimi -> eve don.

    Tam gorevden farki: formasyon degisimi, roll manevrasi ve cok noktali
    ucgen YOK. Amac ilk kez IKI ucagi birlikte havada tutmak ve formasyonun
    gercekten korunup korunmadigini gormek. Formasyon CIZGI: ucaklar gidis
    yonune DIK, yan yana — biri digerinin pervane akiminda kalmaz.
    """
    plan = []
    onceki = dict(baslangic) if baslangic else None
    slot = None

    def ekle(etiket, merkez, heading, formasyon, irtifa, roll,
             yeniden_ata=False, beklet=True):
        nonlocal onceki, slot
        h, slot = hedefler_uret(merkez, heading, formasyon, irtifa, roll,
                                onceki, slot, yeniden_ata)
        plan.append((etiket, heading, h, beklet))
        onceki = h

    KB = 315.0                      # kuzeybati
    MESAFE = 15.0
    r = math.radians(KB)
    hedef = (merkez0[0] + MESAFE * math.cos(r), merkez0[1] + MESAFE * math.sin(r))

    ekle("kalkis: cizgi dizilis", merkez0, KB, "cizgi", GOREV_IRTIFA_M, 0.0,
         yeniden_ata=bool(baslangic))
    ekle("-> kuzeybati %.0f m" % MESAFE, hedef, KB, "cizgi", GOREV_IRTIFA_M, 0.0,
         beklet=False)
    ekle("BEKLE (formasyon tutuyor mu)", hedef, KB, "cizgi", GOREV_IRTIFA_M, 0.0)
    ekle("IRTIFA %.0f->%.0f m" % (GOREV_IRTIFA_M, YENI_IRTIFA_M),
         hedef, KB, "cizgi", YENI_IRTIFA_M, 0.0)
    ekle("-> EV (kalkis noktasi)", merkez0, (KB + 180.0) % 360.0, "cizgi",
         YENI_IRTIFA_M, 0.0, beklet=False)
    return plan


def _kacis_marj() -> float:
    """Kaçış kesicisinin marjı — kaçınma açıkken geniş."""
    return KACIS_MARJ_KACINMA_M if _KACINMA_ACIK else KACIS_MARJ_M


def plan_kur_tam(t):
    """KANIT VİDEOSU KOREOGRAFİSİ — çizgi, ileri, roll, eksen, eve dönüş.

    Adımlar:
      1) çizgi dizilişi (lider kendi kalkış noktasında)
      2) liderin baktığı yönde TAM_MESAFE_M
      3) KUZEYDOĞU'ya rotasyon (lider yerinde, takipçi yay çizer)
      4) ROLL — lider sabit, takipçi ARALIK_M*tan(roll) kadar yukarı
      5) roll'u KORUYARAK KD navigasyonu, evin GÜNEYDOĞU ekseni üzerine
      6) irtifa eşitleme (roll sıfırlanır)
      7) GÜNEYDOĞU'ya rotasyon
      8) eve dönüş, formasyon korunarak
      9) iniş

    GÜNEYDOĞU EKSENİ: KD (45°) ile GD (135°) diktir; KD boyunca ilerlerken
    evin tam GD yönünde kaldığı TEK bir nokta vardır. Mesafesi, (P - ev)
    vektörünün KD birim vektörü üzerindeki izdüşümüdür (işaret ters).
    """
    lider = LIDER
    l = t[lider]
    H = (l["pos_x"], l["pos_y"])
    lyaw = l["yaw_deg"]

    ofs = formasyon_ofsetleri("cizgi", len(DRONELAR))
    slot = {lider: 0}
    for i, did in enumerate([d for d in DRONELAR if d != lider], start=1):
        slot[did] = i

    def _hedefler(nokta, yon, roll=0.0):
        """Lider 'nokta'da ve TAM_IRTIFA_M'de; formasyon 'yon'a, 'roll' eğimli.

        Roll'un dz'si LİDERE göre sıfırlanır: egim_dz sürü merkezini sabit
        tutuyor ve lideri aşağı alıyor; operatör liderin alçalmasını istemedi.
        """
        h = math.radians(yon)
        o_i, o_s = ofs[0]
        merkez = (nokta[0] - (o_i * math.cos(h) + o_s * (-math.sin(h))),
                  nokta[1] - (o_i * math.sin(h) + o_s * math.cos(h)))
        dz = egim_dz(ofs, 0.0, roll)
        dz = [z - dz[0] for z in dz]          # lider referans: kendisi 0
        noktalar = [slot_dunya(merkez, yon, *o) + (TAM_IRTIFA_M + z,)
                    for o, z in zip(ofs, dz)]
        return {did: noktalar[slot[did]] for did in DRONELAR}

    def _rotasyon(plan, nokta, bas, son, roll=0.0):
        """bas -> son yönüne KISA taraftan, geçiş noktalarıyla dilimleyerek."""
        fark = (son - bas) % 360.0
        if fark > 180.0:
            fark -= 360.0
        n = max(1, int(round(abs(fark) / DONUS_ROTASYON_ADIM_DEG)))
        for i in range(1, n + 1):
            ara = (bas + fark * i / n) % 360.0
            if i == n:
                plan.append((f"rotasyon -> {ara:.0f}° tamam", ara,
                             _hedefler(nokta, ara, roll), True))
            else:
                plan.append((f"rotasyon {i}/{n} -> {ara:.0f}°", ara,
                             _hedefler(nokta, ara, roll), False,
                             DONUS_GECIS_R_M))

    h0 = math.radians(lyaw)
    P = (H[0] + TAM_MESAFE_M * math.cos(h0), H[1] + TAM_MESAFE_M * math.sin(h0))
    kd = math.radians(TAM_KD_DEG)
    # Evin GD ekseni uzerine dusen nokta: (P-H)'nin KD uzerindeki izdusumu
    s = -((P[0] - H[0]) * math.cos(kd) + (P[1] - H[1]) * math.sin(kd))
    Q = (P[0] + s * math.cos(kd), P[1] + s * math.sin(kd))
    gd = (math.degrees(math.atan2(H[1] - Q[1], H[0] - Q[0])) + 360.0) % 360.0

    plan = [
        (f"çizgi dizilişi (lider d{lider})", lyaw, _hedefler(H, lyaw), True),
        (f"-> {TAM_MESAFE_M:.0f} m ileri (yön {lyaw:.0f}°)", lyaw,
         _hedefler(P, lyaw), TAM_BEKLEME_S),
    ]
    _rotasyon(plan, P, lyaw, TAM_KD_DEG)
    plan.append((f"ROLL {TAM_ROLL_DEG:.0f}° (takipçi yukarı)", TAM_KD_DEG,
                 _hedefler(P, TAM_KD_DEG, TAM_ROLL_DEG), True))
    plan.append((f"-> GD ekseni, roll KORUNARAK ({s:.0f} m)", TAM_KD_DEG,
                 _hedefler(Q, TAM_KD_DEG, TAM_ROLL_DEG), TAM_BEKLEME_S))
    plan.append(("irtifa EŞİTLE (roll 0)", TAM_KD_DEG,
                 _hedefler(Q, TAM_KD_DEG, 0.0), True))
    _rotasyon(plan, Q, TAM_KD_DEG, gd)
    plan.append((f"-> EV (lider d{lider} kalkış noktası)", gd,
                 _hedefler(H, gd), True))
    return plan


def plan_kur_donus(t):
    """ÇİZGİ formasyonu, 20 m ileri, 180° rotasyon, eve dönüş.

    ROTASYONDA LİDER YERİNDE DURUR, takipçi onun etrafında yay çizer.
    Formasyon merkezi her ara yön için, lider sabit kalacak şekilde geri
    hesaplanır — merkez etrafında döndürseydik lider de 10 m kayardı.

    ROTASYON DİLİMLENİR — bu şart, tercih değil. 180°'yi tek adımda vermek
    takipçinin başlangıç ve bitiş noktalarını liderin İKİ YANINA koyar;
    aradaki düz çizgi tam liderin üzerinden geçer. Setpoint düz gider, yay
    çizmez. plan_dogrula bunu zaten reddeder (ve etmeliydi).

    30°'lik dilimlerde takipçi lidere en yakın R*cos(15°) = 9.7 m'ye
    yaklaşır — ARALIK_M'nin (10 m) pratikte altına inmez.

    Dönüş yönü, dilimler boyunca KISA TARAFTAN gidilecek şekilde seçilir.
    """
    lider = LIDER
    l = t[lider]
    lk, ld, lyaw = l["pos_x"], l["pos_y"], l["yaw_deg"]

    ofs = formasyon_ofsetleri("cizgi", len(DRONELAR))
    slot = {lider: 0}
    for i, did in enumerate([d for d in DRONELAR if d != lider], start=1):
        slot[did] = i

    def _hedefler(nokta, yon):
        """Lider 'nokta'da, formasyon 'yon'a bakacak şekilde hedefler."""
        h = math.radians(yon)
        o_i, o_s = ofs[0]
        merkez = (nokta[0] - (o_i * math.cos(h) + o_s * (-math.sin(h))),
                  nokta[1] - (o_i * math.sin(h) + o_s * math.cos(h)))
        noktalar = [slot_dunya(merkez, yon, *o) + (DONUS_IRTIFA_M,)
                    for o in ofs]
        return {did: noktalar[slot[did]] for did in DRONELAR}

    h0 = math.radians(lyaw)
    ileri = (lk + DONUS_MESAFE_M * math.cos(h0),
             ld + DONUS_MESAFE_M * math.sin(h0))
    eve_yon = (lyaw + 180.0) % 360.0

    plan = [
        (f"çizgi dizilişi (lider d{lider})", lyaw, _hedefler((lk, ld), lyaw),
         True),
        (f"-> {DONUS_MESAFE_M:.0f} m ileri (yön {lyaw:.0f}°)", lyaw,
         _hedefler(ileri, lyaw), DONUS_BEKLEME_S),
    ]

    # 180° ROTASYON — dilim dilim. Lider sabit, takipçi yay çizer.
    n_dilim = max(1, int(round(180.0 / DONUS_ROTASYON_ADIM_DEG)))
    for i in range(1, n_dilim + 1):
        ara = (lyaw + 180.0 * i / n_dilim) % 360.0
        son = (i == n_dilim)
        if son:
            # SON dilimde tam varış istiyoruz: buradan eve uçulacak,
            # formasyonun oturmuş olması lazım.
            plan.append((f"rotasyon {i}/{n_dilim} -> {ara:.0f}° (eve bakıyor)",
                         ara, _hedefler(ileri, ara), True))
        else:
            # ARA NOKTA — 5. eleman geçiş yarıçapı. Uçak durmaz, yavaşlamaz,
            # burnunu ayrı bir fazda çevirmez; yay sürekli akar.
            plan.append((f"rotasyon {i}/{n_dilim} -> {ara:.0f}°",
                         ara, _hedefler(ileri, ara), False, DONUS_GECIS_R_M))

    plan.append((f"-> EV (lider d{lider} kalkış noktası)", eve_yon,
                 _hedefler((lk, ld), eve_yon), True))
    return plan


def plan_kur_takip(t):
    """İKİ DRONLU PROVA — ok başı kur, 15 m ileri, bekle, eve dön.

    Lider OPERATÖRÜN SEÇTİĞİ uçak ve slot 0'a sabitlenir. Formasyon merkezi,
    liderin istenen noktada olması için geri hesaplanır: ok başı ofsetleri
    _merkezle() ile merkezlendiği için lider merkezde DEĞİLDİR (n=2'de
    merkezin 3.54 m önünde, 3.54 m solunda).

    Bu yüzden "lider kalkış noktasına dönsün" demek, formasyon merkezini
    kalkış noktasına göndermek DEĞİLDİR — aradaki ofset kadar kaydırmak
    gerekir. Yoksa lider kendi kalkış noktasının 5 m ötesine iner.

    Yön SABİT: gidişte de dönüşte de liderin kalkış yönü. Uçaklar geri geri
    döner; formasyon yönelimi hiç değişmez ve yaw dilimleme devreye girmez.
    """
    lider = LIDER
    l = t[lider]
    lk, ld, lyaw = l["pos_x"], l["pos_y"], l["yaw_deg"]
    h = math.radians(lyaw)

    # Liderin baktığı yöne TAKIP_MESAFE_M
    hedef_k = lk + TAKIP_MESAFE_M * math.cos(h)
    hedef_d = ld + TAKIP_MESAFE_M * math.sin(h)

    ofs = formasyon_ofsetleri("okbasi", len(DRONELAR))
    # SLOT SABİT: lider 0, diğerleri sırayla. "En yakın slot" ataması
    # kullanılmıyor çünkü lideri operatör seçti.
    slot = {lider: 0}
    for i, did in enumerate([d for d in DRONELAR if d != lider], start=1):
        slot[did] = i

    def _hedefler(nokta):
        """Lider 'nokta'da olacak şekilde bütün slotların dünya konumu."""
        o_i, o_s = ofs[0]
        merkez = (nokta[0] - (o_i * math.cos(h) + o_s * (-math.sin(h))),
                  nokta[1] - (o_i * math.sin(h) + o_s * math.cos(h)))
        noktalar = [slot_dunya(merkez, lyaw, *o) + (TAKIP_IRTIFA_M,)
                    for o in ofs]
        return {did: noktalar[slot[did]] for did in DRONELAR}

    return [
        (f"ok başı dizilişi (lider d{lider})", lyaw, _hedefler((lk, ld)), True),
        (f"-> {TAKIP_MESAFE_M:.0f} m ileri (yön {lyaw:.0f}°)", lyaw,
         _hedefler((hedef_k, hedef_d)), TAKIP_BEKLEME_S),
        (f"-> EV (lider d{lider} kalkış noktası)", lyaw,
         _hedefler((lk, ld)), True),
    ]


def plan_kur_asili(t):
    """KAÇINMA TESTİ — tek uçak kendi yerinin üstünde asılı durur.

    Yatayda HİÇBİR komut verilmiyor: hedef, uçağın ölçülen kendi konumu.
    Dolayısıyla uçak yatayda kımıldarsa sebep bizim komutumuz DEĞİLDİR —
    ya kaçınmadır ya rüzgârdır, ve ikisi ayırt edilebilir (kaçınma yalnız
    komşu yaklaşırken ve ondan uzağa iter).

    Operatör bu sırada ÖTEKİ dronu kumandayla yaklaştırır. Kaçınmanın
    kendi yorumunda yazan durum tam olarak budur:
      "biz asılı duruyorsak teğeti hiç açmıyor. Oysa asılı dururken
       üstümüze gelen bir uçak, teğete en çok ihtiyaç duyduğumuz durum."

    İrtifa ayrımı güvenlik için: kaçınma yalnız yatay çalışıyor, o yüzden
    iki uçağı farklı irtifada tutmak testi bozmaz ama çarpışmayı imkânsız
    kılar.
    """
    did = DRONELAR[0]
    d = t[did]
    return [(f"ASILI DUR {ASILI_SURE_S:.0f}s (kaçınma testi)",
             d["yaw_deg"],
             {did: (d["pos_x"], d["pos_y"], ASILI_IRTIFA_M)},
             ASILI_SURE_S)]


def ucanlar():
    """Komut gonderilecek drone'lar. Lider de dahil — o da kalkiyor."""
    return list(DRONELAR)


def plan_kur_lider(t):
    """LİDER YANINA GEÇİŞ — lider yerde durur, takipçi sağına çizgi kurar.

    Lider hiç kalkmaz; yönü ve konumu TELEMETRİDEN okunur, elle girilmez.
    Takipçi liderin BURNUNUN SAĞINA (yaw + 90°) ARALIK_M mesafeye gider ve
    liderle AYNI yöne döner — çizgi formasyonu budur.

    Lider de KALKAR; hedefi kendi noktasının üstüdür, yani yatayda hiç
    kımıldamaz. İlk yazımda "lider yerde kalır" diye kurmuştum, yanlıştı.
    """
    lider = LIDER
    l = t[lider]
    lk, ld, lyaw = l["pos_x"], l["pos_y"], l["yaw_deg"]
    hedefler = {lider: (lk, ld, FORMASYON_TEST_IRTIFA_M)}
    sag = math.radians(lyaw + 90.0)
    takipciler = [d for d in DRONELAR if d != lider]
    for i, did in enumerate(takipciler, start=1):
        m = ARALIK_M * i
        hedefler[did] = (lk + m * math.cos(sag), ld + m * math.sin(sag),
                         FORMASYON_TEST_IRTIFA_M)
    return [
        (f"ÇİZGİ formasyonu — lider d{lider} yerinde asılı, takipçi sağına",
         lyaw, dict(hedefler), True),
        ("formasyonu TUT", lyaw, dict(hedefler), True),
    ]


def plan_kur_tekli(t):
    """TEK UÇAK — kalkış yönünde 7 m, bekle, aynı noktada 5 m tırman, bekle, in.

    YÖN TELEMETRİDEN OKUNUR. "Kalkış yaptığı yön" uçağın park edildiği
    yöndür; elle girilmez, ROTA_YONU_DEG'e de bakılmaz. Bunun bir yan
    faydası var: plandaki heading ölçülen yaw ile AYNI olduğu için yön
    dilimleme boş kalır, yani uçak burnunu hiç çevirmez. Uçuşta yine de
    ani bir dönüş görülürse sebebi bizim komutumuz DEĞİLDİR — bu senaryo
    o değişkeni yapısal olarak devre dışı bırakıyor.

    İki tırmanış var (0->5 ve 5->10) ve ikisi de aynı çerçeveden geçiyor;
    irtifa sıçraması varsa iki kere görünür, tek seferlik gürültüden
    ayırt edilebilir.
    """
    did = DRONELAR[0]
    d = t[did]
    k0, d0, yaw = d["pos_x"], d["pos_y"], d["yaw_deg"]
    r = math.radians(yaw)
    k1 = k0 + TEKLI_ILERLEME_M * math.cos(r)
    d1 = d0 + TEKLI_ILERLEME_M * math.sin(r)
    irt2 = TEKLI_IRTIFA_M + TEKLI_IRTIFA_ARTIS_M
    return [
        (f"ileri {TEKLI_ILERLEME_M:.0f} m (kalkış yönü {yaw:.0f}°)",
         yaw, {did: (k1, d1, TEKLI_IRTIFA_M)}, TEKLI_BEKLEME_S),
        (f"İRTİFA {TEKLI_IRTIFA_M:.0f} -> {irt2:.0f} m (aynı noktada)",
         yaw, {did: (k1, d1, irt2)}, TEKLI_BEKLEME_S),
    ]


def plan_kur_formasyon(merkez0, baslangic=None):
    """FORMASYON TESTI — rastgele yerlesimden cizgi formasyonuna, sonra inis.

    Amac: ucaklar NEREYE koyulursa koyulsun formasyonu kurabiliyor mu?
    Kalkis noktalari rastgele oldugu icin slot atamasi ve carpismasizlik
    dogrulamasi gercek bir sinav veriyor — plandaki noktalar degil,
    ucaklarin fiilen durdugu yer baslangic kabul ediliyor.

    Yatay hareket YOK: formasyon kalkis merkezinin etrafinda kuruluyor,
    sonra ayni yerde iniliyor. Boylece tek degisken formasyon kurma.
    """
    plan = []
    onceki = dict(baslangic) if baslangic else None
    slot = None

    def ekle(etiket, merkez, heading, formasyon, irtifa, roll,
             yeniden_ata=False, beklet=True):
        nonlocal onceki, slot
        h, slot = hedefler_uret(merkez, heading, formasyon, irtifa, roll,
                                onceki, slot, yeniden_ata)
        plan.append((etiket, heading, h, beklet))
        onceki = h

    y = ROTA_YONU_DEG
    # Tek adim: rastgele durduklari yerden cizgi formasyonuna.
    # yeniden_ata=True -> her ucak EN YAKIN slota gider, kesismezler.
    ekle("CIZGI formasyonu kur", merkez0, y, "cizgi", FORMASYON_TEST_IRTIFA_M,
         0.0, yeniden_ata=bool(baslangic))
    # Formasyon oturunca bir sure tut ki gozle gorulebilsin ve olcebilelim.
    ekle("formasyonu TUT", merkez0, y, "cizgi", FORMASYON_TEST_IRTIFA_M, 0.0)
    return plan


def plan_yaz(plan):
    print("\n=== GÖREV PLANI ===")
    # GECIS NOKTALARI TEK SATIRDA. Yay 80 noktaya bolununce her birini uc
    # satirla basmak plani okunmaz yapiyor; onemli olan yayin varligi ve
    # kac noktadan olustugu.
    gecis_sayisi = 0
    for _adim in plan:
        if len(_adim) > 4 and _adim[4] is not None:
            gecis_sayisi += 1
    if gecis_sayisi:
        print(f"  ({gecis_sayisi} geçiş noktası özetlendi — yay, durak değil)")
    for adim in plan:
        if len(adim) > 4 and adim[4] is not None:
            continue
        etiket, heading, hedefler = adim[0], adim[1], adim[2]
        print(f"  {etiket}   (yön {heading:.0f}°)")
        for did in DRONELAR:
            k, d, i = hedefler[did]
            print(f"      drone {did}: ({k:+7.1f},{d:+7.1f})  irtifa {i:5.1f} m")


# --- Komutlar ---------------------------------------------------------------
def git(did: int, hedef, heading_deg: float, kuru: bool, t_durum):
    k, d, irtifa = hedef
    mevcut = t_durum.get(did)
    if mevcut is None:
        if not kuru:
            raise RuntimeError(f"drone {did} telemetride yok")
    else:
        mesafe = math.hypot(k - mevcut["pos_x"], d - mevcut["pos_y"])
        if mesafe > MAX_GOTO_M:
            raise RuntimeError(
                f"GÜVENLİK: drone {did} hedefi {mesafe:.0f} m uzakta "
                f"(tavan {MAX_GOTO_M:.0f} m). Komut GÖNDERİLMEDİ.")
    if kuru:
        return
    _istek(f"/api/guided/{did}/goto", govde={
        "x": k, "y": d, "z": irtifa, "heading_deg": heading_deg})


MAKS_EGIM_DEG = 35.0   # bunun ustunde ucus normal degil (MPC_TILTMAX_AIR=30)


def guvenlik_ihlali(t) -> str | None:
    """Uçuşu DERHAL kesmeyi gerektiren durum varsa sebebini döndürür.

    1 AĞUSTOS, ylp00: kalkışta yerden kesilemeyip yerde kaydı, devrildi,
    operatör kill switch'e bastı. Kod bunların HİÇBİRİNİ görmedi ve
    KALKIS_ASIM_S dolana kadar 62 SANİYE bekledi. O 62 saniye boyunca uçak
    yerde yatıyordu. Kill switch mesh telemetrisinde ZATEN geliyordu
    (kill_switch_active), sadece kimse bakmıyordu.

    Bakılan üç şey:
      * kill switch  — operatör "hemen kes" dedi; beklemek saçma
      * failsafe     — PX4 kendi kontrolünü devraldı
      * aşırı eğim   — devrilme/çarpma; MPC_TILTMAX_AIR 30° iken 35° normal
                       uçuşta görülmez
    """
    for did in ucanlar():
        d = t.get(did)
        if d is None:
            continue
        if d.get("kill_switch_active"):
            return f"drone {did}: KILL SWITCH (operatör kesti)"
        if d.get("failsafe_active"):
            return f"drone {did}: FAILSAFE"
        egim = max(abs(d.get("roll_deg", 0.0)), abs(d.get("pitch_deg", 0.0)))
        if egim > MAKS_EGIM_DEG:
            return (f"drone {did}: AŞIRI EĞİM {egim:.0f}° "
                    f"(sınır {MAKS_EGIM_DEG:.0f}°) — devrilme olabilir")
    return None


def git_ve_bekle(hedefler, heading_deg: float, asim_s: float, kuru: bool,
                 t_baslangic, tolerans: float | None = None) -> bool:
    """Hedefi gönderir, uçağın varışını bekler ve uçuşu denetler.

    YÖRÜNGE ARTIK BURADA ÜRETİLMİYOR (2 Ağustos, adım 1). Üç aşamadan geçti:

      1) İlk hâl: son nokta TEK goto ile veriliyordu. OFFBOARD'da PX4 konum
         setpoint'ini yumuşatmaz (Auto'nun yörünge üreteci o yolda devrede
         DEĞİL), yani 8 m ötedeki nokta = anında MPC_XY_VEL_MAX kadar hız.
         Ölçüldü: 3.0-3.2 m/s, 4 m/s tavanına dayanmıştı.

      2) Sonra: setpoint BURADA yürütüldü. Hız 2 m/s'e oturdu ama bu sefer
         "gaz bas-çek" çıktı. Sebep ölçüldü: goto'lar burada 10 Hz üretilse
         de drone'a 6.6 Hz ve DÜZENSİZ varıyor (103/203/304 ms), çünkü
         mesh'te POSE/GOTO broadcast gidiyor ve broadcast'te 802.11 ACK/retry
         yok (firmware mesh_config.h:517'de yazılı). Kayıp ~%30 ve her kayıp
         bir sıçrama demek.

      3) Şimdi: yürütme px4_bridge'de, 50 Hz'de, hız ileri-beslemesiyle.
         Buradan yalnız ADIMIN HEDEFİ gidiyor ve tekrarlanıyor. Hedefin bir
         kez ulaşması yeterli — esp32_bridge onu 10 Hz yerel tekrar yayınlar.
         Paket kaybı artık zararsız: kaybolan paket aynı hedefi taşıyordu.

    HIZ VE TAŞMA FRENİ px4_bridge'de: guided_hiz_yatay_mps,
    guided_hiz_dikey_mps, guided_tasma_m (baslat.sh'den veriliyor).
    Buradaki GOREV_HIZ_MPS / GOREV_DIKEY_HIZ_MPS artık YALNIZ BİLGİ AMAÇLI —
    ikisi aynı değerde tutulmalı, yoksa ekrandaki sayı yalan söyler.

    UÇAKTAKİ MPC_XY_VEL_MAX BİLEREK DÜŞÜRÜLMEDİ (4.0 kalıyor):
      * çarpışma kaçınmasının kaçış payı o tavandan geliyor — görev hızına
        eşitlersek kaçış manevrası da 2 m/s'e iner ve itme yetersiz kalır
      * aynı parametre kumandadaki POSCTL'i de sınırlar; pilotun elinden
        manevra kabiliyetini almak güvenliği azaltır

    BURADA KALAN İŞ: güvenlik denetimi (pilot devraldı mı, OFFBOARD düştü mü,
    kill/failsafe/eğim, KAÇIŞ kesicisi) ve varış tespiti.
    """
    if kuru:
        return True
    baslangic_konum = {}
    for did in ucanlar():
        d = t_baslangic.get(did)
        if d is None:
            raise RuntimeError(f"drone {did} telemetride yok")
        baslangic_konum[did] = (d["pos_x"], d["pos_y"], d["alt_m"])
    onceki_konum = dict(baslangic_konum)
    # HIZ OLCUMU icin AYRI durum: telemetri gorev dongusunden YAVAS
    # yenilendigi icin, konumun GERCEKTEN degistigi anlara baglanir.
    olcum_konum = dict(baslangic_konum)
    olcum_t = {did: time.time() for did in baslangic_konum}
    son_hiz = {did: 0.0 for did in baslangic_konum}
    # KAÇIŞ KESİCİSİ durumu — her uçağın hedefe EN ÇOK yaklaştığı mesafe.
    en_yakin = {did: float("inf") for did in baslangic_konum}
    kacis_basladi = {did: None for did in baslangic_konum}

    basla = time.time()
    while time.time() - basla < asim_s:
        time.sleep(SETPOINT_ADIM_S)
        simdi = time.time()
        t = durum()

        # PİLOT DEVRALDI MI / OFFBOARD DÜŞTÜ MÜ — hemen anla, zaman aşımını
        # bekleme. Kumandadan müdahale edilirse (POSCTL, LAND, failsafe) o
        # uçak artık bizim setpoint'lerimizi izlemiyor; diğerlerini 70 sn
        # havada tutmanın anlamı yok.
        #
        # KARAR flight_mode ILE VERILIR, offboard_active ILE DEGIL.
        # offboard_active MESH'TEN GELMIYOR — esp32_bridge'in kendi yorumu:
        # "mesh'e CIKMAZ" (esp32_bridge_node.py:408, 1069). Bayrak hep False
        # kaliyor. 31 Temmuz'daki ilk canli ucusta tam bu yuzden YANLIS ALARM
        # verildi: telemetri "mode=Offboard, flight_mode=4" derken bayrak
        # False oldugu icin gorev 9.4 m'de kendini iptal etti ve saglam bir
        # ucus bosuna indirildi. flight_mode mesh pakette TASINIYOR ve dogru
        # geliyor.
        ihlal = guvenlik_ihlali(t)
        if ihlal:
            print(f"\n      !!! {ihlal} — görev durduruluyor")
            return False

        for did in ucanlar():
            d = t.get(did)
            if d is None:
                continue
            fm = d.get("flight_mode", 0)
            if fm in _PILOT_MODLARI:
                print(f"\n      !!! drone {did} PİLOT KONTROLÜNDE "
                      f"(mod={d.get('mode')}) — görev durduruluyor")
                return False
            if fm != _MOD_OFFBOARD:
                print(f"\n      !!! drone {did} OFFBOARD'DAN ÇIKTI "
                      f"(mod={d.get('mode')}, flight_mode={fm}) — failsafe olabilir")
                return False

        uzak, hiz = {}, {}
        for did in ucanlar():
            dd = t.get(did)
            if dd is None:
                continue
            hedef = hedefler[did]
            konum = (dd["pos_x"], dd["pos_y"], dd["alt_m"])
            uzak[did] = math.dist(konum, hedef)
            # ÖLÇÜLEN YER HIZI — telemetrinin GERÇEKTEN yenilendiği anlara
            # bağlı. Önceki hâli her tik'te dist/dt hesaplıyordu ve görev
            # döngüsü 0.5 -> 0.1 sn'ye inince YANILTICI oldu: mesh ~5-7 Hz
            # veri getiriyor, iki tik arasında konum aynı kalınca hız 0.0,
            # yeni örnek gelince aradaki bütün yol tek tik'e bölünüp 4 m/s
            # görünüyordu. 2 Ağustos uçuşunda örneklerin %40'ı 0.0 okudu ve
            # log "bas-çek" varmış gibi göründü — oysa ölçüm hatasıydı.
            #
            # Konum değişmediyse ESKİ değer korunur; değiştiğinde gerçekten
            # geçen süreye bölünür. Böylece sayı örnekleme hızından bağımsız.
            if konum[:2] != olcum_konum[did][:2]:
                gecen = max(1e-3, simdi - olcum_t[did])
                son_hiz[did] = math.dist(konum[:2], olcum_konum[did][:2]) / gecen
                olcum_konum[did] = konum
                olcum_t[did] = simdi
            hiz[did] = son_hiz[did]
            onceki_konum[did] = konum

            # HEDEF DOĞRUDAN GÖNDERİLİR — ara nokta YÜRÜTÜLMEZ.
            #
            # Yürütme 2 Ağustos'ta px4_bridge'e taşındı (bkz. oradaki
            # _yurutucu_ilerlet). Sebep ölçüldü: goto'lar burada 10 Hz
            # üretiliyordu ama drone'a 6.6 Hz ve DÜZENSİZ varıyordu
            # (103/203/304 ms), çünkü mesh'te POSE/GOTO broadcast gidiyor ve
            # broadcast'te 802.11 ACK/retry yok — kayıp ~%30. Her kayıp,
            # yürütülen setpoint'te bir sıçrama demekti: 304 ms'lik boşluktan
            # sonraki nokta 0.6 m ileride, MPC_XY_P (0.95) ile ~0.57 m/s ani
            # hız talebi. Operatörün "gaz bas-çek" dediği şey buydu.
            #
            # Artık hedefin BİR KEZ ulaşması yeterli: esp32_bridge onu 10 Hz
            # yerel tekrar yayınlıyor, px4_bridge 50 Hz'de kendi yürütüyor.
            # Kaybolan paket zaten aynı hedefi taşıyordu — zararsız.
            #
            # HIZ ARTIK BURADA DEĞİL: GOREV_HIZ_MPS / GOREV_DIKEY_HIZ_MPS
            # yerine px4_bridge'in guided_hiz_yatay_mps / _dikey_mps
            # parametreleri geçerli. İkisi AYNI değerde tutulmalı.

            # TAŞMA FRENİ DE TAŞINDI (px4_bridge, guided_tasma_m). Burada
            # 6.6 Hz'lik ve gecikmeli telemetriye dayanıyordu; orada uçağın
            # kendi konumuyla 50 Hz'de ve gecikmesiz çalışıyor.
            git(did, hedef, heading_deg, kuru, t)

        # KAÇIŞ KESİCİSİ — 1 Ağustos 22:18'de EKSİKTİ ve bedeli ağır oldu.
        #
        # O gece hedefe olan mesafe 6.5 m'den 78.7 m'ye çıktı, kod bunu 40
        # saniye boyunca ekrana YAZDI ve hiçbir şey yapmadı. Mod, kill,
        # failsafe ve eğim denetimleri vardı; "hedeften uzaklaşıyorum"
        # denetimi yoktu. Uçağı pilot kurtardı.
        #
        # ÖLÇÜT "arka arkaya arttı" DEĞİL, "en yakın geldiği yerden bu kadar
        # geri gitti": rüzgâr ve salınım mesafeyi bir tık büyütebilir ama
        # EN İYİ yaklaşmadan kalıcı olarak uzaklaşmak normal değildir.
        # KACIS_MARJ_M kadar geri gitmek + KACIS_ARDISIK ölçüm boyunca öyle
        # kalmak şart; ikisi birden olmadan kesmiyor.
        #
        # En kötü hâlde kaybedilen mesafe: marj + tavan hız x onay süresi
        # = 4 m + 4 m/s x 1.5 s = 10 m. O geceki 78 m ile kıyaslanmaz.
        for did, u in uzak.items():
            if u < en_yakin[did]:
                en_yakin[did] = u
                kacis_basladi[did] = None
            elif u > en_yakin[did] + _kacis_marj():
                if kacis_basladi[did] is None:
                    kacis_basladi[did] = simdi
            else:
                kacis_basladi[did] = None
            if (kacis_basladi[did] is not None
                    and simdi - kacis_basladi[did] >= KACIS_ONAY_S):
                print(f"\n      !!! drone {did} HEDEFTEN UZAKLAŞIYOR — "
                      f"en yakın {en_yakin[did]:.1f} m idi, {u:.1f} m'ye çıktı "
                      f"ve {KACIS_ONAY_S:.1f} sn öyle kaldı. "
                      f"KAÇIŞ: görev kesiliyor, iniliyor.")
                print(f"      (çerçeve kayması olabilir — ön kontroldeki "
                      f"origin kapısına ve px4b logundaki 'ORIGIN OTURMAMIS' "
                      f"satırına bak)")
                return False

        # VARIS TEK SARTA DONDU — ikinci sart artik GEREKSIZ.
        #
        # 1 Agustos'ta "yurutulen setpoint de hedefe otursun" sarti eklenmisti,
        # cunku setpoint burada yurutuluyordu ve 5 m'lik tirmanis 2.5 m'de
        # "vardi" sayilabiliyordu. Yurutme px4_bridge'e tasindi: artik ucak
        # hedefe TAM olarak yuruyor, yarim kalma ihtimali yapisal olarak yok.
        # Burada bakilacak tek sey ucagin gercekten varip varmadigi.
        _tol = TOLERANS_M if tolerans is None else tolerans
        if uzak and all(u <= _tol for u in uzak.values()):
            print("      vardı: " + "  ".join(
                f"d{k}={v:.1f}m" for k, v in sorted(uzak.items())))
            return True
        print("      ... " + "  ".join(
            f"d{k}={uzak[k]:.1f}m({hiz[k]:.1f}m/s)" for k in sorted(uzak)), end="\r")
    print(f"\n      ZAMAN AŞIMI ({asim_s:.0f}s)")
    return False


def indir(kuru: bool):
    """LAND. DISARM ASLA gönderilmez — havada motor kesmek düşmek demektir."""
    global _iniyor
    if _iniyor:
        return
    _iniyor = True
    print("\n>>> İNİŞ (land) — motor kesme YOK")
    for did in ucanlar():
        try:
            if not kuru:
                _istek(f"/api/guided/{did}/land")
            print(f"    drone {did}: land gönderildi")
        except Exception as e:
            print(f"    drone {did}: land GÖNDERİLEMEDİ: {e}")


def on_kontrol(kuru: bool) -> bool:
    print("\n=== ÖN KONTROL ===")
    t = durum_toleransli(kuru)
    if kuru and not t:
        print("  [KURU] YKİ kapalı — telemetri yok, ön kontrol atlandı")
        return True
    tamam = True
    rtk_yok = []
    for did in DRONELAR:
        d = t.get(did)
        if d is None:
            print(f"  drone {did}: TELEMETRİDE YOK")
            tamam = False
            continue
        engel = []
        if not d["connected"]:
            engel.append("BAĞLI DEĞİL")
        if d["armed"]:
            engel.append("ZATEN ARMED")
        if d["gps_fix_type"] < 3:
            engel.append(f"GPS fix={d['gps_fix_type']}")

        # KUMANDA KAPISI. Kumanda kapaliyken gorev BASLAMAMALI: tek gercek
        # iptal yolumuz o. Yazilim iptali (Ctrl-C / durdurma dosyasi) YKI'ye,
        # aga ve mesh'e bagli; kumanda hicbirine bagli degil.
        #
        # rc_link_ok BU ISI GORMUYOR — 1 Agustos'ta olculdu: kumandalar
        # KAPALIYKEN rc_link_ok=True okundu, /mavros/rc/in akmaya devam etti
        # (rssi sabit 41, kanallar donmus). Alici "son degerleri tut"
        # failsafe'inde oldugu icin PX4 kumandanin kapandigini GORMUYOR.
        # Bu yuzden kapiyi PX4'un kendi hukmune baglıyoruz: arm'a hazir mi,
        # kill anahtari acik mi. Kumanda kapaliyken alici failsafe degerlerine
        # dusuyor ve bunlar zaten arm'i engelliyor (ylp00'da KILL okundu).
        if d.get("kill_switch_active"):
            engel.append("KILL ANAHTARI AÇIK (kumandadan kapat)")
        if d.get("rc_signal_failsafe_active"):
            engel.append("RC FAILSAFE")
        if d.get("failsafe_active"):
            engel.append("FAILSAFE")
        if not d.get("ready_to_arm", True):
            engel.append("ARM'A HAZIR DEĞİL (kumanda açık mı?)")

        # ÇERÇEVE KAPISI — 1 Ağustos 22:18'de ylp01 bu yüzden kaçtı.
        #
        # YKİ'nin bildirdiği konum GPS'ten ORTAK origin'e göre hesaplanıyor;
        # PX4 ise setpoint'i KENDİ EKF origin'ine göre yorumluyor. İkisi
        # ayrıysa komut edilen her nokta o fark kadar yanlış yere düşer ve
        # uçak düzeltemez: gidince YKİ konumu büyür, setpoint yeniden
        # hesaplanır, yine aynı kadar ileriyi gösterir. Hata kapanmaz,
        # uçak tam yetkiyle sonsuza kadar gider. Ölçülen ayrılık 12.1 m,
        # uçak 85 m öteye ve 21 m irtifaya çıktı.
        #
        # Bayrak ARTIK GÜVENİLİR: px4_bridge onu göndermekle değil, GPS ile
        # PX4'ün yerel çerçevesini KARŞILAŞTIRARAK koyuyor (_origin_dogrula).
        # Eski hâlinde komut yollanır yollanmaz true yapılıyordu ve o gece
        # true okunuyordu — yani bu kapı o hâliyle kurtarmazdı.
        #
        # Alan yoksa da ENGEL: eski px4_bridge koşuyor demektir, doğrulama
        # yapılmıyordur. Bilinmeyeni "geçti" saymak tam da bu kazayı üretir.
        if not d.get("origin_synced", False):
            engel.append("ORIGIN OTURMAMIŞ (çerçeve kayması — px4b logunda "
                         "'ORIGIN OTURMAMIS' satırına bak)")
        fix = d["gps_fix_type"]
        print(f"  drone {did}: bagli={d['connected']} armed={d['armed']} mod={d['mode']} "
              f"GPS={_FIX_ADI.get(fix, fix)} sat={d['gps_satellites']} "
              f"pil={d['battery_percent']:.0f}% "
              f"NED=({d['pos_x']:+.1f},{d['pos_y']:+.1f})")
        if fix < 5:
            rtk_yok.append(did)
        if engel:
            print(f"           ENGEL: {', '.join(engel)}")
            tamam = False

    # RTK ENGEL DEGIL, UYARI. Gorev RTK olmadan da ucar: carpisma marji
    # (5.16 m) metre mertebesindeki GPS hatasini sogurecek sekilde secildi.
    # Ama RTK fix varsa hata cm'ye iner ve ayni plan cok daha rahat olur —
    # o yuzden ucmadan once gorulmesi gereken bir bilgi.
    if rtk_yok:
        print(f"\n  UYARI: RTK fix YOK (drone {', '.join(map(str, rtk_yok))}). "
              f"Konum hatasi metre mertebesinde olabilir.")
        print(f"  Plan yine de guvenli: en kritik an {MIN_AYRIM_M:.1f} m esiginin "
              "uzerinde tutuluyor. Ruzgar varsa RTK'yi beklemek daha iyi.")
    return tamam


# --- Görev ------------------------------------------------------------------
def gorev(kuru: bool) -> int:
    basla = time.time()

    def kalan():
        return GOREV_ASIM_S - (time.time() - basla)

    if not on_kontrol(kuru) and not kuru:
        print("\n  ÖN KONTROL GEÇMEDİ — görev başlatılmıyor.")
        return 1

    t = durum_toleransli(kuru)
    if t:
        pts = [(t[d]["pos_x"], t[d]["pos_y"]) for d in DRONELAR if d in t]
        merkez0 = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    elif kuru:
        merkez0 = (0.0, 0.0)
        print("\n[KURU] telemetri yok — merkez (0,0) varsayıldı")
    else:
        print("Telemetri yok.")
        return 1
    print(f"\nKalkış merkezi (ölçüldü): ({merkez0[0]:+.1f}, {merkez0[1]:+.1f}) NED")

    baslangic = {did: (t[did]["pos_x"], t[did]["pos_y"], KALKIS_IRTIFA_M)
                 for did in DRONELAR if did in t} or None
    if _SENARYO == "tam":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — tam senaryo konum ve yön "
                  "ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_tam(t)
    elif _SENARYO == "donus":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — dönüş senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_donus(t)
    elif _SENARYO == "takip":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — takip senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_takip(t)
    elif _SENARYO == "asili":
        did = DRONELAR[0]
        if did not in t:
            print(f"Telemetride yok: drone {did} — asılı senaryosu ölçülen "
                  "konuma dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_asili(t)
    elif _SENARYO == "tekli":
        did = DRONELAR[0]
        if did in t:
            plan = plan_kur_tekli(t)
        elif kuru:
            # YKI kapaliyken de plan YAPISI denetlenebilsin diye. Uyari
            # yuksek sesle: harita bu halde GERCEK DEGIL.
            print(f"\n[KURU] drone {did} telemetride yok — yön 0° (kuzey) "
                  "VARSAYILDI. Haritadaki nokta GERÇEK DEĞİL; yalnız plan "
                  "yapısını denetlemek için.")
            plan = plan_kur_tekli({did: {"pos_x": merkez0[0],
                                         "pos_y": merkez0[1], "yaw_deg": 0.0}})
        else:
            print(f"Telemetride yok: drone {did} — tekli senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
    elif _SENARYO == "lider":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — lider senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_lider(t)
    elif _SENARYO == "test":
        plan = plan_kur_test(merkez0, baslangic)
    elif _SENARYO == "formasyon":
        plan = plan_kur_formasyon(merkez0, baslangic)
    else:
        plan = plan_kur(merkez0, baslangic)
    plan_yaz(plan)
    ayak_izi_yaz(plan, merkez0)
    _org = _origin_bul(t)
    koordinat_yaz(plan, merkez0, _org)
    if _HARITA_DOSYA:
        harita_yaz(plan, merkez0, _org, _HARITA_DOSYA, t)
    if not plan_dogrula(plan, baslangic):
        return 1
    if kuru:
        print("\n[KURU] plan doğrulandı, komut gönderilmedi.")
        return 0

    # --- ARM + KALKIŞ -------------------------------------------------------
    # ARM TEYİDİ BEKLENİR: px4_bridge önce OFFBOARD'a geçip sonra arm ediyor
    # (PX4 yerde armlıyken OFFBOARD'a girmiyor). Teyit beklemeden takeoff
    # yollamak, komutun hâlâ disarm uçağa gitmesi ve sessizce düşmesi demek.
    kalkis_irt = (TAM_IRTIFA_M if _SENARYO == "tam"
                  else DONUS_IRTIFA_M if _SENARYO == "donus"
                  else TAKIP_IRTIFA_M if _SENARYO == "takip"
                  else ASILI_IRTIFA_M if _SENARYO == "asili"
                  else TEKLI_IRTIFA_M if _SENARYO == "tekli"
                  else FORMASYON_TEST_IRTIFA_M if _SENARYO in ("formasyon", "lider")
                  else KALKIS_IRTIFA_M)
    print(f"\n=== ARM + KALKIŞ {kalkis_irt:.0f} m ===")
    for did in DRONELAR:
        print(f"    drone {did}: arm")
        _istek(f"/api/guided/{did}/arm")
        t0 = time.time()
        while time.time() - t0 < ARM_ASIM_S:
            time.sleep(0.5)
            if durum().get(did, {}).get("armed"):
                print(f"      arm teyit ({time.time()-t0:.1f}s)")
                break
        else:
            print(f"      ARM EDİLEMEDİ — görev durduruluyor")
            indir(kuru)
            return 1
    # KALKIS TEYIDE BAGLI. Onceden komut BIR KEZ gonderilip umuluyordu ve
    # 1 Agustos'ta bir drone'un takeoff'u mesh hiz sinirinda dusunce o ucak
    # ARMLI halde YERDE kaldi, digeri havada 60 sn bosuna bekledi. Armli ve
    # OFFBOARD'da yerde beklemek motorlari hover itkisinde tutar — motor
    # yaktigimiz durumun aynisi. Artik her ucak icin tirmanis TEYIT ediliyor,
    # baslamadiysa komut TEKRARLANIYOR, olmuyorsa gorev hic baslamiyor.
    # 0.8 m ESIK GURULTUYE ACIKTI. 1 Agustos'ta ucak yerden hic kesilmedigi
    # halde "tirmanis basladi" dendi: devrilince EKF dikey kanali sapti ve
    # irtifa yerde dururken -1.5 ile +1.7 m arasinda gezindi. Esik yukseltildi
    # ve tek ornek yerine ARDISIK IKI olcum aranıyor.
    TIRMANIS_ESIGI_M = 1.5
    kalanlar = list(ucanlar())
    for deneme in range(1, 4):
        for did in kalanlar:
            _istek(f"/api/guided/{did}/takeoff?altitude={kalkis_irt}")
        print(f"    takeoff {kalkis_irt:.0f} m gönderildi "
              f"(deneme {deneme}, drone {kalanlar}), tırmanış bekleniyor...")
        t0 = time.time()
        teyit = {d: 0 for d in kalanlar}
        while time.time() - t0 < 5.0:
            time.sleep(0.5)
            t = durum()
            ihlal = guvenlik_ihlali(t)
            if ihlal:
                print(f"\n    !!! {ihlal} — kalkış kesiliyor")
                indir(kuru)
                return 1
            for d in list(kalanlar):
                if t.get(d, {}).get("alt_m", 0.0) >= TIRMANIS_ESIGI_M:
                    teyit[d] += 1
                else:
                    teyit[d] = 0
                if teyit[d] >= 2:          # ardisik iki olcum
                    kalanlar.remove(d)
            if not kalanlar:
                break
        if not kalanlar:
            print("    tırmanış başladı: hepsi")
            break
        print(f"    tırmanmayan: drone {kalanlar} — komut tekrarlanıyor")
    else:
        print(f"    KALKIŞ KOMUTU ULAŞMADI: drone {kalanlar} — görev iptal")
        indir(kuru)
        return 1

    # TIRMANMIYORSA ERKEN KES. Onceki hali KALKIS_ASIM_S (60 sn) dolana kadar
    # beklerdi. 1 Agustos'ta ylp00 yerden kesilemedi, yerde kaydi, devrildi ve
    # kod 62 saniye bekledi. Yerden kesilemeyen bir ucak icin beklemek
    # durumu SADECE kotulestirir: PX4 yatay konum tutmaya calisir, ucak
    # kayar, duzeltmek icin egilir, pervane yere vurur.
    ERKEN_KES_S = 8.0
    ERKEN_KES_IRTIFA_M = 1.5
    # PLATO TESPITI — 2 Agustos'ta EKSIKTI. O ucusta ylp02 7.8 m'de takildi
    # (sebebi kacinma dugumunun bayat setpoint'i idi) ve kosul "hepsi %90'a
    # ciksin" oldugu icin hicbir zaman saglanmadi: iki ucak 40 SANIYE havada
    # bosuna bekledi, pil yandi, operator elle indirdi. Artik irtifa
    # PLATO_S boyunca PLATO_TOLERANS_M'den fazla artmiyorsa ve hedefin
    # altindaysak temiz bir mesajla kesiyoruz.
    PLATO_S = 12.0
    PLATO_TOLERANS_M = 0.5
    plato_t = {d: time.time() for d in ucanlar()}
    plato_alt = {d: 0.0 for d in ucanlar()}
    # KALKTI MI — erken kesme kontrolu YALNIZ hic kalkamamis ucaga uygulanir.
    # Onceki hali 60 sn'lik pencerede HER AN gecerliydi ve o ucusta operator
    # elle indirirken 53. saniyede "1.5 m'ye cikamadi, YERDEN KESILEMIYOR"
    # diye YANLIS teshis bastirdi — oysa ucak 7.8 m'ye cikmisti.
    kalkti = {d: False for d in ucanlar()}
    print(f"    irtifa bekleniyor...")   # (ofset asagida olculuyor)
    t0 = time.time()
    while time.time() - t0 < KALKIS_ASIM_S:
        time.sleep(1.0)
        t = durum()
        ihlal = guvenlik_ihlali(t)
        if ihlal:
            print(f"\n    !!! {ihlal} — kalkış kesiliyor")
            indir(kuru)
            return 1
        gecen = time.time() - t0
        simdi_t = time.time()
        for d in ucanlar():
            a = t.get(d, {}).get("alt_m", 0.0)
            if a >= ERKEN_KES_IRTIFA_M:
                kalkti[d] = True
            if a > plato_alt[d] + PLATO_TOLERANS_M:
                plato_alt[d] = a
                plato_t[d] = simdi_t
        takilan_plato = [d for d in ucanlar()
                         if kalkti[d]
                         and simdi_t - plato_t[d] > PLATO_S
                         and t.get(d, {}).get("alt_m", 0.0) < kalkis_irt * 0.9]
        if takilan_plato:
            print(f"\n    !!! drone {takilan_plato} irtifada TAKILDI: "
                  + "  ".join(f"d{d}={t.get(d,{}).get('alt_m',0.0):.1f}m"
                              for d in takilan_plato)
                  + f" (hedef {kalkis_irt:.1f} m, {PLATO_S:.0f} sn'dir "
                    f"yükselmiyor) — iniliyor")
            print("      Not: uçak komutu izliyorsa sorun İTKİ değil KOMUTTUR "
                  "— px4b logundaki setpoint'e bak.")
            indir(kuru)
            return 1
        if gecen > ERKEN_KES_S:
            takilan = [d for d in ucanlar()
                       if not kalkti[d]
                       and t.get(d, {}).get("alt_m", 0.0) < ERKEN_KES_IRTIFA_M]
            if takilan:
                print(f"\n    !!! drone {takilan} {gecen:.0f} sn'de "
                      f"{ERKEN_KES_IRTIFA_M:.1f} m'ye çıkamadı — YERDEN "
                      f"KESİLEMİYOR, iniliyor (itki payı / pil?)")
                indir(kuru)
                return 1
        if all(t.get(d, {}).get("alt_m", 0.0) >= kalkis_irt * 0.9 for d in ucanlar()):
            print("    irtifa tamam: " + "  ".join(f"d{d}={t[d]['alt_m']:.1f}m"
                                                   for d in ucanlar()))
            # IRTIFA OFSETI — kalkis ile goto AYNI cerceveye getirilir.
            #
            # Iki ayri referans vardi ve arasindaki fark kalkis biter bitmez
            # bir SICRAMA olarak goruluyordu:
            #   kalkis (px4_bridge:810)  _cached_pos_z - altitude  -> ZEMINE gore
            #   goto   (guided.py:128)   z = -irtifa               -> ORIGIN'e gore
            # Zemin origin'in z=0'inda degilse ikisi ayrisir. 1 Agustos ucusu:
            # zemin z=+1.6, kalkis ucagi zeminden 5 m'ye cikardi (z=-3.4), ilk
            # goto origin'den 5 m istedi (z=-5.0) -> ucak 1.6 m FIRLADI.
            # Operatorun birden fazla gorevde bildirdigi "1-2 metre irtifa
            # sicramasi" buydu.
            #
            # Origin'i duzeltmek yerine ofset OLCULUYOR: kalkis bitince ucagin
            # okudugu irtifa, zeminden kalkis_irt kadar yukarida olmasi
            # gereken bir ucagin ORIGIN'e gore irtifasidir. Aradaki fark
            # ofsettir ve plandaki tum irtifalara eklenir.
            #
            # OTURMA BEKLENIR — 2 Agustos'ta bu EKSIKTI ve olcumu bozuyordu.
            #
            # Kosul irtifanin %90'inda tetikleniyor, yani ucak HALA ~1 m/s ile
            # TIRMANIRKEN. O anlik okuma "ofset" sayilip plana yaziliyordu;
            # ucak momentumla hedefin uzerine cikiyor, sonra yurutucu onu
            # asagi cekiyordu. Operator "kalkista bir irtifaya cikti sonra
            # kendini alcaltti" diye bildirdi; ucus kaydinda yurutucunun
            # dik=-0.56 komut ettigi goruluyor — alcalmayi BIZ istemisiz.
            #
            # Ayrica dort ucusta ofsetin hep -0.3/-0.5 cikmasinin sebebi de
            # buydu: gercek bir cerceve farki degil, gecici rejimde olcum.
            # Dikey cerceve zaten dogrulanmis durumda (px4_bridge
            # _origin_dogrula: "dikey 0.00 m"), yani ofsetin ~0 cikmasi
            # gerekiyor. Oturduktan sonra hala buyuk cikarsa GERCEK bir fark
            # var demektir ve o zaman bakmak anlamli olur.
            print("    tırmanış oturması bekleniyor...")
            for _ in range(int(OTURMA_ASIM_S / 0.5)):
                time.sleep(0.5)
                t = durum()
                ihlal = guvenlik_ihlali(t)
                if ihlal:
                    print(f"\n    !!! {ihlal} — kesiliyor")
                    indir(kuru)
                    return 1
                dvz = [abs(t.get(d, {}).get("vel_z", 0.0)) for d in ucanlar()]
                if dvz and max(dvz) <= OTURMA_DIKEY_HIZ_MPS:
                    break
            print("    oturdu: " + "  ".join(
                f"d{d}={t.get(d,{}).get('alt_m',0.0):.2f}m"
                f"(vz={t.get(d,{}).get('vel_z',0.0):+.2f})" for d in ucanlar()))
            olculen = [t[d]["alt_m"] for d in ucanlar()]
            irtifa_ofset = sum(olculen) / len(olculen) - kalkis_irt
            if abs(irtifa_ofset) > 0.15:
                print(f"    irtifa ofseti {irtifa_ofset:+.2f} m "
                      f"(zemin origin'in z=0'inda değil) — plana ekleniyor")
                # 5. eleman (gecis yaricapi) KORUNUR — dusurulurse ara
                # noktalar tekrar "tam varis" bekler ve yay taksitlenir.
                plan = [(a[0], a[1],
                         {k: (v[0], v[1], v[2] + irtifa_ofset)
                          for k, v in a[2].items()}, *a[3:])
                        for a in plan]
            break
        print("    ... " + "  ".join(f"d{d}={t.get(d,{}).get('alt_m',0.0):.1f}m"
                                     for d in ucanlar()), end="\r")
    else:
        print("\n    KALKIŞ ZAMAN AŞIMI — iniliyor")
        indir(kuru)
        return 1

    # --- Plan adımları ------------------------------------------------------
    # ILK YON DE KADEMELI VERILIR — HER DRONE KENDI OLCULEN YONUNDEN.
    #
    # Ilk yazimda tek bir onceki_heading tutuluyordu ve "birden fazla ucak
    # varsa None" deniyordu. Sonucu: IKI DRONELU ucusta ilk adimda HIC
    # dilimleme yapilmadi, ucaklar park yonunden hedefe TEK HAMLEDE dondu.
    # 1 Agustos'ta olculdu: d1 ~183 dereceden 238.4 dereceye, yani 55 derece,
    # MC_YAWRATE_MAX (200 °/s) hizinda. Operatorun gordugu "asiri hizli yon
    # duzeltmesi" buydu.
    #
    # Ucaklar farkli yonlerde park edilir, dolayisiyla tek skaler yetmez:
    # yon her ucak icin AYRI dilimlenir ve adimlar birlikte yurutulur.
    t_yaw = durum_toleransli(kuru) or {}
    onceki_heading = {d: t_yaw[d]["yaw_deg"] for d in ucanlar() if d in t_yaw}
    for i, _adim in enumerate(plan):
        # 5. eleman OPSIYONEL: gecis yaricapi. Verilirse bu adim bir HEDEF
        # degil GECIS NOKTASIDIR — tam varis beklenmez ve burun donusu ayri
        # bir faz olarak yapilmaz. Bkz. plan_kur_donus'taki rotasyon.
        etiket, heading, hedefler, beklet = _adim[:4]
        gecis_r = _adim[4] if len(_adim) > 4 else None
        print(f"\n=== [{i+1}/{len(plan)}] {etiket}   yön {heading:.0f}°   "
              f"(kalan {kalan():.0f}s) ===")
        t_durum = durum()

        # YON KADEMELI VERILIR. Tek sicrama yerine ara yonler; bkz.
        # YAW_ADIM_DEG yorumu. Konum degismez, YALNIZ BURUN DONER — bu yuzden
        # ara adimlarda ucagin OLCULEN yeri gonderilir. Onceden buraya
        # hedefler[did] (YENI nokta) veriliyordu: yorum "konum degismez"
        # derken kod ucagi doner donmez yola cikariyordu, ustelik yurutulmemis
        # tek sicrama olarak. Ikisi bir arada donuse ek bir savrulma katiyordu.
        # GECIS NOKTASINDA BURUN AYRI DONDURULMEZ. Ayri faz, konumu sabit
        # tutup yaw'i dilimliyor ve dilim basina ~1.6 sn duruyor. Bir yay
        # boyunca bu, her ara noktada "dur, burnunu cevir, git" demek —
        # 2 Agustos'ta operator "taksit taksit, cok cirkin" diye bildirdi.
        # Gecis noktalarinda yon, konumla BIRLIKTE degisir; PX4 zaten
        # MPC_YAWRAUTO_MAX (25 derece/sn) ile sinirliyor, sert donus olmaz.
        if onceki_heading and not kuru and gecis_r is None:
            dilimler = {did: yon_dilimle(onceki_heading[did], heading)
                        for did in ucanlar() if did in onceki_heading}
            en_uzun = max((len(v) for v in dilimler.values()), default=0)
            if en_uzun:
                print("      dönüş " + "  ".join(
                    f"d{k}:{onceki_heading[k]:.0f}°->{heading:.0f}°({len(v)})"
                    for k, v in sorted(dilimler.items()) if v))
                for i_ara in range(en_uzun):
                    for did in ucanlar():
                        d = t_durum.get(did)
                        if d is None:
                            continue
                        ara = dilimler.get(did) or []
                        # Dilimi biten ucak son yonunde bekler; digerleri
                        # donmeye devam eder.
                        y = ara[i_ara] if i_ara < len(ara) else heading
                        git(did, (d["pos_x"], d["pos_y"], d["alt_m"]),
                            y, kuru, t_durum)
                    time.sleep(YAW_ADIM_BEKLE_S)
        onceki_heading = {did: heading for did in ucanlar()}
        for did in DRONELAR:
            h = hedefler[did]
            etiket_s = "  (LİDER — yerinde asılı)" if did == LIDER else ""
            print(f"      drone {did}: ({h[0]:+7.1f},{h[1]:+7.1f}) "
                  f"irtifa {h[2]:5.1f} m yön {heading:5.1f}°{etiket_s}")
        if not git_ve_bekle(hedefler, heading,
                            min(ADIM_ASIM_S, max(kalan(), 5)), kuru, t_durum,
                            tolerans=gecis_r):
            indir(kuru)
            return 1
        if beklet:
            # beklet ya True (varsayilan YERLESME_S) ya da SANIYE degeri.
            # Sayi kabul etmesi tekli senaryosu icin gerekti: orada bekleme
            # suresi gorevin TANIMININ parcasi (5 sn), "videoda gorunsun"
            # diye secilmis bir sayi degil.
            bekle_s = YERLESME_S if beklet is True else float(beklet)
            print(f"    bekleme {bekle_s:.0f}s")
            # BEKLEME SIRASINDA DA DENETLE. Onceki hali duz time.sleep idi:
            # 5 sn'lik yerlesmede zararsizdi ama --senaryo asili 60 sn tutuyor
            # ve o sure boyunca kill/failsafe/egim/pilot denetimi KOR kalirdi.
            # Bekleme sirasinda gorev komut gondermiyor; setpoint'i drone
            # kendi tazeliyor (esp32_bridge 10 Hz yerel tekrar), yani ucak
            # yerinde durmaya devam eder.
            _bekle_basla = time.time()
            while time.time() - _bekle_basla < bekle_s:
                time.sleep(min(0.5, bekle_s))
                _t = durum()
                _ihlal = guvenlik_ihlali(_t)
                if _ihlal:
                    print(f"\n    !!! {_ihlal} — görev durduruluyor")
                    indir(kuru)
                    return 1
                _pilot = [d for d in ucanlar()
                          if _t.get(d, {}).get("flight_mode", 0) in _PILOT_MODLARI]
                if _pilot:
                    print(f"\n    !!! drone {_pilot} PİLOT KONTROLÜNDE — "
                          f"görev durduruluyor")
                    indir(kuru)
                    return 1
        if kalan() < 40:
            print(f"\n    GÖREV SÜRE TAVANI ({kalan():.0f}s) — iniliyor")
            break

    indir(kuru)
    print(f"\n=== GÖREV TAMAM — {time.time()-basla:.0f} s ===")
    return 0




def main() -> int:
    global DRONELAR
    ap = argparse.ArgumentParser(description="Kanıt uçuşu görev koşucusu")
    ap.add_argument("--kuru", action="store_true", help="komut gönderme; planı kur ve doğrula")
    ap.add_argument("--sure", type=float, default=None,
                    help="--senaryo asili icin asili kalma suresi (sn)")
    ap.add_argument("--irtifa", type=float, default=None,
                    help="--senaryo asili icin kalkis/asili irtifasi (m)")
    ap.add_argument("--kacinma", action="store_true",
                    help="carpisma kacinmasi ACIK (drone'da /ws/kacinma var). "
                         "Kacis kesicisinin marjini genisletir, yoksa kesici "
                         "kacinma manevrasini kacis sanip gorevi iptal eder.")
    ap.add_argument("--senaryo",
                    choices=("kanit", "test", "formasyon", "lider", "tekli",
                             "asili", "takip", "donus", "tam"),
                    default="kanit",
                    help="kanit = tam koreografi; test = kuzeybati/bekle/"
                         "irtifa/don; formasyon = rastgele yerlesimden cizgi "
                         "formasyonu kur ve in; lider = lider YERINDE ASILI durur, "
                         "takipci onun sagina cizgi formasyonu kurup iner; "
                         "tekli = TEK ucak, kalkis yonunde 7 m, bekle, 5 m "
                         "tirman, bekle, in")
    ap.add_argument("--lider", type=int, default=None,
                    help="--senaryo lider icin YERINDE ASILI duracak drone (or. 2)")
    ap.add_argument("--harita", nargs="?", const="/tmp/yelpence_rota.html",
                    default=None, metavar="DOSYA",
                    help="rotayi uydu haritasina yaz (varsayilan /tmp/yelpence_rota.html)")
    ap.add_argument("--harita-ofset", default=None, metavar="KUZEY,DOGU",
                    help="uydu goruntusunun georeferans kaymasi, metre "
                         "(or. '4,-2'). YALNIZ CIZIME uygulanir; ucus "
                         "geometrisi NED'de kalir ve etkilenmez.")
    ap.add_argument("--yon", type=float, default=None,
                    help="rota yonu (pusula derecesi). 0=kuzey, 90=dogu. "
                         "Acik alan hangi yondeyse onu ver.")
    ap.add_argument("--dronelar", default="1,2",
                    help="virgülle: 1,2 (prova) veya 1,2,3")
    a = ap.parse_args()
    DRONELAR = [int(x) for x in a.dronelar.split(",") if x.strip()]
    global ROTA_YONU_DEG, _HARITA_DOSYA, _SENARYO, LIDER, HARITA_OFSET_KD
    global _KACINMA_ACIK, ASILI_SURE_S, ASILI_IRTIFA_M
    _KACINMA_ACIK = a.kacinma
    if a.sure is not None:
        ASILI_SURE_S = a.sure
    if a.irtifa is not None:
        ASILI_IRTIFA_M = a.irtifa
    if a.senaryo == "asili" and len(DRONELAR) != 1:
        ap.error("--senaryo asili TAM OLARAK bir drone ister (or. --dronelar 3)")
    if a.harita_ofset:
        try:
            k, _, d = a.harita_ofset.partition(",")
            HARITA_OFSET_KD = (float(k), float(d))
        except ValueError:
            ap.error("--harita-ofset 'KUZEY,DOGU' metre olmali (or. '4,-2')")
    if a.senaryo in ("takip", "donus", "tam"):
        if a.lider is None:
            ap.error(f"--senaryo {a.senaryo} icin --lider N gerekli")
        if a.lider not in DRONELAR:
            ap.error(f"--lider {a.lider} --dronelar listesinde yok")
        if len(DRONELAR) < 2:
            ap.error(f"--senaryo {a.senaryo} en az iki drone ister")
        LIDER = a.lider
    if a.senaryo == "lider":
        if a.lider is None:
            ap.error("--senaryo lider icin --lider N gerekli")
        if a.lider not in DRONELAR:
            ap.error(f"--lider {a.lider} --dronelar listesinde yok")
        if len(DRONELAR) < 2:
            ap.error("--senaryo lider en az iki drone ister (lider + takipci)")
        LIDER = a.lider
    if a.senaryo == "tekli" and len(DRONELAR) != 1:
        ap.error("--senaryo tekli TAM OLARAK bir drone ister "
                 f"(--dronelar 2 gibi; su an {DRONELAR})")
    if a.yon is not None:
        ROTA_YONU_DEG = a.yon
    _HARITA_DOSYA = a.harita
    _SENARYO = a.senaryo

    def _kesildi(_s, _f):
        print("\n\n!!! KESİLDİ (Ctrl-C) !!!")
        indir(a.kuru)
        sys.exit(130)

    signal.signal(signal.SIGINT, _kesildi)
    signal.signal(signal.SIGTERM, _kesildi)

    print("=" * 72)
    print(f"  KANIT KOREOGRAFİSİ — çizgi, {TAM_MESAFE_M:.0f} m, KD, roll "
          f"{TAM_ROLL_DEG:.0f}°, GD ekseni, eve"
          if a.senaryo == "tam" else
          f"  ÇİZGİ + 180° ROTASYON — {DONUS_MESAFE_M:.0f} m ileri, dön, eve"
          if a.senaryo == "donus" else
          f"  İKİ DRONLU PROVA — ok başı, {TAKIP_MESAFE_M:.0f} m ileri, "
          f"bekle, eve dön"
          if a.senaryo == "takip" else
          f"  KAÇINMA TESTİ — {ASILI_IRTIFA_M:.0f} m'de {ASILI_SURE_S:.0f}s "
          f"ASILI DUR (yatayda komut YOK)"
          if a.senaryo == "asili" else
          "  TEK UÇAK TESTİ — kalkış yönünde 7 m, bekle, 5 m tırman, bekle, in"
          if a.senaryo == "tekli" else
          "  LİDER YANINA GEÇİŞ — lider yerinde asılı, takipçi sağına gelir"
          if a.senaryo == "lider" else
          "  BASİT İKİ DRONE TESTİ — kuzeybatı, bekle, irtifa, dönüş"
          if a.senaryo == "test"
          else "  KANIT UÇUŞU — ok başı, roll, formasyon değişimi, irtifa değişimi")
    if a.senaryo == "tam":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ÇİZGİ")
        print(f"  irtifa {TAM_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"roll {TAM_ROLL_DEG:.0f}° (lider sabit, takipçi "
              f"+{ARALIK_M*math.tan(math.radians(TAM_ROLL_DEG)):.2f} m)")
    elif a.senaryo == "donus":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ÇİZGİ")
        print(f"  irtifa {DONUS_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"rotasyon dilimi {DONUS_ROTASYON_ADIM_DEG:.0f}°")
    elif a.senaryo == "takip":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ok başı")
        print(f"  irtifa {TAKIP_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"bekleme {TAKIP_BEKLEME_S:.0f}s")
    elif a.senaryo == "asili":
        print(f"  drone: {DRONELAR[0]}   irtifa {ASILI_IRTIFA_M:.0f} m   "
              f"süre {ASILI_SURE_S:.0f}s")
        print(f"  kaçınma {'AÇIK' if _KACINMA_ACIK else 'KAPALI'}   "
              f"kaçış marjı {_kacis_marj():.0f} m")
    elif a.senaryo == "tekli":
        print(f"  drone: {DRONELAR[0]}   kalkış {TEKLI_IRTIFA_M:.0f} m -> "
              f"{TEKLI_IRTIFA_M + TEKLI_IRTIFA_ARTIS_M:.0f} m   "
              f"ileri {TEKLI_ILERLEME_M:.0f} m   bekleme {TEKLI_BEKLEME_S:.0f}s")
        print(f"  hız {GOREV_HIZ_MPS:.1f} m/s yatay, {GOREV_DIKEY_HIZ_MPS:.1f} m/s dikey"
              f"   (px4_bridge yürütücüsü)")
        print(f"  yatay kilit 2.5 m'ye kadar   yörünge drone'da üretiliyor")
    else:
        print(f"  dronelar: {DRONELAR}   kalkış {KALKIS_IRTIFA_M:.0f} m -> {YENI_IRTIFA_M:.0f} m")
        print(f"  roll {ROLL_ACISI_DEG:.0f}°   aralık {ARALIK_M:.0f} m   kenar {KENAR_M:.0f} m")
    print(f"  mod: {'KURU (komut yok)' if a.kuru else 'CANLI'}")
    print("=" * 72)
    try:
        return gorev(a.kuru)
    except Exception as e:
        print(f"\nHATA: {e}")
        indir(a.kuru)
        return 1


if __name__ == "__main__":
    sys.exit(main())
