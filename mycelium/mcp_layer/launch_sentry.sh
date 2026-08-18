#!/bin/bash
# A.T.H.E.N.A Continuous Ingestion Pipeline - Layer 2 (Alpine Sentry)

echo "[*] Spinning up the Alpine Quarantine Chamber..."

# We run an Alpine container, map the host's data directory, and execute the watchdog script.
# --security-opt label=disable (or :Z on the volume) is required for SELinux permission.
# We map host network so it can reach the FastAPI dashboard on 127.0.0.1:8000

podman run -d \
  --name qflex-sentry-quarantine \
  --network host \
  --user root \
  -v /home/rahshaunchambers/data:/data:Z \
  docker.io/library/alpine:latest \
  sh -c "apk add --no-cache python3 py3-requests py3-watchdog && python3 /data/quarantine_chamber.py"

echo "[+] Alpine Sentry deployed. Watching /home/rahshaunchambers/data for payloads."
