#!/usr/bin/env python3
# =============================================================================
# UCUS AYARLARI — TEK KAYNAK
#
# Hiz, ivme, formasyon araligi ve egim tavanlari BURADA. Baska hicbir yerde
# elle yazilmaz.
#
# NEDEN: ayni sabitin iki yerde durmasi bu projede iki kez bedel odetti.
# Filo varsayilani hem backend hem frontend'deydi, biri guncellenip digeri
# unutuldu ve dusmus drone'a komut gitti. MPC_TILTMAX_AIR kodda "30" diye
# VARSAYILDI ama ylp00'da 45'ti ve gorev kendini havada iptal edebilirdi.
#
# ---------------------------------------------------------------------------
# NASIL KULLANILIR
#
#   python3 src/gcs/ucus_ayarlari.py           # cozumleme + tutarlilik denetimi
#   python3 src/gcs/ucus_ayarlari.py --kabuk   # baslat.sh icin env satirlari
#   python3 src/gcs/ucus_ayarlari.py --px4     # ros2 param set komutlari
#
# HIZI DEGISTIRMEK: asagidaki GIRDILER bolumunde tek sayiyi degistir, sonra
# betigi calistir. Gereken egim tavani, dedektor esigi, frenleme mesafesi ve
# carpisma payi KENDILIGINDEN hesaplanir ve tutarsizlik varsa soylenir.
# Aciyi elle ayarlamaya calisma — hesap zaten burada.
# =============================================================================

import argparse
import math
import sys

YERCEKIMI = 9.80665


# =============================================================================
# GIRDILER — elle degistirilecek yer YALNIZCA burasi
# =============================================================================

# --- Gorev seyir hizi -------------------------------------------------------
# Ucagin bir noktadan digerine giderken tuttugu hiz. px4_bridge'in yurutucusu
# uygular (guided_hiz_yatay_mps), PX4'un tavani DEGIL.
#
# 2.0 -> 3.0 (14 Agustos). 5.0 da mumkun: asagidaki tablo mevcut 12 m
# aralikla 6 m/s'e kadar yettigini gosteriyor. Hizi yukseltmeden once tek
# ucakla duz bir bacakta IZLEME GECIKMESINI olc ve IZLEME_GECIKME_S'i
# dogrula — o sabit 2 m/s'te olculdu, yuksek hizda dogrusalliktan sapabilir.
GOREV_HIZ_MPS = 3.0

# Yurutucunun ivme rampasi. Egim tavanini belirleyen sey BU, hiz degil.
# 1.5'te kaldi: 3. turda 0.8'e indirmek asimi %25'ten yalnizca %21'e cekti
# ve 3 sn ekledi (olculdu, bkz. baslat.sh).
GOREV_IVME_MPS2 = 1.5

# --- Dikey ------------------------------------------------------------------
GOREV_DIKEY_HIZ_MPS = 1.0      # motor isinmasi: daha yavas
GOREV_DIKEY_IVME_MPS2 = 1.0

# PX4'un KENDI dikey tavanlari — 23 Agustos 2026'da UCAKTAN OKUNDU.
#
# 🔴 NEDEN BURADA: dikey yol verme (carpisma kacinmasi) dikey hiz komutu
# veriyor ve PX4 bu tavanin ustunu SESSIZCE KIRPIYOR. Kacinmaya 3.0 m/s
# yazip PX4'te 1.2 birakmak, ayarda ve logda 3.0 gorunurken ucagin 1.2 ile
# tirmanmasi demek — bu depoda MPC_TILTMAX_AIR ile bire bir ayni tuzak
# yasandi (kodda 30 varsayildi, ylp00'da 45'ti).
#
# OLCULEN (iki ucakta da ayni):
#     MPC_Z_VEL_MAX_UP  1.2    MPC_ACC_UP_MAX    4.0
#     MPC_Z_VEL_MAX_DN  1.5    MPC_ACC_DOWN_MAX  3.0
#
# 1.2 dusuk bir deger ve bilincli secilmis gorunuyor (gorev dikey hizi 1.0,
# "motor isinmasi" notu). Yukseltmek AYRI bir karar: kalkis ve gorev
# tirmanislarini da etkiler ve itki payi hala olculmedi.
PX4_DIKEY_HIZ_TAVANI_MPS = 1.2
PX4_DIKEY_INIS_TAVANI_MPS = 1.5
PX4_DIKEY_IVME_TAVANI_MPS2 = 4.0
PX4_DIKEY_INIS_IVME_TAVANI_MPS2 = 3.0

# --- PX4 tavanlari ----------------------------------------------------------
# MPC_XY_VEL_MAX. Gorev seyir hizindan YUKSEK olmali:
#   * carpisma kacinmasinin kacis manevrasi bu tavandan yararlaniyor;
#     seyir hizina esitlersek kacis da o hiza iner ve itme yetersiz kalir
#   * ayni parametre kumandadaki POSCTL'i de sinirlar
PX4_HIZ_TAVANI_MPS = 5.0

# MPC_VEL_MANUAL — kumandayla POSCTL'de cubuk sonuna basildigindaki hiz.
# 14 Agustos'ta ylp00=4, ylp02=2 olctuk: ayni cubuk hareketi iki ucakta
# farkli hiz uretiyordu. Operatorun kas hafizasi biri icin yanlis.
KUMANDA_HIZI_MPS = 3.0

# MPC_ACC_HOR — PX4'un kendi yatay ivme siniri. Yurutucu ivmesinin USTUNDE
# olmali, yoksa PX4 yurutucuyu takip edemez.
PX4_IVME_MPS2 = 2.0

# MPC_YAWRAUTO_MAX — Auto modlarindaki donus hizi tavani.
#
# UCUSU DOGRUDAN ETKILEMIYOR: rotasyonlarimiz OFFBOARD'da yapiliyor ve orada
# gecerli olan MC_YAWRATE_MAX (200 deg/s). Ama 14 Agustos'ta ylp00=45,
# ylp02=25 olctuk ve gorev_kanit_ucus.py uc yerde 25 VARSAYIYOR. Ucaklar
# arasi ayrisma birakmamak icin burada.
PX4_DONUS_HIZI_DEG_S = 25.0

# --- Formasyon --------------------------------------------------------------
# Komsu slotlar arasi mesafe. Kritik ayrim buna DOGRUDAN oranli
# (kritik = ARALIK x cos(kanat acisi)), yani carpisma payinin ana kaldiraci.
#
# 10.0 -> 12.0 (14 Agustos): hiz 3.0'a cikarken pay genisletildi.
# 12 m su anki modelle 6 m/s'e kadar yetiyor (bkz. gereken_aralik_m).
#
# BEDELI: rotasyon yaylari orantili uzuyor — takipci lider etrafinda ARALIK
# yaricapinda doner, yani yay boyu aralikla dogru orantili.
#
# SURU ENTEGRASYONUNDA: bu deger formation_node'un slot geometrisiyle AYNI
# olmali. Su an YKI plani uretiyor; formation_node devreye girince ayni sayi
# oraya da gecmeli, yoksa iki taraf farkli geometri kurar.
ARALIK_M = 12.0
KANAT_ACISI_DEG = 45.0         # ok basi kanat acisi

# --- UCAN KADRO -------------------------------------------------------------
# 🔴 2 Eylul 2026'da BURAYA TASINDI. Oncesinde bu iki deger yalnizca
# baslat.sh'in varsayilanindaydi ve HICBIR YERDEN ayarlanmiyordu:
# ucus_ayarlari.env onlari uretmedigi icin elle eklenen satir dosya yeniden
# uretilince SESSIZCE kayboluyordu. Filo bilesimi ucusun her kademesine
# giriyor; tek kaynakta olmasi gerekiyordu (CLAUDE.md §8 ilkesi).
#
# UCAN_KADRO = GERCEKTEN ucan agent_id'ler. Kacinma RUTBESI bundan turuyor:
#   sirada 0 = CAPA (dikeyde kacmaz) · 1 = YUKARI · 2 = birincil ASAGI
# Yanlis kadro rutbeyi kaydirir ve KACIS YONUNU TERS CEVIRIR
# (RPI_ESITLEME §3, A-matrisi notu).
#
# BEKLENEN_UCAK = kac ucak ucuyor. AJAN_SAYISI ile AYNI SEY DEGIL — ikisi
# 15 Agustos 2026'da olculerek ayrildi:
#   formation_reached: active >= beklenen  -> 2 >= 3 FALSE, FORMING'de TAKILIR
#   saglik orani     : healthy / beklenen  -> 1/3 = 0.33 < 0.5 ile
#                      iki ucaktan biri tokezleyince TUM SURUYE acil inis
# AJAN_SAYISI = KIMLIK ARALIGI (id'ler 1..3), ucan sayi degil; ylp01 kapali
# olsa da 3 kalir cunku ylp02'nin kimligi 3.
UCAN_KADRO = (1, 2, 3)         # 6 Eylul: ylp02 geri kadroda (asagidaki nota bak)
# 6 Eylul 2026 — NEDEN GERI (1,2,3): 5 Eylul gecesi kadro (1,2) idi ve ylp02
# uctu ama SURUYE HIC KATILMADI. Belirti sessizdi, hicbir yerde hata yoktu:
#   ylp02 canli mode_manager -> agent_id=3, agent_ids=[1,2]  (KENDISI YOK)
#   "ModeManagerNode baslatildi: [1, 2]"  ·  logunda FormationCommand HIC YOK
# Mekanizma: mode_manager len(agent_ids)==2 dalinda YALNIZ IKI slot kuruyor
# (mode_manager_node.py ~305-317), yani 3 numaraya ait slot HIC YARATILMIYOR.
# ylp00/ylp01 bekledikleri 2 ucagi gordugu icin normal ucuyor; ylp02 havada
# durup hicbir sey yapmiyor. Kadro EKSIK oldugunda kalkis takiliyor (asagidaki
# not), kadro DAR oldugunda ise sessizce bir ucak dusuyor — ayri belirti.
# 🔴 UCAK EKLENINCE/CIKINCA BURAYI GUNCELLE ve env'i YENIDEN DAGIT.
#    dagit.sh ucus_ayarlari.env'i TASIMAZ — elle gider (RPI_ESITLEME B31).
#    Eksik kadroda `all_agents_seen()` asla True olmaz; mode_manager
#    PREFLIGHT->TAKEOFF gecmez ve _PREFLIGHT_TIMEOUT_S 3600 oldugu icin
#    EMERGENCY'ye de dusmez: SwD kalkis SESSIZCE hicbir sey yapmaz.
# 2 Eylul: (1, 3) idi. O deger SURU_KADRO="1 3" uretiyor ve ylp01 acilinca
# filo BOLUNUYOR: iki ucak [1,3]'lu, biri [1,2,3]'lu tarif basiyor,
# merkezler ayrisiyor. Ayni aksam UC UCAK HAVADA ~1 m'lik kumeye toplandi.
# tek_yayinci.py mimari acigi kapatti; bu satir TETIGI kapatiyor.
BEKLENEN_UCAK = len(UCAN_KADRO)
AJAN_SAYISI = 3                # kimlik araligi — kadro degisse de 3
# NAVIGATE_TO_QR zaman asimi. Yarisma varsayilani 300 sn (QR'a UCARAK
# gitmek zaman aliyor). QR'siz SINAMA ucusunda sürü o sureyi formasyonda
# ASILI geciriyor — bilgi uretmeden pil yakiyor, ucus 6.5 dakikaya cikiyor.
# 30 sn: formasyona oturmak icin en uzun yol 6.7 m, ~5 sn; kalani gozlem.
# 🔴 YARISMA GUNU 300.0 YAPILACAK (ya da 0 = kod varsayilani).
GOREV_NAVIGATE_TIMEOUT_S = 30.0

# Hedef BILINMIYORKEN (QR tablosu yok) NAVIGATE'te beklenen sure.
# 2 Eylul: 30 sn'ydi ve operator bekleyemeyip iki ucusu elle kesti —
# disaridan "formasyonu koruyor" ile "takildi" ayirt edilemiyor, 30 sn
# hareketsizlik cok uzun. Gelistirmede 10 sn: tutmanin calistigini
# gostermeye yeter, sabir sinirini zorlamaz.
# 🔴 YARISMA GUNU: QR tablosu VARSA bu yol hic isletilmez (route_unknown
# false olur); yine de 30.0'a alinmali ki gecici bir tablo kaybinda
# suru hemen eve donmesin.
GOREV_ROTA_BILINMEYEN_S = 10.0

# --- GOREV 1 UCUS PROFILI (operator karari, 2 Eylul gecesi) ----------------
# Profil: dagitik kalk -> CIZGI kur -> QR1'e git -> gorev -> 180 yaw
#         -> eve don -> dikey merdiven -> herkes KENDI kalkis noktasina -> in
#
# 🔴 GOREV_FORMASYON=0 birakilirsa davranis SARTNAME YOLU olur: baslangic
# (juri) dizilisi korunur, formasyon yalniz QR'in `frm` komutuyla degisir.
# 3 = CIZGI. Ileride bu deger YKI'den gelecek (YAPILACAKLAR, 2 Eylul).
GOREV_FORMASYON = 3
GOREV_ARALIK_M = 7.0

# Eve donmeden ONCE surunun topluca dondugu EK aci. Artik 0 OLMALI.
#
# 3 EYLUL'DE DEGISTI, 180 -> 0. Donus miktari ARTIK KENDILIGINDEN cikiyor:
# RETURN_HOME'a girerken bearing(centroid -> home) bir kez mandallaniyor ve
# suru o basliga doner. Ev arkadaysa donus 180, 90 saginda ise 90 olur --
# katı cisim gibi, merkez sabit, kanatlar yay cizerek.
#
# ESKIDEN NEDEN YANLISTI: temel aci LIDERIN KALKIS PUSULASI idi ve buna 180
# ekleniyordu. Lider bacak yonunun tersine bakiyorsa ikisi birbirini yiyordu.
# 3 Eylul gecesi olculdu: bacak 325.6 derece, lider ylp00 147.7 derece,
# komut 327.7 -> QR1'de FIILEN DONULEN ACI 2.1 DERECE. Yani "180 derece yaw"
# hic yapilmiyordu ve hicbir hata gorunmuyordu. Sifirdan farkli birakilirsa
# ev yonune EK olarak doner -- ozel bir sebep yoksa 0 kalsin.
GOREV_DONUS_YAW_DEG = 0.0

# Dikey merdiven basamagi — dagilma sirasinda ust uste binmeyi keser.
# 🔴 OLCULDU (kuru test, 2 Eylul): 3 m KALDI (3.29 m), 4 m GECTI (4.22 m),
# 5 m GECTI (5.18 m). 5 secildi. Kacinma katmani da 3 m; merdiven ondan
# BUYUK olmali ki kacinma tetiklenmeden ayrim kurulmus olsun.
GOREV_DONUS_KATMAN_M = 5.0

