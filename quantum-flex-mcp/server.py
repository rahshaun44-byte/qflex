#!/usr/bin/env python3
"""
Quantum Flex MCP Server
========================
Exposes the running Quantum Flex node stack (logistics-pg, edge-node, ATHENA,
AMARA dashboard, API gateway, sentinel/tripwire) as MCP tools, reachable over
the Tailscale mesh so any MCP client on this PC or on the phone can query and
lightly control the stack.

Explicit authority boundary for container control (see container_status /
container_action below):
    ALLOWED    — inspect, status, logs, pause, unpause (compose-managed
                 containers only: logistics-pg, edge-node)
    NOT ALLOWED — arbitrary exec, arbitrary mount, privileged mode, host
                 filesystem access, running an arbitrary image. None of that
                 is wired up anywhere in this file; podman is only ever
                 invoked with the fixed verbs below, never with user-supplied
                 flags or images.

Postgres is loopback-only (127.0.0.1) on the host, not published on the
tailnet — this MCP server is the only path to it from PC/phone, by design
(phone/PC -> MCP -> Postgres, never phone -> Postgres directly).

ATHENA stays reached over loopback (127.0.0.1) even from here, per its own
"never expose externally" boundary — this server proxies to it, it does not
rebind it.

Nothing here is hardcoded to a Tailscale IP: the bind address is resolved
fresh via `tailscale ip -4` at every startup, and cross-service references
use the stable MagicDNS hostname, so a re-registered/changed tailnet address
never requires a code edit.
"""

import asyncio
import os
import re
import subprocess

import asyncpg
import httpx
from mcp.server import MCPServer

TAILNET_HOST = "yoga.tail2b296e.ts.net"  # stable MagicDNS name, not an IP
MCP_PORT = 9000


def _resolve_bind_ip() -> str:
    return subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=5).strip()


LOGISTICS_DB = {
    "host": "127.0.0.1",
    "port": 5433,
    "user": "amara_admin",
    "database": "amara_matrix",
}
LOGISTICS_DB_PASSWORD = None  # loaded lazily from ~/quantum-flex/.env

ATHENA_URL = "http://127.0.0.1:8001"
DASHBOARD_URL = f"http://{TAILNET_HOST}:8000"
API_NODE_URL = f"http://{TAILNET_HOST}:8002"

KNOWN_CONTAINERS = {"logistics-pg", "edge-node"}
ALLOWED_CONTAINER_ACTIONS = {"pause", "unpause"}

SYSTEMD_UNITS = [
    "tripwire.service",
    "sentinel-drive.timer",
    "qf-monitor.service",
    "athena-node.service",
    "amara-dashboard.service",
    "api-node.service",
]

server = MCPServer(
    name="quantum-flex",
    title="Quantum Flex Node Control",
    description="Query and lightly control the Quantum Flex SOC-in-a-box node stack.",
)


def _load_db_password() -> str:
    global LOGISTICS_DB_PASSWORD
    if LOGISTICS_DB_PASSWORD is None:
        env_path = os.path.expanduser("~/quantum-flex/.env")
        with open(env_path) as f:
            for line in f:
                if line.startswith("POSTGRES_PASSWORD="):
                    LOGISTICS_DB_PASSWORD = line.strip().split("=", 1)[1]
                    break
    return LOGISTICS_DB_PASSWORD


@server.tool()
def list_services() -> dict:
    """List status of all Quantum Flex systemd units and Podman containers."""
    services = {}
    for unit in SYSTEMD_UNITS:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True,
        )
        services[unit] = result.stdout.strip() or result.stderr.strip()

    containers = {}
    result = subprocess.run(
        ["podman", "ps", "-a", "--format", "{{.Names}}|{{.Status}}"],
        capture_output=True, text=True,
    )
    for line in result.stdout.strip().splitlines():
        if "|" not in line:
            continue
        name, status = line.split("|", 1)
        if name in KNOWN_CONTAINERS:
            containers[name] = status

    return {"systemd": services, "podman": containers}


@server.tool()
async def query_logistics_db(sql: str) -> list[dict]:
    """Run a read-only SELECT query against the logistics-pg database
    (shipment_id, timestamp, lat, lon, status, temperature_c in edge_ingest_queue).
    Only SELECT statements are permitted."""
    stripped = sql.strip().rstrip(";")
    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError("Only SELECT statements are permitted through this tool.")
    if ";" in stripped:
        raise ValueError("Multiple statements are not permitted.")

    conn = await asyncpg.connect(
        host=LOGISTICS_DB["host"],
        port=LOGISTICS_DB["port"],
        user=LOGISTICS_DB["user"],
        password=_load_db_password(),
        database=LOGISTICS_DB["database"],
    )
    try:
        rows = await conn.fetch(stripped)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@server.tool()
async def ask_athena(question: str) -> str:
    """Ask ATHENA (the RAG cognitive node) a question. Proxied over loopback —
    ATHENA itself is never exposed off-host, per its own code's safety boundary."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{ATHENA_URL}/query", json={"question": question})
        r.raise_for_status()
        return r.text


@server.tool()
async def dashboard_snapshot() -> str:
    """Fetch the AMARA Sync Dashboard's current status page."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{DASHBOARD_URL}/")
        r.raise_for_status()
        return r.text


@server.tool()
def container_status(container: str) -> dict:
    """Read-only: inspect state/health and the last 30 log lines for one of
    the compose-managed containers (logistics-pg, edge-node). Never mutates
    anything."""
    if container not in KNOWN_CONTAINERS:
        raise ValueError(f"container must be one of {sorted(KNOWN_CONTAINERS)}")

    inspect = subprocess.run(
        ["podman", "inspect", container,
         "--format", "{{.State.Status}} paused={{.State.Paused}} health={{.State.Health.Status}}"],
        capture_output=True, text=True,
    )
    logs = subprocess.run(
        ["podman", "logs", "--tail", "30", container],
        capture_output=True, text=True,
    )
    return {
        "container": container,
        "state": inspect.stdout.strip() or inspect.stderr.strip(),
        "recent_logs": logs.stdout[-4000:],
    }


@server.tool()
def container_action(container: str, action: str) -> str:
    """Pause or unpause one of the compose-managed containers. This is the
    entire authority this tool grants — nothing else.
    container must be one of: logistics-pg, edge-node.
    action must be one of: pause, unpause.
    Explicitly NOT possible through this tool: exec into a container,
    mounting arbitrary paths, privileged mode, host filesystem access, or
    running an arbitrary image — none of that code path exists here."""
    if container not in KNOWN_CONTAINERS:
        raise ValueError(f"container must be one of {sorted(KNOWN_CONTAINERS)}")
    if action not in ALLOWED_CONTAINER_ACTIONS:
        raise ValueError(f"action must be one of {sorted(ALLOWED_CONTAINER_ACTIONS)}")

    result = subprocess.run(
        ["podman", action, container],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return f"{container}: {action} OK"


if __name__ == "__main__":
    asyncio.run(
        server.run_streamable_http_async(host=_resolve_bind_ip(), port=MCP_PORT)
    )
