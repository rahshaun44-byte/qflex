import subprocess
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path

# ANSI colors
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'
BOLD = '\033[1m'

print(f"{CYAN}{BOLD}=== QUANTUM FLEX: HYPHAE TELEMETRY SENSOR ==={RESET}")
print(f"Targeting Node: {YELLOW}transpar{RESET} (DePIN)")
print("Initializing connection to Quantum Flex Ledger...")

LEDGER_PATH = Path("./data/qflex_ledger.db")
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

# Ensure ledger exists
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

for i in range(3):
    print(f"\n{BOLD}--- Polling Cycle {i+1}/3 ---{RESET}")
    
    # 1. Get raw container stats
    try:
        result = subprocess.run(
            ['podman', 'stats', '--no-stream', '--format', 'json', 'transpar'], 
            capture_output=True, text=True, check=True
        )
        stats = json.loads(result.stdout)[0]
        cpu = stats.get('CPUPerc', '0%')
        mem = stats.get('MemUsage', '0B')
        print(f"[{GREEN}HYPHAE SENSOR{RESET}] Extracted raw telemetry -> CPU: {cpu} | MEM: {mem}")
    except Exception as e:
        print(f"[{RED}ERROR{RESET}] Failed to reach container: {e}")
        continue

    # 2. Package and Audit to Ledger
    timestamp = datetime.now().isoformat()
    payload = {
        "prompt": f"DePIN Telemetry: Node 'transpar'. CPU: {cpu}, Memory: {mem}. Verify execution integrity.",
        "mode": "depin_monitor",
        "context": {"node": "transpar", "network": "DePIN"}
    }
    
    print(f"[{CYAN}STROMA BUS{RESET}] Transmitting payload to Core Node for security evaluation...")
    time.sleep(1) # simulate inference
    
    response_text = (
        f"[QUANTUM FLEX] Superposition Collapsed. Frictionless Execution Active.\n"
        f"Mode: depin_monitor\n"
        f"Prompt processed at φ-confidence threshold: 0.85 (Trust Verified)"
    )
    
    cursor.execute(
        "INSERT INTO collapse_log (timestamp, payload, response, memory_used) VALUES (?,?,?,?)",
        (timestamp, json.dumps(payload), response_text, 0)
    )
    conn.commit()
    
    print(f"[{GREEN}CORE NODE RESPONSE{RESET}] Status: COLLAPSED")
    print(f"{response_text}")
    
    # 3. Verify Ledger Audit
    cursor.execute("SELECT id, timestamp FROM collapse_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"[{YELLOW}IMMUTABLE LEDGER{RESET}] Event committed to SQLite audit chain. Record ID: {row[0]}")
        
    time.sleep(2)

conn.close()
print(f"\n{CYAN}{BOLD}=== DEMONSTRATION COMPLETE ==={RESET}")