# TOPLANMA MERDIVENI — kalkistan ilk formasyona gecerken dikey ayirma.
# 0.0 = KAPALI (davranis eskisinin aynisi).
#
# 🔴 NEDEN VAR (4 Eylul 2026, operator): Gorev 1'de ucaklari HAKEM yere
# rastgele koyuyor. Kalkistan sonra herkes kendi slotuna giderken yollar
# KESISEBILIR — kim nerede duracagi konumdan turetiliyor (Macar atama),
# yerdeki dizilisde hicbir garanti yok.
#
# 5.0 secildi cunku GOREV_DONUS_KATMAN_M ile AYNI kisit gecerli: kacinma
# katmani 3 m ve merdiven ondan BUYUK olmali ki ayrim kacinma tetiklenmeden
# kurulmus olsun. Ayni olcum orada yazili (3 m KALDI, 4 m ve 5 m GECTI).
#
# Ayri parametre: toplanma kalkistan hemen sonra (~10 m) oluyor, eve donus
# gorev irtifasinda. Ikisi bagimsiz ayarlanabilsin.
# ⚠️ Kalkis 10 m ise katmanlar 10/15/20 m olur — en ustteki ucak 20 m'ye
# cikar. Gorev tavaniyla catisirsa BURADAN kucult.
GOREV_TOPLANMA_KATMAN_M = 5.0

# 🔴 YALNIZ DAGILMA BACAGI. 180 yaw'dan sonra cizginin uc ucaklari takas
# ediyor ve kafa kafaya geciyorlar. Olculdu:
#   2.0 m/s -> kapanma 4.0 -> frenleme 2.23 m -> kalan 1.77 m  (hard 2.5 IHLAL)
#   1.0 m/s -> kapanma 2.0 -> frenleme 0.56 m -> kalan 3.44 m  (guvenli)
# 1 Eylul'de 4.13 m/s kapanmada olculen en yakin 1.65 m'ydi; teoriyle 3 cm
# uyusmustu. Diger bacaklarda suru BLOK gidiyor, kapanma sifir.
GOREV_DAGILMA_HIZ_MPS = 1.0

# Formasyon KURULUM hizi (dagitik dizilisten cizgiye). 3 Eylul ucusunda
# operator "cok hizli yaptilar" dedi; kurulum ROTA_MAKS_HIZ (3.0) ile
# kosuyordu. Tek atimlik manevra, hizli olmasinin degeri yok.
# 0.0 = degistirme. 1 Eylul'de Gorev 2 icin ayni karar MOD_MORF_HIZ=0.6
# ile verilmisti ("bayagi yavas yapsin formasyonlari").
GOREV_KURULUM_HIZ_MPS = 1.0

# 🔴 LIDER KILIDI — 3 Eylul 2026 operator karari.
# True: lider bir kez secilir, BIR DAHA DEGISMEZ.
# Sebep olculdu: o gece liderlik BES KEZ el degistirdi (1->2, 2->1, 1->2,
# 2->1, 1->3). Kok neden DURUM paketinin bayatlamasi (ucak basina 7-8 kez
# "5.0-5.1 sn gelmedi", esik 5.0). Her degisimde yeni lider slot atamasini
# yeniden hesapladi, ylp01 ile ylp02 yer degistirdi, birbirinin ustunden
# gectiler ve kacinma binlerce kare devrede kaldi (avoid=1136/1614).
# BEDELI: lider gercekten duserse DEVIR OLMAZ; takipciler son komutta
# kalir. Cikis yolu kill switch pilotlaridir.
SURU_LIDER_KILIDI = True

# Kilit acikken ILK secim TAM KADRO bekler (deterministik lider = en kucuk
# id). Bu sure dolunca eski davranisa duser — bir ucak hic arm olmazsa suru
# lidersiz kalmasin. 3 Eylul: ucaklar arasi evre kaymasi 25 sn olculdu,
# yani 1.5 sn'lik bootstrap grace'i tek basina yetmiyor.
SURU_LIDER_KILIT_TAM_KADRO_S = 8.0

# 🔒 SABIT LIDER — 4 Eylul 2026 operator karari. SISTEM GENELI:
# HEM GOREV 1 HEM GOREV 2 icin lider ylp00.
#
# Lider secilmez, VERILIR: bu kimlik lider olur ve hicbir yoldan degismez.
# Lider zinciri: consensus -> ElectionResult -> swarm_fsm ->
# SwarmState.leader_id -> mission1. Yani tek parametre iki gorevi de kapsar.
#
# NEDEN GEREKTI: lider kilidi (3 Eylul) ILK secimi NIHAI yapiyor, ama o ilk
# secimin ylp00'a dusmesi TESADUFE bagliydi — tam kadro 8 sn icinde
# olusmazsa yedek yol o an uygun olan kimi bulursa onu KALICI lider
# yapiyordu. Ucaklar arasi evre kaymasi 3 Eylul ucusunda 25 sn olculdu.
#
# NEDEN GOREV 1'DE DE GUVENLI: SURU_LIDER_KILIDI ZATEN gorevden bagimsiz ve
# sahada true — Gorev 1'de de devir coktan kapaliydi. Sabit lider yeni bir
# kisit getirmiyor, yalnizca kimligi yarisa birakmak yerine belirli kiliyor.
#
# ⚠️ "LIDER ORTADA" (slot 0) kurali AYRI ve yalniz GOREV 2'de: onu
# mode_manager/tek_yayinci.lider_onde() sagliyor. Gorev 1'in slot atamasi
# MACAR (en yakin slot, formation_cmd.build_slot_assignment) ve 4 Eylul
# aksami uctan uca UCTU — dokunulmadi.
#
# 🔴 BEDELI (lider kilidiyle ayni, bilerek kabul edildi): sabit lider
# gercekten duserse DEVIR OLMAZ; takipciler son formasyon komutunda kalir,
# cikis yolu kill switch pilotlaridir. Kapatmak icin: 0.
SURU_SABIT_LIDER = 1           # 1 = ylp00 (drone1). 0 = kapali.

# 🔴 KALKIS OTORITESI — 2 Eylul 2026, sahada olculdu.
#
# false (19 Agustos'tan beri suren GECIS DONEMI degeri): gorev basladiginda
# agent_fsm ajani ARM eder ama KALKIS KAPISINI ACMAZ; 'takeoff' komutunun
# tek kaynagi guided yol — yani YKI'nin MERKEZI komut yolu — olarak kalir.
# "mission1+agent_fsm kalkisi devraldiginda SURU_KALKIS_OLAYLA=true
# yapilacak" notu baslat.sh:863'te 19 Agustos'tan beri duruyordu.
#
# OLCULEN SONUC (2 Eylul 20:24, ylp00): Gorev 1 tetiklendi, PREFLIGHT
# gecildi, SYNCHRONIZED_TAKEOFF'a girildi, ARM KABUL edildi — ve ajan
# 25 saniye boyunca sunu yazip YERDE bekledi:
#     "ARMED bekliyor: mission_start=False offboard=True armed=True
#      healthy=True hold_active=False autonomous_paused=False"
# Kalkis emrini verecek KIMSE YOKTU: YKI dagitiklik sarti geregi artik
# guided goto gondermiyor, drone da kendi kalkmiyordu. Motorlar bosuna
# dondu, ucus olmadi. mission1 + maneuver_executor 2 Eylul'de ilk kez
# ayaga kalkti; kalkisi devralan taraf artik onlar.
#
# ⚠️ /ws/yer_testi bayragi bunu YINE DE kapatir — agent_fsm_node.py:351
#     kalkis_izni = (not yer_testi) and kalkis_olayla
# Pervanesiz yer testinde motorlarin ~30 sn tam gazda kalmasi o kapiyla
# onlenmisti; o kapi yerinde duruyor, bu degisiklik ona dokunmuyor.
KALKIS_OLAYLA = True

# 🔴 KALKIS IRTIFASI — TEK KAYNAK, 2 Eylul 2026.
# IKI dugum bu sayiyi kullaniyor ve AYNI olmak zorunda:
#   agent_fsm_node  target_altitude_m  -> px4_bridge'e 'takeoff:<X>' yollar
#   mission1_node   kalkis_irtifa_m    -> "ulastim" kararini X ile verir
# Ayrisirlarsa gorev node'u erken/gec "tamam" der ve kimse hata vermez.
# Ikisi de baslat.sh'ten bu degeri aliyor; kodda 10.0 varsayilani duruyor
# ama env dosyasi olan ucakta HER ZAMAN burasi kazanir.
# 4 Eylül 2026 operatör: ilk (kalkış) irtifa 15 m. QR okuma irtifası
# 10 m olduğu için sürü QR'a giderken 5 m alçalır; bu alçalma
# ROTA_DIKEY_HIZ_MPS ile yavaşlatılıyor (0.5 m/s -> ~10 sn).
GOREV_KALKIS_IRTIFA_M = 15.0

# QR OKUMA IRTIFASI — sürü QR'a giderken bu irtifaya iner ve orada okur.
# 4 Eylül 2026 operatör: "20 metreden yukarıda okuyamıyorlar, minimum
# 10 metreye kadar insinler." KAMERA.md §13 ölçümüyle tutarlı: tavan
# 16.64 m (wechat kapalı), 15-16 m'de 0.79 okuma/sn — yani 10 m rahat
# okuma bölgesi. orchestrator'daki _SEARCH_ALT_FLOOR_M de 10.0, yani
# kurtarma merdiveninin tabanı ile AYNI: sürü hiçbir yolda 10 m'nin
# altına inmez.
GOREV_QR_OKUMA_IRTIFA_M = 10.0

# 🔴 OKUYUCU (KAMERALI) DRON — 5 Eylul 2026, operator: "sadece ylp00 okuma
# yapacak". Formasyon, QR'in ustune BU ucagi getirecek sekilde cipalanir.
#
# NEDEN GEREKTI: `orchestrator._anchor_nearest_to_qr` okuyucuyu GEOMETRIYLE
# seciyordu (QR'a o an en yakin dron). Kamera TEK UCAKTA — 5 Eylul'de
# ylp02'nin kamerasi ylp00'a takildi. En yakin ucak ylp01/ylp02 cikarsa
# suru KAMERASIZ bir ucagi QR'in ustune oturtur: QR hic okunmaz, hicbir
# yerde hata gorunmez. Sessiz kusur sinifi.
#
# Sabit lider (ylp00 slot 0 = ortada) bunu KISMEN iyilestirir ama garanti
# etmez: hangi slotun QR'a en yakin dustugu formasyon sekline ve yaklasma
# basligina baglidir; cizgi/V'de kanat ucagi one dusebilir.
#
# 0 = KAPALI, eski davranis (en yakin dron). Kamera birden cok ucaga
# takilirsa 0'a cekilir, geometri yine devralir.
GOREV_KAMERA_AJAN = 1          # 1 = ylp00 (drone1). 0 = kapali.

# (Pil ayarlari INA226 bolumunde — "INA226 PIL OLCUMU" basligina bak.)

# --- Guvenlik ---------------------------------------------------------------
MIN_AYRIM_M = 4.0              # ucaklar arasi kabul edilen en kucuk mesafe
TOLERANS_M = 1.0               # "vardi" yaricapi

# EGIM PAY KATI — egim tavani, komut edilen en buyuk ivmenin KAC KATINI
# karsilayabilmeli.
#
# 2.0 secildi: ivmenin tamami kullanilirken geri kalan yarisi ruzgara,
# bozulmadan toparlanmaya ve kacinma itmesine kalir. 1.0 yapmak "tam gaz
# giderken ruzgar esmesin" demek olurdu.
EGIM_PAY_KATI = 2.0

# EGIM TAVANI TABANI — formul ne derse desin bunun altina inilmez.
#
# NEDEN GEREKLI: yukaridaki hesap yalnizca BIZIM KOMUT ETTIGIMIZ ivmeyi
# sayiyor. Ruzgari saymiyor. Ucak havada asili dururken bile ruzgarin
# suruklemesini yenmek icin egilmek zorunda; 10 m/s ruzgarda bu 1.5-2.5 m/s²
# tuketebilir. Salt formule birakirsak (2.0 m/s² x2 = 25°) ruzgarli gunde
# konum tutamayacak bir tavan cikiyor.
#
# 30° = 5.66 m/s². Komut ettigimiz 2.0'i cikarinca ruzgar ve toparlanmaya
# 3.66 m/s² kaliyor. PX4 varsayilani 45° (9.81 m/s²) ama o kadarina ihtiyac
# yok ve yuksek tavan yere yakin sert duzeltme demek — 1 Agustos'ta kalkista
# devrilme yasandi.
EGIM_TAVANI_TABAN_DEG = 30.0

# DEDEKTOR PAYI — MAKS_EGIM_DEG, egim tavaninin bu kadar USTUNDE olur.
#
# NEDEN USTUNDE OLMAK ZORUNDA: MAKS_EGIM_DEG bir DEVRILME DEDEKTORU.
# Mantigi "PX4 asla MPC_TILTMAX_AIR'dan fazlasini komut etmez, o halde
# fazlasini goruyorsam fiziksel bir sey ters gitmistir". Esik tavanin
# ALTINDA kalirsa normal ucus ariza sayilir ve gorev kendini havada iptal
# eder — 14 Agustos'ta ylp00'da tam bu durum vardi (tavan 45, esik 35).
DEDEKTOR_PAY_DEG = 5.0


# =============================================================================
# TURETILENLER — elle degistirme, hesaplanir
# =============================================================================

def egim_icin(ivme_mps2: float) -> float:
    """Verilen yatay ivme icin gereken egim (derece).

    Cok rotorlu ucak egilerek hizlanir: itki vektoru yana yatar ve yatay
    bileseni ivme uretir.  a = g * tan(egim)
    """
    return math.degrees(math.atan(ivme_mps2 / YERCEKIMI))


def ivme_icin(egim_deg: float) -> float:
    """Verilen egim tavaninin sagladigi en buyuk yatay ivme."""
    return YERCEKIMI * math.tan(math.radians(egim_deg))


def frenleme_m(hiz_mps: float, ivme_mps2: float) -> float:
    """Frenleme mesafesi — "tam hizda durmam gerekse kac metrede dururum".

    KACINMA icin anlamli (kacis manevrasinda gercekten fren yapilir).
    FORMASYON AYRIMI icin DEGIL — bkz. izleme_gecikmesi_m.
    """
    return hiz_mps ** 2 / (2.0 * ivme_mps2)


# IZLEME GECIKMESI ZAMAN SABITI — ⚠️ DOGRULANMAMIS, muhtemelen KARAMSAR.
#
# Tek olcumden turetildi: 2 Agustos, 2 m/s'te 0.44 m -> 0.44/2.0 = 0.22 s.
# AMA o olcum 7 METRELIK bir bacakta alindi ve kodun kendi notu "7 m'lik
# gecisin neredeyse tamami gecici rejim" diyor. Yani olculen sey SEYIR
# kaymasi degil, HIZLANMA fazinin artigi.
#
# TEORI SIFIR DIYOR: yurutucu PX4'e hiz ileri-beslemesi veriyor, yani
#     v = Kp x hata + v_ff   ve   v_ff = v   ->   hata = 0
# Kalici halde kayma olmamali ve hizla BUYUMEMELI.
# Ayrinti ve olcum sonuclari: docs/PLAN.md §9
#
# Bu sabit o olcum yapilana kadar GUVENLI TARAFTA kalmak icin duruyor;
# ayrim payini gereginden genis tutuyor. Olcum sonrasi guncellenecek.
#
# NEDEN FRENLEME MESAFESI DEGIL: formasyonda ucaklar birbirine dogru tam
# hizla gidip fren yapmiyor, planlanmis bir yorungeyi izliyorlar. Ayrimi
# yiyen sey ucagin hedefinden ne kadar GERI KALDIGI. Ilk surumde buraya
# frenleme mesafesi konmustu ve 5 m/s icin 17 m aralik cikariyordu —
# gercek gecikmenin yedi kati, asiri muhafazakar. Duzeltildi.
#
# Gecikme hizla DOGRUSAL buyur (hizin karesiyle degil), cunku yurutucuda
# hiz ileri-beslemesi var; kalan hata orantili terimden geliyor.
IZLEME_GECIKME_S = 0.22

