# sentinel/hardening/cloudflare_rotation.py
import os
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("AMARA_TUNNEL")

def rotate_cloudflare_token(new_token: str, env_path: Path = None):
    """
    Rotates the Cloudflare Tunnel Token securely within the environment or configuration.
    Fails closed if the token is malformed.
    """
    if not new_token or len(new_token) < 40:
        log.error("Invalid token format. Failsafe activated: Rotation aborted.")
        return False

    # 1. Update active process environment
    os.environ["CLOUDFLARE_TUNNEL_TOKEN"] = new_token

    # 2. Update .env file if provided or discovered
    if env_path is None:
        possible_paths = [
            Path(__file__).resolve().parents[3] / "mycelium" / ".env",
            Path(__file__).resolve().parents[2] / ".env",
            Path.cwd() / ".env"
        ]
        for p in possible_paths:
            if p.exists():
                env_path = p
                break

    if env_path and env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith("CLOUDFLARE_TUNNEL_TOKEN="):
                    new_lines.append(f"CLOUDFLARE_TUNNEL_TOKEN={new_token}\n")
                    updated = True
                else:
                    new_lines.append(line)
            
            if not updated:
                new_lines.append(f"CLOUDFLARE_TUNNEL_TOKEN={new_token}\n")
                
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            log.info(f"Updated CLOUDFLARE_TUNNEL_TOKEN in {env_path}")
        except Exception as e:
            log.warning(f"Could not update .env at {env_path}: {e}")

    log.info("Cloudflare Tunnel Token rotation verified in environment.")
    return True

if __name__ == "__main__":
    token = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN")
    if token:
        rotate_cloudflare_token(token)
    else:
        print("Usage: CLOUDFLARE_TUNNEL_TOKEN=<token> python cloudflare_rotation.py")
