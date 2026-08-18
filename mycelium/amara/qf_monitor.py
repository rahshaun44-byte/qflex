#!/usr/bin/env python3
"""
A.M.A.R.A. Biological Monitor — Quantum Flex Infrastructure
============================================================
Mimics the Hellgrammite's dissolved-oxygen detection.
Reads kernel vitals every 30s. If the environment degrades
below thresholds, triggers a reflex: pause Athena, log the
event, then resume when conditions recover.

Thresholds (the "h" in Y=f(x-h)+k):
  - iowait  > 15%   → CRITICAL
  - RAM use > 85%   → CRITICAL
  - Swap use > 512MB → WARNING  (any significant swap is a canary)
"""

import subprocess
import time
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "sentinel" / ".env")

# ── PostgreSQL connection (psycopg2 if available, else SQLite fallback) ──────
try:
    import psycopg2
    import psycopg2.extras
    DB_MODE = "postgres"
except ImportError:
    DB_MODE = "sqlite"

# ── Configuration ─────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 30

THRESHOLDS = {
    "iowait_pct":    15.0,   # % — Hellgrammite dissolved-oxygen equivalent
    "ram_used_pct":  85.0,   # % of total RAM
    "swap_used_mb": 512.0,   # MB — any significant swap is a canary
}

# PostgreSQL credentials (matches amara-matrix container)
PG_CONFIG = {
    "host":     os.environ["DB_HOST"],
    "port":     int(os.environ["DB_PORT"]),
    "dbname":   "telemetry",
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}

SQLITE_FALLBACK  = Path(__file__).parent.parent / "sentinel/intelligence/amara_monitor.db"
LEDGER_PATH      = Path(__file__).parent.parent / "sentinel/ledger/ledger.json"
ATHENA_CONTAINER = "athena-node"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("qf-monitor")


# ── Database helpers ──────────────────────────────────────────────────────────
def get_pg_conn():
    return psycopg2.connect(**PG_CONFIG)


def init_sqlite():
    SQLITE_FALLBACK.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_FALLBACK)
    conn.execute("""CREATE TABLE IF NOT EXISTS telemetry_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now')),
        iowait_pct REAL, ram_used_pct REAL,
        swap_used_mb REAL, cpu_load_1m REAL,
        status TEXT, note TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS throttle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now')),
        trigger_metric TEXT, trigger_value REAL,
        threshold REAL, action TEXT, result TEXT)""")
    conn.commit()
    return conn


def log_telemetry(metrics: dict, status: str, note: str = ""):
    row = (
        metrics["iowait_pct"], metrics["ram_used_pct"],
        metrics["swap_used_mb"], metrics["cpu_load_1m"],
        status, note
    )
    if DB_MODE == "postgres":
        try:
            conn = get_pg_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO telemetry_log
                    (iowait_pct, ram_used_pct, swap_used_mb, cpu_load_1m, status, note)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, row)
            conn.commit()
            conn.close()
            return
        except Exception as e:
            log.warning(f"PostgreSQL write failed, falling back to SQLite: {e}")

    conn = init_sqlite()
    conn.execute("""
        INSERT INTO telemetry_log
            (iowait_pct, ram_used_pct, swap_used_mb, cpu_load_1m, status, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, row)
    conn.commit()
    conn.close()


def log_throttle_event(metric: str, value: float, threshold: float, action: str, result: str):
    row = (metric, value, threshold, action, result)
    if DB_MODE == "postgres":
        try:
            conn = get_pg_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO throttle_events
                    (trigger_metric, trigger_value, threshold, action, result)
                VALUES (%s, %s, %s, %s, %s)
            """, row)
            conn.commit()
            conn.close()
            return
        except Exception as e:
            log.warning(f"PostgreSQL throttle log failed: {e}")

    conn = init_sqlite()
    conn.execute("""
        INSERT INTO throttle_events
            (trigger_metric, trigger_value, threshold, action, result)
        VALUES (?, ?, ?, ?, ?)
    """, row)
    conn.commit()
    conn.close()


# ── Kernel telemetry readers ──────────────────────────────────────────────────
def read_iowait() -> float:
    """
    Extract iowait % using vmstat (1 sample, 2 iterations -> take last line).
    Column index 15 (0-based) in vmstat output is 'wa' (iowait).
    """
    try:
        result = subprocess.run(
            ["vmstat", "1", "2"],
            capture_output=True, text=True, timeout=5
        )
        lines = [l for l in result.stdout.strip().splitlines() if l and l[0].isdigit()]
        if lines:
            cols = lines[-1].split()
            return float(cols[15])
    except Exception as e:
        log.warning(f"iowait read failed: {e}")
    return 0.0


def read_memory() -> dict:
    """Read /proc/meminfo — zero syscall overhead, direct kernel data."""
    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])  # kB
    except Exception as e:
        log.warning(f"meminfo read failed: {e}")
        return {"ram_used_pct": 0.0, "swap_used_mb": 0.0, "ram_total_mb": 0.0}

    total    = mem.get("MemTotal", 1)
    free     = mem.get("MemAvailable", 0)
    used_pct = ((total - free) / total) * 100.0

    swap_total   = mem.get("SwapTotal", 0)
    swap_free    = mem.get("SwapFree", 0)
    swap_used_mb = (swap_total - swap_free) / 1024.0

    return {
        "ram_used_pct":  round(used_pct, 2),
        "swap_used_mb":  round(swap_used_mb, 2),
        "ram_total_mb":  round(total / 1024.0, 1),
    }


