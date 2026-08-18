# qflex_memory.py
# PURPOSE: ChromaDB vector store wrapper — RAG memory layer for Quantum Flex
# VERIFIED CLEAN: No network calls, no exfiltration, local filesystem only
# NOTE: Must live in same directory as core_node.py for Docker COPY to find it

import chromadb
import os
from datetime import datetime
from pathlib import Path

CHROMA_PATH = os.environ.get("CHROMA_PATH", "./data/chroma_db")

class QFlexMemory:
    """
    Quantum Flex RAG Memory Layer.
    Persistent ChromaDB vector store for semantic memory retrieval.
    Used by SENTINEL, Core Node, and A.T.H.E.N.A. kernel.
    """

    def __init__(self, collection_name: str = "qflex_memory"):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Quantum Flex persistent RAG memory"}
        )
        print(f"[QFlexMemory] Initialized — collection: {collection_name}")

    def store(self, text: str, metadata: dict = None, doc_id: str = None) -> str:
        """Store a text document in vector memory."""
        import uuid
        if doc_id is None:
            doc_id = f"qfm-{uuid.uuid4().hex[:12]}"
        if metadata is None:
            metadata = {}
        metadata["stored_at"] = datetime.now().isoformat()

        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )
        return doc_id

    def query(self, query_text: str, n_results: int = 5) -> list:
        """Semantic similarity search against stored memory."""
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        return results.get("documents", [[]])[0]

    def delete(self, doc_id: str) -> bool:
        """Remove a document from memory."""
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False

    def count(self) -> int:
        """Return total documents in collection."""
        return self.collection.count()
