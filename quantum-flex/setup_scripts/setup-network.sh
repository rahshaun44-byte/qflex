#!/bin/bash
# setup-network.sh - Configures direct Starlink Bypass Mode networking on Fedora

echo "[+] Identifying active WAN interface..."
WAN_IFACE=$(ip route | awk '/default/ {print $5}')
CONN_NAME=$(nmcli -t -f NAME,DEVICE connection show --active | grep "$WAN_IFACE" | cut -d: -f1)

if [ -z "$CONN_NAME" ]; then
    echo "[-] Could not detect active NetworkManager connection. Are you connected?"
    exit 1
fi

echo "[+] Active connection: $CONN_NAME on $WAN_IFACE"

echo "[+] Adding static route for Starlink Dish Telemetry (192.168.100.1)..."
sudo nmcli connection modify "$CONN_NAME" +ipv4.routes "192.168.100.1/32"

echo "[+] Reloading NetworkManager connection..."
sudo nmcli connection up "$CONN_NAME"

echo "[+] Network configured successfully."