def read_cpu_load() -> float:
    """Read 1-minute load average from /proc/loadavg."""
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


def collect_metrics() -> dict:
    mem = read_memory()
    return {
        "iowait_pct":    read_iowait(),
        "ram_used_pct":  mem["ram_used_pct"],
        "swap_used_mb":  mem["swap_used_mb"],
        "ram_total_mb":  mem.get("ram_total_mb", 0),
        "cpu_load_1m":   read_cpu_load(),
        "timestamp":     datetime.now().isoformat(),
    }


# ── Podman control (neuromuscular output) ─────────────────────────────────────
def podman_action(action: str, container: str) -> str:
    """Issue podman pause/unpause. Rootless-safe — no sudo needed."""
    try:
        result = subprocess.run(
            ["podman", action, container],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"OK: {container} {action}d"
        return f"FAILED: {result.stderr.strip()}"
    except Exception as e:
        return f"ERROR: {str(e)}"


def check_container_running(container: str) -> bool:
    try:
        result = subprocess.run(
            ["podman", "inspect", "--format", "{{.State.Status}}", container],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == "running"
    except Exception:
        return False


# ── Ledger update (feeds amara-dashboard) ────────────────────────────────────
def update_ledger(metrics: dict, status: str, alerts: list):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": metrics["timestamp"],
        "status": status,
        "confidence": 0.92 if status == "OPTIMAL" else 0.35,
        "nodes": ["ghost-node-agent", "amara-dashboard", "athena-node", "qf-monitor"],
        "telemetry": {
            "iowait_pct":   metrics["iowait_pct"],
            "ram_used_pct": metrics["ram_used_pct"],
            "swap_used_mb": metrics["swap_used_mb"],
            "cpu_load_1m":  metrics["cpu_load_1m"],
        },
        "alerts": alerts,
        "source": "qf-monitor",
    }
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Main monitoring loop ──────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("A.M.A.R.A. Biological Monitor — Quantum Flex ONLINE")
    log.info(f"  Database mode : {DB_MODE.upper()}")
    log.info(f"  Poll interval : {POLL_INTERVAL_SECONDS}s")
    log.info(f"  iowait thresh : {THRESHOLDS['iowait_pct']}%")
    log.info(f"  RAM thresh    : {THRESHOLDS['ram_used_pct']}%")
    log.info(f"  Swap thresh   : {THRESHOLDS['swap_used_mb']} MB")
    log.info("=" * 60)

    athena_paused = False

    while True:
        metrics  = collect_metrics()
        alerts   = []
        status   = "OPTIMAL"
        critical = False

        # Evaluate iowait
        if metrics["iowait_pct"] > THRESHOLDS["iowait_pct"]:
            msg = (f"[CRITICAL] iowait={metrics['iowait_pct']}% "
                   f"> threshold {THRESHOLDS['iowait_pct']}%")
            alerts.append(msg)
            status   = "CRITICAL"
            critical = True

        # Evaluate RAM
        if metrics["ram_used_pct"] > THRESHOLDS["ram_used_pct"]:
            msg = (f"[CRITICAL] RAM={metrics['ram_used_pct']}% "
                   f"> threshold {THRESHOLDS['ram_used_pct']}%")
            log.critical(msg)
            alerts.append(msg)
            status   = "CRITICAL"
            critical = True

        # Evaluate Swap
        if metrics["swap_used_mb"] > THRESHOLDS["swap_used_mb"]:
            msg = (f"[WARNING] Swap={metrics['swap_used_mb']:.1f} MB "
                   f"> canary {THRESHOLDS['swap_used_mb']} MB")
            log.warning(msg)
            alerts.append(msg)
            if status == "OPTIMAL":
                status = "WARNING"

        # Throttle Athena if critical
        if critical:
            if check_container_running(ATHENA_CONTAINER):
                result = podman_action("pause", ATHENA_CONTAINER)
                log.critical(f"[REFLEX] Athena throttled: {result}")
                trigger = "iowait" if metrics["iowait_pct"] > THRESHOLDS["iowait_pct"] else "ram"
                val     = metrics["iowait_pct"] if trigger == "iowait" else metrics["ram_used_pct"]
                thr     = THRESHOLDS[trigger + "_pct"]
                log_throttle_event(trigger, val, thr, "pause", result)
                athena_paused = True
            else:
                log.warning("[REFLEX] Athena not running — throttle skipped")

        # Recover Athena when environment stabilizes
        elif not critical and athena_paused:
            result = podman_action("unpause", ATHENA_CONTAINER)
            log.info(f"[RECOVERY] Environment stable. Athena resumed: {result}")
            log_throttle_event("recovery", 0.0, 0.0, "unpause", result)
            athena_paused = False

        # Heartbeat log
        if status == "OPTIMAL":
            log.info(
                f"[OPTIMAL] iowait={metrics['iowait_pct']}% | "
                f"RAM={metrics['ram_used_pct']}% | "
                f"Swap={metrics['swap_used_mb']}MB"
            )

        # Persist
        log_telemetry(metrics, status, " | ".join(alerts) if alerts else "")
        update_ledger(metrics, status, alerts)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
