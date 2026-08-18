import httpx
import uuid
from datetime import datetime
import asyncio

async def run_test():
    payload = []
    for _ in range(1000):
        payload.append({
            "shipment_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "lat": 34.0522,
            "lon": -118.2437,
            "status": "IN_TRANSIT",
            "temperature_c": 4.5
        })
    
    async with httpx.AsyncClient() as client:
        print("Firing 1,000-line JSON payload to Edge Node (Port 8000)...")
        res = await client.post("http://127.0.0.1:8000/ingest", json=payload, timeout=10.0)
        print(f"Response: {res.status_code} - {res.json()}")

if __name__ == "__main__":
    asyncio.run(run_test())
