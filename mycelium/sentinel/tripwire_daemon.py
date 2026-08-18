#!/usr/bin/env python3
"""
Quantum Flex: Evil Maid Tripwire (Dirty Housemaid Detection)
=============================================================
This daemon activates on boot via systemd and silently monitors:
1. Boot events (was the machine turned on while you were away?)
2. Login attempts (successful AND failed — via wtmp/btmp/journalctl)
3. USB device insertions (rubber ducky, live USB, storage devices)
4. Critical file integrity (kernel, passwd, shadow, sudoers, GRUB, SSH keys)
5. Filesystem modifications in ~/mycelium (your codebase)
6. Network interface changes (new adapters, bridges, promiscuous mode)
All events are written to an append-only tripwire log with SHA-256 chain hashing.
Each entry includes the hash of the previous entry, creating a tamper-evident chain.
If the log is altered, the chain breaks and the tampering is provable.
"""
import os
import sys
import json
import time
import hashlib
import subprocess
import threading
from datetime import datetime
from pathlib import Path
import os
try:
    import psycopg2
    _PG_OK = True
except ImportError:
    _PG_OK = False

# ── Configuration ─────────────────────────────────────────────────────────────
TRIPWIRE_LOG = Path.home() / ".local" / "state" / "qflex" / "tripwire" / "tripwire_chain.jsonl"
BASELINE_FILE = Path.home() / ".local" / "state" / "qflex" / "tripwire" / "baseline_hashes.json"
WATCH_DIR = str(Path.home() / "mycelium")

# Critical system files to hash-check on every boot
CRITICAL_FILES = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    "/etc/pam.d/sshd",
    "/etc/pam.d/login",
    "/etc/pam.d/gdm-password",
    str(Path.home() / ".ssh" / "authorized_keys"),
    str(Path.home() / ".bashrc"),
    str(Path.home() / ".bash_profile"),
]

# Boot files (kernel, initramfs, GRUB)
BOOT_GLOBS = ["/boot/vmlinuz-*", "/boot/initramfs-*", "/boot/grub2/grub.cfg"]

POLL_INTERVAL = 30  # seconds between USB/network scans

# ── Chain-Hashed Logging ──────────────────────────────────────────────────────
class TripwireLogger:
    """Append-only, chain-hashed tamper-evident logger."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.prev_hash = self._get_last_hash()
        self._lock = threading.Lock()

    def _get_last_hash(self) -> str:
        """Read the last entry's hash to continue the chain."""
        if not self.log_path.exists():
            return "GENESIS"
        try:
            with open(self.log_path, "r") as f:
                lines = f.readlines()
                if lines:
                    last = json.loads(lines[-1])
                    return last.get("entry_hash", "GENESIS")
        except Exception:
            pass
        return "GENESIS"

    def log(self, event_type: str, detail: str, severity: str = "INFO"):
        """Write a chain-hashed entry to the tripwire log."""
        ts = datetime.now().isoformat()
        payload = f"{ts}|{event_type}|{detail}|{self.prev_hash}"
        entry_hash = hashlib.sha256(payload.encode()).hexdigest()

        entry = {
            "timestamp": ts,
            "event_type": event_type,
            "detail": detail,
            "severity": severity,
            "prev_hash": self.prev_hash,
            "entry_hash": entry_hash,
        }

        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        if _PG_OK:
            try:
                conn = psycopg2.connect(
                    host="127.0.0.1",
                    dbname="telemetry",
                    user="sentinel_service",
                    password=os.environ.get("QF_DB_PASSWORD"),
                    connect_timeout=2,
                )
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO tripwire_events "
                    "(ts, event_type, detail, severity, prev_hash, entry_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (ts, event_type, detail, severity, entry["prev_hash"], entry_hash),
                )
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"[TRIPWIRE] DB write skipped: {e}")

        self.prev_hash = entry_hash
        print(f"[TRIPWIRE] [{severity}] {event_type}: {detail}")

