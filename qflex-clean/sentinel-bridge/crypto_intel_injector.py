import asyncio
import json
from nats.aio.client import Client as NATS

async def inject_crypto_intel():
    nc = NATS()
    
    # 1. Connect to the local bus
    try:
        await nc.connect("nats://127.0.0.1:4222")
        print("STATUS: Connected to NATS JetStream")
    except Exception as e:
        print(f"ERROR: Bus connection failed - Is the nats-server running? ({e})")
        return

    # 2. Define the market intelligence payload
    intel_content = """Bitcoin and ethereum prices pull back in another choppy week: The price of bitcoin dipped below $74,000 and ethereum dropped below $2,000 this week amid a crypto sell-off that occurred while the broader market pushed higher. The bitcoin dip came as the 11 US spot bitcoin ETFs recorded $733 million in net outflows on Wednesday, putting selling pressure on the bitcoin market. Meanwhile, the price of ether continued to trend lower despite Tom Lee’s Bitmine Immersion Technologies announcing it had purchased 111,942 ETH over the previous week, with the treasury company now owning almost 5.4 million ETH tokens. Despite high utility across DeFi, ethereum sentiment has suffered over the past year after it nearly topped out at $5,000 last August.
Strategy completes $1.5 billion debt repurchase: Michael Saylor’s Strategy announced this week it has purchased $1.5 billion in 0% senior convertible notes due in 2029 for $1.38 billion in cash. With the move, Strategy trimmed the company’s aggregate principal amount of convertible notes outstanding from $8.2 billion to $6.7 billion. According to the statement announcing the deal, Strategy has achieved year-to-date BTC yield of 13.3%, or approximately $6.8 billion. It comes after Strategy announced earlier this month it would actively manage its bitcoin treasury, which could include selling bitcoin.
Grayscale pushes back IPO: Crypto-focused asset manager Grayscale has chosen to hold off on IPO planning until Q4 at the earliest, according to Coindesk. A source reportedly cited unfavorable market conditions as the reason for the delay as crypto contends with a prolonged bear market after peaking last October. The Stamford-based firm originally confidentially filed for an IPO this past November. Grayscale is a large digital asset management company, managing tens of billions in publicly-traded crypto funds.
Demand surges for Tether’s USAT stablecoin: The supply of Tether’s USAT stablecoin jumped 540% over the past month, according to a company attestation released Thursday. Specifically, the number of redeemable USAT tokens jumped from 22 million to over 140 million from March to April, with the total reserve supply hitting $141,178,400. Tether, the world’s largest stablecoin company, launched USAT in January in an effort to enter the US market and comply with the GENIUS Act, which was passed last year."""

    payload = {
        "model": "auto",
        "event_type": "market_intelligence",
        "messages": [{"role": "user", "content": intel_content}]
    }

    # 3. Publish to the Mycelial topic
    target_topic = "quantum.mycelium.telemetry"
    await nc.publish(target_topic, json.dumps(payload).encode())
    print(f"PAYLOAD SECURED: Crypto Market Intelligence injected into {target_topic}")

    # 4. Graceful closure
    await nc.drain()

if __name__ == '__main__':
    asyncio.run(inject_crypto_intel())
