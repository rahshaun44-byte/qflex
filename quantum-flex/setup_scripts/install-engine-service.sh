#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer as root: sudo $0" >&2
    exit 1
fi

QF_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QF_BIN_DIR="/usr/local/libexec/quantum-flex"
QF_BIN="$QF_BIN_DIR/quantum_flex"
QF_CONFIG_DIR="/etc/quantum-flex"
QF_DATA_DIR="/var/lib/quantum-flex"
QF_SERVICE_USER="quantum-flex"
QF_PKI_DIR="$QF_CONFIG_DIR/pki"

if ! getent group "$QF_SERVICE_USER" >/dev/null; then
    groupadd --system "$QF_SERVICE_USER"
fi
if ! id "$QF_SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --gid "$QF_SERVICE_USER" --no-create-home \
        --home-dir / --shell /sbin/nologin "$QF_SERVICE_USER"
fi

install -d -m 0755 "$QF_BIN_DIR"
install -d -m 0750 -o "$QF_SERVICE_USER" -g "$QF_SERVICE_USER" "$QF_DATA_DIR"
install -d -m 0750 -o root -g "$QF_SERVICE_USER" "$QF_CONFIG_DIR"
for required_pki in ca.crt server.crt server.key; do
    test -r "$QF_PKI_DIR/$required_pki" || {
        echo "Missing $QF_PKI_DIR/$required_pki; run generate-mtls-pki.sh first." >&2
        exit 1
    }
done
install -o root -g root -m 0755 "$QF_ROOT/build/quantum_flex" "$QF_BIN"
install -o root -g "$QF_SERVICE_USER" -m 0644 \
    "$QF_PKI_DIR/server.crt" "$QF_CONFIG_DIR/server.crt"
install -o root -g "$QF_SERVICE_USER" -m 0640 \
    "$QF_PKI_DIR/server.key" "$QF_CONFIG_DIR/server.key"
install -o root -g "$QF_SERVICE_USER" -m 0644 \
    "$QF_PKI_DIR/ca.crt" "$QF_CONFIG_DIR/root-ca.crt"
install -o root -g "$QF_SERVICE_USER" -m 0640 \
    "$QF_ROOT/data/ed_priv.pem" "$QF_CONFIG_DIR/ed_priv.pem"
install -o root -g "$QF_SERVICE_USER" -m 0640 \
    "$QF_ROOT/data/pqc_priv.pem" "$QF_CONFIG_DIR/pqc_priv.pem"
if [[ -f "$QF_ROOT/data/ledger.dat" ]]; then
    install -o "$QF_SERVICE_USER" -g "$QF_SERVICE_USER" -m 0640 \
        "$QF_ROOT/data/ledger.dat" "$QF_DATA_DIR/ledger.dat"
fi
install -o root -g root -m 0644 \
    "$QF_ROOT/setup_scripts/quantum-flex-engine.service" \
    /etc/systemd/system/quantum-flex-engine.service

# A system service must not execute a user_home_t binary.  Persist the
# executable label so it survives relabels and future rebuilds.
if command -v semanage >/dev/null 2>&1; then
    semanage fcontext -a -t bin_t "$QF_BIN_DIR(/.*)?" 2>/dev/null || \
        semanage fcontext -m -t bin_t "$QF_BIN_DIR(/.*)?"
    restorecon -RFv "$QF_BIN_DIR"
fi

systemctl daemon-reload
systemctl enable quantum-flex-engine.service
systemctl restart quantum-flex-engine.service
systemctl --no-pager --full status quantum-flex-engine.service