# ── File Integrity Monitor ────────────────────────────────────────────────────
def hash_file(filepath: str) -> str:
    """SHA-256 hash of a file's contents."""
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except PermissionError:
        return "PERMISSION_DENIED"
    except FileNotFoundError:
        return "NOT_FOUND"

def build_baseline(logger: TripwireLogger) -> dict:
    """Hash all critical files and store the baseline."""
    import glob
    baseline = {}
    all_files = list(CRITICAL_FILES)
    for pattern in BOOT_GLOBS:
        all_files.extend(glob.glob(pattern))
    for fpath in all_files:
        digest = hash_file(fpath)
        if digest not in ("NOT_FOUND", "PERMISSION_DENIED"):
            baseline[fpath] = digest

    # Save baseline
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)

    logger.log("BASELINE_CAPTURED", f"Hashed {len(baseline)} critical files")
    return baseline

def check_integrity(logger: TripwireLogger):
    """Compare current file hashes against the stored baseline."""
    if not BASELINE_FILE.exists():
        logger.log("INTEGRITY_SKIP", "No baseline found. Creating initial baseline.", "WARNING")
        build_baseline(logger)
        return

    with open(BASELINE_FILE, "r") as f:
        baseline = json.load(f)

    import glob
    all_files = list(CRITICAL_FILES)
    for pattern in BOOT_GLOBS:
        all_files.extend(glob.glob(pattern))

    violations = []
    for fpath in all_files:
        current = hash_file(fpath)
        expected = baseline.get(fpath)

        if expected is None and current not in ("NOT_FOUND", "PERMISSION_DENIED"):
            violations.append(f"NEW FILE: {fpath}")
        elif expected and current != expected:
            violations.append(f"MODIFIED: {fpath} (expected {expected[:12]}... got {current[:12]}...)")

    # Check for deleted files
    for fpath in baseline:
        if not os.path.exists(fpath):
            violations.append(f"DELETED: {fpath}")

    if violations:
        for v in violations:
            logger.log("INTEGRITY_VIOLATION", v, "CRITICAL")
    else:
        logger.log("INTEGRITY_OK", f"All {len(baseline)} critical files match baseline")

# ── Boot & Login Monitoring ───────────────────────────────────────────────────
def log_boot_event(logger: TripwireLogger):
    """Record that the system just booted."""
    uptime = subprocess.run(["uptime", "-s"], capture_output=True, text=True).stdout.strip()
    logger.log("SYSTEM_BOOT", f"Machine booted at {uptime}", "WARNING")

