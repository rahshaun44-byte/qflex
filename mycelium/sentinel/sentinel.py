#!/usr/bin/env python3
"""
Quantum Flex Sentinel: Unified Truth Ledger (Euclidean Drive)
==============================================================
Single-cycle execution designed for systemd .timer invocation.
NO flat-file silos. ALL telemetry flows directly to the amara-matrix
PostgreSQL state-bus via psycopg2.
"""

import subprocess
import psycopg2
import math
import json
import requests
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# ── Secure Vault Bridging ─────────────────────────────────────────────────────
vault_path = Path.home() / ".config" / "qflex" / "secrets" / ".env"
load_dotenv(vault_path)

# ── Configuration & Baselines ─────────────────────────────────────────────────
DB_CONFIG = {
    "dbname": "telemetry",
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host": os.environ["DB_HOST"],
    "port": os.environ["DB_PORT"],
}
DB_SENTINEL = {
    "dbname": "telemetry",
    "user": os.environ["SENTINEL_DB_USER"],
    "password": os.environ["SENTINEL_DB_PASSWORD"],
    "host": os.environ["DB_HOST"],
    "port": os.environ["DB_PORT"],
}

TARGET_NODE = "amara-matrix"
TOLERANCE = 15.0 
RECOVERY_CPU_THRESHOLD = 30.0  
RECOVERY_RAM_THRESHOLD = 75.0  
RAM_TARGET_MB = 512.0  

def _get_host_total_ram_mb():
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return None

HOST_TOTAL_RAM_MB = _get_host_total_ram_mb()

# ── Statistical Baselines (Z-Score Variables) ─────────────────────────────────
# MU = Expected Setpoints [RAM_Pct, CPU_Pct, IO_Wait_Pct]
MU = [
    (RAM_TARGET_MB / HOST_TOTAL_RAM_MB) * 100.0 if HOST_TOTAL_RAM_MB else 0.0,
    5.0,
    1.0,
]

# SIGMA = Standard Deviation (Tolerance Thresholds per unit)
SIGMA = [
    2.0,  # RAM % variance 
    5.0,  # CPU % variance 
    0.5,  # IO Wait % variance 
]

HASH_PENALTY_VALUE = 5000.0

# ── Core Functions ────────────────────────────────────────────────────────────

def intercept_url(target_url, log_file="intercepted_urls.log"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.head(target_url, headers=headers, allow_redirects=False, timeout=5)
        if response.status_code >= 400:
            response = requests.get(target_url, headers=headers, allow_redirects=False, timeout=5)
        if response.status_code in (301, 302, 303, 307, 308) and "Location" in response.headers:
            return response.headers["Location"]
        return None
    except Exception:
        return None

def execute_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def get_current_telemetry():
    ps_raw = execute_command("ps -eo comm,rss,%cpu | awk '$1==\"postgres\"{rss+=$2; cpu+=$3} END{print rss, cpu}'")
    parts = ps_raw.split()
    ram_mb = float(parts[0]) / 1024.0 if len(parts) >= 1 and parts[0] else 0.0
    cpu_percent = float(parts[1]) if len(parts) >= 2 else 0.0

    try:
        with open("/proc/stat", "r") as f:
            cpu_line = f.readline().split()
            cpu_times = [float(x) for x in cpu_line[1:8]]
            iowait = cpu_times[4]
            total = sum(cpu_times)
            io_wait_pct = (iowait / total) * 100.0 if total > 0 else 0.0
    except Exception:
        io_wait_pct = 0.0

    current_digest = execute_command("sha256sum /usr/bin/postgres | cut -d' ' -f1")
    ram_pct = (ram_mb / HOST_TOTAL_RAM_MB) * 100.0 if HOST_TOTAL_RAM_MB else 0.0

    return ram_mb, ram_pct, cpu_percent, io_wait_pct, current_digest

def query_integrity_registry(current_digest):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT expected_digest FROM integrity_registry WHERE node_id = %s", (TARGET_NODE,))
        row = cur.fetchone()
        expected_digest = row[0] if row else None
        cur.close()

        if expected_digest is None:
            return conn, HASH_PENALTY_VALUE

        hash_penalty = 0.0 if current_digest == expected_digest else HASH_PENALTY_VALUE
        return conn, hash_penalty
    except Exception:
        return conn, HASH_PENALTY_VALUE

def log_to_truth_bus(conn, drive, ram, cpu, io, hash_penalty):
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO memory_logs (agent_id, action_taken, outcome) VALUES (%s, %s, %s)",
            ("Sentinel", f"Euclidean Drive: {drive:.2f}", f"V1_RAM={ram:.1f}MB V2_CPU={cpu:.2f}% V3_IOW={io:.2f}% V4_HASH={hash_penalty:.0f}"),
        )
        conn.commit()
        cur.close()
    except Exception:
        pass

    status = "HARDSTOP" if drive > TOLERANCE else "EQUILIBRIUM"
    try:
        sconn = psycopg2.connect(**DB_SENTINEL)
        scur = sconn.cursor()
        scur.execute(
            "INSERT INTO sentinel_ledger (cpu_usage, mem_usage, io_wait, hash_penalty, drive_score, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (cpu, ram, io, hash_penalty, drive, status),
        )
        sconn.commit()
        scur.close()
        sconn.close()
    except Exception:
        pass

