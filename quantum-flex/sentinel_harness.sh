#!/bin/bash
# ==========================================
# QUANTUM FLEX: SENTINEL TEST HARNESS v1.0
# ==========================================

echo "[*] Initializing isolated Podman network..."
podman network create sentinel_net 2>/dev/null || true

echo "[*] Deploying ephemeral Alpine container (frictionless substrate)..."
podman run -d --name sentinel_node --network sentinel_net alpine sleep 300

echo "[*] Injecting Controlled Network Load (Stress Test)..."
# This simulates the high-frequency traffic without persistence or resource exhaustion.
podman exec sentinel_node sh -c '
  for i in $(seq 1 20); do 
    ping -c 1 8.8.8.8 > /dev/null & 
  done; 
  wait
'

echo "[*] Pausing Execution for Sentinel Inspection..."
echo "Run the following command in a separate terminal to inspect the active traffic:"
echo "podman exec -it sentinel_node ip -s link"
read -p "Press Enter to collapse the environment once verification is complete..."

echo "[*] Tearing down infrastructure..."
podman rm -f sentinel_node
podman network rm sentinel_net
echo "[*] Environment collapsed. Zero residual mass."
