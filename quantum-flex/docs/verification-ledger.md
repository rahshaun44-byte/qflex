# Truth Ledger: System Verification & Confidence Model

| Subsystem | Target Claim | Current State | Evidence Vector |
| :--- | :--- | :--- | :--- |
| **Platform** | LUKS/Btrfs Encrypted Single-Drive | `Measured` | `sudo lsblk` telemetry |
| **Supply Chain** | Deterministic Compiler Versions | `Proven` | `verify-supply-chain.sh` |
| **Static Analysis** | Clang-Tidy Gate Catches Unsafe Code | `Proven` | `verify-all.sh` negative test |
| **Runtime** | Memory Safe Execution (ASan/UBSan) | `Proven` | `verify-all.sh` + planted bug interception |
| **Recovery** | Btrfs Automated Rollback | `Proven` | `verify/verify-backups.sh` |