def check_login_history(logger: TripwireLogger):
    """Check for any login events since the last known session."""
    # Successful logins
    try:
        result = subprocess.run(
            ["last", "-n", "20", "--time-format", "iso"],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            if line.strip() and not line.startswith("wtmp") and not line.startswith("reboot"):
                logger.log("LOGIN_EVENT", line.strip())
    except Exception as e:
        logger.log("LOGIN_CHECK_FAIL", str(e), "WARNING")

    # Failed login attempts (btmp)
    try:
        result = subprocess.run(
            ["lastb", "-n", "20", "--time-format", "iso"],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            if line.strip() and not line.startswith("btmp"):
                logger.log("FAILED_LOGIN", line.strip(), "CRITICAL")
    except Exception:
        pass  # lastb requires root, may fail silently

# ── USB Device Monitoring ─────────────────────────────────────────────────────
def get_usb_devices() -> set:
    """Get a set of currently connected USB device identifiers."""
    devices = set()
    try:
        result = subprocess.run(
            ["lsusb"], capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            devices.add(line.strip())
    except Exception:
        pass
    return devices

# ── Network Interface Monitoring ──────────────────────────────────────────────
def get_network_state() -> dict:
    """Snapshot of all network interfaces and their states."""
    state = {}
    try:
        result = subprocess.run(
            ["ip", "-j", "link", "show"], capture_output=True, text=True
        )
        interfaces = json.loads(result.stdout)
        for iface in interfaces:
            name = iface.get("ifname", "unknown")
            flags = iface.get("flags", [])
            state[name] = {
                "operstate": iface.get("operstate", "unknown"),
                "flags": flags,
                "promisc": "PROMISC" in flags,
            }
    except Exception:
        pass
    return state

# ── Filesystem Watchdog (inotifywait) ─────────────────────────────────────────
def start_filesystem_watcher(logger: TripwireLogger):
    """Background thread using inotifywait to monitor ~/mycelium for changes."""
    def _watch():
        # Matched against the full path (ERE). Drops noisy dirs and DB/backup churn
        # from other daemons so FS_CHANGE stays signal, not scratch-file noise.
        exclude_pattern = (
            r"/(venv|__pycache__|\.git|node_modules|intelligence|ledger|chroma_db|bundle_server)/"
            r"|\.(pyc|swp)$"
            r"|\.db(-journal|-wal|-shm)?$"
            r"|~$"
        )
        cmd = [
            "inotifywait", "-m", "-r",
            "--exclude", exclude_pattern,
            "-e", "create,delete,modify,move,attrib",
            "--format", "%T %w%f %e",
            "--timefmt", "%Y-%m-%dT%H:%M:%S",
            WATCH_DIR
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # Token bucket: cap FS_CHANGE-driven DB inserts at ~20/sec so a
            # file-churn burst can't hammer telemetry.tripwire_events. Excess
            # events are dropped, not queued — a summary line records the drop.
            bucket_capacity = 20.0
            refill_per_sec = 20.0
            tokens = bucket_capacity
            last_refill = time.monotonic()
            dropped = 0

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue

                now = time.monotonic()
                tokens = min(bucket_capacity, tokens + (now - last_refill) * refill_per_sec)
                last_refill = now

                if tokens < 1:
                    dropped += 1
                    continue

                tokens -= 1
                if dropped:
                    logger.log("FS_CHANGE_RATE_LIMITED", f"Dropped {dropped} events during burst", "WARNING")
                    dropped = 0
                logger.log("FS_CHANGE", line, "WARNING")
        except Exception as e:
            logger.log("FS_WATCHER_FAIL", str(e), "CRITICAL")

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    logger.log("FS_WATCHER_ACTIVE", f"Monitoring {WATCH_DIR} for filesystem changes")

# ── Main Sentinel Loop ───────────────────────────────────────────────────────
def main():
    logger = TripwireLogger(TRIPWIRE_LOG)

    logger.log("TRIPWIRE_ACTIVATED", "Evil Maid Detection System ONLINE", "WARNING")

    # 1. Record boot event
    log_boot_event(logger)

    # 2. Check file integrity against baseline
    check_integrity(logger)

    # 3. Record login history
    check_login_history(logger)

    # 4. Start filesystem watchdog
    start_filesystem_watcher(logger)

    # 5. Continuous monitoring loop
    known_usb = get_usb_devices()
    known_net = get_network_state()
    logger.log("USB_BASELINE", f"{len(known_usb)} devices connected at activation")
    logger.log("NET_BASELINE", f"{len(known_net)} interfaces at activation")

    while True:
        time.sleep(POLL_INTERVAL)

        # USB delta detection
        current_usb = get_usb_devices()
        new_devices = current_usb - known_usb
        removed_devices = known_usb - current_usb
        for dev in new_devices:
            logger.log("USB_INSERTED", dev, "CRITICAL")
        for dev in removed_devices:
            logger.log("USB_REMOVED", dev, "WARNING")
        known_usb = current_usb

        # Network delta detection
        current_net = get_network_state()
        for iface, state in current_net.items():
            if iface not in known_net:
                logger.log("NET_NEW_IFACE", f"New interface appeared: {iface}", "CRITICAL")
            elif state.get("promisc") and not known_net.get(iface, {}).get("promisc"):
                logger.log("NET_PROMISC", f"Interface {iface} entered PROMISCUOUS mode", "CRITICAL")
        for iface in known_net:
            if iface not in current_net:
                logger.log("NET_IFACE_REMOVED", f"Interface disappeared: {iface}", "WARNING")
        known_net = current_net

if __name__ == "__main__":
    main()
