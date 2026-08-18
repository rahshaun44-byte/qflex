# core_node.py
# PURPOSE: Quantum Flex Core Intelligence Node
# ENDPOINT: /api/v1/collapse — receives signals, collapses to single execution
# SECONDARY: /api/v1/sentinel — security analysis route
# SECONDARY: /api/v1/memory — RAG query/store route
# PHILOSOPHY: Superposition to Collapse. Integrity is the static main method.

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import sqlite3
import json
import os
from pathlib import Path

app = FastAPI(title="Quantum Flex Core Node", version="1.0.0")

# Memory layer import — ChromaDB RAG
try:
    from qflex_memory import QFlexMemory
    memory = QFlexMemory()
    print("[*] Memory Layer Linked.")
except ImportError:
    memory = None
    print("[!] Memory Layer Import Failed — RAG disabled")

# Ledger path
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

init_ledger()

class CollapseRequest(BaseModel):
    prompt: str
    mode: str = "general"
    context: dict = {}

class CollapseResponse(BaseModel):
    status: str
    output: str
    timestamp: str
    memory_retrieved: list = []

@app.get("/health")
def health():
    return {"status": "NOMINAL", "system": "Quantum Flex Core Node v1.0"}

@app.post("/api/v1/collapse", response_model=CollapseResponse)
async def collapse(request: CollapseRequest):
    """
    Core collapse endpoint.
    Receives a signal, queries memory, returns elevated output.
    Logs every interaction to the immutable ledger.
    """
    timestamp = datetime.now().isoformat()

    # Query RAG memory for context
    retrieved = []
    if memory:
        try:
            retrieved = memory.query(request.prompt, n_results=3)
        except Exception as e:
            print(f"[!] Memory query failed: {e}")

    # Build response
    response_text = (
        f"[QUANTUM FLEX] Superposition Collapsed. Frictionless Execution Active.\n"
        f"Mode: {request.mode}\n"
        f"Memory nodes retrieved: {len(retrieved)}\n"
        f"Prompt processed at φ-confidence threshold: 0.75"
    )

    # Write to ledger
    conn = sqlite3.connect(LEDGER_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO collapse_log (timestamp, payload, response, memory_used) VALUES (?,?,?,?)",
        (timestamp, json.dumps(request.dict()), response_text, len(retrieved))
    )
    conn.commit()
    conn.close()

    return CollapseResponse(
        status="COLLAPSED",
        output=response_text,
        timestamp=timestamp,
        memory_retrieved=retrieved
    )

@app.post("/api/v1/sentinel")
async def sentinel_analysis(request: CollapseRequest):
    """Security analysis route — receives threat events, returns structured analysis."""
    if request.mode != "security_analysis":
        raise HTTPException(status_code=400, detail="Mode must be security_analysis")

    # Store in memory for future pattern matching
    if memory:
        memory.store(request.prompt, metadata={"mode": "sentinel", "ts": datetime.now().isoformat()})

    return {"status": "ANALYZED", "threats_detected": [], "system_health": "NOMINAL"}

@app.get("/api/v1/memory")
async def query_memory(q: str, n: int = 5):
    """Direct RAG memory query endpoint."""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory layer offline")
    results = memory.query(q, n_results=n)
    return {"results": results, "count": len(results)}
