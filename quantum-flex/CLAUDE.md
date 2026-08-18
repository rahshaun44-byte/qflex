# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Quantum Flex is a personal, self-hosted "SOC-in-a-box": a C++ evidence/ledger engine plus small
sentinel/harvester agents that stream host telemetry (currently sshd auth events) to it over mTLS.
The roadmap (`core-engine/README.md`, `ai-agents/README.md`, `telemetry/README.md`) is phased —
v1: device discovery, vuln scanning, log collection, dashboard; v2: AI analysis, auto-remediation,
threat intel; v3: multi-node, edge computing. The project is currently in the v1 engine/telemetry
stage (see git history: "Milestone 1 Complete: sd_journal binding and mTLS baseline locked").

## Build & test

The C++ side uses CMake + vcpkg (vendored under `third_party/vcpkg`) with presets:

```bash
cmake --preset debug && cmake --build --preset debug     # or --preset release
ctest --preset debug --output-on-failure                 # all tests
ctest --preset debug --output-on-failure -R <TestSuite.TestName>   # single test
```

`scripts/verify.sh` runs exactly that debug configure+build+ctest sequence.

`./verify-all.sh` is a separate, heavier "health certificate" gate: it runs
`verify/verify-supply-chain.sh` (toolchain fingerprint) and `verify/verify-backups.sh` (Btrfs
snapshot rollback test), then wipes `build/` and does a clean `CC=clang CXX=clang++` configure+build
(no presets, no vcpkg toolchain file) as the static-analysis (clang-tidy) gate. Run this before
declaring a change "verified" in the sense this repo uses that word.

**Known build-graph gap:** `CMakeLists.txt` currently only declares one target, `sentinel_push`
(the root `sentinel_push.cpp`, linked against `libsystemd` + OpenSSL). The engine sources under
`src/core/`, `src/crypto/`, `src/main.cpp`, and the GoogleTest suites in `tests/` are not yet wired
into CMake — `cmake --build` will not produce the engine binary and `ctest` will not discover the
test suites until `add_executable`/`add_subdirectory` entries are added for them. Don't assume
`ctest` covers `tests/*.cpp` until that's fixed.

Linting/formatting contracts: `.clang-tidy` and `.clang-format`. Existing code uses targeted
`// NOLINTNEXTLINE(check-name)` suppressions (e.g. `bugprone-easily-swappable-parameters`,
`cppcoreguidelines-avoid-c-arrays`) rather than disabling checks repo-wide — follow that pattern
for new code that legitimately trips a check.

Python components (`clients/python/`, `src/edge/`) have no build step; install deps ad hoc.
`build_sentinel.sh` compiles `src/edge/hardware_binder.py` into a standalone native binary
(`qf_sentinel.bin`) via Nuitka, for deploying the sentinel to hosts without a Python runtime.

`Dockerfile.pqc` builds a Fedora 40 image with `liboqs` + `oqs-provider` (the OpenSSL post-quantum
provider) — required at runtime for the hybrid Ed25519+PQC signing path. The project standardizes
on rootless Podman over Docker for anything containerized (`setup_scripts/hardening-checklist.md`).

## Architecture

**Core engine** (`src/core/`, `include/quantum_flex/`) — `LocalNode` (`local_node.hpp`) is the
central object and owns:
- `EvidenceEngine`: a hash-chained, tamper-evident map of `evidence_id -> data`. Registration is
  write-once (re-registering an id throws); `verify_evidence`/`verify_file_evidence` re-hash and
  compare. `get_state_root()` collapses the whole ledger into one SHA-256 for equilibrium proofs.
- `HybridSigner` (`crypto_signer.hpp`): Ed25519 + PQC (liboqs/OQS provider) signer loaded from PEM
  key paths — see `Dockerfile.pqc` for the OpenSSL provider config this depends on.
- `StateManager`: SQLite-backed (default `brie_state.db`) partition state machine with an optional
  Postgres LISTEN/NOTIFY listener thread.
- `ReplicationLayer` + `GossipSubHandler`: a gossip-replicated hash-chain of `MycelialBlock`s
  across peer nodes, with a decaying peer-scoring system (reward/penalize/prune) gating what gets
  forwarded to whom.
- `LedgerManager`: periodic snapshot/compaction of `data/ledger.dat`.
- `ForensicLockdown`: OS-level incident-response actions (disable network, remount readonly, stop
  containers, flush TPM) run through an injectable `ICommandExecutor` so it's dry-runnable in tests.

`LocalNode` tracks a `SystemState` (`UNINITIALIZED → LOCKED → ACTIVE`, plus `SUSPECT` /
`QUARANTINED` / `LOCKDOWN_PENDING` / `LOCKDOWN_ACTIVE`). Unlocking requires a Shamir threshold of
key shards (`crypto_shamir.hpp`: GF(256) arithmetic, Lagrange interpolation) via
`unlock_node`/`initialize_node`; `quarantine_node(reason)` moves it to `QUARANTINED` when integrity
checks fail (invalid proof, TPM failure, ledger corruption, etc).