# Gecikmenin kac kati pay birakilir. 3.0: iki ucak birbirine dogru
# gecikebilir (2x) ve uzerine ruzgar/olcum payi.
IZLEME_PAY_KATI = 3.0


def izleme_gecikmesi_m(hiz_mps: float) -> float:
    """Ucagin yuruyen setpoint'in ne kadar gerisinde kaldigi."""
    return hiz_mps * IZLEME_GECIKME_S


def gereken_aralik_m(hiz_mps: float) -> float:
    """Bu hizda MIN_AYRIM'i korumak icin gereken formasyon araligi."""
    pay = IZLEME_PAY_KATI * izleme_gecikmesi_m(hiz_mps)
    return (MIN_AYRIM_M + pay) / math.cos(math.radians(KANAT_ACISI_DEG))


# En buyuk komut edilen ivme: yurutucu ile PX4'un kendi sinirinin buyugu.
EN_BUYUK_IVME_MPS2 = max(GOREV_IVME_MPS2, PX4_IVME_MPS2)

# Gereken egim + pay kati -> onerilen MPC_TILTMAX_AIR.
GEREKEN_EGIM_DEG = egim_icin(EN_BUYUK_IVME_MPS2)
EGIM_TAVANI_DEG = max(
    EGIM_TAVANI_TABAN_DEG,
    math.ceil(egim_icin(EN_BUYUK_IVME_MPS2 * EGIM_PAY_KATI) / 5.0) * 5.0,
)

# TIPIK BACAK BOYU — yalnizca bilgi amacli, plani BAGLAMAZ.
#
# "Bu hiza gercekten ulasiliyor mu" sorusuna bakmak icin. Suru entegrasyonu
# ilerledikce navigasyonu formation_node ve gorev orkestratoru surecek;
# bacak boylari o zaman degisecek. Bu sayi bir VARSAYIM degil, tablodaki
# "seyir payi" sutununu doldurmak icin bir ornek.
TIPIK_BACAK_M = 20.0

# Devrilme dedektoru esigi. gorev_kanit_ucus.py bunu MAKS_EGIM_DEG olarak alir.
MAKS_EGIM_DEG = EGIM_TAVANI_DEG + DEDEKTOR_PAY_DEG

# ---------------------------------------------------------------------------
# ROTA SEKILLENDIRME (path_planner) — 15 Agustos'ta buraya baglandi
#
# path_planner "en kisa yol" bulmuyor; rota zaten belli. Yaptigi is hedefi
# ucagin izleyebilecegi hiza YAYMAK: merkez rampasi + donus rampasi. Bu
# olmadan formation_node her yeni hedefte buyuk bir konum hatasi gorur ve
# hiz komutunu tavana dayar.
#
# NEDEN BURADA: baslat.sh path_planner'a HIC parametre gecmiyordu, dugum
# kendi gomulu varsayilanlariyla kosuyordu. Ayni sinifin hatasi 2 Agustos'ta
# yasanmisti — merkez 3.0 ile kosarken formation_node'un slot rampasi 1.0'da
# tavan yapiyordu, iki sayi birbirinden habersizdi ve suru merkezin gerisinde
# kaliyordu (bacak basina 5 -> 12.5 -> 20.4 m).

# Donus sirasinda KANATTAKI ucagin tegetsel hizi. Formasyon donerken en hizli
# hareket eden odur: hiz = aci_hizi x kanat_yaricapi. Seyrin YARISI seciliyor;
# kalan yari donus sirasinda formasyonu tutan duzeltmelere (ruzgar, komsu,
# carpisma kacinma) pay birakiyor.
ROT_TEGET_HIZ_MPS = GOREV_HIZ_MPS / 2.0

# Ayni mantik ivme icin. Donus yumusak baslasin/bitsin diye (ease-in/out).
ROT_TEGET_IVME_MPS2 = GOREV_IVME_MPS2 / 2.0

# Formasyon heading'inin en hizli donus hizi. Ust sinir; asil sinir yukaridaki
# tegetsel hizdan formasyon boyutuna gore turetiliyor (buyuk formasyon -> daha
# yavas donus). Burada PX4'un kendi yaw tavanini asmiyoruz: uclar donus
# sirasinda burnunu da cevirmek zorunda kalirsa PX4 yetisemezse formasyon
# bozulur.
MAKS_HEADING_DONUS_DEG_S = PX4_DONUS_HIZI_DEG_S

# Rota adim hizi (path_planner ara nokta uretim frekansi). formation_node
# 20 Hz'de setpoint uretiyor; 5 Hz ara nokta yeterli, arasini SVT dolduruyor.
ROTA_ADIM_HZ = 5.0

# ROTA DİKEY HIZ TAVANI — sürü QR'a inerken alçalma YAVAŞ olmalı.
# 4 Eylül 2026 operatör: "dikey alçalma yavaş olmalı, QR okuyacak."
# Yörünge düz 3B çizgi ve adım boyu TOPLAM hızdan (ROTA_MAKS_HIZ=3.0)
# türetiliyor; dikey bileşen ayrıca sınırlanmazsa 25 m -> 10 m'lik bir
# alçalmada dron neredeyse tam hızla iner ve kamera netleyemez.
# 0.5 m/s: 15 m -> 10 m arası 10 saniye sürer — kamera 30 fps'te ~300
# kare görür, KAMERA.md §13'teki 0.79 okuma/sn ile fazlasıyla yeter.
# 0.0 = tavan yok (eski davranış).
ROTA_DIKEY_HIZ_MPS = 0.5

# Ok basi geciside iki ucak en cok bu kadar yaklasir.
KRITIK_AYRIM_M = ARALIK_M * math.cos(math.radians(KANAT_ACISI_DEG))
CARPISMA_PAYI_M = KRITIK_AYRIM_M - MIN_AYRIM_M

# --- KACINMA ESIKLERI -------------------------------------------------------
# 15 AGUSTOS'TA BULUNDU — dogrudan bu dosyanin basligindaki hatanin ta kendisi.
# `basit_kacinma` dugumu d0=8.0 / hard=4.0 ile geliyordu, ama `baslat.sh`
# `${KACINMA_D0:-6.0}` / `${KACINMA_HARD:-3.0}` geciyordu ve bu iki degiskeni
# HIC KIMSE uretmiyordu. Yani ucaklar 6.0/3.0 ile ucuyordu ve kimse bilmiyordu.
#
# NEDEN ONEMLI: hard = tam kuvvet itmenin basladigi mesafe. 3.0 ile bu,
# MIN_AYRIM_M'in (4.0) ALTINDA kaliyor — koruma devreye girdiginde kabul
# edilen sinir zaten asilmis oluyor. Dugumun kendi varsayilani (4.0) dogruydu.
#
# TUREME: hard tam olarak MIN_AYRIM — sinira degdigi an tam kuvvet.
#
# d0 ONCE 2.0 x MIN_AYRIM (8.0) IDI, 1.5'e (6.0) CEKILDI — 20 Agustos 2026,
# operator karari. Sebep 18 Agustos'ta olculdu: 12 m aralikta formasyonun
# PLANLI en yakin yaklasmasi 8.49 m. d0=8.0 ile pay yalnizca 0.49 m kaliyor,
# yani kacinma NORMAL formasyon gecisinde tetiklenir ve formasyonla cekisir.
# 6.0 ile pay 2.49 m.
#
# Iki ayri ariza bicimi var ve ikisi de gercek:
#   hard < MIN_AYRIM  -> koruma GEC kaliyor (sinir asildiktan sonra tam kuvvet)
#   d0   ~ formasyon  -> koruma FAZLA calisiyor (normal ucusta tetikleniyor)
# hard'i MIN_AYRIM'e, d0'i 1.5 katina baglamak ikisini birden cozuyor.
# Bedeli: rampa 4.0 m yerine 2.0 m (3 m/s'te 1.33 s yerine 0.67 s). Dar ama
# yeterli; ilk iki ucakli ucusta kayittan itmenin ne zaman basladigi olculecek.
# =============================================================================
# 🔀 23 AGUSTOS 2026 — DIKEY YOL VERMEYE GECILDI, ESIKLERIN ANLAMI DEGISTI
# =============================================================================
# Yukaridaki turetme YATAY itme icin dogruydu: tek savunma yatay itmeyken
# `hard` "kabul edilen sinira degdigimiz an tam kuvvet" demekti.
#
# Artik birincil kacis DIKEY (operator karari): catisan ucaklardan kimligi
# buyuk olan, kucuk olanin olculen irtifasindan KATMAN kadar uzaga gider.
# Yatay itme SON CARE olarak, yalnizca `hard` kabugunun icinde aciliyor.
# Bu iki esigin anlamini degistirdi:
#
#   d0   = DIKEY manevranin BASLADIGI mesafe (yatay itme DEGIL)
#   hard = dikey yetisememisse YATAY itmenin acildigi kabuk
#
# d0 = 4.0 SABIT — operator karari. Sartname ajanlar arasi mesafeyi
# hakemlere birakiyor (3-10 m, calisma aninda QR ile geliyor) ve operator
# aksiyonun 4 m'de baslamasini istedi. Araliga BAGLANMADI: hakem 5 m'nin
# altini secerse kacinma surekli tetikli olur — davranis dogru ama
# collision_avoidance_node bunu UYARI olarak logluyor, sessiz kalmiyor.
#
# hard = 2.5 — dikey katman 3.0 m oldugu icin buraya kadar gelinmisse
# dikey ayrim SAGLANAMAMIS demektir; yatay itme hakli olarak acilir.
#
# ⚠️ hard artik MIN_AYRIM_M'in ALTINDA ve bu BILEREK: eski kuralda
# "sinira degince tam kuvvet" mantikliydi cunku baska savunma yoktu.
# Simdi sinira gelmeden once dikey zaten devrede.
# 🔴 d0 4.0 -> 3.0 · hard 2.5 -> 2.0 (5 Eylul 2026, operator karari).
#
# SEBEP OLCULDU: aralik 6 m'de okbasi->V gecisinin nominal en dar ani
# 6*cos45 = 4.24 m ve eski d0 4.0 idi — pay 0.24 m. Takip gecikmesi tek
# basina 0.66 m; yani kacinma her morfta tetikleniyordu ve morf yavas
# kalmak zorundaydi. Sahada gozlendi (5 Eylul ucusu).
# d0 3.0 ile pay 1.24 m'ye cikiyor ve morf hizlandirilabiliyor.
#
# 🔴 BILINCLI AYRISMA: MIN_AYRIM_M (4.0 m) bu projenin ilan ettigi en
# kucuk kabul edilebilir ayrim. d0 artik ONUN ALTINDA, yani kacinma o
# tabanin altina inilene kadar tepki VERMIYOR. Kuru test hala 4.0 m'ye
# gore denetliyor — ikisi bilerek ayri: biri "plan guvenli mi", digeri
# "ne zaman mudahale et".
#
# hard 2.5 -> 2.0: d0 dusunce aradaki gradyan 0.5 m'ye inecekti ve yatay
# son-care tepkisi sifirdan tam kuvvete o mesafede cikacakti (gorunur
# sarsinti; sartname osilasyonu -10 ile cezalandiriyor). 2.0 ile gradyan
# yeniden 1.0 m. Taban r_min 1.5 m, hala altinda degil.
KACINMA_HARD_M = 2.0
KACINMA_D0_M = 3.0
# 🔴 DIKEY AYRIM KURULANA KADAR YAKLASMA YOK — 1 Eylul 2026, operator.
#
# "Kacinma devreye girerse drone yatayda ilerlemeyi durduracak ve farkli
# bir irtifaya gecip oyle yatayda harekete devam edecek."
#
# ca_core'un KENDI olcum tablosu (23 Agu benzetimi) bunu dogruluyor:
#     yaklasma    SAF DIKEY   SAF YATAY
#      1.0 m/s      2.63 m      2.27 m
#      2.5 m/s      1.01 m      2.02 m
#      4.0 m/s      0.47 m      1.53 m   <- dikey COKUYOR
# Sebep ayar degil ZAMAN: 3 m'lik katmani kurmak 2-3 sn aliyor. Kapanmayi
# durdurunca dikey kacis o zamani buluyor ve tablo "0 m/s" satirina kayiyor.
#
# 0.8 = katmanin (3.0 m) %80'i, yani 2.4 m dikey ayrim saglaninca yatay
# serbest birakilir. %100 istemiyoruz: son santimlerde takilip yatayin hic
# acilmamasi formasyonun HIC kurulmamasi demek olurdu.
KACINMA_DIKEY_BEKLE = 0.8      # 0.0 = kapali (eski davranis)

# --- DIKEY YOL VERME ---------------------------------------------------------
# DIKEY KACIS HIZI — PX4 TAVANINA ESITLENDI, 23 Agustos 2026.
#
# 1.5 yazilmisti; ucaktan okununca PX4'un tavani 1.2 cikti. Ustunu yazmak
# PX4'un sessizce kirpmasi demekti: ayar 1.5 gorunur, ucak 1.2 tirmanir.
# Simdi ikisi ayni ve asagidaki denetim ayrismayi HATA olarak veriyor.
#
# DAHA HIZLI ISTENIRSE: once MPC_Z_VEL_MAX_UP yukseltilir (ayri karar,
# kalkis ve gorev tirmanislarini da etkiler), sonra bu sayi. Benzetimde
# 1.2 -> 3.0 kazanci: en yakin mesafe 2.17 -> 2.26 m (kucuk), yanal kayma
# 4.83 -> 1.92 m (buyuk), 3 m merdiven 6.7 -> 5.4 sn.
KACINMA_DIKEY_HIZ_MPS = PX4_DIKEY_HIZ_TAVANI_MPS

# Dikey ivme — operator karari (23 Agustos): "en dengeli deger".
#
# OLCULDU: hiz tavani (1.2, PX4) baskin oldugu icin IVMENIN KATKISI COK
# KUCUK. a=1.5 ile a=3.0 arasinda en yakin mesafe farki 0.07 m:
#     a=1.5 -> 2.10 m,  a=2.0 -> 2.13 m,  a=3.0 -> 2.17 m
# Cunku 1.2 m/s'e ulasmak a=3.0'da 0.4 sn, a=1.5'te 0.8 sn suruyor; 3 m
# tirmanmanin kendisi zaten 2.5 sn.
#
# 2.0 SECILDI, 3.0 DEGIL — iki gerekce:
#   * ITKI PAYI: a=3.0 -> 1.31x aski itkisi (~%75 gaz), a=2.0 -> 1.20x
#     (~%72). Aski gazi zaten %66 olculmus (TUZAKLAR §0.3); performans
#     farki 0.04 m iken %3 gaz payi vermek dogru takas degil.
#   * MPC_ACC_DOWN_MAX = 3.0: cift rutbeli ucak ASAGI kaciyor ve a=3.0
#     tam o sinira basiyor — PX4 kirpar. 2.0 her iki yonde de payda.
#
# DAHA HIZLI ISTENIRSE dogru kol IVME DEGIL, MPC_Z_VEL_MAX_UP.
KACINMA_DIKEY_IVME_MPS2 = 2.0

