import os
import hashlib
import shutil
import stat
import sys

def neutralize_payload(file_path):
    """
    Physical intervention: Strips execution rights, extracts the cryptographic hash, 
    and appends the .isolated extension to permanently sever the file from the OS.
    """
    try:
        # 1. Extract Cryptographic Identity (SHA-256)
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        file_hash = sha256_hash.hexdigest()

        # 2. Modify Permissions to Absolute Zero (chmod 000)
        os.chmod(file_path, 0o000)

        # 3. Rename and Isolate
        directory = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        isolated_name = f"{base_name}.isolated"
        isolated_path = os.path.join(directory, isolated_name)
        
        shutil.move(file_path, isolated_path)
        
        return {
            "status": "NEUTRALIZED",
            "original_name": base_name,
            "isolated_name": isolated_name,
            "sha256_hash": file_hash,
            "vault_path": isolated_path
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}

if __name__ == "__main__":
    print("\n[+] QUANTUM FLEX: Sentinel Pipeline Armed")
    
    # Enforce argument check
    if len(sys.argv) < 2:
        print("[-] ERROR: No target payload specified to the engine.")
        print("Usage: podman run <image> <target_file_inside_container>")
        sys.exit(1)
        
    target_payload = sys.argv[1]
    
    if os.path.exists(target_payload):
        result = neutralize_payload(target_payload)
        print(f"[+] NEUTRALIZATION REPORT:\n{result}\n")
    else:
        print(f"[-] ERROR: Target file '{target_payload}' not found in chamber.\n")
