#!/bin/bash
# setup-dns.sh - Configures systemd-resolved for DNS-over-TLS using Control D

# We will use the free Control D resolver. If you have a custom profile, replace the DNS/Domains below.
RESOLVER_IP="76.76.2.0"
RESOLVER_HOSTNAME="freedns.controld.com"

echo "[+] Configuring systemd-resolved for DNS-over-TLS..."

sudo mkdir -p /etc/systemd/resolved.conf.d/
cat <<EOF | sudo tee /etc/systemd/resolved.conf.d/10-controld-dot.conf
[Resolve]
DNS=$RESOLVER_IP#$RESOLVER_HOSTNAME
DNSOverTLS=yes
# Disable fallback to unencrypted DNS
FallbackDNS=
EOF

echo "[+] Restarting systemd-resolved..."
sudo systemctl restart systemd-resolved
sudo systemctl enable systemd-resolved

echo "[+] Verifying DNS configuration..."
resolvectl status | grep -E "DNS Server|DNSOverTLS"