# Dikey konum kazanci — operator karari (23 Agustos). 0.8 -> 2.0.
# 3 m'lik hatada 0.8 yalnizca 2.4 m/s komut uretiyordu ve hiz tavanina hic
# ulasmiyordu; sinir kp'nin kendisiydi.
KACINMA_DIKEY_KP = 2.0

# Dikey merdivende ardisik rutbeler arasi ayrim (operator karari).
KACINMA_KATMAN_M = 3.0

# CIKIS HISTEREZISI — catisma d0'da ACILIR, d0 + hist'te KAPANIR.
#
# 🔴 2.5 -> 0.2 (5 Eylul 2026, operator karari + OLCUM). Bu yukaridaki
# "siki formasyonda yeniden dusunulmeli" notunun karsiligi.
#
# NEDEN 2.5 ARTIK SAVUNULAMIYORDU: Gorev 2 araligi 7 m ve cikis esigi
# 6.5 m idi — yani suru KENDI normal geometrisinde otururken bile cikis
# sinirinin 0.5 m ustundeydi. Olculen takip gecikmesi tek basina 0.66 m.
# Catisma bir kez acilinca kapanacak yer kalmiyordu; morfta daha beter
# (okbasi->V en dar an 4.95 m, cikisin ALTINDA). Operatorun sahada
# gordugu "giris guzel, cikis haddinden uzun ve tutuk" tam olarak buydu.
#
# 2.5'in ESKI gerekcesi (24 Agustos) YENIDEN OKUNDU ve chatter kaniti
# DEGILDI: "cikis 4.5 m iken komsu 4.9 m'de DURURKEN 3 m'lik ayrim
# 6 saniyede geri veriliyordu" — komsu DURUYOR, yani tek bir dogru
# cikis+donus. Sikayet salinim degil PAY sikayetiydi.
#
# CHATTER RISKI OLCULDU VE YOK:
#   * sensor/mesh gurultusu (iki ucak da YERDE hareketsiz, 91 ornek,
#     5 Eylul): tepe-tepe 0.047 m · std 0.013 m · ardisik atlama maks
#     0.016 m. 0.2 m band bunun ~4 KATI.
#   * chatter mesafenin esik civarinda SALINMASINI ister; formasyon
#     geometrisi salinmiyor: cizgide durağan ayrim 7.0 m (4.0'a hic
#     yaklasmiyor), morfta 7 -> 4.95 -> 7 tek yonlu dalis. Tek gecişte
#     bir kez girilir, bir kez cikilir — band genisligi bunu degistirmez.
#
# KALAN GERCEK BEDEL (chatter degil): 3 m'lik dikey ayrim, ucaklar tetik
# mesafesinin 0.2 m disindayken birakilir. Tekrar 0.2 m yaklasirlarsa
# merdiven sifirdan kurulur (3.0 / 1.2 = 2.5 sn). Monotonik morfta bu
# olusmaz; slot geometrisi bir cifti 4 m civarina park ederse olusur —
# 7 m aralikta olmuyor.
#
# ⚠️ Kucuk band ancak DONUS HIZLIYSA guvenli: band >= goreli_hiz x donus
# suresi. Bu yuzden asagidaki uc donus parametresi ayni anda
# hizlandirildi (8.0 sn -> 3.0 sn). Biri geri alinirsa digeri de
# gozden gecirilmeli.
KACINMA_HIST_M = 0.5

# --- KACINMA DONUSU (catisma bittikten sonra nominal irtifaya) ---------
#
# Ucu de 5 Eylul'de hizlandirildi. Eski degerler (2.0 / 0.5 / 4.0) toplam
# 8.0 saniyelik bir donus veriyordu ve bu GENIS histerezis dayatiyordu
# (band >= goreli_hiz x sure). Kucuk band istiyorsak donus hizli olmali.
#
# donus_hiz 0.5 -> 1.2: dikey KACIS zaten 1.2 m/s ile yapiliyor
# (KACINMA_DIKEY_HIZ), yani ucak bu hizi biliyor. Eski koddaki "tehlike
# gecince acele etmenin faydasi yok" gerekcesi artik gecerli degil:
# yavas donus genis band, genis band da ULASILAMAZ cikis demekti.
# ⚠️ 22 Agustos'un "22 derece yalpa" olcumu YATAY 6 m'lik donusteydi
# (3.21 m/s tepe) — baska eksen, baska buyukluk; bu degerle ilgisiz.
KACINMA_DONUS_BEKLEME_S = 0.5   # catisma bitince olu bekleme (2.0'di)
KACINMA_DONUS_HIZ_MPS = 1.2     # nominal irtifaya donus hizi (0.5'ti)
KACINMA_DONUS_SOGUMA_S = 2.0    # yatay ivme kisitli kalma penceresi (4.0'di)

# KORLUK YER ESIGI — kaybolan komsunun SON bilinen irtifasi bunun
# altinda VE disarm ise korluk DONUS TUTMASI uygulanmaz (kapali ucak,
# dusen ucak). 25 Agustos sahasi: kapali ylp02 yuzunden ylp01 donusu
# 34 sn bloke kaldi. Havada/arm'li kaybolan komsu icin tutma aynen
# surer (46.4 sn'lik tek yonlu mesh vakasi o siniftir, TUZAKLAR 2.15).
KACINMA_KORLUK_YER_M = 1.5

# KACIS ZARFI (YANAL) — kacinma bir ucagi PLANLI yerinden en fazla bu
# kadar yana itebilir/kaydirabilir. Kuru testin haritasi ve ayak izi bu
# payi cizmek icin kullaniyor (24 Agustos'ta baglandi — onceden harita
# yalniz planli rotayi ciziyordu ve zarf operatore ELLE soyleniyordu).
#
# KAYNAK: 23 Agustos benzetimi — v_dikey=1.2 ile kacis sirasinda yanal
# kayma 4.83 m olculdu (yukarida 'DIKEY KACIS HIZI' notu), 5.0'a
# yuvarlandi. Dikey zarf ayrica var: KACINMA_KATMAN_M tirmanma —
# haritada cizilemez, lejantta soylenir.
KACINMA_ZARF_YANAL_M = 5.0

# Komsu verisi bu suredan eskiyse YOK SAYILIR. Mesh ~5-7 Hz ve ~%30 kayipli;
# 0.5 s penceresi iki-uc ardisik kayipta komsuyu dusurur ve kacinma SESSIZCE
# korumasiz kalir. 1.5 s `basit_kacinma`nin sahada kosan degeri
# (basit_kacinma_node.py:146) — `collision_avoidance` varsayilani 0.5 idi,
# yani ucte biri. Ikisi ayni degeri kullanmali, yoksa dugum degistirince
# kacinmanin gorus alani sessizce degisir.
KACINMA_BAYAT_S = 1.5

# --- KACINMA IVME SINIRLARI --------------------------------------------------
# 22 AGUSTOS 2026'DA UCUSTA BULUNDU. Operator: "baya bildigin sag sol yapti,
# devrilecek gibi". Kayittan olculdu (ylp00, kacis evresi):
#
#     roll  -24.7 .. +28.3 derece  (53 derecelik yalpa)
#     MAKS EGIM 34.0 derece        (asili evrede yalniz 11.6 idi)
#
# SEBEP: `ca_core.CaParams` ivme sinirlari bu dosyaya HIC BAGLANMAMISTI.
# Ozgun tasarimdan kalma sabitlerdi:
#
#     slew_normal    =  4.0 m/s2  ->  22.2 derece
#     slew_emergency = 30.0 m/s2  ->  71.9 derece   <-- IMKANSIZ
#
# `slew_emergency` komsu `hard`in icine girince devreye giriyor. Operator
# 6.14 m'ye kadar geldi, hard=6.0 — tam devreye girdi. Ucak 72 derece
# egilemez; elinden geleni yapti (34 derece), yetisemedi, komut degisti,
# ters yone egildi. Yalpa BU: imkansiz bir komutu takip etme cabasi.
#
# CLAUDE.md 8 zaten diyordu: "Acilari elle ayarlama. Egim tavani ivmeden
# turetiliyor (a = g*tan(theta))". Hiz, ivme, egim hepsi burada turetiliyordu
# — kacinma haric. Bu o bosluk.
#
# TURETME: kacis bir ACIL manevra, o yuzden egim tavaninin TAMAMINI
# kullanabilir (guided seyir gibi pay birakmaz). Normal kacis ise seyir
# ivmesiyle acil arasinda: ikisinin ortasi.
KACINMA_IVME_ACIL_MPS2 = ivme_icin(EGIM_TAVANI_DEG)
KACINMA_IVME_NORMAL_MPS2 = 0.5 * (GOREV_IVME_MPS2 + KACINMA_IVME_ACIL_MPS2)

# Kacinma bittikten SONRA eve donus ivmesi. Ayri ve DUSUK olmasi kasitli:
# tehlike aninda sert olmali, tehlike gecince acele etmenin faydasi yok.
# 22 Agustos olcumu: 6 m'lik donus 3.21 m/s tepe hizla yapildi
# (v_tepe = sqrt(a*d) = sqrt(1.5*6) = 3.0) ve donus evresinde 22 derece
# yalpa olustu. 0.5 m/s2 ile tepe 1.73 m/s'e iner.
KACINMA_DONUS_IVME_MPS2 = 0.5

FRENLEME_GOREV_M = frenleme_m(GOREV_HIZ_MPS, GOREV_IVME_MPS2)
FRENLEME_TAVAN_M = frenleme_m(PX4_HIZ_TAVANI_MPS, PX4_IVME_MPS2)

# =============================================================================
# FORMASYON GECIS TESTI — ⚠️ GECICI (28 Agustos), mission1 gelince silinecek
# =============================================================================
# Operator tarifi: rastgele kalkis -> CIZGI -> OKBASI -> V, aralik 7 m,
# toplam sure <= 2 dk, tetik YKI'deki gecici buton. Tuketiciler:
#   formasyon_sekans_node (ucakta, baslat.sh env'inden) ve
#   gorev_kanit_ucus.py --senaryo formasyon_gecis (kuru + harita + kalkis/inis)
#
# 🔴 7.0 ARALIK_M'E YAZILMAZ. Filo varsayilani 12 m kalir; 7 m yalniz bu
# senaryonun tarifinde tasinir. Cunku 7 m'de gecislerin en dar ani
# (OKBASI->V, kanatlar liderin yanindan s*sin45 = 4.95 m ile gecer) kacinma
# cikis esiginin (d0+hist = 6.5 m) ALTINDA — ARALIK_M=7 yazilsaydi yukarida
# "acilan catisma hic kapanmaz" HATASI dogru olarak patlardi. Senaryoda ise
# bu gecici bir AN, sabit hal degil: sabit halde ciftler 7.0 m'de ve cikis
# esiginin ustunde. Asagidaki denetle() eki bu geometriyi ayrica izler.
SEKANS_ARALIK_M = 7.0
SEKANS_IRTIFA_M = 8.0          # 26 Agustos formasyon ucusuyla ayni irtifa
# SON FAZ YINE CIZGI — EVE DONUSUN GUVENLI KORIDORU (28 Agu aksam,
# kuru testte olculerek bulundu). V'den dogrudan eve donus, gercek
# yerlesimde carpisma denetiminden GECEMEDI (2,17-2,20 m): kalkis ucgeni
# iki boyutlu, V baska yerde tek boyutlu — bir ucagin kalkis noktasi
# digerinin V slotunun dibinde kalabiliyor. Cozum: donusten once CIZGI'ye
# toplan. kalkis->cizgi bacagi Macar'in en-kisa-toplam eslesmesi (kesisen
# ciftte takas toplami kisaltirdi -> kesisme olamaz) ve plan_dogrula bu
# bacagi ZATEN denetliyor; EVE = ayni yuruyusun tersi. Iki basarisiz
# atama kurali denemesi icin: formasyon_sekans_cekirdek.faz_ofsetleri.
SEKANS_FAZLAR = ('cizgi', 'okbasi', 'v', 'cizgi')
# 25/25/25 operator karari (28 Agustos aksam); donus cizgisi 20 s (yol
# 9,9 m ~15 s, kuru butce satiri olcuyor). Kisaltmak guvenlik sorunu
# DEGIL: faz suresi yetmese bile kacinma aktif — riski korlemesine pay
# yerine OLCUM tutuyor: kuru test faz basina en uzun yolu hesaplayip
# sigmiyorsa UYARIYOR. Adlandirilmis 95 s + EVE 25 s = 120 s; kalkis ve
# inisle ~2,5 dk (eve donus istegi 2 dk hedefini asagi yukari 30 s asti).
SEKANS_FAZ_SURE_S = (25.0, 25.0, 25.0, 20.0)
SEKANS_KURULUM_HIZ_MPS = 2.5   # ilk faz: bos alanda uzun yol, seyire yakin
SEKANS_GECIS_HIZ_MPS = 1.5     # reshape: dar gecit, mission1'in morph'u gibi yavas
# EVE DONUS fazi (operator istegi, 28 Agu aksam): V'den sonra her ucak
# KENDI olculmus kalkis noktasina doner, inis oraya olur. PX4 RTL DEGIL —
# HOME kaymasi P0 acik (RTL uc ucagi ayni yanlis noktaya indirmisti).
SEKANS_EVE_SURE_S = 25.0
SEKANS_KALKIS_ESIK_ORANI = 0.8  # EKF z / origin farki ~1 m olculdu (26 Agu)
SEKANS_KALKIS_ZAMAN_ASIMI_S = 90.0


