import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("brie_medium")

class BrieState(Enum):
    SHRED_VERIFIED = "SHRED_VERIFIED"
    SIGNING = "SIGNING"
    SIGNED_LOCAL = "SIGNED_LOCAL"
    LEDGER_PENDING = "LEDGER_PENDING"
    LEDGER_COMMITTED = "LEDGER_COMMITTED"
    COMPLETE = "COMPLETE"
    SIGNING_INTERRUPTED = "SIGNING_INTERRUPTED"
    REQUIRES_OPERATOR = "REQUIRES_OPERATOR"

class LedgerResult(Enum):
    SUCCESS = "SUCCESS"               # 201 Created or 409 Conflict (Idempotent)
    RETRYABLE_ERROR = "RETRYABLE"     # 500, 502, 503, 504, Timeout
    FATAL_ERROR = "FATAL"             # 400, 401, 403 (Bad auth, malformed request)

class ConcurrencyError(Exception):
    pass

@dataclass(frozen=True)
class AttestationContext:
    schema_version: int
    protocol_version: int
    partition_id: str
    node_id: str
    pre_purge_hash: str
    payload_hash: str
    shred_proof_hash: str
    monotonic_counter: int
    timestamp: int

    def to_canonical_bytes(self) -> bytes:
        return json.dumps(
            asdict(self), 
            sort_keys=True, 
            separators=(',', ':')
        ).encode('utf-8')

    @property
    def context_hash(self) -> str:
        return hashlib.sha256(self.to_canonical_bytes()).hexdigest()

class HybridSigner:
    """Mock HybridSigner for ML-DSA-65+Ed25519"""
    def sign(self, payload: bytes) -> bytes:
        time.sleep(0.5)
        return hashlib.sha256(b"HYBRID_SIG_" + payload).digest()

