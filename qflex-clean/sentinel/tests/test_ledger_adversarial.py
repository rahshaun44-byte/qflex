# sentinel/tests/test_ledger_adversarial.py
import pytest
import sqlite3
import time
import threading
from pathlib import Path
from sentinel.ledger.ledger import wipe_and_rebuild_genesis, verify_chain_integrity, _append_audit, DB_PATH
from sentinel.ledger.exceptions import TamperDetectionException

def setup_module(module):
    """Ensures test database is clean before any tests run."""
    wipe_and_rebuild_genesis()

def test_verify_chain_genesis_validity():
    assert verify_chain_integrity() is True

def test_tamper_detection():
    """Simulates a rogue root user mutating a past entry in SQLite."""
    # Write a legitimate record
    _append_audit("trust_decisions", "DEC-1", "TEST_PAYLOAD", "2026-04-07T00:00:00")
    
    # Assert chain is valid
    assert verify_chain_integrity() is True
    
    # TAMPER: Connect natively and edit the payload directly bypassing Python
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE audit_chain_meta SET payload_snapshot = 'MALICIOUS_PAYLOAD' WHERE record_id = 'DEC-1'")
    conn.commit()
    conn.close()
    
    # Assert chain mathematically halts operations immediately
    with pytest.raises(TamperDetectionException):
        verify_chain_integrity()
        
    # Revert to prevent cascading failure
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE audit_chain_meta SET payload_snapshot = 'TEST_PAYLOAD' WHERE record_id = 'DEC-1'")
    conn.commit()
    conn.close()

def test_append_only_enforcement():
    """Validates structure strictly rejects modifications inherently if designed to fail-close."""
    wipe_and_rebuild_genesis()
    _append_audit("trust_decisions", "DEC-1", "TEST_PAYLOAD")
    _append_audit("trust_decisions", "DEC-2", "TEST_PAYLOAD_2")

    # SQLite allows update internally, but verify_chain_integrity protects us from using the mutated logic.
    # Testing that verify_chain_integrity actually triggers when historical rows are deleted
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audit_chain_meta WHERE record_id = 'DEC-1'")
    conn.commit()
    conn.close()
    
    with pytest.raises(TamperDetectionException) as excinfo:
        verify_chain_integrity()
    assert "Expected" in str(excinfo.value) # Expects prev_hash check to break

def test_replay_resistance():
    """Submits parallel identical payloads and ensures exact UNIQUE failures."""
    wipe_and_rebuild_genesis()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Assuming primary key payload_hash uniquely identifies the exact incoming tuple
    cursor.execute("INSERT INTO ingress_events (payload_hash, source_id, timestamp, raw_payload) VALUES ('HASH_A', 'SRC_1', '123', 'A')")
    conn.commit()
    
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("INSERT INTO ingress_events (payload_hash, source_id, timestamp, raw_payload) VALUES ('HASH_A', 'SRC_1', '123', 'A')")
        conn.commit()
    
    conn.close()

def test_concurrent_write_safety():
    """Simulates 10 threads hitting the append_audit chain simultaneously."""
    wipe_and_rebuild_genesis()
    
    exceptions = []
    def worker(tid):
        try:
            _append_audit("trust_decisions", f"DEC_C_{tid}", f"PAYLOAD_{tid}")
        except Exception as e:
            exceptions.append(e)
            
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # 10 threads + 2 Genesis events = 12 events total. All must have completed without 'database is locked'.
    assert len(exceptions) == 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM audit_chain_meta")
    row = cursor.fetchone()
    conn.close()
    
    assert row[0] == 12
    assert verify_chain_integrity() is True