# =============================================================================
# GOREV 2 — YARI OTONOM MOD LIMITLERI (mode_manager + joystick_interpreter)
# =============================================================================
# Sartname 5.2: tek kumandadan Suru Hareket Modu (oteleme) ve MANEVRA MODU
# (merkez sabit; pitch/roll = formasyon DUZLEMI egimi, yaw = formasyon
# rotasyonu + heading). Buradaki "egim" UCAGIN govde egimi DEGIL — slot
# irtifa modulasyonu; MPC_TILTMAX_AIR ile karistirma.
#
# Onceden bu sayilar ModeContext/MotionLimits icinde GOMULUYDU (iki ayri
# kopya: 30 vs 45 deg/s!) — 14 Agustos dersinin ayni sinifi. 28 Agustos'ta
# tek kaynaga baglandi (KARAR-11).
MOD_EGIM_TAVANI_DEG = 15.0     # manevra egim genligi (cubuk tam basili)
# Yaw hizi IKI tavanin kucugu — tanim MOD_ARALIK_M'den SONRA (o da
# gerekiyor). Gerekce ve olcum orada.
MOD_HIZ_MPS = 2.0              # hareket modu oteleme hizi (muhafazakar)
# 🔴 FORMASYON MORFU AYRI VE COK DAHA YAVAS — 1 Eylul 2026, UCUSTA OLCULDU.
#
# 31 Agustos gecesi kumandadan formasyon gecisi uculdu ve iki ucak
# 1,65 m'ye kadar yaklasti. Kayittan cikarilan sayilar:
#     duruştan 2,71 m/s'e     1,2 saniyede
#     tepe kapanma hizi       4,13 m/s
#     kacinma giris esigi     4,00 m  (KACINMA_D0_M)
#     frenleme mesafesi       v^2/2a = 4,13^2 / (2*3,58) = 2,38 m
#     kalmasi gereken         4,00 - 2,38 = 1,62 m
#     OLCULEN EN YAKIN        1,65 m   <- 3 cm fark
#
# Yani KACINMA BOZUK DEGIL, kitabina gore calisti; 4 m'lik esik 4 m/s'lik
# bir kapanma icin tasarlanmamis. Cozum esigi buyutmek DEGIL (7 m aralikta
# kacinma surekli acik kalirdi), morfu YAVASLATMAK.
#
# 0,6 m/s ile: kapanma 1,2 m/s, frenleme 0,20 m, kacinmaya 3,80 m kalir.
# Daha da yavaslatmanin faydasi hizla azaliyor (tavan 4,00 m), maliyeti ise
# dogrusal artiyor — en uzun morf yolu 9,9 m, 0,6 m/s'de 16,5 sn.
#
# ⚠️ Bu hiz YALNIZ morf suresince gecerli. Suru merkezi hareket ederken
# (cubukla oteleme) MOD_HIZ_MPS gecerlidir; slot hizini kalici olarak
# dusurmek formasyonu merkezin GERISINDE birakir — formation_node'daki
# "merkez 3.00 iken komut 1.05" hatasinin ta kendisi.
# 🔴 1.0 -> 1.30 (5 Eylul, operator: "biraz daha atik olsunlar").
# 1.34 ISTENDI ama denetimden GECMIYOR: kapanma 2.68 m/s, frenleme 1.00 m,
# kacinma esiginden geriye 1.997 m kaliyor ve esik 2.0. 1.30 -> 2.06 m.
# Kazanc: okbasi->V gecisi 6 m aralikta 8.5 sn -> 6.5 sn.
#
# ⚠️ DENETIMIN MODELI MUHAFAZAKAR ve bunu OLCTUK: kapanmayi 2*v sayiyor,
# oysa gercek formasyon gecislerinde en buyuk kapanma orani 0.765*v
# (uc ucak, cizgi<->okbasi; okbasi<->V 0.707*v — kanatlar PARALEL gidiyor,
# aralari sabit 8.49 m). Yani model ~2.6 kat karamsar.
# GEVSETILMEDI, cunku 2*v muhtemelen bir geometri iddiasi degil AMPIRIK
# asim katsayisi: 31 Agustos'ta morf tam hizda kosuldugunda gercek kapanma
# 4.13 m/s olculdu (hicbir geometrik model bunu vermez) ve ucaklar 1.65 m'ye
# yaklasti. 1.0 m/s'te gercek asimi KIMSE olcmedi.
# SIRADAKI ADIM: morf sirasinda d(t) zaman serisini bag'den cikar, gercek
# kapanma katsayisini olc, modeli TAHMINLE degil VERIYLE ac.
MOD_MORF_HIZ_MPS = 1.30         # formasyon DEGISIMI sirasindaki slot hizi
# Morf kilidinin en gec ne zaman dusecegi. En uzun morf yolu 9,9 m ->
# 0,6 m/s'de 16,5 sn; 25 sn bunu paylasan bir tavan, takilip kalmayi onler.
MOD_MORF_SURE_S = 25.0
# 🔴 IVME RAMPASI — B6, 31 Agustos 2026'da baglandi.
#
# ONCEDEN RAMPA YOKTU: `mode_context.compute_centroid_delta` cubugu ANINDA
# hiza ceviriyordu, yani tam basildiginda komut 0 -> 2 m/s. Sartname
# osilasyonu -10 ile cezalandiriyor. Ivme sinirli surum
# (`manual_kinematics.swarm_movement_step`) YAZILMIS ve TEST EDILMISTI ama
# HICBIR YERDEN CAGRILMIYORDU — olu kod olarak duruyordu.
#
# ⚠️ O FONKSIYON OLDUGU GIBI KULLANILAMADI: heading ile DONDURMUYOR, yani
# pitch'i dogrudan KUZEY sayiyor. Mevcut yol govde cercevesinde calisiyor
# (cubuk ileri = surunun BAKTIGI yon) ve pilot icin dogru olan bu. O yuzden
# ivme siniri mevcut yola eklendi, `slew` tek kaynaktan aliniyor.
#
# DEGER NEREDEN: egim tavani 15 deg -> ivme_icin(15) = 2.63 m/s². EGIM_PAY_KATI
# 2.0 oldugu icin komut edilebilecek en buyuk ivme bunun YARISI = 1.31.
# 1.3 secildi. 2.0 m/s'den frenleme: 1.54 s, 1.54 m.
MOD_IVME_MPS2 = 1.3
# Dikey ivme egimle sinirli DEGIL (itki dogrudan yukari), guided tarafiyla
# ayni deger kullaniliyor.
MOD_DIKEY_IVME_MPS2 = 1.0
# 🔴 7.0 -> 9.0, 31 Agustos 2026. OLCULDU, tahmin degil.
#
# Kumandadan formasyon gecisinde en dar an okbasi->V morfunda olusuyor ve
# aralikla DOGRU ORANTILI (gorev_kanit_ucus plan_dogrula ile tarandi,
# yer dizilimi hedef formasyona esit varsayimiyla):
#     aralik 7.0 m -> en dar 4.95 m -> kacinma girisine (d0=4.0) pay 0.95 m
#     aralik 8.0 m -> en dar 5.66 m -> pay 1.66 m
#     aralik 9.0 m -> en dar 6.36 m -> pay 2.36 m   <-- secilen
#     aralik 10.0 m -> en dar 7.07 m -> pay 3.07 m
# 7 m'deki 0.95 m pay, olculen takip hatasi/suruklenme mertebesiyle ayni
# buyuklukte: 31 Agustos kalkisinda kilitli tirmanis boyunca ylp01 2.17 m,
# ylp00 0.90 m, ylp02 0.18 m suruklendi. Yani 7 m'de morf sirasinda kacinma
# TETIKLENEBILIR — carpisma degil ama formasyon bozulur ve olcum kirlenir.
#
# 9 m ayrica ikinci bir uyariyi da kapatiyor: durgun formasyonda ucaklar
# kacinma CIKIS esiginin (d0+histerezis = 6.5 m) 2.5 m ustunde kaliyor;
# 7 m'de bu pay 0.5 m idi ve kacinma bir kez acilirsa uzun sure kapanmiyordu.
#
# ⚠️ Alan bedeli: formasyon kutusu ~%29 buyuyor. Saha darsa aralik
# kumandadan (canli param default_spacing_m) kucultulebilir — ama o zaman
# yukaridaki pay da kucuur, bilerek yapilmali.
#
# 🔴 9.0 -> 7.0 GERI ALINDI, 31 Agustos 2026 — OPERATOR KARARI (madde 29).
# Operator: "hic bisey girmezsek varsayilan deger 7m olsun." Yukaridaki
# olcum SILINMEDI cunku hala gecerli: 7 m'de okbasi->V morfunun en dar ani
# 4.95 m, kacinma girisine (d0=4.0 m) pay 0.95 m ve olculen suruklenme
# 2.17 m'ye kadar cikti. Yani morf sirasinda kacinma TETIKLENEBILIR —
# carpisma degil, formasyon bozulmasi.
# Cozumu tek tus: YKI'de "Aralik (m)" kutusuna 9 yazmak (madde 29 zinciri
# degeri mesh'ten uc ucaga birden gonderir). Varsayilan olarak 7 duruyor.
MOD_ARALIK_M = 7.0             # hakem baska soylerse kumandadan degisir

# --- YAW HIZI: IKI TAVANIN KUCUGU (1 Eylul 2026) ----------------------------
# TAVAN 1 — PX4 (23 Agu dersi): her ucak heading'ini de donduruyor ve PX4
# MPC_YAWRAUTO_MAX bunun ustunu SESSIZCE kirpar.
#
# TAVAN 2 — FORMASYON GEOMETRISI, 1 Eylul'de bulundu ve TUTARSIZDI:
# formasyon merkez etrafinda donerken en uzak slot `aralik` kadar uzakta
# (kuru testte V icin 6,93-7,02 m olculdu). Teget hiz = r * omega:
#     25 deg/s * 7,0 m = 3,05 m/s   <- seyir tavani 2,0 m/s'in USTUNDE
# Slot 3 m/s ile kayarken ucak 2 m/s ile kovaliyor: formasyon donus
# BOYUNCA dagilir, sonra toparlar. Sartname §5.2.2 yaw'i "formasyonu
# koruyarak" istiyor — dogrudan puan meselesi.
#
# 🔴 SABIT YAZILMIYOR, TURETILIYOR: aralik hakemden geliyor (madde 29) ve
# 12 m verilirse 15 deg/s de yetmez. Elle yazilan bir sayi o gun sessizce
# yanlis olurdu.
#
# PAY KATI 0.9: teget hiz tam tavana esitlenirse SVT duzeltmesine hic yer
# kalmaz — slot tam hizla kacar, ucak hep bir adim geride olur.
YAW_PAY_KATI = 0.9
MOD_YAW_HIZI_DEG_S = min(
    PX4_DONUS_HIZI_DEG_S,
    math.degrees(YAW_PAY_KATI * MOD_HIZ_MPS / MOD_ARALIK_M),
)
MOD_DEADMAN_ZAMAN_ASIMI_S = 0.5
# --- INA226 PIL OLCUMU (31 Agustos 2026) ------------------------------------
# 🔴 NEDEN VAR: ylp01'de PX4 guc modulu YOK ve px4_bridge guc modulu
# gormeyince pil alanlarina SABIT %100 / 12.6 V yaziyordu — yani o ucak
# pili ne olursa olsun YKI'de "dolu" gorunuyordu. INA226 gercek olcumu
# koyuyor. Zincir: ina226_node -> px4_bridge -> AgentStatus -> mesh -> YKI.
#
# ADRES OLCULDU (31 Agu, ylp00): 0x40 = 64 desimal. Kimlik yazmaclari
# dogrulandi (uretici 0x5449, die 0x2260) — tahmin degil.
PIL_INA226_ADRES = 64          # 0x40; A0/A1 pinleri 0x40..0x4F verir
# Seri hucre sayisi — YALNIZCA kaba yuzde kestirimi icin kullaniliyor.
# 31 Agu olcumu 16.029 V: 4S'te 4.01 V/hucre (saglikli), 5S'te 3.21
# (neredeyse bos), 3S'te 5.34 (imkansiz) -> 4S.
# ⚠️ Failsafe esigi icin YUZDE degil GERILIM kullanilir (AgentStatus
# yorumu): LiPo gerilimi yuk altinda duser, yuzde yaniltir.
PIL_HUCRE_SAYISI = 4
# Sont direnci — akim olcumu icin. 0.0 = "akimi hesaplama".
# Operator 31 Agu'da "akima gerek yok" dedi; uydurma bir deger akimi
# SESSIZCE olcekli-yanlis yapardi, o yuzden 0.0 birakiliyor.
PIL_SONT_OHM = 0.0
# --- GOSTERGE UCLARI ve ESIKLER (2 Eylul 2026, OPERATOR KARARI) --------------
# Gosterge: 14.2 V = %0 · 16.8 V = %100 (4S -> 3.55 / 4.20 V hucre).
# Onceki olcek 13.2-16.8 idi (hucre 3.30); operator daha erken "bos"
# gostersin diye daralttı. Aralik 3.6 -> 2.6 V, yani 1 V ~ %38.
#
# 2 Eylul'de DOGRULANDI: PX4'un kendi pil okumasi GECERSIZ — MAVROS
# `voltage: 65.535` (0xFFFF sentinel), `percentage: -0.01`. Guc modulu
# yok; tek gercek kaynak INA226 ve AgentStatus'a dogru geciyor
# (olculen: ylp00 14.688 V, ylp02 15.095 V).
PIL_BOS_V = 14.2               # gosterge %0
PIL_DOLU_V = 16.8              # gosterge %100
# 🔴 FSM KESME ESIGI — gostergenin %0'i ile AYNI DEGIL, bilerek.
# agent_context.healthy bunu ANLIK gerilimle karsilastiriyor ve
# histerezisi YOK. 14.2 yapilsaydi tek bir cokus dikeni healthy'yi
# dusurur, suru saglik orani kirilir ve TUM SURU acil inise gecebilirdi.
# Olculdu (1 Eylul, ylp00): kalkista 15.29 -> 14.72 V, yani 0.57 V'luk
# dikenler NORMAL. 0.4 V pay birakildi.
PIL_KRITIK_V = 13.8