**Telemetry ingestion**: `LocalNode::append_evidence(telemetry_id, raw_payload, signature)` hashes
the payload into a `ZkCommitment` (id + salt + commitment hash) and registers *that* into the
ledger — the raw payload itself is never persisted.

**Networking**: `IpcServer` (`ipc_server.hpp`) is a single-threaded mTLS TCP server (OpenSSL,
default `127.0.0.1:9443`). `src/main.cpp`'s loop drives it one connection at a time via
`process_single_connection()` deliberately, to keep behavior deterministic for tests.

**Sentinel/harvester producers** all speak the same pipe-delimited wire protocol into that socket
(e.g. `TELEMETRY|<ts>|SSH_FAILURE|<line>|<signature>`, or the control message
`SYSTEM|SSS_UNLOCK|THRESHOLD_MET|...` — see `clients/python/synthetic_unseal.py` for a manual
trigger of the Shamir-unlock path):
- `sentinel_push.cpp` (root) and `src/sentinel_journal.cpp` — C++, read `sshd.service` from the
  systemd journal via `sd_journal_*`.
- `clients/python/sentinel_harvester.py` — Python equivalent, tails `journalctl -u sshd -f`.

**BrieNode / Akashic attestation subsystem** (`include/quantum_flex/brie_node.hpp`,
`src/core/brie_node.cpp`, with `clients/python/brie_medium.py` as a parallel Python
reference/mock): a separate, Postgres-backed pipeline where `neurogenesis_purge(partition)`
extracts and hashes a DB partition, wipes it, and produces a signed `AuditProof`/
`AttestationContext` (`include/quantum_flex/{attestation_context,audit_proof}.hpp`) while driving
`partition_id` through the `BrieState` machine: `SHRED_VERIFIED → SIGNING → SIGNED_LOCAL →
LEDGER_PENDING → LEDGER_COMMITTED → COMPLETE` (with `SIGNING_INTERRUPTED`/`REQUIRES_OPERATOR`
failure states), persisted with a hash-chained journal table in SQLite for crash recovery
(`sweep_boot_recovery` / `recover_state`). The C++ and Python implementations of this state
machine and wire format must be kept in sync when either changes.

`edge_node.py` and the `edge-node`/`amara-matrix` services in `compose.yaml` are an unrelated
FastAPI+Postgres logistics-ingest prototype (shipment lat/lon/temperature) — not part of the
sentinel/engine telemetry path. Don't conflate its Postgres schema with `StateManager`'s.

**PKI**: three independently-generated certificate sets exist — `keys/`, `qflex_pki/`, and
`data/mtls/`. Check which one a given binary/script actually references (env vars like
`QF_SERVER_CERT`/`QF_CA_CERT`, or hardcoded paths in the C++ sentinels) rather than assuming
they're interchangeable. `setup_scripts/generate-mtls-pki.sh` generates this material.

**Deployment**: engine and sentinel run as separate systemd services under a dedicated
`quantum-flex` system user, installed outside `/home` with SELinux `bin_t`/`etc_t` labeling and a
locked-down systemd sandbox (`ProtectSystem=strict`, `RestrictAddressFamilies=`, etc.) — see
`setup_scripts/install-*-service.sh`, `setup_scripts/quantum-flex-engine.service`,
`sentinel-harvester.service.tmp`, and `setup_scripts/hardening-checklist.md`.

## Repo-state gotchas

- **Private key material is committed to git**, and `origin` is a real GitHub remote
  (`rocks232/Qauntumflex-core-node`): CA root keys, Ed25519/PQC signing keys, and mTLS keys under
  `data/`, `keys/`, and `qflex_pki/` are all tracked. Don't add more secrets to a commit assuming
  `.gitignore` covers them — it only excludes `.env`, not `*.key`/`*.pem`.
- Several `docs/*.md` files are empty stubs (`build.md`, `testing.md`, `coding-standards.md`,
  `decision-log.md`) or are point-in-time ops logs rather than living docs
  (`docs/ai-ide-handoff.md`, `docs/KDE_CONNECT_PROTOCOL.md`, `docs/substrate-report.md` all
  describe the host machine, not the codebase). `HOUSING_DIRECTIVE.md` at the repo root is an
  unrelated personal-automation directive.
- Several top-level files are untracked work-in-progress duplicates of the organized sources
  (`src/core.cpp`, `src/sentinel.cpp`, `src/sentinel_push.cpp`, `src/sentinel_sshd_tail.cpp`,
  `sentinel/`, `test.cpp`, `telemetry.db`, `build_error.log`) — check `git status`/`git ls-files`
  before treating them as canonical. The tracked sources live in `src/core/`, `src/crypto/`,
  `src/edge/`, and `tests/`.
