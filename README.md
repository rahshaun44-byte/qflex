# qflex

Consolidated snapshot of the Quantum Flex project tree, pushed as a fresh
history (no imported git log from the source repos) on 2026-08-07.

## Layout

- `qflex-clean/` — core node, sentinel, ADR docs, sentinel-bridge
- `quantum-flex/` — C++ evidence/ledger engine, sentinel/harvester clients
- `mycelium/` — AMARA/ATHENA/API-node services, MCP layer, sentinel daemons
- `quantum-flex-mcp/` — MCP server exposing the node stack as tools
- `sentinel-root-harness/` — isolated ROOT/Podman packet-metrics test harness

## Deliberately excluded from this snapshot

- All `.env` files and anything matching `*.key` (except CA public certs under
  `mtls/`) — credentials and private key material never left the source
  machine.
- `quantum-flex/data/`, `keys/`, `qflex_pki/`, `deploy_payload/` — PKI
  material directories, excluded wholesale rather than filtered file-by-file.
- `mycelium/.tripwire/` — a 14GB+ runtime append-only log, not source.
- `venv/`, `node_modules/`, `third_party/`, `build/`, `__pycache__/` —
  reproducible from `requirements.txt` / `package.json` / `vcpkg`, not
  committed.
- `.idea/`, `.vscode/`, `.claude/` — local editor/tool config.

Every file in this snapshot was scanned for private-key headers and
hardcoded credential patterns before commit; none were found.
