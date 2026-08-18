#!/bin/bash
set -euo pipefail

echo "======================================"
echo " QUANTUM FLEX : HEALTH CERTIFICATE"
echo "======================================"

# 1. Supply Chain Fingerprint
./verify/verify-supply-chain.sh

# 2. Btrfs Snapshot Rollback Test
./verify/verify-backups.sh

# 3. C++ Compilation & Static Analysis Gate
echo "[*] Initializing CMake Configuration with Clang..."
export CC=clang
export CXX=clang++

rm -rf build
mkdir -p build

echo "[*] Running Static Analysis Gate (Clang-Tidy)..."
if ! cmake -S . -B build > build/cmake_config.log 2>&1; then
    echo "[!] FATAL: CMake Configuration or Static Analysis Check Failed."
    cat build/cmake_config.log | grep -E "error:|warning:" || true
    exit 1
fi

echo "[*] Compiling Binary Targets..."
if ! cmake --build build > build/cmake_build.log 2>&1; then
    echo "[!] FATAL: Compilation failed due to strict compiler flags."
    cat build/cmake_build.log | grep -E "error:" || true
    exit 1
fi

echo "======================================"
echo " OVERALL STATUS: VERIFIED (PROVEN)"
echo "======================================"