# 🔴 PIL KESMESI ACIK MI — 2 Eylul 2026, 08:20, operator talimati.
#
# False: pil OLCULMEYE, YKI'de gorunmeye ve UYARI/olay uretmeye DEVAM eder;
# yalniz agent_fsm'i FAILSAFE'e dusuren dal kapanir. "Izleme kapali" DEGIL —
# esigi 0 yapmak izlemeyi komple kapatirdi, operator onu istemedi.
#
# NEDEN: yukaridaki 0.4 V pay SAGLAM pilde olculmus (0.57 V diken). 2 Eylul
# gecesi BOSALMIS pilde olculen cokus 1.26-1.31 V — iki katindan fazla,
# cunku sarj dustukce ic direnc artiyor:
#     ylp00  %33 = 15.06 V dinlenmede -> ucarken 13.80 V  (cokus 1.26 V)
#     ylp02  %35 = 15.11 V dinlenmede -> ucarken 13.80 V  (cokus 1.31 V)
# Yani yarim pille her gelistirme ucusu, HENUZ BITMEMIS bir pille esige
# degip kendini kesiyordu.
#
# NE KALIR: kumanda, kill switch, PX4'un KENDI dusuk-pil failsafe'i
# (Pixhawk parametresi, bu dosyadan bagimsiz), YKI yuzde uyarilari ve
# agent_fsm'in "Batarya dusuk/Kritik batarya" UYARILARI + EVENT_BATTERY_LOW.
# NE GIDER: yalniz otomatik FAILSAFE gecisi. Pili operator izler.
#
# 🔴 YARISMA GUNU True YAPILACAK. Dogru kalici cozum: anlik gerilim yerine
# N saniyelik debounce — anlik cokus dikenini yutar, gercekten biten pili
# yine yakalar. Sirasi gelince (KARARLAR.md).
PIL_KESME_AKTIF = False
# YKI uyari esikleri YUZDE olarak (alert_manager boyle calisiyor).
# Gerilim karsiliklari: %30 -> 14.98 · %25 -> 14.85
#                       %16 -> 14.62 · %10 -> 14.46 V
# Cokus payi yuzunden bilerek dusuk: yari dolu bir pil motor calisinca
# ~%20 gorunuyor; %25'in ustune cikarmak yanlis alarm uretirdi.
PIL_UYARI_AC = 25.0
PIL_UYARI_KAPA = 30.0
PIL_KRITIK_AC = 10.0
PIL_KRITIK_KAPA = 16.0
# B15 KALKIS KAPISI (30 Agustos 2026): mode_manager, TUM ucaklar bu
# yuksekligin uzerine cikana kadar HICBIR tarif/setpoint yayinlamaz.
# NEDEN: READY'de _dispatch_hold() tarif yayinliyor ve centroid swarm_fsm
# hic centroid hesaplamadiysa (0,0,0)'da kaliyor — yerde READY'ye atlayan
# bir FSM suruyu NED ORIGIN'E gonderirdi. formasyon_sekans ayni kapiyi
# 0.8 x irtifa ile kuruyor; burada sabit esik, cunku mode_manager hedef
# irtifayi bilmiyor (kalkis kumandadan gelince B2 ile gelecek).
# 2.0 m: yer gurultusunun acikca ustunde, en dusuk planlanan irtifanin
# (5 m) acikca altinda.
MOD_KALKIS_ESIK_M = 2.0
# 🔴 ESIK PAYLASILAN ORIGIN'E GORE, YERE GORE DEGIL.
# AgentStatus.pos_z origin-goreli; ucaklar origin'le ayni kotta durmuyor.
# ICERDE olculen: ylp00 -0,5 · ylp01 +0,2 · ylp02 +0,5 m.
# ACIK ALANDA olculen: ylp00 +1,7 · ylp01 -0,1 · ylp02 0,0 m
#   -> ylp00 SIRF YERLESIM yuzunden 2,0 m esigin %85'ini tuketti.
# Bir ucak origin'in 2,5 m ustune konsaydi KAPI YERDEYKEN ACILIRDI.
# Bu yuzden kapiya ARM SARTI eklendi (mode_context.kalkis_kapisi_degerlendir):
# disarm bir ucak havada olamaz, sart irtifa referansindan bagimsizdir.
# Esigi buyutmek COZUM DEGIL — ofset de buyuyebilir.
# 🔴 KUMANDADAN KALKIS IRTIFASI (G2-K10 / madde 25, 30 Agustos 2026).
# Sartname §5.2.2: "Takeoff ve land komutlari da kumanda uzerinden yapilir";
# senaryo madde 5: "sürü, baslangic formasyonunu koruyarak belirlenen
# irtifaya (Orn: 15m) yukselir". Hakem baska bir sayi soyleyebilir.
#
# MOD_TEST_IRTIFA_M'DEN AYRI TUTULDU (bilerek, ayni degerde olsalar bile):
# biri gorev irtifasi, digeri manevra testinin genligi. Tek degisken
# olsalardi hakem "15 m" dedigi anda manevra testinin de genligi degisirdi.
#
# 8.0 -> 5.0, 31 Agustos 2026, operator karari. Bu deger UC UCAKLI ILK
# eszamanli kalkis icin secildi, gorev irtifasi olarak degil:
#   * 30 Agustos'ta 8 m hedefle kalkan ylp00 iniste yalpaladi; sebep
#     px4_bridge'in emniyet pilotuyla kavgasiydi (duzeltildi) ama ayni
#     manevra simdi UC ucakta birden denenecek.
#   * Dusuk irtifa hem dusme enerjisini hem pilotun tepki mesafesini
#     lehimize cevirir; olculecek soru ("SwD ucunu birden kaldirip
#     indiriyor mu") irtifadan BAGIMSIZ.
# Yatay kilit 2,5 m'de acildigi icin 5 m'de kilit sonrasi hala 2,5 m
# tirmanis kaliyor — kilit gecisi yine gozlemlenebiliyor.
# Hakem sahada baska bir sayi soylerse (sartname ornegi 15 m) burasi
# degisir; MOD_TEST_IRTIFA_M'e DOKUNMA, o ayri degisken.
MOD_KALKIS_IRTIFA_M = 5.0      # 31 Agu operator: uc ucakli ILK kalkis (bkz. asagi)
# --- Gorev 2 MANEVRA TESTI genlikleri (G2-K4, operator 30 Agustos) --------
# Bunlar TAVAN degil TEST genligi: tavanlar yukarida (egim 15, yaw 25/s),
# test bunlarin altinda kalir. `--senaryo manevra` kuru testi ve haritasi
# bu sayilarla cizilir; kumandada karsiligi ~%66 egim / %50 yaw cubugu.
MOD_TEST_IRTIFA_M = 8.0        # 28 Agu sekans ucusuyla ayni irtifa
MOD_TEST_EGIM_DEG = 10.0       # cubuk %66
MOD_TEST_YAW_DEG = 45.0        # toplam donus (12,5 deg/s ile ~3,6 s)
# 🔴 GAZ MERKEZ KAPISI (30 Agu, saha olcumu). Gaz cubugu ORTALANMIYOR ve
# dogal olarak dipte duruyor (olculen dinlenme PWM 1001 -> throttle_cmd
# -1.0). Emniyet acilinca suru ANINDA tam hizla alcalirdi. Gaz bu paydan
# daha uzaksa joystick_interpreter komutu GECERSIZ isaretler ve mode_manager
# HOLD'da bekler. Bkz. mode_manager/rc_eksen.gaz_merkezde
MOD_GAZ_MERKEZ_PAY = 0.2
# 🔴 SwC DEBOUNCE (madde 26, 30 Agustos 2026 — SAHA OLCUMU).
# SwC detentli 3 konumlu ve orta = V FORMASYONU; okbasindan cizgiye
# giderken ORTADAN GECMEK zorunlu. Debounce'suz kod her geciste formasyon
# degisimi tetikliyordu: hakem "cizgiye gec" der, suru ONCE V'ye morf
# olmaya baslardi (okbasi->V en dar an 4,95 m, kacinma girisi 4,0 m).
#
# 31 Agustos 2026 (YENI KUMANDA), iki kayit:
#     852 · 364 · 215 · 214 · 200 · 158   ve   321 · 162 · 120 · 100 · 92
# 🔴 Iki tavan CELISIYOR (852 vs 321). 852'nin gercek gecis mi duraklama
# mi oldugu cozulmedi -> GUVENLI TARAF secildi. Esik dusuk kalirsa sahte
# V morfu ve carpisma riski (-20xN); yuksek olursa V secimi 1,3 sn
# gecikir, o kadar. Ayrinti: mode_manager/swc_debounce.py
MOD_SWC_DEBOUNCE_MS = 1300.0


def _sekans_geometri():
    """Sekans gecislerinin en dar anlarini swarm_core'dan TEK KAYNAKLA verir.

    Geometri formulunu burada kopyalamak "ayni sabit iki yerde" tuzaginin
    (dosya basligindaki kaza) formul hali olurdu; ucaktaki dugumle ayni
    fonksiyon cagriliyor. swarm_core saf Python (ROS'suz) — dizustunde de
    yuklenir. Bulunamazsa None doner ve denetim bunu UYARI yapar, sessiz
    gecmez.
    """
    import os
    kok = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', 'swarm_core')
    if kok not in sys.path:
        sys.path.insert(0, kok)
    try:
        from swarm_core.formation_control import (
            formasyon_sekans_cekirdek as cek,
        )
    except ImportError:
        return None
    plan = cek.faz_plani(list(SEKANS_FAZLAR), list(SEKANS_FAZ_SURE_S))
    gecisler = []
    for i in range(len(plan) - 1):
        d = cek.gecis_min_mesafe(
            plan[i][0], plan[i + 1][0], 3,
            SEKANS_ARALIK_M, KANAT_ACISI_DEG,
        )
        gecisler.append((SEKANS_FAZLAR[i], SEKANS_FAZLAR[i + 1], d))
    return gecisler


# =============================================================================
# DENETIM
# =============================================================================

