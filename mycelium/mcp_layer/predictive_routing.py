#!/usr/bin/env python3
"""
Quantum Flex Amara: Cognitive Predictive Routing
==================================================
Mycelial routing logic. Queries the unified PostgreSQL state-bus for
historical Sentinel vectors, calculates Drive Velocity (dD/dt) via
time-based linear regression, and preemptively throttles container
CPU shares to cool the system BEFORE Sentinel's Hardstop fires.

Auto-un-throttling: When velocity stabilizes to zero or negative,
Amara autonomously restores full CPU allocation and logs the recovery
to the Truth Log, maintaining complete state-invariance.

Mathematical Model:
    v = [n(Σ tD) - (Σt)(ΣD)] / [n(Σ t²) - (Σt)²]
    
    If v > 0 and (TOLERANCE - D_current) / v < CRITICAL_WINDOW:
        → PREEMPTIVE THROTTLE (cpu-shares 256)
    If v ≤ 0:
        → RESTORE (cpu-shares 1024)
"""

import re
import subprocess
import logging
import psycopg2
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
PG_CONFIG = {
    "dbname": "telemetry",
    "user": "ghostnode",
    "password": "quantum_flex_auth",
    "host": "127.0.0.1",
    "port": "5432",
}

TARGET_NODE = "amara-matrix"
TOLERANCE = 1500.0
CRITICAL_TIME_HORIZON_SEC = 300  # 5-minute lookahead
SAMPLE_LIMIT = 20
THROTTLED_SHARES = 256
NOMINAL_SHARES = 1024

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] AMARA-ROUTE | %(message)s")
log = logging.getLogger("amara_route")


def execute_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def fetch_drive_history():
    """Extracts recent Sentinel telemetry from the unified state-bus."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT timestamp, action_taken
            FROM memory_logs
            WHERE agent_id = 'Sentinel'
            ORDER BY timestamp DESC
            LIMIT %s
        """, (SAMPLE_LIMIT,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        rows.reverse()  # Chronological order
        return rows
    except Exception as e:
        log.error(f"Truth Log query failure: {e}")
        return []


def is_currently_throttled():
    """Checks the Truth Log for whether a throttle is currently active."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT action_taken FROM memory_logs
            WHERE agent_id = 'Amara-Route'
            ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and "THROTTLE" in row[0]:
            return True
        return False
    except Exception:
        return False


def calculate_trajectory(history):
    """
    Time-based linear regression on Drive values.
    Returns (velocity_D_per_sec, current_drive).
    """
    if len(history) < 2:
        return 0.0, 0.0

    t_values = []
    d_values = []

    base_time = history[0][0].timestamp()

    for ts, action in history:
        t_sec = ts.timestamp() - base_time
        # Match our actual Sentinel format: "Euclidean Drive: 405.52"
        match = re.search(r"Euclidean Drive:\s*([\d.]+)", action)
        if match:
            t_values.append(t_sec)
            d_values.append(float(match.group(1)))

    n = len(t_values)
    if n < 2:
        return 0.0, d_values[-1] if d_values else 0.0

    sum_t = sum(t_values)
    sum_d = sum(d_values)
    sum_t_sq = sum(t ** 2 for t in t_values)
    sum_td = sum(t * d for t, d in zip(t_values, d_values))

    denominator = (n * sum_t_sq) - (sum_t ** 2)
    if denominator == 0:
        return 0.0, d_values[-1]

    velocity = ((n * sum_td) - (sum_t * sum_d)) / denominator
    current_drive = d_values[-1]

    return velocity, current_drive


def log_to_truth_bus(agent_id, action, outcome):
    """Commits a cognitive decision to the unified state-bus."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO memory_logs (agent_id, action_taken, outcome) VALUES (%s, %s, %s)",
            (agent_id, action, outcome),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Truth Log commit failed: {e}")


def execute_preemptive_routing():
    """Single-cycle cognitive routing. Designed for .timer invocation."""
    log.info("Cognitive Routing Cycle Initiated...")

    history = fetch_drive_history()
    if len(history) < 3:
        log.info(f"Insufficient data ({len(history)} samples). Deferring analysis.")
        return

    velocity, current_drive = calculate_trajectory(history)
    throttled = is_currently_throttled()

    log.info(f"Current Drive: {current_drive:.2f} | Velocity: {velocity:.6f} D/sec | Throttled: {throttled}")

    # ── CASE 1: Velocity is negative or neutral — system is cooling ───────
    if velocity <= 0:
        if throttled:
            # Auto-un-throttle: restore full CPU allocation
            log.info("RECOVERY DETECTED. Velocity stabilized. Restoring nominal CPU shares.")
            execute_command(f"podman update --cpu-shares {NOMINAL_SHARES} {TARGET_NODE}")
            log_to_truth_bus(
                "Amara-Route",
                "AUTO_RESTORE: CPU shares → 1024",
                f"Velocity={velocity:.6f} D/sec. System trajectory stable. Throttle released.",
            )
        else:
            log.info("STATUS: OPTIMAL. Pathways clear.")

        log_to_truth_bus(
            "Amara-Route",
            f"Trajectory Analysis: v={velocity:.6f} D/sec",
            f"Drive={current_drive:.2f} | Velocity stable/negative. No action.",
        )
        return

    # ── CASE 2: Velocity is positive — system is heating ──────────────────
    remaining_headroom = TOLERANCE - current_drive
    if remaining_headroom <= 0:
        # Already at or past tolerance — Sentinel will handle this
        log.warning("Drive already at tolerance. Deferring to Sentinel Hardstop.")
        return

    time_to_critical = remaining_headroom / velocity

    log.info(f"Projected Critical Intersection: {time_to_critical:.1f} seconds")

    if time_to_critical < CRITICAL_TIME_HORIZON_SEC:
        # ── PREEMPTIVE THROTTLE ───────────────────────────────────────────
        log.warning(f"TOXICITY HORIZON BREACHED ({time_to_critical:.0f}s < {CRITICAL_TIME_HORIZON_SEC}s).")
        log.warning("INITIATING PREEMPTIVE REROUTE: Dropping CPU shares to 256.")
        execute_command(f"podman update --cpu-shares {THROTTLED_SHARES} {TARGET_NODE}")
        log_to_truth_bus(
            "Amara-Route",
            "PREEMPTIVE THROTTLE: CPU shares → 256",
            f"Velocity={velocity:.6f} D/sec. Critical in {time_to_critical:.0f}s. Cooling initiated.",
        )
    else:
        # Positive velocity but not imminently critical
        if throttled:
            # Still throttled from a previous cycle but danger has receded
            log.info("Threat receding. Restoring nominal CPU shares.")
            execute_command(f"podman update --cpu-shares {NOMINAL_SHARES} {TARGET_NODE}")
            log_to_truth_bus(
                "Amara-Route",
                "AUTO_RESTORE: CPU shares → 1024",
                f"Velocity={velocity:.6f} D/sec. Critical in {time_to_critical:.0f}s (beyond horizon). Safe.",
            )
        else:
            log.info("STATUS: STABLE. Positive velocity but within safe horizon.")

        log_to_truth_bus(
            "Amara-Route",
            f"Trajectory Analysis: v={velocity:.6f} D/sec",
            f"Drive={current_drive:.2f} | Critical in {time_to_critical:.0f}s. No immediate action.",
        )


if __name__ == "__main__":
    execute_preemptive_routing()
