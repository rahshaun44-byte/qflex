#!/usr/bin/env bash
set -euo pipefail

# Install the harvester outside /home.  System services running code and
# private keys from a home directory are commonly denied by SELinux and
# should not need access to a user's home at runtime.
QF_INSTALL_DIR="/usr/local/libexec/quantum-flex"
QF_CONFIG_DIR="/etc/quantum-flex"
QF_SERVICE_USER="quantum-flex"
QF_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QF_PKI_DIR="/etc/quantum-flex/pki"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer as root (for example: sudo $0)." >&2
    exit 1
fi

if ! getent group "$QF_SERVICE_USER" >/dev/null; then
    groupadd --system "$QF_SERVICE_USER"
fi
if ! id "$QF_SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --gid "$QF_SERVICE_USER" --no-create-home \
        --home-dir / --shell /sbin/nologin "$QF_SERVICE_USER"
fi

install -d -m 0755 "$QF_INSTALL_DIR"
install -d -m 0750 -o "$QF_SERVICE_USER" -g "$QF_SERVICE_USER" "$QF_CONFIG_DIR"
for required_pki in ca.crt client.crt client.key; do
    test -r "$QF_PKI_DIR/$required_pki" || {
        echo "Missing $QF_PKI_DIR/$required_pki; run generate-mtls-pki.sh first." >&2
        exit 1
    }
done

install -o root -g root -m 0755 \
    "$QF_ROOT/clients/python/sentinel_harvester.py" \
    "$QF_INSTALL_DIR/sentinel_harvester.py"
install -o root -g "$QF_SERVICE_USER" -m 0640 \
    "$QF_PKI_DIR/client.crt" "$QF_CONFIG_DIR/endpoint.crt"
install -o root -g "$QF_SERVICE_USER" -m 0640 \
    "$QF_PKI_DIR/client.key" "$QF_CONFIG_DIR/endpoint.key"
install -o root -g "$QF_SERVICE_USER" -m 0644 \
    "$QF_PKI_DIR/ca.crt" "$QF_CONFIG_DIR/root-ca.crt"
install -o root -g root -m 0644 \
    "$QF_ROOT/sentinel-harvester.service.tmp" \
    /etc/systemd/system/quantum-flex-sentinel-harvester.service

# Make labels persistent across relabels.  restorecon is deliberately
# conditional so development hosts without SELinux can still use the script.
if command -v semanage >/dev/null 2>&1; then
    semanage fcontext -a -t bin_t "$QF_INSTALL_DIR(/.*)?" 2>/dev/null || \
        semanage fcontext -m -t bin_t "$QF_INSTALL_DIR(/.*)?"
    semanage fcontext -a -t etc_t "$QF_CONFIG_DIR(/.*)?" 2>/dev/null || \
        semanage fcontext -m -t etc_t "$QF_CONFIG_DIR(/.*)?"
    restorecon -RFv "$QF_INSTALL_DIR" "$QF_CONFIG_DIR"
fi

systemctl daemon-reload
systemctl enable --now quantum-flex-sentinel-harvester.service
echo "Installed quantum-flex-sentinel-harvester.service."
