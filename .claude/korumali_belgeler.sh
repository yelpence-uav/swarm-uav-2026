#!/bin/bash
# =============================================================================
# KORUMALI BELGE BEKCISI
#
# NEDEN VAR: iki referans belgesi cok buyuk (MESH_PROTOKOL_KARARLARI 1542
# satir, YELPENCE_RTCM_SPEC 841 satir) ve Claude kesif sirasinda bunlari
# okuyunca baglami bosuna doldurup asil ise yer birakmiyor.
#
# Operator karari (20 Agustos 2026): bu ikisi YALNIZ acikca istenince
# okunacak. Bekci onlari engellemiyor — izin SORDURUYOR. Operator "oku"
# demisse onaylar, demediyse reddeder.
#
# NEDEN IZIN KURALI DEGIL DE HOOK: .claude/settings.local.json'da
# Read(//home/eyup/**) izni var ve local ayar proje ayarini EZIYOR, yani
# settings.json'a yazilan "ask" kurali tutmuyor. Hook izin kontrolunden
# ONCE kostugu icin bu sorunu asiyor.
# =============================================================================
set -uo pipefail

girdi=$(cat)

# Hangi alanlara bakiyoruz: Read/Glob dosya yolu, Grep deseni ve yolu,
# Bash komut satirinin tamami.
hedef=$(printf '%s' "$girdi" | jq -r '
  [ .tool_input.file_path? // empty,
    .tool_input.path?      // empty,
    .tool_input.pattern?   // empty,
    .tool_input.command?   // empty,
    .tool_input.glob?      // empty ] | join(" ")' 2>/dev/null)

case "$hedef" in
  *MESH_PROTOKOL_KARARLARI*|*YELPENCE_RTCM_SPEC*)
    jq -cn '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason:
          "KORUMALI BELGE. Bu iki referans cok buyuk ve baglami doldurur; operator karariyla YALNIZ acikca istenince okunur (20 Agustos 2026). Sen istemediysen REDDET."
      }
    }'
    ;;
  *)
    exit 0
    ;;
esac
