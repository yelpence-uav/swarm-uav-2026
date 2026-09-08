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

# HIZ / IVME / ARALIK / EGIM TEK KAYNAKTAN GELIR.
#
# Bu degerler eskiden burada elle yaziliydi ve MAKS_EGIM_DEG'in yorumunda
# "MPC_TILTMAX_AIR=30" diye bir VARSAYIM duruyordu. 14 Agustos'ta olculdu:
# ylp00'da 45'ti. Yani dedektor esigi kontrol tavaninin ALTINDA kalmisti ve
# normal ucus "devrilme" sayilip gorev havada kendini iptal edebilirdi.
#
# Artik acilar hizdan ve ivmeden TURETILIYOR (ucus_ayarlari.egim_icin).
# Hizi degistirmek icin ucus_ayarlari.py'yi duzenle, sonra:
#     python3 src/gcs/ucus_ayarlari.py          # tutarlilik denetimi
#     python3 src/gcs/ucus_ayarlari.py --px4    # ucaklara yazilacak komutlar
import ucus_ayarlari as AYAR

# --senaryo formasyon_gecis (GECICI): sekans geometrisi UCAKTAKI dugumle
# (formasyon_sekans_node) AYNI fonksiyonlardan gelir — harita neyi
# gosteriyorsa ucak onu ucar. swarm_core saf Python, ROS'suz yuklenir.
# Kopya formul yazmak "ayni sabit iki yerde" kazasinin geometri hali olurdu.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "swarm_core"))
# --senaryo gorev1 ayni gerekceyle swarm_missions'i da ariyor: QR arama
# merdivenini orkestratorun KENDISINDEN okuyor (bkz. plan_kur_gorev1).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "swarm_missions"))
from swarm_core.formation_control import (  # noqa: E402
    formasyon_sekans_cekirdek as SEKANS,
    formation_geometry as GEO,
    manual_kinematics as KIN,
)

YKI = "http://localhost:8000"
ZAMAN_ASIMI_S = 5.0

# ylp00 -> 1, ylp01 -> 2, ylp02 -> 3 (bkz. docs/cihazlar.md)
# 31 Temmuz: ylp02 DEVRE DISI — pusulasi 143 uT / std 63 okuyor (saglami
# 48 uT / std 1), kalibrasyon "unable to fit mag 0" ile basarisiz.
# Olcumle elenenler: kamera guc kablosu, ESP32 mesh yayini, hareket,
# yapilandirma farki. (Olcum araci pusula_olc.py 29 Agu 2026'da silindi —
# gerekirse git gecmisinden gelir.)
DRONELAR = [1, 2]

# --- Geometri ---------------------------------------------------------------
# 2 AGUSTOS — 15.0 DENENDI, 10.0'DA KALINDI. Karar operatorun, gerekce alanda:
# 1. nokta binanin yanindaki beton onlukte ve takipciyi liderin 15 m kuzeyine
# park edecek yer belirsiz. Ayrica dar kutu (48x51 m yerine 54x51 m degil)
# cevredeki binalar acisindan daha iyi.
#
# OLCULDU (saha senaryosu, 5 nokta): kritik ayrim 10 m'de 7.07 m, 15 m'de
# 10.61 m. Sayilar tam dogrusal olcekleniyor cunku kritik an OK BASI gecisinin
# geometrisinden geliyor: 7.07 = 10*cos45, 10.61 = 15*cos45.
#
# BUNUN BEDELI: 4.0 m esigine pay 6.61 m yerine 3.07 m. Ve bu, beklemelerin
# kisildigi turda oluyor — yani tasmanin sondugu yastik da kalkti. Ikisi ayni
# yone biner. TELAFISI: SAHA_BEKLEME_S 0 degil 1.5 sn (bkz. asagi). ~5 sn
# geri verir, karsiliginda her duz bacaktan sonra salinim soner.
#
# HIZ ARTIRILMADI, BILEREK. Operatorun "%50 artiralim" istegi hiz olarak da
# okunabilirdi; secilseydi pay iki koldan incelirdi (frenleme mesafesi hizin
# KARESI, bkz. ~443). Hiz 2.0'da. Satir ~443'teki not zaten "ya hizi 2'ye
# dondur ya ARALIK_M'i 12'ye cikar" diyor — biz hizi 2'de tuttuk.
#
# BU SAYIYI BUYUTURSEN: rotasyon yaylari orantili uzar (takipci lider
# etrafinda ARALIK_M yaricapinda doner) ve rollda takipci ARALIK_M*tan(30)
# kadar yukselir. 10 -> 15 gecisi saha senaryosuna ~21 sn ekliyordu.
ARALIK_M = AYAR.ARALIK_M          # bkz. ucus_ayarlari.py (14 Agu: 10.0 -> 12.0)
KANAT_ACISI_DEG = AYAR.KANAT_ACISI_DEG   # orchestrator wing_alpha ile ayni
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
TOLERANS_M = AYAR.TOLERANS_M      # "vardi" yaricapi
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
# 🔴 23 AGUSTOS 2026 — BU KURAL TERSINE DONDU. ESKI HALI:
#     "IRTIFA AYRIMI GUVENLIK ICIN: kacinma yalniz YATAY calisiyor, yani iki
#      ucagi farkli irtifada tutmak kacinmayi engellemez ama fiziksel
#      carpismayi imkansiz kilar."
#
# Kacinma artik DIKEY de calisiyor (KARAR-06). Yeni kuralda ucak once
# "hepsinden katman kadar ayrik miyim?" diye bakiyor:
#
#     |rel_z| >= katman (3.0 m)  ->  TATMIN  ->  DIKEY KACIS HIC OLMAZ
#
# Yani ESKI GUVENLIK ALISKANLIGI (farkli irtifada ucur) yeni kodu SESSIZCE
# KAPATIYOR: ucus tertemiz gecer, hicbir sey olmaz ve "kacinma calismadi"
# diye yorumlanir.
#
# 🔴 DIKEY TESTTE YAKLASMA BENZER IRTIFADA OLMALI (fark < 3 m).
# Guvenlik artik irtifa ayrimindan degil, kacisin KENDISINDEN ve
# operatorun kumandasindan geliyor. Kacan ucak yukari cikacak — ustunden
# gecme, yandan yaklas.
ASILI_IRTIFA_M = 8.0
ASILI_SURE_S = 60.0

# --- --senaryo irtifa (MESH LINKI ~ GORELI IRTIFA TESTI) --------------------
# 22 Agustos 2026. Soru: mesh linki iki ucagin IRTIFA FARKINA bagli olarak
# bozuluyor mu? 21 Agustos'ta ylp00 komsusunu 46,4 sn HIC gormedi; o sirada
# irtifalar 10 m ve 8 m idi ve ariza TEK YONLUYDU (TUZAKLAR §2.15).
#
# UC BACAK, HEPSI AYNI SUREDE — esit pencere sart, yoksa "maksimum bosluk"
# ornek sayisiyla siser ve fazlar kiyaslanamaz (22 Agustos'ta bu hataya
# dusuldu ve olcum yeniden yapildi):
#   1) ikisi UST irtifada        -> TEMEL
#   2) biri ALT irtifaya iner    -> TEK DEGISKEN: goreli irtifa
#   3) ikisi yine UST irtifada   -> SURUKLENME KONTROLU
#
# 3. BACAK EN ONEMLISI. Onsuz, zamanla ilerleyen bir bozulma (dis girisim,
# pil, isinma) "irtifa etkisi" gibi gorunur. 1. ve 3. bacak birbirini
# tutmuyorsa 2. bacaktaki fark IRTIFADAN DEGILDIR ve olcum gecersizdir.
#
# YATAYDA HICBIR KOMUT YOK: her ucagin hedefi kendi OLCULEN x,y'si. Yani
# yatayda kimildarlarsa sebep biz degiliz (kacinma ya da ruzgar).
# ALCALAN UCAK = DRONELAR[0], yani `--dronelar 1,3` ile ylp00 iner.
# Degistirmek icin sirayi ters yaz: `--dronelar 3,1`.
IRTIFA_TEST_UST_M = 10.0
IRTIFA_TEST_ALCAK_M = 5.0
IRTIFA_TEST_SURE_S = 60.0

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

# --- --senaryo g2 (GOZLEM UCUSU — KISA) -------------------------------------
# 18 Agustos 2026'da operator istegiyle yazildi. AMAC ucmak degil, SURU
# DUGUMLERINI HAVADA GOZLEMLEMEK: consensus lideri kararli tutuyor mu,
# swarm_fsm dogru durum uretiyor mu, formation_node ne hesapliyor, 11 dugum
# kaynak olarak ne yiyor. Cikti /gozlem/... a gidiyor, UCAGA ULASMIYOR.
#
# NEDEN 'saha' DEGIL: o kanit videosunun koreografisi — 103 m yol, roll,
# rotasyonlar, irtifa degisimi, ~187 sn. Gozlem sorularinin hicbiri bunlari
# istemiyor ve pil bosuna yaniyor. Bu senaryo ayni sorulari ~90 saniyede
# cevapliyor.
#
# KOREOGRAFI: kalkis -> 15 m ileri -> kendi kalkis noktasina don.
#   * FORMASYON YOK (operator karari). Her ucak kendi konumundan gidip kendi
#     yerine donuyor; yerdeki dizilim aynen korunuyor.
#   * Burun HIC donmuyor (yon = liderin kalkis yonu), yaw dilimleme devre disi.
#   * NEDEN FORMASYONSUZ YETIYOR: formation_node'u besleyen sey YKI'nin
#     plani DEGIL, ucakta kosan form_yayinla.sh'in bastigi FormationCommand.
#     Ikisi ayri kanal; plandan formasyonu cikarmak gozlem sorularindan
#     hicbir sey eksiltmiyor.
#   * ⚠️ Ayrim artik YERDEKI DIZILIME esit. Formasyonlu senaryolarda kod
#     araligi 12 m'ye aciyordu, burada acmiyor — ucaklari ayri diz.
G2_IRTIFA_M = 20.0
G2_MESAFE_M = 15.0
G2_BEKLEME_S = 3.0

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
# KD BACAGININ BOYU — operator SABIT 30 m istedi.
#
# Once GD ekseni izdusumunden TURETILIYORDU (bu konumda 25.5 m cikiyordu) ve
# o degerde evin yonu TAM 135 (guneydogu) oluyordu. Sabit 30 m'de eksen
# hizasi KAYBOLUYOR: ucaklar ekseni ~4.5 m gecıyor ve evin yonu 135 yerine
# ~143 dereceye kayiyor.
#
# Bu bir kusur DEGIL, sadece "tam GD" ozelligi gidiyor. Eve donus rotasyonu
# zaten hesaplanan gercek yonu kullaniyor (gd degiskeni), yani otomatik
# uyum sagliyor — donus bacagi yine duz bir cizgi.
TAM_KD_MESAFE_M = 35.0
TAM_BEKLEME_S = 3.0

# --- --senaryo final (KANIT VIDEOSUNUN GERCEK KOREOGRAFISI) -----------------
# Operatorun 2 Agustos'ta tarif ettigi dizi:
#   cizgi -> 50 m BATI -> 23 dereceye rotasyon -> 20 m'ye tirmanis ->
#   23 yonunde 40 m -> UCGEN (ok basi) formasyonuna gecis -> 30 m DOGU ->
#   kalkis yonune rotasyon -> CIZGI formasyonuna donus -> ROLL ->
#   eve donus -> 152 dereceye rotasyon -> inis.
#
# YAN KAYMA (CRAB) BILINCLI: operator DOGU bacagindan ve EVE DONUS bacagindan
# ONCE rotasyon istemedi; rotasyonlari ayri adimlar olarak, baska yerlere
# koydu. Yani formasyon o iki bacakta burnunu cevirmeden YANA kayar:
#   * dogu bacagi : formasyon 23 dereceye bakiyor, 90 dereceye gidiyor (67 sapma)
#   * eve donus   : formasyon kalkis yonune bakiyor, ~173 dereceye gidiyor
# Bu bir hata DEGIL, tarifin bire bir uygulanmasi. Videoda "suru yonunden
# bagimsiz otelenebiliyor" diye gorunur. Istenmiyorsa o iki bacagin onune
# birer _rotasyon cagrisi eklemek yeterli.
#
# ROLL EVE DONUS BOYUNCA KORUNUR: operator roll'u iptal etmedi, "roll yapsinlar
# sonrasinda eve gelsinler" dedi. Lider FINAL_IRTIFA2_M'de sabit, takipci
# ARALIK_M*tan(roll) kadar yukarida ve inise kadar oyle kalir.
FINAL_IRTIFA_M = 10.0          # kalkis irtifasi
FINAL_IRTIFA2_M = 20.0         # rotasyondan sonra cikilan irtifa
FINAL_BATI_DEG = 270.0
FINAL_BATI_M = 50.0
FINAL_YON2_DEG = 23.0
FINAL_MESAFE2_M = 40.0
FINAL_DOGU_DEG = 90.0
FINAL_DOGU_M = 30.0
FINAL_FORMASYON2 = "okbasi"    # ucgen: 2 ucakta ok basi = 45 derecelik kanat
FINAL_ROLL_DEG = 30.0
FINAL_INIS_YON_DEG = 152.0
# BEKLEMELER — operator kisaltmak isterse TEK YER burasi.
# Duz seyir bacaklarindan sonra:
FINAL_BEKLEME_S = 3.0
# Manevralardan sonra (rotasyon sonu, irtifa, formasyon degisimi, roll).
# Yerlesme suresi: ucak hedefe "vardi" dedikten sonra salinimin sonmesi icin.
FINAL_MANEVRA_BEKLEME_S = 6.0

# --- --senaryo saha (OKUL SAHASI KANIT VIDEOSU) -----------------------------
# Noktalar operatorun nokta_sec.html ile haritadan sectigi 5 nokta, origin
# 38.6734220 / 39.1850585 (2 Agustos saha olcumu). NED metre, (kuzey, dogu).
#
#   1  (-24.3,  -0.6)  KALKIS   — lider bunun UZERINDE olacak
#   2  (-76.0, -18.3)  roll
#   3  (-43.6, -36.5)  cizgi -> ok basi
#   4  (-14.2, -54.0)  ok basi -> cizgi, irtifa 20 -> 30
#   5  (-33.1, -18.3)  INIS
#
# 1. NOKTA OLCULEREK GELIR: operator "lider nerdeyse ilk nokta orasi" dedi.
# Plan liderin GERCEK konumunu 1. nokta olarak alir, listedeki (-24.3,-0.6)
# yalniz sapmayi ekrana basmak icin tutulur. Digerleri SABIT.
#
# PLAN YAW'DAN BAGIMSIZ: diziliş dogrudan ilk bacagin yonunde kuruluyor,
# sonraki her yon sabit pusula degeri. Yani ucaklarin kalkis yonu ne olursa
# olsun plan AYNI cikar — sahada yalnizca konum olcmek yeter.
#
# DIZILIS NEDEN DOGRUDAN ILK BACAGIN YONUNDE KURULUYOR: cizgi formasyonunda
# takipci liderin SAGINDA durur, yani ilk bacagin yonu + 90. Operator takipciyi
# oraya koyar; ucak zaten slotunun yaninda dogar ve yerine kisa yoldan gider.
# Once lyaw'da dizilip sonra donseydik, lyaw'a gore takipcinin slotu ters
# tarafta kalabilir ve ucak liderin UZERINDEN gecerdi — plan_dogrula bunu
# reddeder ve gorev sahada baslamaz.
# Yonun kendisi SABIT YAZILMAZ, plan basliginda hesaplanip basilir
# (bkz. _pusula_adi): saha degisince talimat da kendiliginde degissin.
# Bedeli: ilki dilimlenmemis tek bir yaw komutu, ama o sirada ucaklar
# yerinde asili duruyor, seyir halinde degil.
#
# NOKTALAR NEDEN GPS, NED DEGIL (2 Agustos'ta degistirildi):
# NED metreleri surunun origin'ine goredir ve origin HER SAHADA farklidir.
# Saha degisince eski NED degerleri sessizce yanlis yeri gosterir — 2 Agustos'ta
# tam bu oldu: yeni sahanin noktalari eski origin'e gore ~2 km cikti. Enlem ve
# boylam ise MUTLAK: nokta_sec.html'de ne secildiyse o. NED'e cevirme ucus
# aninda, telemetriden TURETILEN gercek origin ile yapiliyor (_saha_coz).
# Boylece saha degisince yalnizca asagidaki liste degisir, baska hicbir sey.
SAHA_NOKTALAR_GPS = [
    (38.6904905, 39.1609624),   # 1  kalkis (lider buraya konur)
    (38.6904842, 39.1604850),   # 2  rotasyon -> ROLL 30 -> duzelt
    # 3. NOKTA HARITADAN SECILENIN 8 m DISARISINA (kuzeybatiya) ALINDI.
    # Secilen yerde 2-3-4 neredeyse tam dogrusaldi: orta nokta dogrudan
    # 0.17 m sapiyor, 2->3 yonu 59 derece, 3->4 yonu 60 derece. Aradaki
    # 1 derecelik fark SAHA_MIN_ROTASYON_DEG'in (5) altinda kaldigi icin
    # planda 3. noktada ROTASYON ADIMI HIC OLUSMUYORDU — suru oradan duz
    # geciyor, videoda nokta oldugu anlasilmiyordu. Sartname donusun bir
    # sonraki noktaya gecmeden ONCE gorulebilir olmasini istiyor.
    # 2-4 dogrusundan 8 m disari: donus 45 derece (20 dilim). Bedeli 5.8 sn.
    # Sartnamenin '3 dogrusal olmayan nokta' sarti zaten 1-2-3 ve 3-4-5
    # ucgenleriyle saglaniyordu; bu degisiklik GORUNURLUK icin.
    (38.6906412, 39.1606459),   # 3  CIZGI -> OK BASI
    (38.6906622, 39.1608739),   # 4  yerinde tirmanis 8 -> 15 m
    (38.6905010, 39.1609597),   # 5  INIS
]
# Ucus aninda SAHA_NOKTALAR_GPS'ten doldurulur. --noktalar ile NED olarak
# dogrudan verilirse SAHA_NOKTALAR_GPS bosaltilir ve bu liste aynen kullanilir.
SAHA_NOKTALAR = [(0.0, 0.0)] * 5
SAHA_IRTIFA_M = 8.0           # kalkis; 1-4 noktalari arasi
SAHA_IRTIFA2_M = 15.0         # 4. NOKTADA yerinde cikilir, inise kadar
SAHA_ROLL_DEG = 30.0
SAHA_MIN_ROTASYON_DEG = 5.0   # bunun altindaki donus ayri adim olmaz
# 5. noktaya varinca bu yone donulur ve CIZGI'ye gecilip oyle inilir
# (operator sarti, 2 Agustos). 135 = guneydogu.
SAHA_INIS_YON_DEG = 135.0

