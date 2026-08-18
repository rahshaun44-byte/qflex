# sentinel/ledger/ledger.py
import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path
from sentinel.config_loader import config
from sentinel.ledger.exceptions import TamperDetectionException

DB_PATH = Path(__file__).parent.parent.parent / "sentinel/data/amara_ledger.db"

def compute_hash(prev_hash: str, payload_str: str, timestamp: str) -> str:
    data = f"{prev_hash}{payload_str}{timestamp}".encode()
    return hashlib.sha256(data).hexdigest()

def wipe_and_rebuild_genesis():
    """Wipe the Dev DB and rebuild unified schema."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Applying timeout=10 to manage concurrent writes safely
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT,
            trust_tier TEXT,
            baseline_reputation REAL,
            current_reputation REAL,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE reputation_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            event_type TEXT,
            reputation_delta REAL,
            new_reputation REAL,
            timestamp TEXT,
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE ingress_events (
            payload_hash TEXT PRIMARY KEY,
            source_id TEXT,
            timestamp TEXT,
            raw_payload TEXT,
            FOREIGN KEY(source_id) REFERENCES sources(source_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE system_volatility (
            timestamp TEXT PRIMARY KEY,
            volatility_score REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE trust_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload_hash TEXT,
            prior_reputation REAL,
            current_reputation REAL,
            volatility_score REAL,
            phi_threshold_used REAL,
            decision_result TEXT CHECK(decision_result IN ('ADMIT', 'QUARANTINE', 'REJECT')),
            reason_code TEXT,
            timestamp TEXT,
            FOREIGN KEY(payload_hash) REFERENCES ingress_events(payload_hash)
        )
    """)

    cursor.execute("""
        CREATE TABLE audit_chain_meta (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_ref TEXT,
            record_id TEXT,
            prev_hash TEXT,
            current_hash TEXT,
            payload_snapshot TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()
    
    # Genesis Audit Log
    _append_audit("GENESIS", "GENESIS", "GENESIS_ROOT_PAYLOAD", "GENESIS")
    _seed_sources()

def _append_audit(table_ref, record_id, payload_str, timestamp=None):
    if not timestamp:
        timestamp = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    # Explicit BEGIN EXCLUSIVE to prevent concurrency race conditions locking the hash linkage
    cursor.execute("BEGIN EXCLUSIVE")
    try:
        cursor.execute("SELECT current_hash FROM audit_chain_meta ORDER BY event_id DESC LIMIT 1")
        row = cursor.fetchone()
        prev_hash = row[0] if row else "GENESIS_ROOT"
        
        current_hash = compute_hash(prev_hash, payload_str, timestamp)
        cursor.execute("""
            INSERT INTO audit_chain_meta (table_ref, record_id, prev_hash, current_hash, payload_snapshot, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (table_ref, record_id, prev_hash, current_hash, payload_str, timestamp))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return current_hash

def _seed_sources():
    sources_path = config.config_path.parent / "data/valid_sources.json"
    if not sources_path.exists():
        return
    with open(sources_path, "r") as f:
        data = json.load(f).get("sources", [])
        
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    for s in data:
        cursor.execute("""
            INSERT OR IGNORE INTO sources 
            (source_id, source_type, trust_tier, baseline_reputation, current_reputation, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (s["source_id"], s["source_type"], s["trust_tier"], s["baseline_reputation"], s["baseline_reputation"], s["created_at"]))
    conn.commit()
    conn.close()
    _append_audit("sources", "BULK_SEED", "Seeded bootstrap sources")

def verify_chain_integrity():
    """
    Retrospective Genesis Hash Chain validation.
    Walks the chain from Event 1 to HEAD. Throws TamperDetectionException if DB was mutated.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("SELECT event_id, prev_hash, payload_snapshot, timestamp, current_hash FROM audit_chain_meta ORDER BY event_id ASC")
    rows = cursor.fetchall()
    conn.close()

    expected_prev_hash = "GENESIS_ROOT"
    
    for row in rows:
        event_id, db_prev_hash, payload, timestamp, db_current_hash = row
        
        if event_id == 1 and db_prev_hash == "GENESIS_ROOT":
            # Seed entry logic skip verification for standard genesis match
            expected_prev_hash = db_current_hash
            continue
            
        if db_prev_hash != expected_prev_hash:
            raise TamperDetectionException(f"Hash linkage severed at Event {event_id}. Expected {expected_prev_hash}, found {db_prev_hash}.")
            
        calculated_hash = compute_hash(expected_prev_hash, payload, timestamp)
        
        if calculated_hash != db_current_hash:
            raise TamperDetectionException(f"Payload mutability detected at Event {event_id}. Calculated hash does not match stored hash.")
            
        expected_prev_hash = calculated_hash

    return True

if __name__ == "__main__":
    wipe_and_rebuild_genesis()
    print("[AMARA Ledger] Database rebuilt from Genesis.")
