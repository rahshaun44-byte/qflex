#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script as root: sudo $0" >&2
    exit 1
fi

PKI_DIR="/etc/quantum-flex/pki"
BACKUP_ROOT="/var/backups/quantum-flex-pki"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
umask 077

if ! getent group quantum-flex >/dev/null; then
    groupadd --system quantum-flex
fi

install -d -m 0750 -o root -g quantum-flex /etc/quantum-flex
install -d -m 0700 -o root -g root "$BACKUP_ROOT"

if [[ -d "$PKI_DIR" ]]; then
    backup_dir="$BACKUP_ROOT/$(date +%Y%m%d%H%M%S)"
    mv "$PKI_DIR" "$backup_dir"
    echo "[+] Previous PKI backed up to $backup_dir"
fi

install -d -m 0700 -o root -g root "$PKI_DIR"

openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "$TMP_DIR/ca.key" -out "$TMP_DIR/ca.crt" -days 365 \
    -subj '/C=US/O=QuantumFlex/CN=QuantumFlex Root CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:1' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -addext 'subjectKeyIdentifier=hash'

cat > "$TMP_DIR/server.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:endpoint.local,IP:127.0.0.1
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

cat > "$TMP_DIR/client.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
subjectAltName=DNS:sentinel-01
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

for role in server client; do
    openssl req -new -newkey rsa:3072 -nodes \
        -keyout "$TMP_DIR/$role.key" -out "$TMP_DIR/$role.csr" \
        -subj "/C=US/O=QuantumFlex/CN=$([[ "$role" == server ]] && echo endpoint.local || echo sentinel-01)"
    openssl x509 -req -in "$TMP_DIR/$role.csr" \
        -CA "$TMP_DIR/ca.crt" -CAkey "$TMP_DIR/ca.key" \
        -CAcreateserial -out "$TMP_DIR/$role.crt" -days 365 -sha256 \
        -extfile "$TMP_DIR/$role.ext"
done

install -m 0600 -o root -g root "$TMP_DIR/ca.key" "$PKI_DIR/ca.key"
install -m 0644 -o root -g quantum-flex "$TMP_DIR/ca.crt" "$PKI_DIR/ca.crt"
install -m 0600 -o root -g quantum-flex "$TMP_DIR/server.key" "$PKI_DIR/server.key"
install -m 0640 -o root -g quantum-flex "$TMP_DIR/server.crt" "$PKI_DIR/server.crt"
install -m 0600 -o root -g quantum-flex "$TMP_DIR/client.key" "$PKI_DIR/client.key"
install -m 0640 -o root -g quantum-flex "$TMP_DIR/client.crt" "$PKI_DIR/client.crt"

openssl verify -purpose sslserver -CAfile "$PKI_DIR/ca.crt" "$PKI_DIR/server.crt"
openssl verify -purpose sslclient -CAfile "$PKI_DIR/ca.crt" "$PKI_DIR/client.crt"
echo "[+] Managed mTLS PKI generated in $PKI_DIR"