# --- Beklemeler -------------------------------------------------------------
# 5 DAKIKA SINIRI BUNLARI BELIRLIYOR. Yonerge: video 5 dakikayi gecmemeli VE
# hizlandirma/kirpma/kesme YASAK. Yani sinir gorev saatine degil, kameranin
# kaydettigi her seye: kalkis oncesi + gorev + INIS + disarm. 30 m'den inis
# tek basina ~31 sn (30->10 @1.5, 10->5 rampa, 5->0 @MPC_LAND_SPEED=0.4).
#
# Bekleme KONTROL ICIN GEREKLI DEGIL — setpoint'i drone 10 Hz'de kendi
# tazeliyor (esp32_bridge._guided_hedef_tekrar), beklemesek de ucak durur.
# Tek islevi varistan sonra salinimin sonmesi. Olculen varis hatalari
# 0.1-1.0 m, carpisma payi 7.24 m (esik 4.0) — yani kisaltmanin bedeli
# GORSEL, guvenlik degil.
#
# DIKEY HAREKET SONRASI KISALTILMADI: dikey oturma en yavas olani.
#
# 2 AGUSTOS — OPERATOR "beklemeleri kapatalim" DEDI. Tamamen sifirlamadim,
# gerekcesi asagida. Kesilen: 29 sn -> 12.5 sn (net kazanc 16.5 sn).
#
# SIFIRLANANLAR (dizilis, duz seyir): burada gosterilecek bir sey yok, ucak
# zaten hedefte duruyor. Guvenlik etkisi yok.
#
# SIFIRLANMAYANLAR ve NEDENLERI:
#   * ROTASYON 1.5 sn — sartname "donusun bir sonraki noktaya gecmeden ONCE
#     GORULEBILIR olmasini" sart kosuyor. Yay zaten saniyeler suruyor, ama
#     yayin bittigi ile bir sonraki bacagin basladigi an ust uste binerse
#     hakem "dondu mu, yoksa viraj mi aldi" diye bakar. Bu 1.5 sn o ayrimi
#     videoda tartismasiz kiliyor. UCUS icin degil, KANIT icin duruyor.
#   * FORMASYON 1.5 sn — ayni gerekce: "en az bir formasyon degisimi" sarti
#     ancak degisim TAMAMLANMIS halde goruntuye girerse ispatlanir.
#   * ROLL 5 sn — operatorun kendi sarti, dokunulmadi.
#   * DIKEY 3 sn — dikey oturma en yavasi; roll duzeltmesinde takipci
#     ARALIK_M*tan(30) kadar iniyor ve bunun sonmesi yatay hareketten uzun.
#   * INIS ONCESI 3 sn — LAND komutu ucak hala kayarken giderse inis
#     dedektoru gec tetiklenir.
#
# HIZ ILE BIRLIKTE ARTIRILMAZ: bekleme kismak, varis tasmasinin sondugu
# sureyi kaldiriyor; hizi artirmak tasmayi buyutuyor (frenleme mesafesi
# hizin KARESI, bkz. satir ~414). Ikisi ayni yone biner. Bu yuzden bekleme
# kisildi ve hiz 2.0'da BIRAKILDI.
SAHA_DIZILIS_BEKLEME_S = 0.0    # ilk cizgi dizilisi — gosterilecek sey yok
# DUZ SEYIR: 3.0 -> 0 yapilmisti, 1.5'e GERI ALINDI. Sebep gorsel degil,
# GUVENLIK: ARALIK_M 10 m'de kaldigi icin 4.0 m esigine pay 3.07 m (15 m'de
# 6.61 m olurdu, bkz. ARALIK_M notu). Beklemeyi sifirlarsak bir bacagin varis
# tasmasi sonmeden sonraki adim basliyor ve hata birikiyor — payin dar oldugu
# yerde bunu goze alamayiz. 1.5 sn gorev sacnesine ~5 sn ekliyor.
SAHA_BEKLEME_S = 1.5            # duz seyir bacaklari — varis tasmasi sonsun
SAHA_ROTASYON_BEKLEME_S = 1.5   # sartname: donus GORULEBILIR olmali
SAHA_FORMASYON_BEKLEME_S = 1.5  # sartname: formasyon degisimi ispatlanmali
SAHA_ROLL_BEKLE_S = 5.0         # operator sarti: "rollu sekilde 5 saniye"
SAHA_DIKEY_BEKLEME_S = 3.0      # dikey oturma en yavasi
SAHA_INIS_ONCESI_BEKLEME_S = 3.0  # LAND'den once kayma sonsun

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
MIN_AYRIM_M = AYAR.MIN_AYRIM_M

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

GOREV_HIZ_MPS = AYAR.GOREV_HIZ_MPS        # yatay yurutme hizi
GOREV_DIKEY_HIZ_MPS = AYAR.GOREV_DIKEY_HIZ_MPS   # irtifa degisim hizi
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
# Ofset, ucak HAREKETSIZ iken olculmeli. Tirmanis 1 m/s ile bitiyor.
#
# 2 AGUSTOS — BIR KEZ GEVSETILDI, GERI ALINDI. Once 0.30 m/s ve 3 sn yapildi
# ("kalkistan sonra 10 sn bekliyorlar" sikayeti icin). YANLISTI ve bir ucusu
# askida biraktı: bu pencere sadece bir bekleme degil, IRTIFA OFSETININ
# OLCULDUGU AN. Gevsetince olcum ucak HALA INERKEN alindi (d3: olcum aninda
# 7.85 m, gercekte oturdugu yer 6.68 m), ofset 0.15 esigini gecemedi ve
# uygulanmadi. Sonuc: plan hedefi 8.0'da kaldi, ucak baska irtifada asili
# kaldi, git_ve_bekle "vardi" diyemedi ve gorev ADIM 1'DE SONSUZA KADAR
# BEKLEDI. Operator elle indirmek zorunda kaldi.
#
# Kodun kendi uyarisi zaten bunu soyluyordu: "Ofset, ucak HAREKETSIZ iken
# olculmeli". Olculmus degerlere donuldu.
OTURMA_DIKEY_HIZ_MPS = 0.15
OTURMA_ASIM_S = 6.0

_son_komut_t = 0.0
_iniyor = False
_HARITA_DOSYA = None
_SENARYO = "kanit"

# GOREV 1 senaryosunun QR tablosu: "1:lat,lon;2:lat,lon" (--qr-tablo).
# qr_enjekte.py ile AYNI sozdizimi — operator ayni metni iki yerde de
# kullanabilsin, iki ayri bicim ogrenmesin.
_QR_TABLO = ""
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


# SAHTE TELEMETRI — YALNIZ --kuru ile, YALNIZ CIZIM ICIN.
#
# NEDEN VAR: gorev planlari lider konumu ve YONU olculerek kuruluyor. Sahadan
# uzaktayken (laptop sarjda, dronelar kapali) plan HIC cizilemiyordu. Sahada
# gecirilen dakikalar pahali; koreografiyi masabasinda cizip tartisabilmek
# lazim. Bu bayrak son olculen degerleri elle vererek tam kuru kosuyu
# (plan + harita + carpisma dogrulamasi) sahasiz yapmayi saglar.
#
# CANLI MODA ASLA KARISMAZ: main() --kuru olmadan verilirse hata verir.
# Cizilen plan GOSTERGEDIR — ucaklar yeniden yerlestirilince/acilinca konum ve
# yon degisir, sahada kuru kosu TEKRAR yapilmalidir.
_SAHTE_TELEMETRI: dict = {}


def _sahte_ayristir(metin: str, origin=None) -> dict:
    """'2:-27.11,3.32,222 3:-18.22,-13.53,310' -> telemetri sozlugu.

    Alanlar: drone_id : kuzey , dogu , yaw_derece

    origin (enlem, boylam) verilirse her uçağın lat/lon'u NED'den turetilir;
    boylece harita ve GPS listesi de uretilebilir (_origin_bul lat/lon ister).
    """
    t = {}
    for kayit in metin.split():
        did, _, geri = kayit.partition(":")
        alan = geri.split(",")
        if not did.strip().isdigit() or len(alan) != 3:
            raise ValueError(f"bozuk kayit: '{kayit}' — 'ID:kuzey,dogu,yaw' olmali")
        did = int(did)
        k, d, y = (float(x) for x in alan)
        t[did] = {
            "drone_id": did, "connected": True, "armed": False,
            "flight_mode": 0, "gps_fix_type": 6, "gps_satellites": 32,
            "battery_percent": 100.0, "pos_x": k, "pos_y": d, "pos_z": 0.0,
            "yaw_deg": y, "origin_synced": True, "ready_to_arm": True,
            "kill_switch_active": False, "rc_link_ok": True,
            "failsafe_active": False, "pilot_override_active": False,
            "roll_deg": 0.0, "pitch_deg": 0.0, "lat": 0.0, "lon": 0.0,
            "mode": "Sahte", "healthy": True, "home_set": True,
            "xy_valid": True, "z_valid": True, "v_xy_valid": True,
            "oscillation_detected": False, "unstable_flight": False,
            "vel_x": 0.0, "vel_y": 0.0, "vel_z": 0.0, "status_text": "",
        }
        if origin:
            olat, olon = origin
            t[did]["lat"] = olat + k / 111320.0
            t[did]["lon"] = olon + d / (111320.0 * math.cos(math.radians(olat)))
    return t


def durum() -> dict:
    if _SAHTE_TELEMETRI:
        return {k: dict(v) for k, v in _SAHTE_TELEMETRI.items()}
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


_PUSULA_ADLARI = ("kuzeye", "kuzeydoğuya", "doğuya", "güneydoğuya",
                  "güneye", "güneybatıya", "batıya", "kuzeybatıya")


def _pusula_adi(derece: float) -> str:
    """Dereceyi operatorun sahada kullanabilecegi yon adina cevirir.

    Ekrandaki "takipciyi liderin ...sina koy" talimatinda kullaniliyor.
    45 derecelik sekiz dilim; sinirda hangi tarafa yuvarlandigi onemsiz
    cunku talimat zaten kabaca yerlestirme icin (ucak sonra slotuna gider).
    """
    return _PUSULA_ADLARI[int((derece % 360.0) / 45.0 + 0.5) % 8]


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


def latlon_to_ned(origin, enlem, boylam):
    """ned_to_latlon'un tersi. HARITA_OFSET_KD UYGULANMAZ.

    O ofset yalnizca CIZIME ait bir duzeltme (altlik goruntunun georeferans
    kaymasi). Burada ucus geometrisi uretiliyor; ofseti eklersek gorev
    gercekten kayar. Bilerek asimetrik.
    """
    kuzey = (enlem - origin[0]) * 111320.0
    dogu = (boylam - origin[1]) * 111320.0 * math.cos(math.radians(origin[0]))
    return kuzey, dogu


