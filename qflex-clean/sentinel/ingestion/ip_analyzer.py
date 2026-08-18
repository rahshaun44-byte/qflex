# sentinel/ingestion/ip_analyzer.py
# PURPOSE: Detect brute force patterns from parsed events

from collections import defaultdict

BRUTE_FORCE_THRESHOLD = 5  # failed attempts from same IP = flag

def analyze_ip_frequency(events: list) -> list:
    ip_counts = defaultdict(int)
    for event in events:
        if event.get("event_type") == "ssh_failed":
            groups = event.get("groups", [])
            if len(groups) >= 3:
                source_ip = groups[2]
                ip_counts[source_ip] += 1

    threats = []
    for ip, count in ip_counts.items():
        if count >= BRUTE_FORCE_THRESHOLD:
            threats.append({
                "threat_type": "BRUTE_FORCE_DETECTED",
                "source_ip": ip,
                "attempt_count": count,
                "severity": classify_severity(count),
                "recommended_action": "Block IP at firewall level"
            })
            print(f"[SENTINEL] ⚠ THREAT DETECTED: {ip} → {count} attempts")
    return threats

def classify_severity(attempt_count: int) -> str:
    if attempt_count >= 50:
        return "CRITICAL"
    elif attempt_count >= 20:
        return "HIGH"
    elif attempt_count >= 10:
        return "MEDIUM"
    return "LOW"
