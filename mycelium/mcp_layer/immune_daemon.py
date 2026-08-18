#!/usr/bin/env python3
"""
Quantum Flex — Autonomous Immune Daemon
=========================================
The biological imperative made code. Runs inside the PQC worker
container as PID 1, supervising the worker process and continuously
polling the co-located OPA sidecar for cryptographic health verdicts.

Decision Loop:
    Every 500ms:
        1. Generate CBOM snapshot (active algorithms)
        2. POST to OPA sidecar (localhost:8181)
        3. If verdict == TOXIC:
            a. sed → rewrite crypto_provider.conf
            b. SIGHUP → worker process
            c. Log transition to volatile stdout

Execution Model:
    - Zero external network dependency (OPA is localhost)
    - O(1) decision time (~2ms OPA query + ~1ms sed)
    - Worker process survives SIGHUP (graceful tunnel renegotiation)

Failure Mode:
    - OPA unreachable → FAIL SECURE (assume toxic, trigger fallback)
    - Worker process dies → restart with backoff
    - All algorithms exhausted → HALT (log critical, do not send data)
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import psycopg2
    import requests
except ImportError:
    psycopg2 = None
    requests = None

# ── Configuration ─────────────────────────────────────────────────
OPA_ENDPOINT = os.environ.get("OPA_ENDPOINT", "http://127.0.0.1:8181")
OPA_VERDICT_PATH = "/v1/data/membrane/health/verdict"
POLL_INTERVAL_SEC = float(os.environ.get("POLL_INTERVAL_MS", "500")) / 1000.0
PROVIDER_CONF = Path("/opt/pqc-worker/crypto_provider.conf")
WORKER_CMD = os.environ.get("WORKER_CMD", "python3 /opt/pqc-worker/sss_relay.py")

# Consecutive failure threshold before fail-secure triggers
FAIL_SECURE_THRESHOLD = 3

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] IMMUNE | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,  # Volatile: captured by systemd → /run/user/1000/
)
log = logging.getLogger("immune_daemon")

PG_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "telemetry", "user": os.environ["GHOSTNODE_DB_USER"],
    "password": os.environ["GHOSTNODE_DB_PASSWORD"],
}
DASHBOARD_WEBHOOK = "http://100.120.30.95:8000/api/internal/webhook_transition"

def log_transition_background(old_kem: str, new_kem: str, findings: list):
    """
    Executes in O(1) background thread to prevent I/O blocking during Vein Collapse.
    Logs to the unified PostgreSQL Truth Log (memory_logs) and pushes SSE webhook.
    """
    def _run():
        action = f"VEIN COLLAPSE: {old_kem} → {new_kem}"
        outcome = f"TOXIC findings: {[f.get('algorithm') for f in findings]}"
        
        # 1. Truth Log Insertion
        if psycopg2:
            try:
                conn = psycopg2.connect(**PG_CONFIG)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO memory_logs (agent_id, action_taken, outcome) VALUES (%s, %s, %s)",
                    ("immune_daemon", action, outcome)
                )
                conn.commit()
                cur.close()
                conn.close()
                log.info("Truth Log sync complete (async).")
            except Exception as e:
                log.error(f"Truth Log async insert failed: {e}")

        # 2. Webhook to Dashboard for Real-Time UI Pulse
        if requests:
            try:
                requests.post(
                    DASHBOARD_WEBHOOK,
                    json={"old_kem": old_kem, "new_kem": new_kem, "findings": findings, "timestamp": datetime.now().isoformat()},
                    timeout=2
                )
                log.info("Dashboard webhook push complete (async).")
            except Exception as e:
                log.error(f"Dashboard webhook async push failed: {e}")

    threading.Thread(target=_run, daemon=True).start()

class ImmuneState:
    """Tracks the daemon's current cryptographic posture."""
    def __init__(self):
        self.active_kem = self._read_active_kem()
        self.active_sig = self._read_active_sig()
        self.consecutive_opa_failures = 0
        self.last_transition = None
        self.transition_count = 0
        self.worker_pid = None

    def _read_active_kem(self):
        """Parse the currently active KEM from crypto_provider.conf."""
        try:
            for line in PROVIDER_CONF.read_text().splitlines():
                if line.strip().startswith("active_kem"):
                    return line.split("=")[1].strip()
        except Exception:
            pass
        return "ML-KEM-768"  # Default

    def _read_active_sig(self):
        """Parse the currently active signature algorithm."""
        try:
            for line in PROVIDER_CONF.read_text().splitlines():
                if line.strip().startswith("active_sig"):
                    return line.split("=")[1].strip()
        except Exception:
            pass
        return "ML-DSA-65"  # Default


