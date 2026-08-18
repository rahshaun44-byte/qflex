# sentinel/intelligence/threat_classifier.py
# PURPOSE: Feed parsed events to LLM via FastAPI collapse endpoint
# HARD STOP: Verify /api/v1/sentinel is live before sending

import json
import requests
from datetime import datetime
from pathlib import Path

CORE_NODE_URL = "http://localhost:8001"   # Updated: port shifted to 8001
SENTINEL_ENDPOINT = f"{CORE_NODE_URL}/api/v1/sentinel"
QUEUE_DIR = Path(__file__).parent.parent / "data" / "queue"

def build_threat_analysis_prompt(events: list) -> str:
    event_summary = json.dumps(events[:50], indent=2)
    return f"""
You are SENTINEL, the security intelligence module of Quantum Flex.
You are analyzing real system log events.

HARD RULES:
- Never fabricate data
- If uncertain, state confidence level explicitly
- Classify every threat using: LOW / MEDIUM / HIGH / CRITICAL
- Return ONLY valid JSON — no prose, no markdown

EVENTS TO ANALYZE:
{event_summary}

REQUIRED OUTPUT FORMAT:
{{
  "analysis_timestamp": "ISO8601",
  "total_events_analyzed": 0,
  "threats_detected": [
    {{
      "threat_id": "THR-XXXX",
      "threat_type": "string",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "source_ip": "string or null",
      "affected_user": "string or null",
      "confidence_score": 0.0,
      "description": "string",
      "recommended_action": "string",
      "auto_actionable": true
    }}
  ],
  "system_health": "NOMINAL|DEGRADED|COMPROMISED",
  "root_alert_required": true
}}
"""

def classify_threats(events: list) -> dict:
    if not events:
        print("[SENTINEL] No events to classify.")
        return {}
    prompt = build_threat_analysis_prompt(events)
    try:
        response = requests.post(
            SENTINEL_ENDPOINT,
            json={"prompt": prompt, "mode": "security_analysis"},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        print(f"[SENTINEL] Analysis complete — {len(result.get('threats_detected', []))} threats identified")
        return result
    except requests.exceptions.ConnectionError:
        print("[HARD STOP] Cannot reach qflex-core-node.")
        print("[SENTINEL] Verify Docker container is running.")
        return {"hard_stop": True}
    except Exception as e:
        print(f"[SENTINEL] Classification error: {e}")
        return {}
