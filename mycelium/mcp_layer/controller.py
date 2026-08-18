#!/usr/bin/env python3
"""
Quantum Flex Swarm Controller (The Claw)
==========================================
Agent Orchestrator. Accepts a single complex directive and breaks it down
into atomic tasks. It feeds these tasks sequentially into the local Ollama instance
for structuring and inserts them into the PostgreSQL task_queue via SKIP LOCKED pattern.
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import psycopg2
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "gemma2:2b"
PG_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "telemetry", "user": os.environ["GHOSTNODE_DB_USER"],
    "password": os.environ["GHOSTNODE_DB_PASSWORD"],
}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] CONTROLLER | %(message)s")
log = logging.getLogger("claw")

# ── Pydantic Schema ───────────────────────────────────────────────────────────
class TaskSchema(BaseModel):
    target_node: str
    action: str
    parameters: dict

# ── Orchestrator Logic ────────────────────────────────────────────────────────
def init_db():
    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()
    # Ensure queue exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            status VARCHAR(20) DEFAULT 'PENDING',
            directive TEXT NOT NULL,
            task_payload JSONB NOT NULL,
            assigned_to VARCHAR(50),
            result TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    return conn

async def generate_tasks(directive: str) -> list:
    """Uses the local LLM to break down the directive."""
    prompt = f"""You are the Agent Orchestrator. Break down this directive into a JSON array of sub-tasks.
Each task must conform to this schema: {{"target_node": "string", "action": "string", "parameters": {{}}}}
Target nodes can be: "amara", "athena", "iac".

Directive: {directive}

Return ONLY valid JSON."""

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_URL}/api/generate", json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        })
        r.raise_for_status()
        response_text = r.json().get("response", "[]")
        
    try:
        tasks = json.loads(response_text)
        if isinstance(tasks, dict):
            tasks = [tasks] # Wrap in list if single object
        return tasks
    except Exception as e:
        log.error(f"Failed to parse LLM JSON output: {e}")
        return []

def queue_task(conn, directive: str, payload: dict):
    """Inserts an idempotent task into the PostgreSQL task_queue."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO task_queue (directive, task_payload, status)
        VALUES (%s, %s, 'PENDING')
        RETURNING id;
    """, (directive, json.dumps(payload)))
    task_id = cur.fetchone()[0]
    conn.commit()
    log.info(f"Queued Task [{task_id}] -> Node: {payload.get('target_node')} | Action: {payload.get('action')}")
    return task_id

async def main(directive: str):
    log.info(f"Received Directive: {directive}")
    conn = init_db()
    
    log.info(f"Querying {MODEL} for task breakdown...")
    tasks = await generate_tasks(directive)
    
    if not tasks:
        log.warning("No tasks generated. Swarm initiation aborted.")
        sys.exit(1)
        
    log.info(f"Generated {len(tasks)} sub-tasks. Queuing...")
    for t in tasks:
        queue_task(conn, directive, t)
        
    log.info("Swarm Orchestration Complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 controller.py '<directive>'")
        sys.exit(1)
    
    asyncio.run(main(sys.argv[1]))