def generate_cbom_input(state: ImmuneState) -> dict:
    """
    Generates a minimal CycloneDX-compatible CBOM input for OPA evaluation.
    In production, this would be populated by CBOMkit-theia scanning the container.
    For the immune daemon's hot loop, we generate it from the active provider config.
    """
    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "component": "qflex-pqc-worker",
        },
        "components": [
            {
                "type": "crypto-asset",
                "name": f"active-kem-{state.active_kem}",
                "cryptoProperties": {
                    "assetType": "algorithm",
                    "algorithmProperties": {
                        "algorithm": state.active_kem,
                        "parameterSetIdentifier": state.active_kem,
                    },
                },
            },
            {
                "type": "crypto-asset",
                "name": f"active-sig-{state.active_sig}",
                "cryptoProperties": {
                    "assetType": "algorithm",
                    "algorithmProperties": {
                        "algorithm": state.active_sig,
                    },
                },
            },
        ],
    }


def query_opa(cbom_input: dict) -> dict:
    """
    POST the CBOM input to the local OPA sidecar.
    Returns the structured verdict or raises on failure.
    
    Uses subprocess + curl instead of requests library to minimize
    container image size and avoid dependency conflicts.
    """
    import urllib.request
    import urllib.error

    url = f"{OPA_ENDPOINT}{OPA_VERDICT_PATH}"
    payload = json.dumps({"input": cbom_input}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("result", {})
    except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
        raise ConnectionError(f"OPA query failed: {e}")


def execute_vein_collapse(state: ImmuneState, verdict: dict):
    """
    The Mycelial Handshake: autonomous algorithm renegotiation.
    
    1. Read the recommended fallback from OPA verdict
    2. Rewrite crypto_provider.conf via sed (atomic, in-place)
    3. Send SIGHUP to the worker process (graceful tunnel teardown)
    4. Update internal state
    """
    fallback = verdict.get("recommended_fallback", "NONE")
    toxic_findings = [f for f in verdict.get("findings", []) if f.get("status") == "TOXIC"]

    if fallback == "NONE":
        # CRITICAL: No fallback available. HALT — do not send data on a compromised tunnel.
        log.critical("ALL ALGORITHMS EXHAUSTED. No safe fallback. HALTING worker process.")
        if state.worker_pid:
            os.kill(state.worker_pid, signal.SIGTERM)
        return

    log.warning(f"VEIN COLLAPSE INITIATED: {state.active_kem} → {fallback}")
    for finding in toxic_findings:
        log.warning(f"  TOXIC: {finding.get('algorithm')} — {finding.get('reason')}")

    # ── Step 1: Rewrite crypto_provider.conf ──────────────────────
    old_kem = state.active_kem
    try:
        subprocess.run(
            ["sed", "-i",
             f"s/^active_kem = .*/active_kem = {fallback}/",
             str(PROVIDER_CONF)],
            check=True, capture_output=True, text=True,
        )
        log.info(f"crypto_provider.conf rewritten: active_kem = {fallback}")
    except subprocess.CalledProcessError as e:
        log.error(f"sed rewrite FAILED: {e.stderr}")
        return

    # ── Step 2: SIGHUP the worker process ─────────────────────────
    if state.worker_pid:
        try:
            os.kill(state.worker_pid, signal.SIGHUP)
            log.info(f"SIGHUP sent to worker PID {state.worker_pid}. Tunnel renegotiation initiated.")
        except ProcessLookupError:
            log.warning("Worker process not found. Will restart on next cycle.")
            state.worker_pid = None

    # ── Step 3: Update internal state ─────────────────────────────
    state.active_kem = fallback
    state.last_transition = datetime.now().isoformat()
    state.transition_count += 1

    log.info(f"TRANSITION COMPLETE: {old_kem} → {fallback} "
             f"(total transitions: {state.transition_count})")

    # ── Step 4: Fire async truth logging and webhook ──────────────
    log_transition_background(old_kem, fallback, toxic_findings)


def fail_secure_response(state: ImmuneState):
    """
    OPA is unreachable. Assume compromise. Trigger fallback.
    This mirrors Sentinel's fail-secure design: if the immune system
    cannot verify health, assume the worst.
    """
    log.critical(f"OPA UNREACHABLE ({state.consecutive_opa_failures} consecutive failures). "
                 "FAIL-SECURE: Treating current algorithm as TOXIC.")

    # Construct a synthetic toxic verdict
    synthetic_verdict = {
        "node_status": "TOXIC",
        "recommended_fallback": _get_next_fallback(state.active_kem),
        "findings": [{
            "algorithm": state.active_kem,
            "status": "TOXIC",
            "reason": "OPA sidecar unreachable — fail-secure policy applied",
        }],
    }
    execute_vein_collapse(state, synthetic_verdict)


def _get_next_fallback(current_kem: str) -> str:
    """Hardcoded fallback chain. Mirrors the Rego policy but operates without OPA."""
    chain = {
        "ML-KEM-768": "FrodoKEM-976-AES",
        "ML-KEM-1024": "FrodoKEM-976-AES",
        "ML-KEM-512": "FrodoKEM-640-AES",
        "FrodoKEM-976-AES": "X25519",
        "FrodoKEM-640-AES": "X25519",
        "FrodoKEM-1344-AES": "X25519",
        "X25519": "NONE",
    }
    return chain.get(current_kem, "NONE")


def spawn_worker(state: ImmuneState):
    """Spawn the worker subprocess. The daemon is PID 1."""
    log.info(f"Spawning worker: {WORKER_CMD}")
    try:
        proc = subprocess.Popen(
            WORKER_CMD.split(),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        state.worker_pid = proc.pid
        log.info(f"Worker spawned. PID: {proc.pid}")
        return proc
    except Exception as e:
        log.error(f"Worker spawn FAILED: {e}")
        return None


def main():
    log.info("═══════════════════════════════════════════════════════")
    log.info("  QUANTUM FLEX — Autonomous Immune Daemon ONLINE")
    log.info(f"  OPA Endpoint:  {OPA_ENDPOINT}")
    log.info(f"  Poll Interval: {POLL_INTERVAL_SEC * 1000:.0f}ms")
    log.info(f"  Provider Conf: {PROVIDER_CONF}")
    log.info("═══════════════════════════════════════════════════════")

    state = ImmuneState()
    log.info(f"Initial crypto posture: KEM={state.active_kem} SIG={state.active_sig}")

    # Spawn the worker subprocess
    worker_proc = spawn_worker(state)

    # ── Main Immune Loop ──────────────────────────────────────────
    while True:
        try:
            # Check if worker is still alive
            if worker_proc and worker_proc.poll() is not None:
                log.warning(f"Worker process exited (code={worker_proc.returncode}). Respawning...")
                time.sleep(5)  # Backoff before respawn
                worker_proc = spawn_worker(state)

            # Generate CBOM snapshot
            cbom = generate_cbom_input(state)

            # Query OPA
            try:
                verdict = query_opa(cbom)
                state.consecutive_opa_failures = 0  # Reset on success
            except ConnectionError:
                state.consecutive_opa_failures += 1
                if state.consecutive_opa_failures >= FAIL_SECURE_THRESHOLD:
                    fail_secure_response(state)
                    state.consecutive_opa_failures = 0  # Reset after action
                time.sleep(POLL_INTERVAL_SEC)
                continue

            # Evaluate verdict
            node_status = verdict.get("node_status", "UNKNOWN")

            if node_status == "TOXIC":
                execute_vein_collapse(state, verdict)
            # COMPLIANT: no action needed. Silent pass.

        except Exception as e:
            log.error(f"Immune loop fault: {e}")

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
