import re

def sanitize_ip_payload(payload: str) -> dict:
    """
    DPI Scanner: Validates that the payload is strictly an IPv4 address.
    Traps command injection vectors (like ; rm -rf /).
    """
    ipv4_pattern = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
    clean_payload = payload.strip()
    
    if not ipv4_pattern.match(clean_payload):
        return {
            "status": "QUARANTINE",
            "confidence": 1.0, 
            "reason": "Command injection or malformed IP detected.",
            "original_payload": clean_payload
        }
        
    return {
        "status": "CLEAN",
        "ip": clean_payload
    }
