# Quantum Flex — AI/IDE Handoff: Tailscale SSH Handshake

````## Objective

Establish key-only SSH from a Samsung Galaxy S23 FE running Termux to Fedora host `yoga` over Tailscale.

## Verified state

- Server: `yoga`, Fedora KDE, Tailscale IPv4 `100.120.30.95`
- Client: Samsung Galaxy S23 FE / Termux, Tailscale IPv4 `100.107.237.53`
- `sshd`: active; listeners are `127.0.0.1:22` and `100.120.30.95:22`
- SSH authentication: public-key enabled; password authentication disabled
- firewalld: `tailscale0` is in `trusted`, target `ACCEPT`
- Tailscale ACL: allow-all (`src: ["*"]`, `dst: ["*"]`, all ports)
- Ping works from Termux to the server
- Termux TCP tests to ports `22` and `9999` time out
- Fedora capture sees repeated client SYNs on `tailscale0`, but no SYN-ACK on that capture:

```text
100.107.237.53:60408 > 100.120.30.95:22 Flags [S]
```

- Server route lookup is correct:

```text
100.107.237.53 dev tailscale0 src 100.120.30.95
```

- Reverse-path filtering is not strict:

```text
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.tailscale0.rp_filter = 2
```

- Server self-connect to `100.120.30.95:22` succeeds.

## Root cause — confirmed

The initial SYN is accepted by Tailscale's `ip filter ts-input` chain and then dropped by a separate unmanaged nftables base chain:

```text
ip filter ts-input ... iifname "tailscale0" ... accept
inet filter input ... policy drop
```

The chain is created by `setup_scripts/setup-firewall.sh`. Its rules allow loopback, established traffic, and ICMP, but omit the Tailscale SSH exception. Both `firewalld` and `nftables` were active, creating competing firewall planes. This is the direct cause of the TCP timeout.

Do not disable SELinux or use `iptables -I`; neither addresses the demonstrated drop, and iptables compatibility rules create configuration drift on Fedora.

## Next commands — run on `yoga` during one Termux connection attempt

Use three terminals and keep the existing console session open.

### 1. Confirm socket and TCP state

```bash
sudo ss -Hntp state syn-recv
sudo ss -lntp '( sport = :22 or sport = :9999 )'
sudo journalctl -k --since '5 minutes ago' --no-pager | grep -iE 'martian|rp_filter|drop|tcp|tailscale'
```

### 2. Trace nftables exactly (historical diagnostic)

```bash
sudo nft add table inet qftrace
sudo nft 'add chain inet qftrace prerouting { type filter hook prerouting priority -301; policy accept; }'
sudo nft 'add rule inet qftrace prerouting ip saddr 100.107.237.53 ip daddr 100.120.30.95 tcp dport 22 meta nftrace set 1'
sudo nft monitor trace
```

In Termux, run:

```bash
nc -vz -w 5 100.120.30.95 22
```

Afterward, stop the trace with Ctrl-C and remove the temporary instrumentation:

```bash
sudo nft delete table inet qftrace
```

### 3. Capture both directions and the physical Tailscale transport

```bash
sudo tcpdump -i tailscale0 -nn -S 'host 100.107.237.53 and tcp port 22'
```

In another server terminal:

```bash
sudo tcpdump -i any -nn -S 'host 100.107.237.53 and tcp port 22'
```

If available, also inspect conntrack:

```bash
sudo conntrack -E -o timestamp -p tcp
```

## Remediation

The repository firewall source now adds a narrow allow for the managed phone:

```nft
iifname "tailscale0" ip saddr 100.107.237.53 ip daddr 100.120.30.95 tcp dport 22 ct state new accept
```

Apply it from the Fedora console while keeping the current console open:

```bash
cd /home/rahshaunchambers/quantum-flex
bash setup_scripts/setup-firewall.sh
```

The script validates the ruleset, backs up the persistent nftables file, loads the policy, disables firewalld, enables nftables, and verifies the SSH exception.

## Decision tree

- `nft monitor trace` should now show the `inet filter input` allow rule rather than its default policy drop.
- Trace reaches `accept`, but no `SYN-RECV` appears: investigate local TCP policy/socket state; collect `ss`, kernel journal, and sysctls before changing anything.
- `SYN-ACK` appears on `-i any` but not on `tailscale0`: investigate Tailscale netfilter/transport behavior.
- `SYN-ACK` appears on `tailscale0` but Termux never receives it: investigate the Android Tailscale path, not Fedora SSH.
- No conntrack entry and no trace: packet is being discarded before the expected hook or the capture is not observing the relevant path.

## Security posture notes

Keep `PasswordAuthentication no`, `PermitRootLogin no`, and the Tailscale-only listener. Do not rewrite `/etc/ssh/sshd_config` wholesale until all included drop-ins are inspected; OpenSSH uses the first value encountered for many directives, so a drop-in can silently override assumptions.

Before any SSH restart:

```bash
sudo sshd -t && sudo systemctl reload sshd
```

The Termux Ed25519 key was generated with fingerprint:

```text
SHA256:AUQtbYwlFog7Z/YEhaiG7CKMJVGrMDp/8tadELnPzak
```

The public key still needs to be installed in the Fedora account's `~/.ssh/authorized_keys` through a trusted local console or other authenticated channel. TCP troubleshooting must finish before key installation can occur over SSH.

## Secrets and phishing hygiene

A payment/verification code was pasted into the prior transcript. Treat it as exposed and expired; never enter or share it based on chat instructions. The authenticity of a checkout URL cannot be established from its hostname alone. Verify purchases directly through the official account or merchant UI.
````
