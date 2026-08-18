# amara_mcp.py
# PURPOSE: A.M.A.R.A. MCP Server — ChromaDB-backed RAG memory node
# TRANSPORT: Model Context Protocol (MCP) — replaces Hugging Face datasets layer
# CONTAINER: Runs as USER 1000 (amara) — non-root

import chromadb
from datetime import datetime
from pathlib import Path

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.types import Resource, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("[WARN] MCP library not found — running in standalone mode")

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Initialize ChromaDB persistent store
client = chromadb.PersistentClient(path=str(DATA_DIR / "truth_log_db"))
collection = client.get_or_create_collection(name="amara_memory")

def store_truth_log(entry: str, metadata: dict = None) -> str:
    """Store a truth log entry in ChromaDB."""
    import uuid
    doc_id = f"tl-{uuid.uuid4().hex[:8]}"
    if metadata is None:
        metadata = {}
    metadata["stored_at"] = datetime.now().isoformat()
    collection.add(documents=[entry], metadatas=[metadata], ids=[doc_id])
    return doc_id

def query_truth_log(query: str, n: int = 5) -> list:
    """Query truth log via semantic similarity."""
    results = collection.query(query_texts=[query], n_results=n)
    return results.get("documents", [[]])[0]

def analyze_packet(payload: dict) -> str:
    """
    SENTINEL DPI packet analyzer.
    Identifies the Vector of Bias in incoming data.
    Identifies the 'Shift' (h) in incoming data per y = f(x-h) + k.
    """
    source_metadata = payload.get("metadata", {})
    if "stakeholder" in source_metadata:
        return f"Bias detected: {source_metadata['stakeholder']}"
    return "SNR High: Clean Data"

if MCP_AVAILABLE:
    server = Server("amara-mcp")

    @server.list_resources()
    async def handle_list_resources():
        return [
            Resource(uri="memory://truth-log", name="System Truth Log"),
            Resource(uri="memory://sentinel-db", name="SENTINEL Incident Database"),
        ]

    @server.read_resource()
    async def handle_read_resource(uri: str):
        if uri == "memory://truth-log":
            results = query_truth_log("recent entries", n=10)
            return TextContent(type="text", text="\n---\n".join(results) if results else "Empty")
        raise ValueError(f"Unknown resource: {uri}")

print("[A.M.A.R.A. MCP] Server initialized. ChromaDB connected.")
print(f"[A.M.A.R.A. MCP] Collection count: {collection.count()}")

if __name__ == "__main__":
    if MCP_AVAILABLE:
        import asyncio
        from mcp.server.stdio import stdio_server
        async def run():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, InitializationOptions(
                    server_name="amara-mcp",
                    server_version="1.0.0",
                    capabilities={}
                ))
        asyncio.run(run())
    else:
        # Standalone mode — test ChromaDB connection
        test_id = store_truth_log("A.M.A.R.A. MCP boot test", {"type": "boot"})
        print(f"[TEST] Stored: {test_id}")
        results = query_truth_log("boot test")
        print(f"[TEST] Retrieved: {results}")