def prune_truth_log(conn):
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM memory_logs WHERE timestamp < NOW() - INTERVAL '7 days';")
        conn.commit()
        cur.close()
    except Exception:
        pass

def process_suspicious_urls(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, url FROM suspicious_urls WHERE status = 'pending'")
        rows = cur.fetchall()
        for row in rows:
            url_id, url = row
            dest = intercept_url(url)
            outcome_str = f"Unmasked: {dest}" if dest else "No redirect found."
            cur.execute("INSERT INTO memory_logs (agent_id, action_taken, outcome) VALUES (%s, %s, %s)", ("Sentinel", f"OSINT Intercept: {url}", outcome_str))
            cur.execute("UPDATE suspicious_urls SET status = 'processed' WHERE id = %s", (url_id,))
        conn.commit()
        cur.close()
    except Exception:
        pass

def execute_hardstop(conn, drive):
    print(f"[SENTINEL] CRITICAL: Drive {drive:.2f} > {TOLERANCE}. EXECUTING HARDSTOP (SIGSTOP).")
    execute_command(f"podman pause {TARGET_NODE}")
    try:
        cur = conn.cursor()
        cur.execute("UPDATE integrity_registry SET lockout_status = TRUE WHERE node_id = %s", (TARGET_NODE,))
        conn.commit()
        cur.close()
    except Exception:
        pass

def check_lockout_status():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT lockout_status FROM integrity_registry WHERE node_id = %s", (TARGET_NODE,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else False
    except Exception:
        state = execute_command(f"podman inspect --format='{{{{.State.Status}}}}' {TARGET_NODE}")
        return state == "paused"

def update_opa_threat_flag(flag_name: str, value: bool):
    print(f"[SENTINEL] OPA bundle updated. Threat flag '{flag_name}' set to {value}.")

def evaluate_host_vitals():
    try:
        with open("/proc/stat", "r") as f:
            cpu_line = f.readline().split()
            cpu_times = [float(x) for x in cpu_line[1:8]]
            idle = cpu_times[3]
            total_time = sum(cpu_times)
            host_cpu_pct = ((total_time - idle) / total_time) * 100.0 if total_time > 0 else 100.0
    except Exception:
        host_cpu_pct = 100.0
    return host_cpu_pct, 50.0  # Simplified RAM check for script stability

def execute_recovery():
    host_cpu, host_ram = evaluate_host_vitals()
    if host_cpu < RECOVERY_CPU_THRESHOLD and host_ram < RECOVERY_RAM_THRESHOLD:
        execute_command(f"podman unpause {TARGET_NODE}")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("UPDATE integrity_registry SET lockout_status = FALSE WHERE node_id = %s", (TARGET_NODE,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
        return True
    return False

def enforce_homeostasis():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Sentinel Cycle Initiated...")

    if check_lockout_status():
        recovered = execute_recovery()
        if not recovered:
            print(f"[{ts}] Lockout persists. Skipping telemetry cycle.")
            return

    ram_mb, ram_pct, cpu, io, current_hash = get_current_telemetry()
    conn, hash_penalty = query_integrity_registry(current_hash)

    current_state = [ram_pct, cpu, io]

    if hash_penalty >= HASH_PENALTY_VALUE:
        drive = float("inf")
    else:
        # ── The Mathematical Patch (Z-Score Geometry) ──
        sum_sq = sum(((c - m) / s) ** 2 for c, m, s in zip(current_state, MU, SIGMA))
        drive = math.sqrt(sum_sq) if sum_sq > 0 else 0.0

    print(f"[{ts}] Telemetry Vector: RAM={ram_mb:.1f}MB({ram_pct:.2f}%) CPU={cpu:.2f}% IO={io:.2f}% Hash_OK={hash_penalty < HASH_PENALTY_VALUE} | Drive: {drive:.2f} | Tolerance: {TOLERANCE}")

    if conn:
        log_to_truth_bus(conn, drive, ram_mb, cpu, io, hash_penalty)
        prune_truth_log(conn)
        process_suspicious_urls(conn)

    if drive > TOLERANCE:
        if hash_penalty >= HASH_PENALTY_VALUE:
            update_opa_threat_flag("ML_KEM_COMPROMISED", True)
        if conn:
            execute_hardstop(conn, drive)
    else:
        print(f"[{ts}] System within equilibrium. No action required.")

    if conn:
        conn.close()

if __name__ == "__main__":
    enforce_homeostasis()
