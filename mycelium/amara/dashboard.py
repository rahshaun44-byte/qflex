#!/usr/bin/env python3
"""
A.M.A.R.A. Sync Dashboard — Quantum Flex
==========================================
Premium real-time dashboard. Pulls ALL telemetry from the unified
PostgreSQL state-bus (amara-matrix). NO flat-file silos.
  - sentinel_ledger (Euclidean Drive telemetry)
  - memory_logs (Sentinel/Amara decisions)
  - integrity_registry (cryptographic baseline)
  - Athena node /health (RAG node status)
  - Ollama /api/tags (model inventory)
Port: 8000 (127.0.0.1 — Zero-Trust, Tailscale handles mesh routing)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import httpx
from pydantic import BaseModel
from fastapi import FastAPI, Request, Header, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse

# Add parent dir to path to import Sentinel logic
sys.path.append(str(Path(__file__).parent.parent))
try:
    from sentinel.sentinel import update_opa_threat_flag
except ImportError:
    def update_opa_threat_flag(alg, status): pass

# ── PostgreSQL (optional — falls back gracefully) ─────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

PG_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "quantum_flex", "user": "quantum",
    "password": "flex_secure_pass",
}

# ── Local Inference Engine (A.T.H.E.N.A Vectors) ──────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
    # BAAI/bge-small-en-v1.5 is a highly optimized 384-dimensional embedding model
    embedding_engine = SentenceTransformer('BAAI/bge-small-en-v1.5')
except ImportError:
    embedding_engine = None

app = FastAPI(title="A.M.A.R.A. Dashboard", version="2.0.0")

ATHENA_URL   = "http://127.0.0.1:8001"
OLLAMA_URL   = "http://127.0.0.1:11434"
API_NODE_URL = "http://yoga.tail2b296e.ts.net:8002"

# ── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# ── Data helpers ──────────────────────────────────────────────────────────────
def get_sentinel_drive(limit: int = 1) -> dict:
    """Pulls the latest Euclidean Drive telemetry from sentinel_ledger."""
    if not PG_AVAILABLE:
        return {"drive_score": 0, "status": "NO_DB", "cpu_usage": 0, "mem_usage": 0, "io_wait": 0, "hash_penalty": 0}
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM sentinel_ledger ORDER BY id DESC LIMIT %s", (limit,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return dict(row)
        return {"drive_score": 0, "status": "NO_DATA", "cpu_usage": 0, "mem_usage": 0, "io_wait": 0, "hash_penalty": 0}
    except Exception as e:
        return {"drive_score": 0, "status": "ERROR", "cpu_usage": 0, "mem_usage": 0, "io_wait": 0, "hash_penalty": 0}


def get_sentinel_history(limit: int = 10) -> list:
    """Pulls recent Sentinel drive history from sentinel_ledger."""
    if not PG_AVAILABLE:
        return []
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM sentinel_ledger ORDER BY id DESC LIMIT %s", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def get_integrity_status() -> dict:
    """Reads the integrity_registry for cryptographic baseline status."""
    if not PG_AVAILABLE:
        return {"node_id": "unknown", "lockout_status": False}
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM integrity_registry LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else {"node_id": "unknown", "lockout_status": False}
    except Exception:
        return {"node_id": "unknown", "lockout_status": False}


def get_pg_history(limit: int = 10) -> list:
    if not PG_AVAILABLE:
        return []
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT timestamp, iowait_pct, ram_used_pct, swap_used_mb,
                   cpu_load_1m, status
            FROM telemetry_log
            ORDER BY timestamp DESC LIMIT %s
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def get_throttle_events(limit: int = 5) -> list:
    if not PG_AVAILABLE:
        return []
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT timestamp, trigger_metric, trigger_value,
                   threshold, action, result
            FROM throttle_events
            ORDER BY timestamp DESC LIMIT %s
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


async def probe_athena() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{ATHENA_URL}/health")
            return r.json()
    except Exception as e:
        return {"status": "OFFLINE", "error": str(e)}


async def probe_ollama() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            return {"status": "ONLINE", "models": models}
    except Exception as e:
        return {"status": "OFFLINE", "error": str(e)}


# ── API endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/telemetry")
async def get_telemetry():
    drive   = get_sentinel_drive()
    athena  = await probe_athena()
    ollama  = await probe_ollama()
    history = get_pg_history(10)
    throttle = get_throttle_events(5)
    sentinel = get_sentinel_history(10)
    integrity = get_integrity_status()
    return {
        "drive":             drive,
        "integrity":         integrity,
        "athena":            athena,
        "ollama":            ollama,
        "telemetry_history": history,
        "throttle_events":   throttle,
        "sentinel_history":  sentinel,
        "timestamp":         datetime.now().isoformat(),
    }


@app.post("/api/query")
async def proxy_query(request: Request):
    """Proxy a RAG query to Athena from the dashboard."""
    data = await request.json()
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(f"{ATHENA_URL}/query", json=data)
            return r.json()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


@app.post("/api/threat_flag")
async def toggle_threat(request: Request, x_api_key: str = Header(None)):
    """Interactive Kill Switch. Requires strict API Key auth."""
    expected_key = os.environ.get("DASHBOARD_API_KEY", "quantum-admin-2026")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API Key. Zero-Trust Violation.")
    
    data = await request.json()
    algorithm = data.get("algorithm", "ML-KEM-768")
    status = data.get("status", "TOXIC")

    # Update local bundle data via sentinel function. The Rego policy and
    # sentinel.py's own hardstop path both key off "ML_KEM_COMPROMISED" (bool),
    # not the raw algorithm name/status string the UI sends.
    update_opa_threat_flag("ML_KEM_COMPROMISED", status == "TOXIC")
    
    await manager.broadcast({
        "type": "THREAT_FLAG",
        "algorithm": algorithm,
        "status": status,
        "timestamp": datetime.now().isoformat()
    })
    return {"success": True, "message": f"Threat flag {status} applied to {algorithm}"}


@app.post("/api/internal/webhook_transition")
async def webhook_transition(request: Request):
    """Internal webhook called by immune_daemon in the background thread."""
    data = await request.json()
    data["type"] = "TRANSITION"
    await manager.broadcast(data)
    return {"success": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── A.T.H.E.N.A. Continuous Ingestion Pipeline ────────────────────────────────

class DocumentChunk(BaseModel):
    chunk_id: str
    payload: str
    metadata: dict

async def process_and_shard_vector(chunk: DocumentChunk):
    if not embedding_engine or not PG_AVAILABLE:
        print("[ATHENA] Ingestion failed: engine or DB unavailable.")
        return
        
    try:
        # 1. Local inference call to generate vector embedding
        vector = embedding_engine.encode(chunk.payload).tolist()
        
        # 2. Compute Golden Ratio Modulus 8 Shard
        hash_int = int(chunk.chunk_id, 16)
        phi = 0.6180339887
        shard_index = int(8 * ((hash_int * phi) % 1))
        
        # 3. Direct bare-metal upsert to the specific sharded PostgreSQL table
        table_name = f"edge_ingest_queue.vector_shard_{shard_index}"
        
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {table_name} (id, embedding, content, meta) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (chunk.chunk_id, vector, chunk.payload, json.dumps(chunk.metadata))
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[ATHENA] Sharded chunk {chunk.chunk_id[:8]}... to {table_name}")
    except Exception as e:
        print(f"[ATHENA] Ingestion Error: {e}")

@app.post("/v1/athena/ingest", status_code=202)
async def ingest_buffer(chunk: DocumentChunk, background_tasks: BackgroundTasks):
    """Zero-lock async endpoint for Alpine quarantine chamber telemetry."""
    background_tasks.add_task(process_and_shard_vector, chunk)
    return {"status": "queued", "chunk_id": chunk.chunk_id}


# ── Premium HTML dashboard ────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    drive_data = get_sentinel_drive()
    athena     = await probe_athena()
    ollama     = await probe_ollama()
    history    = get_pg_history(8)
    throttle   = get_throttle_events(5)
    sentinel   = get_sentinel_history(8)
    integrity  = get_integrity_status()

    # Extract live metrics from the unified state-bus
    drive_score = float(drive_data.get("drive_score", 0) or 0)
    iowait   = f"{float(drive_data.get('io_wait', 0) or 0):.2f}"
    ram_mb   = f"{float(drive_data.get('mem_usage', 0) or 0):.1f}"
    cpu_pct  = f"{float(drive_data.get('cpu_usage', 0) or 0):.2f}"
    hash_pen = float(drive_data.get("hash_penalty", 0) or 0)
    status   = drive_data.get("status", "UNKNOWN")
    lockout  = integrity.get("lockout_status", False)
    ts       = str(drive_data.get("timestamp", datetime.now().isoformat()))

    # Confidence = inverse of drive relative to tolerance (1500)
    conf     = max(0, min(1.0, 1.0 - (drive_score / 1500.0)))
    alerts   = []
    if lockout:
        alerts.append("LOCKOUT ACTIVE: Integrity registry breach detected")
    if hash_pen > 0:
        alerts.append(f"HASH MISMATCH: Cryptographic penalty {hash_pen}")
    if drive_score > 1125:
        alerts.append(f"DRIVE WARNING: D={drive_score:.1f} approaching tolerance")

    athena_status = athena.get("status", "OFFLINE")
    athena_vecs   = athena.get("vector_count", "—")
    ollama_status = ollama.get("status", "OFFLINE")
    ollama_models = ", ".join(ollama.get("models", [])) or "none"

    status_color = {
        "OPTIMAL":  "#00ff88",
        "WARNING":  "#ffcc00",
        "CRITICAL": "#ff4444",
    }.get(status, "#888888")

    athena_color = "#00ff88" if athena_status == "ONLINE" else "#ff4444"
    ollama_color = "#00ff88" if ollama_status == "ONLINE" else "#ff4444"

    # Build telemetry history rows
    history_rows = ""
    for row in history:
        s = row.get("status", "")
        sc = {"OPTIMAL": "#00ff88", "WARNING": "#ffcc00", "CRITICAL": "#ff4444"}.get(s, "#888")
        ts_short = str(row.get("timestamp", ""))[:19]
        history_rows += f"""
        <tr>
          <td>{ts_short}</td>
          <td>{row.get('iowait_pct', '—')}%</td>
          <td>{row.get('ram_used_pct', '—')}%</td>
          <td>{row.get('swap_used_mb', '—')} MB</td>
          <td>{row.get('cpu_load_1m', '—')}</td>
          <td style="color:{sc};font-weight:bold">{s}</td>
        </tr>"""

    # Build throttle events
    throttle_rows = ""
    for ev in throttle:
        ts_short = str(ev.get("timestamp", ""))[:19]
        action_color = "#ff4444" if ev.get("action") == "pause" else "#00ff88"
        throttle_rows += f"""
        <tr>
          <td>{ts_short}</td>
          <td>{ev.get('trigger_metric', '—')}</td>
          <td>{ev.get('trigger_value', '—')}</td>
          <td>{ev.get('threshold', '—')}</td>
          <td style="color:{action_color};font-weight:bold">{ev.get('action','—').upper()}</td>
          <td>{ev.get('result', '—')[:40]}</td>
        </tr>"""

    alerts_html = ""
    for a in alerts:
        alerts_html += f'<div class="alert-item">{a}</div>'
    if not alerts_html:
        alerts_html = '<div class="alert-item ok">No active alerts</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta name="description" content="A.M.A.R.A. Quantum Flex Infrastructure Dashboard — Live node telemetry and RAG interface"/>
  <title>A.M.A.R.A. | Quantum Flex</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --bg-primary:   #080c14;
      --bg-card:      #0d1422;
      --bg-card2:     #111927;
      --accent:       #00e5ff;
      --accent2:      #7c3aed;
      --green:        #00ff88;
      --yellow:       #ffcc00;
      --red:          #ff4444;
      --text:         #e2e8f0;
      --text-muted:   #64748b;
      --border:       #1e2d40;
      --glow:         0 0 20px rgba(0,229,255,0.15);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: var(--bg-primary);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }}
    /* Animated background grid */
    body::before {{
      content: '';
      position: fixed;
      inset: 0;
      background-image:
        radial-gradient(circle at 15% 50%, rgba(0, 229, 255, 0.08) 0%, transparent 50%),
        radial-gradient(circle at 85% 30%, rgba(124, 58, 237, 0.08) 0%, transparent 50%),
        linear-gradient(rgba(0,229,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,229,255,0.03) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
      pointer-events: none;
      z-index: 0;
    }}
    .container {{ position: relative; z-index: 1; max-width: 1400px; margin: 0 auto; padding: 24px; }}
    
    /* Glassmorphism Classes */
    .glass-panel {{
      background: rgba(13, 20, 34, 0.6);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 16px;
      box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
    }}

    /* Header */
    .header {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 32px; padding: 24px 32px;
      background: linear-gradient(135deg, rgba(0,229,255,0.08), rgba(124,58,237,0.08));
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 16px;
      box-shadow: var(--glow);
    }}
    .header-left h1 {{
      font-size: 1.8rem; font-weight: 700; letter-spacing: -0.02em;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .header-left .subtitle {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;
    }}
    .header-right .last-sync {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem; color: var(--text-muted); text-align: right;
    }}
    .live-dot {{
      display: inline-block; width: 8px; height: 8px;
      background: var(--green); border-radius: 50%;
      margin-right: 6px;
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(0,255,136,0.4); }}
      50% {{ opacity: 0.8; box-shadow: 0 0 0 6px rgba(0,255,136,0); }}
    }}

    /* Status banner */
    .status-banner {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 20px 32px; margin-bottom: 24px;
      border-radius: 12px; border: 1px solid var(--border);
      background: var(--bg-card);
    }}
    .status-main {{
      display: flex; align-items: center; gap: 16px;
    }}
    .status-badge {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.1rem; font-weight: 700;
      padding: 8px 20px; border-radius: 8px;
      border: 1px solid currentColor;
    }}
    .confidence-bar-wrap {{ flex: 1; max-width: 300px; }}
    .confidence-label {{
      font-size: 0.75rem; color: var(--text-muted);
      margin-bottom: 6px; font-family: 'JetBrains Mono', monospace;
    }}
    .confidence-bar {{
      height: 8px; background: #1e2d40; border-radius: 4px; overflow: hidden;
    }}
    .confidence-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent2), var(--accent));
      border-radius: 4px;
      transition: width 1s ease;
    }}

    /* Metric cards grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }}
    .metric-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px; padding: 20px;
      transition: transform 0.2s, box-shadow 0.2s;
      position: relative; overflow: hidden;
    }}
    .metric-card::before {{
      content: ''; position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }}
    .metric-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 8px 32px rgba(0,229,255,0.1);
    }}
    .metric-label {{
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--text-muted); margin-bottom: 8px;
    }}
    .metric-value {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 2rem; font-weight: 700;
      background: linear-gradient(135deg, #fff, var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .metric-unit {{
      font-size: 0.8rem; color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }}

    /* Node status row */
    .nodes-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }}
    .node-card {{
      background: var(--bg-card); border: 1px solid var(--border);
      border-radius: 12px; padding: 18px;
      display: flex; align-items: center; gap: 14px;
    }}
    .node-icon {{
      width: 40px; height: 40px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1.2rem;
      background: rgba(0,229,255,0.1);
    }}
    .node-info .node-name {{
      font-weight: 600; font-size: 0.9rem; margin-bottom: 4px;
    }}
    .node-info .node-detail {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem; color: var(--text-muted);
    }}
    .node-status-dot {{
      margin-left: auto; width: 10px; height: 10px;
      border-radius: 50%;
    }}

    /* Tables */
    .section-header {{
      font-size: 0.75rem; text-transform: uppercase;
      letter-spacing: 0.12em; color: var(--text-muted);
      margin-bottom: 12px; font-weight: 600;
    }}
    .card {{
      background: var(--bg-card); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px; margin-bottom: 20px;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.65rem; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-muted);
      padding: 8px 12px; text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    td {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem; padding: 10px 12px;
      border-bottom: 1px solid rgba(30,45,64,0.6);
      color: var(--text);
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(0,229,255,0.03); }}

    /* Alerts */
    .alerts-box {{ margin-bottom: 20px; }}
    .alert-item {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem; padding: 10px 14px;
      margin-bottom: 6px; border-radius: 8px;
      border-left: 3px solid var(--red);
      background: rgba(255,68,68,0.07);
      color: #fca5a5;
    }}
    .alert-item.ok {{
      border-left-color: var(--green);
      background: rgba(0,255,136,0.05);
      color: var(--green);
    }}

    /* RAG query box */
    .query-box {{
      background: rgba(13, 20, 34, 0.6); backdrop-filter: blur(12px); 
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 16px; padding: 20px; margin-bottom: 20px;
    }}
    .query-input-row {{
      display: flex; gap: 12px; margin-top: 12px;
    }}
    #rag-input {{
      flex: 1; background: rgba(17, 25, 39, 0.8);
      border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
      padding: 12px 16px; color: var(--text);
      font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
      outline: none; transition: border-color 0.2s;
    }}
    #rag-input:focus {{ border-color: var(--accent); }}
    .btn-premium {{
      padding: 12px 24px; border-radius: 8px; border: none; cursor: pointer;
      background: linear-gradient(135deg, var(--accent2), var(--accent));
      color: #fff; font-weight: 600; font-size: 0.85rem;
      transition: all 0.2s; box-shadow: 0 4px 15px rgba(0,229,255,0.2);
    }}
    .btn-premium:hover {{ opacity: 0.9; transform: translateY(-1px); }}
    .btn-premium:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .btn-danger {{
      background: linear-gradient(135deg, #ff4444, #cc0000);
      box-shadow: 0 4px 15px rgba(255,68,68,0.2);
    }}
    #rag-output {{
      margin-top: 14px; padding: 14px;
      background: rgba(8, 12, 20, 0.8); border-radius: 8px;
      font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
      color: var(--green); min-height: 60px; white-space: pre-wrap;
      display: none; border: 1px solid rgba(255,255,255,0.05);
    }}

    /* Pulse Animation for active tunnels */
    .pulse-tunnel {{
      animation: tunnel-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
    @keyframes tunnel-pulse {{
      0%, 100% {{ opacity: 1; text-shadow: 0 0 10px var(--accent); }}
      50% {{ opacity: 0.5; text-shadow: none; }}
    }}

    /* Immune Control Panel */
    .immune-panel {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;
    }}
    .immune-card {{
      padding: 24px; display: flex; flex-direction: column; gap: 16px;
    }}
    .immune-data-row {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.02);
    }}
    .immune-val {{ font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: var(--accent); }}
    .threat-input {{ width: 100%; margin-bottom: 12px; }}

    /* Two-column layout */
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    @media (max-width: 900px) {{ .two-col, .immune-panel {{ grid-template-columns: 1fr; }} }}

    .footer {{
      text-align: center; padding: 24px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.65rem; color: var(--text-muted);
      border-top: 1px solid var(--border); margin-top: 12px;
    }}
  </style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1>A.M.A.R.A. Intelligence Sync</h1>
      <div class="subtitle">Quantum Flex / Ghost Node Telemetry — Rahshaun Chambers</div>
    </div>
    <div class="header-right">
      <div class="last-sync"><span class="live-dot"></span>LIVE</div>
      <div class="last-sync" style="margin-top:4px">Last sync: {ts[:19]}</div>
      <div class="last-sync" style="margin-top:4px">Substrate: Fedora 44 · AMD Ryzen AI 5 340</div>
    </div>
  </div>

  <!-- Status Banner -->
  <div class="status-banner">
    <div class="status-main">
      <div class="status-badge" style="color:{status_color};border-color:{status_color}">
        {status}
      </div>
      <div>
        <div style="font-size:0.8rem;color:var(--text-muted)">System Decision Gate</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.85rem;margin-top:2px">
          Confidence: <span style="color:{status_color}">{conf:.2f}</span>
        </div>
      </div>
    </div>
    <div class="confidence-bar-wrap">
      <div class="confidence-label">CONFIDENCE SCORE — {conf*100:.0f}%</div>
      <div class="confidence-bar">
        <div class="confidence-fill" style="width:{conf*100:.0f}%"></div>
      </div>
    </div>
  </div>

  <!-- Live Metrics -->
  <p class="section-header">Euclidean Drive Telemetry (Unified State-Bus)</p>
  <div class="metrics-grid">
    <div class="metric-card glass-panel">
      <div class="metric-label">Euclidean Drive (D)</div>
      <div class="metric-value">{drive_score:.1f}</div>
      <div class="metric-unit">tolerance: 1500.0</div>
    </div>
    <div class="metric-card glass-panel">
      <div class="metric-label">V1 · RAM Usage</div>
      <div class="metric-value">{ram_mb}</div>
      <div class="metric-unit">MB (cgroup limit: 2 GiB)</div>
    </div>
    <div class="metric-card glass-panel">
      <div class="metric-label">V2 · CPU Load</div>
      <div class="metric-value">{cpu_pct}</div>
      <div class="metric-unit">% utilization</div>
    </div>
    <div class="metric-card glass-panel">
      <div class="metric-label">V3 · I/O Wait</div>
      <div class="metric-value">{iowait}</div>
      <div class="metric-unit">% — disk pressure</div>
    </div>
    <div class="metric-card glass-panel">
      <div class="metric-label">V4 · Hash Integrity</div>
      <div class="metric-value" style="color:{'var(--green)' if hash_pen == 0 else 'var(--red)'}">{"VALID" if hash_pen == 0 else "BREACH"}</div>
      <div class="metric-unit">penalty: {hash_pen:.0f}</div>
    </div>
  </div>

  <!-- Immune C2 Panel -->
  <p class="section-header">Quantum Flex Immune Engine (C2)</p>
  <div class="immune-panel">
    <div class="immune-card glass-panel">
      <h3 style="color:var(--accent); font-size:1rem;">Biological Cell Monitor</h3>
      <p style="font-size:0.75rem; color:var(--text-muted); margin-bottom: 8px;">Real-time autonomic cryptographic state tracking.</p>
      <div class="immune-data-row">
        <span>Active KEM Tunnel</span>
        <span class="immune-val pulse-tunnel" id="active-kem-display">ML-KEM-768</span>
      </div>
      <div class="immune-data-row">
        <span>Active Signature</span>
        <span class="immune-val" id="active-sig-display">ML-DSA-65</span>
      </div>
      <div class="immune-data-row">
        <span>OPA Sidecar Polling</span>
        <span class="immune-val" style="color:var(--green)">500ms</span>
      </div>
    </div>
    
    <div class="immune-card glass-panel">
      <h3 style="color:#ff4444; font-size:1rem;">Threat Injector</h3>
      <p style="font-size:0.75rem; color:var(--text-muted); margin-bottom: 8px;">Zero-Trust authenticated kill-switch simulation.</p>
      <input type="password" id="api-key-input" class="threat-input" placeholder="Enter DASHBOARD_API_KEY..." style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); color:#fff; padding:10px; border-radius:6px; font-family:'JetBrains Mono', monospace;" />
      <div style="display:flex; gap:12px; margin-top: auto;">
        <button class="btn-premium btn-danger" style="flex:1;" onclick="injectThreat('ML-KEM-768', 'TOXIC')">Poison ML-KEM-768</button>
        <button class="btn-premium" style="flex:1; background:var(--border);" onclick="injectThreat('ML-KEM-768', 'COMPLIANT')">Clear Toxin</button>
      </div>
      <div id="threat-response" style="font-size:0.75rem; font-family:'JetBrains Mono', monospace; margin-top:8px; color:var(--green); display:none;"></div>
    </div>
  </div>

  <!-- Node Status -->
  <p class="section-header">Node Registry</p>
  <div class="nodes-grid">
    <div class="node-card">
      <div class="node-icon">🔬</div>
      <div class="node-info">
        <div class="node-name">Ghost Node Agent</div>
        <div class="node-detail">decision_gate.py · PID active</div>
      </div>
      <div class="node-status-dot" style="background:var(--green)"></div>
    </div>
    <div class="node-card">
      <div class="node-icon">📊</div>
      <div class="node-info">
        <div class="node-name">A.M.A.R.A. Dashboard</div>
        <div class="node-detail">port 8000 · uvicorn</div>
      </div>
      <div class="node-status-dot" style="background:var(--green)"></div>
    </div>
    <div class="node-card">
      <div class="node-icon">🧠</div>
      <div class="node-info">
        <div class="node-name">A.T.H.E.N.A. RAG Node</div>
        <div class="node-detail">port 8001 · ChromaDB · {athena_status}</div>
      </div>
      <div class="node-status-dot" style="background:{athena_color}"></div>
    </div>
    <div class="node-card">
      <div class="node-icon">🗄️</div>
      <div class="node-info">
        <div class="node-name">amara-matrix</div>
        <div class="node-detail">PostgreSQL 15 · Truth Log</div>
      </div>
      <div class="node-status-dot" style="background:{'var(--green)' if PG_AVAILABLE else 'var(--yellow)'}"></div>
    </div>
    <div class="node-card">
      <div class="node-icon">⚡</div>
      <div class="node-info">
        <div class="node-name">Ollama Inference</div>
        <div class="node-detail">port 11434 · {ollama_status}</div>
      </div>
      <div class="node-status-dot" style="background:{ollama_color}"></div>
    </div>
    <div class="node-card">
      <div class="node-icon">🛡️</div>
      <div class="node-info">
        <div class="node-name">Sentinel Pipeline</div>
        <div class="node-detail">quarantine_chamber.py · podman</div>
      </div>
      <div class="node-status-dot" style="background:var(--green)"></div>
    </div>
  </div>

  <!-- Active Alerts -->
  <p class="section-header">Active Alerts</p>
  <div class="alerts-box">{alerts_html}</div>

  <!-- Athena RAG Query -->
  <div class="query-box">
    <p class="section-header">A.T.H.E.N.A. RAG Query Interface</p>
    <div style="font-size:0.8rem;color:var(--text-muted)">
      Query the Athena cognitive node directly. Searches ChromaDB knowledge base.
    </div>
    <div class="query-input-row">
      <input id="rag-input" type="text"
        placeholder="Ask Athena anything about Quantum Flex..."
        onkeydown="if(event.key==='Enter')submitQuery()"/>
      <button class="btn-premium" id="rag-btn" onclick="submitQuery()">Query Athena</button>
    </div>
    <pre id="rag-output"></pre>
  </div>

  <!-- Two-column tables -->
  <div class="two-col">
    <div>
      <p class="section-header">Telemetry History (PostgreSQL)</p>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th><th>iowait</th><th>RAM</th>
              <th>Swap</th><th>Load</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {history_rows if history_rows else '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">No data yet — qf-monitor starting</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
    <div>
      <p class="section-header">Throttle Events (AMARA Reflexes)</p>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Metric</th><th>Value</th>
              <th>Thresh</th><th>Action</th><th>Result</th>
            </tr>
          </thead>
          <tbody>
            {throttle_rows if throttle_rows else '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">No throttle events — environment stable</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Sentinel Ledger History -->
  <p class="section-header">Sentinel Ledger (sentinel_service role)</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>Timestamp</th><th>Drive</th><th>RAM</th><th>CPU</th><th>IOW</th><th>Hash</th><th>Status</th></tr>
      </thead>
      <tbody>
        {''.join(f'<tr><td>{str(s.get("timestamp",""))[:19]}</td><td>{s.get("drive_score",0):.1f}</td><td>{s.get("mem_usage",0):.0f}MB</td><td>{s.get("cpu_usage",0):.2f}%</td><td>{s.get("io_wait",0):.3f}%</td><td style="color:{"var(--green)" if s.get("hash_penalty",0)==0 else "var(--red)"}">{s.get("hash_penalty",0):.0f}</td><td style="color:{"var(--green)" if s.get("status")=="EQUILIBRIUM" else "var(--red)"}">{s.get("status","?")}</td></tr>' for s in sentinel) if sentinel else '<tr><td colspan="7" style="color:var(--text-muted);text-align:center">Awaiting Sentinel data</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="footer">
    A.M.A.R.A. Agentic Framework v2.0 · Quantum Flex Infrastructure · Zero-Trust · Rootless Podman · Fedora 44 SELinux
  </div>
</div>

<script>
  // Auto-refresh every 30 seconds for the non-live tables
  setTimeout(() => location.reload(), 30000);

  // ── WebSocket State Reconciliation (The UI Pulse) ──
  const ws = new WebSocket(`ws://${{window.location.host}}/ws`);
  
  ws.onmessage = function(event) {{
      const data = JSON.parse(event.data);
      console.log("WebSocket Event:", data);
      
      if (data.type === "TRANSITION") {{
          // Triggered by immune_daemon background thread
          const kemDisplay = document.getElementById("active-kem-display");
          kemDisplay.textContent = data.new_kem;
          
          // Flash animation
          kemDisplay.style.color = "#ff4444";
          setTimeout(() => {{
              kemDisplay.style.color = "var(--accent)";
          }}, 600);
      }}
      
      if (data.type === "THREAT_FLAG") {{
          // Status updated by API
          const tr = document.getElementById("threat-response");
          tr.style.display = "block";
          tr.textContent = `[${{data.timestamp.substring(11,19)}}] OPA Bundle Updated: ${{data.algorithm}} -> ${{data.status}}`;
      }}
  }};

  async function injectThreat(algorithm, status) {{
      const apiKey = document.getElementById('api-key-input').value;
      const resDiv = document.getElementById('threat-response');
      if (!apiKey) {{
          resDiv.style.display = "block";
          resDiv.style.color = "#ff4444";
          resDiv.textContent = "[ERROR] API Key Required for C2 Execution.";
          return;
      }}
      
      try {{
          const res = await fetch('/api/threat_flag', {{
              method: 'POST',
              headers: {{
                  'Content-Type': 'application/json',
                  'x-api-key': apiKey
              }},
              body: JSON.stringify({{algorithm, status}})
          }});
          const data = await res.json();
          resDiv.style.display = "block";
          if (!res.ok) {{
              resDiv.style.color = "#ff4444";
              resDiv.textContent = "[SECURITY VIOLATION] " + data.detail;
          }} else {{
              resDiv.style.color = "var(--green)";
              resDiv.textContent = "[SUCCESS] " + data.message;
          }}
      }} catch (e) {{
          resDiv.style.display = "block";
          resDiv.style.color = "#ff4444";
          resDiv.textContent = "[ERROR] " + e;
      }}
  }}

  async function submitQuery() {{
    const input = document.getElementById('rag-input');
    const btn   = document.getElementById('rag-btn');
    const out   = document.getElementById('rag-output');
    const q = input.value.trim();
    if (!q) return;

    btn.disabled = true;
    btn.textContent = 'Querying...';
    out.style.display = 'block';
    out.textContent = '[ATHENA] Processing RAG query...';

    try {{
      const res = await fetch('/api/query', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{question: q}})
      }});
      const data = await res.json();
      if (data.error) {{
        out.textContent = '[ERROR] ' + data.error;
      }} else {{
        out.textContent = '[ANSWER]\\n' + data.answer +
          '\\n\\n[SOURCES] ' + (data.sources || []).join(', ') +
          '\\n[MODEL] ' + data.model +
          '\\n[VECTORS] ' + data.vectors;
      }}
    }} catch(e) {{
      out.textContent = '[OFFLINE] Athena node unavailable: ' + e;
    }}

    btn.disabled = false;
    btn.textContent = 'Query Athena';
  }}
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    import uvicorn
    # Zero-Trust: Bind STRICTLY to localhost. Tailscale handles mesh routing natively.
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8000, reload=False)
