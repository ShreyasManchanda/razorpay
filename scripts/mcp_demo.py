"""Call Warden over a real MCP stdio connection and print the decision."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from warden.keys import ensure_keys_loaded, get_private_key  # noqa: E402
from warden.mandates.schema import CartMandate  # noqa: E402
from warden.mandates.signing import sign_mandate  # noqa: E402


def _sample_request() -> dict:
    ensure_keys_loaded()
    cart = sign_mandate(
        CartMandate(
            agent_id="merchant_agent_v1",
            items=[{"name": "Tamatar", "price": 50}, {"name": "Pyaz", "price": 40}],
            total=90,
            category="vegetables",
            agreement_status="agreed",
            agreement_evidence=[
                "buyer_agreement:turn_2:merchant_offer_turn_1:Tamatar",
                "buyer_agreement:turn_2:merchant_offer_turn_1:Pyaz",
            ],
        ),
        get_private_key("merchant_agent_v1"),
    )
    return {
        "intent": {
            "agent_id": "buyer_agent_v1",
            "raw_goal_text": "Buy fresh tamatar aur pyaz under 150 rupees total, fresh quality only",
            "max_price": 150,
            "allowed_categories": ["vegetables"],
            "red_lines": ["no stale items"],
        },
        "signed_cart": cart.model_dump(),
        "transcript": [
            {
                "speaker": "buyer_agent",
                "action": "counter",
                "reasoning": "Buy fresh tamatar and pyaz under Rs.150, fresh quality only.",
                "message": "Bhaiya, tamatar aur pyaz fresh dena. Budget Rs.150 hai.",
            },
            {
                "speaker": "merchant_agent",
                "action": "offer",
                "reasoning": "Offer only the requested fresh vegetables inside budget.",
                "message": "Tamatar Rs.50 aur pyaz Rs.40, dono fresh hain.",
            },
            {
                "speaker": "buyer_agent",
                "action": "accept",
                "reasoning": "Buy fresh tamatar and pyaz under Rs.150, fresh quality only.",
                "message": "I accept fresh tamatar and pyaz for Rs.90.",
            },
            {
                "speaker": "merchant_agent",
                "action": "accept",
                "reasoning": "Lock the buyer-agreed cart.",
                "message": "Cart locked at Rs.90.",
            },
        ],
        "policy_name": "quick_commerce",
    }


async def run_demo() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "warden.mcp_server"],
        cwd=ROOT,
        env=environment,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            if [tool.name for tool in tools.tools] != ["warden_authorize_payment"]:
                raise RuntimeError("Warden MCP tool registration did not match the expected contract")
            result = await session.call_tool("warden_authorize_payment", {"request": _sample_request()})
            if result.isError:
                raise RuntimeError("Warden MCP authorization call failed")
            print(json.dumps(result.structuredContent, indent=2))


if __name__ == "__main__":
    asyncio.run(run_demo())
