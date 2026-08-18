#!/usr/bin/env python3
"""
Quantum Flex — Automated Neurogenesis (Truth Log Pruning)
==========================================================
Maintains a rolling 7-day state window on memory_logs and sentinel_ledger.
Prevents OOM from unbounded telemetry accumulation (~3000 rows/day).

Designed for daily cron invocation via systemd .timer.
"""

import psycopg2
from datetime import datetime, timedelta
import brie_medium

# Superuser connection (must be able to DELETE from memory_logs)
DB_CONFIG = {
    "dbname": "telemetry",
    "user": "ghostnode",
    "password": "quantum_flex_auth",
    "host": "127.0.0.1",
    "port": "5432",
}

RETENTION_DAYS = 7


def manage_partitions(cur, base_table):
    now = datetime.now()
    
    # 1. Prune T-7 (Drop old partition)
    prune_date = now - timedelta(days=RETENTION_DAYS)
    prune_suffix = prune_date.strftime("%Y_%m_%d")
    prune_table = f"{base_table}_p{prune_suffix}"
    
    # 1.5 Brie Node Medium (Synchronous Purge & Attestation Hook)
    try:
        k_t = brie_medium.neurogenesis_purge(cur, prune_table)
        cur.execute(f"DROP TABLE IF EXISTS {prune_table}")
        print(f"[Neurogenesis] Partition {prune_table} safely dropped post-attestation. k_t: {k_t.hex()[:16]}")
    except Exception as e:
        print(f"[Neurogenesis] ABORTING DROP for {prune_table}: {e}")
        raise RuntimeError(f"PURGE INTEGRITY BREACH on {prune_table}") from e

    
    # 2. Provision T+1 and T+2
    for offset in [1, 2]:
        future_date = now + timedelta(days=offset)
        start_ts = future_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ts = start_ts + timedelta(days=1)
        
        suffix = start_ts.strftime("%Y_%m_%d")
        new_table = f"{base_table}_p{suffix}"
        
        start_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_ts.strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute(f"CREATE TABLE IF NOT EXISTS {new_table} PARTITION OF {base_table} FOR VALUES FROM ('{start_str}') TO ('{end_str}')")

def prune_truth_log():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Neurogenesis Cycle Initiated — enforcing {RETENTION_DAYS}-day rolling window and provisioning future partitions...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        tables_to_manage = ["memory_logs", "sentinel_ledger", "telemetry_log"]
        
        for table in tables_to_manage:
            manage_partitions(cur, table)

        # Log the pruning event itself
        cur.execute(
            """INSERT INTO memory_logs (agent_id, action_taken, outcome)
               VALUES ('Neurogenesis', %s, %s)""",
            (
                f"PRUNE & PROVISION: {RETENTION_DAYS}-day rolling window enforced",
                f"Dropped T-{RETENTION_DAYS} partitions and provisioned T+1, T+2 for all truth logs.",
            ),
        )

        conn.commit()
        cur.close()
        conn.close()

        print(f"[{ts}] Neurogenesis complete: Partitions managed via O(1) ops.")

    except Exception as e:
        print(f"[{ts}] NEUROGENESIS FAILURE: {e}")

if __name__ == "__main__":
    prune_truth_log()
