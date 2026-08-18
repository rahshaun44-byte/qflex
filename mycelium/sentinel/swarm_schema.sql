-- pgvector extension initialization
CREATE EXTENSION IF NOT EXISTS vector;

-- Memory Logs table for Persistent Long-Term Memory (RAG)
CREATE TABLE IF NOT EXISTS memory_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    agent_id VARCHAR(50) NOT NULL,
    context_vector VECTOR(768),
    action_taken TEXT NOT NULL,
    outcome TEXT NOT NULL
);

-- HNSW index for high-performance approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_memory_logs_vector 
ON memory_logs USING hnsw (context_vector vector_cosine_ops);

-- Task Queue table for the Swarm Orchestrator (The Claw)
CREATE TABLE IF NOT EXISTS task_queue (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, RUNNING, COMPLETED, FAILED
    directive TEXT NOT NULL,
    task_payload JSONB NOT NULL,
    assigned_to VARCHAR(50),
    result TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- High-performance polling index for the PENDING state, ordered by insertion time
CREATE INDEX IF NOT EXISTS idx_task_queue_status 
ON task_queue (status, id) 
WHERE status = 'PENDING';
