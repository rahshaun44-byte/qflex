# Fedora Host Hardening Checklist

## 1. SELinux (Security-Enhanced Linux)
Fedora ships with SELinux in **Enforcing** mode by default. Ensure it stays that way.
- **Check status:** `sestatus`
- **Current mode:** `getenforce`
- If you need to troubleshoot blocked actions, use: `sudo ausearch -m AVC,USER_AVC -ts recent`
- Install the harvester with `sudo setup_scripts/install-sentinel-service.sh`. It runs as
  the dedicated `quantum-flex` user, keeps code and keys outside `/home`, and applies
  persistent `bin_t`/`etc_t` labels with `semanage fcontext` and `restorecon`.

## 2. Containerization (Rootless Podman)
Do not use Docker (which runs as a root daemon). Fedora uses **Podman** out of the box, which can run rootless.
- **Run containers as your standard user:** `podman run -d --name quantum-flex-ui nginx`
- Your containers will map to your user namespace, heavily mitigating container breakout attacks.

## 3. systemd Secure Baselines
When you create systemd services for Quantum Flex components, harden them:
```ini
[Service]
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
```
This ensures your daemons cannot overwrite `/usr`, `/boot`, or your home directory.
