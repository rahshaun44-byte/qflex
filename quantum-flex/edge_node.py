import asyncio
import fcntl
import os
import socket
import struct
import asyncpg
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime

app = FastAPI()

class LogisticsData(BaseModel):
    shipment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    lat: float
    lon: float
    status: str
    temperature_c: float

pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        min_size=10,
        max_size=50
    )
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS edge_ingest_queue (
                id SERIAL PRIMARY KEY,
                shipment_id TEXT,
                timestamp TIMESTAMP,
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION,
                status TEXT,
                temperature_c DOUBLE PRECISION
            )
        ''')
    print("Database pool established and edge_ingest_queue table ready.")

@app.post("/ingest")
async def ingest_data(payload: List[LogisticsData]):
    async with pool.acquire() as conn:
        records = [
            (p.shipment_id, p.timestamp, p.lat, p.lon, p.status, p.temperature_c)
            for p in payload
        ]
        # executemany triggers fast asynchronous inserts
        await conn.executemany('''
            INSERT INTO edge_ingest_queue (shipment_id, timestamp, lat, lon, status, temperature_c)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', records)
    return {"status": "success", "inserted": len(payload)}

def _resolve_bind_host() -> str:
    """Never hardcode the Tailscale IP: resolve it fresh at every startup so a
    re-registered/changed tailnet address doesn't require a code/config edit.
    This container has no `tailscale` CLI, but network_mode: host means the
    tailscale0 interface is visible directly — read its address via ioctl
    (stdlib only, no extra install needed)."""
    if "EDGE_HOST" in os.environ:
        return os.environ["EDGE_HOST"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packed_iface = struct.pack("256s", b"tailscale0"[:15])
        addr = fcntl.ioctl(s.fileno(), 0x8915, packed_iface)  # SIOCGIFADDR
        return socket.inet_ntoa(addr[20:24])
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=_resolve_bind_host(),
        port=int(os.environ.get("EDGE_PORT", "8000")),
    )
