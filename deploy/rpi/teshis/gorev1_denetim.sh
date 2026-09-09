#!/bin/bash
# Copyright 2026 Yelpence
# ============================================================================
# GÖREV 1 UÇUŞ DENETİMİ — bir uçuşun tüm açık sorularını TEK komutla cevaplar
#
# NİYE VAR (9 Eylül 2026, finale saatler kala)
# ------------------------------------------
# 8-9 Eylül gecesi her uçuştan sonra aynı sorular soruldu ve her seferinde
# elle grep yazıldı: "w beklendi mi", "adımlar gerçekten tamamlandı mı",
# "süpürme dur-kalk yaptı mı", "QR kabul edildi mi", "slot ataması çalıştı
# mı". Beş ayrı SSH turu, her biri liderin yavaş bağlantısında dakikalar.
# Bu betik hepsini tek turda basar.
#
# KULLANIM (liderin konteynerinde — QR'ı okuyan ve komutu üreten o):
#     ./deploy/yki/drone_bul.sh ylp00 \
#         'docker exec drone1 bash -s' < deploy/rpi/teshis/gorev1_denetim.sh
#
# Eski bir uçuşa bakmak için dizini argüman ver:
#     ... 'docker exec drone1 bash -s' < ... /ws/gunluk/20260909_034512
# ============================================================================
DIZIN="${1:-/ws/gunluk/son}"
M="$DIZIN/mission1.log"
F="$DIZIN/mission_fsm.log"

echo "=== $DIZIN ==="
[ -f "$M" ] || { echo "mission1.log yok"; exit 1; }

# Damgayi saate cevir: [1788899263.23] -> 02:47:43
sa() { awk '{ if (match($0, /\[17[0-9]{8}\.[0-9]+\]/)) {
        d = substr($0, RSTART+1, RLENGTH-2); "date -d @" d " +%H:%M:%S" | getline t;
        sub(/\[17[0-9]{8}\.[0-9]+\]/, t); } print }'; }

echo
echo "--- ① QR KABULU (beklenen QR kapisi calisiyor mu) ---"
grep -hE 'QR kabul edildi|BEKLENMEYEN QR|Ilk hedef|Sonraki hedef' "$F" 2>/dev/null | sa | cut -c1-140
echo "   (BEKLENMEYEN QR satiri = yol ustunde okunan yabanci QR ATLANDI)"

echo
echo "--- ② QR ADIMLARI ve w BEKLEMESI ---"
grep -hE 'QR adimi|bitti — .* sn tutuluyor|QR noktasinda bekleniyor|Gec QR alindi' "$F" 2>/dev/null | sa | cut -c1-140
echo "   BEKLENEN: her adimdan sonra 'X sn tutuluyor', sonra sonraki adim."
echo "   Sartname: form -> w -> manevra -> w -> irtifa -> w -> sonraki QR"

echo
echo "--- ③ ADIM GERCEKTEN OTURDU MU (8 Eylul kusuru) ---"
grep -hE 'Formasyon kuruldu|Rotasyon tamamlandı|slot hatası büyük|varış event' "$M" 2>/dev/null | sa | cut -c1-140
echo "   🔴 'slot hatası büyük' = tolerans tutmadi, 30 sn zaman asimiyla ilerledi."
echo "   Temiz uçusta bu satir HIC olmamali."

echo
echo "--- ④ MANEVRA (pitch/roll gercekten gonderildi mi) ---"
grep -hE 'Manevra gönderildi' "$M" 2>/dev/null | sa | cut -c1-140
echo "   Resmi QR'larda aralik ±15°. 8 m aralikta 15° = 2.1 m dikey yayilim."

echo
echo "--- ⑤ SUPURME (cerceve ofseti ve dur-kalk) ---"
grep -hE 'cerceve ofseti' "$M" 2>/dev/null | sa | cut -c1-140
n=$(grep -c 'supurme BEKLIYOR' "$M" 2>/dev/null)
echo "   supurme BEKLIYOR sayisi: ${n:-0}"
echo "   BEKLENEN: ofset ~0 (origin duzeltildi), BEKLIYOR sayisi 0'a yakin."
echo "   Cok sayida BEKLIYOR = takip tavani (5 m) hala dar demektir."
grep -hE 'supurme BEKLIYOR' "$M" 2>/dev/null | tail -2 | sa | cut -c1-140

echo
echo "--- ⑥ SLOT YENIDEN ATAMA (180° donuste kanat degistirme) ---"
grep -hE 'SLOT YENIDEN ATAMA' "$M" 2>/dev/null | sa | cut -c1-150
echo "   Bu satir yoksa: ya buyuk baslik degisimi olmadi, ya kadro eksikti."

echo
echo "--- ⑦ KADRO (aktif ajan listesi cokuyor mu) ---"
k=$(grep -c 'KADRO SIFIRLANDI' "$M" 2>/dev/null)
echo "   KADRO SIFIRLANDI sayisi: ${k:-0}"
grep -hE 'KADRO EKSIK' "$DIZIN/swarm_fsm.log" 2>/dev/null | tail -3 | sa | cut -c1-150

echo
echo "--- ⑧ DONUS ve BITIS ---"
grep -hE 'RETURN_HOME:|donus faz|MISSION_COMPLETE' "$M" "$F" 2>/dev/null | tail -6 | sa | cut -c1-140
echo
echo "--- ⑨ COKME / HATA ---"
grep -hcE 'Traceback|Error' "$M" "$F" 2>/dev/null | paste -sd' ' - | sed 's/^/   mission1 ve mission_fsm hata satiri: /'
