# sentinel/quarantine/quarantine_chamber.py
# PURPOSE: Isolate flagged data, extract Versioned Signatures
# DESIGN: Event-Sourced SOC sandboxing model
# HARD RULE: Nothing in this module touches the live stack directly

import json
import sqlite3
from datetime import datetime
from pathlib import Path

QUARANTINE_DB = Path(__file__).parent.parent / "data" / "quarantine.db"

def initialize_quarantine():
    QUARANTINE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QUARANTINE_DB)
    cursor = conn.cursor()
    # Base entry table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_entries (
            q_id            TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            raw_payload     TEXT NOT NULL,
            source_profile  TEXT
        )
    """)
    # Event sourcing table (append-only)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_events (
            event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            q_id          TEXT NOT NULL,
            event_type    TEXT NOT NULL,
            timestamp     TEXT NOT NULL,
            metadata      TEXT,
            FOREIGN KEY(q_id) REFERENCES quarantine_entries(q_id)
        )
    """)
    conn.commit()
    conn.close()

def log_quarantine_event(q_id: str, event_type: str, metadata: dict):
    conn = sqlite3.connect(QUARANTINE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quarantine_events (q_id, event_type, timestamp, metadata)
        VALUES (?, ?, ?, ?)
    """, (q_id, event_type, datetime.now().isoformat(), json.dumps(metadata)))
    conn.commit()
    conn.close()

def quarantine_payload(payload: dict, fail_reason: str) -> str:
    import uuid
    initialize_quarantine()
    q_id = f"QRN-{uuid.uuid4().hex[:8].upper()}"
    conn = sqlite3.connect(QUARANTINE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quarantine_entries (q_id, timestamp, raw_payload)
        VALUES (?, ?, ?)
    """, (q_id, datetime.now().isoformat(), json.dumps(payload)))
    conn.commit()
    conn.close()
    
    log_quarantine_event(q_id, "QUARANTINED", {"fail_reason": fail_reason})
    print(f"[QUARANTINE] Payload isolated. Event QUARANTINED → {q_id}")
    return q_id

def analyze_quarantine_intent(q_id: str, llm_analysis: dict):
    log_quarantine_event(q_id, "ANALYZED", llm_analysis)
    print(f"[QUARANTINE] Event ANALYZED logged → {q_id}")

def extract_intelligence(q_id: str, intelligence: dict):
    # Enforcing Versioned Signature Schema
    versioned_signature = {
        "signature_schema_version": "v1.0",
        "pattern_class": intelligence.get("pattern_class", "genetic_anomaly"),
        "feature_vector_hash": intelligence.get("feature_vector_hash", "UNKNOWN_HASH"),
        "confidence_distribution": intelligence.get("confidence", 0.0),
        "expiry_half_life": intelligence.get("expiry_half_life", 86400),
        "cross_domain_applicability": intelligence.get("cross_domain", False),
        "original_payload_ref": q_id
    }
    log_quarantine_event(q_id, "INTELLIGENCE_EXTRACTED", versioned_signature)
    print(f"[QUARANTINE] Event INTELLIGENCE_EXTRACTED logged → {q_id}")
    return versioned_signature
