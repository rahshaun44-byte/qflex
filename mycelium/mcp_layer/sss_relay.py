#!/usr/bin/env python3
"""
Quantum Flex: Dedicated SSS Shard Relay
=======================================
This worker focuses entirely on the mathematical heavy lifting of Shamir's Secret Sharing (SSS)
shards. It ingests a shard, encapsulates it in the currently active liboqs algorithm, and routes it.

It reacts gracefully to SIGHUP. When the immune daemon sends SIGHUP due to a Rego policy violation,
this relay will:
1. Hold any in-flight shards in the local volatile memory buffer.
2. Read the new algorithm from `crypto_provider.conf`.
3. Re-encapsulate the held shards in the new algorithm.
4. Continue routing.
"""

import signal
import sys
import time
import logging
from pathlib import Path

# Stub for oqs-python since we simulate it outside the container if testing locally
try:
    import oqs
    OQS_AVAILABLE = True
except ImportError:
    OQS_AVAILABLE = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None
import os

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] SSS_RELAY | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("sss_relay")

PROVIDER_CONF = Path("/opt/pqc-worker/crypto_provider.conf")

class SSSRelay:
    def __init__(self):
        self.active_kem = "ML-KEM-768"
        self.active_sig = "ML-DSA-65"
        self.reload_config()
        self.buffer = [] # Volatile buffer for in-flight shards
        
    def reload_config(self):
        """Read the active algorithms from the mutable config file."""
        old_kem = self.active_kem
        try:
            for line in PROVIDER_CONF.read_text().splitlines():
                if line.strip().startswith("active_kem"):
                    self.active_kem = line.split("=")[1].strip()
                elif line.strip().startswith("active_sig"):
                    self.active_sig = line.split("=")[1].strip()
        except Exception as e:
            log.warning(f"Could not read config, using defaults: {e}")
            
        if old_kem != self.active_kem:
            log.info(f"Mycelial Handshake: Tunnel renegotiated from {old_kem} to {self.active_kem}")
            self.re_encapsulate_buffer()

    def handle_sighup(self, signum, frame):
        """Immune Daemon triggered a vein collapse. Gracefully shift algorithms."""
        log.warning("SIGHUP received from Immune Daemon. Toxin detected.")
        self.reload_config()

    def ingest_shard(self, shard_data: bytes):
        """Ingest a new SSS shard to route."""
        log.debug(f"Ingesting shard of size {len(shard_data)} bytes")
        self.buffer.append(shard_data)
        
    def re_encapsulate_buffer(self):
        """Re-wraps all held shards in the new algorithm without exposing plaintext to network."""
        if not self.buffer:
            return
            
        log.info(f"Re-encapsulating {len(self.buffer)} in-flight shards using {self.active_kem}")
        # In a real implementation:
        # 1. Strip the old KEM envelope (using old private key if applicable)
        # 2. Re-wrap with self.active_kem
        # We simulate the compute time here:
        time.sleep(0.01 * len(self.buffer))
        log.info("Re-encapsulation complete. Shards ready for healthy vein.")
        
    def simulate_remote_node_key(self):
        """Simulate a remote node generating a ML-KEM-768 keypair and sharing its public key."""
        if OQS_AVAILABLE:
            with oqs.KeyEncapsulation(self.active_kem) as kem:
                public_key = kem.generate_keypair()
                return public_key
        return b"MOCK_PUBLIC_KEY"

    def hybrid_encapsulate(self, shard_data: bytes, remote_pub_key: bytes) -> dict:
        """
        Executes the Hybrid Encapsulation Workflow:
        1. Encapsulation (Local) using KEM and remote public key.
        2. Symmetric Encryption of the SSS shard using AES-256-GCM.
        3. Bundle creation.
        """
        if OQS_AVAILABLE and AESGCM:
            with oqs.KeyEncapsulation(self.active_kem) as kem:
                # 2. Encapsulation (Local)
                kem_ciphertext, shared_secret = kem.encap_secret(remote_pub_key)
                
                # 3. Symmetric Encryption (AES-256-GCM uses the 32-byte shared secret)
                aesgcm = AESGCM(shared_secret[:32])
                nonce = os.urandom(12)
                aes_ciphertext = aesgcm.encrypt(nonce, shard_data, None)
                
                # 4. Transmission Bundle
                return {
                    "kem_ciphertext": kem_ciphertext,
                    "aes_nonce": nonce,
                    "aes_ciphertext": aes_ciphertext
                }
        else:
            # Fallback mock for local testing without C-bindings
            return {
                "kem_ciphertext": b"MOCK_KEM_CT",
                "aes_nonce": b"MOCK_NONCE",
                "aes_ciphertext": b"MOCK_AES_CT_" + shard_data
            }

    def route_shards(self):
        """Route the encapsulated shards to their destination using hybrid encryption."""
        if not self.buffer:
            return
            
        log.debug(f"Routing {len(self.buffer)} shards via {self.active_kem} hybrid tunnel...")
        
        # 1. Key Generation (Remote - simulated)
        remote_pub_key = self.simulate_remote_node_key()
        
        for shard in self.buffer:
            bundle = self.hybrid_encapsulate(shard, remote_pub_key)
            log.info(f"Transmitting Bundle -> KEM CT: {len(bundle['kem_ciphertext'])}B | AES CT: {len(bundle['aes_ciphertext'])}B")
            
        # Simulate network routing delay
        time.sleep(0.05)
        self.buffer.clear()
        
    def run(self):
        log.info(f"SSS Relay Online. Active KEM: {self.active_kem}, Active SIG: {self.active_sig}")
        
        # Attach the SIGHUP handler for autonomic response
        signal.signal(signal.SIGHUP, self.handle_sighup)
        
        if OQS_AVAILABLE:
            log.info("liboqs bindings detected. Cryptographic primitives armed.")
        else:
            log.warning("liboqs not available in this environment. Simulating crypto ops.")

        # Main relay loop
        shard_counter = 0
        while True:
            # Simulate receiving shards
            shard_counter += 1
            synthetic_shard = f"SSS_SHARD_{shard_counter}_DATA".encode('utf-8')
            self.ingest_shard(synthetic_shard)
            
            # Route them
            self.route_shards()
            
            # Sleep to prevent burning CPU in the demo loop
            time.sleep(1.0)

if __name__ == "__main__":
    relay = SSSRelay()
    relay.run()
