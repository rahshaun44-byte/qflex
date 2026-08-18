# quantum_flex_notifier.py
# PURPOSE: Telegram notification + filesystem watchdog for AMARA vault directories
# USAGE: python quantum_flex_notifier.py
# REQUIRES: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID in environment

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
import aiohttp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("QFlexNotifier")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")

WATCH_PATHS = [
    Path.home() / "quantum-flex",
]

async def send_alert(message: str):
    """Send Telegram alert to ROOT."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set — alert suppressed")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })

def check_connectivity(host="8.8.8.8", port=53, timeout=3) -> bool:
    """Lightweight connectivity probe via DNS port."""
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

class AMARAWatcher(FileSystemEventHandler):
    def __init__(self, loop):
        self.loop = loop

    def on_modified(self, event):
        if not event.is_directory:
            msg = f"📝 *FILE MODIFIED*\n`{event.src_path}`\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            asyncio.run_coroutine_threadsafe(send_alert(msg), self.loop)

    def on_created(self, event):
        if not event.is_directory:
            msg = f"🆕 *FILE CREATED*\n`{event.src_path}`\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            asyncio.run_coroutine_threadsafe(send_alert(msg), self.loop)

async def main():
    valid_paths = [p for p in WATCH_PATHS if p.exists()]
    if not valid_paths:
        log.error("No valid watch paths found.")
        return

    loop = asyncio.get_event_loop()
    handler = AMARAWatcher(loop)
    observer = Observer()

    for path in valid_paths:
        observer.schedule(handler, str(path), recursive=True)
        log.info(f"Watching directory for changes: {path}")

    observer.start()
    
    await send_alert(
        "🚀 *QUANTUM FLEX ONLINE*\n"
        f"Watching {len(valid_paths)} directories\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    
    log.info("[*] Notifier active.")
    
    try:
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        log.info("[*] Shutting down notifier...")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    asyncio.run(main())
