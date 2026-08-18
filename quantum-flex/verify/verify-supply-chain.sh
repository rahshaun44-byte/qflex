#!/bin/bash
set -euo pipefail
DATE=$(date -I)
OUT_DIR="artifacts/supply-chain/$DATE"
mkdir -p "$OUT_DIR"

echo "[*] Fingerprinting Supply Chain..."
gcc --version | head -n 1 > "$OUT_DIR/gcc.txt"
clang --version | head -n 1 > "$OUT_DIR/clang.txt"
cmake --version | head -n 1 > "$OUT_DIR/cmake.txt"
git rev-parse HEAD > "$OUT_DIR/git-hash.txt" || echo "No Git Commits Yet" > "$OUT_DIR/git-hash.txt"
uname -r > "$OUT_DIR/kernel.txt"

echo "[*] PASS: Supply Chain Fingerprinted to $OUT_DIR"
exit 0
