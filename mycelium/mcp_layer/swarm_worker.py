#!/usr/bin/env python3
"""
Quantum Flex Swarm Worker
===========================
Constantly polls the PostgreSQL task_queue using FOR UPDATE SKIP LOCKED
to prevent concurrent workers from picking up the same task.
Executes the task payload, updates status to COMPLETED/FAILED, 
and logs the outcome to memory_logs.
"""

import os
import time
import json
import logging
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PG_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "telemetry", "user": os.environ["GHOSTNODE_DB_USER"],
    "password": os.environ["GHOSTNODE_DB_PASSWORD"],
}
AGENT_ID = "swarm_worker_01"

logging.basicConfig(level=logging.INFO, format=f"[%(asctime)s] {AGENT_ID} | %(message)s")
log = logging.getLogger(AGENT_ID)

def get_db():
    return psycopg2.connect(**PG_CONFIG)

def poll_task():
    """Polls the queue using SKIP LOCKED for concurrent safety."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Fetch and lock the next pending task
    cur.execute("""
        SELECT id, directive, task_payload 
        FROM task_queue 
        WHERE status = 'PENDING' 
        ORDER BY id ASC 
        FOR UPDATE SKIP LOCKED 
        LIMIT 1;
    """)
    task = cur.fetchone()
    
    if not task:
        conn.rollback()
        cur.close()
        conn.close()
        return None
        
    # 2. Mark as RUNNING
    task_id = task['id']
    cur.execute("""
        UPDATE task_queue 
        SET status = 'RUNNING', assigned_to = %s, updated_at = NOW() 
        WHERE id = %s;
    """, (AGENT_ID, task_id))
    conn.commit()
    cur.close()
    conn.close()
    
    return task

def execute_task(task):
    """Executes the specific atomic task logic."""
    payload = task['task_payload']
    target = payload.get('target_node', 'unknown')
    action = payload.get('action', 'unknown')
    
    log.info(f"Executing Task [{task['id']}] -> target: {target}, action: {action}")
    
    # Simulate execution logic (IaC deployment, RAG query, etc)
    # In full production, this dispatches to specific handlers.
    time.sleep(2) 
    
    outcome = f"Successfully executed action '{action}' on node '{target}'"
    return "COMPLETED", outcome

def complete_task(task_id, status, outcome):
    """Updates the task queue and logs to persistent memory."""
    conn = get_db()
    cur = conn.cursor()
    
    # Update queue
    cur.execute("""
        UPDATE task_queue 
        SET status = %s, result = %s, updated_at = NOW() 
        WHERE id = %s;
    """, (status, outcome, task_id))
    
    # Insert into memory_logs (null vector for now, can be hydrated later via Athena)
    cur.execute("""
        INSERT INTO memory_logs (agent_id, action_taken, outcome)
        VALUES (%s, %s, %s);
    """, (AGENT_ID, f"Task {task_id}", outcome))
    
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"Task [{task_id}] marked as {status}. Memory updated.")

def main():
    log.info("Swarm Worker Online. Polling for tasks...")
    while True:
        try:
            task = poll_task()
            if task:
                status, outcome = execute_task(task)
                complete_task(task['id'], status, outcome)
            else:
                time.sleep(3) # Idle backoff
        except Exception as e:
            log.error(f"Worker fault: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
