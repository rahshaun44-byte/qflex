import sys
import os
import subprocess
import shutil

def deploy_to_chamber(target_file_path):
    print("\n[>>] QUANTUM FLEX: Initializing Sentinel Orchestrator...")
    
    # Define absolute boundaries — correct path for this host
    host_airlock = os.path.expanduser("~/mycelium/sentinel")
    container_airlock = "/opt/sentinel"
    engine_image = "localhost/qflex/sentinel:v1"
    
    # 1. Verify Host Payload
    if not os.path.exists(target_file_path):
        print(f"[-] FATAL: Target payload '{target_file_path}' does not exist on host.")
        sys.exit(1)
        
    base_name = os.path.basename(target_file_path)
    staged_payload_path = os.path.join(host_airlock, base_name)
    container_payload_path = f"{container_airlock}/{base_name}"
    
    # 2. Stage the Payload (Copy to Airlock)
    try:
        shutil.copy2(target_file_path, staged_payload_path)
        print(f"[+] Payload securely copied to airlock: {staged_payload_path}")
    except Exception as e:
        print(f"[-] FATAL: Failed to stage payload: {e}")
        sys.exit(1)
        
    # 3. Construct the Anti-Gravity Execution String
    podman_cmd = [
        "podman", "run", "--rm", 
        "--network=none", 
        "--user", "0",
        "--security-opt", "no-new-privileges=true",
        "--cap-drop=ALL",
        "--read-only",
        "-v", f"{host_airlock}:{container_airlock}:Z",
        engine_image,
        container_payload_path
    ]
    
    print(f"[>>] Detonating Chamber: {' '.join(podman_cmd)}")
    
    # 4. Detonate and Extract Output
    try:
        result = subprocess.run(podman_cmd, capture_output=True, text=True, check=True)
        print("\n=== SENSOR TELEMETRY ===")
        print(result.stdout.strip())
        print("========================")
    except subprocess.CalledProcessError as e:
        print("\n[-] FATAL: Engine Execution Failed.")
        print(f"Error Output: {e.stderr.strip()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_sentinel.py </path/to/suspicious/file>")
        sys.exit(1)
        
    deploy_to_chamber(sys.argv[1])
