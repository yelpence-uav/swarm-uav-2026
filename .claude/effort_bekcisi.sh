#!/usr/bin/env bash
# Effort bekcisi — KARAR-02
#
# Yelpence kurali: ucusa dokunan is `max` effort ile yapilir, ultracode
# menuden acilmaz (bkz. docs/KARARLAR.md KARAR-02). Bu betik her kullanici
# mesajinda (UserPromptSubmit hook) calisir ve seviye max degilse uyarir.
#
# NEDEN BOYLE KARISIK: 15 Agustos 2026'da hook ortami olculdu (68 degisken) —
#   * $CLAUDE_EFFORT Bash aracinda CANLI ve dogru, ama hook ortaminda HIC YOK.
#     Ilk deneme bunu varsaymisti ve max'tayken bile "bilinmiyor" diye
#     bagiriyordu. Buradan okunamaz.
#   * Hook'ta $CLAUDE_PROJECT_DIR ve $CLAUDE_CODE_SESSION_ID VAR — transkripti
#     tahmin etmeden bulmak icin ikisi de kullaniliyor.
#   * Seviye transkriptte her `assistant` kaydinda "effort":"..." olarak
#     yaziyor. Oradan okunabiliyor ama BIR TUR GERIDEN geliyor
#     (son yazilan kayit onceki turun seviyesi).
# Cozum: transkript hizli ama gecikmeli tripwire olarak kullanilir; kesin
# dogrulamayi Claude `echo $CLAUDE_EFFORT` ile yapar. Bu yuzden supheli her
# durumda modele "dogrula ve operatore bildir" talimati gonderiliyor.

set -uo pipefail

GEREKEN="max"
GIRDI="$(cat 2>/dev/null || true)"

# 1) Transkript yolu: once hook girdisinden, yoksa cwd'den turet.
#    jq'ya bagimli olmamak icin grep ile — takim arkadaslarinin
#    makinesinde jq kurulu olmayabilir.
TRANSKRIPT="$(printf '%s' "$GIRDI" \
    | grep -o '"transcript_path":"[^"]*"' | head -1 | cut -d'"' -f4)"

if [ -z "$TRANSKRIPT" ] || [ ! -f "$TRANSKRIPT" ]; then
    KOK="${CLAUDE_PROJECT_DIR:-$PWD}"
    DIZIN="$HOME/.claude/projects/$(printf '%s' "$KOK" | sed 's/[^a-zA-Z0-9]/-/g')"
    # Once oturum kimliginden dogrudan; olmazsa dizindeki en yeni dosya.
    # (En yeni dosya sirali calisma kuralina guvenir — ayni anda iki oturum
    #  acilirsa yanlis dosyayi secebilir, o yuzden ikinci sirada.)
    if [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] \
       && [ -f "$DIZIN/$CLAUDE_CODE_SESSION_ID.jsonl" ]; then
        TRANSKRIPT="$DIZIN/$CLAUDE_CODE_SESSION_ID.jsonl"
    else
        TRANSKRIPT="$(ls -t "$DIZIN"/*.jsonl 2>/dev/null | head -1)"
    fi
fi

# 2) Son kaydedilen effort. Dosya cok buyuyebilir, sonundan oku.
SEVIYE=""
if [ -n "${TRANSKRIPT:-}" ] && [ -f "$TRANSKRIPT" ]; then
    SEVIYE="$(tail -c 300000 "$TRANSKRIPT" 2>/dev/null \
        | grep -o '"effort":"[a-z]*"' | tail -1 | cut -d'"' -f4)"
fi

[ "$SEVIYE" = "$GEREKEN" ] && exit 0   # her sey yolunda, sessiz cik

# 3) JSON kacisi: metin icine tirnak/ters bolu girmesin.
kacir() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

if [ -z "$SEVIYE" ]; then
    # Okunamadi — operatoru rahatsiz etme, modele dogrulat.
    printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"EFFORT BEKCISI: seviye transkriptten okunamadi. `echo $CLAUDE_EFFORT` ile dogrula; max degilse operatore HEMEN bildir (docs/KARARLAR.md KARAR-02)."}}\n'
    exit 0
fi

S="$(kacir "$SEVIYE")"
printf '{"systemMessage":"UYARI - effort: %s (max degil). Yelpence kurali: ucusa dokunan is max ile yapilir. /effort ile max sec.","hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"EFFORT BEKCISI: transkriptteki son seviye %s, max degil (bir tur gecikmeli olabilir). `echo $CLAUDE_EFFORT` ile dogrula ve operatore bildir. Bkz. docs/KARARLAR.md KARAR-02."}}\n' "$S" "$S"
