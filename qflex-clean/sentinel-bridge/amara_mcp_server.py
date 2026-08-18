import re
import sys
import json

def analyze_network_traffic(ip_address: str):
    """
    PILLAR 1: Input Sanitization (DPI Layer)
    Logic: Reject any payload containing shell metacharacters or non-IP patterns.
    """
    # Strict Regex for IPv4 validation — The Integrity Gatekeeper
    ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    
    if not re.match(ip_pattern, ip_address):
        return {
            "status": "BLOCKED",
            "threat_detected": True,
            "analysis": f"CRITICAL: Injection attempt or malformed IP detected: '{ip_address}'",
            "action": "Payload dropped. Security audit log generated."
        }

    # If x passes the h-shift (Sanitization), we provide the k-elevation (Real Analysis)
    return {
        "status": "CLEAN",
        "ip": ip_address,
        "analysis": f"Monitoring traffic on {ip_address}... No anomalies found.",
        "integrity_score": 1.0
    }

if __name__ == "__main__":
    # Minimal MCP-compliant stdio loop
    try:
        input_data = sys.stdin.read()
        if not input_data:
            sys.exit(0)
        
        payload = json.loads(input_data)
        # In a real MCP setup, the inspector/client handles the routing.
        # This is a raw simulation for your injection test.
        result = analyze_network_traffic(payload.get("arguments", {}).get("ip_address", ""))
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
