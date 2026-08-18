# sentinel/ingestion/sentinel_parser.py
# PURPOSE: Parse system auth logs into structured JSON events
# AUTHOR: Quantum Flex SENTINEL v1.0
# HARD STOP: Verify log file exists before running

import re
import json
import os
from datetime import datetime
from pathlib import Path

LOG_SOURCES = {
    "auth": "/var/log/auth.log",
    "syslog": "/var/log/syslog",
    "kern": "/var/log/kern.log"
}

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "queue"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PATTERNS = {
    "ssh_failed": re.compile(
        r'(\w+\s+\d+\s+[\d:]+).*Failed password for (\S+) from ([\d.]+) port (\d+)'
    ),
    "ssh_success": re.compile(
        r'(\w+\s+\d+\s+[\d:]+).*Accepted \S+ for (\S+) from ([\d.]+) port (\d+)'
    ),
    "sudo_attempt": re.compile(
        r'(\w+\s+\d+\s+[\d:]+).*sudo:.*USER=(\S+).*COMMAND=(.*)'
    ),
    "invalid_user": re.compile(
        r'(\w+\s+\d+\s+[\d:]+).*Invalid user (\S+) from ([\d.]+)'
    ),
}

def parse_log_file(log_type: str, filepath: str) -> list:
    if not os.path.exists(filepath):
        print(f"[SENTINEL] Log not found: {filepath}")
        return []

    events = []
    with open(filepath, "r", errors="ignore") as f:
        for line in f:
            for event_type, pattern in PATTERNS.items():
                match = pattern.search(line)
                if match:
                    events.append({
                        "event_type": event_type,
                        "log_source": log_type,
                        "raw_line": line.strip(),
                        "groups": list(match.groups()),
                        "parsed_at": datetime.now().isoformat()
                    })
    return events

def save_events_to_queue(events: list, log_type: str):
    if not events:
        print(f"[SENTINEL] No events to queue for {log_type}")
        return
    output_file = OUTPUT_DIR / f"{log_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(events, f, indent=2)
    print(f"[SENTINEL] {len(events)} events queued → {output_file}")

def run_ingestion():
    print("\n[SENTINEL] ═══ INGESTION CYCLE INITIATED ═══")
    all_events = []
    for log_type, filepath in LOG_SOURCES.items():
        events = parse_log_file(log_type, filepath)
        if events:
            save_events_to_queue(events, log_type)
            all_events.extend(events)
    print(f"[SENTINEL] ═══ TOTAL EVENTS QUEUED: {len(all_events)} ═══\n")
    return all_events

if __name__ == "__main__":
    run_ingestion()
