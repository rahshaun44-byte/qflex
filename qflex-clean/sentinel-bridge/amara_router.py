import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from semantic_router import Route, RouteLayer
from semantic_router.encoders import HuggingFaceEncoder
from nats.aio.client import Client as NATS

# 1. Initialize Local Encoder
encoder = HuggingFaceEncoder(name="sentence-transformers/all-MiniLM-L6-v2")

# 2. Define the Topology
edge_route = Route(
    name="local_ollama",
    utterances=[
        "Starlink ping success",
        "classify obstruction data",
        "telemetry ping drop",
        "packet loss detected",
        "analyze low complexity hardware logs"
    ]
)

cloud_route = Route(
    name="cloud_gemini",
    utterances=[
        "Write a complex python application",
        "Summarize this threat intelligence report",
        "Generate a system architecture document"
    ]
)

market_route = Route(
    name="market_intelligence",
    utterances=[
        "Bitcoin dip",
        "Ethereum price",
        "ETF outflows",
        "Crypto sell-off",
        "Stablecoin supply surge",
        "Debt repurchase yield"
    ]
)

rl = RouteLayer(encoder=encoder, routes=[edge_route, cloud_route, market_route])

# 3. Build the NATS Background Listener
async def nats_subscriber():
    nc = NATS()
    try:
        await nc.connect("nats://127.0.0.1:4222")
        print("A.M.A.R.A: Connected to NATS JetStream. Listening for telemetry...")

        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            content = data.get("messages", [{}])[-1].get("content", "")
            
            # Execute Semantic Classification
            decision = rl(content)
            target = "http://localhost:11434 (qwen3-coder)" if decision.name == "local_ollama" else "https://api.gemini.google.com"
            
            print("\n=== [MYCELIAL ROUTE TRIGGERED] ===")
            print(f"Payload: {content}")
            print(f"Classification: {decision.name or 'unclassified_default_cloud'}")
            print(f"Execution Target: {target}")
            print("==================================\n")

        await nc.subscribe("quantum.mycelium.telemetry", cb=message_handler)
    except Exception as e:
        print(f"NATS Subscriber Error: {e}")

# 4. Attach Listener to FastAPI Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(nats_subscriber())
    yield
    task.cancel()

app = FastAPI(title="A.M.A.R.A. Quantum Flex Node", lifespan=lifespan)

# 5. Maintain REST API Fallback
class ChatPayload(BaseModel):
    messages: list
    model: str = "auto"

@app.post("/v1/chat/completions")
async def route_telemetry(payload: ChatPayload):
    content = payload.messages[-1].get("content", "")
    decision = rl(content)
    target_backend = "http://localhost:11434 (qwen3-coder)" if decision.name == "local_ollama" else "https://api.gemini.google.com"
    return {
        "status": "Mycelial Route Established",
        "telemetry_received": content,
        "classification": decision.name or "unclassified_default_cloud",
        "execution_target": target_backend,
        "node": "Pittston-Quantum-Flex"
    }
