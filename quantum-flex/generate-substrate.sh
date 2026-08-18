#!/bin/bash
set -euo pipefail

REPORT="docs/substrate-report.md"
mkdir -p docs
echo "# Quantum Flex: Substrate Reality Report" > "$REPORT"
echo "**Timestamp:** $(date -u +'%Y-%m-%dT%H:%M:%SZ')" >> "$REPORT"

echo -e "\n## 1. Block Device & Encryption State" >> "$REPORT"
lsblk -o NAME,FSTYPE,SIZE,FSAVAIL,FSUSE%,MOUNTPOINTS >> "$REPORT" || echo "lsblk failed" >> "$REPORT"

echo -e "\n## 2. Btrfs Subvolume Topology" >> "$REPORT"
sudo -n btrfs subvolume list / >> "$REPORT" || echo "btrfs failed" >> "$REPORT"

echo -e "\n## 3. EFI Bootloader State" >> "$REPORT"
sudo -n efibootmgr -v >> "$REPORT" || echo "efibootmgr failed" >> "$REPORT"

echo -e "\n## 4. UEFI Secure Boot Verification" >> "$REPORT"
mokutil --sb-state >> "$REPORT" || echo "mokutil failed" >> "$REPORT"

echo -e "\n## 5. Network Boundary (Firewalld)" >> "$REPORT"
sudo -n firewall-cmd --list-all >> "$REPORT" || echo "firewalld failed" >> "$REPORT"

echo "[*] Substrate Report Generated at $REPORT"
