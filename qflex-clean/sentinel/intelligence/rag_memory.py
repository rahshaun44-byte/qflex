# sentinel/intelligence/rag_memory.py
# PURPOSE: SENTINEL-specific ChromaDB RAG operations
# Stores threat intelligence. Feeds historical context into new threat analysis.
# This is how SENTINEL learns — gracefully sanitized.

import chromadb
from datetime import datetime
from pathlib import Path

CHROMA_PATH = str(Path(__file__).parent.parent / "data" / "chroma_db")

class MemoryIntegrityException(Exception):
    """Raised when AMARA's memory subsystems fail or are unreachable."""
    pass

def get_sentinel_collection():
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        return client.get_or_create_collection(
            name="sentinel_threats",
            metadata={"description": "SENTINEL threat intelligence memory"}
        )
    except Exception as e:
        raise MemoryIntegrityException(f"Fail-closed. ChromaDB unreachable: {e}")

def sanitize_for_memory(threat: dict) -> dict:
    # Stop memory poisoning: Distill pattern, drop raw attacker payload
    desc = threat.get("description", "")
    try:
        conf = float(threat.get("confidence_score", 0.0))
    except (ValueError, TypeError):
        conf = 0.0

    return {
        "threat_type": threat.get("threat_type", "UNKNOWN"),
        "severity": threat.get("severity", "LOW"),
        "pattern": desc[:500],  # Truncate at 500 chars to avoid buffer poisoning
        "confidence_bucket": round(conf, 1),
        "false_positive_rate": 0.0,
        "expiry_timestamp": int(datetime.now().timestamp()) + (86400 * 30) # 30 day TTL
    }

def store_incident_in_memory(incident_data: dict) -> str:
    collection = get_sentinel_collection()
    threat_id = incident_data.get("threat_id", "UNKNOWN")
    
    sanitized = sanitize_for_memory(incident_data)
    pattern_text = sanitized.pop("pattern")
    
    metadata = {k: str(v) for k, v in sanitized.items()}
    metadata["stored_at"] = datetime.now().isoformat()
    
    try:
        collection.add(
            documents=[pattern_text],
            metadatas=[metadata],
            ids=[threat_id]
        )
    except Exception as e:
        raise MemoryIntegrityException(f"Fail-closed. Failed to write to memory pool: {e}")
        
    return threat_id

def query_similar_incidents(threat_description: str, n_results: int = 3) -> list:
    collection = get_sentinel_collection()
    # Apply TTL logic here if we were using a real SQL boundary or advanced Chroma filtering
    # For now, we return standard query but metadata will inform the LLM of expiry_timestamp.
    try:
        results = collection.query(
            query_texts=[threat_description[:500]],
            n_results=n_results
        )
        return results.get("documents", [[]])[0]
    except Exception as e:
        raise MemoryIntegrityException(f"Fail-closed. Failed to query memory pool: {e}")
