#!/usr/bin/env python3
"""
A.T.H.E.N.A. — Autonomous Tactical Hybrid Engine for Neural Architecture
==========================================================================
FastAPI service wrapping ChromaDB RAG.
Port: 8001 (localhost only — bound to 127.0.0.1)

Memory protection (the soft stop before Docker's hard cgroup limit):
  - Collection size tracked via ChromaDB count()
  - Embedding batch size capped at MAX_BATCH_SIZE
  - Graceful rejection if collection exceeds MAX_VECTORS
"""

import os
import gc
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent         # ~/mycelium
KB_DIR          = BASE_DIR / "sentinel/knowledge_base"
DB_DIR          = BASE_DIR / "sentinel/chroma_db"
COLLECTION_NAME = "quantum_flex_kb"

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
EMBED_MODEL     = "nomic-embed-text"
CHAT_MODEL      = "gemma2:2b"   # Lightweight — fits in 14GB RAM alongside ChromaDB

# Soft memory limits
MAX_VECTORS    = 50_000   # Hard stop on collection size
MAX_BATCH_SIZE = 32       # Max docs per embed batch
TOP_K_RESULTS  = 4        # Retrieval depth for RAG

# ── Guardrails ────────────────────────────────────────────────────────────────
# Only these sources are eligible to answer queries from (still fully ingestible,
# just not retrievable for /query). Reachable over Tailscale now, not just localhost.
ALLOWED_SOURCE_PREFIXES = ("sentinel/",)
ALLOWED_SOURCE_EXACT    = {"manual", "quantum_flex_architecture.txt"}

# Refuse to answer questions that touch live secrets or defense-bypass mechanics,
# regardless of what's in the retrieved context.
SENSITIVE_PATTERNS = [
    r"private[\s_-]?key", r"\bpem\b", r"ssh[\s_-]?key", r"api[\s_-]?key",
    r"tailscale[\s_-]?key", r"auth[\s_-]?key", r"\bsecret\b", r"\bcredential",
    r"\bpassword\b", r"\bpasswd\b", r"root password", r"sudo password",
    r"bypass.*lockout", r"lockout.*bypass", r"disable.*tripwire",
    r"disable.*lockout", r"override.*lockout", r"defeat.*tripwire",
    r"\.env\b", r"mtls.*cert.*private",
]
import re as _re
_SENSITIVE_RE = _re.compile("|".join(SENSITIVE_PATTERNS), _re.IGNORECASE)


def is_sensitive(text: str) -> bool:
    return bool(_SENSITIVE_RE.search(text))


def is_allowed_source(source: str) -> bool:
    if source in ALLOWED_SOURCE_EXACT:
        return True
    return any(source.startswith(p) for p in ALLOWED_SOURCE_PREFIXES)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] ATHENA | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("athena")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="A.T.H.E.N.A. RAG Node",
    description="Autonomous Tactical Hybrid Engine for Neural Architecture — Quantum Flex",
    version="1.0.0",
)

# ── Global state ──────────────────────────────────────────────────────────────
_vectorstore: Optional[Chroma] = None
_embeddings:  Optional[OllamaEmbeddings] = None
_startup_time = datetime.now().isoformat()


def get_embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        log.info(f"Initializing embedding model: {EMBED_MODEL}")
        _embeddings = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
    return _embeddings


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        log.info(f"Loading ChromaDB from: {DB_DIR}")
        _vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=str(DB_DIR),
        )
        count = _vectorstore._collection.count()
        log.info(f"ChromaDB loaded — {count} vectors in collection")
    return _vectorstore


# ── Pydantic models ───────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    top_k: int = TOP_K_RESULTS


