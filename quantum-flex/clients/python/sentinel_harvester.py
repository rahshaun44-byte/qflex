#!/usr/bin/env python3
import socket
import ssl
import os
import subprocess
import sys
import time
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

HOST = "127.0.0.1"
PORT = 9443
CLIENT_CERT = os.environ.get("QF_CLIENT_CERT", "/etc/quantum-flex/endpoint.crt")
CLIENT_KEY = os.environ.get("QF_CLIENT_KEY", "/etc/quantum-flex/endpoint.key")
CA_CERT = os.environ.get("QF_CA_CERT", "/etc/quantum-flex/root-ca.crt")
SERVER_NAME = os.environ.get("QF_SERVER_NAME", "endpoint.local")

def build_mtls_context():
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=CA_CERT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = True
    context.load_cert_chain(certfile=CLIENT_CERT, keyfile=CLIENT_KEY)
    return context

def wait_for_engine(host=HOST, port=PORT, retries=30):
    """Polls the engine with a real mTLS handshake, not a plaintext probe."""
    print(f"[*] Awaiting Quantum Flex Engine on {host}:{port}...")
    context = build_mtls_context()
    for i in range(retries):
        try:
            with socket.create_connection((host, port), timeout=1) as sock:
                with context.wrap_socket(sock, server_hostname=SERVER_NAME):
                    pass
                print("[+] Engine socket is live. Proceeding with TLS initialization...")
                return True
        except (socket.timeout, ConnectionRefusedError, OSError, ssl.SSLError):
            time.sleep(2)
    print("[!] FATAL: Engine failed to bind within timeout window.")
    sys.exit(1)

def send_to_engine(payload_str):
    """Helper to establish strict mTLS connection and send payload to C++ Engine."""
    context = build_mtls_context()

    try:
        with socket.create_connection((HOST, PORT)) as sock:
            with context.wrap_socket(sock, server_hostname=SERVER_NAME) as ssock:
                ssock.sendall(payload_str.encode('utf-8'))
                # Execute graceful cryptographic teardown to prevent OpenSSL EOF errors
                try:
                    ssock.unwrap()
                except ssl.SSLError:
                    pass
    except Exception as e:
        print(f"[!] Failed to send payload: {e}")

def main():
    print("[*] Sentinel Harvester Online.")

    # Generate ephemeral key for the session
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    print(f"[*] Harvester Public Key: {pub_bytes.hex()}")

    # [!] PAUSE AND INSPECT: Block until C++ Engine is ready
    wait_for_engine()
    
    print(f"[*] Tailing SSH telemetry and piping over strict mTLS to {HOST}:{PORT}...")
    
    process = subprocess.Popen(
        ["journalctl", "-u", "sshd", "-f", "-n", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    for line in iter(process.stdout.readline, ''):
        if "Failed password" in line or "Disconnecting" in line:
            print(f"[*] Intercepted Event: {line.strip()}")
            payload = f"TELEMETRY|{time.time()}|SSH_FAILURE|{line.strip()}|SIGNATURE_PLACEHOLDER\n"
            send_to_engine(payload)
            print(f"[+] Committed to Engine: {time.time()}")

if __name__ == "__main__":
    main()
