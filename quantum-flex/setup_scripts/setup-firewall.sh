#!/bin/bash
# setup-firewall.sh - Installs the Quantum Flex nftables-only firewall policy.

set -euo pipefail

echo "[+] Installing nftables (if not present)..."
sudo dnf install -y nftables

echo "[+] Writing hardened nftables ruleset..."
cat << 'EOF' | sudo tee /etc/nftables/hardened-edge.nft
#!/usr/sbin/nft -f

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;

        # Accept loopback traffic
        iif "lo" accept

        # Accept established and related connections
        ct state established,related accept

        # Drop invalid packets (XMAS, NULL, SYN-FIN etc)
        ct state invalid drop

        # Zero-trust SSH: only the managed Galaxy S23 FE may reach sshd,
        # which is itself bound only to the Tailscale address and loopback.
        iifname "tailscale0" ip saddr 100.107.237.53 ip daddr 100.120.30.95 tcp dport 22 ct state new accept

        # Allow essential ICMP (ping, fragmentation needed)
        ip protocol icmp icmp type { echo-request, echo-reply, destination-unreachable, time-exceeded } accept
        ip6 nexthdr icmpv6 icmpv6 type { echo-request, echo-reply, destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-router-advert, nd-neighbor-solicit, nd-neighbor-advert } accept
        
        # Everything else drops (default policy)
    }

    chain forward {
        type filter hook forward priority 0; policy drop;
    }

    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF

echo "[+] Validating the ruleset before changing firewall ownership..."
sudo nft -c -f /etc/nftables/hardened-edge.nft

echo "[+] Backing up the current persistent nftables configuration..."
if sudo test -f /etc/sysconfig/nftables.conf; then
    sudo cp --preserve=mode,ownership,timestamps /etc/sysconfig/nftables.conf \
        /etc/sysconfig/nftables.conf.quantum-flex.bak
fi

echo "[+] Loading the nftables-only policy..."
# Replace only the Quantum Flex table. Do not flush the complete ruleset:
# Tailscale owns separate ip/ip6 tables and must retain those chains.
sudo nft delete table inet filter 2>/dev/null || true
sudo nft -f /etc/nftables/hardened-edge.nft

echo "[+] Making nftables authoritative..."
sudo systemctl disable --now firewalld || true
sudo systemctl enable --now nftables

# Save to default load path so it persists reboots
sudo cp /etc/nftables/hardened-edge.nft /etc/sysconfig/nftables.conf

echo "[+] Firewall hardened. Current ruleset:"
sudo nft list ruleset

echo "[+] Verifying the managed SSH exception and firewall ownership..."
sudo nft list chain inet filter input | grep -F '100.107.237.53' >/dev/null
test "$(systemctl is-active firewalld)" = "inactive"
test "$(systemctl is-active nftables)" = "active"
echo "[+] Verification passed."
