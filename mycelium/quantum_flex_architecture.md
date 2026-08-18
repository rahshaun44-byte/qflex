# QUANTUM FLEX ARCHITECTURE v2.1 (The Swarm)
**Senior Software Executive Chief:** Rahshaun Chambers
**System Posture:** Zero-Trust, Decentralized, Rootless Podman, Native Fedora SELinux.

## 1. Cryptographic Neutralization (The Perimeter)
- **Physical Lock:** LUKS2 Full Disk Encryption (`/dev/nvme0n1p3`). Requires manual passphrase on boot.
- **Volatile Logging (Zero-Trace):** All user-level agent services (`amara-dashboard`, `amara-predict`, `athena-node`, `sentinel-drive`) write output logs strictly to RAM (`/run/user/1000/`). If the physical drive is extracted and loses power, all telemetry and operational states instantly evaporate.

## 2. Telemetry Capture (qf-monitor)
- **Path:** `/home/rahshaunchambers/mycelium/amara/qf_monitor.py`
- **Service:** `qf-monitor.service` (Systemd User Daemon, 30s cadence)
- **Function:** Reads `/proc` and `vmstat` kernel metrics (iowait, RAM, swap, load) and writes `sentinel/ledger/ledger.json`, consumed by the AMARA dashboard.
- **Retired:** Ghost Node (`sentinel/decision_gate.py` + the unused Go stub in `systemd-backup/main.go`) was a duplicate, disabled implementation of this same telemetry-to-ledger job. It produced no output `qf-monitor` didn't already provide, so it and its systemd unit have been removed (2026-08-06).
- **Ingest load safety:** `api_node/main.py`'s `/ingest` and `/webhook/ingest` endpoints previously spawned an unbounded subprocess per request. This is now capped by an `asyncio.Semaphore` (`INGEST_CONCURRENCY_LIMIT`, default 4) so a traffic burst waits for a free slot instead of exhausting host RAM/CPU.

## 3. A.M.A.R.A. Matrix & Task Queue (The Dual-Role Truth Log)
- **Container:** `amara-matrix` (Rootless Podman, `postgres:15-alpine`)
- **Port:** `127.0.0.1:5432`
- **Security Constraint:** Locked to a strict 2GB memory bound (`podman update --memory 2g`).
- **Blast-Radius Containment (Dual-Role DB):**
  - **`ghostnode`:** Administrative superuser. Full access to `memory_logs` (Truth Log) and `integrity_registry`.
  - **`sentinel_service`:** Restricted service account. Only permitted to `INSERT` to `sentinel_ledger` and `SELECT` from `integrity_registry`. Prevents a compromised Sentinel from corrupting the core swarm memory.

## 4. Sentinel: Euclidean Drive Monitor (The Homeostatic Reflex)
- **Path:** `/home/rahshaunchambers/mycelium/sentinel/sentinel.py`
- **Service:** `sentinel-drive.service` (Systemd User Daemon, 30s cadence)
- **Mathematical Bound:** $D = \sqrt{\sum_{i=1}^{4} (Sc_i - Sb_i)^2}$
- **Variables:** $V_1$ (Memory), $V_2$ (CPU), $V_3$ (I/O Wait), $V_4$ (Cryptographic Integrity Penalty).
- **Function:** Reactive Wall. If $D > 1500$, Sentinel executes a Hardstop (`SIGSTOP`) on the deviant container.

## 5. Amara Predictive Routing (The Cognitive Engine)
- **Path:** `/home/rahshaunchambers/mycelium/mcp_layer/predictive_routing.py`
- **Service:** `amara-predict.service` (Systemd User Daemon, 5min cadence)
- **Function:** Preemptive routing. Analyzes historical $D$ trajectory over time ($v = dD/dt$). If velocity indicates an imminent breach of the 1500 threshold within 300 seconds, it artificially throttles CPU shares to 256. If velocity stabilizes ($v \le 0$), it automatically restores CPU shares to 1024.

## 6. A.T.H.E.N.A. Cognitive Node (The Mind)
- **Service:** `athena-node.service` (Systemd User Daemon)
- **Port:** `127.0.0.1:8001`
- **Model:** `gemma2:2b` / `gemma2:9b` (Ollama)
- **Function:** Local RAG interface housing the persistent Knowledge Base via ChromaDB, bound by the System Truth Directive.

## 7. A.M.A.R.A. Dashboard (The Sync Interface)
- **Service:** `amara-dashboard.service` (Systemd User Daemon)
- **Port:** `127.0.0.1:8000` (Zero-Trust mesh binding, no `0.0.0.0`)
- **Function:** Aggregates data natively from PostgreSQL (`sentinel_ledger` and `memory_logs`). Visualizes the Euclidean Drive, Confidence metric, and active alerts.

## 8. Remote Ledger Push (The Sync Protocol)
- **Protocol:** Configuration drift and architecture manifests are tracked via local Git. Upon verified system state modification, a deterministic commit is generated and pushed to the remote decentralized ledger (Git over Tailscale SSH), ensuring the swarm's memory is backed up off-node securely.

**OPERATIONAL PROTOCOL:** Before executing commands, read this document. Do not hallucinate paths or use Docker. We use rootless Podman and Systemd user services (`loginctl enable-linger`).
