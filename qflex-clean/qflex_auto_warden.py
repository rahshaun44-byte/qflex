import subprocess
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path

# Configuration
NODE_NAME = "transpar"
POLL_INTERVAL = 10 # Seconds between checks
CPU_THRESHOLD = 30.0 # Percentage max CPU
FAILURE_STRINGS = [
    "Network Overused",
    "Unusable IP",
    "Error processing authorisation",
    "Offline",
    "Connection refused"
]

# Formatting
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'
BOLD = '\033[1m'

LEDGER_PATH = Path("./data/qflex_ledger.db")
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_ledger():
    conn = sqlite3.connect(LEDGER_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collapse_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            payload     TEXT NOT NULL,
            response    TEXT NOT NULL,
            memory_used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def log_to_ledger(reason: str, telemetry: dict):
    timestamp = datetime.now().isoformat()
    payload = {
        "prompt": f"Warden triggered HARD STOP on node '{NODE_NAME}'. Reason: {reason}",
        "mode": "auto_warden_execution",
        "context": telemetry
    }
    response_text = f"[QUANTUM FLEX WARDEN] Execution completed. Node stopped. Defense active."
    
    conn = sqlite3.connect(LEDGER_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO collapse_log (timestamp, payload, response, memory_used) VALUES (?,?,?,?)",
        (timestamp, json.dumps(payload), response_text, 0)
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id

def is_running():
    try:
        res = subprocess.run(
            ['podman', 'inspect', '-f', '{{.State.Running}}', NODE_NAME],
            capture_output=True, text=True
        )
        return res.stdout.strip() == "true"
    except:
        return False

def get_telemetry():
    res = subprocess.run(
        ['podman', 'stats', '--no-stream', '--format', 'json', NODE_NAME], 
        capture_output=True, text=True
    )
    if not res.stdout.strip():
        return None
    stats = json.loads(res.stdout)[0]
    cpu_str = stats.get('CPUPerc', '0%').replace('%', '')
    try:
        cpu_val = float(cpu_str)
    except:
        cpu_val = 0.0
    
    return {
        "cpu_perc": cpu_val,
        "mem": stats.get('MemUsage', '0B'),
        "raw": stats
    }

def get_logs():
    res = subprocess.run(
        ['podman', 'logs', '--tail', '20', NODE_NAME], 
        capture_output=True, text=True
    )
    # Podman logs can be in stderr or stdout depending on the container
    return res.stdout + "\n" + res.stderr

def execute_hard_stop(reason: str, telemetry: dict):
    print(f"\n{RED}{BOLD}[!!] CRITICAL THRESHOLD BREACH DETECTED [!!]{RESET}")
    print(f"{YELLOW}Reason: {reason}{RESET}")
    print(f"[{CYAN}WARDEN{RESET}] Executing Hard Stop protocol on {NODE_NAME}...")
    
    # 1. Stop container
    subprocess.run(['podman', 'stop', NODE_NAME], capture_output=True)
    
    # 2. Write to immutable ledger
    record_id = log_to_ledger(reason, telemetry)
    
    print(f"[{GREEN}SUCCESS{RESET}] Node neutralized.")
    print(f"[{YELLOW}LEDGER{RESET}] Action permanently audited to DB. Record ID: {record_id}\n")

def run_warden():
    init_ledger()
    print(f"{CYAN}{BOLD}=== QUANTUM FLEX: AUTO-WARDEN ACTIVE ==={RESET}")
    print(f"Monitoring Target: {YELLOW}{NODE_NAME}{RESET}")
    print(f"Rules of Engagement: CPU > {CPU_THRESHOLD}% OR Network Failure Strings")
    
    while True:
        if not is_running():
            print(f"[{YELLOW}WAIT{RESET}] Node '{NODE_NAME}' is not running. Standing by...")
            time.sleep(POLL_INTERVAL)
            continue
            
        # Poll Telemetry
        telemetry = get_telemetry()
        if not telemetry:
            time.sleep(POLL_INTERVAL)
            continue
            
        print(f"[{CYAN}POLL{RESET}] CPU: {telemetry['cpu_perc']}% | MEM: {telemetry['mem']} | State: Nominal", end="\r")
        
        # Rule 1: CPU Threshold
        if telemetry["cpu_perc"] > CPU_THRESHOLD:
            print("\n")
            execute_hard_stop(f"CPU violation ({telemetry['cpu_perc']}% > {CPU_THRESHOLD}%)", telemetry)
            continue
            
        # Rule 2: Log Failures (Panera WiFi constraint)
        logs = get_logs()
        for fail_str in FAILURE_STRINGS:
            if fail_str in logs:
                print("\n")
                execute_hard_stop(f"Network violation detected: '{fail_str}'", telemetry)
                break
                
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        run_warden()
    except KeyboardInterrupt:
        print(f"\n{CYAN}Warden shutting down.{RESET}")