class StateManager:
    def __init__(self, db_path: str = "brie_state.db"):
        self.db_path = db_path
        self.logger = logging.getLogger("StateManager")
        self.MAX_RETRIES = 5
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS partition_state (
                    partition_id TEXT PRIMARY KEY,
                    current_state TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    last_attempt TIMESTAMP,
                    attestation_bundle BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state_journal (
                    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    partition_id TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    previous_journal_hash TEXT,
                    transitioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def _journal_transition(self, conn: sqlite3.Connection, partition_id: str, prev_state: str, new_state: str, actor: str = "brie_daemon"):
        cursor = conn.execute("SELECT event_hash FROM state_journal ORDER BY journal_id DESC LIMIT 1")
        row = cursor.fetchone()
        prev_journal_hash = row[0] if row else "0000000000000000000000000000000000000000000000000000000000000000"

        timestamp = int(datetime.now(timezone.utc).timestamp())
        raw_event = f"{prev_journal_hash}:{prev_state}:{new_state}:{timestamp}:{partition_id}".encode('utf-8')
        event_hash = hashlib.sha256(raw_event).hexdigest()

        conn.execute(
            """
            INSERT INTO state_journal 
            (partition_id, previous_state, new_state, actor, event_hash, previous_journal_hash) 
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (partition_id, prev_state, new_state, actor, event_hash, prev_journal_hash)
        )

    def transition(self, partition_id: str, new_state: BrieState):
        with sqlite3.connect(self.db_path, isolation_level="IMMEDIATE") as conn:
            cursor = conn.execute(
                "SELECT current_state FROM partition_state WHERE partition_id = ?",
                (partition_id,)
            )
            row = cursor.fetchone()
            old_state = row[0] if row else "UNKNOWN"
            
            conn.execute(
                """
                UPDATE partition_state 
                SET current_state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE partition_id = ?
                """,
                (new_state.value, partition_id)
            )
            self._journal_transition(conn, partition_id, old_state, new_state.value)
            conn.commit()

    def increment_network_retry(self, partition_id: str) -> int:
        with sqlite3.connect(self.db_path, isolation_level="IMMEDIATE") as conn:
            cursor = conn.execute(
                "SELECT retry_count FROM partition_state WHERE partition_id = ?",
                (partition_id,)
            )
            row = cursor.fetchone()
            if not row:
                return 0
            
            new_retry = row[0] + 1
            conn.execute(
                """
                UPDATE partition_state 
                SET retry_count = ?, last_attempt = CURRENT_TIMESTAMP
                WHERE partition_id = ?
                """,
                (new_retry, partition_id)
            )
            conn.commit()
            return new_retry

    def reset_retries(self, partition_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE partition_state SET retry_count = 0 WHERE partition_id = ?",
                (partition_id,)
            )
            conn.commit()

    def attest_partition(self, context: AttestationContext, signer: HybridSigner) -> bytes:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT current_state FROM partition_state WHERE partition_id = ?", 
                (context.partition_id,)
            )
            row = cursor.fetchone()
            
            if not row or row[0] != BrieState.SHRED_VERIFIED.value:
                raise ValueError(f"Invalid state for attestation: {row[0] if row else 'NOT FOUND'}")

        self.transition(context.partition_id, BrieState.SIGNING)

        try:
            payload = context.context_hash.encode('utf-8')
            signature_bundle = signer.sign(payload)
            
            full_bundle = json.dumps({
                "algorithm": "ML-DSA-65+Ed25519",
                "signature": signature_bundle.hex(),
                "context_hash": context.context_hash,
                "version": context.protocol_version
            }).encode('utf-8')

        except Exception as e:
            self.handle_signing_failure(context.partition_id, str(e))
            self.transition(context.partition_id, BrieState.SIGNING_INTERRUPTED)
            raise

        with sqlite3.connect(self.db_path, isolation_level="IMMEDIATE") as conn:
            cursor = conn.execute(
                """
                UPDATE partition_state 
                SET current_state = ?, 
                    attestation_bundle = ?, 
                    updated_at = CURRENT_TIMESTAMP,
                    retry_count = 0,
                    last_error = NULL
                WHERE partition_id = ? AND current_state = ?
                """,
                (
                    BrieState.SIGNED_LOCAL.value, 
                    full_bundle, 
                    context.partition_id, 
                    BrieState.SIGNING.value
                )
            )
            
            if cursor.rowcount == 0:
                conn.rollback()
                self.logger.warning(f"[{context.partition_id}] Concurrency collision. Aborting update.")
                raise ConcurrencyError("State changed during cryptographic signing.")

            self._journal_transition(conn, context.partition_id, BrieState.SIGNING.value, BrieState.SIGNED_LOCAL.value)
            conn.commit()
            
            return full_bundle

    def handle_signing_failure(self, partition_id: str, error_msg: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE partition_state 
                SET last_error = ?, last_attempt = CURRENT_TIMESTAMP
                WHERE partition_id = ?
                """,
                (error_msg, partition_id)
            )
            conn.commit()
            self.logger.error(f"[{partition_id}] Signing failure recorded: {error_msg}")

    def register_shredded_partition(self, partition_id: str):
        with sqlite3.connect(self.db_path, isolation_level="IMMEDIATE") as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO partition_state (partition_id, current_state)
                VALUES (?, ?)
                """,
                (partition_id, BrieState.SHRED_VERIFIED.value)
            )
            conn.commit()

    def get_bundle(self, partition_id: str) -> Optional[bytes]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT attestation_bundle FROM partition_state WHERE partition_id = ?", (partition_id,))
            row = cursor.fetchone()
            return row[0] if row else None

class LedgerClient:
    def __init__(self, endpoint: str = "https://amara.matrix.internal/v1/commit"):
        self.endpoint = endpoint
        self.logger = logging.getLogger("LedgerClient")
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _generate_commit_id(self, partition_id: str, context_hash: str, signature: str) -> str:
        sig_hash = hashlib.sha256(signature.encode('utf-8')).hexdigest()
        raw_id = f"{partition_id}:{context_hash}:{sig_hash}".encode('utf-8')
        return hashlib.sha256(raw_id).hexdigest()

    def transmit(self, commit_id: str, payload: dict) -> LedgerResult:
        try:
            # Mock matrix request
            class MockResponse:
                status_code = 409
                def json(self): return {"acknowledged_commit_id": commit_id}
            
            response = MockResponse()
            
            if response.status_code in (201, 409):
                if response.json().get("acknowledged_commit_id") == commit_id:
                    return LedgerResult.SUCCESS
                return LedgerResult.FATAL_ERROR
                
            if response.status_code >= 500:
                return LedgerResult.RETRYABLE_ERROR
                
            return LedgerResult.FATAL_ERROR
            
        except requests.exceptions.RequestException:
            return LedgerResult.RETRYABLE_ERROR

def process_ledger_pending(state_manager: StateManager, ledger_client: LedgerClient, partition_id: str, bundle_bytes: bytes):
    bundle = json.loads(bundle_bytes.decode('utf-8'))
    commit_id = ledger_client._generate_commit_id(
        partition_id, 
        bundle['context_hash'], 
        bundle['signature']
    )
    
    payload = {
        "commit_id": commit_id,
        "partition_id": partition_id,
        "attestation": bundle
    }
    
    result = ledger_client.transmit(commit_id, payload)
    
    if result == LedgerResult.SUCCESS:
        state_manager.transition(partition_id, BrieState.LEDGER_COMMITTED)
        state_manager.transition(partition_id, BrieState.COMPLETE)
        logger.info(f"[{partition_id}] Successfully transmitted and completed.")
    elif result == LedgerResult.RETRYABLE_ERROR:
        retries = state_manager.increment_network_retry(partition_id)
        if retries > state_manager.MAX_RETRIES:
            state_manager.transition(partition_id, BrieState.REQUIRES_OPERATOR)
            logger.error(f"[{partition_id}] Exceeded max retries. Escalating to REQUIRES_OPERATOR.")
        else:
            logger.warning(f"[{partition_id}] Network error. Retrying later (attempt {retries}).")
    elif result == LedgerResult.FATAL_ERROR:
        state_manager.transition(partition_id, BrieState.REQUIRES_OPERATOR)
        logger.error(f"[{partition_id}] Fatal matrix error. Escalating to REQUIRES_OPERATOR.")

def recover_state(state_manager: StateManager, ledger_client: LedgerClient, signer: HybridSigner):
    logger.info("[*] Sweeping WAL for boot recovery...")
    
    with sqlite3.connect(state_manager.db_path) as conn:
        cursor = conn.execute("SELECT partition_id, current_state FROM partition_state WHERE current_state NOT IN (?, ?)", (BrieState.COMPLETE.value, BrieState.REQUIRES_OPERATOR.value))
        rows = cursor.fetchall()

    if not rows:
        logger.info("[+] No pending states. Node cleanly synchronized.")
        return

    for partition_id, current_state in rows:
        logger.info(f"Recovering partition {partition_id} from {current_state}")
        
        if current_state == BrieState.LEDGER_PENDING.value or current_state == BrieState.SIGNED_LOCAL.value:
            bundle = state_manager.get_bundle(partition_id)
            if bundle:
                state_manager.transition(partition_id, BrieState.LEDGER_PENDING)
                process_ledger_pending(state_manager, ledger_client, partition_id, bundle)
            else:
                logger.error(f"Partition {partition_id} marked as {current_state} but missing bundle! Rolling back.")
                state_manager.transition(partition_id, BrieState.SHRED_VERIFIED)
                
        elif current_state == BrieState.SIGNING.value or current_state == BrieState.SIGNING_INTERRUPTED.value:
            state_manager.transition(partition_id, BrieState.SHRED_VERIFIED)
            
        elif current_state == BrieState.SHRED_VERIFIED.value:
            ctx = AttestationContext(
                schema_version=1,
                protocol_version=2,
                partition_id=partition_id,
                node_id="quantum_node_1",
                pre_purge_hash="abc123hash",
                payload_hash="payload_hx",
                shred_proof_hash="shred_hx",
                monotonic_counter=1,
                timestamp=int(datetime.now(timezone.utc).timestamp())
            )
            bundle = state_manager.attest_partition(ctx, signer)
            state_manager.transition(partition_id, BrieState.LEDGER_PENDING)
            process_ledger_pending(state_manager, ledger_client, partition_id, bundle)

if __name__ == "__main__":
    logger.info("Starting Brie Node Execution...")
    sm = StateManager()
    lc = LedgerClient()
    hs = HybridSigner()
    
    test_partition = "part_005"
    sm.register_shredded_partition(test_partition)
    
    ctx = AttestationContext(
        schema_version=1,
        protocol_version=2,
        partition_id=test_partition,
        node_id="quantum_node_1",
        pre_purge_hash="hash456",
        payload_hash="payload_hx",
        shred_proof_hash="shred_hx",
        monotonic_counter=2,
        timestamp=int(datetime.now(timezone.utc).timestamp())
    )
    
    logger.info("Initiating Attestation with Optimistic Concurrency...")
    try:
        bundle = sm.attest_partition(ctx, hs)
        logger.info(f"Attestation Complete. Transmitting...")
        sm.transition(test_partition, BrieState.LEDGER_PENDING)
        process_ledger_pending(sm, lc, test_partition, bundle)
    except ConcurrencyError as e:
        logger.error(f"Concurrency collision detected: {e}")
        
    recover_state(sm, lc, hs)
    logger.info("Brie Node Execution Finished.")
