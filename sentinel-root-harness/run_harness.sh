#!/bin/bash

echo "[*] Creating persistent data directory..."
mkdir -p data

echo "[*] Building isolated Podman test harness..."
podman build -t sentinel-root-harness .

echo "[*] Executing Sentinel C++ ROOT integration..."
# The :Z flag is critical here to rewrite the SELinux context of the local ./data directory
podman run --rm -v $(pwd)/data:/opt/sentinel/data:Z sentinel-root-harness

echo "[*] Verifying output..."
ls -lh data/sentinel_capture.root
