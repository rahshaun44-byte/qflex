#!/usr/bin/env python3
import socket
import ssl
import sys
import os

HOST = "127.0.0.1"
PORT = 9443
# The synthetic unlock command format expected by the C++ state machine
PAYLOAD = "SYSTEM|SSS_UNLOCK|THRESHOLD_MET|LOCAL_STAGING_OVERRIDE\n"

def fire_payload():
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=os.environ.get("QF_CA_CERT", "/home/rahshaunchambers/quantum-flex/qflex_pki/qflex_root.crt"),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = True
    
    context.load_cert_chain(
        certfile="/home/rahshaunchambers/quantum-flex/qflex_pki/endpoint.crt",
        keyfile="/home/rahshaunchambers/quantum-flex/qflex_pki/endpoint.key"
    )
    
    print(f"[*] Firing synthetic SSS threshold payload to {HOST}:{PORT}...")
    try:
        with socket.create_connection((HOST, PORT)) as sock:
            with context.wrap_socket(sock, server_hostname="endpoint.local") as ssock:
                ssock.sendall(PAYLOAD.encode('utf-8'))
                try:
                    ssock.unwrap()
                except ssl.SSLError:
                    pass
        print("[+] Payload delivered. Engine should now be unsealed.")
    except Exception as e:
        print(f"[!] Target unreachable: {e}")

if __name__ == "__main__":
    fire_payload()