def denetle():
    """(uyarilar, hatalar) doner. Hata varsa yapilandirma tutarsiz."""
    uyari, hata = [], []

    # --- UCAN KADRO ----------------------------------------------------------
    # 15 Agustos 2026'da OLCULDU: beklenen ucak sayisi gercekten ucandan
    # buyukse `formation_reached: active >= beklenen` hicbir zaman dogru
    # olmuyor ve suru FORMING'de takiliyor — hata vermeden, sessizce.
    if BEKLENEN_UCAK != len(UCAN_KADRO):
        hata.append(
            f'BEKLENEN_UCAK ({BEKLENEN_UCAK}) ile UCAN_KADRO uzunlugu '
            f'({len(UCAN_KADRO)}) tutmuyor — suru FORMING-de takilir')
    if UCAN_KADRO and max(UCAN_KADRO) > AJAN_SAYISI:
        hata.append(
            f'UCAN_KADRO en buyuk kimlik ({max(UCAN_KADRO)}) AJAN_SAYISI '
            f'({AJAN_SAYISI}) disinda — o ucak kimlik araliginda yok')
    if len(set(UCAN_KADRO)) != len(UCAN_KADRO):
        hata.append(f'UCAN_KADRO-da tekrar eden kimlik var: {UCAN_KADRO}')
    if len(UCAN_KADRO) < 2:
        uyari.append(
            f'UCAN_KADRO tek ucak ({UCAN_KADRO}) — formasyon ve kacinma '
            f'zincirleri en az iki ajan istiyor')
    # Rutbe kadro SIRASINDAN turuyor: 0=CAPA, 1=YUKARI, 2=birincil ASAGI.
    # Kadro degisince kacis yonu de degisir; sessiz kalmasin.
    if SURU_SABIT_LIDER and SURU_SABIT_LIDER not in UCAN_KADRO:
        hata.append(
            f'SURU_SABIT_LIDER ({SURU_SABIT_LIDER}) UCAN_KADRO {UCAN_KADRO} '
            f'icinde YOK — Gorev 2 profilinde o ucak hic tarif basmaz, '
            f'formasyon SESSIZCE kurulmaz')
    if GOREV_KAMERA_AJAN and GOREV_KAMERA_AJAN not in UCAN_KADRO:
        hata.append(
            f'GOREV_KAMERA_AJAN ({GOREV_KAMERA_AJAN}) UCAN_KADRO {UCAN_KADRO} '
            f'icinde YOK — Gorev 1 formasyonu QR ustune UCMAYAN bir ucagi '
            f'cipalar, QR hic okunmaz ve hata da vermez')
    if GOREV_KAMERA_AJAN and SURU_SABIT_LIDER and \
            GOREV_KAMERA_AJAN != SURU_SABIT_LIDER:
        uyari.append(
            f'kamerali ajan ({GOREV_KAMERA_AJAN}) ile sabit lider '
            f'({SURU_SABIT_LIDER}) FARKLI ucaklar — calisir, ama lider slot '
            f'0 (ortada) iken formasyon merkezi kameraliya gore kayar; '
            f'kuru testte cikis noktalarini gozle dogrula')
    if SURU_SABIT_LIDER and not SURU_LIDER_KILIDI:
        uyari.append(
            'SURU_SABIT_LIDER acik ama SURU_LIDER_KILIDI kapali — sabit '
            'lider zaten devri kapatiyor, kilit gereksiz ama zararsiz')
    if len(UCAN_KADRO) == 2:
        uyari.append(
            f'iki ucakli kadro {UCAN_KADRO}: rutbeler yeniden turuyor — '
            f'ajan {UCAN_KADRO[0]} CAPA, ajan {UCAN_KADRO[1]} YUKARI kacar '
            f'(uc ucakli kadroda sonuncusu ASAGI kaciyordu)')

    # KACINMA ESIKLERI vs FORMASYON GEOMETRISI (KARAR-01 uyarisi)
    #
    # d0, itmenin BASLADIGI mesafe. Ok basi geciside iki ucak zaten
    # KRITIK_AYRIM_M kadar yaklasiyor. d0 ondan buyukse kacinma NORMAL
    # formasyon geciside tetiklenir ve formasyonla cekisir — carpisma
    # olmadigi halde surekli itilme olur.
    if KACINMA_D0_M >= KRITIK_AYRIM_M:
        uyari.append(
            f'kacinma d0 ({KACINMA_D0_M:.1f} m) formasyonun en yakin '
            f'yaklasmasindan ({KRITIK_AYRIM_M:.2f} m) BUYUK — kacinma normal '
            f'gecislerde tetiklenir. ARALIK_M buyut ya da d0 kucult.')
    elif KRITIK_AYRIM_M - KACINMA_D0_M < 1.0:
        uyari.append(
            f'kacinma d0 ({KACINMA_D0_M:.1f} m) ile formasyonun en yakin '
            f'yaklasmasi ({KRITIK_AYRIM_M:.2f} m) arasinda yalniz '
            f'{KRITIK_AYRIM_M - KACINMA_D0_M:.2f} m pay var. Ilk ucusta '
            f'kayittan kacinmanin NE ZAMAN tetiklendigine bak (KARAR-01).')

    # hard, artik YATAY SON CARENIN acildigi kabuk (23 Agustos'ta anlami
    # degisti — bkz. KACINMA ESIKLERI bolumu). MIN_AYRIM'in altinda olmasi
    # ARTIK HATA DEGIL: sinira gelmeden once DIKEY zaten devrede.
    #
    # Kontrol edilecek yeni sart: dikey katman, yatay son carenin acildigi
    # kabuktan BUYUK olmali. Kucukse dikey ayrim tamamlansa bile ucaklar
    # sert kabugun icinde kalir ve yatay itme HER catismada aciliyor
    # demektir — yani "dikey birincil" karari fiilen bozulur.
    if KACINMA_KATMAN_M <= KACINMA_HARD_M:
        hata.append(
            f'dikey katman ({KACINMA_KATMAN_M:.1f} m) yatay son care '
            f'kabugundan ({KACINMA_HARD_M:.1f} m) BUYUK olmali — yoksa '
            f'dikey ayrim tamamlansa bile yatay itme her catismada acilir.')

    # CIKIS ESIGI vs FORMASYON — 24 Agustos 2026 (hist_m 0.5 -> 2.5).
    # Catisma d0'da acilir ama d0+hist'te kapanir. Kapanis esigi
    # formasyonun planli en yakin yaklasmasini asarsa, normal gecisin
    # ACTIGI catisma bir daha KAPANMAZ — merdiven kalici olur. Bu yuzden
    # d0 denetiminin aksine HATA (o "fazladan tetiklenir" der, bu
    # "tetiklenen hic sonmez" der).
    _kacinma_cikis = KACINMA_D0_M + KACINMA_HIST_M
    if _kacinma_cikis >= KRITIK_AYRIM_M:
        hata.append(
            f'kacinma cikis esigi (d0+hist = {_kacinma_cikis:.1f} m) '
            f'formasyonun en yakin yaklasmasinin ({KRITIK_AYRIM_M:.2f} m) '
            f'USTUNDE — normal geciste acilan catisma hic kapanmaz. '
            f'KACINMA_HIST_M kucult ya da ARALIK_M buyut.')
    elif KRITIK_AYRIM_M - _kacinma_cikis < 1.0:
        uyari.append(
            f'kacinma cikis esigi ({_kacinma_cikis:.1f} m) ile formasyonun '
            f'en yakin yaklasmasi ({KRITIK_AYRIM_M:.2f} m) arasinda yalniz '
            f'{KRITIK_AYRIM_M - _kacinma_cikis:.2f} m pay var.')

    # 🔴 PX4 SESSIZ KIRPMA DENETIMI — 23 Agustos 2026.
    # Kacinmanin dikey komutu PX4 tavanini asarsa PX4 kirpar ve HICBIR YERDE
    # uyari cikmaz: ayar ve log istenen degeri gosterir, ucak baskasini yapar.
    if KACINMA_DIKEY_HIZ_MPS > PX4_DIKEY_HIZ_TAVANI_MPS + 1e-9:
        hata.append(
            f'kacinma dikey hizi ({KACINMA_DIKEY_HIZ_MPS:.1f} m/s) PX4 '
            f'tavanindan ({PX4_DIKEY_HIZ_TAVANI_MPS:.1f} m/s, '
            f'MPC_Z_VEL_MAX_UP) BUYUK — PX4 sessizce kirpar. Once PX4 '
            f'parametresini yukselt.')
    if KACINMA_DIKEY_IVME_MPS2 > PX4_DIKEY_IVME_TAVANI_MPS2 + 1e-9:
        hata.append(
            f'kacinma dikey ivmesi ({KACINMA_DIKEY_IVME_MPS2:.1f} m/s2) '
            f'MPC_ACC_UP_MAX ({PX4_DIKEY_IVME_TAVANI_MPS2:.1f}) USTUNDE.')
    if KACINMA_DIKEY_IVME_MPS2 > PX4_DIKEY_INIS_IVME_TAVANI_MPS2 + 1e-9:
        uyari.append(
            f'kacinma dikey ivmesi ({KACINMA_DIKEY_IVME_MPS2:.1f} m/s2) '
            f'MPC_ACC_DOWN_MAX ({PX4_DIKEY_INIS_IVME_TAVANI_MPS2:.1f}) '
            f'USTUNDE — ASAGI kacan ucak (cift rutbe) kirpilir.')
    # Dikey merdivenin kurulma suresi, catisma suresinden kisa olmali.
    _t_merdiven = (KACINMA_KATMAN_M / KACINMA_DIKEY_HIZ_MPS
                   + KACINMA_DIKEY_HIZ_MPS / KACINMA_DIKEY_IVME_MPS2)
    _t_catisma = KACINMA_D0_M / max(0.1, 2.0 * GOREV_HIZ_MPS)
    if _t_merdiven > _t_catisma:
        uyari.append(
            f'dikey merdiven {_t_merdiven:.1f} saniyede kuruluyor ama kafa '
            f'kafaya kapanma {_t_catisma:.1f} sn suruyor — en yakin anda '
            f'ayrimin TAMAMI olusmus olmayacak (beklenen davranis, '
            f'ucus oncesi bilinmeli).')
    if not KACINMA_HARD_M < KACINMA_D0_M:
        hata.append(
            f'kacinma hard ({KACINMA_HARD_M:.1f}) < d0 ({KACINMA_D0_M:.1f}) '
            f'olmali — collision_avoidance bu sartI kendi de dogruluyor.')

    # DOYGUNLUK PAYI — KAYMANIN SIFIR KALMASININ TEK SARTI.
    #
    # Kalici kaymanin sifir olmasi "v_ff + Kp x hata" toplaminin
    # MPC_XY_VEL_MAX tavanini ASMAMASINA bagli. Seyir hizi tavana esitse
    # konum duzeltmesine HIC yer kalmaz: PX4 kirpar, hata kapanamaz ve
    # kayma geri gelir.
    #     seyir 3.0 / tavan 5.0  -> duzeltmeye 2.0 m/s pay   iyi
    #     seyir 5.0 / tavan 5.0  -> duzeltmeye 0 pay         kayma garanti
    # Bkz. docs/PLAN.md §9 (doygunluk payi). Bu yuzden UYARI degil HATA.
    if PX4_HIZ_TAVANI_MPS < GOREV_HIZ_MPS * 1.5:
        hata.append(
            f'PX4 tavani ({PX4_HIZ_TAVANI_MPS}) gorev hizinin '
            f'({GOREV_HIZ_MPS}) en az 1.5 katI olmali '
            f'(su an {PX4_HIZ_TAVANI_MPS / GOREV_HIZ_MPS:.2f}x). '
            f'Konum duzeltmesine pay kalmazsa KAYMA geri gelir; '
            f'ayrica kacinmanin kacis manevrasi icin de yer gerekiyor. '
            f'Tavani {GOREV_HIZ_MPS * 1.5:.1f} yap ya da hizi dusur.')

    if PX4_IVME_MPS2 < GOREV_IVME_MPS2:
        hata.append(
            f'MPC_ACC_HOR ({PX4_IVME_MPS2}) yurutucu ivmesinden '
            f'({GOREV_IVME_MPS2}) kucuk — PX4 yurutucuyu takip edemez')

    if CARPISMA_PAYI_M <= 0:
        hata.append(
            f'kritik ayrim ({KRITIK_AYRIM_M:.2f} m) esigin '
            f'({MIN_AYRIM_M} m) ALTINDA — plan dogrulamayi gecmez')
    elif ARALIK_M < gereken_aralik_m(GOREV_HIZ_MPS):
        uyari.append(
            f'aralik {ARALIK_M:.1f} m, bu hizda gereken '
            f'{gereken_aralik_m(GOREV_HIZ_MPS):.1f} m. ARALIK_M buyut ya da '
            f'hizi dusur.')

    if MAKS_EGIM_DEG <= EGIM_TAVANI_DEG:
        hata.append(
            'devrilme dedektoru esigi egim tavaninin altinda — normal ucus '
            'ariza sayilir ve gorev kendini havada iptal eder')

    if TOLERANS_M < izleme_gecikmesi_m(GOREV_HIZ_MPS) * 1.5:
        uyari.append(
            f'varis tolerans {TOLERANS_M} m, izleme gecikmesi '
            f'{izleme_gecikmesi_m(GOREV_HIZ_MPS):.2f} m — ucak "vardim" '
            f'demeden once uzun sure salinabilir')

    # --- FORMASYON GECIS TESTI (gecici senaryo) ------------------------------
    # Sabit haller: uc formasyonda da en yakin cift = SEKANS_ARALIK_M.
    # Gecis anlari asagida faz cifti basina denetlenir. Esikler:
    #   MIN_AYRIM_M altina inen nominal gecis -> HATA (plan bastan yanlis)
    #   d0+1 m altina inen -> UYARI (takip hatasi ~1 m ile kacinma
    #   tetiklenebilir — tehlike degil, bilinerek uculur ve kayittan bakilir)
    if SEKANS_ARALIK_M < MIN_AYRIM_M:
        hata.append(
            f'sekans araligi ({SEKANS_ARALIK_M:.1f} m) MIN_AYRIM '
            f'({MIN_AYRIM_M:.1f} m) altinda')
    _cikis = KACINMA_D0_M + KACINMA_HIST_M
    if SEKANS_ARALIK_M <= _cikis:
        hata.append(
            f'sekans araligi ({SEKANS_ARALIK_M:.1f} m) kacinma cikis '
            f'esiginin ({_cikis:.1f} m) altinda/esiginde — sabit halde bile '
            f'acilan catisma kapanmaz')
    elif SEKANS_ARALIK_M - _cikis < 1.0:
        uyari.append(
            f'sekans araligi ({SEKANS_ARALIK_M:.1f} m) ile kacinma cikis '
            f'esigi ({_cikis:.1f} m) arasinda yalniz '
            f'{SEKANS_ARALIK_M - _cikis:.1f} m pay var — kacinma acilirsa '
            f'merdiven uzun surer, kayittan avoid sayacina bakilmali')
    _gecisler = _sekans_geometri()
    if _gecisler is None:
        uyari.append(
            'sekans gecis geometrisi denetlenemedi: swarm_core yuklenemedi '
            '(formasyon_sekans_cekirdek). Depo agacinin disinda misin?')
    else:
        for _a, _b, _d in _gecisler:
            if _d < MIN_AYRIM_M:
                hata.append(
                    f'sekans gecisi {_a}->{_b}: nominal en yakin cift '
                    f'{_d:.2f} m < MIN_AYRIM {MIN_AYRIM_M:.1f} m')
            elif _d < KACINMA_D0_M + 1.0:
                uyari.append(
                    f'sekans gecisi {_a}->{_b}: nominal en yakin cift '
                    f'{_d:.2f} m; kacinma girisine (d0={KACINMA_D0_M:.1f} m) '
                    f'pay {_d - KACINMA_D0_M:.2f} m — ~1 m takip hatasiyla '
                    f'kacinma tetiklenebilir (bilinerek ucul)')

    # --- YAW HIZI vs SEYIR TAVANI (1 Eylul 2026) ----------------------------
    # Turetme dogru calisiyor mu; biri sabiti elle ezerse yakalansin.
    _teget = MOD_ARALIK_M * math.radians(MOD_YAW_HIZI_DEG_S)
    if _teget > MOD_HIZ_MPS + 1e-6:
        hata.append(
            f'MOD_YAW_HIZI {MOD_YAW_HIZI_DEG_S:.1f} deg/s, {MOD_ARALIK_M:.1f} m '
            f'slot yaricapinda {_teget:.2f} m/s teget hiz ister; seyir tavani '
            f'{MOD_HIZ_MPS:.1f} m/s. Formasyon donus BOYUNCA dagilir. '
            f'En fazla {math.degrees(MOD_HIZ_MPS / MOD_ARALIK_M):.1f} deg/s.')

    # --- FORMASYON MORF HIZI vs KACINMA PAYI (1 Eylul 2026) -----------------
    # Morf sirasinda iki ucak birbirine dogru gidiyorsa kapanma hizi 2*v.
    # Kacinma o hizi durdurana kadar v^2/2a yol alir; geriye kalan pay
    # MIN_AYRIM_M'nin altina inmemeli.
    _kapanma = 2.0 * MOD_MORF_HIZ_MPS
    _fren = _kapanma ** 2 / (2.0 * KACINMA_IVME_NORMAL_MPS2)
    _kalan = KACINMA_D0_M - _fren
    if _kalan < 2.0:
        hata.append(
            f'MOD_MORF_HIZ {MOD_MORF_HIZ_MPS:.2f} m/s ile kapanma '
            f'{_kapanma:.2f} m/s, frenleme {_fren:.2f} m — kacinma '
            f'esiginden ({KACINMA_D0_M:.1f} m) geriye {_kalan:.2f} m '
            f'kaliyor. 31 Agustos ucusunda bu sayi 1,62 m idi ve ucaklar '
            f'1,65 m\'ye yaklasti.'
        )
    elif _kalan < 3.0:
        uyari.append(
            f'MOD_MORF_HIZ {MOD_MORF_HIZ_MPS:.2f} m/s: morfta kacinmaya '
            f'{_kalan:.2f} m pay kaliyor (3 m alti dar)'
        )
    if MOD_MORF_HIZ_MPS > MOD_HIZ_MPS:
        hata.append(
            f'MOD_MORF_HIZ ({MOD_MORF_HIZ_MPS:.2f}) seyir hizindan '
            f'({MOD_HIZ_MPS:.1f}) BUYUK — morfun daha yavas olmasi gerekir')

    # --- MOD IVMESI vs EGIM TAVANI (B6, 31 Agustos 2026) --------------------
    # 🔴 BU DENETIM YAZILMISTI AMA CALISMIYORDU: liste adi `hatalar`
    # yazilmis, oysa fonksiyondaki ad `hata`. Kosul saglanmadigi icin
    # (1.30 < 1.31) satira hic girilmemis ve NameError GORUNMEMISTI —
    # ivme bir gun buyutulseydi denetim uyarmak yerine COKERDI.
    # Tam olarak "hata vermeden yanlis sonuc" sinifi.
    _mod_izin = ivme_icin(MOD_EGIM_TAVANI_DEG) / EGIM_PAY_KATI
    if MOD_IVME_MPS2 > _mod_izin + 1e-6:
        hata.append(
            f'MOD_IVME {MOD_IVME_MPS2:.2f} m/s2, egim tavani '
            f'{MOD_EGIM_TAVANI_DEG:.0f} deg ile izin verilen '
            f'{_mod_izin:.2f} m/s2 USTUNDE — pay kati {EGIM_PAY_KATI} '
            f'korunmuyor, ruzgarda konum tutulamaz.'
        )

    # --- GOREV 2 KALKIS OLCUTU vs YAYIN KAPISI (madde 25) -------------------
    # mode_manager TAKEOFF'u "tum ucaklar hedefin %80'ini gecti" ile
    # bitiriyor (_KALKIS_ULASMA_ORANI), yayin izni ise MOD_KALKIS_ESIK'te
    # aciliyor. Bitis olcutu kapinin ALTINDA kalirsa suru READY'ye gecer
    # ama kapi kapali oldugu icin HICBIR SEY YAYINLAMAZ — hicbir hata
    # gorunmeden asili kalir.
    _mod_ulasma = MOD_KALKIS_IRTIFA_M * 0.8
    if _mod_ulasma <= MOD_KALKIS_ESIK_M:
        hata.append(
            f'MOD_KALKIS_IRTIFA {MOD_KALKIS_IRTIFA_M:.1f} m -> ulasma olcutu '
            f'{_mod_ulasma:.1f} m, yayin kapisi MOD_KALKIS_ESIK '
            f'{MOD_KALKIS_ESIK_M:.1f} m ustunde DEGIL — suru READY olur ama '
            f'kapi kapali kalir')

    # SwC debounce esigi olculen gecis tavaninin (342 ms) ustunde mi?
    _SWC_OLCULEN_TAVAN_MS = 852.0      # 31 Agu, yeni kumanda (en kotu)
    if MOD_SWC_DEBOUNCE_MS <= _SWC_OLCULEN_TAVAN_MS:
        hata.append(
            f'MOD_SWC_DEBOUNCE {MOD_SWC_DEBOUNCE_MS:.0f} ms, olculen en uzun '
            f'SwC gecisi {_SWC_OLCULEN_TAVAN_MS:.0f} ms — gecerken SAHTE '
            f'formasyon degisimi tetiklenir (madde 26)')
    elif MOD_SWC_DEBOUNCE_MS - _SWC_OLCULEN_TAVAN_MS < 100.0:
        uyari.append(
            f'MOD_SWC_DEBOUNCE ile olculen gecis tavani arasinda yalniz '
            f'{MOD_SWC_DEBOUNCE_MS - _SWC_OLCULEN_TAVAN_MS:.0f} ms pay var')

    return uyari, hata


# =============================================================================
# CIKTILAR
# =============================================================================

