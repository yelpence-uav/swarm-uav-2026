#!/usr/bin/env python3
import os

key = os.urandom(16)
hex_key = key.hex()

print("=" * 50)
print("YENİ AES-128 ANAHTARI:")
print(hex_key)
print("=" * 50)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aes_key.txt")
with open(out, "w") as f:
    f.write(hex_key + "\n")
print(f"Kaydedildi: {out}")
print(f"\nProvision komutu:")
print(f"  python tools/nvs_provision.py --port /dev/ttyUSB0 --key {hex_key}")
