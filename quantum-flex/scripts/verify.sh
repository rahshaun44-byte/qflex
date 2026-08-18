#!/bin/bash
set -euo pipefail

echo "[*] Initiating Reality CI: Configuration..."
cmake --preset debug

echo "[*] Compiling Substrate (Debug + Sanitizers)..."
cmake --build --preset debug

echo "[*] Executing GoogleTest Matrix..."
ctest --preset debug --output-on-failure

echo "[*] Pipeline Complete: Zero System Conflicts Detected."
