#!/bin/bash
set -e

echo "=== Quantum Flex: Compiling SNN Sentinel Node ==="
podman build -t localhost/qflex/snn_sentinel:v1 -f Containerfile.snn .

echo "=== Detonating Sentinel Sandbox (Live Log Mode) ==="
# Mount live host authentication traffic strictly as read-only
podman run --rm --network=host --security-opt label=disable \
    -v /var/log/secure:/var/log/secure:ro \
    localhost/qflex/snn_sentinel:v1 python lif_sentinel.py /var/log/secure
