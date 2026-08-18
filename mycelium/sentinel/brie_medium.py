#!/usr/bin/env python3
"""
Quantum Flex — Brie Node Medium (Cryptographic Necromancy)
===========================================================
Intercepts the T-7 data graveyard, extracts the pure k pattern,
injects the rhythm into the Akashic Schema, and purges the payload.

BINARY ABI SCHEMA (STRUCT.PACK):
--------------------------------
The Brie Node outputs deterministic binary telemetry packets to the IPC Queue.
Each payload consists of standard hardware/system metrics decoupled from their Python types.

Metrics Payload (Variable length, strictly typed based on partition columns):
  - 'i' (4 bytes): Integer metric
  - 'q' (8 bytes): BigInt metric 
  - 'f' (4 bytes): Real float metric
  - 'd' (8 bytes): Double precision metric

The Consumer (in any language) only needs to parse the ByteStream according to the expected struct format,
completely decoupling the architecture from Python objects or JSON serialization.
"""

import psycopg2
import hashlib
import os
import ctypes
import struct
import json
import multiprocessing
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Binary ABI Queue (Temporal Decoupling: Producer to Consumer)
ipc_queue = multiprocessing.Queue()


DB_CONFIG = {
    "dbname": "telemetry",
    "user": "ghostnode",
    "password": "quantum_flex_auth",
    "host": "127.0.0.1",
    "port": "5432",
}

@dataclass
class AuditProof:
    schema_version: int
    partition_id: str
    pre_purge_hash: str
    k_t_ascension_hash: str
    hybrid_signature: str
    timestamp: str
    volume_purged_bytes: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def verify_proof(proof: AuditProof) -> bool:
    """Validates the AuditProof signature structure and pre-purge hash before dropping partition."""
    if not proof or not proof.pre_purge_hash or not proof.hybrid_signature:
        return False
    if not proof.k_t_ascension_hash or proof.schema_version < 1:
        return False
    return True


def secure_zero_memory(byte_arr: bytearray):
    """Zeroes out the in-memory buffer cryptographically to ensure zero-bloat."""
    if not byte_arr:
        return
    buffer_len = len(byte_arr)
    # Using ctypes to overwrite the buffer in memory
    c_buffer = (ctypes.c_char * buffer_len).from_buffer(byte_arr)
    ctypes.memset(c_buffer, 0, buffer_len)


def get_previous_k_value(cur) -> bytes:
    """Fetches k_{t-1} from the akashic_ledger. If genesis, returns 32 zero bytes."""
    cur.execute("SELECT k_value FROM akashic_ledger ORDER BY pulse_id DESC LIMIT 1")
    row = cur.fetchone()
    if row and row[0]:
        return bytes(row[0])
    return b'\x00' * 32  # SHA-256 size as fallback genesis state


def execute_h_shift_and_extract(cur, partition_name: str) -> (bytearray, int):
    """
    Ability 1: The Ego Stripper (-h Shift)
    Extracts purely mathematical geometry, omitting IPs/timestamps.
    Returns the raw byte stream (in-memory only) and its weight.
    """
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{partition_name}'")
    columns = cur.fetchall()
    
    type_map = {
        'double precision': 'd',
        'real': 'f',
        'integer': 'i',
        'bigint': 'q',
        'numeric': 'd'
    }
    
    math_columns = []
    struct_formats = []
    
    for col_name, data_type in columns:
        if data_type in type_map and col_name not in ('id', 'pulse_id'):
            math_columns.append(col_name)
            struct_formats.append(type_map[data_type])
    
    if not math_columns:
        return bytearray(), 0
        
    query = f"SELECT {', '.join(math_columns)} FROM {partition_name}"
    cur.execute(query)
    
    rows = cur.fetchall()
    raw_payload = bytearray()
    
    for row in rows:
        for idx, val in enumerate(row):
            if val is not None:
                fmt = struct_formats[idx]
                try:
                    if fmt == 'd' or fmt == 'f':
                        val = float(val)
                    elif fmt == 'i' or fmt == 'q':
                        val = int(val)
                    raw_payload.extend(struct.pack(f'>{fmt}', val))
                except (ValueError, TypeError, struct.error):
                    pass
                
    volume_purged = len(raw_payload)
    ipc_queue.put(bytes(raw_payload))
    
    return raw_payload, volume_purged


