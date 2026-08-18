from fastapi import FastAPI, Request
import asyncio
import httpx
import os
from datetime import datetime

app = FastAPI(title="Quantum Flex Core Node API", version="2.0.0")

# Correct absolute paths for this host
ORCHESTRATOR = "/home/rahshaunchambers/mycelium/run_sentinel.py"
ATHENA_URL = "http://127.0.0.1:8001"

# Each ingest request spawns a full python3 subprocess (run_sentinel.py).
# Without a cap, a burst of requests spawns unbounded concurrent subprocesses
# and can exhaust host RAM/CPU. This bounds concurrent subprocess execution;
# excess requests wait for a slot instead of each spawning immediately.
INGEST_CONCURRENCY_LIMIT = int(os.environ.get("INGEST_CONCURRENCY_LIMIT", "4"))
_ingest_semaphore = asyncio.Semaphore(INGEST_CONCURRENCY_LIMIT)


async def run_orchestrator(*args: str) -> tuple[int, bytes, bytes]:
    """Run run_sentinel.py as a subprocess, bounded by _ingest_semaphore."""
    async with _ingest_semaphore:
        process = await asyncio.create_subprocess_exec(
            "python3", ORCHESTRATOR, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout, stderr


@app.get("/status")
async def system_status():
    """Full health check of all Quantum Flex nodes."""
    nodes = {}

    # Check Athena RAG node
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{ATHENA_URL}/health")
            nodes["athena"] = r.json()
    except Exception as e:
        nodes["athena"] = {"status": "OFFLINE", "error": str(e)}

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            nodes["ollama"] = {"status": "ONLINE", "models": models}
    except Exception as e:
        nodes["ollama"] = {"status": "OFFLINE", "error": str(e)}

    return {
        "timestamp": datetime.now().isoformat(),
        "api_node": "ONLINE",
        "nodes": nodes
    }


@app.post("/query")
async def query_athena(request: Request):
    """Route a RAG query to the Athena node."""
    data = await request.json()
    question = data.get("question", "")
    if not question:
        return {"status": "error", "message": "No question provided"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{ATHENA_URL}/query", json={"question": question})
            return r.json()
    except Exception as e:
        return {"status": "fatal", "error": str(e)}


@app.post("/ingest")
async def ingest_payload(request: Request):
    """Stage a file into the Sentinel quarantine pipeline."""
    data = await request.json()
    file_path = data.get("file_path")

    if not file_path:
        return {"status": "error", "message": "No file_path provided"}

    print(f"[>>] API Received Ingestion Request for: {file_path}")

    try:
        returncode, stdout, stderr = await run_orchestrator(file_path)

        if returncode == 0:
            return {"status": "success", "telemetry": stdout.decode().strip()}
        else:
            return {"status": "fatal", "error": stderr.decode().strip()}
    except Exception as e:
        return {"status": "fatal", "error": str(e)}


@app.post("/webhook/ingest")
async def webhook_ingest(request: Request):
    """Stage raw HTTP POST JSON payload directly into the Sentinel sandbox."""
    try:
        data = await request.json()
    except Exception as e:
        return {"status": "error", "message": f"Invalid JSON payload: {e}"}

    import random
    temp_dir = "/home/rahshaunchambers/.gemini/antigravity-ide/scratch/quantum-flex_HIDDEN/quarantine"
    os.makedirs(temp_dir, exist_ok=True)
    
    filename = f"webhook_{int(datetime.now().timestamp())}_{random.randint(100, 999)}.json"
    temp_file_path = os.path.join(temp_dir, filename)

    try:
        with open(temp_file_path, "w") as f:
            import json
            json.dump(data, f)
            
        returncode, stdout, stderr = await run_orchestrator(temp_file_path)

        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if returncode == 0:
            return {"status": "success", "telemetry": stdout.decode().strip()}
        else:
            return {"status": "fatal", "error": stderr.decode().strip()}
            
    except Exception as e:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        return {"status": "fatal", "error": str(e)}