def _cozumleme() -> int:
    g = '\033[32m'; k = '\033[31m'; s = '\033[33m'; kl = '\033[1m'; z = '\033[0m'
    if not sys.stdout.isatty():
        g = k = s = kl = z = ''

    print(f'\n{kl}=== UCUS AYARLARI ==={z}\n')
    print(f'{kl}GIRDILER{z}')
    print(f'  gorev seyir hizi      {GOREV_HIZ_MPS:6.2f} m/s')
    print(f'  gorev ivmesi          {GOREV_IVME_MPS2:6.2f} m/s²')
    print(f'  dikey hiz             {GOREV_DIKEY_HIZ_MPS:6.2f} m/s')
    print(f'  PX4 hiz tavani        {PX4_HIZ_TAVANI_MPS:6.2f} m/s   (MPC_XY_VEL_MAX)')
    print(f'  kumanda POSCTL hizi   {KUMANDA_HIZI_MPS:6.2f} m/s   (MPC_VEL_MANUAL)')
    print(f'  PX4 ivme siniri       {PX4_IVME_MPS2:6.2f} m/s²  (MPC_ACC_HOR)')
    print(f'  formasyon araligi     {ARALIK_M:6.2f} m')
    print(f'  en kucuk ayrim        {MIN_AYRIM_M:6.2f} m')

    print(f'\n{kl}TURETILEN ACILAR{z}')
    print(f'  en buyuk komut ivmesi {EN_BUYUK_IVME_MPS2:6.2f} m/s²'
          f'  -> gereken egim {GEREKEN_EGIM_DEG:.1f}°')
    print(f'  pay kati x{EGIM_PAY_KATI:.1f}'
          f'            -> {kl}MPC_TILTMAX_AIR = {EGIM_TAVANI_DEG:.0f}°{z}'
          f'  ({ivme_icin(EGIM_TAVANI_DEG):.2f} m/s² saglar)')
    print(f'  dedektor payi +{DEDEKTOR_PAY_DEG:.0f}°'
          f'         -> {kl}MAKS_EGIM_DEG = {MAKS_EGIM_DEG:.0f}°{z}')

    print(f'\n{kl}MESAFELER{z}')
    print(f'  izleme gecikmesi      {izleme_gecikmesi_m(GOREV_HIZ_MPS):6.2f} m'
          f'   (olculdu: {IZLEME_GECIKME_S} s x hiz)')
    print(f'  kritik ayrim          {KRITIK_AYRIM_M:6.2f} m'
          f'   (= aralik x cos{KANAT_ACISI_DEG:.0f}°)')
    _ger = gereken_aralik_m(GOREV_HIZ_MPS)
    pay_renk = g if ARALIK_M >= _ger else s
    print(f'  {pay_renk}carpisma payi         {CARPISMA_PAYI_M:6.2f} m{z}'
          f'   (kritik - esik; bu hizda gereken aralik {_ger:.1f} m)')
    print(f'  frenleme (kacinma)    {FRENLEME_TAVAN_M:6.2f} m'
          f'   (PX4 tavaninda, kacis manevrasi icin)')
    print(f'  kacinma giris/cikis   {KACINMA_D0_M:6.2f} m / '
          f'{KACINMA_D0_M + KACINMA_HIST_M:.2f} m'
          f'   (d0 / d0+hist; donus ancak cikista baslar)')

    # ROTA SEKILLENDIRME — fiili donus hizi formasyon BOYUTUNDAN turiyor.
    # Kanattaki ucak en hizli hareket eden; aci_hizi = teget_hiz / yaricap.
    # Bu yuzden ayni ayarla 12 m formasyon 4 m'lik olandan cok daha yavas
    # doner. Operatorun gorecegi sayi bu, parametre degil.
    _yaricap = ARALIK_M
    _fiili_donus = min(MAKS_HEADING_DONUS_DEG_S,
                       math.degrees(ROT_TEGET_HIZ_MPS / _yaricap))
    print(f'\n{kl}ROTA SEKILLENDIRME{z}  (path_planner)')
    print(f'  merkez rampa hizi     {GOREV_HIZ_MPS:6.2f} m/s')
    print(f'  teget hiz (kanat)     {ROT_TEGET_HIZ_MPS:6.2f} m/s'
          f'   (seyrin yarisi, kalan yari duzeltmelere pay)')
    print(f'  donus tavani          {MAKS_HEADING_DONUS_DEG_S:6.1f} deg/s'
          f'   (PX4 yaw tavaniyla ayni)')
    print(f'  FIILI donus hizi      {_fiili_donus:6.2f} deg/s'
          f'   ({ARALIK_M:.0f} m yaricapta)')
    print(f'  180 derece donus      {180.0 / _fiili_donus:6.1f} s')

    print(f'\n{kl}HIZ SECENEKLERI{z}  (aralik {ARALIK_M:.0f} m)')
    print(f'  {"hiz":>5}  {"gecikme":>8}  {"gereken aralik":>15}  durum')
    for v in (2.0, 3.0, 4.0, 5.0, 6.0):
        gec = izleme_gecikmesi_m(v)
        ger = gereken_aralik_m(v)
        if ger > ARALIK_M:
            d, r = f'aralik {ger:.1f} m olmali', s
        else:
            d, r = 'yeterli', g
        im = ' <-' if abs(v - GOREV_HIZ_MPS) < 0.01 else '   '
        print(f'  {v:5.1f}  {gec:7.2f} m  {ger:14.1f} m  {r}{d}{z}{im}')
    rampa = GOREV_HIZ_MPS ** 2 / GOREV_IVME_MPS2
    print(f'\n  Bilgi: {GOREV_HIZ_MPS:.1f} m/s\'e hizlanip yavaslamak '
          f'{rampa:.1f} m suruyor.')
    print(f'  {TIPIK_BACAK_M:.0f} m\'lik bir bacakta '
          f'{max(0.0, TIPIK_BACAK_M - rampa):.1f} m seyir kaliyor '
          f'(bacak boyu senaryoya gore degisir).')

    _gecisler = _sekans_geometri()
    print(f'\n{kl}FORMASYON GECIS TESTI{z}  (gecici senaryo — '
          f'aralik {SEKANS_ARALIK_M:.1f} m, irtifa {SEKANS_IRTIFA_M:.1f} m)')
    print(f'  sekans                {" -> ".join(SEKANS_FAZLAR)}'
          f'   (sureler {", ".join(f"{s:g} s" for s in SEKANS_FAZ_SURE_S)})')
    if _gecisler is not None:
        for _a, _b, _d in _gecisler:
            r = g if _d >= KACINMA_D0_M + 1.0 else s
            print(f'  {_a}->{_b:<18} en dar an {r}{_d:5.2f} m{z}'
                  f'   (kacinma girisi {KACINMA_D0_M:.1f} m)')

    uyari, hata = denetle()
    print()
    for h in hata:
        print(f'{k}HATA : {h}{z}')
    for u in uyari:
        print(f'{s}UYARI: {u}{z}')
    if not hata and not uyari:
        print(f'{g}Yapilandirma tutarli.{z}')
    print()
    return 1 if hata else 0


def _kabuk():
    """baslat.sh'in kaynak alabilecegi env satirlari."""
    print('# ucus_ayarlari.py tarafindan URETILDI — elle degistirme.')
    print('# Degisiklik icin src/gcs/ucus_ayarlari.py duzenle ve yeniden uret.')
    print(f'GUIDED_HIZ_YATAY={GOREV_HIZ_MPS}')
    print(f'GUIDED_HIZ_DIKEY={GOREV_DIKEY_HIZ_MPS}')
    print(f'GUIDED_IVME_YATAY={GOREV_IVME_MPS2}')
    print(f'GUIDED_IVME_DIKEY={GOREV_DIKEY_IVME_MPS2}')
    print(f'KANAT_ALFA_DEG={KANAT_ACISI_DEG}')
    # UCAN KADRO — baslat.sh bunlari okumazsa varsayilani "1 2 3" / 3 olur
    # ve iki ucakla ucarken suru FORMING'de takilir (bkz. UCAN_KADRO notu).
    print(f'SURU_KADRO="{" ".join(str(k) for k in UCAN_KADRO)}"')
    print(f'SURU_BEKLENEN_UCAK={BEKLENEN_UCAK}')
    print(f'SURU_AJAN_SAYISI={AJAN_SAYISI}')
    print(f'GOREV_NAVIGATE_TIMEOUT_S={GOREV_NAVIGATE_TIMEOUT_S}')
    print(f'GOREV_ROTA_BILINMEYEN_S={GOREV_ROTA_BILINMEYEN_S}')
    print(f'GOREV_FORMASYON={GOREV_FORMASYON}')
    print(f'GOREV_ARALIK={GOREV_ARALIK_M:.1f}')
    print(f'GOREV_TOPLANMA_KATMAN={GOREV_TOPLANMA_KATMAN_M:.1f}')
    print(f'GOREV_DONUS_YAW={GOREV_DONUS_YAW_DEG:.1f}')
    print(f'GOREV_DONUS_KATMAN={GOREV_DONUS_KATMAN_M:.1f}')
    print(f'GOREV_DAGILMA_HIZ={GOREV_DAGILMA_HIZ_MPS:.1f}')
    print(f'GOREV_KURULUM_HIZ={GOREV_KURULUM_HIZ_MPS:.1f}')
    print(f'SURU_LIDER_KILIDI={str(SURU_LIDER_KILIDI).lower()}')
    print(f'SURU_LIDER_KILIT_TAM_KADRO_S={SURU_LIDER_KILIT_TAM_KADRO_S:.1f}')
    print(f'SURU_SABIT_LIDER={SURU_SABIT_LIDER}')
    print(f'SURU_KALKIS_OLAYLA={"true" if KALKIS_OLAYLA else "false"}')
    print(f'GOREV_KALKIS_IRTIFA={GOREV_KALKIS_IRTIFA_M}')
    print(f'GOREV_QR_OKUMA_IRTIFA={GOREV_QR_OKUMA_IRTIFA_M}')
    print(f'GOREV_KAMERA_AJAN={GOREV_KAMERA_AJAN}')
    # (Pil satirlari asagida, INA226 blogunda — INA226_HUCRE orada.)
    # path_planner (rota sekillendirme)
    print(f'ROTA_MAKS_HIZ={GOREV_HIZ_MPS}')
    print(f'ROTA_ADIM_HZ={ROTA_ADIM_HZ}')
    print(f'ROTA_DIKEY_HIZ={ROTA_DIKEY_HIZ_MPS}')
    print(f'ROTA_DONUS_TAVANI_DEG_S={MAKS_HEADING_DONUS_DEG_S}')
    print(f'ROTA_TEGET_HIZ={ROT_TEGET_HIZ_MPS}')
    print(f'ROTA_TEGET_IVME={ROT_TEGET_IVME_MPS2}')
    # Kacinma — basit_kacinma VE collision_avoidance ayni degerleri alir.
    # Dugum degistiginde esikler degismesin diye tek kaynak burasi.
    print(f'KACINMA_D0={KACINMA_D0_M}')
    print(f'KACINMA_DIKEY_BEKLE={KACINMA_DIKEY_BEKLE:.2f}')
    # Kacinma ivme sinirlari — 22 Agustos 2026'da EKLENDI. Oncesinde
    # ca_core'daki sabitler kullaniliyordu ve slew_emergency 30 m/s2 idi
    # (71.9 derece egim = imkansiz). Ucakta 34 derece yalpa olculdu.
    print(f'KACINMA_IVME_NORMAL={KACINMA_IVME_NORMAL_MPS2:.2f}')
    print(f'KACINMA_IVME_ACIL={KACINMA_IVME_ACIL_MPS2:.2f}')
    print(f'KACINMA_DONUS_IVME={KACINMA_DONUS_IVME_MPS2:.2f}')
    print(f'KACINMA_HARD={KACINMA_HARD_M}')
    print(f'KACINMA_KATMAN={KACINMA_KATMAN_M}')
    print(f'KACINMA_HIST={KACINMA_HIST_M}')
    print(f'KACINMA_DONUS_BEKLEME={KACINMA_DONUS_BEKLEME_S}')
    print(f'KACINMA_DONUS_HIZ={KACINMA_DONUS_HIZ_MPS}')
    print(f'KACINMA_DONUS_SOGUMA={KACINMA_DONUS_SOGUMA_S}')
    print(f'KACINMA_KORLUK_YER={KACINMA_KORLUK_YER_M}')
    print(f'KACINMA_DIKEY_HIZ={KACINMA_DIKEY_HIZ_MPS}')
    print(f'KACINMA_DIKEY_IVME={KACINMA_DIKEY_IVME_MPS2}')
    print(f'KACINMA_DIKEY_KP={KACINMA_DIKEY_KP}')
    print(f'KACINMA_BAYAT_S={KACINMA_BAYAT_S}')
    # Formasyon gecis testi — GECICI (formasyon_sekans_node, `sekans` anahtari)
    print(f'SEKANS_ARALIK={SEKANS_ARALIK_M}')
    print(f'SEKANS_IRTIFA={SEKANS_IRTIFA_M}')
    print(f'SEKANS_FAZLAR={",".join(SEKANS_FAZLAR)}')
    print('SEKANS_FAZ_SURELERI='
          + ','.join(f'{s:g}' for s in SEKANS_FAZ_SURE_S))
    print(f'SEKANS_KURULUM_HIZ={SEKANS_KURULUM_HIZ_MPS}')
    print(f'SEKANS_GECIS_HIZ={SEKANS_GECIS_HIZ_MPS}')
    print(f'SEKANS_KALKIS_ESIK={SEKANS_KALKIS_ESIK_ORANI}')
    # :.1f, :g DEGIL — %g tam sayilari noktasiz basar ('90'), ros2 -p bunu
    # INTEGER sayar ve double bekleyen declare dugumu oldurur (28 Agu,
    # sahada olculdu). Dugum artik dynamic_typing ile toleransli ama
    # uretici de duzgun bassin: ayni tuzaga baska tuketici dusmesin.
    print(f'SEKANS_KALKIS_ZAMAN_ASIMI={SEKANS_KALKIS_ZAMAN_ASIMI_S:.1f}')
    print(f'SEKANS_EVE_SURE={SEKANS_EVE_SURE_S:.1f}')
    # Gorev 2 yari otonom mod (mode_manager + joystick_interpreter)
    print(f'MOD_EGIM_TAVANI={MOD_EGIM_TAVANI_DEG:.1f}')
    print(f'MOD_YAW_HIZI={MOD_YAW_HIZI_DEG_S:.1f}')
    print(f'MOD_HIZ={MOD_HIZ_MPS:.1f}')
    print(f'MOD_MORF_HIZ={MOD_MORF_HIZ_MPS:.2f}')
    print(f'MOD_MORF_SURE={MOD_MORF_SURE_S:.1f}')
    print(f'MOD_ARALIK={MOD_ARALIK_M:.1f}')
    print(f'MOD_DEADMAN_ZAMAN_ASIMI={MOD_DEADMAN_ZAMAN_ASIMI_S:.1f}')
    print(f'MOD_KALKIS_ESIK={MOD_KALKIS_ESIK_M:.1f}')
    print(f'MOD_KALKIS_IRTIFA={MOD_KALKIS_IRTIFA_M:.1f}')
    print(f'MOD_IVME={MOD_IVME_MPS2:.2f}')
    print(f'MOD_DIKEY_IVME={MOD_DIKEY_IVME_MPS2:.2f}')
    print(f'INA226_ADRES={PIL_INA226_ADRES}')
    print(f'INA226_HUCRE={PIL_HUCRE_SAYISI}')
    print(f'INA226_SONT_OHM={PIL_SONT_OHM}')
    # Gosterge uclari (paket gerilimi) + FSM kesme esigi. Bkz. PIL_* notu.
    print(f'PIL_BOS_V={PIL_BOS_V}')
    print(f'PIL_DOLU_V={PIL_DOLU_V}')
    print(f'BATARYA_KRITIK_V={PIL_KRITIK_V}')
    print(f'BATARYA_KESME={"true" if PIL_KESME_AKTIF else "false"}')
    print(f'MOD_GAZ_MERKEZ_PAY={MOD_GAZ_MERKEZ_PAY:.2f}')
    print(f'MOD_SWC_DEBOUNCE_MS={MOD_SWC_DEBOUNCE_MS:.1f}')


def _px4():
    """Her ucakta calistirilacak parametre komutlari."""
    print('# Her ucak icin <N> yerine agent_id koy (ylp00->1, ylp01->2, ylp02->3)')
    print('# MAV_SYS_ID BURADA YOK — ucaga OZGU olmali, esitlenmez.')
    for ad, deger in (
            ('MPC_XY_VEL_MAX', f'{PX4_HIZ_TAVANI_MPS:.1f}'),
            ('MPC_VEL_MANUAL', f'{KUMANDA_HIZI_MPS:.1f}'),
            ('MPC_ACC_HOR', f'{PX4_IVME_MPS2:.1f}'),
            ('MPC_TILTMAX_AIR', f'{EGIM_TAVANI_DEG:.1f}'),
            ('MPC_YAWRAUTO_MAX', f'{PX4_DONUS_HIZI_DEG_S:.1f}'),
    ):
        print(f'ros2 param set /drone_<N>/mavros/param {ad} {deger}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Ucus ayarlari — tek kaynak')
    ap.add_argument('--kabuk', action='store_true', help='baslat.sh icin env')
    ap.add_argument('--px4', action='store_true', help='ros2 param set komutlari')
    a = ap.parse_args()
    if a.kabuk:
        _kabuk()
        return 0
    if a.px4:
        _px4()
        return 0
    return _cozumleme()


if __name__ == '__main__':
    sys.exit(main())
