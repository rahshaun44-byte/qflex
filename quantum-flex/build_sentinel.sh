#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# QUANTUM FLEX: NUITKA BUILD PIPELINE
# Target: src/edge/hardware_binder.py -> qf_sentinel.bin
# ==========================================

# Step 1: Verify environment dependencies and compiler tools
echo "[-] Auditing compilation dependencies..."
if ! command -v nuitka &> /dev/null; then
    echo "[NOTICE] Nuitka not found in current environment. Bootstrapping installation..."
    pip install --break-system-packages --upgrade nuitka setuptools patchelf
fi

# Step 2: Isolate targets and variables
SRC_TARGET="src/edge/hardware_binder.py"
OUT_NAME="qf_sentinel.bin"

if [ ! -f "$SRC_TARGET" ]; then
    echo "[!] CRITICAL FAULT: Source file '$SRC_TARGET' is missing from the working directory. Halting pipeline."
    exit 1
fi

echo "[-] Initializing Nuitka standalone compilation sequence for $SRC_TARGET..."

# Step 3: Execute C-level translation and binary packaging
python3 -m nuitka \
    --standalone \
    --remove-output \
    --lto=yes \
    --output-filename="$OUT_NAME" \
    --assume-yes-for-downloads \
    "$SRC_TARGET"

# Step 4: Verify binary integrity
if [ -f "$OUT_NAME" ] || [ -d "${OUT_NAME}.dist" ] || [ -d "hardware_binder.dist" ]; then
    echo "[+] SUCCESS: Sentinel binary compiled and isolated."
else
    echo "[!] FATAL: Binary emission failed."
    exit 1
fi
