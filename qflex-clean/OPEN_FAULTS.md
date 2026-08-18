╔══════════════════════════════════════════════════════════════════════════════╗
║              QUANTUM FLEX — OPEN FAULTS REGISTRY                             ║
║              STATUS: UNRESOLVED AS OF 2026-04-07                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  FAULT-001: SENTINEL ZK Verification — DUMMY KEY                             ║
║  File    : sentinel/data/verification_key.json                               ║
║  Problem : Prior "REMEDIATED" mark was FALSE — verified 2026-08-05.          ║
║            Phase 1 (pot12_*.ptau) was done, but Phase 2 (the circuit-        ║
║            specific zkey) never got a contribution: vk_delta_2 was the       ║
║            untouched BN254 G2 generator, i.e. delta was never re-randomized. ║
║  Fix     : snarkjs zkey contribute + snarkjs zkey beacon, run 2026-08-05.    ║
║            See sentinel/hardening/CEREMONY.md for the full record and       ║
║            an end-to-end proof/verify test against the new key.             ║
║  Status  : ✅ REMEDIATED (2026-08-05, actually verified this time)           ║
║                                                                              ║
║  FAULT-002: Cloudflare Tunnel Token — EXPIRED                                ║
║  Container: qflex-cf-tunnel                                                  ║
║  Problem : CLOUDFLARE_TUNNEL_TOKEN in .env is invalid/expired.               ║
║  Fix     : Rotate token at dash.cloudflare.com →                             ║
║            Zero Trust → Tunnels → Configure → Delete connector →             ║
║            Add connector → copy new eyJ... token → update .env               ║
║  Status  : ✅ REMEDIATED                                                     ║
║                                                                              ║
║  FAULT-003: SELinux Policy for MCP Mock Server — UNVERIFIED                  ║
║  Problem : SELinux policy for athena_mcp.py inside Podman container          ║
║            has not been generated or verified.                               ║
║  Fix     : sudo ausearch -m avc -ts recent | audit2allow -M athena_mcp       ║
║            sudo semodule -i athena_mcp_policy.pp                             ║
║  Status  : 🟡 NULL — PENDING VERIFICATION                                    ║
║                                                                              ║
║  FAULT-004: ChromaDB → host-gateway Latency — UNBENCHMARKED                  ║
║  Problem : Latency between Podman container and host ChromaDB                ║
║            instance not measured. No threshold defined.                      ║
║  Fix     : Benchmark via podman exec athena-core curl timing test            ║
║            Acceptable: <5ms | Monitor: 5–20ms | Investigate: >20ms           ║
║  Status  : ✅ REMEDIATED (Tested: 0.00039s)                                  ║
║                                                                              ║
║  FAULT-005: Git Repository — NOT PUSHED                                      ║
║  Target  : github.com/rahshaun-chambers/quantum-flex (PRIVATE)               ║
║  Problem : Code not pushed to private repo. Local only = no backup.         ║
║  Fix     : Verify repo exists → git init → git add . →                      ║
║            git commit → git push -u origin main                              ║
║  Status  : 🔴 CRITICAL — DO THIS IMMEDIATELY                                 ║
║                                                                              ║
║  FAULT-006: .env — LIVE-LOOKING SECRETS TRACKED IN GIT                       ║
║  File    : .env (committed in f279cc2, ironically an infra-hardening        ║
║            commit; .gitignore added afterward so it stayed tracked)          ║
║  Problem : N8N_DB_PASSWORD/N8N_AUTH_PASSWORD (identical value) and           ║
║            CLOUDFLARE_TUNNEL_TOKEN in plaintext, in git history, in a        ║
║            file still `git ls-files`-tracked. n8n was confirmed never       ║
║            deployed (SESSION_HANDOFF_2026-08-04, §2) — this is dead config.  ║
║  Fix     : untracked + deleted locally 2026-08-05 (see git log). History    ║
║            still contains it — purge (filter-repo) + force-push is a        ║
║            separate, deliberately-deferred step; ask before doing that.     ║
║  Status  : 🟡 PARTIAL — untracked, history purge pending explicit go-ahead   ║
║                                                                              ║
║  FAULT-007: chromadb 1.5.9 — PYSEC-2026-311 (pre-auth RCE), NO FIX YET       ║
║  Problem : /api/v2/.../collections + trust_remote_code=true allows RCE       ║
║            on chromadb's HTTP server. No patched version exists upstream.    ║
║  Mitigation: all in-repo usage is chromadb.PersistentClient (embedded,       ║
║            no HTTP server, no trust_remote_code anywhere in the codebase).   ║
║            docker-compose.yml's `chroma` service (server mode) is bound to  ║
║            127.0.0.1 only and is not currently running (verified 2026-08-05,║
║            `docker ps` empty). Risk is currently dormant, not exploitable.   ║
║  Status  : 🟡 MONITORED — re-check when a fix version ships; do not expose   ║
║            the chroma container beyond 127.0.0.1 or set trust_remote_code.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
