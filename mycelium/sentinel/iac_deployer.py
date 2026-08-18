#!/usr/bin/env python3
"""
Quantum Flex IaC Vibe Coder
=============================
Hydrates the Gold Standard template and uses rootless podman-compose
to spin up zero-trust services locally on demand.
"""

import os
import sys
import subprocess
from string import Template

BASE_DIR = "/home/rahshaunchambers/mycelium"
TEMPLATE_PATH = os.path.join(BASE_DIR, "sentinel/templates/gold_standard.yml")
DEPLOY_DIR = os.path.join(BASE_DIR, "sentinel/deployments")

def deploy_service(service_name, image, host_port, container_port):
    print(f"[*] Deploying {service_name} with Vibe Coder...")
    
    os.makedirs(DEPLOY_DIR, exist_ok=True)
    
    with open(TEMPLATE_PATH, "r") as f:
        template = Template(f.read())
        
    hydrated = template.safe_substitute(
        SERVICE_NAME=service_name,
        IMAGE_NAME=image.split(':')[0],
        IMAGE_TAG=image.split(':')[1] if ':' in image else "latest",
        HOST_PORT=host_port,
        CONTAINER_PORT=container_port
    )
    
    compose_path = os.path.join(DEPLOY_DIR, f"{service_name}_compose.yml")
    with open(compose_path, "w") as f:
        f.write(hydrated)
        
    print(f"[+] Hydrated template written to {compose_path}")
    print("[*] Spinning up container via podman-compose...")
    
    try:
        subprocess.run(
            ["podman-compose", "-f", compose_path, "up", "-d"],
            check=True
        )
        print(f"[SUCCESS] {service_name} deployed successfully on port {host_port}")
    except subprocess.CalledProcessError as e:
        print(f"[FAILED] Deployment failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: iac_deployer.py <service_name> <image:tag> <host_port> <container_port>")
        sys.exit(1)
        
    deploy_service(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
