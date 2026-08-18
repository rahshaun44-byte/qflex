#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Quantum Flex — OPA Bundle Server
# Serves the localized bundle.tar.gz for OPA sidecars to poll.
# Runs on host port 8182 (accessible to pod via 10.0.2.2)
# ═══════════════════════════════════════════════════════════════════

BUNDLE_DIR="/home/rahshaunchambers/mycelium/sentinel/bundle_server"
mkdir -p "${BUNDLE_DIR}"

# Create an initial empty bundle if one doesn't exist
if [ ! -f "${BUNDLE_DIR}/bundle.tar.gz" ]; then
    cd "${BUNDLE_DIR}"
    echo '{"threat_flags": {}}' > data.json
    tar -czf bundle.tar.gz data.json -C /home/rahshaunchambers/mycelium/sentinel/policies membrane_health.rego
    echo "[$(date)] Initial OPA bundle created."
fi

# Kill any existing server
pkill -f "python3 -m http.server 8182" || true

cd "${BUNDLE_DIR}"
nohup python3 -m http.server 8182 > server.log 2>&1 &
echo "[$(date)] Bundle server listening on 8182."