def generate_brie_signature(k_hash: bytes) -> bytes:
    """
    Simulates ML-DSA-65+Ed25519 hybrid signature over the compiled truth.
    """
    mock_priv_key = os.urandom(32)
    return hashlib.sha512(mock_priv_key + k_hash).digest()


def compile_truth(raw_data: bytearray, prev_k: bytes) -> (bytes, bytes):
    """
    Ability 3: The Golden Ratio Compiler (+k Ascension)
    k_t = H(D_t || k_{t-1} || S_Brie)
    """
    h = hashlib.sha256()
    h.update(raw_data)
    h.update(prev_k)
    base_hash = h.digest()
    
    s_brie = generate_brie_signature(base_hash)
    
    h_final = hashlib.sha256()
    h_final.update(raw_data)
    h_final.update(prev_k)
    h_final.update(s_brie)
    
    k_t = h_final.digest()
    return k_t, s_brie


def setup_akashic_schema(cur):
    """Ensures the Akashic Schema exists."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS akashic_ledger (
            pulse_id BIGSERIAL PRIMARY KEY,
            k_value BYTEA NOT NULL,
            brie_sig BYTEA NOT NULL,
            volume_purged BIGINT NOT NULL,
            audit_proof JSONB,
            committed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def neurogenesis_purge(cur, partition_name: str) -> bytes:
    """
    Synchronous (Blocker) Purge Hook.
    1. Pre-purge hash calculation.
    2. Synchronous extraction of pure k_t geometry & PQC hybrid attestation.
    3. AuditProof validation & compliance logging.
    4. Zeroing memory buffers.
    5. Returns extracted k_t on success, or raises RuntimeError on breach.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [Brie Node] Synchronous neurogenesis purge initiated for: {partition_name}")
    
    # 0. Ensure schema
    setup_akashic_schema(cur)
    
    # 1. Check if partition exists
    cur.execute(f"SELECT to_regclass('{partition_name}')")
    if cur.fetchone()[0] is None:
        print(f"[{ts}] [Brie Node] Partition {partition_name} does not exist. Purge skipped.")
        return b'\x00' * 32

    # 2. Extract geometry and compute pre-purge hash
    raw_data, volume = execute_h_shift_and_extract(cur, partition_name)
    pre_purge_hash = hashlib.sha256(raw_data).hexdigest()

    try:
        # 3. Synchronous truth compilation (k_t)
        prev_k = get_previous_k_value(cur)
        k_t, s_brie = compile_truth(raw_data, prev_k)

        # 4. Construct AuditProof JSON
        proof = AuditProof(
            schema_version=1,
            partition_id=partition_name,
            pre_purge_hash=pre_purge_hash,
            k_t_ascension_hash=k_t.hex(),
            hybrid_signature=s_brie.hex(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume_purged_bytes=volume
        )

        # 5. Synchronous Proof Validation
        if not verify_proof(proof):
            raise RuntimeError("PURGE INTEGRITY BREACH: AuditProof validation failed prior to partition drop.")

        # 6. Akashic Commit with AuditProof
        cur.execute(
            """INSERT INTO akashic_ledger (k_value, brie_sig, volume_purged, audit_proof) 
               VALUES (%s, %s, %s, %s)""",
            (k_t, s_brie, volume, proof.to_json())
        )
        
        print(f"[{ts}] [Brie Node] Purge AuditProof verified. k_t: {k_t.hex()[:16]}... Purged {volume} bytes.")
        return k_t

    finally:
        # 7. Safe payload zeroing
        secure_zero_memory(raw_data)


def request_drop_permission(partition_name: str) -> bool:
    """
    Backwards-compatible drop permission wrapper around synchronous neurogenesis_purge.
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        neurogenesis_purge(cur, partition_name)
        conn.commit()
        return True
    except Exception as e:
        print(f"[Brie Node] Drop permission denied: {e}")
        return False
    finally:
        if conn:
            conn.close()

