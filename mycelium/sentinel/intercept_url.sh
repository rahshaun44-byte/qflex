#!/bin/bash

# intercept_url.sh
# Unmask shortened URLs and log their true destination for OSINT analysis.
# Usage: ./intercept_url.sh <shortened_url>

if [ -z "$1" ]; then
    echo "Usage: $0 <shortened_url>"
    exit 1
fi

TARGET_URL="$1"
LOG_FILE="$(dirname "$0")/intercepted_urls.log"

echo "[*] Intercepting URL: $TARGET_URL"

# Fetch the headers and extract the Location field
# We use curl -sI to silently fetch only headers.
# Add a User-Agent to bypass basic bot-protection (like Cloudflare)
USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
TRUE_DESTINATION=$(curl -sI -A "$USER_AGENT" "$TARGET_URL" | grep -i "^location:" | awk '{print $2}' | tr -d '\r')

if [ -z "$TRUE_DESTINATION" ]; then
    echo "[!] No redirect (Location header) found for $TARGET_URL"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $TARGET_URL - [NO REDIRECT FOUND]" >> "$LOG_FILE"
else
    echo "[+] Unmasked Destination: $TRUE_DESTINATION"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $TARGET_URL - $TRUE_DESTINATION" >> "$LOG_FILE"
fi

echo "[*] Analysis logged to $LOG_FILE"
