import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Configuration
KB_DIR = "sentinel/knowledge_base"
DB_DIR = "sentinel/chroma_db"

def ingest_knowledge():
    # Verify Knowledge Base exists
    if not os.path.exists(KB_DIR):
        print(f"Error: {KB_DIR} not found. Please create it and add .txt files.")
        return

    # Check for files
    files = [f for f in os.listdir(KB_DIR) if f.endswith(".txt")]
    if not files:
        print(f"Error: No .txt files found in {KB_DIR}")
        return

    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    documents = []

    # Load files
    for filename in files:
        print(f"Loading: {filename}")
        loader = TextLoader(os.path.join(KB_DIR, filename))
        documents.extend(loader.load())

    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    texts = text_splitter.split_documents(documents)

    # Vectorize
    print(f"Indexing {len(texts)} chunks...")
    Chroma.from_documents(texts, embeddings, persist_directory=DB_DIR)
    print(f"Success. Database persisted to {DB_DIR}")

if __name__ == "__main__":
    ingest_knowledge()