def _saha_coz(t, kuru: bool) -> bool:
    """SAHA_NOKTALAR'i GPS listesinden, OLCULEN origin'e gore doldurur.

    Ucus aninda cagrilir, cunku origin'i ancak telemetri gelince biliyoruz.
    Basarisizsa False doner ve gorev BASLAMAZ — noktalari sessizce (0,0)
    birakip ucmak, suruyu origin'in oldugu yere gondermek demektir.
    """
    if not SAHA_NOKTALAR_GPS:
        return True                      # --noktalar ile NED verilmis
    org = _origin_bul(t)
    if org is None:
        # Telemetride lat/lon yoksa (ornegin --sahte ile origin verilmeden)
        # mutlak konum uretemeyiz. Yine de GEOMETRIYI dogrulayabilmek icin
        # 1. noktayi (0,0) kabul edip digerlerini ona gore koyuyoruz: bacak
        # uzunluklari ve donus acilari dogru cikar, yalnizca sahadaki mutlak
        # yer bilinmez. Bu YALNIZ kuru testte anlamli.
        if not kuru:
            print("  [saha] origin türetilemedi — GPS noktaları NED'e "
                  "çevrilemiyor, görev başlatılmıyor.")
            return False
        org = SAHA_NOKTALAR_GPS[0]
        print("  [saha] origin yok — 1. nokta (0,0) kabul edildi "
              "(yalnız geometri doğrulanır, mutlak konum DEĞİL)")
    SAHA_NOKTALAR[:] = [latlon_to_ned(org, la, lo)
                        for la, lo in SAHA_NOKTALAR_GPS]
    print(f"  [saha] origin {org[0]:.7f},{org[1]:.7f} — noktalar NED'e çevrildi:")
    for i, ((la, lo), (kz, dg)) in enumerate(
            zip(SAHA_NOKTALAR_GPS, SAHA_NOKTALAR), 1):
        print(f"         {i}: {la:.7f},{lo:.7f}  ->  ({kz:+8.1f}, {dg:+8.1f})")
    return True


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
.inisEt{background:#af52de;color:#fff;border:none;font:600 12px system-ui;
box-shadow:0 1px 4px #0007}
.inisEt::before{border-bottom-color:#af52de}
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
var inis=%(inis)s;      // her drone'un INIS yeri (plan'in son adimi)
var inisMesafe=%(inis_mesafe)s;  // iki inis yeri arasi, metre
var dronelar=%(dronelar)s;  // ucaklarin SU ANKI olculen yeri
var zarf=%(zarf)s;      // kacis zarfi yaricapi (m) — ucus_ayarlari tek kaynak
var hepsi=[];
if(yol.length>1){
  var cizgi=yol.map(function(p){return [p[1],p[2]]});
  L.polyline(cizgi.concat([cizgi[0]]),{color:'#ff3b30',weight:3}).addTo(m);
  hepsi=hepsi.concat(cizgi);
}
yol.forEach(function(p){
  hepsi.push([p[1],p[2]]);
  // KACIS ZARFI (SARI kesikli, gercek metre): kacinma tetiklenirse ucak
  // planli noktadan bu kadar YANA itilebilir. Yesil noktanin bos olmasi
  // yetmez — bu dairenin ICI de bina/agac/tel icermemeli.
  L.circle([p[1],p[2]],{radius:zarf,color:'#ffd60a',weight:2,
    dashArray:'6,4',fill:false}).addTo(m);
  L.circleMarker([p[1],p[2]],{radius:8,color:'#fff',weight:2,
    fillColor:'#34c759',fillOpacity:1}).addTo(m)
   .bindTooltip(p[0],{permanent:true,direction:'top'});
});
// INIS NOKTALARI — MOR. Plan'in SON adimindaki hedefler, yani ucaklarin
// gercekten inecegi yerler. Ayri ve belirgin ciziliyorlar cunku operatorun
// haritadan yapacagi en kritik kontrol bu: cizgi formasyonunda takipci
// liderden ARALIK_M kadar YANDA iniyor ve orasinin bos olmasi gerekiyor.
// Daha once bunlar kucuk mavi noktalardi ve "hedef" diye etiketleniyordu;
// hangisinin inis yeri oldugu haritaya bakan icin belli degildi.
if(inis.length>1){
  var il=inis.map(function(p){return [p[1],p[2]]});
  L.polyline(il,{color:'#af52de',weight:2,dashArray:'6,6'}).addTo(m)
   .bindTooltip(inisMesafe,{permanent:true,direction:'center'});
}
inis.forEach(function(p){
  hepsi.push([p[1],p[2]]);
  // 5 m GERCEK-METRE daire: inis alaninda bos tutulmasi gereken bolge.
  // L.circle (L.circleMarker degil) — yakinlastirinca boyu degismez, yani
  // uydu goruntusundeki bina/arac ile dogrudan karsilastirilabilir.
  L.circle([p[1],p[2]],{radius:5,color:'#af52de',weight:2,
    fillColor:'#af52de',fillOpacity:0.18}).addTo(m);
  // INIS ZARFI (MOR kesikli): kacinma inis yaklasmasinda iterse ucak
  // 5 m'lik bos alanin da DISINA, bu halkaya kadar sasabilir (5 + zarf).
  L.circle([p[1],p[2]],{radius:5+zarf,color:'#af52de',weight:1.5,
    dashArray:'6,4',fill:false}).addTo(m);
  L.circleMarker([p[1],p[2]],{radius:9,color:'#fff',weight:3,
    fillColor:'#af52de',fillOpacity:1}).addTo(m)
   .bindTooltip(p[0],{permanent:true,direction:'bottom',offset:[0,10],
     className:'inisEt'});
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
    # INIS YERLERI = plan'in SON adimindaki hedefler. Plan bitince gorev()
    # dogrudan indir() cagiriyor, yani ucaklar tam bu noktalarda iniyor.
    inis = []
    if plan:
        for did, h in sorted(plan[-1][2].items()):
            la, lo = ned_to_latlon(origin, h[0], h[1])
            etiket = f"d{did} İNİŞ" + (" (LİDER)" if did == LIDER else "")
            inis.append([etiket, la, lo])
    # Iki inis yeri arasi mesafe NED'de olculur, lat/lon'da degil: harita
    # ofseti ikisine de ayni biniyor ve boylece sadelesiyor.
    inis_mesafe = ""
    if plan and len(plan[-1][2]) == 2:
        (_a, ha), (_b, hb) = sorted(plan[-1][2].items())
        inis_mesafe = f"{math.dist(ha[:2], hb[:2]):.1f} m"
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
    zarf = AYAR.KACINMA_ZARF_YANAL_M
    ozet = (f"aralik {ARALIK_M:.0f} m &middot; yon {ROTA_YONU_DEG:.0f}&deg;{ofs}<br>"
            f"<b>kod engel gormez</b> - rotada bina/agac olmamali<br>"
            f"<span style='color:#af52de'><b>MOR = INIS YERI</b></span>"
            f" (5 m daire bos tutulmali"
            + (f", aralari {inis_mesafe}" if inis_mesafe else "") + ")<br>"
            f"<span style='color:#c7a500'><b>SARI kesikli = KACIS ZARFI</b>"
            f"</span> ({zarf:.0f} m: kacinma iterse ucak planli noktadan bu"
            f" kadar yana kayabilir; dikeyde +{AYAR.KACINMA_KATMAN_M:.0f} m"
            f" tirmanma haritada gorunmez)<br>"
            f"yesil = gorev noktasi &middot; "
            f"turuncu = ucaklarin SU ANKI yeri (altlik kaymasini buradan olc)")
    pathlib.Path(dosya).write_text(
        _HARITA_SABLON % {"yol": _j.dumps(yol), "inis": _j.dumps(inis),
                          "inis_mesafe": _j.dumps(inis_mesafe),
                          "dronelar": _j.dumps(dronelar), "ozet": ozet,
                          "zarf": _j.dumps(zarf)},
        encoding="utf-8")
    print(f"\n=== HARITA YAZILDI ===\n  {dosya}")
    print(f"  Tarayicida ac:  xdg-open {dosya}")


_HARITA_SEKANS_SABLON = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Yelpence - formasyon gecis</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#h{height:100%%;margin:0}
.bilgi{position:absolute;z-index:1000;top:10px;left:50px;background:#fffd;
padding:8px 12px;font:13px system-ui;border-radius:6px;box-shadow:0 1px 6px #0006;max-width:340px}
.fazEt{background:#fff;border:none;font:700 12px system-ui;border-radius:4px;
box-shadow:0 1px 4px #0007;padding:2px 6px}
.kalkEt{background:#e0342c;color:#fff;border:none;font:700 12px system-ui;
box-shadow:0 1px 4px #0007}
.kalkEt::before{border-bottom-color:#e0342c}
</style></head><body>
<div class="bilgi">%(ozet)s</div>
<div id="h"></div><script>
var m=L.map('h');
// maxNativeZoom 18 SART: Esri z19+ icin bu bolgede yer tutucu donduruyor.
var uydu=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:22,maxNativeZoom:18,attribution:'Esri'}).addTo(m);
var clarity=L.tileLayer('https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:22,maxNativeZoom:19,attribution:'Esri Clarity'});
var fazlar=%(fazlar)s;   // [{ad,renk,etiket_konum:[la,lo],slotlar:[[did,la,lo],..]},..]
var kalkis=%(kalkis)s;   // [[did,la,lo],..]  kalkis = INIS
var yollar=%(yollar)s;   // [{did,noktalar:[[la,lo],..]},..]
var simdiki=%(simdiki)s; // [[etiket,la,lo],..]
var zarfKose=%(zarf_kose)s; // [[la,lo] x4] tampon dikdortgen
var hepsi=[];

// FAZ SEKILLERI — faz basina TEK renk, slotlar ince cizgiyle bagli,
// kalici etiket yalniz faz merkezinde (1 CIZGI / 2 OK BASI / ...).
var gFaz=L.layerGroup().addTo(m);
fazlar.forEach(function(f){
  var pts=f.slotlar.map(function(s){return [s[1],s[2]]});
  pts.forEach(function(p){hepsi.push(p)});
  L.polyline(pts,{color:f.renk,weight:3,opacity:0.9}).addTo(gFaz);
  f.slotlar.forEach(function(s){
    L.circleMarker([s[1],s[2]],{radius:6,color:'#fff',weight:2,
      fillColor:f.renk,fillOpacity:1}).addTo(gFaz)
     .bindTooltip('d'+s[0]+' · '+f.ad,{direction:'top'});
  });
  L.marker(f.etiket_konum,{opacity:0}).addTo(gFaz)
   .bindTooltip(f.etiket,{permanent:true,direction:'center',
     className:'fazEt'});
});

// UCAK YOLLARI — gri kesikli; kimin oldugu uzerine gelince.
var gYol=L.layerGroup().addTo(m);
yollar.forEach(function(y){
  L.polyline(y.noktalar,{color:'#555',weight:1.5,dashArray:'4,6',
    opacity:0.8}).addTo(gYol).bindTooltip('d'+y.did+' yolu');
});

// KALKIS = INIS — kirmizi hedef isareti + 5 m bos-alan dairesi (gercek
// metre; yakinlastirinca buyumez, uydudaki engelle dogrudan kiyaslanir).
var gKalk=L.layerGroup().addTo(m);
kalkis.forEach(function(s){
  hepsi.push([s[1],s[2]]);
  L.circle([s[1],s[2]],{radius:5,color:'#e0342c',weight:2,
    fillColor:'#e0342c',fillOpacity:0.12}).addTo(gKalk);
  L.circleMarker([s[1],s[2]],{radius:9,color:'#fff',weight:3,
    fillColor:'#e0342c',fillOpacity:1}).addTo(gKalk)
   .bindTooltip('d'+s[0]+' KALKIŞ+İNİŞ',{permanent:true,
     direction:'bottom',offset:[0,10],className:'kalkEt'});
});

// SU ANKI KONUM (turuncu) — altlik kaymasini gozle olcmek icin.
var gSimdi=L.layerGroup().addTo(m);
simdiki.forEach(function(p){
  L.circleMarker([p[1],p[2]],{radius:6,color:'#000',weight:1.5,
    fillColor:'#ff9f0a',fillOpacity:0.95}).addTo(gSimdi)
   .bindTooltip(p[0]);
});

// GUVENLIK ZARFI — nokta basina daire YERINE tum alani saran TEK
// dikdortgen (butun faz slotlari + kacis payi). Ici bos olmali.
var gZarf=L.layerGroup().addTo(m);
L.polygon(zarfKose,{color:'#ffd60a',weight:2.5,dashArray:'8,6',
  fill:false}).addTo(gZarf);
zarfKose.forEach(function(p){hepsi.push(p)});

L.control.layers({'Uydu (Esri)':uydu,'Uydu (Clarity)':clarity},
 {'Faz şekilleri':gFaz,'Uçak yolları':gYol,'Kalkış/İNİŞ':gKalk,
  'Şu anki konum':gSimdi,'Güvenlik zarfı':gZarf},
 {collapsed:false}).addTo(m);
L.control.scale({metric:true,imperial:false,maxWidth:220}).addTo(m);
m.fitBounds(L.latLngBounds(hepsi).pad(0.6),{maxZoom:20});
</script></body></html>
"""

_SEKANS_FAZ_RENKLERI = ("#0a84ff", "#b57500", "#af52de", "#1f9d4d")


def harita_yaz_sekans(plan, origin, dosya, t=None):
    """formasyon_gecis icin OKUNAKLI harita — genel harita_yaz yerine.

    Genel harita bu senaryoda karisiyordu (28 Agu operator geri bildirimi):
    dort fazin noktalari ayni bolgeye ust uste dusuyor, her noktaya kalici
    etiket + zarf dairesi binince okunmaz oluyordu. Burada:
      * faz basina TEK renk ve TEK kalici etiket (slot adlari hover'da)
      * ucak yollari ince gri kesikli (kim nereden nereye — hover)
      * kalkis=INIS tek kirmizi isaret (eve donusuyle ayni nokta)
      * zarf: nokta basina daire yerine tum alani saran TEK dikdortgen
      * katman denetimiyle her grup ac/kapa
    """
    if origin is None:
        print("  harita: origin turetilemedi, atlandi")
        return
    import json as _j
    fazlar = []
    for i, adim in enumerate(plan):
        etiket, _h, hedefler = adim[0], adim[1], adim[2]
        ad = etiket.split(" (")[0]
        renk = _SEKANS_FAZ_RENKLERI[i % len(_SEKANS_FAZ_RENKLERI)]
        slotlar = []
        for did in sorted(hedefler):
            la, lo = ned_to_latlon(origin, hedefler[did][0], hedefler[did][1])
            slotlar.append([did, la, lo])
        mk = sum(hedefler[d][0] for d in hedefler) / len(hedefler)
        md = sum(hedefler[d][1] for d in hedefler) / len(hedefler)
        ela, elo = ned_to_latlon(origin, mk, md)
        fazlar.append({"ad": ad, "renk": renk, "etiket": f"{i + 1} {ad}",
                       "etiket_konum": [ela, elo], "slotlar": slotlar})
    # Kalkis = son adim (EVE) hedefleri = inis yerleri.
    kalkis = []
    if plan:
        for did in sorted(plan[-1][2]):
            h = plan[-1][2][did]
            la, lo = ned_to_latlon(origin, h[0], h[1])
            kalkis.append([did, la, lo])
    # Ucak basina yol: kalkis -> her fazin slotu (sirali).
    yollar = []
    for did in DRONELAR:
        noktalar = []
        for k in kalkis:
            if k[0] == did:
                noktalar.append([k[1], k[2]])
        for adim in plan:
            h = adim[2][did]
            la, lo = ned_to_latlon(origin, h[0], h[1])
            noktalar.append([la, lo])
        yollar.append({"did": did, "noktalar": noktalar})
    simdiki = []
    for did, d in sorted((t or {}).items()):
        if not d.get("connected") or abs(d.get("lat", 0.0)) < 0.001:
            continue
        la, lo = ned_to_latlon(origin, d["pos_x"], d["pos_y"])
        simdiki.append([f"d{did} şu an", la, lo])
    # Zarf dikdortgeni: butun plan noktalarinin NED bbox'u + kacis payi.
    zarf = AYAR.KACINMA_ZARF_YANAL_M
    ks = [h[0] for adim in plan for h in adim[2].values()]
    ds = [h[1] for adim in plan for h in adim[2].values()]
    kmin, kmax = min(ks) - zarf, max(ks) + zarf
    dmin, dmax = min(ds) - zarf, max(ds) + zarf
    zarf_kose = [list(ned_to_latlon(origin, kk, dd))
                 for kk, dd in ((kmax, dmin), (kmax, dmax),
                                (kmin, dmax), (kmin, dmin))]
    ozet = (f"<b>Formasyon geçiş testi</b> — aralık "
            f"{AYAR.SEKANS_ARALIK_M:.1f} m · irtifa "
            f"{AYAR.SEKANS_IRTIFA_M:.0f} m<br>"
            + " → ".join(f"<span style='color:{f['renk']}'><b>{f['ad']}"
                         f"</b></span>" for f in fazlar) + "<br>"
            f"<span style='color:#e0342c'><b>KIRMIZI = kalkış VE iniş"
            f"</b></span> (eve dönüş; 5 m daire boş olmalı)<br>"
            f"<span style='color:#c7a500'><b>SARI çerçeve</b></span> = "
            f"uçuş alanı + {zarf:.0f} m kaçış payı — İÇİ tamamen boş "
            f"olmalı (kod engel görmez); dikeyde +"
            f"{AYAR.KACINMA_KATMAN_M:.0f} m<br>"
            f"gri kesikli = uçak yolları · turuncu = şu anki yer "
            f"(altlık kayması buradan ölçülür)")
    pathlib.Path(dosya).write_text(
        _HARITA_SEKANS_SABLON % {
            "fazlar": _j.dumps(fazlar), "kalkis": _j.dumps(kalkis),
            "yollar": _j.dumps(yollar), "simdiki": _j.dumps(simdiki),
            "zarf_kose": _j.dumps(zarf_kose), "ozet": ozet},
        encoding="utf-8")
    print(f"\n=== HARITA YAZILDI (sekans gorunumu) ===\n  {dosya}")


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
    # KACIS ZARFI: kacinma tetiklenirse ucak planli noktadan yana itilir;
    # temiz tutulmasi gereken alan kutudan ZARF kadar genis (24 Agustos).
    z_pay = AYAR.KACINMA_ZARF_YANAL_M
    print(f"  + kaçış zarfı (her yana {z_pay:.0f} m): "
          f"{max(k)-min(k)+2*z_pay:.0f} m (K-G) x "
          f"{max(d)-min(d)+2*z_pay:.0f} m (D-B)"
          f"  · dikeyde +{AYAR.KACINMA_KATMAN_M:.0f} m tırmanma payı")
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
    # SABIT MESAFE (operator karari). Referans olarak GD ekseninin nerede
    # oldugunu da hesaplayip ekrana basiyoruz ki ne kadar gecildigi gorulsun.
    s_eksen = -((P[0] - H[0]) * math.cos(kd) + (P[1] - H[1]) * math.sin(kd))
    s = TAM_KD_MESAFE_M
    Q = (P[0] + s * math.cos(kd), P[1] + s * math.sin(kd))
    gd = (math.degrees(math.atan2(H[1] - Q[1], H[0] - Q[0])) + 360.0) % 360.0
    print(f"    [tam] KD bacağı {s:.0f} m · GD ekseni {s_eksen:.1f} m'de "
          f"({s - s_eksen:+.1f} m geçiliyor) · eve yön {gd:.0f}° "
          f"(eksende olsaydı 135°)")

    plan = [
        (f"çizgi dizilişi (lider d{lider})", lyaw, _hedefler(H, lyaw), True),
        (f"-> {TAM_MESAFE_M:.0f} m ileri (yön {lyaw:.0f}°)", lyaw,
         _hedefler(P, lyaw), TAM_BEKLEME_S),
    ]
    _rotasyon(plan, P, lyaw, TAM_KD_DEG)
    plan.append((f"ROLL {TAM_ROLL_DEG:.0f}° (takipçi yukarı)", TAM_KD_DEG,
                 _hedefler(P, TAM_KD_DEG, TAM_ROLL_DEG), True))
    plan.append((f"-> KD {s:.0f} m, roll KORUNARAK", TAM_KD_DEG,
                 _hedefler(Q, TAM_KD_DEG, TAM_ROLL_DEG), TAM_BEKLEME_S))
    plan.append(("irtifa EŞİTLE (roll 0)", TAM_KD_DEG,
                 _hedefler(Q, TAM_KD_DEG, 0.0), True))
    _rotasyon(plan, Q, TAM_KD_DEG, gd)
    plan.append((f"-> EV (lider d{lider} kalkış noktası)", gd,
                 _hedefler(H, gd), True))
    return plan


def plan_kur_saha(t):
    """KANIT VİDEOSU — haritadan seçilen 5 nokta (bkz. SAHA_NOKTALAR_GPS).

     1) kalkış SAHA_IRTIFA_M; takipçi liderin yanına ÇİZGİ formasyonunda
        gelir (diziliş doğrudan 1→2 bacağının yönünde kurulur)
     2) 2. noktaya (formasyon korunarak)
     3) 3. noktanın yönüne DÖN — roll'dan ÖNCE
     4) ROLL 30° — lider sabit, takipçi yukarı; 5 sn rollü bekleme
     5) roll DÜZELT
     6) 3. noktaya
     7) ÇİZGİ -> OK BAŞI
     8) 4. noktaya (ok başı ile)
     9) 4. NOKTADA YERİNDE irtifa SAHA_IRTIFA_M -> SAHA_IRTIFA2_M
    10) 5. noktaya (ok başı korunarak)
    11) SAHA_INIS_YON_DEG yönüne dön, OK BAŞI -> ÇİZGİ
    12) iniş (plan bitince gorev() indir() çağırır)

    Her bacaktan ÖNCE sürü gideceği yöne döner (dilimlenmiş yay; lider
    yerinde durur, takipçi etrafında yay çizer).
    """
    lider = LIDER
    l = t[lider]
    P = [(l["pos_x"], l["pos_y"])] + list(SAHA_NOKTALAR[1:])

    sapma = math.hypot(P[0][0] - SAHA_NOKTALAR[0][0],
                       P[0][1] - SAHA_NOKTALAR[0][1])
    print(f"    [saha] 1. nokta ÖLÇÜLDÜ: ({P[0][0]:+.1f}, {P[0][1]:+.1f}) — "
          f"haritada seçtiğinden {sapma:.1f} m sapma")

    slot = {lider: 0}
    for i, did in enumerate([d for d in DRONELAR if d != lider], start=1):
        slot[did] = i

    def _hedefler(nokta, yon, formasyon, irtifa, roll=0.0):
        """Lider 'nokta'da ve 'irtifa'da; formasyon 'yon'a, 'roll' eğimli."""
        ofs = formasyon_ofsetleri(formasyon, len(DRONELAR))
        h = math.radians(yon)
        o_i, o_s = ofs[0]
        merkez = (nokta[0] - (o_i * math.cos(h) + o_s * (-math.sin(h))),
                  nokta[1] - (o_i * math.sin(h) + o_s * math.cos(h)))
        dz = egim_dz(ofs, 0.0, roll)
        dz = [z - dz[0] for z in dz]          # lider referans: kendisi 0
        noktalar = [slot_dunya(merkez, yon, *o) + (irtifa + z,)
                    for o, z in zip(ofs, dz)]
        return {did: noktalar[slot[did]] for did in DRONELAR}

    def _rotasyon(plan, nokta, bas, son, formasyon, irtifa):
        """bas -> son yönüne KISA taraftan, geçiş yarıçaplı dilimlerle.

        KUCUK ACILAR ATLANIR: 3->4 bacaginda donus yalniz 2 derece. Bunu ayri
        bir rotasyon adimi yapmak 6 saniyelik yerlesme beklemesi ekliyor ve
        videoda gorunmuyor bile. Esigin altinda kalirsa hic adim uretmiyoruz;
        yeni yon bir sonraki bacagin uzerinde tasiniyor (ucak seyir ederken
        2 derece cevirmek bedava).
        """
        fark = (son - bas) % 360.0
        if fark > 180.0:
            fark -= 360.0
        if abs(fark) < SAHA_MIN_ROTASYON_DEG:
            return
        n = max(1, int(round(abs(fark) / DONUS_ROTASYON_ADIM_DEG)))
        for i in range(1, n + 1):
            ara = (bas + fark * i / n) % 360.0
            if i == n:
                plan.append((f"rotasyon -> {ara:.0f}° tamam", ara,
                             _hedefler(nokta, ara, formasyon, irtifa),
                             SAHA_ROTASYON_BEKLEME_S))
            else:
                plan.append((f"rotasyon {i}/{n} -> {ara:.0f}°", ara,
                             _hedefler(nokta, ara, formasyon, irtifa),
                             False, DONUS_GECIS_R_M))

    yon = [yon_derece(P[i], P[i + 1]) for i in range(4)]
    uzn = [math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1])
           for i in range(4)]
    for i in range(4):
        print(f"    [saha] {i+1}→{i+2}: {uzn[i]:.1f} m, yön {yon[i]:.0f}°")

    C1, C2 = "cizgi", "okbasi"
    A1, A2 = SAHA_IRTIFA_M, SAHA_IRTIFA2_M

    plan = [
        # Takipcinin yonu HESAPLANIR, yazilmaz: cizgi formasyonunda takipci
        # liderin SAGINDA durur, yani ilk bacagin yonu + 90. Burasi eskiden
        # "takipci batiya" diye SABIT yaziliyordu (199 derecelik eski sahaya
        # gore dogruydu). Saha degisince etiket yanlis yere isaret eder ve
        # operator ucagi ters tarafa koyar; o zaman takipci liderin UZERINDEN
        # gecmek zorunda kalir ve plan_dogrula gorevi sahada reddeder.
        (f"çizgi dizilişi (lider d{lider}, takipçi "
         f"{_pusula_adi((yon[0] + 90.0) % 360.0)})", yon[0],
         _hedefler(P[0], yon[0], C1, A1), SAHA_DIZILIS_BEKLEME_S),
        (f"-> 2. NOKTA ({uzn[0]:.0f} m, yön {yon[0]:.0f}°)", yon[0],
         _hedefler(P[1], yon[0], C1, A1), SAHA_BEKLEME_S),
    ]
    # ROTASYON ROLL'DAN ONCE (operator sarti, 2 Agustos): "nokta 2'ye gitsinler,
    # orada nokta 3'e donsunler HAREKET ETMEDEN ONCE roll yapsin, sonra rollu
    # duzeltsin". Eskiden sira roll -> duzelt -> rotasyon idi.
    #
    # YAN FAYDASI GERCEK: roll, takipciyi liderin etrafinda ARALIK_M yaricapli
    # bir yay uzerinde tutarak yukari kaldiriyor. Once rotasyonu bitirirsek
    # takipci roll aninda ZATEN son yonundeki slotunda duruyor; roll bitince
    # yalnizca DIKEY iniyor ve arkasindan yatay hareket gelmiyor. Eski sirada
    # roll duzeltmesinin dikey oturmasi ile rotasyon yayinin yatay hareketi
    # ust uste biniyordu.
    _rotasyon(plan, P[1], yon[0], yon[1], C1, A1)
    plan.append((f"ROLL {SAHA_ROLL_DEG:.0f}° (takipçi yukarı)", yon[1],
                 _hedefler(P[1], yon[1], C1, A1, SAHA_ROLL_DEG),
                 SAHA_ROLL_BEKLE_S))
    plan.append(("roll DÜZELT", yon[1],
                 _hedefler(P[1], yon[1], C1, A1), SAHA_DIKEY_BEKLEME_S))
    plan.append((f"-> 3. NOKTA ({uzn[1]:.0f} m, yön {yon[1]:.0f}°)", yon[1],
                 _hedefler(P[2], yon[1], C1, A1), SAHA_BEKLEME_S))
    plan.append(("formasyon: ÇİZGİ -> OK BAŞI", yon[1],
                 _hedefler(P[2], yon[1], C2, A1), SAHA_FORMASYON_BEKLEME_S))
    _rotasyon(plan, P[2], yon[1], yon[2], C2, A1)
    plan.append((f"-> 4. NOKTA ({uzn[2]:.0f} m, yön {yon[2]:.0f}°)", yon[2],
                 _hedefler(P[3], yon[2], C2, A1), SAHA_BEKLEME_S))
    # TIRMANIS 4. NOKTADA, YERINDE (operator sarti): "nokta 4'e gitsinler
    # ORADA 15 metre irtifaya ciksinlar". Onceki surumde son bacaga gomuluydu.
    # OK BASI KORUNUYOR: operator 4. noktada cizgiye donmeyi istemedi, yani
    # suru 3. noktadan INISE KADAR ok basi formasyonunda kaliyor. Sartnamenin
    # "en az bir formasyon degisimi" sarti cizgi -> ok basi ile zaten saglandi.
    plan.append((f"irtifa {A1:.0f} -> {A2:.0f} m (yerinde, ok başı)", yon[2],
                 _hedefler(P[3], yon[2], C2, A2), SAHA_DIKEY_BEKLEME_S))
    _rotasyon(plan, P[3], yon[2], yon[3], C2, A2)
    plan.append((f"-> 5. NOKTA ({uzn[3]:.0f} m, yön {yon[3]:.0f}°)",
                 yon[3], _hedefler(P[4], yon[3], C2, A2),
                 SAHA_BEKLEME_S))
    # INIS DIZILISI (operator sarti, 2 Agustos): "5 numaraya geldiginde
    # guneydoguya donsunler ve cizgi formasyonuna gecsinler, oyle insinler."
    #
    # SIRA BILEREK BOYLE: once rotasyon, sonra formasyon. Rotasyon takipciyi
    # liderin etrafinda ARALIK_M yaricapli bir yay uzerinde tasiyor. Formasyonu
    # once degistirseydik takipci once ok basi slotundan cizgi slotuna gider,
    # ARDINDAN yay boyunca yeniden tasinirdi — iki ayri hareket. Bu sirayla
    # takipci son slotuna tek seferde oturuyor.
    #
    # INISTEN ONCEKI SON ADIM BU: plan bitince gorev indir() cagiriyor, yani
    # ucaklar bu formasyonda ve bu yonde iniyor. Cizgi formasyonunda takipci
    # liderin SAGINDA, yani 135+90 = 225 (guneybati) yonunde ARALIK_M kadar
    # otede. Operator inis alanini ona gore bos tutmali.
    _rotasyon(plan, P[4], yon[3], SAHA_INIS_YON_DEG, C2, A2)
    plan.append((f"formasyon: OK BAŞI -> ÇİZGİ (iniş dizilişi, yön "
                 f"{SAHA_INIS_YON_DEG:.0f}° {_pusula_adi(SAHA_INIS_YON_DEG)})",
                 SAHA_INIS_YON_DEG,
                 _hedefler(P[4], SAHA_INIS_YON_DEG, C1, A2),
                 SAHA_INIS_ONCESI_BEKLEME_S))
    return plan


def plan_kur_gorev1(t):
    """GOREV 1'in KAGIT MODELI — bu betik gorevi YURUTMEZ, CIZER.

    🔴 KARISMASIN: Gorev 1 ZATEN YAZILI ve UCAKTA kosuyor
    (`swarm_missions/mission1_dynamic_swarm` + `mission_fsm`). Otonom
    zincir odur; YKI'nin izinli tek rolu "gorevi baslat".

    Burasi o zincirin YERDEKI MODELI. Tek amaci CLAUDE.md §9 madde 5'i
    yerine getirmek:
      * `--kuru`  -> carpisma denetimi (hangi iki ucak birbirine yaklasiyor)
      * `--harita`-> ucaklarin gidecegi ve ozellikle INECEGI noktalari
                     uydu goruntusune koymak
    Diger senaryolar (kanit/final/saha) YKI'den goto basar; bu senaryo
    hicbir sey GONDERMEZ, yalnizca plan uretir. Canli kosulursa da tek
    yaptigi ayni noktalari basmaktir — ama amaci o degil.

    🔴 KAYMA RISKI VE NASIL ONLENDI. Elle yazilmis bir model, ucaktaki
    kodla zamanla ayrisir ve harita SESSIZCE yalan soylemeye baslar. Bu
    yuzden hicbir sayi burada tekrar YAZILMIYOR:
      * irtifalar / kadro / kamerali ajan  -> `ucus_ayarlari` (AYAR)
      * QR arama merdiveni                 -> orkestratorun KENDISINDEN
        (`Mission1Orchestrator._arama_merdiveni`), yani ucak hangi
        basamaklari ucacaksa harita onlari cizer
      * kalkis dizilisi ve iniş noktalari  -> CANLI TELEMETRI
      * QR konumlari                       -> --qr-tablo (enjekte edilenle
        ayni sozdizimi)

    MODELLENEN AKIS (orchestrator.py karsiliklariyla):
      1) kalkis            herkes KENDI yerinde, GOREV_KALKIS_IRTIFA
      2) QR'a seyir        `_on_navigate`: merkez, KAMERALI ucak QR'in
                           ustune gelecek sekilde cipalanir
      3) QR uzerinde       `_maybe_qr_recovery`: inen irtifa merdiveni
      4) eve donus         `_donus_hedefi` faz 1
      5) dikey merdiven    faz 2 (yatayda kimildama yok)
      6) dagilma           faz 3 — herkes KENDI kalkis noktasina
      7) inis              faz 4; plan'in SON adimi = INIS NOKTALARI

    ⚠️ DIZILIS SEYIRDE DONER. Ofsetler kalkis basligi cercevesinde
    saklaniyor (`_snapshot_offsets` + `_ters_dondur`), asagi akista
    `formation_node` onlari komutun heading'iyle donduruyor. Kalkista
    heading = kalkis basligi (iki dondurme sadelesir), seyirde ise
    heading = QR'a bearing — yani diziliş aradaki fark kadar DONER.
    Model bunu taklit ediyor; etmeseydi harita takipcileri yanlis yerde
    gosterirdi.
    """
    eksik = [d for d in DRONELAR if d not in t]
    if eksik:
        raise SystemExit(
            f"Telemetride yok: drone {eksik} — gorev1 senaryosu kalkis "
            f"dizilisini OLCUYOR, uydurmuyor. Ucaklar ayakta olmali."
        )
    origin = _origin_bul(t)
    if origin is None:
        raise SystemExit("origin turetilemedi (GPS yok) — QR konumlari "
                         "NED'e cevrilemez.")
    if not _QR_TABLO:
        raise SystemExit(
            "gorev1 senaryosu --qr-tablo ISTER: \"1:lat,lon;2:lat,lon\".\n"
            "  Ucaklara enjekte edilen tabloyla AYNI metni ver — harita "
            "baska bir tabloyu cizerse kontrol degeri kalmaz."
        )

    # --- Kalkis dizilisi: OLCULUR ------------------------------------------
    K = {d: (t[d]["pos_x"], t[d]["pos_y"]) for d in DRONELAR}
    home = (sum(p[0] for p in K.values()) / len(K),
            sum(p[1] for p in K.values()) / len(K))
    kalkis_yaw = float(t[LIDER].get("yaw_deg") or 0.0)

    def _govdeye(dk, dd, yon):
        """Dunya ofsetini govde (ileri, sag) cercevesine cevirir."""
        h = math.radians(yon)
        return (dk * math.cos(h) + dd * math.sin(h),
                -dk * math.sin(h) + dd * math.cos(h))

    # Ofsetler KALKIS BASLIGI cercevesinde — orchestrator._ters_dondur.
    ofs = {d: _govdeye(K[d][0] - home[0], K[d][1] - home[1], kalkis_yaw)
           for d in DRONELAR}

    def _hedefler(merkez, yon, irtifa, katman=None):
        """merkez + dondurulmus ofset -> {drone: (kuzey, dogu, irtifa)}."""
        out = {}
        for i, d in enumerate(DRONELAR):
            x, y = slot_dunya(merkez, yon, *ofs[d])
            z = irtifa + (0.0 if katman is None else katman * i)
            out[d] = (x, y, z)
        return out

    # --- QR tablosu --------------------------------------------------------
    qr_ned = []
    for parca in _QR_TABLO.split(";"):
        parca = parca.strip()
        if not parca:
            continue
        qid, konum = parca.split(":", 1)
        la, lo = konum.split(",", 1)
        qr_ned.append((int(qid), latlon_to_ned(origin, float(la), float(lo))))

    kam = int(AYAR.GOREV_KAMERA_AJAN or 0) or LIDER
    if kam not in DRONELAR:
        raise SystemExit(f"GOREV_KAMERA_AJAN={kam} kadroda ({DRONELAR}) YOK — "
                         f"formasyon QR ustune UCMAYAN bir ucagi cipalar.")

    # --- Arama merdiveni: ORKESTRATORUN KENDISINDEN ------------------------
    try:
        from swarm_missions.mission1_dynamic_swarm.orchestrator import (
            Mission1Orchestrator, OrchestratorConfig,
        )
        merdiven = Mission1Orchestrator(OrchestratorConfig(
            qr_okuma_irtifa_m=AYAR.GOREV_QR_OKUMA_IRTIFA_M,
        ))._arama_merdiveni()
    except ImportError as e:
        raise SystemExit(
            f"orchestrator ithal edilemedi ({e}) — arama merdivenini "
            f"BURADA TEKRAR YAZMAK yerine duruyoruz: elle yazilan bir "
            f"merdiven ucaktakinden sessizce ayrisir ve harita yalan soyler."
        )

    kalkis_irtifa = float(AYAR.GOREV_KALKIS_IRTIFA_M)
    katman = float(AYAR.GOREV_DONUS_KATMAN_M)
    # 🔴 TOPLANMA MERDIVENI DE MODELLENMELI (8 Eylul'de eksikti).
    # `_on_takeoff` kalkista bu merdiveni kuruyor ve QR'da formasyon
    # OTURANA KADAR acik tutuyor (`_maybe_formation_settled` kaldiriyor).
    # Modelde yoktu; gidis bacagini ucaklar AYNI irtifadaymis gibi
    # cizdigi icin olmayan carpismalar raporluyordu.
    toplanma = float(getattr(AYAR, 'GOREV_TOPLANMA_KATMAN_M', 0.0) or 0.0)

    def _gecis(plan, etiket, m0, y0, m1, y1, irtifa, katman=None):
        """Merkez ve heading'i BIRLIKTE dilimleyerek plana ekler.

        🔴 DILIMLEMEK ZORUNLU, yoksa DENETIM YALAN SOYLER. Carpisma
        denetleyicisi ardisik iki adim arasini DUZ CIZGI sayiyor. Buyuk
        bir heading degisimini tek adimda yazarsak, 26 m arayla duran
        ucaklar "merkezden gecerek" karsi tarafa gidiyormus gibi gorunur
        ve 0.69 m'lik sahte bir ihlal cikar (bu yasandi).
        Gercekte oyle olmuyor: `path_planner._step_heading_deg` heading'i
        `max_heading_slew_deg_s` ile RAMPALIYOR, saf rotasyonda da
        `_yay_kur` merkezi sabit tutup YAY cizdiriyor. Rijit donuste
        ucaklar arasi mesafe DEGISMEZ. Dilimleyince denetim bunu gorur ve
        geriye yalnizca GERCEK yaklasmalar kalir.

        Dilim acisi `DONUS_ROTASYON_ADIM_DEG` — `plan_kur_final._rotasyon`
        ile ayni sabit, ayni gerekce.
        """
        fark = (y1 - y0) % 360.0
        if fark > 180.0:
            fark -= 360.0
        n = max(1, int(round(abs(fark) / DONUS_ROTASYON_ADIM_DEG)))
        for i in range(1, n + 1):
            ara_y = (y0 + fark * i / n) % 360.0
            ara_m = (m0[0] + (m1[0] - m0[0]) * i / n,
                     m0[1] + (m1[1] - m0[1]) * i / n)
            if i == n:
                plan.append((etiket, ara_y,
                             _hedefler(ara_m, ara_y, irtifa, katman),
                             8.0))
            else:
                plan.append((f"{etiket} [{i}/{n}]", ara_y,
                             _hedefler(ara_m, ara_y, irtifa, katman),
                             False, DONUS_GECIS_R_M))

    plan = []
    plan.append(("kalkis — herkes KENDI yerinde (toplanma merdiveni)",
                 kalkis_yaw,
                 _hedefler(home, kalkis_yaw, kalkis_irtifa, toplanma), 5.0))

    merkez, yon = home, kalkis_yaw
    for qid, (qk, qd) in qr_ned:
        # `_on_navigate`: heading = merkezden QR'a bearing.
        yeni_yon = math.degrees(math.atan2(qd - merkez[1],
                                           qk - merkez[0])) % 360.0
        # `_anchor_nearest_to_qr` + `_okuyucu_indeks`: merkez, KAMERALI
        # ucak QR'in TAM ustune gelecek sekilde geri hesaplanir.
        kx, ky = slot_dunya((0.0, 0.0), yeni_yon, *ofs[kam])
        yeni_merkez = (qk - kx, qd - ky)
        # Seyir TOPLANMA MERDIVENI acikken yapiliyor; merdiven ancak
        # QR'da formasyon oturunca kalkiyor (`_maybe_formation_settled`).
        _gecis(plan, f"QR{qid}'e seyir ({merdiven[0]:.1f} m, katmanli)",
               merkez, yon, yeni_merkez, yeni_yon, float(merdiven[0]),
               katman=toplanma)
        merkez, yon = yeni_merkez, yeni_yon
        # QR ustunde merdiven kalkar: hepsi ayni okuma irtifasina iner.
        for j, alt in enumerate(merdiven, start=1):
            plan.append((f"QR{qid} okuma basamagi {j} ({alt:.1f} m)", yon,
                         _hedefler(merkez, yon, alt), 8.0))
        toplanma = 0.0

    son_alt = float(merdiven[-1])
    ev_yon = math.degrees(math.atan2(home[1] - merkez[1],
                                     home[0] - merkez[0])) % 360.0
    # RETURN_HOME faz 0: YERINDE yaw (merkez sabit) — `_donus_ilerlet`.
    _gecis(plan, "donus faz0 — yerinde yaw (merdiven kuruluyor)",
           merkez, yon, merkez, ev_yon, son_alt, katman=katman)
    # 🔴 faz 1 MERDIVEN, faz 2 EVE DONUS — 8 Eylul'de YER DEGISTIRDILER.
    # Eski sirada eve donus bacagi uc ucagi da AYNI irtifada tasiyordu ve
    # en yakin an TAMAMEN yerdeki dizilise bagliydi (ayni gun 3.83 / 2.56 /
    # 0.31 m olculdu). Finalde dizilisi hakem sectigi icin profil HER
    # dizilise dayanikli olmak zorunda: merdiven ONCE kuruluyor, donus
    # katmanli yapiliyor.
    plan.append(("faz1 dikey merdiven — YERINDE", ev_yon,
                 _hedefler(merkez, ev_yon, son_alt, katman=katman), 5.0))
    plan.append(("faz2 eve don — KATMANLI", ev_yon,
                 _hedefler(home, ev_yon, son_alt, katman=katman), 6.0))
    # faz 3 girisinde baslik KALKIS basligina doner: yine YERINDE rotasyon.
    _gecis(plan, "faz3 oncesi — kalkis basligina don",
           home, ev_yon, home, kalkis_yaw, son_alt, katman=katman)
    # faz 3/4: baslik KALKIS basligina doner -> diziliş geri gelir, herkes
    # kendi noktasinda. Son adimin hedefleri = INIS NOKTALARI (harita_yaz
    # bu adimi mavi noktalar olarak ciziyor).
    plan.append(("dagilma — herkes KENDI kalkis noktasina (katmanli)",
                 kalkis_yaw,
                 _hedefler(home, kalkis_yaw, son_alt, katman=katman), 8.0))
    plan.append(("inis oncesi — irtifalar esitlenir", kalkis_yaw,
                 _hedefler(home, kalkis_yaw, son_alt), 4.0))
    return plan


def plan_kur_final(t):
    """KANIT VİDEOSU — operatörün tarif ettiği tam dizi.

     1) çizgi dizilişi, batıya bakarak (lider kendi kalkış noktasında)
     2) 50 m BATI
     3) 23°'ye rotasyon (lider yerinde, takipçi yay çizer)
     4) 10 -> 20 m tırmanış
     5) 23° yönünde 40 m
     6) çizgi -> ÜÇGEN (ok başı) formasyon değişimi
     7) 30 m DOĞU — formasyon 23°'ye bakmaya devam eder (yan kayma)
     8) kalkış yönüne rotasyon
     9) ok başı -> ÇİZGİ formasyon değişimi
    10) ROLL 30° (lider sabit, takipçi yukarı)
    11) EVE dönüş — roll KORUNARAK, formasyon kalkış yönüne bakarak (yan kayma)
    12) 152°'ye rotasyon
    13) iniş

    LİDER HER ADIMDA VERİLEN NOKTADA: formasyon merkezi, liderin slot 0
    ofseti çıkarılarak geri hesaplanıyor. Formasyon değişiminde ofsetler
    değiştiği için merkez de kayar — lider yerinde kalır, hareket eden
    takipçidir. İstenen bu.
    """
    lider = LIDER
    l = t[lider]
    H = (l["pos_x"], l["pos_y"])
    lyaw = l["yaw_deg"]

    slot = {lider: 0}
    for i, did in enumerate([d for d in DRONELAR if d != lider], start=1):
        slot[did] = i

    def _hedefler(nokta, yon, formasyon, irtifa, roll=0.0):
        """Lider 'nokta'da ve 'irtifa'da; formasyon 'yon'a, 'roll' eğimli.

        Roll'un dz'si LİDERE göre sıfırlanır (egim_dz sürü merkezini sabit
        tutup lideri aşağı alıyor; operatör liderin alçalmasını istemedi).
        """
        ofs = formasyon_ofsetleri(formasyon, len(DRONELAR))
        h = math.radians(yon)
        o_i, o_s = ofs[0]
        merkez = (nokta[0] - (o_i * math.cos(h) + o_s * (-math.sin(h))),
                  nokta[1] - (o_i * math.sin(h) + o_s * math.cos(h)))
        dz = egim_dz(ofs, 0.0, roll)
        dz = [z - dz[0] for z in dz]          # lider referans: kendisi 0
        noktalar = [slot_dunya(merkez, yon, *o) + (irtifa + z,)
                    for o, z in zip(ofs, dz)]
        return {did: noktalar[slot[did]] for did in DRONELAR}

    def _rotasyon(plan, nokta, bas, son, formasyon, irtifa, roll=0.0):
        """bas -> son yönüne KISA taraftan, geçiş noktalarıyla dilimleyerek.

        Ara dilimlerde 5. eleman geçiş yarıçapı: uçak noktaya tam varmadan
        bir sonrakine geçer, yay durmadan akar (2 Ağustos'ta ölçüldü).
        """
        fark = (son - bas) % 360.0
        if fark > 180.0:
            fark -= 360.0
        n = max(1, int(round(abs(fark) / DONUS_ROTASYON_ADIM_DEG)))
        for i in range(1, n + 1):
            ara = (bas + fark * i / n) % 360.0
            if i == n:
                plan.append((f"rotasyon -> {ara:.0f}° tamam", ara,
                             _hedefler(nokta, ara, formasyon, irtifa, roll),
                             FINAL_MANEVRA_BEKLEME_S))
            else:
                plan.append((f"rotasyon {i}/{n} -> {ara:.0f}°", ara,
                             _hedefler(nokta, ara, formasyon, irtifa, roll),
                             False, DONUS_GECIS_R_M))

    # --- Noktalar (hepsi liderin izlediği yol) ------------------------------
    b = math.radians(FINAL_BATI_DEG)
    P1 = (H[0] + FINAL_BATI_M * math.cos(b), H[1] + FINAL_BATI_M * math.sin(b))
    y2 = math.radians(FINAL_YON2_DEG)
    P2 = (P1[0] + FINAL_MESAFE2_M * math.cos(y2),
          P1[1] + FINAL_MESAFE2_M * math.sin(y2))
    d = math.radians(FINAL_DOGU_DEG)
    P3 = (P2[0] + FINAL_DOGU_M * math.cos(d), P2[1] + FINAL_DOGU_M * math.sin(d))
    eve = (math.degrees(math.atan2(H[1] - P3[1], H[0] - P3[0])) + 360.0) % 360.0
    eve_m = math.hypot(H[0] - P3[0], H[1] - P3[1])
    print(f"    [final] eve dönüş bacağı {eve_m:.1f} m, gerçek yön {eve:.0f}° — "
          f"formasyon {lyaw:.0f}°'ye bakarken uçulacak "
          f"({(eve - lyaw + 180) % 360 - 180:+.0f}° yan kayma)")
    print(f"    [final] doğu bacağı 30 m, formasyon {FINAL_YON2_DEG:.0f}°'ye "
          f"bakarken uçulacak ({(FINAL_DOGU_DEG - FINAL_YON2_DEG):+.0f}° yan kayma)")

    C1 = "cizgi"
    C2 = FINAL_FORMASYON2
    # ILK ROTASYON — operator istemedi ama GEREKLI. Kalkis yonu (lyaw) neresi
    # olursa olsun bati bacagi icin formasyon 270'ye bakmali. Dizilisi dogrudan
    # 270'de kursaydik, ucaklar TEK ADIMDA lyaw -> 270 donerdi; OFFBOARD'da yaw
    # setpoint'i dogrudan gectigi icin bu yarim saniyelik bir savrulma olur
    # (31 Temmuz'da sahada "ani donus" diye goruldu). Dilimlenince yumusuyor.
    # Lider kalkisinda zaten batiya bakiyorsa bu rotasyon KENDILIGINDEN 1 dilime
    # duser, yani bedeli yok.
    plan = [
        (f"çizgi dizilişi (lider d{lider})", lyaw,
         _hedefler(H, lyaw, C1, FINAL_IRTIFA_M), FINAL_MANEVRA_BEKLEME_S),
    ]
    _rotasyon(plan, H, lyaw, FINAL_BATI_DEG, C1, FINAL_IRTIFA_M)
    plan += [
        (f"-> {FINAL_BATI_M:.0f} m BATI", FINAL_BATI_DEG,
         _hedefler(P1, FINAL_BATI_DEG, C1, FINAL_IRTIFA_M), FINAL_BEKLEME_S),
    ]
    _rotasyon(plan, P1, FINAL_BATI_DEG, FINAL_YON2_DEG, C1, FINAL_IRTIFA_M)
    plan.append((f"irtifa {FINAL_IRTIFA_M:.0f} -> {FINAL_IRTIFA2_M:.0f} m",
                 FINAL_YON2_DEG,
                 _hedefler(P1, FINAL_YON2_DEG, C1, FINAL_IRTIFA2_M),
                 FINAL_MANEVRA_BEKLEME_S))
    plan.append((f"-> {FINAL_MESAFE2_M:.0f} m (yön {FINAL_YON2_DEG:.0f}°)",
                 FINAL_YON2_DEG,
                 _hedefler(P2, FINAL_YON2_DEG, C1, FINAL_IRTIFA2_M),
                 FINAL_BEKLEME_S))
    plan.append(("formasyon: ÇİZGİ -> ÜÇGEN (ok başı)", FINAL_YON2_DEG,
                 _hedefler(P2, FINAL_YON2_DEG, C2, FINAL_IRTIFA2_M),
                 FINAL_MANEVRA_BEKLEME_S))
    plan.append((f"-> {FINAL_DOGU_M:.0f} m DOĞU (burun {FINAL_YON2_DEG:.0f}°'de)",
                 FINAL_YON2_DEG,
                 _hedefler(P3, FINAL_YON2_DEG, C2, FINAL_IRTIFA2_M),
                 FINAL_BEKLEME_S))
    _rotasyon(plan, P3, FINAL_YON2_DEG, lyaw, C2, FINAL_IRTIFA2_M)
    plan.append(("formasyon: ÜÇGEN -> ÇİZGİ", lyaw,
                 _hedefler(P3, lyaw, C1, FINAL_IRTIFA2_M),
                 FINAL_MANEVRA_BEKLEME_S))
    plan.append((f"ROLL {FINAL_ROLL_DEG:.0f}° (takipçi yukarı)", lyaw,
                 _hedefler(P3, lyaw, C1, FINAL_IRTIFA2_M, FINAL_ROLL_DEG),
                 FINAL_MANEVRA_BEKLEME_S))
    plan.append((f"-> EV (lider d{lider} kalkış noktası), roll KORUNARAK", lyaw,
                 _hedefler(H, lyaw, C1, FINAL_IRTIFA2_M, FINAL_ROLL_DEG),
                 FINAL_BEKLEME_S))
    _rotasyon(plan, H, lyaw, FINAL_INIS_YON_DEG, C1, FINAL_IRTIFA2_M,
              FINAL_ROLL_DEG)
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


def plan_kur_g2(t):
    """GÖZLEM UÇUŞU — kalk, 15 m git, kendi yerine dön.

    FORMASYON YOK. Her uçak KENDİ ölçülen konumundan yola çıkar, ortak yönde
    G2_MESAFE_M gider ve KENDİ kalkış noktasına döner. Yerdeki dizilim aynen
    korunur; slot ataması, formasyon merkezi, yeniden atama — hiçbiri yok.

    NEDEN FORMASYONSUZ (18 Ağustos, operatör kararı): bu uçuşun amacı sürü
    düğümlerini gözlemlemek ve **YKİ'nin uçurduğu formasyon ile düğümlerin
    hesapladığı formasyon ayrı şeyler**. `formation_node`'u besleyen şey bu
    plan değil, uçakta koşan form_yayinla.sh'ın bastığı FormationCommand
    (aynı gün ölçüldü). Dolayısıyla formasyonu plandan çıkarmak gözlem
    sorularından hiçbir şey eksiltmiyor, ama uçuşu kısaltıyor ve slot
    atamasıyla ilgili bütün riski ortadan kaldırıyor.

    ⚠️ BEDELİ: uçaklar arası ayrım artık YERDEKİ DİZİLİME eşit ve uçuş boyunca
    öyle kalır. Formasyonlu senaryolarda kod aralığı 12 m'ye açıyordu; burada
    açmıyor. Uçakları en az MIN_AYRIM_M kadar (tercihen 8+ m) ayrı diz —
    kuru test bunu denetliyor ve geçmezse görev başlamaz.

    Yön ortak ve LİDERİN bakışından alınır; uçaklar burunlarını hiç çevirmez,
    dönüşte geri geri gelirler. Böylece yaw dilimleme devreye girmez.
    """
    yon = t[LIDER]["yaw_deg"]
    h = math.radians(yon)

    baslangic = {did: (t[did]["pos_x"], t[did]["pos_y"], G2_IRTIFA_M)
                 for did in DRONELAR}
    ileri = {did: (p[0] + G2_MESAFE_M * math.cos(h),
                   p[1] + G2_MESAFE_M * math.sin(h),
                   G2_IRTIFA_M)
             for did, p in baslangic.items()}

    return [
        (f"kalkış noktasında otur ({G2_IRTIFA_M:.0f} m)", yon, baslangic, True),
        (f"-> {G2_MESAFE_M:.0f} m ileri (yön {yon:.0f}°)", yon, ileri,
         G2_BEKLEME_S),
        ("-> EV (herkes kendi kalkış noktasına)", yon, baslangic, True),
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
    # 22 Agustos 2026: TEK ucaktan N ucaga genellestirildi. Niyet degismedi —
    # her ucagin hedefi KENDI olculen x,y'si, yani yatayda yine HICBIR komut
    # yok. Tek uçaklı kullanim birebir ayni calisir (N=1).
    #
    # YON TEK SKALER: yurutucu bacak basina tek heading aliyor, ucak basina
    # ayri yon verilemiyor. DRONELAR[0]'in olculen yonu kullaniliyor; ucaklar
    # bir kez o yone doner ve test boyunca bir daha donmez.
    yon = t[DRONELAR[0]]["yaw_deg"]
    hedefler = {}
    for did in DRONELAR:
        d = t[did]
        hedefler[did] = (d["pos_x"], d["pos_y"], ASILI_IRTIFA_M)
    return [(f"ASILI DUR {ASILI_SURE_S:.0f}s (kaçınma testi)",
             yon, hedefler, ASILI_SURE_S)]


def plan_kur_irtifa(t):
    """MESH ~ GÖRELİ İRTİFA testi — üç eşit bacak, sonuncusu kontrol.

    Sabitlerin gerekçesi yukarıda (IRTIFA_TEST_*). Burada yalnız yapı:

      1) hepsi ÜST      -> TEMEL
      2) DRONELAR[0] ALÇAK, diğerleri ÜST  -> tek değişken: göreli irtifa
      3) hepsi ÜST      -> SÜRÜKLENME KONTROLÜ (1 ile aynı çıkmalı)

    YATAYDA HİÇBİR KOMUT YOK: hedef, her uçağın kendi ölçülen x,y'si.

    YÖN TEK SKALER — yürütücü bacak başına tek heading alıyor, uçak başına
    ayrı yön veremiyor. Bu yüzden ÜÇ BACAKTA DA AYNI yön kullanılıyor
    (DRONELAR[0]'ın ölçülen yönü): uçaklar bir kez o yöne döner ve test
    boyunca bir daha dönmez. Yani yön bir DEĞİŞKEN değil, sabit — irtifa
    ile karışmaz. Bacaklar farklı yön alsaydı her geçişte burun dönerdi ve
    anten yönelimi irtifayla birlikte değişip ölçümü kirletirdi.
    """
    yon = t[DRONELAR[0]]["yaw_deg"]
    alcalan = DRONELAR[0]

    def hedef(irtifa_alcalan):
        h = {}
        for did in DRONELAR:
            d = t[did]
            irt = irtifa_alcalan if did == alcalan else IRTIFA_TEST_UST_M
            h[did] = (d["pos_x"], d["pos_y"], irt)
        return h

    s = IRTIFA_TEST_SURE_S
    return [
        (f"TEMEL — hepsi {IRTIFA_TEST_UST_M:.0f} m, {s:.0f}s",
         yon, hedef(IRTIFA_TEST_UST_M), s),
        (f"İRTİFA FARKI — d{alcalan} {IRTIFA_TEST_ALCAK_M:.0f} m, "
         f"diğerleri {IRTIFA_TEST_UST_M:.0f} m, {s:.0f}s",
         yon, hedef(IRTIFA_TEST_ALCAK_M), s),
        (f"KONTROL — hepsi yine {IRTIFA_TEST_UST_M:.0f} m, {s:.0f}s "
         f"(temelle aynı çıkmalı)",
         yon, hedef(IRTIFA_TEST_UST_M), s),
    ]


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


# --- --senaryo manevra (GOREV 2 — sürüyü PILOT surer) ------------------------
# Bu senaryo digerlerinden farkli: PLAN YURUTULMEZ. Sürüyü ylp00'a takili
# ikinci kumanda surer (gorev2.md B1). Kosucunun rolu sartnamedeki YKI
# rolunun ta kendisi: baslat (arm+takeoff), izle, sonda indir.
#
# O zaman kuru test NEYI dogruluyor? Ucus sirasinda ULASILABILECEK
# geometrilerin ZARFINI:
#   * baslangic dizilisi ve slot ayrimlari (carpisma denetimi)
#   * EGIM ZARFI — +-MOD_TEST_EGIM_DEG'de slot basina dikey kayma
#   * YAW ZARFI  — formasyon donunce ayak izi
#   * INIS NOKTALARI — G2-K5: her ucak KENDI slotunun ustune iner
#
# 🔴 YATAY yolu GOSTEREMEZ ve gostermeye calismamali: hareket modunda
# merkezi pilot surer, kod sinirlamaz. Bunu sessizce gecmek haritayi
# oldugundan guvenli gosterirdi.
MANEVRA_IZLEME_S = 150.0     # arm+takeoff sonrasi pilota birakilan sure
MANEVRA_ZARF_PAY_M = 2.0     # ayak izi yaricapina guvenlik payi


def _manevra_slotlar(merkez, heading_deg, pitch_deg=0.0, roll_deg=0.0):
    """Verilen egim/heading'de drone_id -> (kuzey, dogu, irtifa).

    UCAKTAKI ZINCIRLE AYNI IKI FONKSIYON kullaniliyor:
      * GEO.compute_slot_offsets  -> mode_manager._publish_formation_command
      * KIN.apply_tilt            -> maneuver_mode._egik_ofsetler
    Kopya formul yazmak "ayni sabit iki yerde" kazasinin geometri hali olur.
    """
    n = len(DRONELAR)
    ofs = GEO.compute_slot_offsets(
        GEO.FORMATION_CIZGI, n, AYAR.MOD_ARALIK_M,
        math.radians(KANAT_ACISI_DEG))
    egik = KIN.apply_tilt(ofs, pitch_deg, roll_deg)
    h = math.radians(heading_deg)
    hedefler = {}
    for i, did in enumerate(DRONELAR):
        ox, oy, _ = ofs[i]
        kz = merkez[0] + ox * math.cos(h) - oy * math.sin(h)
        dg = merkez[1] + ox * math.sin(h) + oy * math.cos(h)
        hedefler[did] = (kz, dg, AYAR.MOD_TEST_IRTIFA_M + egik[i][2])
    return hedefler, ofs, egik


def _manevra_zarf_yaz(merkez, heading_ucak, heading_dizilis, heading_R, ofs):
    """Kuru testin asil ciktisi: ucusta ulasilabilecek geometrilerin zarfi."""
    e = AYAR.MOD_TEST_EGIM_DEG
    yaricap = max(math.hypot(o[0], o[1]) for o in ofs)

    print(f"\n  MANEVRA ZARFI — sürüyü PILOT surer, bu plan YURUTULMEZ")
    print(f"    formasyon     CIZGI, aralik {AYAR.MOD_ARALIK_M:.1f} m, "
          f"irtifa {AYAR.MOD_TEST_IRTIFA_M:.1f} m")
    print(f"    merkez        ({merkez[0]:+.1f},{merkez[1]:+.1f}) NED")
    print(f"    heading       {heading_ucak:.1f} deg  "
          f"(ucaklarin OLCULEN yaw ortalamasi — mode_manager kalkis "
          f"kapisinda")
    print(f"                  ayni fonksiyonla tohumluyor: "
          f"manual_kinematics.dairesel_ortalama_deg)")
    print(f"    ayak izi      yaricap {yaricap:.2f} m -> yaw ne olursa olsun "
          f"merkez cevresi {yaricap + MANEVRA_ZARF_PAY_M:.1f} m TEMIZ olmali")

    print(f"\n  EGIM ZARFI (cubuk ~%66 -> +-{e:.0f} deg)")
    for ad, p_deg, r_deg in (("ROLL ", 0.0, e), ("PITCH", e, 0.0)):
        egik = KIN.apply_tilt(ofs, p_deg, r_deg)
        dz = [g[2] for g in egik]
        yayilim = max(dz) - min(dz)
        detay = "  ".join(f"d{did} {z:+.2f}"
                          for did, z in zip(DRONELAR, dz))
        print(f"    {ad} {e:+.0f} deg   {detay}   yayilim {yayilim:.2f} m")
    print(f"      ^ CIZGI'de PITCH dz URETMEZ (butun slotlarin dx=0). "
          f"BU DOGRU DAVRANIS —")
    print(f"        merkez-kaymasi regresyonunun olcum noktasi (KARAR-11). "
          f"Havada")
    print(f"        pitch'te irtifa degisirse EGIM MATEMATIGI BOZUK demektir.")

    print(f"\n  🔴 YATAY ZARF — KOD SINIRLAMIYOR")
    print(f"    Hareket modunda merkezi PILOT surer: {AYAR.MOD_HIZ_MPS:.1f} m/s "
          f"x ucus suresi.")
    print(f"    {MANEVRA_IZLEME_S:.0f} s'de teorik "
          f"{AYAR.MOD_HIZ_MPS * MANEVRA_IZLEME_S:.0f} m. Bu plan yatay yolu "
          f"GOSTEREMEZ;")
    print(f"    harita yalniz BASLANGIC dizilisini ve INIS noktalarini "
          f"gosterir.")
    print(f"    Ucus alani sinirini OPERATOR ve PILOT tutar.")

    if heading_R < 0.0:
        print(f"\n  ⚠️  Telemetride yaw YOK — heading dizilisten turetildi "
              f"({heading_dizilis:.0f} deg).")
        print(f"    Ucak OLCULEN yaw kullanacak; ikisi tutmayabilir. "
              f"Ucaklar acikken KURU TEST TEKRARLANMALI.")
    elif heading_R < 0.9:
        print(f"\n  🔴 UCAKLARIN YAW'LARI DAGINIK (tutarlilik "
              f"{heading_R:.2f} < 0.90)")
        print(f"    Ortalama heading {heading_ucak:.0f} deg cikti ama bu "
              f"zayif bir ortalama — ucaklar")
        print(f"    ayni yone bakmiyor. Formasyon devir aninda beklenmedik "
              f"yerlesir.")
        print(f"    YAPILACAK: ucaklari ayni yone cevir, kuru testi TEKRARLA.")
    else:
        fark = abs((heading_dizilis - heading_ucak + 180.0) % 360.0 - 180.0)
        print(f"\n  heading tutarliligi {heading_R:.2f} — ucaklar ayni yone "
              f"bakiyor ✓")
        if fark > 20.0:
            print(f"    NOT: dizilis geometrisi {heading_dizilis:.0f} deg "
                  f"gosteriyor, yaw ortalamasi {heading_ucak:.0f} deg "
                  f"({fark:.0f} deg fark).")
            print(f"    Formasyon burunlarin baktigi yone gore kurulacak — "
                  f"beklenen buysa sorun yok.")


def plan_kur_manevra(t):
    """Gorev 2 manevra testinin ZARFINI kurar (yurutulmez, dogrulanir).

    Adimlar ucusun sirasi DEGIL, ulasilabilecek uc noktalar: kuru test her
    ikisi arasinda carpisma denetimi yapsin diye. SON ADIM duz CIZGI ve
    baslangic heading'i — G2-K5 geregi INIS oraya, yani haritadaki mavi
    noktalar gercek inis yerleri.
    """
    konumlar = {did: (t[did]["pos_x"], t[did]["pos_y"]) for did in DRONELAR}
    merkez = SEKANS.agirlik_merkezi(konumlar)
    heading_dizilis = SEKANS.otomatik_heading_deg(konumlar)
    # UCAGIN KULLANACAGI heading — B17 kapandiktan sonra (30 Agu):
    # mode_manager kalkis kapisi acilirken heading'i ucaklarin OLCULEN
    # yaw'inin DAIRESEL ortalamasindan tohumluyor. Kuru test AYNI
    # fonksiyonu cagiriyor, yani modellenen sey uculacak seyin ta kendisi.
    yawlar = [float(t[did].get("yaw_deg", 0.0)) for did in DRONELAR
              if "yaw_deg" in t[did]]
    if len(yawlar) == len(DRONELAR):
        heading_ucak, heading_R = KIN.dairesel_ortalama_deg(yawlar)
    else:
        # Telemetride yaw yok (temsili yerlesim / eski snapshot).
        # Dizilisten turetileni kullan ama GUVENME diye isaretle.
        heading_ucak, heading_R = heading_dizilis, -1.0

    e = AYAR.MOD_TEST_EGIM_DEG
    y = AYAR.MOD_TEST_YAW_DEG
    adimlar = [
        ("CIZGI kur (duz)",        heading_ucak,      0.0,  0.0),
        (f"ROLL +{e:.0f} deg",     heading_ucak,      0.0,   +e),
        (f"ROLL -{e:.0f} deg",     heading_ucak,      0.0,   -e),
        (f"PITCH +{e:.0f} deg",    heading_ucak,       +e,  0.0),
        (f"YAW +{y:.0f} deg",      heading_ucak + y,  0.0,  0.0),
        ("DUZLE + INIS HAZIR",     heading_ucak,      0.0,  0.0),
    ]
    plan = []
    ofs = None
    for etiket, hd, p_deg, r_deg in adimlar:
        hedefler, ofs, _ = _manevra_slotlar(merkez, hd, p_deg, r_deg)
        plan.append((f"{etiket} [PILOT]", hd, hedefler, True))

    _manevra_zarf_yaz(merkez, heading_ucak, heading_dizilis, heading_R, ofs)
    return plan


def _manevra_izle(kuru: bool, kalan) -> int:
    """Sürüyü PILOT surerken YKI tarafindan izleme + sonda inis.

    Buradan HICBIR hareket komutu cikmaz — sartname 5.2'nin istedigi tam
    bu: gorev basladiktan sonra YKI mudahalesi YASAK. Kosucu yalnizca
    kalkisi verir, izler ve sure dolunca indirir.
    """
    print(f"\n=== SURU PILOTUN — {MANEVRA_IZLEME_S:.0f} s izlenecek, "
          f"YKI'den HAREKET KOMUTU GONDERILMEZ ===")
    print("    pilot: SwA emniyet ac -> SwB mod -> cubuklar. "
          "Kill pilotlari tetikte.")
    t0 = time.time()
    while time.time() - t0 < MANEVRA_IZLEME_S:
        time.sleep(1.0)
        if kalan() < 40:
            print(f"\n    GOREV SURE TAVANI ({kalan():.0f}s) — iniliyor")
            break
        try:
            t = durum()
        except RuntimeError as e:
            print(f"\n    UYARI: telemetri kesildi ({e}) — sürüyü pilot "
                  f"surmeye devam eder, izleme sayacla surer")
            continue
        gecen = time.time() - t0
        irt = "  ".join(
            f"d{d}:{-t[d].get('pos_z', 0.0):.1f}m" for d in DRONELAR if d in t)
        print(f"\r    t+{gecen:5.1f}s  {irt}   ", end="", flush=True)
    print()
    indir(kuru)
    return 0


# --- --senaryo formasyon_gecis (GECICI — 28 Agustos) -------------------------
# CIZGI -> OKBASI -> V gecis testi. GECISLER BU BETIKTEN GONDERILMEZ:
# tarif kaynagi ucaktaki formasyon_sekans_node (suru_dugumleri: `sekans`),
# tetigi guided ARM'in urettigi EVENT_MISSION_STARTED. Bu betigin rolu
# yalnizca sartnamedeki YKI rolu: baslat (arm+takeoff), izle, sonda indir.
# Kuru modda ise ucagin ucacagi geometriyi AYNI cekirdek fonksiyonlariyla
# kurup dogrular ve haritaya cizer.
SEKANS_IZLEME_PAY_S = 20.0   # sekans suresi ustune izleme payi (kalkis
#                              kapisi gecikmesi + faz gecis beklemeleri)


def plan_kur_formasyon_gecis(t):
    """Sekansin faz hedeflerini UCAKTAKI cekirdekle birebir ayni kurar.

    Girdi gercek konumlar (telemetri) — sekans dugumunun t0'da gorecegi
    konumlarin yerdeki hali. Merkez, heading ve slot atamasi ayni
    fonksiyonlardan geldigi icin dogrulanan/haritalanan geometri ile
    uculacak geometri ozdes. Son fazin slotlari ayni zamanda INIS
    NOKTALARI — harita onlari mavi cizer, operator gozle dogrular.
    """
    konumlar = {did: (t[did]["pos_x"], t[did]["pos_y"]) for did in DRONELAR}
    merkez = SEKANS.agirlik_merkezi(konumlar)
    heading = SEKANS.otomatik_heading_deg(konumlar)
    fazlar = SEKANS.faz_plani(list(AYAR.SEKANS_FAZLAR),
                              list(AYAR.SEKANS_FAZ_SURE_S))
    print(f"\n  sekans merkezi ({merkez[0]:+.1f},{merkez[1]:+.1f}) NED, "
          f"heading {heading:.1f}° (kalkis diziliminden turetildi — ucak da "
          f"ayni kurali kosacak)")
    plan = []
    poz = dict(konumlar)
    # Atama BIR KEZ, ILK FAZDA (Macar, kalkis konumlarindan); slot INDEKSI
    # sonraki fazlara aynen tasinir — dugumle birebir ayni kural, gerekce
    # ve iki basarisiz onceki deneme: formasyon_sekans_cekirdek.faz_ofsetleri.
    sabit_ids = None
    for i, ((tip, sure), ad) in enumerate(zip(fazlar, AYAR.SEKANS_FAZLAR)):
        if sabit_ids is None:
            sabit_ids, ofsetler = SEKANS.atama(
                tip, konumlar, merkez, heading,
                AYAR.SEKANS_ARALIK_M, KANAT_ACISI_DEG)
        else:
            ofsetler = SEKANS.faz_ofsetleri(
                tip, len(sabit_ids), AYAR.SEKANS_ARALIK_M, KANAT_ACISI_DEG)
        ids = sabit_ids
        dunya = SEKANS.dunya_konumlari(ids, ofsetler, merkez, heading)
        hedefler = {did: (dunya[did][0], dunya[did][1],
                          AYAR.SEKANS_IRTIFA_M) for did in DRONELAR}
        # FAZ SURESI BU YERLESIME YETIYOR MU — 25/25/25 karari (28 Agu)
        # korlemesine pay yerine bu olcume dayaniyor: en uzun yol / faz
        # hizi + oturma payi. Yetmiyorsa guvenlik sorunu DEGIL (gecis o
        # anki konumdan yeniden atanir, kacinma aktif) ama formasyon tam
        # oturmadan morph baslar — operator bilerek ucsun ya da ucaklari
        # daha toplu koysun / SEKANS_FAZ_SURE_S'i buyutsun.
        hiz = (AYAR.SEKANS_KURULUM_HIZ_MPS if i == 0
               else AYAR.SEKANS_GECIS_HIZ_MPS)
        en_uzun = max(math.hypot(dunya[d][0] - poz[d][0],
                                 dunya[d][1] - poz[d][1])
                      for d in DRONELAR)
        # SVT rampasi tam hizda gitmez; 0.7 etkin-hiz carpani + 6 s oturma
        # (YERLESME_S ile ayni mertebe) muhafazakar bir kestirim.
        tahmin = en_uzun / max(0.1, 0.7 * hiz) + 6.0
        isaret = "" if tahmin <= sure else "  ⚠️ SUREYE SIGMIYOR"
        print(f"  faz {ad:<7} en uzun yol {en_uzun:5.1f} m  ~{tahmin:4.0f} s"
              f"  (butce {sure:.0f} s){isaret}")
        if tahmin > sure:
            print(f"    UYARI: {ad} fazi {sure:.0f} sn'ye sigmayabilir — "
                  f"ucaklari birbirine yakin koy ya da SEKANS_FAZ_SURE_S "
                  f"buyut (ucus_ayarlari.py). Guvenlik sorunu degil, "
                  f"formasyon tam oturmadan sonraki faz baslar.")
        plan.append((f"{ad.upper()} formasyonu ({sure:.0f} s) [UCAKTA]",
                     heading, hedefler, True))
        poz = {did: dunya[did] for did in DRONELAR}
    # EVE DONUS (operator istegi, 28 Agu): her ucak KENDI kalkis noktasina.
    # PX4 RTL DEGIL — HOME kaymasi P0. Atama SABIT (herkes kendi yerine),
    # Macar yok; plan_dogrula V->EVE yollarinin kesisip kesismedigini
    # OLCUYOR — kesisiyorsa SONUC: KALDI der ve ucaklar yeniden dizilir.
    eve_hedefler = {did: (konumlar[did][0], konumlar[did][1],
                          AYAR.SEKANS_IRTIFA_M) for did in DRONELAR}
    en_uzun = max(math.hypot(eve_hedefler[d][0] - poz[d][0],
                             eve_hedefler[d][1] - poz[d][1])
                  for d in DRONELAR)
    tahmin = en_uzun / max(0.1, 0.7 * AYAR.SEKANS_GECIS_HIZ_MPS) + 6.0
    isaret = "" if tahmin <= AYAR.SEKANS_EVE_SURE_S else "  ⚠️ SUREYE SIGMIYOR"
    print(f"  faz eve     en uzun yol {en_uzun:5.1f} m  ~{tahmin:4.0f} s"
          f"  (butce {AYAR.SEKANS_EVE_SURE_S:.0f} s){isaret}")
    plan.append((f"EVE DONUS ({AYAR.SEKANS_EVE_SURE_S:.0f} s) [UCAKTA]",
                 heading, eve_hedefler, True))
    return plan


def _formasyon_gecis_izle(kuru: bool, kalan) -> int:
    """Sekans ucakta akarken YKI tarafindan IZLEME + sonda inis.

    Buradan HICBIR gecis komutu cikmaz — sartname provasi tam da bu: YKI
    baglantisi kesilse sekans ucakta surer, kaybedilen tek sey bu ekrandaki
    izleme ve otomatik inis komutu olur (kumanda/QGC her zaman elde).

    Inis GUVENLIGI: butun fazlarin slotlari kuru testte dogrulandi ve
    haritada gosterildi; sekans hangi fazda donarsa donsun ucaklar
    onceden onaylanmis bir dizilisin ustunde asilidir — "suresi doldu,
    oldugu yerde indir" bu yuzden guvenli. Normal akista son faz EVE:
    ucaklar KENDI kalkis noktalarinin ustunde ve inis oraya olur.
    """
    toplam = (sum(AYAR.SEKANS_FAZ_SURE_S) + AYAR.SEKANS_EVE_SURE_S
              + SEKANS_IZLEME_PAY_S)
    sinirlar = []
    biriken = 0.0
    for ad, sure in zip(AYAR.SEKANS_FAZLAR, AYAR.SEKANS_FAZ_SURE_S):
        biriken += sure
        sinirlar.append((biriken, ad))
    biriken += AYAR.SEKANS_EVE_SURE_S
    sinirlar.append((biriken, 'eve'))
    print(f"\n=== SEKANS UCAKTA KOSUYOR — {toplam:.0f} s izlenecek, "
          f"gecis komutu YKI'den GONDERILMEZ ===")
    print("    beklenen akis: " + "  ".join(
        f"{ad}<= t0+{s:.0f}s" for s, ad in sinirlar))
    t0 = time.time()
    uyari_t = 0.0
    while time.time() - t0 < toplam:
        time.sleep(1.0)
        gecen = time.time() - t0
        if kalan() < 40:
            print(f"\n    GOREV SURE TAVANI ({kalan():.0f}s) — iniliyor")
            break
        try:
            t = durum()
        except RuntimeError as e:
            # YKI telemetrisi koptu diye inis komutu YOLLANMAZ (zaten
            # ulasmazdi) — sekans ucakta surer, biz sayacla bekleriz.
            print(f"\n    UYARI: telemetri kesildi ({e}) — sekans ucakta "
                  f"surer, izleme sayacla devam ediyor")
            continue
        ihlal = guvenlik_ihlali(t)
        if ihlal:
            print(f"\n    !!! {ihlal} — gorev durduruluyor")
            indir(kuru)
            return 1
        pilot = [d for d in ucanlar()
                 if t.get(d, {}).get("flight_mode", 0) in _PILOT_MODLARI]
        if pilot:
            print(f"\n    !!! drone {pilot} PILOT KONTROLUNDE — "
                  f"gorev durduruluyor")
            indir(kuru)
            return 1
        # En yakin cift — kacinmanin isini YKI'den bolme: 4 m alti gorulse
        # bile inis komutu GONDERILMEZ (CA dikey yol veriyor; o anda inise
        # zorlamak katmani bozar). Yalniz yuksek sesle soylenir.
        cift = ""
        if len(DRONELAR) >= 2:
            en_kucuk, en_cift = float("inf"), ""
            for a, b in itertools.combinations(DRONELAR, 2):
                da, db = t.get(a), t.get(b)
                if da is None or db is None:
                    continue
                m = math.dist(
                    (da["pos_x"], da["pos_y"], da.get("alt_m", 0.0)),
                    (db["pos_x"], db["pos_y"], db.get("alt_m", 0.0)))
                if m < en_kucuk:
                    en_kucuk, en_cift = m, f"d{a}-d{b}"
            if en_kucuk < float("inf"):
                cift = f"  en yakin {en_cift}={en_kucuk:.1f}m"
                if (en_kucuk < MIN_AYRIM_M
                        and time.time() - uyari_t > 3.0):
                    uyari_t = time.time()
                    print(f"\n    UYARI: {en_cift} = {en_kucuk:.2f} m "
                          f"< {MIN_AYRIM_M:.1f} m — kacinma calisiyor "
                          f"olmali (dikey ayrima bak); inis komutu "
                          f"bilerek GONDERILMIYOR")
        faz = next((ad for s, ad in sinirlar if gecen <= s), "bitti/inis")
        irtifalar = "  ".join(
            f"d{d}={t.get(d, {}).get('alt_m', 0.0):.1f}m"
            for d in ucanlar())
        print(f"    t0+{gecen:5.0f}s  beklenen faz: {faz:<7} "
              f"{irtifalar}{cift}", end="\r")
    else:
        print(f"\n    sekans penceresi doldu ({toplam:.0f} s)")
    print("    Not: formasyon hic kurulmadiysa once suna bak: uc ucakta da "
          "suru_dugumleri icinde `sekans` var mi; sonra mesh_diag "
          "form_tx/form_rx/form_lider_degil sayaclari.")
    indir(kuru)
    return 0


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


# TURETILIR, sabit degil: MPC_TILTMAX_AIR + pay. Eskiden 35.0 sabitti ve
# yorumunda "MPC_TILTMAX_AIR=30" varsayimi vardi; ylp00'da 45 cikti.
MAKS_EGIM_DEG = AYAR.MAKS_EGIM_DEG


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
    elif _SENARYO == "saha":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — saha senaryosu lider "
                  "konum ölçümüne dayanır, başlatılamaz.")
            return 1
        # Noktalar GPS olarak tutuluyor; NED'e cevirme ancak telemetri
        # gelince (origin bilinince) yapilabilir — bu yuzden tam burada.
        if not _saha_coz(t, kuru):
            return 1
        plan = plan_kur_saha(t)
    elif _SENARYO == "gorev1":
        plan = plan_kur_gorev1(t)
    elif _SENARYO == "final":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — final senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_final(t)
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
    elif _SENARYO == "g2":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — g2 senaryosu konum ve "
                  "yön ölçümüne dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_g2(t)
    elif _SENARYO == "asili":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — asılı senaryosu ölçülen "
                  "konuma dayanır, başlatılamaz.")
            return 1
        plan = plan_kur_asili(t)
    elif _SENARYO == "irtifa":
        eksik = [d for d in DRONELAR if d not in t]
        if eksik:
            print(f"Telemetride yok: drone {eksik} — irtifa senaryosu her "
                  "uçağın ÖLÇÜLEN konumuna dayanır, başlatılamaz.")
            return 1
        if len(DRONELAR) < 2:
            print("irtifa senaryosu EN AZ İKİ uçak ister — ölçülen şey iki "
                  "uçak ARASINDAKİ linkin göreli irtifaya duyarlılığı. "
                  "Örnek: --dronelar 1,3")
            return 1
        plan = plan_kur_irtifa(t)
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
    elif _SENARYO == "manevra":
        eksik = [d for d in DRONELAR if d not in t]
        if not eksik:
            plan = plan_kur_manevra(t)
        elif kuru:
            # formasyon_gecis ile ayni kalip: YKI kapaliyken plan YAPISI
            # denetlenebilsin, ama harita UCULACAK geometri DEGIL.
            print("\n[KURU] telemetri yok — TEMSILI yerlesim varsayildi. "
                  "Harita ve dogrulama GERCEK DEGIL; sahada ucaklar "
                  "acikken KURU TEST TEKRARLANMADAN UCULMAZ.")
            _tems = {}
            for _i, _did in enumerate(DRONELAR):
                _tems[_did] = {"pos_x": merkez0[0],
                               "pos_y": merkez0[1] + AYAR.MOD_ARALIK_M * _i}
            plan = plan_kur_manevra(_tems)
        else:
            print(f"Telemetride yok: drone {eksik} — manevra senaryosu "
                  "gercek konumlara dayanir, baslatilamaz.")
            return 1
    elif _SENARYO == "formasyon_gecis":
        eksik = [d for d in DRONELAR if d not in t]
        if not eksik:
            plan = plan_kur_formasyon_gecis(t)
        elif kuru:
            # YKI kapaliyken plan YAPISI denetlenebilsin (tekli ile ayni
            # kalip). Uyari yuksek sesle: heading/merkez/atama GERCEK
            # konumdan turetiliyor, temsili yerlesimle cikan harita
            # UCULACAK geometri DEGIL.
            print("\n[KURU] telemetri yok — TEMSILI rastgele yerlesim "
                  "varsayildi. Harita ve dogrulama GERCEK DEGIL; sahada "
                  "ucaklar acikken KURU TEST TEKRARLANMADAN UCULMAZ.")
            _temsili = {}
            for _i, _did in enumerate(DRONELAR):
                _aci = 2.0 * math.pi * _i / max(1, len(DRONELAR)) + 0.7
                _temsili[_did] = {
                    "pos_x": merkez0[0] + 9.0 * math.cos(_aci) * (1 + _i % 2),
                    "pos_y": merkez0[1] + 9.0 * math.sin(_aci),
                }
            plan = plan_kur_formasyon_gecis(_temsili)
        else:
            print(f"Telemetride yok: drone {eksik} — formasyon_gecis "
                  "senaryosu gercek konumlara dayanir, baslatilamaz.")
            return 1
    else:
        plan = plan_kur(merkez0, baslangic)
    plan_yaz(plan)
    ayak_izi_yaz(plan, merkez0)
    _org = _origin_bul(t)
    koordinat_yaz(plan, merkez0, _org)
    if _HARITA_DOSYA:
        if _SENARYO == "formasyon_gecis":
            harita_yaz_sekans(plan, _org, _HARITA_DOSYA, t)
        else:
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
                  else SAHA_IRTIFA_M if _SENARYO == "saha"
                  else FINAL_IRTIFA_M if _SENARYO == "final"
                  else DONUS_IRTIFA_M if _SENARYO == "donus"
                  else TAKIP_IRTIFA_M if _SENARYO == "takip"
                  else G2_IRTIFA_M if _SENARYO == "g2"
                  else ASILI_IRTIFA_M if _SENARYO == "asili"
                  else IRTIFA_TEST_UST_M if _SENARYO == "irtifa"
                  else TEKLI_IRTIFA_M if _SENARYO == "tekli"
                  else FORMASYON_TEST_IRTIFA_M if _SENARYO in ("formasyon", "lider")
                  else AYAR.SEKANS_IRTIFA_M if _SENARYO == "formasyon_gecis"
                  else AYAR.MOD_TEST_IRTIFA_M if _SENARYO == "manevra"
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
        # PENCERE 5.0 IDI VE HER UCUSTA KISA GELDI. Iki dronlu ucuslarin
        # ikisinde de log "deneme 1 ... deneme 2 ... tirmanis basladi" dedi ve
        # hemen ardindan ucaklar 5.2 / 3.1 m'de olcuIdu — yani ILK komut
        # calismisti, biz goremiyorduk. Gecikmeler toplaniyor: drone tarafinda
        # dikey ivme rampasi (1.0 m/s^2), mesh komut gecikmesi, 0.5 sn
        # ornekleme ve telemetri gecikmesi. Ucak zamaninda tirmanirsa dongu
        # ZATEN erken cikiyor, yani uzatmanin bedeli yok; kazanci gereksiz
        # ikinci komutun kalkmasi (TIP_KOMUT 200 ms sinirini iki drone
        # PAYLASIYOR — 1 Agustos'ta bir ucak bu yuzden armli yerde kaldi).
        while time.time() - t0 < 9.0:
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
            # IRTIFA OFSETI UCAK BASINA — 2 Agustos'ta tek ORTALAMA skalerdi
            # ve bir ucusu askida biraktı.
            #
            # OLCULDU (ylp00 + ylp02, ayni kalkis, ikisine de 8.0 m komutu):
            #   d3 -> alt_m 7.98  (hedefe 0.03 m, kusursuz)
            #   d1 -> alt_m 6.50  (hedefe 1.50 m, TOLERANS_M=1.0'in disinda)
            # Iki ucagin z referansi ~1.5 m farkli: d1'in kopru tarafindaki
            # kalkis capasi "8.0m -> NED z=-9.4" derken mesh'teki yer kotu
            # -0.10 idi. Sebebi ne olursa olsun (EKF origin farki, home kotu),
            # bunu TEK ortalama ile kapatmak matematiksel olarak imkansiz:
            # ortalama (7.98+6.50)/2-8.0 = -0.76 cikar, ikisini de yanlis yere
            # koyar. d1 hicbir zaman 1.0 m icine giremez, git_ve_bekle "vardi"
            # diyemez ve gorev ADIM 1'DE SONSUZA KADAR BEKLER — sahada aynen
            # bu oldu, operator elle indirdi.
            #
            # Ucak basina ofset her ucagi KENDI olculen irtifasina sabitler:
            # hedef = komut edilen irtifa + (o ucagin olculeni - komut edilen)
            #       = o ucagin olculen irtifasi. Yani "bulundugun yerde kal"
            # ve sonraki adimlarda ayni bagil fark korunur. Formasyonun DIKEY
            # gecerliligi bundan etkilenmez: roll/tirmanis adimlari zaten bagil
            # (v[2] her ucak icin ayni miktarda degisiyor).
            ofset = {d: t[d]["alt_m"] - kalkis_irt for d in ucanlar()}
            buyuk = {d: o for d, o in ofset.items() if abs(o) > 0.15}
            if buyuk:
                print("    irtifa ofseti (uçak başına, zemin/EKF farkı): "
                      + "  ".join(f"d{d}={o:+.2f}m" for d, o in sorted(ofset.items()))
                      + " — plana ekleniyor")
                # 5. eleman (gecis yaricapi) KORUNUR — dusurulurse ara
                # noktalar tekrar "tam varis" bekler ve yay taksitlenir.
                plan = [(a[0], a[1],
                         {k: (v[0], v[1], v[2] + ofset.get(k, 0.0))
                          for k, v in a[2].items()}, *a[3:])
                        for a in plan]
            break
        print("    ... " + "  ".join(f"d{d}={t.get(d,{}).get('alt_m',0.0):.1f}m"
                                     for d in ucanlar()), end="\r")
    else:
        print("\n    KALKIŞ ZAMAN AŞIMI — iniliyor")
        indir(kuru)
        return 1

    # --- formasyon_gecis: plan YURUTULMEZ, izlenir --------------------------
    # Gecisleri ucaktaki formasyon_sekans_node veriyor (guided ARM'in
    # urettigi EVENT_MISSION_STARTED ile tetiklendi, kadro irtifaya cikinca
    # basladi). Asagidaki genel yurutucu goto gonderir — o yuzden bu
    # senaryoda HIC girilmez; formasyon-surer modda mesh goto zaten ucaga
    # ulasmaz (SP_REMAP), ama gondermek kaydi kirletir ve niyeti bulandirir.
    if _SENARYO == "formasyon_gecis":
        return _formasyon_gecis_izle(kuru, kalan)

    # --- manevra: plan YURUTULMEZ, sürüyü PILOT surer -----------------------
    # Sartname 5.2: gorev basladiktan sonra YKI mudahalesi YASAK. Asagidaki
    # genel yurutucu goto gonderirdi; bu senaryoda HIC girilmez.
    if _SENARYO == "manevra":
        return _manevra_izle(kuru, kalan)

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
            #
            # HEDEF DE TEKRARLANIR — 21 Agustos 2026'da ucusta OLCULDU.
            #
            # Eskiden burada komut GONDERILMIYORDU; gerekce "setpoint'i drone
            # kendi tazeliyor (esp32_bridge 10 Hz yerel tekrar)" idi. Dogru
            # ama EKSIK: yerel tekrar ancak `_guided_hedef` bir kez KURULMUSSA
            # calisir, o da en az bir `goto` cercevesinin ulasmasini ister.
            #
            # `--senaryo asili`de hedef ucagin KENDI konumu, yani git_ve_bekle
            # daha ilk turda "vardi" deyip cikiyor ve `git()` HIC cagrilmiyor.
            # Olculdu (21 Agustos, asili ucusu): esp.log'da o ucus boyunca
            # goto sayisi SIFIR; collision_avoidance'in passthrough sayaci
            # 181'de dondu ve `avoid=0` kaldi. Yani kacinma calismadigi icin
            # degil, GIRDISI OLMADIGI icin sinanamadi.
            #
            # 🔴 BU YALNIZ TEST KUSURU DEGIL: kacinma dugumu /raw ile
            # /setpoint arasinda bir FILTRE. Akis kesilince filtreleyecek bir
            # sey kalmiyor ve px4_bridge kalkis capasiyla konumu kendi
            # tutuyor — yani HER bekleme evresinde carpisma onleme ATIL.
            # Formasyonda "hedefe varildi, bekle" evreleri var; orada da ayni
            # boslugun olusmamasi icin tekrar buraya kondu.
            #
            # Maliyeti yok: ayni hedef tekrar gonderiliyor, px4_bridge zaten
            # 50 Hz'de kendi yurutuyor ve kaybolan paket ayni hedefi tasiyor.
            _bekle_basla = time.time()
            while time.time() - _bekle_basla < bekle_s:
                time.sleep(min(0.5, bekle_s))
                _t = durum()
                for _did in ucanlar():
                    _h = hedefler.get(_did)
                    if _h is not None:
                        git(_did, _h, heading, kuru, _t)
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
    ap.add_argument("--mesafe", type=float, default=None,
                    metavar="M",
                    help="g2 senaryosunda ileri gidilecek mesafe (m). "
                         "Kayma olcumu icin >=40 m ister "
                         "(docs/PLAN.md §9).")
    ap.add_argument("--irtifa", type=float, default=None,
                    help="--senaryo asili icin kalkis/asili irtifasi (m); "
                         "--senaryo irtifa icin UST irtifa; g2 icin ucus irtifasi")
    ap.add_argument("--aralik", type=float, default=None,
                    help="Formasyon araligi (m) — senaryonun sabitini EZER. "
                         "🔴 KUMANDADAN formasyon ucusunu kuru test etmek "
                         "icin ZORUNLU: ucakta gecerli olan aralik "
                         "MOD_ARALIK (ucus_ayarlari) ama formasyon_gecis "
                         "senaryosu SEKANS_ARALIK ile plan kuruyordu, yani "
                         "dogrulanan geometri ile uculan geometri AYRI "
                         "olabiliyordu (31 Agustos'ta fark edildi). "
                         "Or: --senaryo formasyon_gecis --aralik 9")
    ap.add_argument("--alcak", type=float, default=None,
                    help="--senaryo irtifa: 2. bacakta ALCALAN ucagin "
                         "irtifasi (m). Alcalan ucak = --dronelar listesinin "
                         "ILKI. Varsayilan 5 m.")
    ap.add_argument("--kacinma", action="store_true",
                    help="carpisma kacinmasi ACIK (drone'da /ws/kacinma var). "
                         "Kacis kesicisinin marjini genisletir, yoksa kesici "
                         "kacinma manevrasini kacis sanip gorevi iptal eder.")
    ap.add_argument("--senaryo",
                    choices=("kanit", "test", "formasyon", "formasyon_gecis",
                             "manevra", "lider", "tekli",
                             "asili", "irtifa", "takip", "g2", "donus", "tam",
                             "final", "saha", "gorev1"),
                    default="kanit",
                    help="kanit = tam koreografi; test = kuzeybati/bekle/"
                         "irtifa/don; formasyon = rastgele yerlesimden cizgi "
                         "formasyonu kur ve in; formasyon_gecis = arm+takeoff "
                         "sonrasi CIZGI->OKBASI->V sekansi UCAKTA kosar "
                         "(formasyon_sekans dugumu), YKI yalniz izler ve "
                         "indirir; lider = lider YERINDE ASILI durur, "
                         "takipci onun sagina cizgi formasyonu kurup iner; "
                         "tekli = TEK ucak, kalkis yonunde 7 m, bekle, 5 m "
                         "tirman, bekle, in")
    ap.add_argument("--sahte", default=None, metavar="ID:K,D,YAW ...",
                    help="SAHADAN UZAKTA plan cizmek icin elle telemetri. "
                         "Or: --sahte '2:-27.11,3.32,222 3:-18.22,-13.53,310' "
                         "(kuzey, dogu metre; yaw pusula derecesi). "
                         "YALNIZ --kuru ile calisir.")
    ap.add_argument("--noktalar", default=None, metavar="K,D K,D ...",
                    help="--senaryo saha icin 5 nokta, NED metre. Or: "
                         "'-24.6,-2.4 -75.6,-21.5 -44.5,-38.5 -13.3,-54.1 "
                         "-4.0,-32.2'. GPS listesini DEVRE DISI birakir.")
    ap.add_argument("--noktalar-gps", default=None, metavar="LAT,LON ...",
                    help="--senaryo saha icin 5 nokta, ENLEM,BOYLAM. "
                         "nokta_sec.html'den kopyalanir. Verilmezse koddaki "
                         "SAHA_NOKTALAR_GPS kullanilir. NED'e cevirme ucus "
                         "aninda olculen origin ile yapilir.")
    ap.add_argument("--sahte-origin", default=None, metavar="LAT,LON",
                    help="--sahte ile: NED origin'i. Verilirse harita ve GPS "
                         "listesi de uretilir. Or: '38.6734220,39.1850585'")
    ap.add_argument("--lider", type=int, default=None,
                    help="--senaryo lider icin YERINDE ASILI duracak drone (or. 2)")
    ap.add_argument("--qr-tablo", dest="qr_tablo", default="",
                    metavar='"1:lat,lon;2:lat,lon"',
                    help="gorev1 senaryosu icin QR konum tablosu. "
                         "qr_enjekte.py ile AYNI sozdizimi — ucaklara "
                         "enjekte edilen metnin AYNISI verilmeli, yoksa "
                         "harita baska bir rotayi cizer.")
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
    global _KACINMA_ACIK, ASILI_SURE_S, ASILI_IRTIFA_M, _SAHTE_TELEMETRI
    global IRTIFA_TEST_UST_M, IRTIFA_TEST_ALCAK_M, IRTIFA_TEST_SURE_S
    global G2_MESAFE_M, G2_IRTIFA_M, ARALIK_M
    if a.sahte:
        # CANLI MODDA ASLA. Sahte konumla gercek komut gondermek, ucaklari
        # olmadiklari yere gore hesaplanmis hedeflere yollamak demektir —
        # 1 Agustos'taki cerceve ayrismasi kacisinin aynisi.
        if not a.kuru:
            ap.error("--sahte YALNIZ --kuru ile kullanilir "
                     "(canli ucusta sahte konum = kacis)")
        sahte_org = None
        if a.sahte_origin:
            try:
                la, _, lo = a.sahte_origin.partition(",")
                sahte_org = (float(la), float(lo))
            except ValueError:
                ap.error("--sahte-origin 'LAT,LON' olmali")
        try:
            _SAHTE_TELEMETRI = _sahte_ayristir(a.sahte, sahte_org)
        except ValueError as e:
            ap.error(str(e))
    _KACINMA_ACIK = a.kacinma
    if a.noktalar and a.noktalar_gps:
        ap.error("--noktalar ve --noktalar-gps birlikte kullanilamaz")
    if a.noktalar:
        try:
            n = [tuple(float(x) for x in p.split(",")) for p in a.noktalar.split()]
        except ValueError:
            n = []
        if len(n) != 5 or any(len(x) != 2 for x in n):
            ap.error("--noktalar TAM 5 tane 'kuzey,dogu' cifti ister")
        SAHA_NOKTALAR[:] = n
        # NED dogrudan verildi: GPS listesi devrede kalirsa _saha_coz onu
        # ucus aninda EZER ve operatorun verdigi noktalar kaybolur.
        SAHA_NOKTALAR_GPS.clear()
    if a.noktalar_gps:
        try:
            g = [tuple(float(x) for x in p.split(","))
                 for p in a.noktalar_gps.split()]
        except ValueError:
            g = []
        if len(g) != 5 or any(len(x) != 2 for x in g):
            ap.error("--noktalar-gps TAM 5 tane 'enlem,boylam' cifti ister")
        if any(not (-90 <= la <= 90) or not (-180 <= lo <= 180) for la, lo in g):
            ap.error("--noktalar-gps: enlem/boylam araligi disinda")
        SAHA_NOKTALAR_GPS[:] = g
    if a.sure is not None:
        ASILI_SURE_S = a.sure
        # irtifa senaryosunda --sure BACAK BASINA suredir ve ucu de ayni
        # degeri alir. Esit pencere sart: farkli surelerde "maksimum bosluk"
        # ornek sayisiyla siser ve fazlar kiyaslanamaz hale gelir.
        IRTIFA_TEST_SURE_S = a.sure
    if a.irtifa is not None:
        # --irtifa uc senaryoda gecerli: asili (tek ucak), g2 ve irtifa.
        # g2'nin sabiti 20 m idi ve override yoktu; kisa dogrulama
        # ucuslarinda (or. lider secimi olcumu) daha alcak istenebiliyor.
        if a.senaryo == "g2":
            if not 3.0 <= a.irtifa <= 30.0:
                ap.error("--irtifa g2 icin 3..30 m araliginda olmali")
            G2_IRTIFA_M = a.irtifa
        elif a.senaryo == "irtifa":
            if not 3.0 <= a.irtifa <= 30.0:
                ap.error("--irtifa 3..30 m araliginda olmali")
            IRTIFA_TEST_UST_M = a.irtifa
        else:
            ASILI_IRTIFA_M = a.irtifa
    if a.aralik is not None:
        # 🔴 NEDEN VAR (31 Agustos 2026): kumandadan formasyon ucusunda
        # gecerli aralik MOD_ARALIK_M, ama hicbir kuru test senaryosu onu
        # kullanmiyordu — formasyon_gecis SEKANS_ARALIK_M (7 m),
        # formasyon ise ARALIK_M (12 m) ile plan kuruyor. Yani
        # "kuru test GECTI" demek uculacak geometrinin gectigi anlamina
        # GELMIYORDU. Bu bayrak o boslugu kapatiyor.
        #
        # Alt sinir MIN_AYRIM_M: daha darinda durgun formasyon bile
        # carpisma esiginin altinda kalir, plan kurmanin anlami yok.
        # Ust sinir 25.5 m: mesh'te aralik desimetre-bayt ile tasiniyor
        # (esp32_bridge tavani), ustu sessizce kirpilirdi.
        if not MIN_AYRIM_M <= a.aralik <= 25.5:
            ap.error(f"--aralik {MIN_AYRIM_M:.1f} ile 25.5 m arasinda olmali "
                     "(alt: carpisma esigi, ust: mesh tavani)")
        AYAR.SEKANS_ARALIK_M = a.aralik
        ARALIK_M = a.aralik
        print(f"  [--aralik] formasyon araligi {a.aralik:.1f} m olarak "
              f"EZILDI (senaryo sabiti yerine)")
    if a.alcak is not None:
        if a.senaryo != "irtifa":
            ap.error("--alcak yalniz --senaryo irtifa icin")
        # Alt sinir 2 m: daha alcakta yer etkisi (mesh ve EKF) olcumu kirletir
        # ve inis dedektorune yaklasilir. Ust sinir UST irtifanin ALTI olmali,
        # yoksa "irtifa farki" bacagi fark uretmez ve test anlamsizlasir.
        if not 2.0 <= a.alcak < IRTIFA_TEST_UST_M:
            ap.error(f"--alcak 2.0 ile {IRTIFA_TEST_UST_M:.1f} m arasinda "
                     "olmali (UST irtifanin ALTINDA)")
        IRTIFA_TEST_ALCAK_M = a.alcak
    if a.mesafe is not None:
        # Kayma olcumu icin uzun DUZ BACAK gerekiyor (docs/PLAN.md §9:
        # rampa + 4tau oturma + olcum penceresi). Tavan MAX_GOTO_M ile ayni
        # kelepcede: tek goto icin mesafe siniri zaten orada.
        if a.senaryo != "g2":
            ap.error("--mesafe yalniz --senaryo g2 icin")
        if not 1.0 <= a.mesafe <= MAX_GOTO_M:
            ap.error(f"--mesafe 1..{MAX_GOTO_M:.0f} m araliginda olmali")
        G2_MESAFE_M = a.mesafe
    if a.senaryo == "asili" and len(DRONELAR) < 1:
        ap.error("--senaryo asili en az bir drone ister (or. --dronelar 1,3)")
    if a.senaryo == "irtifa" and len(DRONELAR) < 2:
        # Burada, telemetriye BAGLANMADAN once durur. Ayni kontrol plan
        # kurulurken de var (gec kalan yedek); ilki kullaniciyi bosuna
        # bekletmemek icin.
        ap.error("--senaryo irtifa EN AZ IKI drone ister — olculen sey iki "
                 "ucak ARASINDAKI link (or. --dronelar 1,3)")
    if a.senaryo == "manevra" and len(DRONELAR) < 2:
        ap.error("--senaryo manevra EN AZ IKI drone ister — egim ve yaw "
                 "zarfi tek ucakta olculemez (slot ofseti sifir).")
    if a.senaryo == "formasyon_gecis" and len(DRONELAR) < 2:
        ap.error("--senaryo formasyon_gecis EN AZ IKI drone ister — tek "
                 "ucakta reshape diye bir sey yok (or. --dronelar 1,2,3)")
    if a.harita_ofset:
        try:
            k, _, d = a.harita_ofset.partition(",")
            HARITA_OFSET_KD = (float(k), float(d))
        except ValueError:
            ap.error("--harita-ofset 'KUZEY,DOGU' metre olmali (or. '4,-2')")
    if a.senaryo in ("takip", "g2", "donus", "tam", "final", "saha"):
        if a.lider is None:
            ap.error(f"--senaryo {a.senaryo} icin --lider N gerekli")
        if a.lider not in DRONELAR:
            ap.error(f"--lider {a.lider} --dronelar listesinde yok")
        if len(DRONELAR) < 2:
            ap.error(f"--senaryo {a.senaryo} en az iki drone ister")
        LIDER = a.lider
    if a.senaryo == "gorev1":
        # LIDER'i --lider ZORUNLU KILMIYORUZ: Gorev 1'de lider zaten
        # SABIT ve degeri `ucus_ayarlari.SURU_SABIT_LIDER` (KARAR-17).
        # Operatore ayni sayiyi bir kez daha yazdirmak, iki yerde iki
        # farkli deger olma riskini acardi (§9 "ayni sabiti iki yere
        # yazma"). Elle verilirse o kazanir — kadro daraltilmis testler
        # icin.
        if len(DRONELAR) < 2:
            ap.error("--senaryo gorev1 en az iki drone ister")
        LIDER = (a.lider
                 or int(getattr(AYAR, "SURU_SABIT_LIDER", 0) or 0)
                 or DRONELAR[0])
        if LIDER not in DRONELAR:
            ap.error(f"lider {LIDER} --dronelar listesinde ({DRONELAR}) yok")
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
    global _SENARYO, _QR_TABLO
    _SENARYO = a.senaryo
    _QR_TABLO = a.qr_tablo

    def _kesildi(_s, _f):
        print("\n\n!!! KESİLDİ (Ctrl-C) !!!")
        indir(a.kuru)
        sys.exit(130)

    signal.signal(signal.SIGINT, _kesildi)
    signal.signal(signal.SIGTERM, _kesildi)

    print("=" * 72)
    print("  GOREV 1 KAGIT MODELI — ucus ONBOARD kosar, bu yalniz "
          "carpisma denetimi + HARITA"
          if a.senaryo == "gorev1" else
          "  OKUL SAHASI — 5 nokta, roll, çizgi/ok başı, 20->30 m, iniş"
          if a.senaryo == "saha" else
          f"  KANIT VİDEOSU — batı {FINAL_BATI_M:.0f} m, {FINAL_YON2_DEG:.0f}° "
          f"{FINAL_MESAFE2_M:.0f} m, üçgen, doğu {FINAL_DOGU_M:.0f} m, roll, eve"
          if a.senaryo == "final" else
          f"  KANIT KOREOGRAFİSİ — çizgi, {TAM_MESAFE_M:.0f} m, KD, roll "
          f"{TAM_ROLL_DEG:.0f}°, GD ekseni, eve"
          if a.senaryo == "tam" else
          f"  ÇİZGİ + 180° ROTASYON — {DONUS_MESAFE_M:.0f} m ileri, dön, eve"
          if a.senaryo == "donus" else
          f"  GÖZLEM UÇUŞU — kalk, {G2_MESAFE_M:.0f} m ileri, kendi yerine dön (formasyonsuz)"
          if a.senaryo == "g2" else
          f"  İKİ DRONLU PROVA — ok başı, {TAKIP_MESAFE_M:.0f} m ileri, "
          f"bekle, eve dön"
          if a.senaryo == "takip" else
          f"  KAÇINMA TESTİ — {ASILI_IRTIFA_M:.0f} m'de {ASILI_SURE_S:.0f}s "
          f"ASILI DUR (yatayda komut YOK)"
          if a.senaryo == "asili" else
          f"  MESH ~ İRTİFA TESTİ — {IRTIFA_TEST_UST_M:.0f} m / "
          f"d{DRONELAR[0]} {IRTIFA_TEST_ALCAK_M:.0f} m / {IRTIFA_TEST_UST_M:.0f} m, "
          f"her bacak {IRTIFA_TEST_SURE_S:.0f}s (yatayda komut YOK)"
          if a.senaryo == "irtifa" else
          f"  GÖREV 2 MANEVRA — ÇİZGİ {AYAR.MOD_ARALIK_M:.0f} m / "
          f"{AYAR.MOD_TEST_IRTIFA_M:.0f} m, eğim ±{AYAR.MOD_TEST_EGIM_DEG:.0f}°, "
          f"yaw {AYAR.MOD_TEST_YAW_DEG:.0f}° — SÜRÜYÜ PİLOT SÜRER"
          if a.senaryo == "manevra" else
          "  TEK UÇAK TESTİ — kalkış yönünde 7 m, bekle, 5 m tırman, bekle, in"
          if a.senaryo == "tekli" else
          "  LİDER YANINA GEÇİŞ — lider yerinde asılı, takipçi sağına gelir"
          if a.senaryo == "lider" else
          "  BASİT İKİ DRONE TESTİ — kuzeybatı, bekle, irtifa, dönüş"
          if a.senaryo == "test"
          else "  KANIT UÇUŞU — ok başı, roll, formasyon değişimi, irtifa değişimi")
    if a.senaryo == "saha":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   ÇİZGİ -> OK BAŞI -> ÇİZGİ")
        print(f"  irtifa {SAHA_IRTIFA_M:.0f} -> {SAHA_IRTIFA2_M:.0f} m   "
              f"aralık {ARALIK_M:.0f} m   roll {SAHA_ROLL_DEG:.0f}° "
              f"({SAHA_ROLL_BEKLE_S:.0f}s bekleme, lider sabit, takipçi "
              f"+{ARALIK_M*math.tan(math.radians(SAHA_ROLL_DEG)):.2f} m)")
        print(f"  bekleme: diziliş {SAHA_DIZILIS_BEKLEME_S:.0f} · seyir "
              f"{SAHA_BEKLEME_S:.0f} · rotasyon {SAHA_ROTASYON_BEKLEME_S:.0f} · "
              f"formasyon {SAHA_FORMASYON_BEKLEME_S:.0f} · roll "
              f"{SAHA_ROLL_BEKLE_S:.0f} · dikey {SAHA_DIKEY_BEKLEME_S:.0f} · "
              f"iniş öncesi {SAHA_INIS_ONCESI_BEKLEME_S:.0f} sn")
        print(f"  1. nokta ÖLÇÜLÜR, 2-5 sabit   tırmanış son bacağa GÖMÜLÜ")
    elif a.senaryo == "final":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   ÇİZGİ -> ÜÇGEN -> ÇİZGİ")
        print(f"  irtifa {FINAL_IRTIFA_M:.0f} -> {FINAL_IRTIFA2_M:.0f} m   "
              f"aralık {ARALIK_M:.0f} m   roll {FINAL_ROLL_DEG:.0f}° "
              f"(lider sabit, takipçi "
              f"+{ARALIK_M*math.tan(math.radians(FINAL_ROLL_DEG)):.2f} m)")
        print(f"  bekleme: manevra sonrası {FINAL_MANEVRA_BEKLEME_S:.0f}s, "
              f"seyir sonrası {FINAL_BEKLEME_S:.0f}s   "
              f"iniş yönü {FINAL_INIS_YON_DEG:.0f}°")
    elif a.senaryo == "tam":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ÇİZGİ")
        print(f"  irtifa {TAM_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"roll {TAM_ROLL_DEG:.0f}° (lider sabit, takipçi "
              f"+{ARALIK_M*math.tan(math.radians(TAM_ROLL_DEG)):.2f} m)")
    elif a.senaryo == "donus":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ÇİZGİ")
        print(f"  irtifa {DONUS_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"rotasyon dilimi {DONUS_ROTASYON_ADIM_DEG:.0f}°")
    elif a.senaryo == "g2":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}")
        print(f"  irtifa {G2_IRTIFA_M:.0f} m   ileri {G2_MESAFE_M:.0f} m   "
              f"aralık {ARALIK_M:.0f} m   bekleme {G2_BEKLEME_S:.0f}s")
        print(f"  kalk -> {G2_MESAFE_M:.0f} m ileri -> kendi yerine dön   "
              f"(FORMASYON YOK, roll YOK, irtifa değişimi YOK)")
        print(f"  ⚠ ayrım = yerdeki dizilim; uçakları en az "
              f"{MIN_AYRIM_M:.0f} m (tercihen 8+ m) ayrı diz")
    elif a.senaryo == "takip":
        print(f"  dronelar: {DRONELAR}   LİDER: d{LIDER}   formasyon ok başı")
        print(f"  irtifa {TAKIP_IRTIFA_M:.0f} m   aralık {ARALIK_M:.0f} m   "
              f"bekleme {TAKIP_BEKLEME_S:.0f}s")
    elif a.senaryo == "asili":
        print(f"  dronelar: {DRONELAR}   irtifa {ASILI_IRTIFA_M:.0f} m   "
              f"süre {ASILI_SURE_S:.0f}s   (her uçak KENDİ yerinin üstünde)")
        print(f"  kaçınma {'AÇIK' if _KACINMA_ACIK else 'KAPALI'}   "
              f"kaçış marjı {_kacis_marj():.0f} m")
    elif a.senaryo == "irtifa":
        print(f"  dronelar: {DRONELAR}   alçalan: d{DRONELAR[0]}")
        print(f"  bacaklar: {IRTIFA_TEST_UST_M:.0f} m → "
              f"d{DRONELAR[0]} {IRTIFA_TEST_ALCAK_M:.0f} m → "
              f"{IRTIFA_TEST_UST_M:.0f} m   (her biri {IRTIFA_TEST_SURE_S:.0f}s)")
        print("  3. bacak SÜRÜKLENME KONTROLÜ — 1. ile aynı çıkmazsa "
              "ölçüm geçersiz")
    elif a.senaryo == "formasyon_gecis":
        print(f"  dronelar: {DRONELAR}   kalkış {AYAR.SEKANS_IRTIFA_M:.0f} m"
              f"   aralık {AYAR.SEKANS_ARALIK_M:.1f} m (senaryoya özgü — "
              f"filo ARALIK_M {ARALIK_M:.0f} m DEĞİL)")
        print("  sekans: " + " -> ".join(AYAR.SEKANS_FAZLAR)
              + " -> EVE(kalkış yerine dönüş)"
              + "   süreler: " + ", ".join(f"{s:g}s"
                                           for s in AYAR.SEKANS_FAZ_SURE_S)
              + f" + eve {AYAR.SEKANS_EVE_SURE_S:g}s"
              + f"   izleme payı {SEKANS_IZLEME_PAY_S:.0f}s")
        print("  GEÇİŞLER UÇAKTA (formasyon_sekans düğümü) — YKİ yalnız "
              "arm+takeoff verir, izler, sonda indirir")
        print("  ŞART: üç uçakta da suru_dugumleri içinde `sekans` açık "
              "olmalı; heading kalkış diziliminden türetilir (haritaya bak)")
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
        # 🔴 TURU VE IZI DE BAS. Once yalniz `{e}` basiliyordu ve bos
        # mesajli bir istisna ekrana "HATA: None" diye dusuyordu — hangi
        # satirda ne oldugu HICBIR YERDE gorunmuyordu. Teshis edilemeyen
        # hata, hata vermemekten farksiz.
        import traceback as _tb
        print(f"\nHATA ({type(e).__name__}): {e}")
        _tb.print_exc()
        indir(a.kuru)
        return 1


if __name__ == "__main__":
    sys.exit(main())
