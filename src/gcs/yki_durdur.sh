#!/bin/bash
# YKİ süreçlerini durdur (base bridge + backend + frontend).
# Not: pgrep kendini hariç tutar; bu script'in komut satırı deseni içermez
#      ("bash yki_durdur.sh"), o yüzden düz desen güvenli.
for pat in "esp32_base" "uvicorn backend" "vite"; do
  pids=$(pgrep -f "$pat" 2>/dev/null)
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null
    echo "durduruldu: $pat ($pids)"
  fi
done
echo "YKİ durduruldu."
