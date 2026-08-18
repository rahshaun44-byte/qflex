package membrane.health

import rego.v1

# ═══════════════════════════════════════════════════════════════════
# QUANTUM FLEX — Membrane Health Policy
# The Biological Imperative: Autonomous Cryptographic Compliance
#
# Input: CycloneDX CBOM JSON (from CBOMkit-theia scan)
# Output: Structured verdict with per-component compliance status
# ═══════════════════════════════════════════════════════════════════

# ── Approved Algorithm Registry ──────────────────────────────────
# NIST FIPS 203/204/205 approved algorithms (2026 baseline)
quantum_safe_kem := {
    "ML-KEM-512",
    "ML-KEM-768",
    "ML-KEM-1024",
}

quantum_safe_sig := {
    "ML-DSA-44",
    "ML-DSA-65",
    "ML-DSA-87",
    "SLH-DSA-SHA2-128f",
    "SLH-DSA-SHA2-128s",
    "SLH-DSA-SHA2-192f",
    "SLH-DSA-SHAKE-128f",
}

# Classical algorithms permitted for hybrid mode only
classical_approved := {
    "X25519",
    "Ed25519",
    "AES-256-GCM",
    "SHA-384",
    "SHA-512",
}

# Conservative lattice fallbacks (non-NIST but mathematically distinct)
fallback_approved := {
    "FrodoKEM-640-AES",
    "FrodoKEM-976-AES",
    "FrodoKEM-1344-AES",
}

# Union of all approved algorithms
all_approved := quantum_safe_kem | quantum_safe_sig | classical_approved | fallback_approved

# ── Threat Flags ─────────────────────────────────────────────────
# These are set via OPA data API by Sentinel or external threat feed.
# Default: no algorithms are compromised.
default ml_kem_compromised := false
ml_kem_compromised if data.threat_flags.ML_KEM_COMPROMISED == true

default frodokem_compromised := false
frodokem_compromised if data.threat_flags.FRODOKEM_COMPROMISED == true

# Dynamic compromised set — built from active threat flags
compromised_algorithms contains "ML-KEM-512" if ml_kem_compromised
compromised_algorithms contains "ML-KEM-768" if ml_kem_compromised
compromised_algorithms contains "ML-KEM-1024" if ml_kem_compromised
compromised_algorithms contains "FrodoKEM-640-AES" if frodokem_compromised
compromised_algorithms contains "FrodoKEM-976-AES" if frodokem_compromised
compromised_algorithms contains "FrodoKEM-1344-AES" if frodokem_compromised

# ── Per-Component Evaluation ─────────────────────────────────────
# Evaluates each cryptographic component in the CBOM

component_verdict(comp) := {"algorithm": algo, "status": "TOXIC", "reason": reason} if {
    algo := comp.cryptoProperties.algorithmProperties.algorithm
    algo in compromised_algorithms
    reason := sprintf("Algorithm %v flagged as COMPROMISED by active threat intelligence", [algo])
}

component_verdict(comp) := {"algorithm": algo, "status": "TOXIC", "reason": reason} if {
    algo := comp.cryptoProperties.algorithmProperties.algorithm
    not algo in all_approved
    not algo in compromised_algorithms
    reason := sprintf("Algorithm %v not in approved registry (unknown/deprecated)", [algo])
}

component_verdict(comp) := {"algorithm": algo, "status": "COMPLIANT", "reason": "Approved"} if {
    algo := comp.cryptoProperties.algorithmProperties.algorithm
    algo in all_approved
    not algo in compromised_algorithms
}

# ── Aggregate Verdict ────────────────────────────────────────────
# The node is TOXIC if ANY component is TOXIC

findings contains finding if {
    some comp in input.components
    comp.type == "crypto-asset"
    finding := component_verdict(comp)
}

toxic_findings contains f if {
    some f in findings
    f.status == "TOXIC"
}

default node_status := "COMPLIANT"
node_status := "TOXIC" if count(toxic_findings) > 0

# ── Primary Decision Endpoint ────────────────────────────────────
# Query: POST /v1/data/membrane/health/verdict
verdict := {
    "node_status": node_status,
    "total_components": count(findings),
    "toxic_count": count(toxic_findings),
    "findings": findings,
    "recommended_fallback": recommended_fallback,
    "evaluated_at": input.metadata.timestamp,
}

# ── Fallback Recommendation ─────────────────────────────────────
# If ML-KEM is toxic, recommend FrodoKEM. If FrodoKEM is toxic, recommend classical.
recommended_fallback := "FrodoKEM-976-AES" if {
    ml_kem_compromised
    not frodokem_compromised
}

recommended_fallback := "X25519" if {
    ml_kem_compromised
    frodokem_compromised
}

default recommended_fallback := "NONE"