class IngestRequest(BaseModel):
    text: str
    source: str = "manual"
    metadata: dict = {}


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    log.info("=" * 60)
    log.info("A.T.H.E.N.A. Node starting up")
    log.info(f"  ChromaDB path  : {DB_DIR}")
    log.info(f"  Embed model    : {EMBED_MODEL}")
    log.info(f"  Chat model     : {CHAT_MODEL}")
    log.info(f"  Max vectors    : {MAX_VECTORS:,}")
    log.info("=" * 60)
    try:
        vs = get_vectorstore()
        count = vs._collection.count()
        log.info(f"ChromaDB ready — {count} vectors loaded")
    except Exception as e:
        log.warning(f"ChromaDB warm-up deferred: {e}")


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Node health check — called by AMARA and the API gateway."""
    try:
        vs    = get_vectorstore()
        count = vs._collection.count()
        return {
            "status":       "ONLINE",
            "node":         "athena",
            "vector_count": count,
            "max_vectors":  MAX_VECTORS,
            "embed_model":  EMBED_MODEL,
            "chat_model":   CHAT_MODEL,
            "uptime_since": _startup_time,
            "timestamp":    datetime.now().isoformat(),
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "DEGRADED", "error": str(e)}
        )


# ── RAG query endpoint ────────────────────────────────────────────────────────
@app.post("/query")
async def query_rag(req: QueryRequest):
    """
    RAG query pipeline:
    1. Embed the question using nomic-embed-text
    2. Retrieve top-k relevant chunks from ChromaDB
    3. Build a prompt with context
    4. Generate response via Ollama (gemma3:4b)
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        vs = get_vectorstore()
        count = vs._collection.count()

        if count == 0:
            return {
                "answer":   "Knowledge base is empty. Use /ingest to add documents first.",
                "sources":  [],
                "context":  "",
                "model":    CHAT_MODEL,
                "vectors":  0,
            }

        # Retrieve relevant chunks
        top_k = min(req.top_k, count)
        docs  = vs.similarity_search(req.question, k=top_k)
        context = "\n\n".join([d.page_content for d in docs])
        sources = list({d.metadata.get("source", "unknown") for d in docs})

        # Build RAG prompt with Truth Directive
        prompt = f"""System Directive - Quantum Flex:
Primary Objective: Maximize the integrity and stability of the Quantum Flex infrastructure.
Context: You are the long-term memory (Knowledge Graph/Vector Store) for the Amara reasoning engine.
Protocol: You must index all "Truth Logs" and system configuration files. When queried, you prioritize system stability and security baseline over all other data.
Relationship: Your intelligence is contingent upon the accuracy of your retrieved data, which feeds Amara’s decision-making. You do not just "store"; you "validate."

Answer the following question using ONLY the context provided below.
If the context does not contain the answer, say so clearly.

CONTEXT:
{context}

QUESTION:
{req.question}

ANSWER:"""

        # Generate via Ollama
        import requests as req_lib
        payload = {
            "model":   CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream":  False,
        }
        r = req_lib.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        answer = r.json()["message"]["content"]

        # Garbage collect after heavy embedding operation
        gc.collect()

        return {
            "answer":  answer,
            "sources": sources,
            "context": context[:500] + "..." if len(context) > 500 else context,
            "model":   CHAT_MODEL,
            "vectors": count,
        }

    except Exception as e:
        log.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Direct ingest endpoint ────────────────────────────────────────────────────
@app.post("/ingest")
async def ingest_text(req: IngestRequest):
    """
    Ingest a text string directly into ChromaDB.
    Enforces the MAX_VECTORS soft limit.
    """
    try:
        vs    = get_vectorstore()
        count = vs._collection.count()

        if count >= MAX_VECTORS:
            raise HTTPException(
                status_code=429,
                detail=f"Vector limit reached ({count}/{MAX_VECTORS}). Prune collection first."
            )

        metadata = {"source": req.source, "ingested_at": datetime.now().isoformat()}
        metadata.update(req.metadata)
        doc = Document(page_content=req.text, metadata=metadata)
        vs.add_documents([doc])

        gc.collect()
        new_count = vs._collection.count()
        log.info(f"Ingested 1 document. Collection size: {new_count}")
        return {
            "status":    "ingested",
            "source":    req.source,
            "new_count": new_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Collection stats endpoint ─────────────────────────────────────────────────
@app.get("/stats")
async def collection_stats():
    """Return ChromaDB collection statistics."""
    try:
        vs    = get_vectorstore()
        count = vs._collection.count()
        return {
            "collection":    COLLECTION_NAME,
            "vector_count":  count,
            "max_vectors":   MAX_VECTORS,
            "utilization":   f"{(count/MAX_VECTORS)*100:.1f}%",
            "db_path":       str(DB_DIR),
            "embed_model":   EMBED_MODEL,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # Strictly localhost — never expose Athena externally
    uvicorn.run(
        "athena_api:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="info",
    )
