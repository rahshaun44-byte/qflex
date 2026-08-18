package membrane.health_test

import data.membrane.health
import rego.v1

# Test: Healthy node with ML-KEM-768 and no threat flags
test_healthy_ml_kem if {
    result := health.verdict with input as {
        "metadata": {"timestamp": "2026-07-15T19:00:00Z"},
        "components": [{
            "type": "crypto-asset",
            "cryptoProperties": {
                "algorithmProperties": {"algorithm": "ML-KEM-768"}
            }
        }]
    } with data.threat_flags as {}
    
    result.node_status == "COMPLIANT"
    count(result.toxic_findings) == 0  # Verify through verdict
}

# Test: ML-KEM-768 flagged as compromised
test_compromised_ml_kem if {
    result := health.verdict with input as {
        "metadata": {"timestamp": "2026-07-15T19:00:00Z"},
        "components": [{
            "type": "crypto-asset",
            "cryptoProperties": {
                "algorithmProperties": {"algorithm": "ML-KEM-768"}
            }
        }]
    } with data.threat_flags as {"ML_KEM_COMPROMISED": true}
    
    result.node_status == "TOXIC"
    result.recommended_fallback == "FrodoKEM-976-AES"
}

# Test: All PQC compromised — classical reversion
test_full_reversion if {
    result := health.verdict with input as {
        "metadata": {"timestamp": "2026-07-15T19:00:00Z"},
        "components": [{
            "type": "crypto-asset",
            "cryptoProperties": {
                "algorithmProperties": {"algorithm": "ML-KEM-768"}
            }
        }]
    } with data.threat_flags as {
        "ML_KEM_COMPROMISED": true,
        "FRODOKEM_COMPROMISED": true
    }
    
    result.node_status == "TOXIC"
    result.recommended_fallback == "X25519"
}
