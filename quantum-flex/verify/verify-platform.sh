#!/bin/bash
set -euo pipefail

echo "[*] Extracting Platform Telemetry..."

DATE=$(date -I)
OUT_DIR="artifacts/substrate/$DATE"
mkdir -p "$OUT_DIR"

lsblk -o NAME,FSTYPE,SIZE,FSAVAIL,FSUSE%,MOUNTPOINTS > "$OUT_DIR/lsblk.txt"
mokutil --sb-state > "$OUT_DIR/secureboot.txt" || echo "mokutil unavailable" > "$OUT_DIR/secureboot.txt"
uname -r > "$OUT_DIR/kernel.txt"

echo "PASS Platform"
