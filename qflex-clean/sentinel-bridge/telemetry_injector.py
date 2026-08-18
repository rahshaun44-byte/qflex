import asyncio
import json
from nats.aio.client import Client as NATS

async def inject_telemetry():
    nc = NATS()
    
    # 1. Connect to the local bus
    try:
        await nc.connect("nats://127.0.0.1:4222")
        print("STATUS: Connected to NATS JetStream")
    except Exception as e:
        print(f"ERROR: Bus connection failed - Is the nats-server running? ({e})")
        return

    # 2. Define the exact DPI payload
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": "Starlink ping success 54.90% — classify complexity"}]
    }

    # 3. Publish to the Mycelial topic
    target_topic = "quantum.mycelium.telemetry"
    await nc.publish(target_topic, json.dumps(payload).encode())
    print(f"PAYLOAD SECURED: Telemetry injected into {target_topic}")

    # 4. Graceful closure
    await nc.drain()

if __name__ == '__main__':
    asyncio.run(inject_telemetry())
