import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from dotenv import load_dotenv

load_dotenv()


async def main():
    from httpx import ASGITransport, AsyncClient

    from warden.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/negotiate",
            json={
                "intent_text": "Buy tamatar aur pyaz under 150 rupees total, fresh quality only",
                "max_price": 150,
                "allowed_categories": ["vegetables"],
                "red_lines": ["no stale items"],
                "scenario": "sabziwala_vs_mom",
            },
        )
        print(f"Status: {resp.status_code}")
        data = resp.json()
        tx_id = data.get("tx_id")
        print(f"Verdict: {data.get('verdict')} | Trust: {data.get('trust_score_trajectory')}")

        if tx_id:
            t = await client.get(f"/transcripts/{tx_id}")
            if t.status_code == 200:
                turns = t.json()
                print(f"\n{'=' * 60}")
                print("NEGOTIATION TRANSCRIPT")
                print("=" * 60)
                for turn in turns:
                    speaker = "MOM" if "buyer" in turn.get("speaker", "") else "SABZIWALA"
                    action = turn.get("action", "")
                    msg = turn.get("message", "")[:200]
                    reasoning = turn.get("reasoning", "")[:100]
                    print(f"\n{speaker} [{action}]")
                    print(f"  {msg}")
                    if reasoning:
                        print(f"  (thinking: {reasoning})")


if __name__ == "__main__":
    asyncio.run(main())
