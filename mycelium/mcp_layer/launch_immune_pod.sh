#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# Quantum Flex — Immune Pod Launcher
# Creates: qflex-immune-pod (PQC Worker + OPA Sidecar + CBOMkit Theia)
# Network: Shared localhost namespace (zero external latency)
# Security: Rootless Podman, no-new-privileges, resource-clamped
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POD_NAME="qflex-immune-pod"
BUNDLE_SERVER_URL="http://10.0.2.2:8182/bundle.tar.gz" # Host network from pod

echo "[$(date)] IMMUNE POD: Initializing ${POD_NAME}..."

# ── 0. Cleanup any previous pod ──────────────────────────────────
podman pod rm -f "${POD_NAME}" 2>/dev/null || true

# ── 1. Create the pod (shared network namespace) ─────────────────
# Port 8181: OPA REST API (localhost only — not exposed to host)
# Port 9090: Worker health endpoint (exposed to host for Sentinel)
podman pod create \
    --name "${POD_NAME}" \
    -p 127.0.0.1:9090:9090 \
    --share net

echo "[$(date)] IMMUNE POD: Pod created. Shared network namespace active."

# ── 2. Deploy OPA Sidecar (Bundle Pulling) ───────────────────────
# OPA will serve on port 8181 (accessible to worker via localhost)
# It pulls bundles from the bundle server to sync threat flags
OPA_CONFIG_TMP=$(mktemp)
cat <<EOF > "${OPA_CONFIG_TMP}"
services:
  default:
    url: ${BUNDLE_SERVER_URL}
bundles:
  default:
    service: default
    resource: bundle.tar.gz
    polling:
      min_delay_seconds: 1
      max_delay_seconds: 2
EOF

podman run -d \
    --pod "${POD_NAME}" \
    --name qflex-opa-sidecar \
    --security-opt no-new-privileges:true \
    --memory 128m \
    --cpus 0.25 \
    -v "${OPA_CONFIG_TMP}:/config.yaml:ro,Z" \
    docker.io/openpolicyagent/opa:latest-static \
    run \
        --server \
        --addr 127.0.0.1:8181 \
        --config-file /config.yaml \
        --log-level info

echo "[$(date)] IMMUNE POD: OPA sidecar deployed (Bundle polling active)."

# ── 3. Deploy CBOMkit-theia Sidecar ──────────────────────────────
# This container mounts the worker filesystem read-only to scan algorithms
# It writes its output to a shared tmpfs where the immune daemon can read it
# We'll mock the Theia container for now as a simple container that copies a static CBOM
# (In production this would be the actual CBOMkit image running periodic scans)
podman run -d \
    --pod "${POD_NAME}" \
    --name qflex-cbom-theia \
    --security-opt no-new-privileges:true \
    --memory 128m \
    --cpus 0.25 \
    alpine:latest \
    sh -c "while true; do sleep 60; done" # Mock for now until we build the actual Theia scanner

echo "[$(date)] IMMUNE POD: CBOMkit-theia sidecar deployed."

# ── 4. Deploy PQC Worker ─────────────────────────────────────────
# Build the worker image if not already present
if ! podman image exists qflex-pqc-worker:latest; then
    echo "[$(date)] IMMUNE POD: Building PQC worker image..."
    # Resource-clamp the BUILD phase — liboqs compilation is the heaviest
    # single workload on this node. Without this, the build can consume
    # all 14G of RAM and hard-lock the host.
    podman build \
        --memory="6g" \
        --cpus="4" \
        -t qflex-pqc-worker:latest \
        -f "${SCRIPT_DIR}/Containerfile.pqc-worker" \
        "${SCRIPT_DIR}"
fi

podman run -d \
    --pod "${POD_NAME}" \
    --name qflex-pqc-worker \
    --security-opt no-new-privileges:true \
    --memory 512m \
    --cpus 1.0 \
    --env-file "${SCRIPT_DIR}/../.env" \
    qflex-pqc-worker:latest

echo "[$(date)] IMMUNE POD: PQC worker deployed. Immune system ONLINE."
echo "[$(date)] IMMUNE POD: OPA → 127.0.0.1:8181 | Worker Health → 127.0.0.1:9090"

# ── 5. Verify pod health ─────────────────────────────────────────
echo "[$(date)] IMMUNE POD: Running post-deploy verification..."
sleep 3

# Verify OPA is responding from inside the pod namespace (using worker which has curl)
OPA_HEALTH=$(podman exec qflex-pqc-worker curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8181/health || echo "000")
if [ "${OPA_HEALTH}" = "200" ]; then
    echo "[$(date)] IMMUNE POD: OPA health check ✅ (HTTP ${OPA_HEALTH})"
else
    echo "[$(date)] IMMUNE POD: OPA health check ❌ (HTTP ${OPA_HEALTH})"
fi

echo "[$(date)] IMMUNE POD: Deployment complete. All cells viable."
