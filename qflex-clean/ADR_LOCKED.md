╔══════════════════════════════════════════════════════════════════════════════╗
║                    QUANTUM FLEX — ARCHITECTURE DECISION RECORDS              ║
║                         STATUS: LOCKED. DO NOT CHANGE.                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

ADR-003: DATABASE — PostgreSQL, no extensions
  Decision : PostgreSQL 16 — zero extensions
  Reason   : CockroachDB compatibility for future horizontal scaling
  Impact   : No pgvector. ChromaDB handles ALL semantic/vector storage.
  Status   : ✅ LOCKED
 
ADR-004: SPORE BANK — ChromaDB (semantic) + PostgreSQL (episodic)
  Decision : Dual-engine persistent memory
             ChromaDB → unstructured, vector, semantic queries
             PostgreSQL → structured, episodic, audit-grade records
  Status   : ✅ LOCKED
 
ADR-005: CHEMICAL SIGNAL LAYER — NATS + JetStream
  Decision : NATS with JetStream enabled
  Rejected : Kafka (too heavy), MQTT (no persistence)
  Reason   : Single Go binary, subject-based routing, persistent replay,
             at-least-once delivery, CockroachDB orthogonal
  Config   : server_name: "quantum-mycelium-nats"
             Stream: QUANTUM_MYCELIUM
             Subjects: qm.signals.>, qm.events.>, qm.commands.>
  Status   : ✅ LOCKED

ADR-006: EXECUTION LAYER — Python + Rust
  Decision : Python for LLM agent logic
             Rust for signal bus, trust scoring, Anastomosis fusion
  Reason   : Each language in its natural domain.
             Build in Python first. Rust comes Phase 2 when hot paths identified.
  Status   : ✅ LOCKED
 
QUANTUM MYCELIUM LEXICON (OFFICIAL — DO NOT RENAME):
  Stroma          → Mycelial Core / Orchestrator
  Hyphae          → Specialized agents
  Anastomosis     → Agent context fusion (prevent duplicate compute)
  Spore Bank      → Persistent memory (ChromaDB + PostgreSQL)
  Chemical Signal → NATS/JetStream event bus
  Fruiting Body   → Collapsed high-confidence output surfaced to ROOT
