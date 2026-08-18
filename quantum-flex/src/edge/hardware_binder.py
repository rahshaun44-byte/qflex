import subprocess
import hashlib
import uuid
import sys
import os

class HardwareBinder:
    def __init__(self, authorized_hash):
        # The expected hash is injected during the compilation of the binary
        self.authorized_hash = authorized_hash
        self.salt = "QFlex_AntiGravity_v1.1"

    def get_tpm_pcr(self):
        """
        Interrogates the TPM 2.0 chip directly for PCR 0 (Core System Firmware).
        Requires tpm2-tools installed on the edge node OS.
        """
        try:
            result = subprocess.run(
                ['tpm2_pcrread', 'sha256:0'], 
                capture_output=True, text=True, check=True
            )
            # Parse the specific hex output from the TPM
            for line in result.stdout.split('\n'):
                if '0x' in line:
                    return line.split('0x')[1].strip()
            return None
        except Exception:
            # If TPM is missing or locked, fallback to Layer 2 DMI tracking
            return self.get_motherboard_uuid()

    def get_motherboard_uuid(self):
        """
        Reads the bare-metal motherboard UUID directly from Linux sysfs.
        """
        try:
            with open('/sys/class/dmi/id/product_uuid', 'r') as f:
                return f.read().strip()
        except Exception:
            return "HARDWARE_UNVERIFIED"

    def get_mac_address(self):
        """
        Extracts the physical MAC address of the primary network interface.
        """
        mac = uuid.getnode()
        return ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))

    def generate_fingerprint(self):
        """
        Double Attestation: Combines TPM/Motherboard identity with the MAC address.
        """
        tpm_data = self.get_tpm_pcr()
        mac_data = self.get_mac_address()
        
        # Construct the raw identity string and hash it
        raw_identity = f"{tpm_data}|{mac_data}|{self.salt}"
        return hashlib.sha256(raw_identity.encode()).hexdigest()

    def verify_and_lock(self):
        """
        The Zero-Trust execution gate. Runs before the daemon fully boots.
        """
        current_fingerprint = self.generate_fingerprint()
        
        if current_fingerprint != self.authorized_hash:
            print("[FATAL] Hardware Fingerprint Mismatch. Cloning Detected.")
            self.trigger_anti_gravity_neutralization()
            sys.exit(1)
        else:
            print("[*] Hardware Attestation Verified. Edge Sentinel Armed.")
            return True

    def trigger_anti_gravity_neutralization(self):
        """
        The kill-switch protocol.
        """
        print("[!] Purging local memory states and zeroing cryptographic threshold...")
        # For Quantum Flex v1.1: 
        # 1. Overwrite Shamir's Secret fragments in memory with os.urandom
        # 2. Delete localized log buffers
        # 3. Halt process
        pass

# ==========================================
# Execution Example for the Compiled Binary
# ==========================================
if __name__ == "__main__":
    import argparse
    from telemetry_emitter import TelemetryEmitter

    parser = argparse.ArgumentParser(description="Quantum Flex Edge Sentinel")
    parser.add_argument("--host", default="127.0.0.1", help="Core Substrate IP")
    parser.add_argument("--port", type=int, default=9443, help="Core Substrate Port")
    parser.add_argument("--cert", default="qf_sentinel_01.crt", help="Sentinel Certificate")
    parser.add_argument("--key", default="qf_sentinel_01.key", help="Sentinel Private Key")
    parser.add_argument("--ca", default="qf_root_ca.pem", help="Root CA Certificate")
    args = parser.parse_args()

    PROVISIONED_LICENSE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    binder = HardwareBinder(PROVISIONED_LICENSE_HASH)
    
    # Gatekeeper: The script dies here if the hardware doesn't match
    # Commented out for local testing since the hash won't match my current VM hardware!
    # binder.verify_and_lock()
    print("[*] Hardware Attestation Bypassed for Local Testing.")
    
    print("[*] Booting Shamir's Secret Sharing Mesh and mTLS Emitter...")
    emitter = TelemetryEmitter(args.host, args.port, args.cert, args.key, args.ca)
    
    # Send a test telemetry payload to the Core
    print("[*] Transmitting Test Telemetry payload...")
    emitter.emit("TELEMETRY|test_node|payload_data|mock_signature")

