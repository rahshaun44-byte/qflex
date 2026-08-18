# sentinel/decision/score_calculator.py
# PURPOSE: Modular Ingress Pipeline & Trinary Gate Engine
import sqlite3
from sentinel.config_loader import config
from pathlib import Path

# Connects to the same DB Path used by ledger.py
DB_PATH = Path(__file__).parent.parent.parent / "sentinel/data/amara_ledger.db"

def validate_identity(source_id: str) -> dict:
    """1. Validate source identity"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT trust_tier, current_reputation FROM sources WHERE source_id = ?", (source_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"status": "UNKNOWN", "trust_tier": None, "reputation": None}
    return {"status": "VALID", "trust_tier": row[0], "reputation": float(row[1])}

def assess_anomaly_severity(threat_severity: str) -> float:
    """2. Assess anomaly severity (returns the reputation penalty/gain)"""
    # Fetch configured weights
    weights = config.get("reputation_weights")
    if threat_severity == "CRITICAL":
        return float(weights.get("critical_anomaly", -0.20))
    elif threat_severity == "HIGH":
        return float(weights.get("high_anomaly", -0.10))
    elif threat_severity == "MEDIUM":
        return float(weights.get("medium_anomaly", -0.05))
    return float(weights.get("positive_event", 0.02))

def calculate_volatility_modifier() -> float:
    """3. Calculate rolling volatility index over last 15m"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT severity, count(*) FROM ingress_events ie
            JOIN trust_decisions td ON ie.payload_hash = td.payload_hash
            WHERE ie.timestamp >= datetime('now', '-15 minutes')
        """)
        # Since standard payload severity isn't natively bound identically in Phase 2 DB, 
        # we pull from `trust_decisions.reason_code` or `system_volatility` cache.
        # Fallback simplified lookup using system_volatility log:
        cursor.execute("""
            SELECT SUM(volatility_score) FROM system_volatility 
            WHERE timestamp >= datetime('now', '-15 minutes')
        """)
        row = cursor.fetchone()
        v = float(row[0]) if row and row[0] is not None else 0.0
    except sqlite3.OperationalError:
        v = 0.0
    finally:
        conn.close()
    return v

def evaluate_threat(source_id: str, threat: dict) -> dict:
    """
    Modular Pipeline execution:
    Identify -> Rep -> Anomaly Score -> Volatility -> Final Gate
    """
    result = {
        "source_id": source_id,
        "execution_mode": "REJECT",
        "decision_result": "REJECT",
        "reason_code": "",
        "phi_threshold_used": 0.0,
        "volatility_score": 0.0,
        "prior_reputation": 0.0,
        "new_reputation": 0.0
    }
    
    # 1. Identity
    identity = validate_identity(source_id)
    if identity["status"] == "UNKNOWN":
        result["reason_code"] = "UNKNOWN_SOURCE"
        return result
        
    result["prior_reputation"] = identity["reputation"]
    
    # 2. Extract Data
    severity = threat.get("severity", "LOW")
    try:
        confidence = float(threat.get("confidence_score", 0.0))
    except (ValueError, TypeError):
        confidence = 0.0

    # 3. Anomaly
    delta = assess_anomaly_severity(severity)
    result["new_reputation"] = max(0.0, min(result["prior_reputation"] + delta, 1.0))
    
    # 4. Volatility Modifiers
    v = calculate_volatility_modifier()
    result["volatility_score"] = v
    base_phi = float(config.get("thresholds", "phi_base"))
    
    warn_trigger = float(config.get("thresholds", "volatility_warning_trigger"))
    crit_trigger = float(config.get("thresholds", "volatility_critical_trigger"))
    
    if v >= crit_trigger:
        effective_phi = base_phi + float(config.get("scaling_modifiers", "high_volatility_boost"))
    elif v >= warn_trigger:
        effective_phi = base_phi + float(config.get("scaling_modifiers", "moderate_volatility_boost"))
    else:
        effective_phi = base_phi
        
    result["phi_threshold_used"] = effective_phi
    
    # 5. Final Gate (Ternary Logic: ADMIT / QUARANTINE / REJECT)
    # Reject path
    if identity["reputation"] < 0.2:
        result["decision_result"] = "REJECT"
        result["reason_code"] = "REPUTATION_TOO_LOW"
        return result
        
    # Critical always requires REJECT or QUARANTINE until root reviews
    if severity == "CRITICAL":
        result["decision_result"] = "QUARANTINE"
        result["execution_mode"] = "ROOT_REQUIRED"
        result["reason_code"] = "CRITICAL_SEVERITY_MANDATES_ROOT_REVIEW"
        return result
        
    # Trinary Confidence bounds
    # Admit boundary
    if confidence >= effective_phi:
        result["decision_result"] = "ADMIT"
        result["execution_mode"] = "AUTO"
        result["reason_code"] = "CONFIDENCE_EXCEEDS_DYNAMIC_PHI"
    # Quarantine boundary (uncertain)
    elif confidence >= (effective_phi - 0.20):
        result["decision_result"] = "QUARANTINE"
        result["execution_mode"] = "REVIEW"
        result["reason_code"] = "AMBIGUOUS_CONFIDENCE_QUARANTINED"
    # Reject boundary
    else:
        result["decision_result"] = "REJECT"
        result["execution_mode"] = "REVIEW"
        result["reason_code"] = "LOW_CONFIDENCE_REJECTED"

    return result
