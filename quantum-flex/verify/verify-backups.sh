#!/bin/bash
set -euo pipefail

echo "[*] Initiating Btrfs Temporal Rollback Test..."

# Define test paths
TEST_VOL="artifacts/btrfs-test-vol"
SNAP_VOL="artifacts/btrfs-test-snap"
TEST_FILE="$TEST_VOL/telemetry.dat"

# Ensure clean state
if [ -d "$TEST_VOL" ]; then sudo btrfs subvolume delete "$TEST_VOL" >/dev/null; fi
if [ -d "$SNAP_VOL" ]; then sudo btrfs subvolume delete "$SNAP_VOL" >/dev/null; fi

# 1. Create nested subvolume & initial data
sudo btrfs subvolume create "$TEST_VOL" >/dev/null
echo "QUANTUM_FLEX_SECURE_BASELINE" | sudo tee "$TEST_FILE" > /dev/null

# 2. Cryptographic hashing of initial state
ORIGINAL_HASH=$(sha256sum "$TEST_FILE" | awk '{ print $1 }')
echo " -> Baseline Hash: $ORIGINAL_HASH"

# 3. Create snapshot
sudo btrfs subvolume snapshot "$TEST_VOL" "$SNAP_VOL" >/dev/null
echo " -> Snapshot Locked."

# 4. Simulate catastrophic corruption
echo "MALICIOUS_LOGIC_BOMB_INSERTED" | sudo tee "$TEST_FILE" > /dev/null
CORRUPTED_HASH=$(sha256sum "$TEST_FILE" | awk '{ print $1 }')
echo " -> Mutated Hash:  $CORRUPTED_HASH"

if [ "$ORIGINAL_HASH" == "$CORRUPTED_HASH" ]; then
    echo "[!] FATAL: Mutation failed."
    exit 1
fi

# 5. Execute Rollback (Destroy corrupted volume, restore from snapshot)
sudo btrfs subvolume delete "$TEST_VOL" >/dev/null
sudo btrfs subvolume snapshot "$SNAP_VOL" "$TEST_VOL" >/dev/null

# 6. Verify recovered state
RECOVERED_HASH=$(sha256sum "$TEST_FILE" | awk '{ print $1 }')
echo " -> Restored Hash: $RECOVERED_HASH"

# 7. Teardown
sudo btrfs subvolume delete "$TEST_VOL" >/dev/null
sudo btrfs subvolume delete "$SNAP_VOL" >/dev/null

# 8. Assert Truth
if [ "$ORIGINAL_HASH" == "$RECOVERED_HASH" ]; then
    echo "[*] PASS: Btrfs Snapshot Rollback Proven."
    exit 0
else
    echo "[!] FATAL: Recovery failed to match initial baseline."
    exit 1
fi
