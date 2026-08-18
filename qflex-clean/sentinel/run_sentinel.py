# sentinel/run_sentinel.py
import time
import json
import logging
from datetime import datetime
from pathlib import Path

from sentinel.ingestion.sentinel_parser import run_ingestion
from sentinel.ingestion.ip_analyzer import analyze_ip_frequency
from sentinel.intelligence.threat_classifier import classify_threats
from sentinel.intelligence.rag_memory import store_incident_in_memory, query_similar_incidents
from sentinel.decision.score_calculator import evaluate_threat
from sentinel.ledger.ledger import compute_hash, _append_audit
from sentinel.quarantine.quarantine_chamber import quarantine_payload, extract_intelligence
from sentinel.schemas import ThreatModel
from rich.console import Console
from rich.table import Table

console = Console()
log = logging.getLogger("AMARA_SENTINEL")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def hash_chain_save_or_fail(gate_result: dict, raw_payload_str: str):
    """Phase 4 Integrity controls. Fail closed instantly if database/hash logic mismatches."""
    import sqlite3
    DB_PATH = Path(__file__).parent / "data" / "amara_ledger.db"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Execute as transaction block
    try:
        cursor.execute("BEGIN TRANSACTION;")
        
        # Ingress Event (Hashes payload)
        payload_hash = compute_hash("STATIC", raw_payload_str, time.time())
        source = gate_result["source_id"]
        
        cursor.execute("""
            INSERT OR IGNORE INTO ingress_events (payload_hash, source_id, timestamp, raw_payload)
            VALUES (?, ?, ?, ?)
        """, (payload_hash, source, datetime.now().isoformat(), raw_payload_str))

        # Reputation Log
        if gate_result["decision_result"] != "UNKNOWN_SOURCE":
            cursor.execute("""
                INSERT INTO reputation_events (source_id, event_type, reputation_delta, new_reputation, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (source, gate_result["decision_result"], gate_result["new_reputation"] - gate_result["prior_reputation"], gate_result["new_reputation"], datetime.now().isoformat()))
            
            cursor.execute("""
                UPDATE sources SET current_reputation = ? WHERE source_id = ?
            """, (gate_result["new_reputation"], source))

        # Trust Decision Log
        cursor.execute("""
            INSERT INTO trust_decisions 
            (payload_hash, prior_reputation, current_reputation, volatility_score, phi_threshold_used, decision_result, reason_code, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (payload_hash, gate_result["prior_reputation"], gate_result["new_reputation"], 
              gate_result["volatility_score"], gate_result["phi_threshold_used"], 
              gate_result["decision_result"], gate_result["reason_code"], datetime.now().isoformat()))

        # Commit logic
        conn.commit()
        # Create macro audit hash explicitly tying trust decision chain
        _append_audit("trust_decisions", payload_hash, json.dumps(gate_result))
    except sqlite3.Error as e:
        conn.rollback()
        log.critical(f"[FAIL-CLOSED] Integrity validation aborted via DB Exception: {e}")
        raise RuntimeError("Hash-chain transaction broken. Aborting processing.")
    finally:
        conn.close()

def run_sentinel_cycle():
    from datetime import datetime
    console.print("\n[bold green]═══ AMARA C_OS CYCLE INITIATED ═══[/bold green]")
    start_time = time.time()

    # Hardware Ingress Sim
    ingress_source = "AMARA-CORE-001"
    
    events = run_ingestion()
    if not events:
        console.print("[yellow]System Nominal. Cycle resting.[/yellow]")
        return
        
    analysis = classify_threats(events)
    raw_threats = analysis.get("threats_detected", [])
    
    table = Table(title="AMARA Integrity Report")
    table.add_column("Type", style="cyan")
    table.add_column("Severity", style="red")
    table.add_column("Gate Result", style="green")
    table.add_column("Reason Code")

    for raw in raw_threats:
        try:
            valid_model = ThreatModel(**raw)
            threat = valid_model.dict()
        except Exception as e:
            log.error("Schema validation dropped malformed inference", extra={"payload": raw})
            continue

        # Phase 3 -> Modular Routing
        gate_result = evaluate_threat(ingress_source, threat)
        
        # Phase 4 -> Integrity enforcement logic
        hash_chain_save_or_fail(gate_result, json.dumps(threat))

        # Admitted Memory
        if gate_result["decision_result"] == "ADMIT":
            store_incident_in_memory({**threat, "action_taken": "ADMITTED_VIA_TRUST"})
        elif gate_result["decision_result"] == "QUARANTINE":
            # Phase 3 -> Isolate the payload in the chamber
            q_id = quarantine_payload(threat, gate_result["reason_code"])
            # Extract cryptographic intelligence signature
            extract_intelligence(q_id, threat)
        elif gate_result["decision_result"] == "REJECT":
            log.warning(f"Payload REJECTED. Dropping from memory pool. Reason: {gate_result['reason_code']}")
            
        table.add_row(
            threat.get("threat_type", "UNKNOWN"),
            threat.get("severity", "LOW"),
            f"[{'green' if gate_result['decision_result'] == 'ADMIT' else 'yellow' if gate_result['decision_result'] == 'QUARANTINE' else 'red'}]{gate_result['decision_result']}[/]",
            gate_result["reason_code"]
        )

    console.print(table)
    log.info(f"Cycle latency: {(time.time() - start_time) * 1000:.2f} ms")

if __name__ == "__main__":
    run_sentinel_cycle()
