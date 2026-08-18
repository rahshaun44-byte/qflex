# Quantum Flex: Substrate Reality Report
**Timestamp:** 2026-07-20T02:35:50Z

## 1. Block Device & Encryption State
NAME                                          FSTYPE        SIZE FSAVAIL FSUSE% MOUNTPOINTS
zram0                                         swap            8G                [SWAP]
nvme0n1                                                   476.9G                
├─nvme0n1p1                                   vfat          600M  569.8M     5% /boot/efi
├─nvme0n1p2                                   ext4            2G    1.2G    33% /boot
└─nvme0n1p3                                   crypto_LUKS 474.4G                
  └─luks-7ad5581d-7c56-47bb-a9fc-4b1a92739ac3 btrfs       474.3G  396.2G    15% /home
                                                                                /

## 2. Btrfs Subvolume Topology
btrfs failed

## 3. EFI Bootloader State
efibootmgr failed

## 4. UEFI Secure Boot Verification
SecureBoot enabled

## 5. Network Boundary (Firewalld)
firewalld failed
