# KDE Connect Convergence Architecture

## Operational Mandate
Running Fedora 44 KDE alongside a mobile device provides access to KDE Connect. Because it operates locally over the Wi-Fi network without routing through external cloud servers, it delivers zero-latency convergence, shared clipboards, and remote terminal execution with minimal security exposure.

## Technical Architecture & Firewall Protocol
Under the hood, KDE Connect uses UDP broadcast discovery and establishes an end-to-end encrypted TLS socket connection over local TCP ports `1714` through `1764`.

Because Fedora ships with strict `firewalld` rules by default, the local network interface will drop these incoming pairing packets until the service is explicitly permitted in the active firewall zone.

### Ingress Firewall Configuration (`firewalld`)
Run these commands on the host to grant persistent access:
```bash
sudo firewall-cmd --add-service=kdeconnect --permanent
sudo firewall-cmd --reload
sudo firewall-cmd --list-services
```

## High-Leverage Convergence Workflows

### 1. Trigger System Focus Sprints from Your Phone
Bind custom CLI commands to your phone screen via KDE Connect to launch or stop the local `focus.py` script directly from a quick-settings tile.
- **Target Command:** `sudo /usr/local/bin/focus -t 45`
- **Mechanism:** KDE Connect executes the command as the local desktop user over an authenticated local D-Bus interface.

### 2. Encrypted Cross-Device Clipboard & File Transfer
- **Shared Clipboard:** Any string copied on the phone is instantly available in the Linux terminal selection (`xclip` / `wl-paste` compatible on Wayland/Plasma 6).
- **Direct AirDrop-Style Transfers:** Send captures, logs, or payload files between phone and PC via local TLS sockets without uploading to third-party cloud storage.

### 3. Notification Muting During Heavy Execution
Configure KDE Connect on Plasma to automatically pause media or mute phone notifications whenever the PC enters a high-load execution block or runs a specific application.

## Pair & Deploy Protocol

1. **Install Mobile Client:** Install KDE Connect on the phone (F-Droid / Play Store). Ensure both host and phone are on the same local Wi-Fi subnet or VPN tunnel.
2. **Initiate Device Pairing:** Establish mutual TLS trust via desktop or phone. Open System Settings -> KDE Connect on Fedora KDE, request pairing, and accept the cryptographic fingerprint.
3. **Configure Custom Commands:** In KDE Connect settings on Fedora, navigate to Run Commands -> Edit Commands.
   - **Name:** `Start 30m Focus Sprint` | **Command:** `focus -t 30`
   - **Name:** `System Status` | **Command:** `notify-send "CPU Temp" "$(sensors | grep 'Package id 0:')"`
