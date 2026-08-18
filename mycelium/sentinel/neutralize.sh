#!/usr/bin/env bash
# Quantum Flex - Memory Wipe & Neutralization Trigger
# This script must run as root (triggered by hardware GPIO or Sentinel monitor).

echo "[$(date)] INITIATING CRYPTOGRAPHIC NEUTRALIZATION" > /dev/kmsg

# 1. Flush non-sensitive filesystem buffers safely
sync

# 2. Clear PageCache, dentries, and inodes (Volatile RAM)
# This eradicates lingering cached keys or unencrypted file chunks from memory.
echo 3 > /proc/sys/vm/drop_caches

# 3. Secure immediate halt (Kernel Panic trigger)
# We do NOT run a clean shutdown, as that might write state to disk or give an attacker time.
# 'o' triggers an immediate ACPI power-off (or halt if power-off fails).
# The encrypted LUKS volume remains locked, and the network key is lost from RAM.
echo 1 > /proc/sys/kernel/sysrq
echo o > /proc/sysrq-trigger
