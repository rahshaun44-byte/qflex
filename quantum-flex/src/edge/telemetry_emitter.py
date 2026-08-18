import socket
import ssl
import sys
import time

class TelemetryEmitter:
    def __init__(self, host, port, cert_file, key_file, ca_file):
        self.host = host
        self.port = port
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        self.context = self._build_mtls_context()

    def _build_mtls_context(self):
        print("[*] Initializing mTLS Context (TLS 1.3)...")
        # Enforce strict TLS 1.3 for post-quantum safety and maximum performance
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=self.ca_file)
        context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        
        context.check_hostname = True
        return context

    def emit(self, payload):
        try:
            print(f"[*] Dialing Core Substrate at {self.host}:{self.port}...")
            with socket.create_connection((self.host, self.port), timeout=10) as sock:
                with self.context.wrap_socket(sock, server_hostname="endpoint.local") as ssock:
                    print(f"[+] mTLS Handshake Success. Cipher: {ssock.cipher()}")
                    
                    # Transmit the payload
                    ssock.sendall(payload.encode('utf-8'))
                    
                    # Wait for acknowledgement
                    response = ssock.recv(1024)
                    print(f"[+] Core Acknowledgment: {response.decode('utf-8').strip()}")
                    return True
        except ssl.SSLError as e:
            print(f"[!] FATAL: Cryptographic handshake rejected by Core Substrate: {e}")
        except ConnectionRefusedError:
            print(f"[!] FATAL: Core Substrate unreachable at {self.host}:{self.port}")
        except Exception as e:
            print(f"[!] FATAL: Telemetry emission failed: {e}")
        return False
